---
id: dec-108
title: Golden-rule enforcement at commit time via standalone script invoked from pre-commit hook
status: accepted
category: architectural
date: 2026-05-01
summary: 'Ship scripts/check_aac_golden_rule.py (stdlib, idempotent, side-effect-free) invoked from git-pre-commit-hook.sh Block D to detect generated-output edits without source changes; line-adjacent # aac-override: <reason> escape hatch; sentinel EC dimension reuses the same script in audit mode.'
tags: [aac, dac, hook, enforcement, drift-detection, override, sentinel, ec, gate]
made_by: agent
agent_type: systems-architect
pipeline_tier: standard
affected_files:
  - scripts/check_aac_golden_rule.py
  - scripts/git-pre-commit-hook.sh
  - rules/writing/aac-dac-conventions.md
  - agents/sentinel.md
re_affirms: dec-106
re_affirmed_by:
  - dec-106
  - dec-107
  - dec-110
---

## Context

The v1 AaC substrate (fence convention `dec-098`, validator script, `architect-validator` agent `dec-100`) created the **convention** for distinguishing generated content from authored content but did not create the **enforcement** that prevents drift in the first place. Without a gate, contributors can hand-edit a generated `.d2`/`.svg` artifact or a generated region inside `ARCHITECTURE.md` without re-running the source DSL — the v1 fence validator will eventually catch this in the `architect-validator`'s pre-merge run, but a commit-time gate is the cheapest and earliest signal.

Two distinct sub-problems coexist:
- **Generated file outputs** (`docs/diagrams/<name>/<view>.{d2,svg}`) edited without staging the corresponding `<name>.c4` change.
- **Fence-interior content** (text inside `<!-- aac:generated source=X view=Y -->` ... `<!-- aac:end -->`) edited without staging the source `X`.

A legitimate-but-rare counter-case exists: an author needs to hand-edit a generated artifact temporarily (e.g., to fix a typo in a rendered SVG until a regen lands). Without an explicit override, the gate would block legitimate work; with no gate at all, accidental drift accumulates silently.

## Decision

Ship a new standalone script `scripts/check_aac_golden_rule.py`:

