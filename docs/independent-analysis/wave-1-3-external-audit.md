---
title: Wave 1–3 External Audit (Adversarial)
type: independent-analysis
audience: implementer / maintainer
status: audit report (read-only)
date: 2026-06-27
author: Independent external auditor (Cursor agent)
scope: Waves 1–3 artifact remediation on main; ADRs dec-248 (re-affirmed), dec-249, dec-250, dec-251, dec-252
method: ground-truth reproduction on disk; gates exercised with bad/good inputs; full pytest on Python 3.13 venv
---

## A. EXECUTIVE VERDICT

| Wave | Verdict | Rationale |
|---|---|---|
| **1 — Honesty sweep** | **PASS-WITH-FINDINGS** | Doc corrections and DESIGN/DESIGN_CHANGELOG split reproduce on disk; dead baselines removed; PF-06 pointer fixed. No code regressions introduced. |
| **2 — Criticals** | **PASS-WITH-FINDINGS** | WAL rotation + windowed `_read_wal` are real, tested, and non-blocking. Always-loaded TASK_BRIEF floor text is load-bearing and decoupled from 2×2. **But R2/A1 “closed” overclaims:** production remains sparse (2 briefs vs 6 plans), and dec-250’s “committed-before-rotation” premise is not guaranteed. |
| **3 — Production-gate cohort** | **PASS-WITH-FINDINGS** | Registry spine, CODE gates (SH08/CA03), and dogfood spec archival reproduce. §0.1 has stale counts; PROMPT gates (P06/P07/P08) lack mechanical pytest liveness; full suite is not all-green in this environment (10 Codex-bridge failures). |

**Bottom line:** The three waves deliver real, mostly test-backed improvements — honesty fixes, WAL bounding, declarative registry, and two deterministic detectors — but several §0.1 ✅ marks overstate *behavior change*. The highest-risk gap matches the prior audit class: **TASK_BRIEF still has no production gate, only absence detection**, and legacy slugs remain non-compliant. dec-250 embeds a **false durability premise** (“every event is committed to git before rotation”) that is not enforced. Wave 3’s R4 detector correctly fires on Praxion itself (`covered:false`, 14 uncalibrated commits) but the wave did not append owed calibration rows — consistent with “detector-not-producer” design, not a bug.

### BLOCKING BEFORE WAVE 4

1. **EA-01** — Correct dec-250 / DESIGN onboarding copy: “committed-before-rotation” is not mechanically true; document actual durability (local `.1` + 7-day window) or add a pre-rotation flush/commit policy.
2. **EA-02** — Fix registry semantics for `TASK_BRIEF.md`: `production_gate=sentinel:P06` names a *detection* gate, not a producer; mislabels the declarative spine’s contract.
3. **EA-03** — Decide R2 hardening: either backfill briefs for legacy `SYSTEMS_PLAN` slugs **or** accept P06 WARN noise and downgrade §0.1 “A1 closed” to “detection wired, production sparse.”
4. **EA-04** — Append calibration rows for Wave 2/3 pipeline work (14 `feat:`/`fix:` commits since 2026-06-22) **or** explicitly defer with a dated owner — R4 is red on dogfood by design.
5. **EA-05** — Reconcile §0.1 test-count claim (1561 all green) with CI/local reality; fix or qualify the 12→14 uncalibrated commit count.

---

## B. CONFIRMATIONS

What is solid — do not re-investigate unless regressing.

