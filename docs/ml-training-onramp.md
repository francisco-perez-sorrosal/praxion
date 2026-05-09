---
diataxis: tutorial
audience: developer
---

# ML Training Onramp

Companion doc for Praxion's third project archetype: ML/AI training. Where the SWE archetype reaches code via tests and the Agentic-AI archetype reaches deployable agents via behavioral acceptance, the ML archetype reaches a checkpoint that meets a metric threshold via evals. This doc covers the artifacts, modes, commands, and rules that make Praxion eval-aware. Pre-training v1; the [autoresearch case study](#the-autoresearch-case-study) is the proof target, not the only target.

## Quick links

- **Skills:** [`ml-training`](../skills/ml-training/SKILL.md), [`llm-training-eval`](../skills/llm-training-eval/SKILL.md), [`neo-cloud-abstraction`](../skills/neo-cloud-abstraction/SKILL.md), [`experiment-tracking`](../skills/experiment-tracking/SKILL.md)
- **Skill references:** [`gpu-compute-budgeting`](../skills/deployment/references/gpu-compute-budgeting.md) (under `deployment`), [`ml-experiment-ci`](../skills/cicd/references/ml-experiment-ci.md) (under `cicd`)
- **Rules:** [`ml/eval-driven-verification`](../rules/ml/eval-driven-verification.md), [`ml/gpu-budget-conventions`](../rules/ml/gpu-budget-conventions.md), [`ml/experiment-tracking-conventions`](../rules/ml/experiment-tracking-conventions.md)
- **Commands:** [`/run-experiment`](../commands/run-experiment.md), [`/check-experiment`](../commands/check-experiment.md), [`/onboard-project`](../commands/onboard-project.md) Phase 8c
- **Architecture:** [`docs/architecture.md`](architecture.md), `.ai-state/DESIGN.md`

## The third archetype in context

Praxion now recognizes three project archetypes:

| Archetype | Reaches done via | Quality gate | Primary feedback signal |
|-----------|------------------|--------------|-------------------------|
| SWE | Tests pass | Behavioral tests | Pass/fail per acceptance criterion |
| Agentic-AI | Tests + eval harness | Behavioral tests + agent evals | Pass/fail + capability scores |
| ML/AI training | Metric threshold met | Eval suite against a checkpoint | Numeric metric vs. tolerance band |

ML training is its own archetype because the failure modes are different: training is **eval-driven** rather than test-driven, **resource-bound** (GPU hours, dollar budgets, wall-clock weeks), and **exploratory** by nature — the right hyperparameters are not known up front, and "done" means a checkpoint cleared a threshold, not that 12 unit tests went green.

**Dual-archetype composition.** Karpathy's [autoresearch](https://github.com/karpathy/autoresearch) is the v1 proof target precisely because it sits at the intersection: it is a piece of software (SWE archetype) that drives an autonomous training loop (ML archetype). Managing it tests both archetypes simultaneously, which is why it is the seed.

The archetype recognizes six ML artifact types that no SWE project has and that no SWE convention manages well:

1. **Frozen eval harness** — the suite a checkpoint must clear; pinned by hash so progress is comparable across runs.
2. **Pinned dataset** — content-addressed; if the data changes, the experiment is a new experiment.
3. **Experiment log** — the chronological record of runs (see [`experiment-tracking`](../skills/experiment-tracking/SKILL.md)).
4. **Checkpoints** — saved model state per run; storage-cost gravity comes with these.
5. **Compute budget** — GPU hours and dollars declared up front; the verifier enforces.
6. **Hyperparameter block** — the dimensions you sweep over; the unit of "what changed."

## The three operational modes

Praxion supports three modes for where the GPU lives relative to your editor. The user-facing insight is that **Mode A and Mode B are the same Praxion configuration** — co-located with the GPU, whether the GPU is yours or rented.

| Mode | Where the GPU lives | Where Praxion runs | Praxion config |
|------|---------------------|--------------------|----------------|
| **A** | Your owned hardware (Mac M-series, RTX, on-prem) | Same machine | Local backend default |
| **B** | Rented GPU box (RunPod, Lambda, Crusoe, CoreWeave, etc.) — you SSH in | Same machine (the rented box) | **Identical to Mode A** |
| **C** | Remote (rented or owned) | Your laptop, dispatching to remote | SkyPilot default-remote, or opt-in direct adapters |

