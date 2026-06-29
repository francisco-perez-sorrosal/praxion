---
title: Wave 4–5 External Audit (Adversarial)
type: independent-analysis
date: 2026-06-29
auditor: Independent external auditor (Cursor agent)
head_sha_audited: da4d1c387eeeb1c620cc225a4ef75906cc3727e1
scope: Waves 4a/4b/4c, Wave 5, EA-11 closure, R12b closure, and residual fixes since 2026-06-27
verification_legend:
  CONFIRMED: claim re-proven against code + execution
  OVERCLAIMED: claim materially exceeds what code/evidence supports
  REFUTED: plausible defect disproven by execution evidence
  BY-DESIGN: limitation is real and honestly documented as deliberate
  UNVERIFIABLE: could not reproduce due missing runtime substrate
---

## 0. Executive Summary

Overall verdict: **PASS WITH FINDINGS**.

- **Findings by severity:** 0 BLOCKING, 1 IMPORTANT, 1 SUGGESTED, 1 BY-DESIGN, 4 REFUTED
- **Most important issue:** Wave 4/5 docs claim the registry spine fields are still "populated, not projected", but `dec-259` made `cleanup_policy` load-bearing in `clean_work_safety`; the architecture/design docs now understate shipped behavior.
- High-risk claims (EA-11 one-way-door safety, R12b volatile split + finalize gate, R10 chain liveness) were re-run with direct evidence and mutation-style bite checks.

---

## Findings

### EA4-01 — IMPORTANT — Registry-consumer docs are stale after dec-259 (OVERCLAIMED)

**Claim audited (quoted):**

- Wave 4/5 closure claims say the 4->3 coherence sweep was applied across `DESIGN.md` and `docs/architecture.md`.

**Evidence (commands + outputs):**

- `rg "populated, not projected|_GATE_KINDS|sentinel, script" .ai-state/DESIGN.md docs/architecture.md`
- Result shows:
  - `.ai-state/DESIGN.md` still states `_GATE_KINDS = {sentinel, script, hook, producer, none, deferred}` and "fields are populated, not projected".
  - `docs/architecture.md` still states `production_gate`/`cleanup_policy` are "populated, not projected".
- `ReadFile scripts/clean_work_safety.py` shows `from artifact_registry import cleanup_policy_for` and `_severity_for()` mapping from registry policy to classification severity.
- `python3 -m pytest -q -o addopts='' scripts/test_clean_work_safety.py::test_wip_severity_changes_when_policy_overridden`
  - `1 passed` (policy override flips verdict), proving the read is load-bearing.

**Verdict:** **OVERCLAIMED**.

Docs remain semantically stale at a load-bearing seam. The code and tests prove registry consumption is active; the design docs still describe the pre-dec-259 world.

**Remediation:**

- Update `DESIGN.md` and `docs/architecture.md` registry rows to:
  - remove `sentinel` from production gate kind set;
  - state that `cleanup_policy` is now projected by `clean_work_safety`.

---

### EA4-02 — REFUTED — EA-11 behavior-preservation regression concern

**Claim audited (quoted):**

- "`clean_work_safety` reader is behavior-preserving; dry-run diff over 22 live dirs is empty."

**Evidence (commands + outputs):**

- Old-vs-new replay over live repo state:
  - `git show a008547^:scripts/clean_work_safety.py > /tmp/.../old_clean_work_safety.py`
  - Run old and new with `--repo-root /Users/fperez/dev/praxion --json`, compare payloads.
- Output:
  - `old_exit=1 new_exit=1`
  - `old_summary={'total': 22, 'block': 4, 'warn': 11, 'safe': 7, 'stale_safe': 0}`
  - `new_summary={'total': 22, 'block': 4, 'warn': 11, 'safe': 7, 'stale_safe': 0}`
  - `equal_payload=True`

**Verdict:** **CONFIRMED** (therefore regression concern **REFUTED**).

No behavior drift detected on live `.ai-work` shapes.

---

### EA4-03 — REFUTED — EA-11 non-load-bearing reader concern

**Claim audited (quoted):**

- "Registry read is load-bearing; unknown/archive policies floor to WARN; drift gate bites."

**Evidence (commands + outputs):**

- `python3 -m pytest -q -o addopts='' scripts/test_clean_work_safety.py::test_wip_severity_changes_when_policy_overridden scripts/test_clean_work_safety.py::test_detected_blockers_equal_registry_non_delete_artifacts scripts/test_clean_work_safety.py::test_severity_for_unknown_artifact_is_warn`
  - `3 passed`
- `PYTHONPATH=... python3 - <<'PY' ...`
  - `archive_severity warn`
  - `unknown_severity warn`

**Verdict:** **CONFIRMED** (concern **REFUTED**).

The reader is functional, monotonic (never widens deletion), and coupling drift is guarded.

---

### EA4-04 — REFUTED — R12b dropped durable manifest surfaces

**Claim audited (quoted):**

- "Committed manifest has zero `.ai-work` surfaces and no durable surface dropped."

**Evidence (commands + outputs):**

- Pre/post generator comparison using pre-R12b script from `07f8386^`:
  - old generator + old registry run on current checkout
  - current generator run on current checkout
