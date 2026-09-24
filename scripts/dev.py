"""One-command local start.

    python scripts/dev.py            # real providers: needs keys in backend/.env
    python scripts/dev.py --demo     # no keys, no network: mock providers + mock judge + learned router + shadow mode

Creates backend/.venv and installs requirements on first run, creates backend/.env from the example
if missing (never overwrites it), installs frontend packages on first run, then starts the API on
http://localhost:8000 and the console on http://localhost:5173. Ctrl+C stops both.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import venv
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BACKEND, FRONTEND = ROOT / "backend", ROOT / "frontend"
VENV = BACKEND / ".venv"
PY = VENV / ("Scripts/python.exe" if os.name == "nt" else "bin/python")

DEMO_ENV = {
    "USE_MOCK_PROVIDERS": "true",
    "JUDGE_PROVIDER": "mock",
    "EVALUATE_ON_CHAT": "true",
    "ROUTER_TYPE": "learned",
    "EMBEDDING_MODEL": "hashing",
    "LEARNED_MIN_SAMPLES": "20",
    "SHADOW_ROUTER_ENABLED": "true",
    "DATABASE_URL": "sqlite:///./data/demo.db",
}


def run(cmd: list[str], cwd: Path) -> None:
    print("$", " ".join(cmd), flush=True)
    subprocess.run(cmd, cwd=cwd, check=True, shell=(os.name == "nt" and cmd[0] == "npm"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--demo", action="store_true", help="mock providers, no API keys needed")
    parser.add_argument("--no-frontend", action="store_true")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()

    if not PY.exists():
        print("creating backend/.venv ...")
        venv.create(VENV, with_pip=True)
        run([str(PY), "-m", "pip", "install", "-r", "requirements.txt"], BACKEND)
    env_file = BACKEND / ".env"
    if not env_file.exists():
        shutil.copy(BACKEND / ".env.example", env_file)
        print("created backend/.env from .env.example (add provider keys there for real providers)")

    procs: list[subprocess.Popen] = []
    env = {**os.environ, **(DEMO_ENV if args.demo else {})}
    try:
        procs.append(
            subprocess.Popen([str(PY), "-m", "uvicorn", "app.main:app", "--reload", "--port", str(args.port)], cwd=BACKEND, env=env)
        )
        if not args.no_frontend and shutil.which("npm"):
            if not (FRONTEND / "node_modules").exists():
                run(["npm", "install"], FRONTEND)
            procs.append(subprocess.Popen(["npm", "run", "dev"], cwd=FRONTEND, shell=(os.name == "nt")))
        elif not args.no_frontend:
            print("npm not found: starting the API only (install Node 18+ for the console)")
        print(f"\nAPI     http://localhost:{args.port}/docs\nConsole http://localhost:5173\n(Ctrl+C to stop)\n")
        for p in procs:
            p.wait()
    except KeyboardInterrupt:
        pass
    finally:
        for p in procs:
            if p.poll() is None:
                p.terminate()
    return 0


if __name__ == "__main__":
    sys.exit(main())