The Mode A ≡ Mode B equivalence is load-bearing: when you move from your laptop GPU to a rented H100 box, you do not reconfigure Praxion. You SSH into the box, install Praxion there, and run the same `/run-experiment` you ran locally. Mode C is the only mode that requires a backend choice, and that choice is governed by the [neo-cloud abstraction](#the-neo-cloud-abstraction).

For full walkthroughs of each mode (provisioning, environment setup, mode-specific gotchas), see [`skills/ml-training/references/operational-modes.md`](../skills/ml-training/references/operational-modes.md).

## The experiment loop

The read/write loop ties planning, dispatch, results, and verification together:

```
plan with metric-threshold AC
        |
        v
/run-experiment dispatches via configured backend (local | skypilot | direct)
        |
        v
backend writes TRAINING_RESULTS.md
        |
        v
/check-experiment polls (in-flight) or reports (completed)
        |
        v
verifier Phase 3a evaluates against ACs (PASS / FAIL / WARN with tolerance bands)
```

Four touch points:

- **[`/run-experiment`](../commands/run-experiment.md)** — dispatches the run via the configured backend (local, SkyPilot, or a direct adapter). Writes `TRAINING_RESULTS.md` as the run progresses; the schema is owned by the [`llm-training-eval`](../skills/llm-training-eval/SKILL.md) skill (see [`training-results-schema.md`](../skills/llm-training-eval/references/training-results-schema.md)).
- **[`/check-experiment`](../commands/check-experiment.md)** — reads `TRAINING_RESULTS.md`. Polls for in-flight runs; reports completed-run summaries (final metrics vs. ACs, wall-clock, dollars, checkpoints produced).
- **[`verifier` Phase 3a](../agents/verifier.md)** — eval-aware sub-branch of the existing verifier's Phase 3. Activates when `TRAINING_RESULTS.md` exists for the task slug; evaluates metric thresholds with tolerance bands per [`rules/ml/eval-driven-verification.md`](../rules/ml/eval-driven-verification.md).
- **`program.md`** — project-local meta-prompt for an autonomous experiment loop. Sibling of `CLAUDE.md`; consumed by `implementation-planner` and `verifier` when present.

**Dual lifecycle.** `TRAINING_RESULTS.md` lives ephemerally at `.ai-work/<task-slug>/TRAINING_RESULTS.md` for the duration of the pipeline. When a run is "kept" (autoresearch git-commit semantics), an archival copy is written to `.ai-state/training_runs/<run-tag>.md`. Failed runs leave the ephemeral copy in `.ai-work/` and are deleted with the rest of the task slug.

## The autoresearch case study

[Autoresearch](https://github.com/karpathy/autoresearch) is Karpathy's autonomous pre-training loop — a piece of software that proposes a hyperparameter change, dispatches a training run, evaluates the resulting checkpoint, and decides whether to keep or discard it. It is the v1 proof target for the third archetype because managing it exercises both the SWE and ML archetypes at once.

Two reference variants:

- **[`karpathy/autoresearch`](https://github.com/karpathy/autoresearch)** — NVIDIA reference implementation (CUDA).
- **[`miolini/autoresearch-macos`](https://github.com/miolini/autoresearch-macos)** — Apple Silicon fork (MPS).

When you onboard autoresearch with [`/onboard-project`](../commands/onboard-project.md), Phase 8c detects ML signals in the codebase (training entry points, eval harness, checkpoint directories, `program.md`) and scaffolds the conventions described in this doc — `rules/ml/`, `program.md` recognition, `TRAINING_RESULTS.md` placement, and the `runs/` directory if absent.

## Beyond autoresearch — what this archetype supports

The archetype is not autoresearch-specific. The same artifacts and conventions apply to:

- **LoRA / QLoRA fine-tuning.** Same eval-driven AC pattern; `gpu-budget-conventions` covers the (much smaller) per-run cost; `experiment-tracking` logs adapter weights as artifacts.
- **Multi-stage RL pipelines (SFT → reward → PPO).** Each stage has its own metric-threshold ACs; `program.md` orchestrates the multi-stage flow; `TRAINING_RESULTS.md` carries per-stage metrics.
- **Inference-evaluation harnesses (lm-eval-harness against deployed models).** No training, but the eval-driven verifier path applies unchanged; `experiment-tracking` records eval-only runs.
- **Multimodal training (VLM, multimodal LLMs).** Pinned-dataset convention covers paired modalities; eval suite is the bottleneck.
- **Embedding / RAG fine-tuning.** Smaller compute footprint; same artifact taxonomy; eval threshold is retrieval/recall metric instead of perplexity.

For each case the same six artifact types apply; only their concrete shape changes.

## The neo-cloud abstraction

Mode C — laptop driving remote training — is the mode that needs a backend choice. The [`neo-cloud-abstraction`](../skills/neo-cloud-abstraction/SKILL.md) skill defines a **mode-invariant `training_job_descriptor`**: the same descriptor that runs locally (Modes A/B via `subprocess.run`) routes to remote without modification.

Three-tier backend strategy:

| Tier | Backend | When to use |
|------|---------|-------------|
| 1 (default) | Local — `subprocess.run` | Modes A/B (co-located GPU, your machine or rented box you SSH'd into) |
| 2 (default-remote) | [SkyPilot 0.12.x](../skills/neo-cloud-abstraction/references/skypilot-backend.md) | Mode C exploration; 20+ providers; one config, many clouds |
| 3 (opt-in) | [Direct adapters](../skills/neo-cloud-abstraction/references/runpod-direct-adapter.md) | Mode C commitment; you've picked a provider and want native features (RunPod via `@runpod/mcp-server` is the v1 reference) |

**Praxion does not ship per-provider MCP servers.** Per user adjudication (Q6, see `LEARNINGS.md`), the `neo-cloud-abstraction` skill teaches the integration pattern for direct adapters; users invoke whichever upstream MCP server (or HTTP API) the provider publishes. This keeps the abstraction's contract clear without coupling Praxion to per-vendor maintenance cycles.

## Cross-references

| Surface | Path |
|---------|------|
| Skills | [`ml-training`](../skills/ml-training/SKILL.md), [`llm-training-eval`](../skills/llm-training-eval/SKILL.md), [`neo-cloud-abstraction`](../skills/neo-cloud-abstraction/SKILL.md), [`experiment-tracking`](../skills/experiment-tracking/SKILL.md) |
| Skill references | [`operational-modes`](../skills/ml-training/references/operational-modes.md), [`training-results-schema`](../skills/llm-training-eval/references/training-results-schema.md), [`local-backend`](../skills/neo-cloud-abstraction/references/local-backend.md), [`skypilot-backend`](../skills/neo-cloud-abstraction/references/skypilot-backend.md), [`runpod-direct-adapter`](../skills/neo-cloud-abstraction/references/runpod-direct-adapter.md), [`gpu-compute-budgeting`](../skills/deployment/references/gpu-compute-budgeting.md), [`ml-experiment-ci`](../skills/cicd/references/ml-experiment-ci.md) |
| Rules | [`ml/eval-driven-verification`](../rules/ml/eval-driven-verification.md), [`ml/gpu-budget-conventions`](../rules/ml/gpu-budget-conventions.md), [`ml/experiment-tracking-conventions`](../rules/ml/experiment-tracking-conventions.md) |
| Commands | [`/run-experiment`](../commands/run-experiment.md), [`/check-experiment`](../commands/check-experiment.md), [`/onboard-project`](../commands/onboard-project.md) Phase 8c |
| Architecture | [`docs/architecture.md`](architecture.md), `.ai-state/DESIGN.md` |
| Verifier extension | [`agents/verifier.md`](../agents/verifier.md) Phase 3a |

The pipeline that produced these artifacts also generated `RESEARCH_FINDINGS`, `SYSTEMS_PLAN`, and ADR drafts in `.ai-work/<task-slug>/` and `.ai-state/decisions/drafts/`. Drafts are promoted to stable `dec-NNN` records at merge-to-main; the `RESEARCH_FINDINGS` and `SYSTEMS_PLAN` are pipeline-internal and deleted with `.ai-work/`.

## Troubleshooting / FAQ

**Do I need a GPU to use this?** No, not to use the planning surfaces. Mode C lets you drive remote GPUs from a laptop with no local accelerator. To run anything end-to-end without a GPU, you use Mode C with a SkyPilot or direct-adapter backend.

**How does this differ from app observability?** [Observability](observability.md) traces agent sessions and tool calls (Phoenix, OTel) — what happened in a Claude Code session. [`experiment-tracking`](../skills/experiment-tracking/SKILL.md) tracks training runs (MLflow, W&B, Aim) — what happened in a model. They have different time horizons (seconds vs. weeks), different data shapes (spans vs. scalar metric series), and different decision models (debug a session vs. compare runs). Praxion treats them as conceptually distinct.

**Can I use Praxion for fine-tuning, not just pre-training?** Yes. Pre-training is the v1 *proof* target (autoresearch); the archetype's artifacts and conventions apply to LoRA/QLoRA fine-tuning, RL pipelines, embedding training, and inference-evaluation harnesses unchanged. See [Beyond autoresearch](#beyond-autoresearch--what-this-archetype-supports).

**Where does `program.md` live and what reads it?** Project root, sibling of `CLAUDE.md`. `implementation-planner` reads it when present (it shapes how the planner decomposes an experiment-loop task); `verifier` reads it when present (it informs Phase 3a's understanding of "what is this run trying to achieve"). Discovery is by file presence — no manifest entry needed.
