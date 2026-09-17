# Adaptive Model Router → Adaptive AI Gateway: Technical Audit

Audit-only. No files were modified, deleted, or renamed as part of this document.

---

## A. Current Architecture

```
React dashboard (frontend/)
        │  axios → /api, /health (proxied by Vite); /v1 called directly
        ▼
FastAPI app (backend/app/main.py)
        │
        ├── app/api/*           one router module per resource, all mounted in main.py
        ├── app/router/         feature extraction → task classification → difficulty → policy
        │                       4 interchangeable Router implementations (rule_based/tfidf/embedding/bert)
        ├── app/models/registry.py   JSON-backed model registry, tier lookup, tier overrides
        ├── app/providers/      one adapter per vendor + mock; common BaseModelProvider interface
        ├── app/services/       chat orchestration, fallback executor, 4 separate in-memory job managers
        ├── app/evaluation/     judge (mock/openai), metrics aggregation, benchmark + experiment runners
        ├── app/training/       3 trainers (tfidf/embedding/bert), joblib artifact registry
        ├── app/datasets/       preference-dataset generation, JSONL storage
        └── app/db/             sqlite3 connection + hand-written repository (no ORM)
```

Single FastAPI process, single SQLite file, in-memory job state, synchronous request/response chat (no streaming, no queueing). Everything is stateless between restarts except what's persisted to `data/` and `models/`.

---

## B. Current Features (verified in code)

| Feature | Where |
|---|---|
| Prompt → task type (13 types) via keyword/regex scoring | [task_classifier.py](backend/app/router/task_classifier.py) |
| Prompt → difficulty score (0–1) via feature-weighted formula | [difficulty.py](backend/app/router/difficulty.py) |
| Tier selection: cheapest tier meeting `QUALITY_FLOOR` | [policy.py](backend/app/router/policy.py) |
| 4 router backends behind one interface, swappable via `ROUTER_TYPE` | [base.py](backend/app/router/base.py) |
| 5 provider adapters (OpenAI, Anthropic, Google, OpenAI-compatible, Mock) | [providers/](backend/app/providers/) |
| Model registry: JSON file, tier/cost/quality metadata, CRUD, tier-override env vars | [registry.py](backend/app/models/registry.py) |
| Chat orchestration: route → generate → cost → judge → log | [chat.py](backend/app/services/chat.py) |
| Fallback: provider-error retry across tiers + one-shot quality-triggered escalation | [fallback.py](backend/app/services/fallback.py) |
| LLM-as-judge: deterministic mock scorer or real OpenAI-only judge | [judge.py](backend/app/evaluation/judge.py) |
| Routing-log SQLite table → aggregate metrics (cost saved, quality retention, strong usage, fallback rate) | [repository.py](backend/app/db/repository.py) |
| Benchmark runner: Always Strong / Always Cheap / Adaptive Router comparison | [evaluation/benchmark.py](backend/app/evaluation/benchmark.py) |
| Preference-dataset generation (3-tier response + judge label) for training | [datasets/generator.py](backend/app/datasets/generator.py) |
| 3 trainable routers (TF-IDF+LR, SentenceTransformer+classifier, BERT-MLP) | [training/](backend/app/training/) |
| Final-evaluation suite (strategy / quality-floor / router comparisons) | [evaluation/experiments.py](backend/app/evaluation/experiments.py) |
| OpenAI-compatible `/v1/chat/completions`, `/v1/models`, optional bearer auth, `X-Quality-Floor` header | [openai_compat.py](backend/app/api/openai_compat.py) |
| Full React dashboard (9 pages) over all of the above | [frontend/src/pages/](frontend/src/pages/) |
| 60 pytest tests, all against mock providers/judge | [tests/](backend/tests/) |

---

## C. Current Strengths — do not touch

