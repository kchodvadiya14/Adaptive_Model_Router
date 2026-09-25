# Reference

Configuration, API, console and developer reference. For the design see [ARCHITECTURE.md](ARCHITECTURE.md); for routing logic see [HOW_ROUTING_WORKS.md](HOW_ROUTING_WORKS.md).

Contents: [Providers and models](#providers-and-models) · [Configuration](#configuration) · [Using the API](#using-the-api) · [Endpoint list](#endpoint-list) · [Console](#console) · [Training the ML routers](#training-the-ml-routers) · [Benchmarks and experiments](#benchmarks-and-experiments) · [Development](#development)

## Providers and models

The default registry runs on free-tier models:

| Tier | Model | Provider | Paid list price (in / out per 1M tokens) |
|---|---|---|---|
| small | `openai/gpt-oss-20b` | Groq | $0.075 / $0.30 |
| small (pinned use) | `nvidia/nemotron-3-super-120b-a12b:free` | OpenRouter | $0.08 / $0.45 |
| medium | `openai/gpt-oss-120b` (also the quality judge) | Groq | $0.15 / $0.60 |
| strong | `gemini-3.5-flash-lite` | Google | $0.30 / $2.50 |
| strong (pinned use) | `gemini-3.5-flash` | Google | $1.50 / $9.00 |

Costs are the providers' published paid prices (September 2026), so cost and "saved vs strong" figures show what the traffic would cost on a paid plan even though free-tier calls are billed $0. Put keys in `backend/.env`:

```env
GROQ_API_KEY=...
GOOGLE_API_KEY=...
OPENAI_COMPATIBLE_BASE_URL=https://openrouter.ai/api/v1
OPENAI_COMPATIBLE_API_KEY=...
JUDGE_PROVIDER=registry
JUDGE_MODEL_ID=openai/gpt-oss-120b
```

Free-tier limits matter: Gemini 3.5 Flash allows about 20 requests a day and a free OpenRouter key about 50, which is why those two are secondary models used only when pinned. Batch jobs retry rate-limited calls with backoff and skip a prompt only if it keeps failing.

The fallback router resolves each tier to the **cheapest enabled model** in it that passes capability, health and constraint filters. The learned router scores every enabled model. The offline mock models used by the tests live in `backend/tests/model_fixtures.py`; with `USE_MOCK_PROVIDERS=true` *every* registry model is answered by the mock provider instead.

## Configuration

All settings are environment variables read from `backend/.env` (copy `backend/.env.example`). The tables below are authoritative and match `backend/app/config/settings.py`.

### Routing

| Variable | Description | Default |
|---|---|---|
| `ROUTER_TYPE` | `rule_based` · `learned` · `tfidf` · `embedding` · `bert` | `rule_based` |
| `QUALITY_FLOOR` | Minimum expected quality a model must meet to be eligible | `0.90` |
| `ROUTING_THRESHOLD` | Trained ML routers: P(strong is better) above which the strong tier wins | `0.60` |
| `COST_PRIORITY` / `LATENCY_PRIORITY` | Weights for the static router's cost/latency trade-off | `0.7` / `0.3` |

### Learned routing, quality guard and shadow mode

| Variable | Description | Default |
|---|---|---|
| `EMBEDDING_MODEL` | Prompt encoder (`sentence-transformers/all-MiniLM-L12-v2`; `hashing` is a dependency-free, much cruder fallback) | MiniLM-L12 |
| `COLLECT_EMBEDDINGS` | Keep each prompt's embedding (never its text) with judged outcomes; always on for `learned` | `false` |
| `LEARNED_MIN_SAMPLES` | Judged, embedded outcomes needed before `learned` replaces the static fallback | `50` |
| `LEARNED_K` / `LEARNED_PRIOR_WEIGHT` / `LEARNED_MIN_SIMILARITY` | Neighbours used, prior strength, similarity cut-off | `40` / `3.0` / `0.5` |
| `EXPLORATION_BONUS` | Optimism for models with little evidence on a kind of prompt | `0.10` |
| `GUARD_WINDOW` / `GUARD_MIN_SAMPLES` / `GUARD_TOLERANCE` | Quality guard: recent answers per task type, minimum to act, allowed shortfall below the floor | `50` / `20` / `0.05` |
| `SHADOW_ROUTER_ENABLED` | Log what the learned router would choose for every request without acting on it | `false` |

### Fallback

| Variable | Description | Default |
|---|---|---|
| `FALLBACK_ENABLED` | Escalate a tier on retryable failure or low quality | `true` |
| `MAX_FALLBACK_ATTEMPTS` | Models tried per request (1 to 5) | `3` |
| `FALLBACK_ON_QUALITY_BELOW` | Re-run at a higher tier if the judge scores below this | `0.85` |
| `FALLBACK_ESCALATION` | `tier_up` (one step at a time) or `strong_only` | `tier_up` |

### Health and circuit breaking

| Variable | Description | Default |
|---|---|---|
| `HEALTH_FAILURE_THRESHOLD` | Consecutive retryable failures before a model's circuit opens | `3` |
| `HEALTH_COOLDOWN_SECONDS` | Wait before an open circuit allows one half-open trial | `30` |
| `REQUEST_MIN_ATTEMPT_BUDGET_MS` | With `timeout_ms` set, do not start another step with less than this much budget left | `10` |

### Models and providers

| Variable | Description | Default |
|---|---|---|
| `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` / `GOOGLE_API_KEY` / `GROQ_API_KEY` | Provider credentials | empty |
| `OPENAI_COMPATIBLE_BASE_URL` / `OPENAI_COMPATIBLE_API_KEY` | Any OpenAI-shaped endpoint (vLLM, Ollama, OpenRouter, ...) | empty |
| `SMALL_MODEL_ID` / `MEDIUM_MODEL_ID` / `STRONG_MODEL_ID` | Pin one model per tier | empty |
| `USE_MOCK_PROVIDERS` | Answer every model with the deterministic mock provider (no keys, no network) | `false` |
| `PROVIDER_TIMEOUT` | Per-provider-call timeout, seconds | `60` |
| `MAX_REQUEST_MESSAGES` | Max messages accepted per chat request | `50` |

### Judging

| Variable | Description | Default |
|---|---|---|
| `JUDGE_PROVIDER` | `mock` (heuristic, offline), `openai`, or `registry` (any registry model through the gateway's own providers) | `mock` |
| `JUDGE_MODEL_ID` | Judge model for `openai` or `registry` | `gpt-4o-mini` |
| `EVALUATE_ON_CHAT` | Score every chat response inline | `true` |

### Server and storage

| Variable | Description | Default |
|---|---|---|
| `BACKEND_HOST` / `BACKEND_PORT` | Bind address | `0.0.0.0` / `8000` |
| `CORS_ORIGINS` | Comma-separated allowed origins | `http://localhost:5173,...` |
| `DATABASE_URL` | SQLite database | `sqlite:///./data/router.db` |
| `STORE_PROMPTS` | Persist raw prompt text in logs | `false` |
| `LOG_LEVEL` | Python log level | `INFO` |
| `ROUTER_API_KEY` | When set, `/api/*` and `/v1/*` require `Authorization: Bearer <key>` (`/health` stays open) | empty |

The console sends the key from `localStorage['router_api_key']` or the build-time `VITE_API_KEY`.

## Using the API

Interactive docs are served at `/docs`. Add `-H "Authorization: Bearer <key>"` to every call when `ROUTER_API_KEY` is set.

```bash
# Routing decision only: no model call, no cost
curl -X POST http://localhost:8000/api/route -H "Content-Type: application/json" \
  -d '{"prompt":"Explain the CAP theorem"}'

# Chat with automatic routing, a caller identity, a cost cap and a hard deadline
curl -X POST http://localhost:8000/api/chat -H "Content-Type: application/json" \
  -d '{"model":"auto","messages":[{"role":"user","content":"Explain the CAP theorem"}],"user_id":"alice","tags":{"app":"support-bot"},"max_cost":0.01,"timeout_ms":15000}'

# A soft preference, honoured only if that model passes every eligibility check
curl -X POST http://localhost:8000/api/chat -H "Content-Type: application/json" \
  -d '{"model":"auto","preferred_model":"openai/gpt-oss-120b","messages":[{"role":"user","content":"Hello"}]}'

# Metrics, usage, circuit health, performance, shadow comparison, per-task quality
curl http://localhost:8000/api/metrics
curl "http://localhost:8000/api/usage?user_id=alice"
curl http://localhost:8000/api/health/models
curl http://localhost:8000/api/performance/models
curl http://localhost:8000/api/shadow/summary
curl http://localhost:8000/api/performance/segments
```

### OpenAI-compatible API

Point any OpenAI SDK at the gateway and set `model` to `"auto"`:

```python
from openai import OpenAI

client = OpenAI(base_url="http://localhost:8000/v1", api_key="not-needed")   # your ROUTER_API_KEY if set
response = client.chat.completions.create(
    model="auto",
    messages=[{"role": "user", "content": "Summarise merge sort."}],
    user="alice",                       # recorded as user_id
    metadata={"app": "support-bot"},    # recorded as usage tags
)
print(response.choices[0].message.content)
print(response.model)   # the model actually chosen
```

| Header | Effect |
|---|---|
| `X-Quality-Floor: 0.95` | Override the quality floor for this request |
| `X-Request-ID: <id>` | Correlation id, echoed on the response and in logs |
| `X-Request-Timeout-Ms: 15000` | Wall-clock budget for the whole request |
| `Authorization: Bearer <key>` | Required when `ROUTER_API_KEY` is set |

Responses use the standard OpenAI shape plus an optional `router` block (task type, tier, cost, fallback info, request id). `stream=true` is not supported.

## Endpoint list

| Method | Endpoint | Description |
|---|---|---|
| GET | `/health` | Service status (always open) |
| POST | `/api/route` | Routing decision only; supports `preferred_model`, `max_cost`, `max_latency_ms` |
| GET | `/api/router/status` | Active router type and configuration |
| POST | `/api/chat` | Chat completion; `model:"auto"`, request metadata, deadline, constraints |
| GET, POST | `/api/models` | List / register models |
| GET, PATCH | `/api/models/{id}` | Model detail / update |
| POST | `/api/models/{id}/enable` · `/disable` | Enable / disable |
| GET | `/api/health/models` | Circuit-breaker state per model |
| GET | `/api/performance/models` | Historical per-model performance (filterable) |
| GET | `/api/performance/segments` | Recent judged quality per task type and whether the guard has tripped |
| GET | `/api/performance/calibration` | Preview quality scores calibrated against judged outcomes |
| POST | `/api/performance/calibration/apply` | Write calibrated quality scores to the registry |
| GET | `/api/shadow/summary` | Agreement and estimated cost change of shadowed decisions |
| GET | `/api/usage` | Scoped usage totals and breakdowns |
| POST | `/api/evaluate` | Judge a prompt/response pair |
| GET | `/api/metrics` | Aggregated routing metrics |
| POST · GET | `/api/benchmark` · `/api/benchmark/status/{job_id}` · `/api/benchmarks[/{id}]` | Benchmark jobs and reports |
| POST · GET | `/api/dataset/generate` · `/api/dataset/generate/status/{job_id}` · `/api/dataset[/{id}]` | Preference-dataset generation and records |
| POST | `/api/dataset/{id}/human-eval` | Override a label by hand |
| POST · GET | `/api/training/start` · `/api/training/status/{job_id}` · `/api/training/models` | Train and list ML routers |
| POST · GET | `/api/experiments/run` · `/api/experiments/status/{job_id}` · `/api/experiments[/{id}]` | Evaluation experiments |
| POST | `/v1/chat/completions` | Drop-in OpenAI chat completions |
| GET | `/v1/models` · `/v1/models/{id}` | Models, including the virtual `auto` |

Request metadata (`request_id`, `user_id`, `session_id`, free-form `tags`) travels into the routing log; `GET /api/usage` reports totals, cost and latency with breakdowns by user, model and tag, filterable by each.

## Console

| Page | What it does |
|---|---|
| Overview | System status and quick navigation |
| Chat | Send prompts, see the routing explanation and per-model estimates (marked measured or assumed), override the quality floor |
| Models | Registry create/edit/enable/disable, live circuit health and historical performance |
| Analytics | Cost reduction, quality retention, strong-model usage, fallback rate, breakdowns by tier and task |
| Benchmark | Always Strong / Always Cheap / Adaptive Router over a prompt set; past reports |
| Dataset | Generate preference datasets, browse records, review and override labels |
| Training | Train an ML router, watch progress, compare runs |
| Experiments | Run the evaluation suite and read reports |
| Settings | Current routing, fallback and health configuration (read-only) |

Stack: React 18, TypeScript, Vite, Tailwind CSS, Recharts, React Router, axios, lucide-react. A small shared component library backs every page.

## Training the ML routers

The `tfidf`, `embedding` and `bert` routers are separate from the learned router. They predict **P(the strong model is meaningfully better)** from a preference dataset generated by the system itself: each prompt is answered at all three tiers, scored by the judge, and reduced to a binary label. None ships trained; selecting one before training raises `FileNotFoundError`. The embedding router needs `pip install -r requirements-ml.txt`.

```bash
# 1. Generate a preference dataset (at least 4 labelled records are needed to train)
curl -X POST http://localhost:8000/api/dataset/generate -H "Content-Type: application/json" \
  -d '{"source_path":"data/benchmarks/sample_prompts.json","max_prompts":8,"quality_floor":0.9}'

# 2. Train (review and correct labels on the Dataset page first; human overrides win)
curl -X POST http://localhost:8000/api/training/start -H "Content-Type: application/json" \
  -d '{"dataset_id":"<UUID>","router_type":"tfidf","routing_threshold":0.6}'

# 3. Activate: set ROUTER_TYPE=tfidf in backend/.env, restart, confirm with GET /api/router/status
```

Training metrics describe how well the model reproduces the judge's labels on a held-out split. They are not a claim that routed quality improved.

## Benchmarks and experiments

```bash
curl -X POST http://localhost:8000/api/benchmark -H "Content-Type: application/json" \
  -d '{"strategy":"adaptive_router","max_prompts":8}'
curl -X POST http://localhost:8000/api/experiments/run -H "Content-Type: application/json" \
  -d '{"experiment_type":"final_evaluation","max_prompts":8,"quality_floor":0.9}'
```

Benchmarks compare Always Strong / Always Cheap / Adaptive Router over one prompt set (reports in `backend/experiments/benchmarks/`). The experiment suite has three sections (strategy comparison, quality-floor ablation, router comparison; reports in `backend/experiments/reports/`). Live runs spend provider quota. The larger, controlled offline study is in [EVALUATION.md](EVALUATION.md) and `backend/routing_lab/`.

## Development

```bash
# Backend tests, from backend/ (fully offline: mock providers and judge)
python -m pytest -q
python -m pytest tests/test_learned_router.py -q     # one module

# Whole flow with no keys
python scripts/e2e_demo.py

# Frontend
cd frontend && npm run build && npm run lint

# Offline routing lab (needs requirements-ml.txt plus pandas, pyarrow)
cd backend && python -m routing_lab.download && python -m routing_lab.embed && python -m routing_lab.evaluate
```

Tests are isolated: an autouse fixture gives every test a fresh temporary database and the offline test registry, pins judge and quality settings, and blanks every provider key; a session guard fails the run if anything touches the developer's real `backend/data/router.db`.

**Adding a provider:** implement `BaseModelProvider` in `backend/app/providers/`, register it in `providers/factory.py`, add models to the registry with the right tier, cost and capabilities.

**Adding a router:** subclass `Router` in `backend/app/router/`, register it in `router/base.py`, and add its name to the `ROUTER_TYPE` literal in `backend/app/config/settings.py`.