- **Stdlib-only Python**, idempotent, side-effect-free (mirrors `aac_fence_validator.py`'s contract).
- **Inputs**: paths from `git diff --cached --name-only --diff-filter=ACMR` and hunks from `git diff --cached -U0` (when fence-interior detection is needed).
- **Detection**:
  - **Path-pair detection.** For each staged generated-output file matching `docs/diagrams/<name>/<view>.{d2,svg}`, FAIL unless the corresponding `<name>.c4` is also staged or an override comment was staged for that file.
  - **Fence-interior detection.** For each staged `**/ARCHITECTURE.md` or `docs/architecture.md`, find hunks whose line range falls inside an `aac:generated` region (parsed by reusing the existing `_GENERATED_PATTERN` / `_CLOSER_PATTERN` regex from `aac_fence_validator.py`); FAIL unless the fence's `source=` path is also staged or an override comment was staged adjacent to the change.
- **Override syntax**:
  - Code/config/d2/yaml/sh: `# aac-override: <reason>` on the violating line or the line immediately above.
  - SVG/HTML/Markdown: `<!-- aac-override: <reason> -->` same adjacency rule.
  - Reason must be non-empty (mirrors the fitness waiver rule).
- **Modes**:
  - `--mode=gate` (default): scans staged diff; exits 1 on violation.
  - `--mode=audit`: scans the last N commits (configurable horizon); always exits 0; produces JSON findings for sentinel consumption.
- **Output**: stdout findings list with file:line, severity, and remedy hint; `--json` for machine consumption.

Invoke the script from `scripts/git-pre-commit-hook.sh` as **Block D** (after Block A — shipped-artifact isolation, Block B — canonical-block sync, and Block C — diagram regeneration). Block D runs only when the staged set includes a path matching the architectural-trigger globs.

`agents/sentinel.md` gains one new EC-dimension check that runs `python3 scripts/check_aac_golden_rule.py --mode=audit --json` and surfaces findings as `important`-severity TECH_DEBT_LEDGER rows (`class: drift, source: sentinel, owner-role: implementer`).

`rules/writing/aac-dac-conventions.md` (already path-scoped) gains an Override Syntax section (≤30 lines) — zero always-loaded token cost.

## Considered Options

### Option 1 — Extend `scripts/diagram-regen-hook.sh` with an enforcement mode

**Pros:** Single hook script; matches the brief's framing.

**Cons:** `diagram-regen-hook.sh` is **side-effecting** (it runs `likec4 gen` and `git add`). Folding enforcement into a side-effecting script creates two operating modes that share the same invocation surface — the script must distinguish "regenerate" from "verify-only" cleanly, multiplying its responsibility. Sentinel's audit-mode invocation must not mutate working tree state, which forbids reusing a side-effecting script. Rejected on simplicity-first and side-effect-isolation grounds.

### Option 2 — New standalone `scripts/check_aac_golden_rule.py` (chosen)

**Pros:** Clean separation: regeneration vs enforcement. Side-effect-free script can be reused by sentinel without working-tree concerns. Follows the established `check_*` script convention (`check_id_citation_discipline.py`, `check_shipped_artifact_isolation.py`, `check_squash_safety.py`). Fitness rule already declares the precondition-boundary contract (pre-commit `check_*` scripts must not import post-merge `finalize_*` scripts) — the new script slots into the existing layout.

**Cons:** One more script in `scripts/`. The Block D addition to the pre-commit hook is small but is a new entry point that contributors must learn. Mitigated by the rule update.

### Option 3 — Checksum sidecar files

**Pros:** Explicit, machine-parseable.

**Cons:** Introduces sidecar files that contradict `dec-094`'s commit-both convention. Doubles the git-tracked artifact count for diagrams. Rejected.

### Option 4 — No commit-time gate; rely on `architect-validator` pre-merge only

**Pros:** No new script.

**Cons:** Drift is detected only at PR time, after a human has already committed. Re-work cost compounds. The `architect-validator` runs an Opus-tier reasoning pass; using it as the *only* gate forces every architectural commit through API spend even when a mechanical check would suffice. Rejected.

## Consequences

**Positive:**

- Closes the "drift in flight" gap between v1 fence convention and v1 PR-time validator.
- One reusable script serves two consumers (commit-time hook + sentinel audit).
- Override syntax matches existing precedents (`# fitness-waiver:`, `<!-- shipped-artifact-isolation:ignore -->`); contributor cognitive load is small.
- Zero always-loaded token cost (rule update is path-scoped; no skill loaded by default).

**Negative:**

- One additional pre-commit check; commit time grows by milliseconds for non-architectural commits (early exit) and by ~50ms for architectural commits.
- Override-syntax misuse is possible; mitigated by sentinel EC counting overrides and by PR review.

**Operational:**

- `scripts/check_aac_golden_rule.py` must declare its citation in the module docstring (matches the fitness citation contract: cite the relevant ADR id or `CLAUDE.md§<principle>`).
- Block D addition to `git-pre-commit-hook.sh` requires updating `scripts/CLAUDE.md` to list the new script.
- The sentinel agent file gains one new check id (assigned per sentinel's own conventions).
- The Block D addition is **Praxion-author-only** at v1.1 — it is not propagated to user projects via `/onboard-project` Phase 4 in this slate. Downstream rollout deferred until the AaC fence convention is exercised across at least one consumer project.
- Library-version verification: no new external library introduced. The script depends on `git`, Python 3.13 stdlib, and existing project conventions.

## Prior Decision

This ADR re-affirms `dec-106` (the AaC architecture CI pipeline, sibling draft). The CI pipeline at PR time and the commit-time gate share the `check_aac_golden_rule.py` script as substrate but operate at different lifecycle points; they remain two ADRs because they have distinct surfaces and triggers. If the CI pipeline ADR is later superseded with a different enforcement architecture, the script's gate-mode use survives and the audit-mode use migrates to whatever replaces sentinel.
