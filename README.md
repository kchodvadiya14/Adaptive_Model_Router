# Adaptive Model Router

A production-style, self-hostable system that automatically chooses the most appropriate LLM for every incoming user query — selecting the **cheapest model that still meets a configured quality requirement**.

> **Current status: Milestone 10 — Final Evaluation (v1.0.0)**

## Problem Statement

Large language models vary widely in cost, latency, and capability. Routing every query to the strongest model is expensive; routing everything to the cheapest model sacrifices quality. This project builds an adaptive router that analyzes prompts, estimates task difficulty, and selects an optimal model tier.

## Architecture

```
User → React Frontend → FastAPI Backend → Router Engine → Model Providers → Response
                                              ↓
                                    Evaluation + Metrics
```

## Features

### Milestone 1
- FastAPI backend with health check
- Model registry with tier-based metadata (Small / Medium / Strong)
- REST API for listing, viewing, enabling/disabling models
- React dashboard shell with Model Registry UI

### Milestone 2
- Provider adapters (OpenAI, Anthropic, Google, OpenAI-compatible, Mock)
- `POST /api/chat` with cost and latency tracking

### Milestone 3
- Prompt feature extraction (length, code, math, reasoning, instructions)
- Task classification across 13 task types
- Difficulty scoring (0–1)
- Quality/cost routing policy with configurable quality floor
- `RuleBasedRouter` with explainable structured decisions
- `POST /api/route` and `model: "auto"` in chat
- Chat UI with routing preview and explanation panel

### Milestone 4
- SQLite routing logs (cost, latency, quality, task type)
- Central metrics module (`cost_reduction`, `quality_retention`, `strong_model_usage`)
- Mock + OpenAI LLM-as-judge evaluation
- Benchmark runner (Always Strong / Always Cheap / Adaptive Router)
- `POST /api/evaluate`, `POST /api/benchmark`, `GET /api/metrics`, `GET /api/benchmarks`
- Analytics and Benchmark dashboard pages with Recharts

### Milestone 5
- Multi-model response collection (small / medium / strong)
- Judge scoring with full structured metadata per tier
- Preference labels (`preferred_model`, `small_sufficient`, etc.)
- JSONL dataset storage + manifest index
- Human evaluation override endpoint
- `POST /api/dataset/generate`, dataset viewer UI
- Training CLI scripts (`generate_dataset.py`, `evaluate_responses.py`, `prepare_dataset.py`)

### Milestone 6
- Preference dataset → binary `strong_better` labels for router training
- TF-IDF + Logistic Regression, SentenceTransformer embedding, and BERT-style MLP trainers
- Trained artifact registry (`models/`) with joblib persistence
- ML routers (`tfidf`, `embedding`, `bert`) with probability-based tier selection
- `POST /api/training/start`, `GET /api/training/status/{id}`, `GET /api/training/models`
- Training dashboard with metrics, confusion matrix, and router activation

### Milestone 7
- Automatic tier escalation on retryable provider errors (timeout, rate limit, network)
- Quality-based escalation when judge score falls below `FALLBACK_ON_QUALITY_BELOW`
- Configurable fallback chain (`tier_up` or `strong_only`) with `MAX_FALLBACK_ATTEMPTS`
- Cost/latency-weighted model selection via `COST_PRIORITY` and `LATENCY_PRIORITY`
- Fallback metadata in chat responses and routing logs (`fallback_rate` in analytics)

### Milestone 8
- Dashboard overview page with system metrics and quick navigation
- Complete Chat UI: tier comparison, prompt features, quality floor override, response evaluation
- Model registry CRUD with detail view (create, edit, enable/disable)
- Analytics refresh, tier chart, total/average cost metrics
- Benchmark strategy picker, progress bars, clickable report history
- Dataset pagination, record review modal, human evaluation overrides
- Training progress, trained-model comparison table, test-in-chat link
- Settings page with full routing/fallback config and API docs link

### Milestone 9
- OpenAI-compatible `POST /v1/chat/completions` with `model: "auto"` adaptive routing
- `GET /v1/models` and `GET /v1/models/{id}` including the virtual `auto` model
- Standard OpenAI response shape (`choices`, `usage`, `chat.completion` object)
- Optional `router` metadata block with task type, tier, cost, and fallback info
- Optional bearer auth via `ROUTER_API_KEY` for production drop-in use
- Quality floor override via `X-Quality-Floor` request header

### Milestone 10
- Final evaluation suite: strategy comparison, quality-floor ablation, router comparison
- `POST /api/experiments/run`, experiment job status, report listing and retrieval
- Auto-generated markdown summaries from measured metrics (no hard-coded results)
- CLI runner: `python experiments/run_final_evaluation.py`
- Experiments dashboard page with charts and report history
- Reports persisted under `experiments/reports/`

