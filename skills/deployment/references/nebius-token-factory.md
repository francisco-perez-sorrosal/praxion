# Nebius Token Factory — Management Reference

Pro-level operation of **Nebius Token Factory** (the managed, OpenAI-compatible inference platform
that evolved from "Nebius AI Studio"). Use this when serving open models or your fine-tunes on Nebius
**without managing GPUs** — the platform owns the H200/H100 fleet; you call an API.
Back to [ai-native-platforms.md](ai-native-platforms.md) · [SKILL.md](../SKILL.md).

For **bring-your-own-GPU** serving (your own vLLM server on Nebius GPUs) or **training-job dispatch**,
see [ai-native-platforms.md](ai-native-platforms.md) and
[neo-cloud-abstraction/references/nebius-direct-adapter.md](../../neo-cloud-abstraction/references/nebius-direct-adapter.md).

## Contents

- [Mental model: control plane vs data plane](#mental-model-control-plane-vs-data-plane)
- [Authentication and access management](#authentication-and-access-management)
- [Model catalog — the live source of truth](#model-catalog--the-live-source-of-truth)
- [Inference (data plane)](#inference-data-plane)
- [Dedicated endpoints (control plane)](#dedicated-endpoints-control-plane)
- [Fine-tuning (managed post-training)](#fine-tuning-managed-post-training)
- [Cost and usage management](#cost-and-usage-management)
- [Hackathon fast path](#hackathon-fast-path)
- [References](#references)

---

## Mental model: control plane vs data plane

Token Factory separates **two** API surfaces — managing them well means not conflating them:

| Plane | Purpose | Auth | Examples |
|---|---|---|---|
| **Data plane** | Run inference | `NEBIUS_API_KEY` (or a dedicated endpoint's routing key) | `chat/completions`, `embeddings`, `models` |
| **Control plane** | Manage resources | `NEBIUS_API_KEY` (admin/project-scoped) | create/scale/delete dedicated endpoints; fine-tuning jobs; files |

Shared access (serverless) uses only the data plane. Dedicated endpoints add a control-plane lifecycle
and issue a **dedicated routing key** that the data plane uses to target your isolated deployment.

## Authentication and access management

<!-- last-verified: 2026-06-06 -->

- **API key:** `Authorization: Bearer $NEBIUS_API_KEY`. Created in the Token Factory dashboard,
  **displayed once**, revocable if leaked. Set it as an env var; never commit it.
- **Base URL:** `https://api.tokenfactory.nebius.com/v1/` (OpenAI-compatible — point any OpenAI SDK here).
- **Dedicated routing key:** each dedicated endpoint issues its own key tied to that endpoint; use it
  in place of the shared key to route inference to your isolated deployment.
- **Enterprise controls:** Teams & Access Management, SSO, **project separation** (`ai_project_id`),
  granular RBAC (least-privilege roles), audit trails, and project-scoped billing. For a hackathon,
  a single project + one API key is enough; for production, separate projects per environment.

## Model catalog — the live source of truth

<!-- last-verified: 2026-06-06 -->

**Do not hardcode a model list — it drifts.** Query the catalog:

```bash
curl https://api.tokenfactory.nebius.com/v1/models \
  -H "Authorization: Bearer $NEBIUS_API_KEY"
```

```python
client.models.list()                       # ids like "deepseek-ai/DeepSeek-R1-0528"
```

Response is the OpenAI `list` shape — `data: [{ id, created, object, owned_by }]`. Two query params:

| Param | Effect |
|---|---|
| `verbose=true` | Returns the `RichModel` schema: `supported_features` (e.g. chat, embeddings, vision, fine-tunable), architecture, and pricing |
| `ai_project_id=<id>` | Filters the catalog to a project (includes your own fine-tuned/hosted models) |

Token Factory publishes **60+ open models**. Families commonly available include **DeepSeek**, **Qwen**
(Qwen3 / Qwen2.5 — dense, MoE, coder), **GLM**, **Gemma**, **Llama**, **Mistral**, **GPT-OSS**, and
**NVIDIA** (Nemotron; Cosmos world-foundation models where provisioned). Treat any named list as an
example — `GET /v1/models?verbose=true` is the authoritative, current catalog for your project and
region, including which models are fine-tunable.

## Inference (data plane)

<!-- last-verified: 2026-06-06 -->

Standard OpenAI surface — chat, streaming, structured output, embeddings:

```python
import os
from openai import OpenAI

client = OpenAI(
    base_url="https://api.tokenfactory.nebius.com/v1/",
    api_key=os.environ["NEBIUS_API_KEY"],   # or a dedicated endpoint routing key
)

# chat (add stream=True for token streaming)
resp = client.chat.completions.create(
    model="deepseek-ai/DeepSeek-R1-0528",
    messages=[{"role": "user", "content": "hello"}],
)

# structured / schema-constrained output
resp = client.chat.completions.create(
    model="Qwen/Qwen3-30B-A3B",
    messages=[{"role": "user", "content": "extract the invoice as JSON"}],
    response_format={"type": "json_schema", "json_schema": {"name": "invoice", "schema": {...}}},
)

# embeddings
emb = client.embeddings.create(model="<embedding-model-id>", input=["text to embed"])
```

Structure-aware decoding (schema-constrained output) is a first-class feature — pair it with
`response_format` to guarantee parseable output. Confirm a model supports it via the `verbose` catalog.

## Dedicated endpoints (control plane)

<!-- last-verified: 2026-06-06 -->

A **dedicated endpoint** is an isolated deployment of a model template with reserved capacity, a 99.9%
SLA, predictable latency, and autoscaling — distinct from shared (serverless, multi-tenant) access.
Created and managed through the **control plane** (dashboard or control-plane API). You define:

| Parameter | Purpose |
|---|---|
| **Region** | Data residency + latency (EU / US) |
| **GPU type + GPUs/replica** | The hardware behind each replica (e.g. H200) |
| **Autoscaling** | `min_replicas` (baseline; set 2 for guaranteed capacity) and `max_replicas` (peak-cost bound, e.g. 8) |
| **Model / checkpoint** | A catalog model template, or your fine-tuned checkpoint (Custom Weights Hub) |

**Lifecycle operations:** create, **update**, **enable**, **disable**, **delete** — control-plane and
data-plane scale independently, so you manage capacity without interrupting traffic execution. Each
endpoint issues a **dedicated routing key**; point the OpenAI SDK at the base URL with that key to hit
your isolated deployment.

**Custom Weights Hub:** deploy a fine-tuned or distilled checkpoint to an endpoint without changing
tools, and **update the same endpoint with a new checkpoint** as you iterate — the endpoint identity
(and routing key) stays stable across model versions.

> Exact control-plane endpoint paths / CLI verbs are evolving; the dashboard exposes the full lifecycle,
> and canonical API examples live in the [token-factory-cookbook](https://github.com/nebius/token-factory-cookbook).
> Verify the current control-plane API shape there before scripting endpoint automation.

**When to go dedicated vs shared:** start on **shared access** (serverless, $/token, free credits) for
experiments and bursty traffic; move to a **dedicated endpoint** when you need guaranteed latency, a
data-residency region pin, reserved capacity for sustained high volume, or to serve a private fine-tune.

## Fine-tuning (managed post-training)

<!-- last-verified: 2026-06-06 -->

Token Factory runs LoRA and full fine-tuning as a **managed** service (no GPU provisioning) and
auto-hosts the result — the OpenAI fine-tuning API shape:

**1. Upload a JSONL dataset** via the Files API (split 80–90% train / 10–20% validation):

```python
training_file = client.files.create(file=open("training.jsonl", "rb"), purpose="fine-tune")
```

**2. Launch the job** (`POST /v1/fine_tuning/jobs`):

```python
job = client.fine_tuning.jobs.create(
    model="meta-llama/Llama-3.1-8B-Instruct",   # a fine-tunable catalog model
    training_file=training_file.id,
    hyperparameters={"n_epochs": 3, "batch_size": 8, "learning_rate": 1e-5},
    # LoRA-specific (when lora=true): lora_r, lora_alpha, lora_dropout
    # integrations: Weights & Biases / Hugging Face for metrics + model export
)
```

| Hyperparameter | Range | Default |
|---|---|---|
| `lora` | true (frozen base + adapter) / false (full retrain) | true |
| `n_epochs` | 1–20 | 3 |
| `batch_size` | 8–32 | 8 |
| `learning_rate` | 1e-6 – 5e-5 | 1e-5 |
| `context_length` | model-dependent | 8192 |
| `lora_r` / `lora_alpha` / `lora_dropout` | 8–128 / ≥8 / 0–1 | 8 / 8 / 0 |

**3. Monitor** — poll every 15 s+:

```bash
GET /v1/fine_tuning/jobs/<job_id>            # status + trained_steps/total_steps/trained_tokens
GET /v1/fine_tuning/jobs/<job_id>/events     # lifecycle log
GET /v1/fine_tuning/jobs/<job_id>/checkpoints # result_files = adapter config + weights
```

Status progression: `validating_files → queued → running → succeeded | failed`.

**4. Deploy** — serve the produced checkpoint from the same OpenAI-compatible surface (key models like
Llama-3.1-8B / Qwen2.5-72B / Llama-3.3-70B support instant auto-hosting), or attach it to a dedicated
endpoint via Custom Weights Hub.

> **Two fine-tuning paths, pick deliberately:** Token Factory's *managed* FT (above) needs no GPU
> management and auto-hosts — ideal for a hackathon. For full control over the training loop on raw
> GPUs, dispatch a training job via the `nebius-direct` backend
> ([nebius-direct-adapter.md](../../neo-cloud-abstraction/references/nebius-direct-adapter.md)) and serve
> the result here. The managed path trades control for speed; the dispatch path trades speed for control.

## Cost and usage management

- **Shared access:** transparent **$/token** (input/output priced separately), volume discounts, no
  idle-GPU cost — you pay only for tokens served. Free credits to start.
- **Dedicated endpoints:** reserved capacity (priced for the reservation) — bound peak spend with
  `max_replicas` and reclaim cost by `disable`-ing idle endpoints.
- **Visibility:** per-project billing + audit trails; pull live per-model pricing from
  `GET /v1/models?verbose=true`. For Praxion ML projects, record served-inference spend alongside
  training spend (the `deployment` skill's
  [gpu-compute-budgeting.md](gpu-compute-budgeting.md) covers the budget-declaration discipline).

## Hackathon fast path

The lowest-latency route to "calling H200-backed models":

```bash
export NEBIUS_API_KEY="<from the Token Factory dashboard>"
curl https://api.tokenfactory.nebius.com/v1/models -H "Authorization: Bearer $NEBIUS_API_KEY" \
  | jq '.data[].id'                                   # see what's instantly available
```

```python
from openai import OpenAI; import os
client = OpenAI(base_url="https://api.tokenfactory.nebius.com/v1/", api_key=os.environ["NEBIUS_API_KEY"])
print(client.chat.completions.create(
    model="deepseek-ai/DeepSeek-R1-0528",              # swap for any catalog id: Qwen, GLM, Gemma, Cosmos...
    messages=[{"role": "user", "content": "ship it"}],
).choices[0].message.content)
```

No GPU provisioning, no container, no endpoint to manage — instant model access on the shared tier.
Reach for a dedicated endpoint only when you need a region pin, reserved capacity, or to serve a
private fine-tune.

## References

- [Token Factory docs](https://docs.tokenfactory.nebius.com/) — quickstart, API reference
- [List models API](https://docs.tokenfactory.nebius.com/api-reference/models/list-models) — catalog endpoint + `verbose`
- [How to fine-tune](https://docs.tokenfactory.nebius.com/post-training/how-to-fine-tune) — Files API, jobs, checkpoints
- [Dedicated Endpoints + Custom Weights Hub](https://nebius.com/blog/posts/dedicated-endpoints-and-custom-weights-hub) — control-plane concepts
- [token-factory-cookbook](https://github.com/nebius/token-factory-cookbook) — canonical API examples (verify current control-plane shapes here)
- [Token Factory product page](https://nebius.com/services/token-factory) — tiers, SLA, pricing model
