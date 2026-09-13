# Adaptive Model Router

Route every LLM query to the **cheapest model that still meets your quality bar** — automatically, with an explanation for every decision.

A self-hostable routing layer that analyses each prompt, estimates its difficulty, and picks a Small / Medium / Strong model tier accordingly. Ships with a FastAPI backend, a React dashboard, four interchangeable routers (one rule-based, three trained), an LLM-as-judge evaluation pipeline, and an OpenAI-compatible endpoint you can point any existing OpenAI SDK at.

---

## Table of Contents

- [Why](#why)
- [How It Works](#how-it-works)
- [Quick Start](#quick-start)
- [Configuration](#configuration)
- [Usage](#usage)
- [Routers](#routers)
- [Training a Router](#training-a-router)
- [Evaluation & Experiments](#evaluation--experiments)
- [API Reference](#api-reference)
- [Project Structure](#project-structure)
- [Development](#development)
- [Limitations](#limitations)
- [Roadmap](#roadmap)
- [License](#license)

---

## Why

Frontier models cost 20–60× more than small models per token, but most real traffic doesn't need them. "Summarise this paragraph" and "prove this theorem" are not the same workload, yet a single hard-coded `model=` parameter treats them identically.

Routing everything to the strongest model is expensive. Routing everything to the cheapest sacrifices quality. This project takes the middle path: score each prompt, then spend only what the prompt actually requires — and measure whether that decision was right.

**Every routing decision is auditable.** A route returns the task type, the difficulty score, the per-tier cost/quality/latency estimates it compared, the tier it picked, and a human-readable reason.

---

## How It Works

```
                    ┌──────────────────────────────────────────┐
   Prompt ────────► │  Feature Extraction                      │
                    │  length · code · math · reasoning cues   │
                    │  instruction count · question complexity │
                    └───────────────────┬──────────────────────┘
                                        ▼
                    ┌──────────────────────────────────────────┐
                    │  Task Classification  (13 task types)    │
                    │  coding · debugging · mathematics · ...  │
                    └───────────────────┬──────────────────────┘
                                        ▼
                    ┌──────────────────────────────────────────┐
                    │  Difficulty Estimation  (0.0 – 1.0)      │
                    └───────────────────┬──────────────────────┘
                                        ▼
                    ┌──────────────────────────────────────────┐
                    │  Routing Policy                          │
                    │  Per tier: expected quality, estimated   │
                    │  cost, estimated latency.                │
                    │  Pick cheapest tier >= QUALITY_FLOOR.    │
                    └───────────────────┬──────────────────────┘
                                        ▼
              SMALL ───────────── MEDIUM ───────────── STRONG
                │                    │                    │
                └────────────────────┴────────────────────┘
                                     ▼
                    ┌──────────────────────────────────────────┐
                    │  Provider Adapter → Response             │
                    │  OpenAI · Anthropic · Google · Mock      │
                    └───────────────────┬──────────────────────┘
                                        ▼
                    ┌──────────────────────────────────────────┐
                    │  Judge + Fallback                        │
                    │  score below floor, or retryable error   │
                    │  → escalate a tier and retry             │
                    └───────────────────┬──────────────────────┘
                                        ▼
                    ┌──────────────────────────────────────────┐
                    │  SQLite routing log → /api/metrics       │
                    └──────────────────────────────────────────┘
```

**Tiers, not models.** The router chooses a *tier*; the registry resolves that tier to the cheapest enabled model in it. Swapping providers is a registry edit, not a code change.

---

## Quick Start

Runs end-to-end with **no API keys** — the registry ships with three zero-cost `mock-*` models covering all three tiers, so you can exercise routing, benchmarking, dataset generation, and training completely offline.

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
cp ../.env.example .env         # note: .env belongs in backend/, not the repo root

uvicorn app.main:app --reload --port 8000
```

> **Start the backend from `backend/`.** Config, database, datasets, trained artifacts, and reports all resolve relative to the working directory. Launching uvicorn elsewhere silently creates a second set of empty data directories.

API docs: <http://localhost:8000/docs> · Health: <http://localhost:8000/health>

### 2. Frontend

```bash
cd frontend
npm install
npm run dev
```

Dashboard: <http://localhost:5173> (the dev server proxies `/api` and `/health` to port 8000)

### 3. First route

```bash
curl -X POST http://localhost:8000/api/route \
  -H "Content-Type: application/json" \
  -d "{\"prompt\":\"Write a Python function to detect a cycle in a linked list.\"}"
```

```jsonc
{
  "task_type": "coding",
  "difficulty": 0.67,
  "difficulty_label": "medium",
  "selected_tier": "medium",
  "selected_model": "...",
  "reason": "...",
  "tier_evaluations": [ /* cost, quality and latency per tier */ ]
}
```

Then send a real chat with `"model": "auto"`:

```bash
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d "{\"model\":\"auto\",\"messages\":[{\"role\":\"user\",\"content\":\"Summarise merge sort.\"}]}"
```

### 4. Going live with real providers

1. Put your key in `backend/.env` (`OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, or `GOOGLE_API_KEY`).
2. Pin one model per tier so routing stops selecting the free mocks:

   ```env
   SMALL_MODEL_ID=gpt-4o-mini
   MEDIUM_MODEL_ID=gpt-4o
   STRONG_MODEL_ID=gpt-4-turbo
   ```

   Setting a tier override enables that model and disables every other model in the same tier. The **Models** page does the same thing interactively.
3. Restart the backend.

> Each tier resolves to the **cheapest enabled model** in it. Because the mock models cost $0, they win every tier until you override or disable them.

---

## Configuration

All settings are environment variables read from `backend/.env`. Copy [.env.example](.env.example) as your starting point.

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
| `FALLBACK_ENABLED` | Escalate a tier on retryable failure | `true` |
| `MAX_FALLBACK_ATTEMPTS` | Models tried per request (1–5) | `3` |
| `FALLBACK_ON_QUALITY_BELOW` | Re-run at a higher tier if the judge scores below this | `0.85` |
| `FALLBACK_ESCALATION` | `tier_up` (one step at a time) or `strong_only` | `tier_up` |

### Models & Providers

| Variable | Description | Default |
|---|---|---|
| `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` / `GOOGLE_API_KEY` | Provider credentials | empty |
| `OPENAI_COMPATIBLE_BASE_URL` / `OPENAI_COMPATIBLE_API_KEY` | Any OpenAI-shaped endpoint (vLLM, Ollama, Together, …) | empty |
| `SMALL_MODEL_ID` / `MEDIUM_MODEL_ID` / `STRONG_MODEL_ID` | Pin one model per tier | empty |
| `USE_MOCK_PROVIDERS` | Force offline mock responses | `false` |
| `PROVIDER_TIMEOUT` | Per-request provider timeout, in seconds | `60` |
| `MAX_REQUEST_MESSAGES` | Max messages accepted per chat request | `50` |

### Evaluation

| Variable | Description | Default |
|---|---|---|
| `JUDGE_PROVIDER` | `mock` (deterministic, free) or `openai` | `mock` |
| `JUDGE_MODEL_ID` | Model used when the judge is `openai` | `gpt-4o-mini` |
| `EVALUATE_ON_CHAT` | Score every chat response inline | `true` |

### Server & Storage

| Variable | Description | Default |
|---|---|---|
| `BACKEND_HOST` / `BACKEND_PORT` | Bind address | `0.0.0.0` / `8000` |
| `CORS_ORIGINS` | Comma-separated allowed origins | `http://localhost:5173,…` |
| `DATABASE_URL` | Routing-log database | `sqlite:///./data/router.db` |
| `STORE_PROMPTS` | Persist raw prompt text in logs (off for privacy) | `false` |
| `LOG_LEVEL` | Python log level | `INFO` |
| `ROUTER_API_KEY` | When set, `/v1/*` requires `Authorization: Bearer <key>` | empty |

---

## Usage

### Dashboard

| Page | What it does |
|---|---|
| **Overview** | System metrics and quick navigation |
| **Chat** | Send prompts, compare tiers side by side, inspect extracted features, override the quality floor per message |
| **Analytics** | Cost reduction, quality retention, strong-model usage, fallback rate, per-tier and per-task breakdowns |
| **Models** | Full registry CRUD — add, edit, enable/disable, inspect cost and quality metadata |
| **Benchmark** | Run Always Strong / Always Cheap / Adaptive Router against a prompt set; browse past reports |
| **Dataset** | Generate preference data, page through records, override labels by hand |
| **Training** | Train a router, watch progress, compare trained models, activate one |
| **Experiments** | Run the full evaluation suite and read generated reports |
| **Settings** | Current routing and fallback configuration |

### Native API

```bash
# Routing decision only — no model call, no cost
curl -X POST http://localhost:8000/api/route \
  -H "Content-Type: application/json" \
  -d "{\"prompt\":\"Explain the CAP theorem\"}"

# Chat with automatic routing
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d "{\"model\":\"auto\",\"messages\":[{\"role\":\"user\",\"content\":\"Explain the CAP theorem\"}]}"

# Chat pinned to a specific model
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d "{\"model\":\"gpt-4o-mini\",\"messages\":[{\"role\":\"user\",\"content\":\"Hello\"}]}"

# Aggregate metrics across all logged requests
curl http://localhost:8000/api/metrics
```

### OpenAI-Compatible API

Point any OpenAI SDK at this server and set `model` to `"auto"`. No other code changes.

```python
from openai import OpenAI

client = OpenAI(base_url="http://localhost:8000/v1", api_key="not-needed")

response = client.chat.completions.create(
    model="auto",
    messages=[{"role": "user", "content": "Summarise merge sort."}],
)

print(response.choices[0].message.content)
print(response.model)   # the model actually chosen, e.g. "gpt-4o-mini"
```

```bash
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d "{\"model\":\"auto\",\"messages\":[{\"role\":\"user\",\"content\":\"Explain binary search\"}]}"

curl http://localhost:8000/v1/models   # includes the virtual "auto" model
```

Responses use the standard OpenAI shape (`choices`, `usage`, `object: "chat.completion"`) plus an optional `router` block carrying task type, tier, cost, and fallback metadata.

**Optional headers**

| Header | Effect |
|---|---|
| `X-Quality-Floor: 0.95` | Override the quality floor for this request only |
| `Authorization: Bearer <key>` | Required when `ROUTER_API_KEY` is set |

> The Vite dev server proxies `/api` and `/health` but **not** `/v1` — call the OpenAI-compatible endpoints on port 8000 directly.

---

## Routers

All four implement the same interface and are swapped with a single environment variable.

| `ROUTER_TYPE` | Approach | Needs training? |
|---|---|---|
| `rule_based` | Feature extraction → task classification → difficulty score → policy. Fully explainable, no cold start. | No |
| `tfidf` | TF-IDF + logistic regression over prompt text | Yes |
| `embedding` | SentenceTransformer embeddings + classifier | Yes |
| `bert` | BERT-style MLP head over embeddings | Yes |

The ML routers predict **P(the strong model is meaningfully better)** and compare it against `ROUTING_THRESHOLD`. They load the most recent trained artifact from `backend/models/` at startup and raise a clear error if none exists — so train before switching `ROUTER_TYPE`.

---

## Training a Router

Training data is generated by the system itself: each prompt is answered at all three tiers, scored by the judge, and reduced to a binary `strong_better` label.

**1. Generate a preference dataset** (at least 4 labeled records are needed to train)

```bash
# API
curl -X POST http://localhost:8000/api/dataset/generate \
  -H "Content-Type: application/json" \
  -d "{\"source_path\":\"data/benchmarks/sample_prompts.json\",\"max_prompts\":8,\"quality_floor\":0.9}"

# CLI, from backend/
python -m training.generate_dataset --max-prompts 8
```

Records land in `backend/data/processed/datasets/<uuid>.jsonl` with a manifest in `index.json`. Review and correct labels on the **Dataset** page — human overrides take precedence over judge labels.

**2. Train**

```bash
curl -X POST http://localhost:8000/api/training/start \
  -H "Content-Type: application/json" \
  -d "{\"dataset_id\":\"<UUID>\",\"router_type\":\"tfidf\",\"routing_threshold\":0.6}"
```

Poll `GET /api/training/status/{job_id}` for accuracy, F1, and the confusion matrix, or watch the **Training** page.

**3. Activate**

```env
ROUTER_TYPE=tfidf
```

Restart the backend, then confirm with `GET /api/router/status`.

**Other CLI helpers** (run from `backend/`):

```bash
python -m training.prepare_dataset --dataset-id <UUID> --output data/processed/training_set.csv
python -m training.evaluate_responses
python -m training.train_tfidf_router
```

---

## Evaluation & Experiments

### Judge

An LLM-as-judge scores responses on a 0–1 scale. `JUDGE_PROVIDER=mock` gives deterministic, free scoring for development; `openai` uses a real model for meaningful numbers.

### Metrics

`GET /api/metrics` aggregates every logged request:

| Metric | Meaning |
|---|---|
| `cost_saved` | Spend avoided versus routing everything to the strong tier |
| `quality_retention` | Achieved quality as a fraction of the strong-tier baseline |
| `strong_model_usage` | Share of requests that reached the strong tier |
| `fallback_rate` | Share of requests that escalated |
| `average_cost` / `average_latency_ms` | Per-request averages |
| `requests_by_model` / `_task` / `_tier` | Distribution breakdowns |

### Benchmarks

Compare strategies over one prompt set:

```bash
curl -X POST http://localhost:8000/api/benchmark \
  -H "Content-Type: application/json" \
  -d "{\"strategy\":\"adaptive_router\",\"max_prompts\":8}"
```

Reports persist to `backend/experiments/benchmarks/`.

### Full evaluation suite

```bash
# API
curl -X POST http://localhost:8000/api/experiments/run \
  -H "Content-Type: application/json" \
  -d "{\"experiment_type\":\"final_evaluation\",\"max_prompts\":8,\"quality_floor\":0.9}"

# CLI, from backend/
python experiments/run_final_evaluation.py --max-prompts 8
```

Three sections, all measured at run time — nothing in the report is hard-coded:

1. **Strategy comparison** — Always Strong vs. Always Cheap vs. Adaptive Router
2. **Quality-floor ablation** — adaptive routing at floors 0.85 / 0.90 / 0.95
3. **Router comparison** — rule-based vs. each trained router (untrained routers are skipped, not failed)

Reports and their generated markdown summaries land in `backend/experiments/reports/`. Suite parameters live in [experiments/configs/final_evaluation.json](experiments/configs/final_evaluation.json).

---

## API Reference

Interactive docs at `/docs`; full OpenAPI schema at `/openapi.json`.

### Health

| Method | Endpoint | Description |
|---|---|---|
| GET | `/health` | Service status, version, environment |

### Routing

| Method | Endpoint | Description |
|---|---|---|
| POST | `/api/route` | Analyse a prompt and return the routing decision |
| GET | `/api/router/status` | Active router type and configuration |

### Chat

| Method | Endpoint | Description |
|---|---|---|
| POST | `/api/chat` | Chat completion; `model: "auto"` enables routing |

### Models

| Method | Endpoint | Description |
|---|---|---|
| GET | `/api/models` | List registered models |
| GET | `/api/models/{model_id}` | Model detail |
| POST | `/api/models` | Register a model |
| PATCH | `/api/models/{model_id}` | Update model metadata |
| POST | `/api/models/{model_id}/enable` | Enable a model |
| POST | `/api/models/{model_id}/disable` | Disable a model |

### Evaluation & Metrics

| Method | Endpoint | Description |
|---|---|---|
| POST | `/api/evaluate` | Judge a prompt/response pair |
| GET | `/api/metrics` | Aggregated routing metrics |
| POST | `/api/benchmark` | Start a benchmark job |
| GET | `/api/benchmark/status/{job_id}` | Benchmark job status |
| GET | `/api/benchmarks` | List benchmark reports |
| GET | `/api/benchmarks/{report_id}` | Benchmark report detail |

### Dataset

| Method | Endpoint | Description |
|---|---|---|
| POST | `/api/dataset/generate` | Start preference-dataset generation |
| GET | `/api/dataset/generate/status/{job_id}` | Generation job status |
| GET | `/api/dataset` | List datasets |
| GET | `/api/dataset/{dataset_id}` | Paginated preference records |
| POST | `/api/dataset/{dataset_id}/human-eval` | Override a label by hand |

### Training

| Method | Endpoint | Description |
|---|---|---|
| POST | `/api/training/start` | Train a router from a dataset |
| GET | `/api/training/status/{job_id}` | Training job status and metrics |
| GET | `/api/training/models` | List trained artifacts |

### Experiments

| Method | Endpoint | Description |
|---|---|---|
| POST | `/api/experiments/run` | Run the evaluation suite |
| GET | `/api/experiments/status/{job_id}` | Experiment job status |
| GET | `/api/experiments` | List experiment reports |
| GET | `/api/experiments/{report_id}` | Experiment report detail |

### OpenAI-Compatible

| Method | Endpoint | Description |
|---|---|---|
| POST | `/v1/chat/completions` | Drop-in OpenAI chat completions |
| GET | `/v1/models` | List models, including the virtual `auto` |
| GET | `/v1/models/{model_id}` | Model detail |

---

## Project Structure

```
Adaptive_Model_Router/
├── backend/
│   ├── app/
│   │   ├── api/            # FastAPI route handlers, one module per resource
│   │   ├── config/         # Pydantic settings loaded from .env
│   │   ├── datasets/       # Preference-dataset generation and JSONL storage
│   │   ├── db/             # SQLite engine and routing-log repository
│   │   ├── evaluation/     # Judge, metrics, benchmarks, experiment reports
│   │   ├── models/         # Model registry (tiers, cost, quality metadata)
│   │   ├── providers/      # OpenAI · Anthropic · Google · compatible · mock
│   │   ├── router/         # Features → task → difficulty → policy; 4 routers
│   │   ├── schemas/        # Pydantic request/response contracts
│   │   ├── services/       # Chat orchestration, fallback, background jobs
│   │   ├── training/       # Trainers, artifact registry, training service
│   │   ├── utils/          # Cost, tokens, logging, OpenAI conversion
│   │   └── main.py         # App factory and router wiring
│   ├── data/               # Runtime state: registry, datasets, router.db
│   ├── experiments/        # CLI runner and generated reports
│   ├── models/             # Trained router artifacts (.joblib)
│   ├── tests/              # 60 pytest tests
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── components/     # Shared UI: cards, charts, headers, banners
│   │   ├── pages/          # One component per dashboard route
│   │   ├── services/api.ts # Typed axios client
│   │   └── types/          # TypeScript mirrors of the backend schemas
│   └── package.json
├── data/ · models/ · experiments/   # Placeholder dirs for root-level runs
├── .env.example            # Copy to backend/.env
└── docker-compose.yml
```

### Tech stack

| Layer | Technology |
|---|---|
| Frontend | React 18, TypeScript, Vite 6, Tailwind, Recharts, React Router 7, axios |
| Backend | Python 3.11+, FastAPI, Pydantic v2, Uvicorn, httpx |
| Storage | SQLite (routing logs), JSON (model registry), JSONL (datasets) |
| ML | scikit-learn, sentence-transformers, joblib, NumPy |
| Testing | pytest, pytest-asyncio |

---

## Development

```bash
# Backend tests, from backend/
pytest -v
pytest tests/test_rule_router.py -v     # a single module

# Frontend
npm run lint
npm run build
npm run preview
```

Tests use mock providers and the mock judge throughout — no API keys, no network, no cost.

**Adding a provider:** implement `BaseModelProvider` in [backend/app/providers/](backend/app/providers/), register it in [factory.py](backend/app/providers/factory.py), then add your models to the registry with the correct tier and cost metadata.

**Adding a router:** subclass the base in [backend/app/router/](backend/app/router/), register it in [base.py](backend/app/router/base.py), and add its name to the `ROUTER_TYPE` literal in [settings.py](backend/app/config/settings.py).

---

## Limitations

- **No streaming.** `stream=true` is not supported on `/v1/chat/completions`.
- **Settings are read-only in the UI.** Change `backend/.env` and restart.
- **Background jobs are in-memory.** Training, dataset, benchmark, and experiment jobs do not survive a restart.
- **`docker-compose.yml` is not usable as-is** — it references `backend/Dockerfile` and `frontend/Dockerfile`, neither of which is in the repo. Use the local setup above.
- **Working directory matters.** Run the backend from `backend/`; every data path is relative to it.
- **Pre-call quality is a heuristic.** Expected tier quality comes from registry metadata and a difficulty penalty, not from measuring that specific prompt. The judge measures actual quality *after* the call.

---

## Roadmap

| Status | Item |
|---|---|
| ✅ | Model registry, provider adapters, chat API |
| ✅ | Rule-based router with explainable decisions |
| ✅ | LLM-as-judge evaluation, metrics, benchmarking |
| ✅ | Preference-dataset pipeline with human override |
| ✅ | Trained routers: TF-IDF, embedding, BERT |
| ✅ | Quality- and error-driven fallback escalation |
| ✅ | Full React dashboard |
| ✅ | OpenAI-compatible API |
| ✅ | Final evaluation suite |
| ⬜ | Streaming responses |
| ⬜ | Contextual-bandit routing (extension point prepared) |
| ⬜ | PostgreSQL persistence |
| ⬜ | Celery/RQ for durable background jobs |
| ⬜ | Working Docker images |
| ⬜ | Rate limiting |

---

## License

Academic project — final-year AI/ML coursework.