- **Router abstraction is genuinely clean.** `create_router(router_type)` returns one of four interchangeable implementations behind a single `Router.route()` interface. Adding a 5th (e.g. a bandit) is additive, not invasive. **Preserve this contract exactly.**
- **Provider abstraction is equally clean.** `BaseModelProvider.generate()` / `.is_available()` / `.estimate_cost()` is a small, complete surface. `get_provider_for_model()` is the single chokepoint for provider dispatch — a gateway can hang capability/health tracking off this without touching adapters.
- **Fallback chain construction is already tier-aware and configurable** (`tier_up` vs `strong_only`, max attempts, retryable-error allowlist). The escalation logic in [fallback.py](backend/app/services/fallback.py) is close to what a gateway needs; it mainly needs to run for manual (non-`auto`) requests too and support multi-step quality re-escalation.
- **The routing decision is transparent by construction** — `RoutingDecision` already carries task type, difficulty, per-tier cost/quality/latency estimates, and a reason string. This is exactly the shape a "why did you pick this model" gateway feature needs; no new data model required.
- **Registry tier-override mechanism** (`SMALL_MODEL_ID` etc.) is a clean seam for user/request-level model preference — extend it rather than replacing it.
- **Tests run entirely offline** against mock providers/judge. Any gateway change should keep this property; it's what makes the test suite fast and free to run in CI.
- **Schema-first design** (Pydantic throughout) — API contracts are enforced, not conventions. New endpoints should follow the same `schemas/` + `api/` split.

---

## D. Current Weaknesses (fragile / technically weak)