| Claim | Check | Result |
|---|---|---|
| **B2** WAL row names real consumers | `grep` `.ai-state/DESIGN.md:64` | VERIFIED — lists `reconcile_pipeline_state.py`, post-merge dedup; dashboard marked planned |
| **B3** Recovery loop Built | `.ai-state/DESIGN.md:162` + `scripts/reconcile_pipeline_state.py` exists | VERIFIED |
| **A6 split** | `.ai-state/DESIGN.md:25` points to `DESIGN_CHANGELOG.md`; changelog exists (11,498 B) | VERIFIED — §1 is a short pointer, not 1,830-char history |
| **PF-06** schema pointer | `.ai-state/TECH_DEBT_RESOLVED.md:9` → skill reference | VERIFIED |
| **B1 doc-half (Wave 1)** | dec-248 body still mentions auto-rotation as *assumed*; Wave 1 corrected DESIGN | VERIFIED corrected in Wave 1; mechanism in Wave 2 |
| **R17 baselines removed** | `git log -1 -- .ai-state/evals/baselines/` → d23027e delete; dir absent on disk | VERIFIED |
| **R1 rotation code** | `hooks/_hook_utils.py:42-54`, `OBSERVATIONS_MAX_BYTES=10*1024*1024` | VERIFIED; `hooks/test_hook_utils.py` rotation tests pass (py3.13 venv) |
| **R1 windowed read + scenario 6** | `scripts/reconcile_pipeline_state.py:451-483`; `scripts/test_reconcile_pipeline_state.py:494-529` | VERIFIED — 58/58 gate/WAL tests pass |
| **R2 always-loaded floor** | `rules/swe/swe-agent-coordination-protocol.md:135` | VERIFIED — “unconditionally before the first agent spawn”; decoupled from 2×2 |
| **R2 skill mirror** | `skills/goal-disambiguation/SKILL.md:26,82` | VERIFIED |
| **P06 + verifier WARN defined** | `agents/sentinel.md:158,162`; `agents/verifier.md:48` | VERIFIED (PROMPT-kind) |
| **dec-248 re-affirmed** | `.ai-state/decisions/248-*.md` frontmatter `re_affirmed_by: [dec-250]` | VERIFIED |
| **Always-loaded budget** | `python3` byte sum CLAUDE.md + rules without `paths:` → **82,678 B** (~22,966 tok @ ÷3.6) | VERIFIED < 87,500 B (§0.1 claimed 82,691 — within rounding) |
| **Registry 24 artifacts, 0 none/deferred** | `grep production_gate= scripts/artifact_registry.py` → 24 rows; no `none`/`deferred` values | VERIFIED |
| **6 drift assertions** | `pytest scripts/test_artifact_registry.py -q` | VERIFIED — 44 passed including spine self-consistency + canaries |
| **SH08 detector** | `python3.13 scripts/check_spec_archival_gap.py --json` on Praxion | VERIFIED `gap:false`, newest spec `SPEC_production-gate-cohort_2026-06-26.md` |
| **CA03 detector** | `python3.13 scripts/check_calibration_coverage.py --json` | VERIFIED `covered:false`, 14 commits (detector bites on dogfood) |
| **R5 verifier harvest prose** | `agents/verifier.md:166` | VERIFIED — LEARNINGS `### Technical Debt` → td-NNN with dedup |
| **A6 producer** | `grep -rl DESIGN_CHANGELOG skills/` → `architecture-documentation.md:57` | VERIFIED |
| **Wave 3 dogfood spec** | `.ai-state/specs/SPEC_production-gate-cohort_2026-06-26.md` exists | VERIFIED |
| **Wave 2 preserved WAL/P06** | Wave 3 commits touch registry/sentinel, not `_hook_utils.py` or intake gate text | VERIFIED — no regression in diff scope |
| **Sentinel/verifier T03 exception** | `agents/sentinel.md:599` lines, `verifier.md:612`; T03 fail=700 for these two | VERIFIED within fail ceiling (warn band exceeded) |
| **Deferred R9-dashboard, R17, R19** | §0.1 + dec-252 Register Objection | VERIFIED explicitly deferred with reason |

---

## C. FINDINGS TABLE

