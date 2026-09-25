# How this compares with other model-routing systems

Several large platforms and open-source projects already route requests between language models. This page describes how they work (from their own documentation), how this project differs, and where it is weaker. It is a comparison of *designs*. **No head-to-head benchmark against any of these systems has been run**, so nothing here claims that this project performs better.

Vendor details were read from primary documentation on 2026-09-25 and can change; every row links its source. Anything that could not be confirmed from a primary source is marked *not verified*.

## Summary table

| System | Routes between | How the choice is made | Uses your own traffic to adapt? | Routing fee | Published savings claim (self-reported unless noted) |
|---|---|---|---|---|---|
| **Azure AI Foundry model router** | A pool of models from several vendors (docs list OpenAI, Anthropic, xAI, DeepSeek, Meta) | A trained language model that reads the prompt; modes *Balanced* (default), *Cost*, *Quality*; optional model subset; automatic failover | Not described in the docs | See Azure pricing page | None with a figure in the docs. A Microsoft community blog reports 4.5% to 14.2% savings in its own test (secondary source, not verified) |
| **AWS Bedrock Intelligent Prompt Routing** | Two models from **one family** (for example a Claude pair or a Llama pair) | Predicts each model's response quality per prompt; a configurable "quality difference" threshold decides when to switch | No: the docs say it cannot use application-specific performance data | Not re-checked (no extra cost during the 2024 preview) | "Up to 30 percent" without stated methodology |
| **Google Vertex AI Model Optimizer** | Gemini models | User sets a quality/cost balance | Not verified | Not verified | None found. *Primary doc did not load; details not verified* |
| **Databricks Unity AI Gateway smart routing** (beta) | Models in the gateway catalog, aimed at coding agents | A cheap model classifies the task once at session start; escalates or de-escalates from a default | Not described | Not stated | "30%+ lower cost per task"; vendor benchmarks |
| **OpenRouter Auto Router** | Many providers' models | A classifier assigns one of about 30 task types; candidates ranked by recent community spend within a cost band; allow/exclude lists | No | None beyond the selected model's price | None found |
| **LiteLLM** (open source) | Any provider | Load-balancing strategies; an *Auto Router* (beta) using heuristic scoring, keywords or an LLM classifier | Rules you write | Open source | None |
| **RouteLLM** (open source, LMSYS) | One stronger and one weaker model | Routers trained on human preference data; a threshold sets the share sent to the strong model | You can train your own | Open source | Reported in the paper on specific benchmarks |
| **Not Diamond** | Many providers' models | Pre-trained routers, or custom routers trained on your evaluation data | Yes, on evaluation data you supply | Not public in docs | Not quantified in docs |
| **This project** | Any enabled model in the registry (mixed vendors via adapters) | Learned router: per-model quality estimated from *this deployment's* judged history, cheapest model that clears your quality floor; static fallback until enough data | Yes, by design; it cannot use data it does not have, and falls back when it lacks it | Self-hosted; you pay only your model providers | **None claimed.** Offline results are in [EVALUATION.md](EVALUATION.md) |