## Technology Stack

| Layer    | Technology                          |
|----------|-------------------------------------|
| Frontend | React, TypeScript, Vite, Tailwind   |
| Backend  | Python, FastAPI, Pydantic, Uvicorn |
| Data     | JSON (registry), SQLite (planned)   |
| ML       | scikit-learn, sentence-transformers (Milestone 6+) |

## Project Structure

```
adaptive-model-router/
├── backend/          # FastAPI application
├── frontend/         # React dashboard
├── data/             # Datasets and registry persistence
├── models/           # Trained ML router artifacts
├── experiments/      # Benchmark results
└── docs/             # Documentation
```

## Installation

### Prerequisites

- Python 3.11+
- Node.js 18+
- (Optional) API keys for LLM providers

### Backend Setup

```bash
cd adaptive-model-router/backend
python -m venv .venv

# Windows
.venv\Scripts\activate

# macOS/Linux
source .venv/bin/activate

pip install -r requirements.txt
cp ../.env.example ../.env
```

### Frontend Setup

```bash
cd adaptive-model-router/frontend
npm install
```

## Running the Application

### Start Backend

```bash
cd backend
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

API docs: http://localhost:8000/docs

### Start Frontend

```bash
cd frontend
npm run dev
```

Dashboard: http://localhost:5173

## Environment Variables

Copy `.env.example` to `.env` at the project root:

| Variable           | Description                          | Default        |
|--------------------|--------------------------------------|----------------|
| `ROUTER_TYPE`      | Router implementation (`rule_based`, `tfidf`, `embedding`, `bert`) | `rule_based`   |
| `ROUTING_THRESHOLD`| ML router probability threshold for strong tier | `0.60`         |
| `FALLBACK_ENABLED` | Enable automatic tier escalation on failures | `true`         |
| `MAX_FALLBACK_ATTEMPTS` | Max models to try per request           | `3`            |
| `FALLBACK_ON_QUALITY_BELOW` | Escalate when judge score is below | `0.85`         |
| `FALLBACK_ESCALATION` | `tier_up` or `strong_only`             | `tier_up`      |
| `QUALITY_FLOOR`    | Minimum acceptable quality           | `0.90`         |
| `COST_PRIORITY`    | Cost vs latency weight               | `0.7`          |
| `OPENAI_API_KEY`   | OpenAI provider key                  | (empty)        |
| `ANTHROPIC_API_KEY`| Anthropic provider key               | (empty)        |
| `GOOGLE_API_KEY`   | Google provider key                  | (empty)        |
| `STORE_PROMPTS`    | Persist user prompts (privacy)       | `false`        |

## API Endpoints (Milestone 1)

| Method | Endpoint              | Description              |
|--------|-----------------------|--------------------------|
| GET    | `/health`             | Health check             |
| GET    | `/api/models`         | List all models          |
| GET    | `/api/models/{id}`    | Get model by ID          |
| POST   | `/api/models`         | Add a model              |
| PATCH  | `/api/models/{id}`    | Update model metadata    |
| POST   | `/api/models/{id}/enable`  | Enable model          |
| POST   | `/api/models/{id}/disable` | Disable model         |
| GET    | `/api/router/status`  | Router configuration     |
| POST   | `/api/route`          | Analyze prompt & route   |
| POST   | `/api/chat`           | Chat (supports `auto`)   |
| POST   | `/api/evaluate`       | Judge a prompt/response  |
| POST   | `/api/benchmark`      | Start benchmark job      |
| GET    | `/api/benchmark/status/{id}` | Benchmark job status |
| GET    | `/api/benchmarks`     | List benchmark reports   |
| GET    | `/api/metrics`        | Aggregated routing metrics |
| POST   | `/api/dataset/generate` | Start preference dataset job |
| GET    | `/api/dataset/generate/status/{id}` | Dataset job status |
| GET    | `/api/dataset`        | List datasets            |
| GET    | `/api/dataset/{id}`   | View preference records  |
| POST   | `/api/dataset/{id}/human-eval` | Human label override |
| POST   | `/api/training/start` | Train an ML router from a dataset |
| GET    | `/api/training/status/{id}` | Training job status |
| GET    | `/api/training/models` | List trained router artifacts |

## Using Chat (Milestone 2)

**Without API keys** — use mock models (`mock-echo`, `mock-echo-medium`, `mock-echo-strong`):

```bash
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"model":"mock-echo","messages":[{"role":"user","content":"Hello"}]}'
```

**With OpenAI** — set `OPENAI_API_KEY` in `.env`, then use `gpt-4o-mini`, `gpt-4o`, or `gpt-4-turbo`.

The Chat page at http://localhost:5173/chat lets you select a model, send prompts, and view cost/latency metadata.

## OpenAI-Compatible API (Milestone 9)

Use any OpenAI SDK by pointing `base_url` at this server. Set `model` to `"auto"` for adaptive routing.

```bash
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"auto","messages":[{"role":"user","content":"Explain binary search"}]}'
```

**Python (OpenAI SDK):**

```python
from openai import OpenAI

