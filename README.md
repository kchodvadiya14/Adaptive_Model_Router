# Adaptive AI Gateway

Route every LLM request to the **cheapest model that still meets your quality bar** — automatically, with circuit breakers for failing providers, request deadlines, per-caller usage tracking, and an explanation for every decision.

A self-hostable gateway that analyses each prompt, estimates its difficulty, and picks a Small / Medium / Strong model tier accordingly — while enforcing capability requirements (vision, tools, context window), skipping models whose circuit is currently open, respecting per-request cost/latency/timeout budgets, and recording every attempt as feedback for future routing decisions. Ships with a FastAPI backend, a React console, four interchangeable routers, an LLM-as-judge evaluation pipeline, and an OpenAI-compatible endpoint you can point any existing OpenAI SDK at.

---

## Table of Contents

- [Why](#why)
- [How It Works](#how-it-works)
- [Quick Start](#quick-start)
- [Configuration](#configuration)
- [Using the Gateway](#using-the-gateway)
- [Routers](#routers)
- [Reliability & Gateway Features](#reliability--gateway-features)
- [Training a Router](#training-a-router)
- [Evaluation & Experiments](#evaluation--experiments)
- [API Reference](#api-reference)
- [Frontend Console](#frontend-console)
- [Project Structure](#project-structure)
- [Development](#development)
- [Limitations](#limitations)
- [Roadmap](#roadmap)
- [License](#license)

---

## Why

Frontier models cost 20–60× more than small models per token, but most real traffic doesn't need them. Routing everything to the strongest model is expensive; routing everything to the cheapest sacrifices quality. This project takes the middle path: score each prompt, spend only what it actually requires, and stay useful when things go wrong — a model outage, a slow provider, a request that needs vision or tool-calling, a caller with a hard cost ceiling.

**Every decision is auditable.** A route returns the task type, difficulty score, per-tier cost/quality/latency estimates, which tiers were excluded and why (capability, health, or a cost/latency constraint), the tier it picked, and a human-readable reason.

---

## How It Works

```
                    ┌──────────────────────────────────────────┐
   Request ───────► │  Feature Extraction → Task Classification │
                    │  → Difficulty Estimation (0.0–1.0)        │
                    └───────────────────┬───────────────────────┘
                                        ▼
                    ┌──────────────────────────────────────────┐
                    │  Hard Eligibility Filters (in order)      │
                    │  1. Capability  (vision / tools / context)│
                    │  2. Health      (circuit breaker state)   │
                    │  3. Constraints (max_cost / max_latency)  │
                    │  A tier failing any of these is removed   │
                    │  before cost/quality comparison — never   │
                    │  merely penalized.                        │
                    └───────────────────┬───────────────────────┘
                                        ▼
                    ┌──────────────────────────────────────────┐
                    │  Routing Policy                          │
                    │  Cheapest eligible tier ≥ QUALITY_FLOOR,  │
                    │  or the caller's preferred_model if it    │
                    │  passes every filter above.               │
                    └───────────────────┬───────────────────────┘
                                        ▼
              SMALL ───────────── MEDIUM ───────────── STRONG
                │                    │                    │
                └────────────────────┴────────────────────┘
                                     ▼
                    ┌──────────────────────────────────────────┐
                    │  Provider Adapter → Response              │
                    │  OpenAI · Anthropic · Google · Mock       │
                    │  bounded by the request's timeout_ms      │
                    │  (one shared budget, not per-attempt)     │
                    └───────────────────┬───────────────────────┘
                                        ▼
                    ┌──────────────────────────────────────────┐
                    │  Judge + Fallback + Health Recording      │
                    │  retryable error → escalate a tier         │
                    │  low quality → escalate a tier             │
                    │  timeout → recorded, never a health failure│
                    │  3 consecutive failures → circuit opens    │
                    └───────────────────┬───────────────────────┘
                                        ▼
                    ┌──────────────────────────────────────────┐
                    │  SQLite: routing log · model outcomes ·   │
                    │  jobs · model health                      │
                    │  → /api/metrics · /api/usage ·             │
                    │    /api/performance/models                │
                    └──────────────────────────────────────────┘
```

**Tiers, not models.** The router chooses a *tier*; the registry resolves that tier to the cheapest enabled model in it that passes every eligibility filter. Swapping providers is a registry edit, not a code change.

---

## Quick Start

Needs free-tier API keys from Groq, Google AI Studio and (optionally) OpenRouter — see [Provider keys](#4-provider-keys). The test suite needs no keys and runs fully offline.

### Prerequisites

- Python 3.11+
- Node.js 18+

### 1. Backend

```bash
cd backend

python -m venv .venv
.venv\Scripts\activate          # Windows
source .venv/bin/activate       # macOS / Linux

pip install -r requirements.txt
cp .env.example .env            # .env belongs in backend/, not the repo root

uvicorn app.main:app --reload --port 8000
```

> **Start the backend from `backend/`.** Config, the SQLite database, the model registry, dataset/report/model-artifact directories all resolve relative to the working directory.

API docs: <http://localhost:8000/docs> · Health: <http://localhost:8000/health>

### 2. Frontend

```bash
cd frontend
npm install
npm run dev
```

Console: <http://localhost:5173> (the dev server proxies `/api` and `/health` to port 8000; it does **not** proxy `/v1` — call the OpenAI-compatible endpoints on port 8000 directly)

### 3. First route

```bash
curl -X POST http://localhost:8000/api/route \
  -H "Content-Type: application/json" \
  -d "{\"prompt\":\"Write a Python function to detect a cycle in a linked list.\"}"
```

Then send a real chat with `"model": "auto"`:

```bash
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d "{\"model\":\"auto\",\"messages\":[{\"role\":\"user\",\"content\":\"Summarise merge sort.\"}]}"
```

### 4. Provider keys

The default registry runs entirely on **free-tier** models:

| Tier | Model | Provider | Paid list price (in / out per 1M tokens) |
|---|---|---|---|
| small | `openai/gpt-oss-20b` | Groq | $0.075 / $0.30 |
| small (pinned use) | `nvidia/nemotron-3-super-120b-a12b:free` | OpenRouter | $0.08 / $0.45 |
| medium | `openai/gpt-oss-120b` (also the quality judge) | Groq | $0.15 / $0.60 |
| strong | `gemini-3.5-flash-lite` | Google | $0.30 / $2.50 |
| strong (pinned use) | `gemini-3.5-flash` | Google | $1.50 / $9.00 |

Costs are the providers' published paid prices (Sept 2026), so cost and "saved vs strong" figures show what the traffic would cost on a paid plan even though free-tier calls are billed $0. Put the keys in `backend/.env`:

```env
GROQ_API_KEY=...
GOOGLE_API_KEY=...
OPENAI_COMPATIBLE_BASE_URL=https://openrouter.ai/api/v1
OPENAI_COMPATIBLE_API_KEY=...
JUDGE_PROVIDER=registry
JUDGE_MODEL_ID=openai/gpt-oss-120b
```

Free-tier limits matter: Gemini 3.5 Flash allows about 20 requests/day and a free OpenRouter key about 50/day, which is why those two are secondary models used only when pinned. Batch jobs (dataset generation, benchmarks) retry rate-limited calls with backoff and skip a prompt only if it keeps failing.

> Each tier resolves to the **cheapest enabled model** in it that passes capability, health, and any per-request constraints. The offline mock models exist only in the test suite's registry (`backend/tests/model_fixtures.py`).

---

## Configuration

All settings are environment variables read from `backend/.env`. Copy [backend/.env.example](backend/.env.example) as a starting point — note it currently only lists a subset of these; the full set below is authoritative (verified against `backend/app/config/settings.py`).

### Routing

| Variable | Description | Default |
|---|---|---|
| `ROUTER_TYPE` | `rule_based` · `tfidf` · `embedding` · `bert` | `rule_based` |
| `QUALITY_FLOOR` | Minimum expected quality a tier must meet to be eligible | `0.90` |
| `ROUTING_THRESHOLD` | ML routers: P(strong is better) above which the strong tier wins | `0.60` |
| `COST_PRIORITY` | Weight on cost when breaking ties between eligible tiers | `0.7` |
| `LATENCY_PRIORITY` | Weight on latency when breaking ties | `0.3` |

### Fallback

| Variable | Description | Default |
|---|---|---|
| `FALLBACK_ENABLED` | Escalate a tier on retryable failure or low quality | `true` |
| `MAX_FALLBACK_ATTEMPTS` | Models tried per request (1–5) | `3` |
| `FALLBACK_ON_QUALITY_BELOW` | Re-run at a higher tier if the judge scores below this | `0.85` |
| `FALLBACK_ESCALATION` | `tier_up` (one step at a time) or `strong_only` | `tier_up` |

### Health & Circuit Breaking

| Variable | Description | Default |
|---|---|---|
| `HEALTH_FAILURE_THRESHOLD` | Consecutive retryable failures before a model's circuit opens | `3` |
| `HEALTH_COOLDOWN_SECONDS` | Time an open circuit waits before allowing one half-open trial request | `30` |
| `REQUEST_MIN_ATTEMPT_BUDGET_MS` | With `timeout_ms` set, don't start another generation/evaluation step with less than this much budget left | `10` |

### Models & Providers

| Variable | Description | Default |
|---|---|---|
| `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` / `GOOGLE_API_KEY` / `GROQ_API_KEY` | Provider credentials | empty |
| `OPENAI_COMPATIBLE_BASE_URL` / `OPENAI_COMPATIBLE_API_KEY` | Any OpenAI-shaped endpoint (vLLM, Ollama, OpenRouter, …) | empty |
| `SMALL_MODEL_ID` / `MEDIUM_MODEL_ID` / `STRONG_MODEL_ID` | Pin one model per tier | empty |
| `USE_MOCK_PROVIDERS` | Force offline mock responses | `false` |
| `PROVIDER_TIMEOUT` | Per-provider-call timeout, in seconds | `60` |
| `MAX_REQUEST_MESSAGES` | Max messages accepted per chat request | `50` |

### Evaluation

| Variable | Description | Default |
|---|---|---|
| `JUDGE_PROVIDER` | `mock` (heuristic, offline), `openai`, or `registry` (any registry model, through the gateway's own providers) | `mock` |
| `JUDGE_MODEL_ID` | Judge model for `openai` or `registry` | `gpt-4o-mini` |
| `EVALUATE_ON_CHAT` | Score every chat response inline | `true` |

### Server & Storage

| Variable | Description | Default |
|---|---|---|
| `BACKEND_HOST` / `BACKEND_PORT` | Bind address | `0.0.0.0` / `8000` |
| `CORS_ORIGINS` | Comma-separated allowed origins | `http://localhost:5173,…` |
| `DATABASE_URL` | SQLite database (routing logs, model outcomes, jobs, model health, benchmark reports) | `sqlite:///./data/router.db` |
| `STORE_PROMPTS` | Persist raw prompt text in logs (off for privacy) | `false` |
| `LOG_LEVEL` | Python log level | `INFO` |
| `ROUTER_API_KEY` | When set, `/v1/*` requires `Authorization: Bearer <key>` | empty |

---

## Using the Gateway

### Console

| Page | What it does |
|---|---|
| **Overview** | System status and quick navigation |
| **Chat** | Send prompts, compare tiers, inspect extracted features, override the quality floor |
| **Models** | Registry CRUD (create/edit/enable/disable) plus **live circuit health** and **historical performance** per model, clearly separated in the table and detail view |
| **Analytics** | Cost reduction, quality retention, strong-model usage, fallback rate, per-tier/task breakdowns |
| **Benchmark** | Run Always Strong / Always Cheap / Adaptive Router against a prompt set; browse past reports |
| **Dataset** | Generate preference datasets, browse/search/filter records, review and override labels by hand |
| **Training** | Train a router (TF-IDF / embedding / BERT), watch progress, compare runs over time, see accuracy/precision/recall/F1/confusion-matrix charts |
| **Experiments** | Run the full evaluation suite and read generated reports |
| **Settings** | Current routing, fallback, and health configuration |

### Native API

```bash
# Routing decision only — no model call, no cost
curl -X POST http://localhost:8000/api/route \
  -H "Content-Type: application/json" \
  -d "{\"prompt\":\"Explain the CAP theorem\"}"

# Chat with automatic routing, a caller identity, and a hard deadline
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d "{\"model\":\"auto\",\"messages\":[{\"role\":\"user\",\"content\":\"Explain the CAP theorem\"}],\"user_id\":\"alice\",\"tags\":{\"app\":\"support-bot\"},\"max_cost\":0.01,\"timeout_ms\":15000}"

# Chat pinned to a specific model, with a soft preference honored only if eligible
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d "{\"model\":\"auto\",\"preferred_model\":\"openai/gpt-oss-120b\",\"messages\":[{\"role\":\"user\",\"content\":\"Hello\"}]}"

# Aggregate metrics, scoped usage, per-model circuit health, and historical performance
curl http://localhost:8000/api/metrics
curl "http://localhost:8000/api/usage?user_id=alice"
curl http://localhost:8000/api/health/models
curl http://localhost:8000/api/performance/models
```

### OpenAI-Compatible API

Point any OpenAI SDK at this server and set `model` to `"auto"`. No other code changes.

```python
from openai import OpenAI

client = OpenAI(base_url="http://localhost:8000/v1", api_key="not-needed")

response = client.chat.completions.create(
    model="auto",
    messages=[{"role": "user", "content": "Summarise merge sort."}],
    user="alice",                       # recorded as user_id
    metadata={"app": "support-bot"},    # recorded as usage tags
)

print(response.choices[0].message.content)
print(response.model)   # the model actually chosen, e.g. "openai/gpt-oss-20b"
```

**Optional headers**

| Header | Effect |
|---|---|
| `X-Quality-Floor: 0.95` | Override the quality floor for this request only |
| `X-Request-ID: <id>` | Correlation ID; echoed back on the response and in logs |
| `X-Request-Timeout-Ms: 15000` | Overall wall-clock budget for the whole request |
| `Authorization: Bearer <key>` | Required when `ROUTER_API_KEY` is set |

Responses use the standard OpenAI shape plus an optional `router` block (task type, tier, cost, fallback info, request ID).

---

## Routers

All four implement the same interface and are swapped with a single environment variable.

| `ROUTER_TYPE` | Approach | Needs training? |
|---|---|---|
| `rule_based` | Feature extraction → task classification → difficulty score → policy. Fully explainable, no cold start. | No |
| `tfidf` | TF-IDF + logistic regression over prompt text | Yes |
| `embedding` | SentenceTransformer embeddings + classifier | Yes |
| `bert` | BERT-style MLP head over embeddings | Yes |

The ML routers predict **P(the strong model is meaningfully better)** and compare it against `ROUTING_THRESHOLD`. They load the most recently trained artifact of their type from `backend/models/` at startup.

---

## Reliability & Gateway Features

Everything in this section is invisible when nothing is wrong — it only changes behavior when a request actually needs it.

### Capability-aware routing

Models declare `supports_vision` and `supports_tools` (alongside `context_window`, already present). A request with an image or a non-empty `tools` list, or one whose estimated token count exceeds a tier's context window, hard-excludes any model that can't handle it — before cost/quality comparison, not as a soft penalty.

### Circuit breaking

Each model has an independent circuit: `CLOSED` (healthy) → `OPEN` after `HEALTH_FAILURE_THRESHOLD` consecutive *retryable* provider failures → `HALF_OPEN` for exactly one trial request once `HEALTH_COOLDOWN_SECONDS` has elapsed → `CLOSED` on success or back to `OPEN` on failure. Non-retryable errors (bad request, auth/config issues) never count toward health. `GET /api/health/models` exposes live state, consecutive failures, and cooldown remaining for every registered model.

### Request deadlines

An optional `timeout_ms` is one shared budget across the *entire* request — initial generation, provider-error fallback, quality evaluation, and quality escalation all draw from the same clock, and a step that doesn't have enough budget left is never started. A deadline exhaustion is a distinct `RequestTimeoutError`, never counted as a provider health failure, and returns a structured 504 with the stage, model, and timing.

### Cost & latency constraints, and a soft model preference

`max_cost` and `max_latency_ms` are additional hard filters using the router's existing cost estimate and the registry's `avg_latency_ms` — no new estimation model. `preferred_model` is a *preference*, not a bypass: it's checked against the same capability/health/constraint filters as every other candidate, and if it fails one, routing proceeds normally and the response explains why the preference wasn't honored.

### Request metadata & scoped usage

`request_id` (auto-generated if omitted), `user_id`, `session_id`, and free-form `tags` travel with a request into the routing log. `GET /api/usage` reports total/successful/fallback request counts, total estimated cost, and average latency, with breakdowns by user, model, and tag, filterable by `user_id`, `session_id`, `model_id`, and `tag_key`/`tag_value`.

### Historical model performance

Every generation attempt the gateway makes — including fallback and escalation attempts — is recorded with its outcome: `success`, `quality_failure` (answered, but below the escalation threshold), `retryable_failure`, `non_retryable_failure`, or `timeout`. `GET /api/performance/models` aggregates these per model: request count, success rate, fallback rate, average latency/cost/quality, and an outcome breakdown, filterable by model, task type, and time window. This is reporting only — it does not yet feed back into routing decisions.

### Persistent, restart-safe background jobs

Dataset generation, training, benchmark, and experiment runs share one generic SQLite-backed job manager. A job's status survives a backend restart; one still `running` when the process exits is marked `failed` (never silently reported as completed) the next time its job type is used.

---

## Training a Router

Training data is generated by the system itself: each prompt is answered at all three tiers, scored by the judge, and reduced to a binary `strong_better` label.

**1. Generate a preference dataset** (at least 4 labeled records are needed to train)

```bash
curl -X POST http://localhost:8000/api/dataset/generate \
  -H "Content-Type: application/json" \
  -d "{\"source_path\":\"data/benchmarks/sample_prompts.json\",\"max_prompts\":8,\"quality_floor\":0.9}"
```

Review and correct labels on the **Dataset** console page — human overrides take precedence over judge labels.

**2. Train**

```bash
curl -X POST http://localhost:8000/api/training/start \
  -H "Content-Type: application/json" \
  -d "{\"dataset_id\":\"<UUID>\",\"router_type\":\"tfidf\",\"routing_threshold\":0.6}"
```

Watch progress and see accuracy/precision/recall/F1 and the confusion matrix on the **Training** page, or poll `GET /api/training/status/{job_id}`.

**3. Activate**

```env
ROUTER_TYPE=tfidf
```

Restart the backend, then confirm with `GET /api/router/status`.

> Training metrics describe how well the model reproduces the judge's preference labels on a held-out split — they are not a claim that routed response quality improved. The **Training** page's "How training works" panel states this explicitly.

---

## Evaluation & Experiments

### Metrics

`GET /api/metrics` aggregates every logged request: `cost_saved`, `quality_retention`, `strong_model_usage`, `fallback_rate`, average cost/latency, and distributions by model/task/tier.

### Benchmarks

```bash
curl -X POST http://localhost:8000/api/benchmark \
  -H "Content-Type: application/json" \
  -d "{\"strategy\":\"adaptive_router\",\"max_prompts\":8}"
```

Compares Always Strong / Always Cheap / Adaptive Router over one prompt set; reports persist to `backend/experiments/benchmarks/`.

### Full evaluation suite

```bash
curl -X POST http://localhost:8000/api/experiments/run \
  -H "Content-Type: application/json" \
  -d "{\"experiment_type\":\"final_evaluation\",\"max_prompts\":8,\"quality_floor\":0.9}"
```

Three measured sections — strategy comparison, quality-floor ablation, router comparison — persisted with an auto-generated markdown summary to `backend/experiments/reports/`.

---

## API Reference

Interactive docs at `/docs`; full OpenAPI schema at `/openapi.json`.

| Method | Endpoint | Description |
|---|---|---|
| GET | `/health` | Service status, version, environment |
| POST | `/api/route` | Analyse a prompt; supports `preferred_model`, `max_cost`, `max_latency_ms` |
| GET | `/api/router/status` | Active router type and configuration |
| POST | `/api/chat` | Chat completion; `model:"auto"`, request metadata, deadline, constraints |
| GET | `/api/models` | List registered models |
| GET | `/api/models/{id}` | Model detail |
| POST | `/api/models` | Register a model |
| PATCH | `/api/models/{id}` | Update model metadata |
| POST | `/api/models/{id}/enable` / `/disable` | Enable / disable |
| GET | `/api/health/models` | Live circuit-breaker state per model |
| GET | `/api/performance/models` | Historical per-model performance (filterable) |
| GET | `/api/usage` | Scoped usage totals and breakdowns |
| POST | `/api/evaluate` | Judge a prompt/response pair |
| GET | `/api/metrics` | Aggregated routing metrics |
| POST | `/api/benchmark` | Start a benchmark job |
| GET | `/api/benchmark/status/{job_id}` | Benchmark job status |
| GET | `/api/benchmarks` / `/api/benchmarks/{id}` | List / get benchmark reports |
| POST | `/api/dataset/generate` | Start preference-dataset generation |
| GET | `/api/dataset/generate/status/{job_id}` | Generation job status |
| GET | `/api/dataset` / `/api/dataset/{id}` | List datasets / paginated records |
| POST | `/api/dataset/{id}/human-eval` | Override a label by hand |
| POST | `/api/training/start` | Train a router from a dataset |
| GET | `/api/training/status/{job_id}` | Training job status and metrics |
| GET | `/api/training/models` | List trained artifacts |
| POST | `/api/experiments/run` | Run the evaluation suite |
| GET | `/api/experiments/status/{job_id}` | Experiment job status |
| GET | `/api/experiments` / `/api/experiments/{id}` | List / get experiment reports |
| POST | `/v1/chat/completions` | Drop-in OpenAI chat completions |
| GET | `/v1/models` / `/v1/models/{id}` | List models, including virtual `auto` |

---

## Frontend Console

| Layer | Technology |
|---|---|
| Framework | React 18, TypeScript, Vite 6 |
| Styling | Tailwind CSS (custom design tokens: `surface`/`ink`/`line` scales, semantic `success`/`warning`/`danger`/`info` colors) |
| Charts | Recharts |
| Routing | React Router 7 |
| HTTP | axios |
| Icons | lucide-react |

A small shared component library (`Card`, `Button`, `Badge`, `Modal`, `Table`, `Input`, `Select`, `EmptyState`, `ErrorBanner`, `JobProgressBar`, `PageHeader`, `StatCard`) backs every page for a consistent look, with loading skeletons and explicit empty/error states throughout. Each page's larger pieces (charts, modals, formatters) live colocated under `src/pages/<page>/` rather than in one large file.

---

## Project Structure

```
Adaptive_Model_Router/
├── backend/
│   ├── app/
│   │   ├── api/            # FastAPI route handlers, one module per resource
│   │   ├── config/         # Pydantic settings loaded from .env
│   │   ├── datasets/       # Preference-dataset generation and JSONL storage
│   │   ├── db/             # SQLite connection + repositories (routing logs, jobs,
│   │   │                   #   model health, model outcomes, benchmark reports)
│   │   ├── evaluation/     # Judge, metrics, benchmarks, experiment reports
│   │   ├── models/         # Model registry (tiers, cost, quality, capabilities)
│   │   ├── providers/      # OpenAI · Anthropic · Google · Groq · compatible · mock
│   │   ├── router/         # features → task → difficulty → policy; capability,
│   │   │                   #   health, and constraint eligibility; 4 routers
│   │   ├── schemas/        # Pydantic request/response contracts
│   │   ├── services/       # Chat orchestration, fallback + health + deadlines,
│   │   │                   #   outcome recording, usage/performance, background jobs
│   │   ├── training/       # Trainers, artifact registry, training service
│   │   ├── utils/          # Cost, tokens, logging, OpenAI conversion
│   │   └── main.py         # App factory and router wiring
│   ├── data/               # Runtime state: registry, datasets, router.db
│   ├── experiments/        # CLI runner and generated reports
│   ├── models/             # Trained router artifacts (.joblib)
│   ├── tests/              # 216 pytest tests, incl. per-test database/registry isolation
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── components/     # Shared design-system components
│   │   ├── pages/          # One page per route, with colocated `pages/<name>/` helpers
│   │   ├── services/api.ts # Typed axios client
│   │   └── types/          # TypeScript mirrors of backend schemas
│   └── package.json
├── data/ · models/ · experiments/   # Placeholder dirs for root-level runs
└── docker-compose.yml       # Not currently usable — see Limitations
```

---

## Development

```bash
# Backend tests, from backend/
pytest -v
pytest tests/test_model_health.py -v     # a single module

# Frontend
cd frontend
npm run build     # tsc -b && vite build
npm run lint
npm run preview
```

Backend tests are fully offline (mock providers, mock judge) and isolated: an autouse fixture gives every test a fresh temporary SQLite database and the offline test registry (`tests/model_fixtures.py`), pins judge/quality settings and blanks every provider key, so tests never read or write the developer's real `backend/data/router.db`, and a session-scoped guard fails the run if anything ever does.

**Adding a provider:** implement `BaseModelProvider` in [backend/app/providers/](backend/app/providers/), register it in [factory.py](backend/app/providers/factory.py), then add your models to the registry with the correct tier, cost, and capability metadata.

**Adding a router:** subclass the base in [backend/app/router/](backend/app/router/), register it in [base.py](backend/app/router/base.py), and add its name to the `ROUTER_TYPE` literal in [settings.py](backend/app/config/settings.py).

---

## Limitations

- **No streaming.** `stream=true` is not supported on `/v1/chat/completions`.
- **Settings are read-only in the UI.** Change `backend/.env` and restart.
- **`docker-compose.yml` is not usable as-is** — it references `backend/Dockerfile` and `frontend/Dockerfile`, neither of which exists in the repo.
- **Both `.env.example` files are stale** — they don't list the health/deadline/request-metadata variables documented above. Use the [Configuration](#configuration) tables in this README as the source of truth.
- **Working directory matters.** Run the backend from `backend/`; every data path is relative to it.
- **Historical performance is reporting only.** `GET /api/performance/models` does not yet influence routing decisions.
- **Free-tier rate limits** — Groq, Google and OpenRouter free tiers throttle bursts; large dataset or benchmark runs slow down on retries and may skip a prompt.
- **A model whose one live health-check trial fails with a non-retryable error can stay stuck `HALF_OPEN`** rather than reopening — a known edge case in the circuit breaker, not covered by an automatic recovery path yet.
- **No authentication on the native `/api/*` endpoints** — only `/v1/*` supports `ROUTER_API_KEY`.
- **No rate limiting, and no per-tenant model preference beyond the per-request `preferred_model` field.**

---

## Roadmap

| Status | Item |
|---|---|
| ✅ | Model registry, provider adapters, chat API |
| ✅ | Rule-based and trained (TF-IDF/embedding/BERT) routers |
| ✅ | LLM-as-judge evaluation, metrics, benchmarking, final-evaluation suite |
| ✅ | Preference-dataset pipeline with human override |
| ✅ | Provider-error and quality-based fallback escalation |
| ✅ | Capability-aware routing (vision, tools, context window) |
| ✅ | Per-model circuit breaking with health cooldown/recovery |
| ✅ | End-to-end request deadlines, independent of routing-latency constraints |
| ✅ | Request metadata, `preferred_model`, cost/latency constraints, scoped usage reporting |
| ✅ | Historical per-model performance from recorded generation outcomes |
| ✅ | Unified, restart-safe background job manager |
| ✅ | Full React console: Overview, Chat, Models+Health, Analytics, Benchmark, Dataset, Training, Experiments, Settings |
| ✅ | OpenAI-compatible API |
| ⬜ | Use historical performance to influence routing (contextual bandit or similar) |
| ⬜ | Streaming responses |
| ✅ | Provider-agnostic judge (`JUDGE_PROVIDER=registry`) |
| ⬜ | PostgreSQL persistence, authentication, rate limiting |
| ⬜ | Working Docker images |

---

## License

Academic project — final-year AI/ML coursework.