| ID | Severity | Wave & R/A | Title | Blocking |
|---|---|---|---|---|
| EA-01 | **Critical** | W2 / R1, dec-250 | “Committed-before-rotation” premise is unenforced — uncommitted rows can land in gitignored `.1` | **Y** |
| EA-02 | Important | W3 / R2 registry | `TASK_BRIEF` `production_gate=sentinel:P06` mislabels detection as production | **Y** |
| EA-03 | Important | W2 / R2, A1 | §0.1 “A1 closed” overclaims — 4/6 `SYSTEMS_PLAN` slugs still lack `TASK_BRIEF` | **Y** |
| EA-04 | Important | W3 / R4 | Calibration rows owed for Wave 2/3 work; §0.1 cites “12” commits, disk shows **14** | **Y** |
| EA-05 | Important | W2–3 | §0.1 “1561 tests green” — 1551 passed, **10 failed** (Codex install/bridge) in py3.13 venv | **Y** |
| EA-06 | Important | W3 / P06,P07,P08 | PROMPT sentinel gates lack mechanical pytest liveness (fixtures only) | N |
| EA-07 | Important | W3 / R5 | LEARNINGS→td harvest is PROMPT-only — no CODE gate or golden pytest | N |
| EA-08 | Suggested | W2 | P06 registry lists TASK_BRIEF as `activation=conditional` while floor is Standard/Full-only | N |
| EA-09 | Suggested | Dogfooding | `check_id_citation_discipline.py` ships to managed projects but is **not** in Praxion `.pre-commit-config.yaml` | N |
| EA-10 | Suggested | W2–3 | System `/usr/bin/python3` is 3.9 — `datetime.UTC` breaks capture hooks and several scripts | N |
| EA-11 | Suggested | W3 / dec-251 | Declarative spine is “populated, not read” — visibility without consumer enforcement (known dissent) | N |
| EA-12 | Suggested | W3 / R3 | 90-day / 3-ADR thresholds are reasonable on dogfood but untested against doc-only ADR clusters | N |

---

## D. PER-FINDING DETAIL

### EA-01 — “Committed-before-rotation” premise unenforced

- **Claim audited:** dec-250 Context: “every event is committed to git history before rotation can move it”; Consequences: “Losing `.1` costs nothing — its rows were committed to git history.”
- **What you found — VERIFIED:**

```28:35:.ai-state/decisions/250-wal-bounding-rotation.md
One fact makes the design simple: **every event is committed to git history before rotation can move it.**
...
Losing `.1` costs nothing — its rows were committed to git history before rotation moved them.
```

  Rotation is synchronous on append (`hooks/_hook_utils.py:71-73`), not on commit. WAL is 7.4 MiB on disk (`ls -la .ai-state/observations.jsonl` → 7,413,792 bytes). `.1` is gitignored (`.gitignore:56`). No hook commits `observations.jsonl` before rotate.

  Reproduction:
  ```bash
  grep -n "committed to git" .ai-state/decisions/250-wal-bounding-rotation.md
  ls -la .ai-state/observations.jsonl
  git check-ignore -v .ai-state/observations.jsonl.1
  ```
- **Why it matters:** After rotation, recent events may exist **only** in gitignored `.1` until the next commit. Fresh clone, `git clean`, or `.1` loss drops recovery hints for in-window sessions — contradicting the ADR’s durability story. Local `_read_wal` still works within 7 days if `.1` survives.
- **Fix (pick one):**
  1. **Honest docs (XS):** Reword dec-250, DESIGN, onboard-project copy to “durability = local `.1` + 7-day reconciler window; git history is best-effort, not guaranteed per row.”
  2. **Pre-rotation commit hook (L):** Optional `git add observations.jsonl` before rename — heavy, probably wrong for async hooks.
  3. **Track `.1` or numbered segments (M):** Adopt dec-250 reversal trigger early if commit cadence stays sparse.
- **Verification path:** Document scenario test: populate WAL without commit → rotate → assert `_read_wal` returns rows from `.1` but `git show HEAD:.ai-state/observations.jsonl` lacks them.
- **Effort:** XS (docs) / M (segment retention)

---

### EA-02 — TASK_BRIEF production_gate mislabels detection as production

- **Claim audited:** §0.1 “0 deferred (every artifact names a real gate)”; registry spine makes production visible.
- **What you found — VERIFIED:**

```91:99:scripts/artifact_registry.py
    Artifact(
        "TASK_BRIEF.md",
        ...
        production_gate="sentinel:P06",
```

  P06 fires when `SYSTEMS_PLAN.md` exists **without** `TASK_BRIEF.md` (`agents/sentinel.md:158`) — absence detection, not production.

  ```bash
  grep -A8 'TASK_BRIEF.md' scripts/artifact_registry.py
  sed -n '158p' agents/sentinel.md
  ```
