---
paths:
- evaluate.py
- data/private/**
- tasks/**
- "**/MANIFEST.json"
core: false
---

## Eval Data Governance

Path-scoped conventions for benchmark/eval-driven projects. Loaded when eval scoring
code (`evaluate.py`), held-out ground truth (`data/private/`), task definitions
(`tasks/`), or a dataset provenance manifest (`**/MANIFEST.json`) is touched.

Zero always-loaded cost — these conventions apply only inside eval/benchmark projects,
not every session.

### Rules

**1. Held-out vs public split discipline.** When a project has `data/private/` alongside a
public split, the private directory must not appear in any shipped or committed artifact
(package data, release bundle, or committed file outside `data/private/`). Ground truth —
answer keys, expected outputs — lives in `data/private/` only. Any file in `data/` (outside
`data/private/`) that contains JSON/YAML/JSONL keys named `answer`, `solution`,
`ground_truth`, or `expected_output` is a governance violation. The sentinel check below
enforces this; the detection patterns are in
`skills/context-security-review/references/benchmark-leakage.md`.

**2. No ground-truth in a shipped or committed artifact.** A committed file outside
`data/private/` must not contain fields named `answer`, `solution`, `expected_output`, or
`ground_truth` in any JSON, YAML, or JSONL structure. This includes `tasks/` example files,
`data/public/` splits, and any file installed via package data. Rationale: answer-key leakage
contaminates any model that trains on or is fine-tuned with repo contents, and it invalidates
held-out evaluation validity for all future runs. When adding new data files, verify they
contain only inputs and metadata — never labels or reference answers.

**3. Dataset provenance MANIFEST.json requirement.** Every directory under `tasks/**` or
`data/private/**` that contains scored examples must include a `MANIFEST.json` sibling with
these four required fields:

| Field | Type | Description |
|-------|------|-------------|
| `sha256` | string | SHA-256 of the dataset archive or canonical file set |
| `version` | string | Semver (e.g. `1.0.0`) or date string (e.g. `2025-03-01`) |
| `source` | string | URL or bibliographic citation for the dataset |
| `split` | string | One of `held_out`, `public`, or `mixed` |

The verifier reads `dataset_sha` from `EVAL_RESULTS.md` and compares it against
`MANIFEST.json sha256` before scoring. A mismatch is a **FAIL** finding — it means
the run was scored against a different dataset version than the one recorded. The
`dataset_sha` binding is defined in `skills/agent-evals/references/run-ledger-schema.md`.
For the full governance rationale and split-design guidance, see
`skills/agent-evals/references/data-governance.md`.

**4. Eval determinism.** Stochastic sampling must be seeded or disabled during CI scoring
runs (not during human exploratory runs). When results are inherently non-deterministic, set
`deterministic: false` in the task's `MANIFEST.json`. The CI smoke-test (defined in
`skills/agent-evals/references/cicd-integration.md`) will skip threshold gates for
non-deterministic evals and emit WARN rather than FAIL. Never commit a `deterministic: false`
manifest for a task that was previously deterministic without a corresponding version bump.

### Sentinel Checks

These checks fire when any path listed in this rule's `paths:` frontmatter is touched.
Wiring into `agents/sentinel.md` is handled separately (see the P3 wave plan). The contract
for each check is:

**Check 1 — Ground-truth-in-shipped-artifact scan.**
- Trigger: `evaluate.py`, `tasks/**`, or `data/` files touched (excluding `data/private/**`).
- Method: grep for JSON/YAML/JSONL keys `answer`, `solution`, `ground_truth`,
  `expected_output` in committed files outside `data/private/`. See
  `skills/context-security-review/references/benchmark-leakage.md` for the full detection
  patterns.
- Outcome on violation: tech-debt row (FAIL severity) — "Answer key found outside
  `data/private/`; benchmark contamination risk."
- Non-violation note: the *presence* of `data/private/` is expected and correct; the check
  flags ground truth found OUTSIDE `data/private/`, not its presence inside.

**Check 2 — Missing MANIFEST.json detection.**
- Trigger: any `tasks/**` or `data/private/**` directory touched.
- Method: for each task or private-data directory that contains `.json`, `.jsonl`, `.yaml`,
  or `.csv` files, verify a `MANIFEST.json` sibling exists with `sha256`, `version`,
  `source`, and `split` fields.
- Outcome on missing provenance: tech-debt row (WARN severity) — "Task/data directory
  missing `MANIFEST.json`; dataset provenance unverifiable."

**Check 3 — dataset_sha / MANIFEST.json sha256 agreement.**
- Trigger: `EVAL_RESULTS.md` or `**/MANIFEST.json` touched.
- Method: when both `EVAL_RESULTS.md` and a `MANIFEST.json` are present in the same task
  scope, compare `EVAL_RESULTS.md` frontmatter field `dataset_sha` against
  `MANIFEST.json sha256`. A full or prefix match is required.
- Outcome on mismatch: tech-debt row (FAIL severity) — "`dataset_sha` in `EVAL_RESULTS.md`
  does not match `MANIFEST.json sha256`; run provenance is broken."
- Outcome when either file is absent: no finding (incomplete state is expected during
  authoring).