Sources: Azure [model router docs](https://learn.microsoft.com/en-us/azure/ai-foundry/openai/concepts/model-router) and a Microsoft [community blog](https://techcommunity.microsoft.com/blog/azuredevcommunityblog/optimising-ai-costs-with-microsoft-foundry-model-router/4494776); AWS [prompt routing docs](https://docs.aws.amazon.com/bedrock/latest/userguide/prompt-routing.html) and [announcement](https://aws.amazon.com/blogs/aws/reduce-costs-and-latency-with-amazon-bedrock-intelligent-prompt-routing-and-prompt-caching-preview/); Google [Vertex model optimizer](https://docs.cloud.google.com/vertex-ai/generative-ai/docs/model-reference/vertex-ai-model-optimizer); Databricks [smart routing docs](https://docs.databricks.com/aws/en/ai-gateway/smart-routing) and [blog](https://www.databricks.com/blog/smart-routing-unity-ai-gateway-match-frontier-quality-30-lower-cost-task); OpenRouter [Auto Router](https://openrouter.ai/docs/guides/routing/routers/auto-router); LiteLLM [routing](https://docs.litellm.ai/docs/routing) and [auto routing](https://docs.litellm.ai/docs/proxy/auto_routing); RouteLLM [paper](https://arxiv.org/abs/2406.18665) and [repository](https://github.com/lm-sys/RouteLLM); Not Diamond [docs](https://docs.notdiamond.ai/docs/what-is-model-routing).

## Common ground

Every system above turns "which model?" into a prediction problem: estimate, before calling anything, whether a cheaper model will be good enough for *this* prompt. They differ in what they predict from (the prompt alone, or also outcomes), what they are trained on, and who controls the training data.

## How this project differs

- **The training data is yours.** The hyperscaler routers are closed models trained on data their vendors do not disclose. This project's learned router trains only on the judged outcomes of the deployment it runs in, so it adapts to your workload and your models, and nothing about your traffic leaves your database.
- **Every decision is explained.** Each response carries the task type, per-model estimates marked *measured* or *assumed*, what was excluded and why, and whether the choice was a fallback, a guarded segment, or a bet on limited evidence.
- **Hard constraints are separate from preference.** Capability, circuit health and cost/latency limits are filters applied before scoring, so a cheap model that cannot do what the request needs is never chosen for being cheap.
- **A way to observe before acting.** Shadow mode logs what the learned router would have chosen without affecting any request, and a per-task quality guard stops cost-cutting where quality drops. See [HOW_ROUTING_WORKS.md](HOW_ROUTING_WORKS.md).
- **Vendor-neutral.** Providers are small adapters. AWS's router works within one model family; Vertex's within Gemini.
- **Reproducible evidence.** [`backend/routing_lab`](../backend/routing_lab) evaluates routers against baselines (each single model, the best single model, random mixing, an oracle) with bootstrap confidence intervals, on a public dataset anyone can download.

## Where this project is weaker

- **Scale.** The large platforms route across dozens of current models with training data far beyond anything here. This project's evaluation covered 13 models from 2024 on one public benchmark.
- **No production track record.** The results are offline. The learned router has not been run on live traffic, and only mock providers have been used end to end.
- **No managed service.** No hosted option, no service-level agreement, and no built-in multi-tenant isolation: one shared API key and SQLite storage today.
- **Missing features.** No streaming responses, no per-customer keys or rate limits.
- **Cold start.** Until a deployment has enough judged traffic the router uses hand-set static rules, which on the offline evaluation were no better than random mixing.
- **Judge dependence.** Quality is only as trustworthy as the judge model, a dependency the closed platforms also have but hide.
- **Bandit feedback.** Online, the router only sees answers from models it chose. The offline evaluation had every model's answer to every prompt, so it flatters the online setting.

## What independent evidence says about routing in general

The one independent, large-scale comparison found was **LLMRouterBench** ([arXiv 2601.07206](https://arxiv.org/abs/2601.07206)): over 400,000 instances, 21 datasets, 33 models. Its authors report that many routing methods perform similarly under a unified evaluation and that several recent approaches, *including a commercial router (OpenRouter)*, fail to reliably beat a simple baseline of the best single model. It also finds a large gap between routers and an oracle that always picks the best model. No independent measurement of the savings claimed by the Azure, AWS, Google or Databricks routers was found.

The lesson this project takes from that: a routing claim is only meaningful against the right baselines. Its own evaluation therefore compares with the best single model, the cheapest single model that meets the same quality bar, random mixing and an oracle, and reports intervals. Its result is modest and stated as such: the learned router beat random mixing by a small, statistically clear margin (AIQ uplift +0.030, 95% interval 0.025 to 0.035), the original static rules did not (+0.004), and the learned router did not transfer to data sources it had not been trained on. Details and caveats are in [EVALUATION.md](EVALUATION.md).

## Choosing between them

| If you need... | Consider |
|---|---|
| A managed router inside an existing Azure or AWS estate, no infrastructure to run | The platform's own router |
| Simple, predictable rules and load balancing across providers | LiteLLM |
| A research baseline to build on | RouteLLM |
| A router trained on your evaluation data as a service | Not Diamond |
| A self-hosted gateway where the routing is trained on your own traffic, explainable, and observable before it acts | This project, accepting the limits above |
