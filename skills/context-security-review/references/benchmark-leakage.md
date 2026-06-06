# Benchmark-Leakage Detection Patterns

Detection patterns for answer-key-in-package / ground-truth-leakage in eval and benchmark projects. Reference material for [Context Security Review](../SKILL.md).

## Scope

This reference covers how to detect committed files that embed evaluation ground truth, expected outputs, or benchmark answer keys **outside** the designated private data directory (`data/private/`). The key threat model: an answer key that ships in a published package, committed public split, or `tasks/` example directory invalidates held-out evaluation validity for all future runs and can contaminate any model that trains on repo contents.

Ground truth living **inside** `data/private/` is expected and correct. The checks here flag ground truth found **outside** that boundary.

### Activation Gate

These checks apply only when the project matches the eval-data-governance layout:

- `evaluate.py` exists (eval scoring entry point)
- `data/private/` exists (held-out split)
- `tasks/` exists (task definition directory)

Outside this layout the checks produce no findings. The path-scoped rule `rules/eval/eval-data-governance.md` is the activation gate — its `paths:` frontmatter triggers only for projects that touch these paths.

---

## Detection Patterns

### Pattern 1 — Ground-Truth Key in JSON / YAML / JSONL (outside `data/private/`)

Grep target: any `.json`, `.jsonl`, or `.yaml` / `.yml` file outside `data/private/`.

```
# JSON / JSONL — key at any nesting level
"answer"\s*:
"solution"\s*:
"ground_truth"\s*:
"expected_output"\s*:
"correct_answer"\s*:
"gold_answer"\s*:
"reference_output"\s*:

# YAML — key at any indentation level
^[ \t]*answer\s*:
^[ \t]*solution\s*:
^[ \t]*ground_truth\s*:
^[ \t]*expected_output\s*:
^[ \t]*correct_answer\s*:
^[ \t]*gold_answer\s*:
^[ \t]*reference_output\s*:
```

**Shell one-liner** (run from project root):

```bash
grep -rn \
  -e '"answer"\s*:' \
  -e '"solution"\s*:' \
  -e '"ground_truth"\s*:' \
  -e '"expected_output"\s*:' \
  -e '"correct_answer"\s*:' \
  -e '"gold_answer"\s*:' \
  -e '"reference_output"\s*:' \
  --include="*.json" --include="*.jsonl" \
  --include="*.yaml" --include="*.yml" \
  --exclude-dir="data/private" \
  .
```

A match is a FAIL finding unless the false-positive exclusions below apply.

### Pattern 2 — Answer-Key Filename in `data/` outside `private/`

Files with these names (or names containing these substrings) in any `data/` subdirectory **except** `data/private/`:

| Filename pattern | Risk |
|-----------------|------|
| `answers.json` | Answer key |
| `answers.jsonl` | Answer key |
| `solutions.json` | Answer key |
| `ground_truth.jsonl` | Ground truth |
| `ground_truth.json` | Ground truth |
| `expected_outputs.json` | Expected outputs |
| `labels.json` | Classification labels |
| `labels.jsonl` | Classification labels |
| `*_answers.*` | Filename contains "answers" |
| `*_solutions.*` | Filename contains "solutions" |
| `*_gt.*` | Filename contains "gt" (ground truth) |

**Shell one-liner**:

```bash
find data/ -not -path "data/private/*" \
  \( -name "answers.*" -o -name "solutions.*" \
     -o -name "ground_truth.*" -o -name "expected_outputs.*" \
     -o -name "labels.*" -o -name "*_answers.*" \
     -o -name "*_solutions.*" -o -name "*_gt.*" \) \
  -print
```

A match is a FAIL finding unless the false-positive exclusions below apply.

### Pattern 3 — Ground-Truth Literal Keys in `tasks/**`

Any file in `tasks/` (the task-definition directory used by eval harnesses) that contains the literal strings below as JSON/YAML keys:

```
"correct_answer"
"gold_answer"
"reference_output"
```

These are the most specific signal: they are unlikely to appear in task *input* definitions and almost always indicate a shipped answer key.

**Shell one-liner**:

```bash
grep -rn \
  -e '"correct_answer"\s*:' \
  -e '"gold_answer"\s*:' \
  -e '"reference_output"\s*:' \
  --include="*.json" --include="*.jsonl" \
  --include="*.yaml" --include="*.yml" \
  tasks/
```

A match is a FAIL finding.

---

## Distinguishing Legitimate `data/private/` from Leaked Ground Truth

| Path | Ground-truth keys? | Assessment |
|------|-------------------|------------|
| `data/private/**` | Yes | **Expected** — held-out split. No finding. |
| `data/private/**` | No | Normal — public-facing metadata only. |
| `data/public/**` | Yes | **FAIL** — leaked into public split. |
| `data/**` (not under `private/`) | Yes | **FAIL** — leaked. |
| `tasks/**` | Yes (Pattern 1 keys) | **FAIL** — task definitions must not embed answers. |
| `tasks/**` | Yes (Pattern 3 keys only) | **FAIL** — strongest signal. |
| `tasks/**` | No | Normal — input definitions only. |
| Package wheel `.whl` / sdist `.tar.gz` | Any ground-truth content | **FAIL** — shipped artifact isolation violated. |

**Wheel / sdist check**: if the project builds a Python package, verify that `data/private/` is excluded from `package_data` / `MANIFEST.in`. A common misconfiguration includes `data/` recursively and ships the private split in the distribution artifact.

```bash
# Verify private data is excluded from the wheel
unzip -l dist/*.whl 2>/dev/null | grep "data/private" && echo "LEAK" || echo "OK"
tar -tzf dist/*.tar.gz 2>/dev/null | grep "data/private" && echo "LEAK" || echo "OK"
```

---

## False-Positive Handling

The following contexts produce Pattern 1 / Pattern 2 matches that are **not** governance violations:

| Context | Why it is not a violation | How to confirm |
|---------|--------------------------|---------------|
| Unit test fixtures in `tests/` | Test expected values are not evaluation answer keys | File path starts with `tests/` |
| Schema documentation examples | Illustrative JSON in `*.md` files | File is markdown (`.md`) — grep targets are JSON/YAML files |
| Metric calculation helpers | Files that compute metrics may reference field names as strings | File is `.py` (Python source), not data |
| `conftest.py` / pytest fixtures | Test infrastructure | File path contains `conftest.py` or is in `tests/` |
| Mock eval datasets for CI | Synthetic data used only in CI smoke tests | File is under `tests/` or `ci/` |

**Rule of thumb**: the check is concerned with *data files* (`.json`, `.jsonl`, `.yaml`, `.yml`, `.csv`), not source code or documentation. When Pattern 1 fires on a `.py` or `.md` file, treat it as WARN (field-name string in code/docs) rather than FAIL (ground truth in a data artifact).

The activation gate (eval-data-governance layout) already narrows the check to projects with `evaluate.py` + `data/private/` + `tasks/`. Test-only projects without this layout are unaffected.

---

## Sentinel Check Design

> Wiring to `agents/sentinel.md` is scheduled for a later implementation step.

The checks below are designed to feed into the sentinel's path-scoped activation model. They fire only when the eval-data-governance `paths:` gate is active.

### Check BL-01 — Ground-Truth-in-Shipped-Artifact

**Trigger**: any file outside `data/private/` is touched that matches `tasks/**`, `data/**`, or a release artifact pattern.

**Detection logic**:
1. Collect all modified `.json`, `.jsonl`, `.yaml`, `.yml` files not under `data/private/`.
2. Run Pattern 1 and Pattern 3 grep against each file.
3. Run Pattern 2 filename check against any file in `data/` not under `data/private/`.
4. For release builds: run the wheel/sdist leak check.