client = OpenAI(base_url="http://localhost:8000/v1", api_key="not-needed")
response = client.chat.completions.create(
    model="auto",
    messages=[{"role": "user", "content": "Summarize merge sort."}],
)
print(response.choices[0].message.content)
print(response.model)  # actual routed model id
```

Optional headers:
- `X-Quality-Floor: 0.92` — override routing quality requirement
- `Authorization: Bearer <ROUTER_API_KEY>` — required when `ROUTER_API_KEY` is set in `.env`

List models (includes virtual `auto` model):

```bash
curl http://localhost:8000/v1/models
```

Responses include an optional `router` object with routing metadata (task type, tier, cost, fallback).

## Configuring Models

Models are stored in `data/processed/model_registry.json`. Default models include three OpenAI tiers (Small/Medium/Strong). Enable additional providers by setting API keys and toggling models in the Model Registry UI.

Override tier assignments via environment variables:

```
SMALL_MODEL_ID=gpt-4o-mini
MEDIUM_MODEL_ID=gpt-4o
STRONG_MODEL_ID=gpt-4-turbo
```

## Running Tests

```bash
cd backend
pytest -v
```

## Development Roadmap

| Milestone | Feature                          | Status      |
|-----------|----------------------------------|-------------|
| 1         | Infrastructure + Model Registry  | ✅ Complete |
| 2         | Provider adapters + Chat API       | ✅ Complete |
| 3         | Rule-based router                | ✅ Complete |
| 4         | Evaluation + Benchmarking        | ✅ Complete |
| 5         | Preference dataset pipeline      | ✅ Complete |
| 6         | ML routers (TF-IDF, Embedding, BERT) | ✅ Complete |
| 7         | Fallback + optimization          | ✅ Complete |
| 8         | Full dashboard                   | ✅ Complete |
| 9         | OpenAI-compatible API            | ✅ Complete |
| 10        | Final evaluation                 | ✅ Complete |

## Generating Preference Data

```bash
# Via API
curl -X POST http://localhost:8000/api/dataset/generate \
  -H "Content-Type: application/json" \
  -d "{\"source_path\":\"data/benchmarks/sample_prompts.json\",\"max_prompts\":8,\"quality_floor\":0.9}"

# Via CLI (from backend/)
python -m training.generate_dataset --max-prompts 8
python -m training.prepare_dataset --dataset-id <UUID> --output data/processed/training_set.csv
```

## Training an ML Router

1. Generate a preference dataset (Milestone 5) with at least 4 labeled records.
2. Open the **Training** page or call the API:

```bash
curl -X POST http://localhost:8000/api/training/start \
  -H "Content-Type: application/json" \
  -d "{\"dataset_id\":\"<UUID>\",\"router_type\":\"tfidf\",\"routing_threshold\":0.6}"
```

3. Set `ROUTER_TYPE=tfidf` (or `embedding` / `bert`) in `.env` after training completes.
4. Restart the backend so the trained artifact is loaded.

## Final Evaluation (Milestone 10)

Run the complete research suite comparing strategies, quality floors, and router implementations:

```bash
# Via API
curl -X POST http://localhost:8000/api/experiments/run \
  -H "Content-Type: application/json" \
  -d "{\"experiment_type\":\"final_evaluation\",\"max_prompts\":8,\"quality_floor\":0.9}"

# Via CLI (from backend/)
python experiments/run_final_evaluation.py --max-prompts 8
```

The suite produces three sections:
1. **Strategy Comparison** — Always Strong vs Always Cheap vs Adaptive Router
2. **Quality Floor Ablation** — adaptive routing at 0.85 / 0.90 / 0.95 floors
3. **Router Comparison** — rule-based vs trained ML routers (skips unavailable models)

Reports are saved to `experiments/reports/` with auto-generated markdown summaries. Use the **Experiments** page in the dashboard to run and inspect results.

## Limitations (v1.0)

- Streaming (`stream=true`) is not supported on `/v1/chat/completions`
- Settings are read-only in the UI (configure via `.env` + backend restart)
- Background jobs are in-memory (Celery/RQ planned)

## Future Improvements

- Contextual bandit routing (extension point prepared)
- PostgreSQL persistence
- Celery/RQ for background training jobs
- Streaming chat responses
- Rate limiting and authentication

## License

Academic project — final year AIML coursework.
#   A d a p t i v e _ M o d e l _ R o u t e r  
 