- **Why it matters:** `grep production_gate` falsely implies TASK_BRIEF has a producer gate; undermines the spine’s purpose (visibility of *production* mechanisms).
- **Fix:** Set `production_gate="producer:orchestrator"` (or `"producer:orchestrator:intake-gate"`) and add `detection_gate="sentinel:P06"` **or** document P06 as `detection_gate` in a separate field. Minimum: change TASK_BRIEF row to `producer:orchestrator` + footnote that P06 is absence backstop.
- **Verification path:** Extend `test_core_artifacts_have_a_gate` or add `test_detection_gates_distinct_from_production_gates`.
- **Effort:** S

---

### EA-03 — A1 / R2 “closed” overclaims sparse production

- **Claim audited:** §0.1 “R2 — and A1 (the dead criteria-thread gate) now closed”; Wave 2 dogfood TASK_BRIEF passed verifier.
- **What you found — VERIFIED:**

  ```bash
  find .ai-work -name TASK_BRIEF.md | wc -l        # → 2
  find .ai-work -name SYSTEMS_PLAN.md | wc -l      # → 6
  ```

  Briefs exist only for `production-gate-cohort` and `wal-bound-brief-floor`. Four legacy slugs with plans but no brief would trip P06 if sentinel ran.

  Always-loaded floor is **not inert** — text at `rules/swe/swe-agent-coordination-protocol.md:135` is mandatory language. But dec-249’s own falsifier applies: WARN-only backstop without production.

  ```bash
  sed -n '135p' rules/swe/swe-agent-coordination-protocol.md
  find .ai-work -name TASK_BRIEF.md -o -name SYSTEMS_PLAN.md
  ```
- **Why it matters:** Criteria-thread provenance remains broken for most historical slugs; verifier carry-forward still has nothing on 4/6 runs.
- **Fix:**
  1. Backfill `TASK_BRIEF.md` for slugs with `SYSTEMS_PLAN.md` (retroactive, S).
  2. Harden to blocking gate: refuse architect spawn until brief exists (M — behavior change).
  3. Downgrade §0.1 to “detection wired; production sparse on legacy slugs.”
- **Verification path:** `find .ai-work -name SYSTEMS_PLAN.md -execdir test -f TASK_BRIEF.md \; -print` → empty.
- **Effort:** S–M

---

### EA-04 — Calibration coverage red on dogfood; §0.1 count stale

- **Claim audited:** §0.1 “R4 `covered:false` (12 uncalibrated commits — the producer rows are owed)”.
- **What you found — VERIFIED:**

  ```bash
  python3.13 scripts/check_calibration_coverage.py --json
  # → "uncalibrated_commits": 14, "newest_calibration": "2026-06-22"
  git log --oneline --since=2026-06-22 | grep -E '^[0-9a-f]+ (feat|fix):' | wc -l  # → 14
  ```

  R4 detector **correctly bites**. Owed rows not appended — consistent with dec-252 dissent (detector-not-producer) but §0.1 should not imply closure.
- **Why it matters:** CA03 will WARN on every sentinel pass until rows appended; undermines “dogfood consistency” narrative.
- **Fix:** Append calibration rows for `wal-bound-brief-floor`, `production-gate-cohort`, and intervening pipeline commits; update §0.1 count.
- **Verification path:** `check_calibration_coverage.py --json` → `covered:true`.
- **Effort:** XS

---

### EA-05 — Full suite not all-green vs §0.1 claim

- **Claim audited:** §0.1 Wave 3 “1561 tests green”.
- **What you found — VERIFIED (this environment):**

  ```bash
  python3.13 -m venv /tmp/praxion-audit-venv && pip install pytest pyyaml
  pytest hooks/ scripts/ tests/ -q -o addopts=""
  # → 1551 passed, 10 failed, 1 skipped, 1 xfailed
  ```

  Failures confined to Codex bridge/install (`scripts/test_export_codex_rules_bridge.py`, `scripts/test_install_codex.py`, `scripts/test_manage_codex_mcp.py`) — likely environment/home-layout, not wave code. Wave-specific tests: **58/58 passed** (WAL, spec gap, calibration, hook utils, registry).
- **Why it matters:** §0.1 overstates CI health; implementer may miss Codex regressions.
- **Fix:** Re-run CI `test.yml` on main; update §0.1 with qualified count or fix Codex tests.
- **Verification path:** Green GitHub Actions `test` job on merge commit `6ccd3db`.
- **Effort:** S (investigate Codex failures)

