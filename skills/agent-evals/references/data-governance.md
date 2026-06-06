# Eval Data Governance

How to design contamination-safe, provenance-tracked evaluations. Reference material for
[Agent Evals](../SKILL.md). For the enforced constraints, see
`rules/eval/eval-data-governance.md`.

---

## Why Governance Matters

Eval data governance addresses a structural risk in empirical AI evaluation: a model that
has seen the benchmark answers during training or fine-tuning will produce inflated scores
that do not reflect real capability. This is **benchmark contamination**. Because agent
frameworks often operate on codebases that also contain training data, the contamination
path is shorter than it looks — a `data/` directory committed to a repo that is later
used as training material poisons any future evaluation on those tasks.

A second risk is **leaderboard gaming**: without provenance tracking, it is impossible to
tell whether a high-scoring run used the held-out split, an unseen variant, or a cheated
split. The `held_out_delta` field in
[`run-ledger-schema.md`](run-ledger-schema.md) is the quantitative signal for this: a
negative delta (held-out score lower than the public score) is evidence that the held-out
split is genuinely harder and the model has not seen it. A delta near zero — or positive —
warrants investigation.

Good governance makes contamination detectable, makes provenance auditable, and makes
eval results defensible to future consumers of the data.

---

## Held-Out Split Design

Structure eval data into two tiers:

| Directory | Contents | Committed? | Purpose |
|---|---|---|---|
| `data/public/` | Samples used for development and debugging | Yes | Sanity checks, prompt tuning |
| `data/private/` | The held-out scored split | Yes (directory), but contents are not shipped | CI scoring, leaderboard updates |

The `data/private/` directory IS expected to exist in a project repo. The governance check
flags ground truth that escapes outside of `data/private/`, not the directory itself.

### The `split` field in `MANIFEST.json`

Every scored data directory must declare its split type in a `MANIFEST.json` sibling:

```json
{
  "sha256": "9e3c2a1b4d7f0e5c8a2b6d9f3e1c4a7b...",
  "version": "2026-06-01",
  "source": "https://example.com/benchmark-v1",
  "split": "held_out"
}
```

Valid `split` values: `held_out` | `public` | `mixed`.

A **negative** `held_out_delta` in `EVAL_RESULTS.md` is the expected outcome: it means the
model scored lower on the private split than on the public development set, which is the
contamination-free baseline behavior. A positive or near-zero delta is a red flag that the
model may have been exposed to the held-out data.

---

## MANIFEST.json Schema

Every `tasks/**` or `data/private/**` directory containing scored examples must carry a
`MANIFEST.json` sibling. This is the dataset provenance anchor.

### Required Fields

| Field | Type | Description |
|---|---|---|
| `sha256` | string | SHA-256 of the dataset archive or the canonical file set |
| `version` | string | Semver (`1.0.0`) or date string (`2026-06-01`) |
| `source` | string | URL, citation, or internal identifier |
| `split` | string | `held_out` \| `public` \| `mixed` |

Optional but recommended:

| Field | Type | Description |
|---|---|---|
| `deterministic` | bool | Whether the eval produces deterministic scores (default `true`) |
| `n_examples` | int | Number of scored examples in this split |
| `created_at` | string | ISO 8601 creation date |

### Binding to `EVAL_RESULTS.md`

The `dataset_sha` field in `EVAL_RESULTS.md` frontmatter (see
[run-ledger-schema.md §Field Constraints](run-ledger-schema.md)) holds the SHA-256 that
matches `MANIFEST.json sha256`. This creates a verifiable chain:

```
EVAL_RESULTS.md  dataset_sha  ──→  MANIFEST.json  sha256
                                    └─ version
                                    └─ source
                                    └─ split
```

If `dataset_sha` in a result does not match the `sha256` in the corresponding `MANIFEST.json`,
either the dataset was changed after scoring or the wrong manifest was referenced. The governance
sentinel check (see `rules/eval/eval-data-governance.md §Sentinel Checks`) emits a WARN for
this mismatch.

### Example

```json
{
  "sha256": "9e3c2a1b4d7f0e5c8a2b6d9f3e1c4a7b2e8d5f1a3c6b9e2f4a7d0c3b6e9f2a5c",
  "version": "1.0.0",
  "source": "https://example.com/coding-benchmark-v1",
  "split": "held_out",
  "deterministic": true,
  "n_examples": 200,
  "created_at": "2026-06-01"
}
```

---

## Answer-Key Isolation

Ground truth — expected outputs, reference solutions, answer keys — must not appear in any
file outside `data/private/`. The reason is the contamination path described above: if answer
keys are committed in a shared or public location, they can enter training corpora.

### What constitutes ground truth

Any file containing these keys in a JSON/YAML/JSONL structure, outside `data/private/`:

- `answer`, `solution`, `expected_output`, `ground_truth`
- `correct_answer`, `gold_answer`, `reference_output`
- Files named `answers.json`, `solutions.json`, `ground_truth.jsonl`

### What does not constitute ground truth

- Test fixture files under `tests/` with expected values — these are test code, not benchmark data
- Unit test assertions — these are deterministic code checks, not scored eval data
- Example outputs in skill or command documentation

The activation gate for this check is the presence of `evaluate.py` + `data/private/` +
`tasks/` in the same project. A project without this layout is not subject to eval-data
governance (the `rules/eval/eval-data-governance.md` `paths:` frontmatter encodes this).

For the full detection patterns and false-positive handling, see
[`skills/context-security-review/references/benchmark-leakage.md`](../../context-security-review/references/benchmark-leakage.md).

---

## Eval Determinism Practices

Stochastic sampling must be seeded or disabled during CI scoring. The goal is reproducible
scores across runs so that threshold gates are meaningful.

### Practices

1. **Seed all random sources.** Set `random.seed(42)`, `numpy.random.seed(42)`, and the
   model sampling seed (`temperature=0` or equivalent) for CI scoring runs. Use a different
   seed for exploratory runs to avoid over-fitting to a single seed's noise.

2. **Declare non-determinism explicitly.** If an eval cannot be made deterministic (e.g., it
   tests an inherently stochastic agent behavior), set `deterministic: false` in `MANIFEST.json`.
   The CI smoke-test (see
   [`references/cicd-integration.md`](cicd-integration.md)) skips threshold gates for
   non-deterministic evals and emits WARN instead of FAIL.

3. **Run multiple trials for non-deterministic evals.** The `agent-evals` skill's guidance on
   `pass@k` vs `pass^k` applies here — see the parent skill for statistical aggregation
   patterns.

4. **Version the prompt.** The `prompt_hash` field in `EVAL_RESULTS.md` binds each result to
   the exact prompt template used. This enables detecting score changes caused by prompt drift
   versus model updates.

### CI vs exploratory runs

| Context | Seeding | Threshold gates | MANIFEST deterministic |
|---|---|---|---|
| CI scoring | Always seeded | Active | `true` |
| Exploratory / human | Optional | Not active | Either |
| Non-deterministic eval | N/A | Skipped (WARN emitted) | `false` |

---

## Cross-References

- **Enforcement rule** (prescriptive, path-scoped): `rules/eval/eval-data-governance.md`
- **Schema** (run_store_descriptor, EVAL_RESULTS fields, EVAL_LOG columns):
  [`references/run-ledger-schema.md`](run-ledger-schema.md)
- **Contamination detection patterns** (sentinel check design, false-positive handling):
  [`skills/context-security-review/references/benchmark-leakage.md`](../../context-security-review/references/benchmark-leakage.md)
- **CI smoke-test integration** (fixture isolation, non-deterministic skip):
  [`references/cicd-integration.md`](cicd-integration.md)