- Output:
  - `old_total 429`
  - `new_total 350`
  - `old_ai_work 79`
  - `new_ai_work 0`
  - `old_durable 350`
  - `new_durable 350`
  - `durable_equal True`
  - `durable_missing_in_new 0`

**Verdict:** **CONFIRMED** (drop concern **REFUTED**).

Volatile surfaces were removed; durable index parity holds.

---

### EA4-05 — REFUTED — R12b `.claude` exclusion residual fix is unproven

**Claim audited (quoted):**

- "Root-under-`.claude` exclusion bug fixed; regression test guards it."

**Evidence (commands + outputs):**

- Replay old (`62daa5c^`) vs current `build_doc_manifest.py` on synthetic root at `.claude/worktrees/proj/docs/guide.md`.
- Output:
  - `old_docs []`
  - `new_docs ['docs/guide.md']`
  - `bug_reproduced True`
- Regression guard exists:
  - `scripts/test_build_doc_manifest.py::test_docs_indexed_when_root_lives_under_an_excluded_dir`

**Verdict:** **CONFIRMED** (unproven-fix concern **REFUTED**).

The one-line path-relativization fix is real and necessary.

---

### EA4-06 — REFUTED — R10 chain eval is hollow/mocked

**Claim audited (quoted):**

- "Criteria→spec chain eval runs real validators in always-green suite and each link bites."

**Evidence (commands + outputs):**

- `python3 -m pytest -q -o addopts='' tests/test_criteria_spec_eval.py`
  - included in 120-test batch: all passed.
- Mutation-style bite checks:
  - monkeypatch `run_p06 -> []` => `link1_failed_as_expected`
  - monkeypatch `detect_drift -> []` => `link2_failed_as_expected`
  - control (no REQ removal) => `link3_control_failed_as_expected`
  - monkeypatch `detect_gap -> {'gap': False}` => `link4_failed_as_expected`
- File inspection confirms direct imports of real modules:
  - `scripts.spec_drift.detect_drift`
  - `check_p06_task_brief`
  - `check_spec_archival_gap`

**Verdict:** **CONFIRMED** (hollow-gate concern **REFUTED**).

The chain test is live, deterministic, and validator-connected.

---

### EA4-07 — BY-DESIGN — P07/P08 remain fixture/prompt semantics, not dedicated CODE scripts

**Claim audited (quoted):**

- Wave-4 carry-forward asks that P07/P08 still bite on golden bad-cases.

**Evidence (commands + outputs):**

- P07 fixture replay:
  - `INTERFACE_DESIGN.md` (bad) => `p07_badcase_flags True`
  - `INTERFACE_DESIGN_no_challenge.md` (control) => `p07_control_flags False`
- P08 fixture replay:
  - `clean_work_safety_stale.json` => `p08_badcase_advisory True value 3`
  - `clean_work_safety_clean.json` => `p08_control_advisory False value 0`
- Sentinel catalog still defines these as fixture/golden checks rather than separate script modules.

**Verdict:** **BY-DESIGN**.

Behavior is reproducible via shipped fixtures and described rules; no contradiction found.

---

### EA4-08 — SUGGESTED — Full-suite green claim was not reproducible in this environment (UNVERIFIABLE)

**Claim audited (quoted):**

- Multiple rows claim full `scripts/` + `tests/` green counts.

**Evidence (commands + outputs):**

- `python3 --version` => `Python 3.9.6`
- `python3 -m pytest -q -o addopts='' scripts/ tests/` fails collection:
  - `ModuleNotFoundError: No module named 'tomllib'` in multiple `scripts/project_metrics` and codex tests.
- `python3.11 --version` and `uv run ...` are unavailable in this environment.
- Targeted Wave 4–5 matrix still executed cleanly:
  - `120 passed in 1.51s` across all high-risk Wave 4–5 test files.

**Verdict:** **UNVERIFIABLE** (environmental).

Not a code refutation, but full-claim reproduction cannot be completed from this runtime substrate.

**Remediation:**

- Record expected runtime prerequisites directly in audit/runbook commands (e.g., Python >=3.11 path) so full-suite claims are reproducible outside canonical maintainer machines.

---

## Disposition Table

| Finding | Severity | Verdict | Recommended action |
| --- | --- | --- | --- |
| EA4-01 | IMPORTANT | OVERCLAIMED | Update `DESIGN.md` + `docs/architecture.md` registry rows to match dec-259 reality |
| EA4-08 | SUGGESTED | UNVERIFIABLE | Document runtime prerequisites for full-suite reproduction |
| EA4-07 | BY-DESIGN | BY-DESIGN | None |
| EA4-02 | REFUTED | CONFIRMED (claim holds) | None |
| EA4-03 | REFUTED | CONFIRMED (claim holds) | None |
| EA4-04 | REFUTED | CONFIRMED (claim holds) | None |
| EA4-05 | REFUTED | CONFIRMED (claim holds) | None |
| EA4-06 | REFUTED | CONFIRMED (claim holds) | None |

---

## What I Could Not Verify

- I could not reproduce the **entire** `scripts/` + `tests/` suite counts in this shell because only Python 3.9 is available (`tomllib` import failures), and no `python3.11`/`uv` runtime is installed here.
- I did not execute `finalize_chain.sh` against a truly separate downstream onboarded project checkout; instead I validated existence-gating and order via `scripts/test_finalize_chain.py` and local shell replay.