---

### EA-06 — PROMPT gates lack mechanical pytest liveness

- **Claim audited:** §0.1 “each with a gate-liveness proof (canary for CODE, golden bad-case for PROMPT)”.
- **What you found — VERIFIED:**

  Fixtures exist (`tests/fixtures/sentinel/p06_missing_task_brief/`, `challenge_no_disposition/`, `stale_slug_advisory/`). `tests/test_sh07_sentinel.py:180-193` explicitly TODO — **no mechanical P06 checker**.

  SH08/CA03 have pytest (`scripts/test_check_spec_archival_gap.py`, `scripts/test_check_calibration_coverage.py`) — **58 passed**.

  ```bash
  grep -n "TODO: wire a mechanical P06" tests/test_sh07_sentinel.py
  ls tests/fixtures/sentinel/
  ```
- **Why it matters:** P06/P07/P08 liveness depends on sentinel LLM discipline; regressions won’t turn CI red.
- **Fix:** Add `scripts/check_task_brief_presence.py` (P06), optional P07 disposition grep script; wire sentinel auto-checks + pytest canaries (mirror SH08 pattern).
- **Verification path:** pytest canary on `p06_missing_task_brief/` fixture → exit 1.
- **Effort:** M

---

### EA-07 — R5 LEARNINGS harvest is PROMPT-only

- **Claim audited:** §0.1 “verifier harvests LEARNINGS ### Technical Debt → td-NNN”.
- **What you found — VERIFIED:** Prose at `agents/verifier.md:166` is clear and preserves four-writer contract. No pytest golden for promotion; `rules/swe/agent-intermediate-documents.md:126` honestly marks prose sections skill-genesis-or-lost.
- **Why it matters:** Harvest fires only when verifier runs and complies; silent skip possible.
- **Fix:** Optional golden test parsing verifier Phase-1 checklist against fixture LEARNINGS; or accept PROMPT gate per dec-252.
- **Verification path:** Fixture-driven verifier self-test or integration eval (R10).
- **Effort:** M

---

### EA-08 — TASK_BRIEF activation vs floor mismatch

- **Claim audited:** Registry spine accuracy.
- **What you found — VERIFIED:** `TASK_BRIEF.md` has `activation="conditional"` (`scripts/artifact_registry.py:95`) while floor applies only Standard/Full — not Lightweight-always. Minor semantic drift.
- **Fix:** Document in registry description or split activation to `standard-full`.
- **Effort:** XS

---

### EA-09 — Dogfooding: id-citation not in Praxion pre-commit

- **Claim audited:** Convention compliance / dogfood consistency (audit item 8).
- **What you found — VERIFIED:** `.pre-commit-config.yaml` includes shipped-artifact isolation (Block A) but **not** `check_id_citation_discipline.py`. `commands/onboard-project.md:300` installs id-citation for **user projects only**.
- **Why it matters:** Wave 3 id-citation FAIL was caught in verifier loop, not pre-commit — downstream stricter than self.
- **Fix:** Add Block F local hook mirroring onboard-project, or document intentional asymmetry in `README_DEV.md`.
- **Effort:** S

---

### EA-10 — Python 3.9 system interpreter breaks hooks

- **Claim audited:** Hook non-blocking / graceful behavior.
- **What you found — VERIFIED:**

  ```bash
  /usr/bin/python3 --version   # 3.9.6
  python3 hooks/capture_memory.py  # ImportError: cannot import name 'UTC' from 'datetime'
  ```

  CI uses Python 3.13 (`.github/workflows/test.yml:37`). Codex/hook shebangs use bare `python3`.
- **Why it matters:** macOS Xcode python3 users get broken observability hooks silently (exit 1).
- **Fix:** Pin hook shebang to `python3.11+` or use `timezone.utc` shim for 3.9.
- **Effort:** S

---

### EA-11 — Registry spine checked-not-read (design, not defect)

- **Claim audited:** dec-251 value proposition.
- **What you found — VERIFIED:** No consumer reads `production_gate`/`cleanup_policy`; dissent in dec-251 is accurate. Drift tests enforce self-consistency only.
- **Why it matters:** Wave 4+ should wire `clean_work_safety.py` to registry or accept documentation-only spine until then.
- **Fix:** Track in Wave 4/5; no immediate code change required.
- **Effort:** — (design)

