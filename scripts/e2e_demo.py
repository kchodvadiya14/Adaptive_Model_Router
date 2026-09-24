"""End-to-end local run of the whole gateway with no API keys and no network.

    python scripts/e2e_demo.py [--encoder hashing|sentence-transformers/all-MiniLM-L12-v2] [--keep]

Starts the real FastAPI app in a subprocess (mock providers, mock judge, learned router with shadow
mode on, isolated temp state), sends prompts through gateway -> router -> provider -> judge -> log,
and checks that every stage did its job: routing, cold-start fallback, switch to the learned router
once judged data exists, embedding collection, shadow logging, the quality guard endpoint, the
OpenAI-compatible route, and API-key protection.

The mock providers only simulate answers (stronger tiers write fuller ones), so the numbers printed
here demonstrate that the pipeline works. They are NOT evidence about real model quality or savings.
"""

from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
BACKEND = ROOT / "backend"
PROMPTS = json.loads((BACKEND / "data/benchmarks/routing_prompts_extended.json").read_text(encoding="utf-8"))


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def python_for_backend() -> str:
    venv = BACKEND / (".venv/Scripts/python.exe" if os.name == "nt" else ".venv/bin/python")
    return str(venv) if venv.exists() else sys.executable


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--encoder", default="hashing")
    parser.add_argument("--keep", action="store_true", help="keep the temp state directory")
    parser.add_argument("--min-samples", type=int, default=20)
    args = parser.parse_args()

    port, key = free_port(), "demo-key"
    state = Path(tempfile.mkdtemp(prefix="router-e2e-"))
    env = {
        **os.environ,
        "PYTHONPATH": str(BACKEND),
        "APP_ENV": "production",
        "USE_MOCK_PROVIDERS": "true",
        "LOG_LEVEL": "WARNING",
        "JUDGE_PROVIDER": "mock",
        "EVALUATE_ON_CHAT": "true",
        "ROUTER_TYPE": "learned",
        "EMBEDDING_MODEL": args.encoder,
        "LEARNED_MIN_SAMPLES": str(args.min_samples),
        "SHADOW_ROUTER_ENABLED": "true",
        "QUALITY_FLOOR": "0.80",
        "FALLBACK_ON_QUALITY_BELOW": "0.60",
        "DATABASE_URL": f"sqlite:///{(state / 'router.db').as_posix()}",
        "ROUTER_API_KEY": key,
        "GROQ_API_KEY": "",
        "GOOGLE_API_KEY": "",
    }
    # cwd = temp dir: the app's relative data paths (registry, datasets, reports) land there, not in the repo.
    server = subprocess.Popen(
        [python_for_backend(), "-m", "uvicorn", "app.main:app", "--port", str(port), "--log-level", "warning"],
        cwd=state, env=env,
    )
    base = f"http://127.0.0.1:{port}"
    auth = {"Authorization": f"Bearer {key}"}
    failures: list[str] = []

    def check(ok: bool, what: str) -> None:
        print(f"  [{'ok' if ok else 'FAIL'}] {what}")
        if not ok:
            failures.append(what)

    try:
        with httpx.Client(base_url=base, timeout=120) as http:
            for _ in range(120):
                try:
                    if http.get("/health").status_code == 200:
                        break
                except httpx.HTTPError:
                    pass
                time.sleep(0.5)
            else:
                print("backend did not start")
                return 1
            print(f"backend up on {base} (state in {state})")

            print("\n1. Security")
            check(http.get("/api/models").status_code == 401, "/api/* rejects requests without the key")
            check(http.get("/health").status_code == 200, "/health stays open")

            print("\n2. Cold start: no judged data yet, so the static fallback routes")
            first = http.post("/api/chat", headers=auth, json={"model": "auto", "messages": [{"role": "user", "content": PROMPTS[0]["prompt"]}]})
            check(first.status_code == 200, "auto-routed chat succeeds with mock providers")
            check(first.json()["routing"]["features"]["router_type"] == "learned:fallback", "cold start uses the fallback router")

            print(f"\n3. Traffic: {len(PROMPTS)} prompts x 2 passes through gateway -> router -> provider -> judge")
            phases: list[dict] = []
            for pass_number in (1, 2):
                chosen, kinds, cost = {}, {}, 0.0
                for i, item in enumerate(PROMPTS):
                    r = http.post(
                        "/api/chat", headers=auth,
                        json={"model": "auto", "request_id": f"p{pass_number}-{i}", "messages": [{"role": "user", "content": item["prompt"]}]},
                    )
                    if r.status_code != 200:
                        failures.append(f"chat {r.status_code}: {r.text[:200]}")
                        continue
                    body = r.json()
                    chosen[body["model"]] = chosen.get(body["model"], 0) + 1
                    kind = body["routing"]["features"]["router_type"]
                    kinds[kind] = kinds.get(kind, 0) + 1
                    cost += body["cost"]["total_cost"]
                phases.append({"models": chosen, "router": kinds, "cost": cost})
                print(f"  pass {pass_number}: router={kinds} models={chosen} cost=${cost:.5f}")
            check(phases[0]["router"].get("learned:fallback", 0) > 0, "pass 1 began on the fallback router")
            check(phases[1]["router"].get("learned", 0) > 0, "pass 2 used the learned router once enough data existed")

            print("\n4. What was collected")
            metrics = http.get("/api/metrics", headers=auth).json()
            check(metrics["total_requests"] >= 2 * len(PROMPTS), f"routing log has {metrics['total_requests']} requests")
            perf = http.get("/api/performance/models", headers=auth).json()["models"]
            check(any(m["average_quality_score"] is not None for m in perf), "judged quality recorded per model")

            print("\n5. Shadow mode (records would-be choices; served requests unchanged)")
            pinned = http.post(
                "/api/chat", headers=auth,
                json={"model": "openai/gpt-oss-120b", "messages": [{"role": "user", "content": "What is the capital of France?"}]},
            )
            check(pinned.status_code == 200 and pinned.json()["model"] == "openai/gpt-oss-120b", "a pinned model is served exactly as pinned")
            shadow = http.get("/api/shadow/summary", headers=auth).json()
            check(shadow["requests"] >= 2 * len(PROMPTS), f"{shadow['requests']} shadow decisions logged")
            print(f"     agreement {shadow['agreement_rate']:.0%}, estimated cost change {shadow['estimated_cost_change']:+.1%}  (shadow quality is predicted, not measured)")

            print("\n6. Quality guard and calibration endpoints")
            segments = http.get("/api/performance/segments", headers=auth).json()["segments"]
            check(len(segments) > 0, f"{len(segments)} task segments monitored")
            calibration = http.get("/api/performance/calibration", headers=auth, params={"min_samples": 5})
            check(calibration.status_code == 200, "calibration preview works")

            print("\n7. OpenAI-compatible route")
            v1 = http.post("/v1/chat/completions", headers=auth, json={"model": "auto", "messages": [{"role": "user", "content": "Say hi"}]})
            check(v1.status_code == 200 and v1.json()["choices"][0]["message"]["content"], "/v1/chat/completions answers")
    finally:
        server.terminate()
        try:
            server.wait(timeout=10)
        except subprocess.TimeoutExpired:
            server.kill()
        if not args.keep:
            import shutil

            shutil.rmtree(state, ignore_errors=True)

    print("\nRESULT:", "FAILED" if failures else "all checks passed")
    for f in failures:
        print("  -", f)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