**Finding format**:
```
[BL-01] FAIL — Answer key found outside data/private/
File: <path>
Key: "<key_name>" at line <N>
Risk: Benchmark contamination — held-out answers committed to public artifact.
Remediation: Move the file to data/private/ or strip the answer field before committing.
```

**Non-violation note**: the *presence* of `data/private/` is expected and correct. BL-01 flags ground truth found **outside** `data/private/`, not its presence inside.

### Check BL-02 — Missing MANIFEST.json

**Trigger**: any `tasks/**` or `data/private/**` directory is touched.

**Detection logic**:
1. For each directory under `tasks/` or `data/private/` that contains `.json`, `.jsonl`, `.yaml`, or `.csv` files, check for a `MANIFEST.json` sibling.
2. If present, validate it has the four required fields: `sha256`, `version`, `source`, `split`.

**Finding format (missing)**:
```
[BL-02] WARN — Task/data directory missing MANIFEST.json
Directory: <path>
Risk: Dataset provenance unverifiable; SHA integrity cannot be confirmed.
Remediation: Add MANIFEST.json with sha256, version, source, and split fields.
```

**Finding format (invalid)**:
```
[BL-02] WARN — MANIFEST.json missing required fields
File: <path>/MANIFEST.json
Missing fields: <list>
Risk: Partial provenance record; integrity checks cannot run.
```

Severity is WARN, not FAIL. A MANIFEST may legitimately be absent during initial dataset setup. The check prompts rather than blocks.

### Check BL-03 — dataset_sha / MANIFEST.json sha256 Agreement

**Trigger**: `EVAL_RESULTS.md` or any `**/MANIFEST.json` is touched.

**Detection logic**:
1. When both `EVAL_RESULTS.md` and a `MANIFEST.json` are present in the same task scope, read `dataset_sha` from `EVAL_RESULTS.md` frontmatter.
2. Read `sha256` from `MANIFEST.json`.
3. Require a full or prefix match (prefix match allows recording a short hash; full match is preferred).

**Finding format (mismatch)**:
```
[BL-03] FAIL — dataset_sha mismatch
EVAL_RESULTS.md dataset_sha: <recorded>
MANIFEST.json sha256:        <actual>
Risk: Run was scored against a different dataset version than the one recorded.
Remediation: Re-run eval against the dataset matching MANIFEST.json, or update MANIFEST.json if the dataset was intentionally updated.
```

**Finding format (absent)**:
No finding. An absent `EVAL_RESULTS.md` or `MANIFEST.json` is an expected incomplete state during authoring — do not emit a finding for absence alone.

---

## Remediation Guidance

| Finding | Immediate action | Long-term action |
|---------|----------------|-----------------|
| Answer key in `data/public/` | Move to `data/private/` and force-push (before upstream indexing) | Add `data/private/` to `.gitignore` if not already there |
| Answer key in `tasks/` | Strip the answer field from task definition files; store answers only in `data/private/` | Review task-authoring workflow to prevent recurrence |
| Answer key in wheel / sdist | Exclude `data/private/` from `package_data` and `MANIFEST.in`; rebuild and re-publish | Add CI check to verify wheel contents before release |
| Missing MANIFEST.json | Create `MANIFEST.json` with all four required fields | Add MANIFEST generation to the dataset preparation pipeline |
| dataset_sha mismatch | Re-run eval or update MANIFEST.json; never patch the hash by hand | Automate MANIFEST.json generation at dataset freeze time |

### Git History Scrubbing

If ground-truth data was committed and pushed, the data is in git history even after removal. Additional steps may be required:

1. Use `git filter-repo` (preferred) or `BFG Repo Cleaner` to scrub the file from history.
2. Force-push to all remotes.
3. Notify downstream consumers (clones, forks, CI caches) to re-clone.
4. Consider whether the leaked data invalidates existing benchmark results.

History scrubbing is disruptive. Prevention (CI gate) is strongly preferred.