---

### EA-12 — R3 heuristic edge cases

- **Claim audited:** SH08 90-day / 3-ADR cluster thresholds.
- **What you found — VERIFIED on dogfood:** `gap:false` with fresh spec. Fixture tests pass (`test_check_spec_archival_gap.py`). **INFERRED risk:** chore/docs ADRs sharing tags could theoretically cluster without a feature — not reproduced on Praxion.
- **Fix:** Monitor; add tag-exclusion list if false fires appear.
- **Effort:** XS if needed

---

## E. DESIGN-DISCONFIRMATION

| Decision | Strongest case against | Verdict |
|---|---|---|
| **Gitignored `.1` segment (dec-250)** | Uncommitted rows rotate out of git tracking; durability relies on local disk + 7-day read, not git history as ADR states | **Revisit** — fix copy or retention (EA-01) before Wave 4 |
| **R4 detector-not-producer (dec-252)** | CA03 will stay red on active repos until humans append rows; calibration remains voluntary | **Re-affirm** for Wave 3 scope — but Wave 4 should append owed rows or add hook |
| **R5 verifier-owned harvest (dec-252)** | PROMPT gate can skip; planner/implementer could file faster | **Re-affirm** — preserves four-writer contract; defer CODE gate to R10 eval |
| **90-day spec threshold (R3)** | Fast-moving projects archive specs quarterly at most; 90d may be lax | **Re-affirm** on current dogfood; falsifier = repeated `gap:true` with legitimate specs |
| **TASK_BRIEF WARN-only floor (dec-249)** | dec-249 falsifier explicitly predicts this; 4/6 slugs still non-compliant | **Revisit** before claiming A1 closed — hardening or backfill (EA-03) |
| **Populated-not-projected registry (dec-251)** | Second hand-maintained list that drifts from reality | **Re-affirm** short-term; wire one consumer in Wave 4 to prove value |

---

## F. SUGGESTED REMEDIATION SEQUENCE

**Batch 1 — parallel, blocking (before Wave 4 kickoff)**

1. **EA-01** — Fix dec-250 / onboarding durability language (XS).
2. **EA-04** — Append calibration rows for Wave 2/3 slugs (XS).
3. **EA-02** — Correct TASK_BRIEF registry gate semantics (S).
4. **EA-03** — Either backfill legacy briefs or downgrade §0.1 A1 claim (S).

**Batch 2 — parallel, non-blocking**

5. **EA-05** — Confirm CI green on `6ccd3db`; fix Codex test failures if reproducible in CI (S).
6. **EA-06** — Mechanical P06 checker + pytest (M).
7. **EA-09** — Decide id-citation dogfood policy (S).

**Batch 3 — Wave 4 alignment**

8. **EA-10** — Python version policy for hooks (S).
9. **EA-07 / EA-11** — Wire registry to `clean_work_safety` or R10 eval harness (M–L).

---

## Appendix — Key reproduction commands

```bash
# Always-loaded budget (Praxion project scope)
python3 -c "
from pathlib import Path
root = Path('.')
total = root.joinpath('CLAUDE.md').stat().st_size
for f in sorted((root/'rules').rglob('*.md')):
    text = f.read_text()
    if text.startswith('---') and 'paths:' in text.split('---',2)[1]: continue
    total += f.stat().st_size
print(total)
"

# TASK_BRIEF vs SYSTEMS_PLAN coverage
find .ai-work -name TASK_BRIEF.md
find .ai-work -name SYSTEMS_PLAN.md

# Gates on live repo (requires Python ≥3.11)
python3.13 scripts/check_spec_archival_gap.py --json
python3.13 scripts/check_calibration_coverage.py --json

# Wave-focused tests (Python 3.13 venv recommended)
pytest scripts/test_artifact_registry.py hooks/test_hook_utils.py \
  scripts/test_check_spec_archival_gap.py scripts/test_check_calibration_coverage.py \
  scripts/test_reconcile_pipeline_state.py -q -o addopts=""
```

**Evidence labels used:** VERIFIED = reproduced on disk; INFERRED = reasoned, not reproduced; RISK = potential, unconfirmed.
