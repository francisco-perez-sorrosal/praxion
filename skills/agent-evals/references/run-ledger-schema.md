# Run-Ledger Schema

Schema reference for `EVAL_RESULTS.md`, `EVAL_LOG.md`, and the `run_store_descriptor`.
Owned by the `agent-evals` skill. Back to [SKILL.md](../SKILL.md).

<!-- last-verified: 2026-06-05 -->
<!-- conceptual ancestry: skills/llm-training-eval/references/training-results-schema.md -->

## Contents

- [Schema Overview](#schema-overview)
- [Canonical YAML — run_store_descriptor](#canonical-yaml--run_store_descriptor)
- [Field Constraints](#field-constraints)
- [Markdown Body](#markdown-body)
- [Dual Lifecycle](#dual-lifecycle)
- [Verifier Consumption](#verifier-consumption)
- [Run-Store Backend Abstraction](#run-store-backend-abstraction)
- [Schema Versioning](#schema-versioning)
- [Minimal Valid Example](#minimal-valid-example)

---

## Schema Overview

This document defines three artifacts that together implement the **two-tier storage model**
for agentic/eval-bearing managed projects:

| Artifact | Location | Tier | Purpose |
|---|---|---|---|
| `run_store_descriptor` | in-memory / `project_profile.yaml` | — | Backend-invariant run identity |
| `EVAL_RESULTS.md` | project root (sibling to `TRAINING_RESULTS.md`) | 2a (curated) | Per-kept-run curated summary |
| `EVAL_LOG.md` | `.ai-state/eval_ledger/EVAL_LOG.md` | 2b (aggregate) | Append-only run leaderboard |

**Writers:** the project's eval loop (when a run is *kept*)
**Readers:** `verifier` (metric-threshold evaluation), `/scores` command,
dashboard eval panel

**Invariant:** heavy per-run artifacts (generated code, logs, submissions, trajectories,
per-step traces) live exclusively in the tier-1 run store at `store_uri`. Only the curated
tier-2 summary and aggregate row are committed. No operational artifact appears in
`git status`.

---

## Canonical YAML — run_store_descriptor

The `run_store_descriptor` is **backend-invariant**: no field requires knowing which
backend is active except the resolved `store_uri`. Backend selection lives in
`project_profile.yaml` (`run_store_backend` + `run_store_root`), never in the descriptor.

> **Absent-behavior:** `project_profile.yaml` is `future-designed` — there is no onboarding producer yet (see `skills/software-planning/references/artifact-inventory.md`), so it is absent on essentially all projects today. When absent, consumers MUST fall back to live detection (default `local-home`: `$HOME/.<project-name>/runs/`); never assume the file exists.

```yaml
# run_store_descriptor — backend-invariant. NO backend-conditional fields.
# Backend is a project-level config concern (project_profile.yaml), NOT a descriptor field.
run_id: <string>         # Required. Content-addressed slug or UUID; assigned at run start.
project_name: <string>   # Required. Used to derive the default store_uri.
                         # Backend URI derivations (from project_profile.yaml):
                         #   local-home   → $HOME/.<project-name>/runs/<run_id>/
                         #   local-custom → <run_store_root>/runs/<run_id>/
                         #   s3           → s3://<bucket>/<prefix>/runs/<run_id>/
                         #   tracker      → mlflow|wandb run URI (via experiment-tracking)
store_uri: <uri>         # Required. Resolved location. THE ONLY backend-varying value
                         # downstream. Assigned after backend resolution.
artifact_paths:          # Required. Logical paths the eval loop writes.
  - code/
  - logs/
  - submission/
  - trace/metrics.jsonl
```

**Invariance rule:** trace the descriptor through all four backends. Does any field
besides `store_uri` require `if backend == s3` logic downstream? If yes, the schema is
wrong and the abstraction is leaking.

**Security rule:** credentials (`s3` bucket creds, tracker API keys) travel **outside**
the descriptor — never inside it. Same rule as `neo-cloud-abstraction`.

---

The `EVAL_RESULTS.md` schema uses YAML frontmatter + Markdown body, mirroring
`training-results-schema.md`'s structure but with eval-run-specific fields:

```yaml
---
schema_version: "1.0"     # Required. Increment major on breaking changes.

# Run identity
run_id: <string>           # Required. Cross-references the tier-1 store.
store_uri: <uri>           # Required. Where tier-1 heavy artifacts live.

# Task context
task: <string>             # Required. Which benchmark or task was evaluated.
generation: <int>          # Required. Iteration number in the eval loop.

# Metrics
primary_metric: <float>    # Required. The scored result (accuracy, F1, pass@k, …).
held_out_delta: <float>    # Required. Held-out vs public delta (contamination signal).
model_id: <string>         # Required. Model identifier (e.g., "claude-sonnet-4-5").

# Binding fields
prompt_hash: <string>      # SHA of the prompt template that produced this run.
                           # Hashing convention: skills/llm-prompt-engineering/
                           # references/versioning.md § Managed Prompt Versioning.
dataset_sha: <string>      # P3 provenance — dataset MANIFEST sha256.
                           # (Field is stable and required from Wave 0; the P3
                           # data-governance wave populates the validation rule.)

# Costs
token_usage:               # Required. Token accounting many agent loops discard — capture it.
  input: <int>
  output: <int>
  total: <int>
cost_usd: <float>          # Required. Monetary cost (0.0 for free-tier/local).

# Provenance
git_sha: <string>          # Required. Full SHA of HEAD at eval dispatch time.

# Verdict
verdict:
  acceptance_criteria_met: <bool>    # Required. True only if ALL metric-threshold
                                     # AC items in SYSTEMS_PLAN.md were PASS.
  tolerance_band_applied: <bool>     # Required. True if any AC declared ± tolerance.
  notes: <string>                    # Optional. Free-form evaluation summary.
---
```

---

## Field Constraints

### run_store_descriptor fields

| Field | Required | Type | Notes |
|---|---|---|---|
| `run_id` | Yes | string | Unique per run; UUID or content-addressed slug |
| `project_name` | Yes | string | Used to derive `$HOME/.<project-name>/` default |
| `store_uri` | Yes | URI string | Assigned after backend resolution; the only varying field |
| `artifact_paths` | Yes | list of strings | Logical paths written by the eval loop |

**NO `backend:` field in the descriptor.** Backend is a project-level config concern
recorded in `project_profile.yaml` (`run_store_backend` + `run_store_root`), not carried
per-descriptor.

### EVAL_RESULTS.md frontmatter fields

| Field | Required | Type | Notes |
|---|---|---|---|
| `schema_version` | Yes | string | `"1.0"` for v1; quoted to avoid YAML float coercion |
| `run_id` | Yes | string | Must match the tier-1 descriptor `run_id` |
| `store_uri` | Yes | URI string | Cross-reference to tier-1; the only backend-varying value |
| `task` | Yes | string | Benchmark / task identifier (e.g., `"swebench_verified"`) |
| `generation` | Yes | int | Loop iteration number; starts at 1 |
| `primary_metric` | Yes | float | Accuracy, F1, pass@k — depends on task |
| `held_out_delta` | Yes | float | Held-out score minus public score; negative = contamination signal |
| `model_id` | Yes | string | Model identifier used for the run |
| `prompt_hash` | Yes | string | SHA of the prompt template; hashing convention: `versioning.md` (see note below) |
| `dataset_sha` | Yes | string | SHA256 of the dataset MANIFEST (P3 binding; see note below) |
| `token_usage.input` | Yes | int | Input tokens consumed |
| `token_usage.output` | Yes | int | Output tokens consumed |
| `token_usage.total` | Yes | int | `input + output` |
| `cost_usd` | Yes | float | `0.0` for free-tier; actual cost otherwise |
| `git_sha` | Yes | string | Full 40-char SHA; short SHAs not accepted |
| `verdict.acceptance_criteria_met` | Yes | bool | True iff all metric-threshold ACs are PASS |
| `verdict.tolerance_band_applied` | Yes | bool | True if any AC declared `± <value>` |
| `verdict.notes` | No | string | One paragraph; omit if empty |

**`prompt_hash` field note:**
SHA of the prompt template file (or canonicalized prompt string) at eval dispatch time.
The authoritative hashing convention — how to compute the hash, what constitutes a
load-bearing prompt change, and when to write a `category: behavioral` ADR — is defined
in `skills/llm-prompt-engineering/references/versioning.md`
§ "Managed Prompt Versioning for Agentic/Eval Projects". That section points back here
as the binding target, completing the bidirectional cross-reference.

**`dataset_sha` field note (P3 binding):**
This field binds to the P3 data-governance wave. Populate with the SHA256 of the dataset
MANIFEST file. The P3 wave will populate `rules/eval/eval-data-governance.md` with the
provenance validation rule.

---

## Markdown Body

Below the YAML frontmatter, the `EVAL_RESULTS.md` body provides human-readable narrative.
The eval loop generates this body automatically; it may be edited by the user.

```markdown
# Eval Results — <task>-gen<generation>

## Summary

[One paragraph: task, model, prompt template highlights, overall outcome. State the
primary_metric score and whether acceptance criteria were met.]

## Metrics

[Table or prose describing the metric results. If primary_metric improved over the
prior generation or baseline, state by how much. Include held_out_delta interpretation.]

## Comparison

[Comparison vs. baseline or prior generation. State the baseline source (run_id or
threshold from SYSTEMS_PLAN.md). Highlight delta on primary_metric.]

## Notes

[Free-form analysis: what worked, what to try next, anomalies observed during
evaluation (scoring errors, API timeouts, unexpected task failures).]
```

---

## Dual Lifecycle

### EVAL_RESULTS.md

**Ephemeral (always written during the pipeline run):**
- Location: `.ai-work/<task-slug>/EVAL_RESULTS.md`
- Written by: the eval loop at run completion
- Read by: `verifier` during the current pipeline (metric-threshold evaluation)
- Deleted: with `.ai-work/<task-slug>/` at pipeline cleanup

**Archival copy (opt-in, "kept" runs only):**
- Location: `EVAL_RESULTS.md` at project root (sibling to `TRAINING_RESULTS.md`)
- Written by: the eval loop upon user confirmation ("Keep this run?")
- Triggered by: `primary_metric` improvement over the prior kept run, or explicit user
  marking
- Retained: indefinitely; committed to git; the project-level curated summary
- Naming: single file at project root (not timestamped — the current kept run overwrites)

**Signaling the archival decision:**
- The presence of `EVAL_RESULTS.md` at project root IS the signal that a run was kept
- `run_id` in the frontmatter identifies which tier-1 run it summarizes

### EVAL_LOG.md aggregate

**Append-only table at `.ai-state/eval_ledger/EVAL_LOG.md`:**
- One row appended per kept run (same event that writes/overwrites project-root `EVAL_RESULTS.md`)
- Never overwritten — only appended; the log is the full history
- Columns: see [EVAL_LOG.md column set](#eval_logmd-column-set) below

---

## EVAL_LOG.md Column Set

The aggregate log is an append-only Markdown table following the `METRICS_LOG.md` convention.
Eleven columns, one row per kept run:

```markdown
| run_id | task | generation | primary_metric | held_out_delta | model_id | prompt_hash | dataset_sha | cost_usd | git_sha | store_uri |
|---|---|---|---|---|---|---|---|---|---|---|
```

**Column descriptions:**

| Column | Type | Notes |
|---|---|---|
| `run_id` | string | Cross-reference to tier-1 descriptor and `EVAL_RESULTS.md` |
| `task` | string | Benchmark / task identifier |
| `generation` | int | Loop iteration number |
| `primary_metric` | float | Scored result for this run |
| `held_out_delta` | float | Contamination signal |
| `model_id` | string | Model used |
| `prompt_hash` | string | Short (8-char) prefix of the full hash for readability |
| `dataset_sha` | string | Short (8-char) prefix of the MANIFEST SHA256 |
| `cost_usd` | float | Monetary cost |
| `git_sha` | string | Short (7-char) prefix of HEAD commit SHA |
| `store_uri` | string | Full URI to tier-1 store location |

---

## Verifier Consumption

The `verifier` agent reads `EVAL_RESULTS.md` when two conditions are met:
1. `SYSTEMS_PLAN.md` acceptance criteria contain metric threshold syntax
   (e.g., `accuracy > 0.62`, `primary_metric > 0.55 ± 0.01`)
2. `EVAL_RESULTS.md` exists (either at project root or in `.ai-work/<task-slug>/`)

### Reuse of eval-driven-verification.md

**No new verifier code is required.** The verifier reuses the existing tolerance-band
mechanism in `rules/ml/eval-driven-verification.md` — the eval `primary_metric` substitutes
for `val_bpb` in the evaluation logic:

- `val_bpb < 1.75` → `primary_metric > 0.62` (direction flips; logic is identical)
- `val_bpb < 1.75 ± 0.02` → `primary_metric > 0.62 ± 0.01`

**Verifier evaluation steps:**
1. Load this schema reference to understand field layout
2. Read `primary_metric` and `held_out_delta` from the YAML frontmatter
3. For each metric-threshold AC item:
   - Parse syntax: `<metric> <op> <value>` or `<metric> <op> <value> ± <tolerance>`
   - Compare `primary_metric` (or named metric) against the threshold
   - Classify: PASS / FAIL / WARN (per tolerance rules in `rules/ml/eval-driven-verification.md`)
4. Set `verdict.acceptance_criteria_met` to `true` iff all AC items are PASS
5. Emit findings in `VERIFICATION_REPORT.md`:
   ```
   [PASS] AC-3: primary_metric=0.64 vs threshold=0.62 (no tolerance band)
   [WARN] AC-4: primary_metric=0.61 vs threshold=0.62 ± 0.01 (within tolerance)
   [FAIL] AC-5: primary_metric=0.48 vs threshold=0.55 (outside tolerance)
   ```

**When `EVAL_RESULTS.md` is absent:**
```
[WARN] EVAL_RESULTS.md not found — metric threshold criteria not evaluated.
Run the eval loop and re-invoke verifier, or confirm evaluation was not expected
for this step.
```

See `rules/ml/eval-driven-verification.md` for the canonical tolerance-band protocol.

---

## Run-Store Backend Abstraction

The `run_store_descriptor` is **backend-invariant**: only `store_uri` varies across backends.
This section documents the four supported backends, their `store_uri` derivation rules, the
five standard operations, and the `local-home` reference-implementation proof that verifies the
abstraction is correctly designed — mirroring the `neo-cloud-abstraction`
`pricing_query()→0.0` canonical pattern.

### Backend Table

| Backend | Resolved `store_uri` | Use |
|---|---|---|
| `local-home` | `$HOME/.<project-name>/runs/<run_id>/` | zero-config default; no credentials required |
| `local-custom` | `<run_store_root>/runs/<run_id>/` | custom local mount or network filesystem |
| `s3` | `s3://<bucket>/<prefix>/runs/<run_id>/` | remote object store (AWS S3 or compatible) |
| `tracker` | MLflow / W&B run URI | reuse external tracker; delegates to `experiment-tracking` |

`run_store_root` and `run_store_backend` are recorded in `project_profile.yaml` — never in the
descriptor. The descriptor carries only the resolved `store_uri`.

### Backend Operations

Five operations define the backend contract. Every backend implements all five:

| Operation | Signature | Description |
|---|---|---|
| `resolve_uri` | `resolve_uri(descriptor) → store_uri` | Derive the full `store_uri` from `run_id` + `project_name` + backend config |
| `put` | `put(run_id, path, bytes) → None` | Write artifact bytes to `store_uri/<path>` |
| `get` | `get(run_id, path) → bytes` | Read artifact bytes from `store_uri/<path>` |
| `list` | `list(run_id) → paths` | List all artifact paths present under `store_uri` |
| `prune` | `prune(policy) → count` | Delete runs matching the retention policy; return count removed |

### `local-home` Reference-Implementation Proof

The `local-home` backend is the **reference implementation** that proves the abstraction
is correctly designed. It mirrors the `neo-cloud-abstraction` `pricing_query()→0.0`
canonical proof pattern:

- `resolve_uri` for `local-home` returns a plain filesystem path:
  `$HOME/.<project-name>/runs/<run_id>/`
- No network call. No credentials. No environment variables beyond `$HOME`.
- `put`, `get`, `list`, and `prune` operate on the local filesystem — stdlib I/O only.

**Why this proves the abstraction:** if the abstraction were leaking, then `resolve_uri`
would need a backend-conditional branch (e.g., `if backend == "s3": return s3_url(...)`),
or the descriptor itself would need a `backend:` field so callers could branch on it. The
`local-home` path through all five operations using only `store_uri` — without any
`if backend == ...` check — is the proof that no backend-conditional logic reaches downstream.

A test that verifies `local-home` URI derivation without any import of network or
credentials libraries is the zero-credential testability proof for the full abstraction.

### Invariance Self-Test

> Trace the descriptor through all four backends. Does any field besides `store_uri`
> require `if backend == s3` logic downstream? If yes, the schema is wrong.

This self-test (verbatim from the ADR) is the AC-4 acceptance criterion. Apply it whenever
extending the descriptor schema or adding a new backend. If the answer is "yes," the
addition belongs in backend-specific config (`project_profile.yaml`), not the descriptor.

### Security Note

Credentials (`s3` bucket credentials, tracker API keys) travel **outside** the descriptor —
never inside it. Same rule as `neo-cloud-abstraction`. The `env_vars` field (if present in
project config) carries metadata, not secrets. Secrets are injected via environment variables
or a secrets manager at backend-initialization time, before the descriptor is constructed.

### `tracker` Backend Delegation

The `tracker` backend delegates run-URI construction and artifact management to
`skills/experiment-tracking/SKILL.md` (MLflow / W&B). No new library is introduced at the
Praxion convention layer — the `tracker` backend is an adapter that translates the five
operations above into the experiment-tracking skill's native calls. `resolve_uri` for
`tracker` returns the MLflow or W&B run URI as the `store_uri`.

---

## Schema Versioning

`schema_version` is a quoted string (`"1.0"`) to prevent YAML from parsing it as a float.

| Version | Change |
|---|---|
| `"1.0"` | Initial schema (this document; Wave 0) |

**Versioning rules:**
- Additive fields (new optional fields): increment minor (`"1.0"` → `"1.1"`)
- Breaking changes (rename, type change, remove required field): increment major (`"1.0"` → `"2.0"`)
- Verifier checks `schema_version` and emits WARN if the version is newer than expected

---

## Minimal Valid Example

### EVAL_RESULTS.md — fully populated example

The following example shows a kept run from a SWE-bench Verified task, generation 3.
`run_id` cross-references are consistent with the `EVAL_LOG.md` row below.

```yaml
---
schema_version: "1.0"
run_id: "eval-swebench-g3-a4b2c1"
store_uri: "~/.myproject/runs/eval-swebench-g3-a4b2c1/"
task: "swebench_verified"
generation: 3
primary_metric: 0.641
held_out_delta: -0.012
model_id: "claude-sonnet-4-5"
prompt_hash: "f3a9d2b7c1e84f6a2d0b9c3e7f1a4d8b"
dataset_sha: "9e3c2a1b4d7f0e5c8a2b6d9f3e1c4a7b"
token_usage:
  input: 1480523
  output: 312847
  total: 1793370
cost_usd: 7.23
git_sha: "a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0"
verdict:
  acceptance_criteria_met: true
  tolerance_band_applied: false
  notes: "primary_metric 0.641 beats threshold 0.62. held_out_delta -0.012 within acceptable range."
---

# Eval Results — swebench_verified-gen3

## Summary

Generation 3 run on SWE-bench Verified with claude-sonnet-4-5. primary_metric improved
from 0.598 (gen2) to 0.641, beating the 0.62 threshold. Token usage 1.79M, cost $7.23.

## Metrics

| Metric | Value | Threshold | Result |
|---|---|---|---|
| primary_metric | 0.641 | > 0.62 | PASS |
| held_out_delta | -0.012 | — | (informational; negative = no contamination) |

## Notes

Prompt refinement in gen3 improved patch applicability. Next: investigate 12 remaining
failure cases for systematic patterns.
```

### Minimal EVAL_LOG.md Row

The following shows a populated `EVAL_LOG.md` table consistent with the example above:

```markdown
| run_id | task | generation | primary_metric | held_out_delta | model_id | prompt_hash | dataset_sha | cost_usd | git_sha | store_uri |
|---|---|---|---|---|---|---|---|---|---|---|
| eval-swebench-g3-a4b2c1 | swebench_verified | 3 | 0.641 | -0.012 | claude-sonnet-4-5 | f3a9d2b7 | 9e3c2a1b | 7.23 | a1b2c3d | ~/.myproject/runs/eval-swebench-g3-a4b2c1/ |
```

Both cross-references (`run_id = eval-swebench-g3-a4b2c1`, `store_uri`) are consistent
with the `EVAL_RESULTS.md` frontmatter above.