1. **In-memory jobs, 4 separate managers, no persistence.** [jobs.py](backend/app/services/jobs.py), plus near-identical copies in `dataset_jobs.py`, `training_jobs.py`, `experiment_jobs.py` — four duplicated implementations of the same pattern (`dict[str, Status]` + `asyncio.create_task`, no cancellation, no retry, lost on restart). This is the single largest piece of duplicated logic in the backend.
2. **Judge is hardcoded to OpenAI.** [judge.py:81-115](backend/app/evaluation/judge.py#L81-L115) calls `https://api.openai.com/v1/chat/completions` directly — it doesn't go through the provider abstraction, doesn't honor `OPENAI_COMPATIBLE_BASE_URL`, and can't use Anthropic/Google as a judge even though those adapters exist.
3. **Judge invoked redundantly on the auto path.** In `ChatService.chat()`, when `model == "auto"`, the judge scores the response once inside `FallbackExecutor` (to decide on escalation) and again in `_evaluate_response_quality` for logging ([chat.py:96](backend/app/services/chat.py#L96) and [chat.py:108](backend/app/services/chat.py#L108)) — two judge calls minimum, three if escalation fires. With `JUDGE_PROVIDER=openai` this doubles judge cost and latency for every auto-routed request.
4. **Quality-based escalation only applies to `model="auto"` requests.** A user who pins `model="gpt-4o-mini"` gets provider-error fallback but never quality escalation — `quality_evaluator` is only constructed when `request.model == AUTO_MODEL` ([chat.py:93](backend/app/services/chat.py#L93)).
5. **Quality escalation is one-shot, not chained.** `FallbackExecutor` escalates once on low quality; if the escalated response is *also* below the floor, there's no second attempt ([fallback.py:202-238](backend/app/services/fallback.py#L202-L238)).
6. **Metrics computation loads the entire `routing_logs` table into Python on every call.** [repository.py:82-83](backend/app/db/repository.py#L82-L83) — `SELECT * ... ORDER BY id DESC` with no `LIMIT`, no date filtering, no SQL-side aggregation. Fine at hundreds of rows, not fine at production volume.
7. **No concept of provider/model health or circuit breaking.** `is_available()` only checks whether an API key is configured ([factory.py](backend/app/providers/factory.py)), not whether the provider is currently erroring. A provider having a bad day gets retried on every single request with no backoff or temporary demotion.
8. **No per-request timeout budget across the fallback chain.** `PROVIDER_TIMEOUT` applies per provider call; a 3-attempt fallback chain can take up to 3× the configured timeout with no overall request deadline.
9. **No streaming anywhere** — not in provider adapters, not in `/api/chat`, not in `/v1/chat/completions`. This is a hard blocker for "real-world/day-to-day" usage; most OpenAI-SDK consumers expect `stream=True` to work.
10. **No authentication on the native API**, only on `/v1/*` (and only if `ROUTER_API_KEY` is set). `/api/chat`, `/api/models`, etc. are open by default.
11. **Task classification is pure keyword/regex matching** ([task_classifier.py](backend/app/router/task_classifier.py), [features.py](backend/app/router/features.py)) — no embeddings, no learned model. It's fast and explainable but will misclassify prompts that don't contain its keyword vocabulary (e.g. a coding question phrased without any of `CODE_PATTERNS`).
12. **No per-user/per-tenant concept anywhere** — no request attribution beyond a SHA-256 prompt hash. "User preference" and "historical performance per user" from the target list have no data model to attach to yet.
13. **No capability declaration for models beyond a flat `capabilities: list[str]`** — no vision/tool-use/context-length-aware routing; a prompt requiring image input or function calling would be routed purely on text difficulty.
14. **CORS is wide open on methods/headers** (`allow_methods=["*"], allow_headers=["*"]`) — acceptable for a dev dashboard, worth tightening before "real-world" use.
15. **`docker-compose.yml` references Dockerfiles that don't exist** in `backend/` or `frontend/` — not a gateway concern, but it undermines "production-style" framing.

---

## E. Missing Product Features

- Single unified gateway endpoint usable by *any* client shape (not just OpenAI's), e.g. a generic `/v1/complete` that also accepts non-chat use cases.
- Per-request/per-API-key model preference and policy override (currently only global env vars or the ad hoc `X-Quality-Floor` header).
- Request-level metadata/tagging (e.g. `user_id`, `application`, `tags`) for later cost/quality breakdown — schema has none of this today.
- Usage/cost reporting scoped to a caller, not just global aggregate metrics.
- Streaming responses (SSE) on both native and OpenAI-compatible endpoints.
- A simple API-key system beyond the single global `ROUTER_API_KEY` (even a static multi-key allowlist would unblock multi-tenant demos).

## F. Missing Intelligence Features

- **Model capability awareness** in routing: context window, vision, tool/function calling, JSON mode — the policy only reasons about tier/cost/quality/difficulty today, not "can this model even do what's asked."
- **Historical performance feedback loop**: `requests_by_model`/task metrics exist, but nothing feeds them *back* into routing decisions (e.g. "this model has degraded quality on `coding` this week, weight it down").
- **User/session preference weighting** (e.g. "always prefer low latency for this caller") — no concept of a caller profile.
- **Embedding-based task classification** as an option alongside the keyword classifier, for prompts outside the keyword vocabulary. (Separate from the existing tfidf/embedding/bert *routers*, which classify strong-vs-not, not task type.)

## G. Missing Reliability Features

- **Provider/model health tracking with circuit breaking** — track recent error rate per model, temporarily skip a model that's failing instead of retrying it every request.
- **Overall request-level timeout/deadline** spanning the whole fallback chain, not just per-call.
- **Persistent job state** for the four background job types (dataset/training/benchmark/experiments) — currently lost on restart, and duplicated across four near-identical in-memory managers.
- **Idempotency / retry-safety on the caller side** — no request ID or idempotency key support.
- **Rate limiting** — explicitly out of scope per the instructions, but worth naming as a gap for later.

## H. Missing Developer Experience Features

- **Unified job-status abstraction** — one `JobManager` generic over payload type instead of four copies.
- **A single "why did the gateway choose this model" trace** that's consistent across `/api/route`, `/api/chat`, and `/v1/chat/completions` — today `/v1/chat/completions`'s optional `router` metadata block and `/api/chat`'s `routing`/`fallback` fields are separately shaped.
- **SDK/quickstart snippets beyond curl + one Python OpenAI-SDK example** — no equivalent for Anthropic-shaped or LangChain-shaped clients.
- **Structured request logs a developer can query** (currently only aggregate `/api/metrics`, no per-request lookup/list endpoint against `routing_logs`).

---

## I. Recommended Implementation Order

Ranked by demo/evaluation impact → real-world usefulness → technical depth → reusability → risk of breaking existing functionality, smallest high-impact changes first:

1. **Unify judge invocation on the chat path** (fix #3) — pure internal refactor, zero API-surface change, immediately halves judge cost/latency for every auto request. Lowest risk, does today's system correctly.
2. **Extend quality escalation to manual (`model=`) requests** (fix #4) — small change to `chat.py`, makes fallback behave consistently regardless of how the model was selected. High real-world value (most gateway callers pin a model most of the time).
3. **Route judge calls through the provider abstraction** instead of a hardcoded OpenAI HTTP call (fix #2) — lets Anthropic/Google/compatible act as judge, removes a special case, strictly additive.
4. **Add model capability metadata + capability-aware routing gate** (context window, vision, tool-calling) — extends `ModelMetadata` and `policy.py`'s eligibility filter; the biggest single step toward "the system decides based on capabilities," and it's additive to the existing tier-eligibility loop, not a rewrite of it.
5. **Add a generic, persistent `JobManager`** collapsing the four duplicated in-memory managers into one (SQLite-backed status table, same repository pattern already used for routing logs) — removes the largest duplication and gives jobs restart-survivability, a concrete reliability win with moderate effort.
6. **Add provider/model health tracking + circuit breaking** in `get_provider_for_model`/`FallbackExecutor` — track a rolling error count per model, skip models that are currently failing before retrying them. Meaningful reliability story for a demo ("the gateway noticed this model was down and routed around it").
7. **Add per-request metadata (`user_id`/`tags`) + scoped usage reporting** — schema/DB extension, additive column, enables the "user preference" and "historical performance" framing without a tenant system.
8. **Streaming support** — highest real-world impact but the deepest change (touches every provider adapter, both chat endpoints, and the frontend Chat page); sequence after the smaller wins above so it lands on a more solid base.

## J. Top 5 Features to Build First

1. **Fix double judge invocation + extend quality escalation to manual model requests** (items 1–2 above, bundled — they touch the same function and are trivially safe).
2. **Judge via provider abstraction, provider-agnostic.**
3. **Capability-aware routing** (context window / vision / tool-calling as hard eligibility filters, not just soft capability-tag scoring).
4. **Unified persistent JobManager** replacing the four in-memory copies.
5. **Provider health tracking with circuit breaking** in the fallback path.

These five are chosen because each is: independently shippable without touching the router/provider public interfaces (Section C), individually testable against the existing mock-only test suite, and — as a set — turns "picks a tier by difficulty" into "picks a model by capability, cost, quality, *and* live reliability," which is the actual gap between today's router and a gateway.

---

## Proposed Phase 1

Scope: items 1–4 of the Top 5 (defer circuit breaking to Phase 2, since it benefits from Phase 1's health-signal groundwork being in place first — specifically, having per-request outcome logging already flowing through one job/metrics path makes the "recent error rate per model" computation trivial to add on top rather than a new subsystem).

1. Collapse the double judge call in `ChatService.chat()` into a single evaluation shared between fallback-escalation and logging.
2. Make `quality_evaluator` unconditional (not gated on `model == "auto"`) so pinned-model requests get the same escalation behavior as routed ones.
3. Route `LLMJudge` through `get_provider_for_model`/the existing provider adapters instead of a hardcoded OpenAI call.
4. Add `context_window` capability checks (already present as a field) and new `supports_vision` / `supports_tools` booleans to `ModelMetadata`; add a hard filter step in `policy.evaluate_tiers` before the cost/quality comparison.
5. Introduce a single generic `JobManager[T]` in `app/services/jobs.py`, backed by a new `jobs` SQLite table (same connection/repository pattern as `routing_logs`), and migrate the three duplicate managers (`dataset_jobs.py`, `training_jobs.py`, `experiment_jobs.py`) onto it without changing their public API surface (`create_job`/`start_job`/`get_job` signatures stay the same, so `app/api/*.py` callers don't change).

Each step is independently testable against the existing mock-provider test suite, none changes a public schema in a breaking way, and none touches the router/provider abstractions identified as strengths in Section C.
