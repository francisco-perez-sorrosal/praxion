---
id: dec-110
title: golden-rule hook placement in Block D, not Block C
status: retired
retired_by:
  - dec-246
category: implementation
date: 2026-05-01
summary: "Block C in git-pre-commit-hook.sh is already occupied by diagram regeneration; the golden-rule enforcement check lands in Block D. SYSTEMS_PLAN.md's 'Block C' reference was a codebase-drift error corrected at planning time."
tags: [aac, dac, hook, enforcement, pre-commit, block-d, planning-correction]
made_by: agent
agent_type: implementation-planner
pipeline_tier: standard
affected_files:
  - scripts/git-pre-commit-hook.sh
re_affirms: dec-108
---

## Context

`dec-108` (the golden-rule enforcement hook ADR) refers to the pre-commit hook addition as "Block C". During implementation planning, codebase verification revealed that `scripts/git-pre-commit-hook.sh` already has three blocks:

- Block A: Shipped-artifact isolation (`check_shipped_artifact_isolation.py`)
- Block B: Canonical-block sync (`sync_canonical_blocks.py`)
- Block C: Diagram regeneration (`diagram-regen-hook.sh`)

"Block C" is occupied. The SYSTEMS_PLAN's reference to "Block C invocation" for the new golden-rule script was a codebase-drift error — the architect did not read the hook file during architecture phase (the hook had Block C added as part of the v1 implementation that landed before this v1.1 planning pass).

## Decision

The golden-rule enforcement script (`scripts/check_aac_golden_rule.py`) is wired into `scripts/git-pre-commit-hook.sh` as **Block D** — the next sequential block label after the existing three. No renaming of existing blocks is needed.

The `dec-108` ADR remains correct in every other respect (script design, override syntax, sentinel EC reuse). Only the block label is corrected here.

## Considered Options

### Option 1 — Use Block D (chosen)

The next available block label is D. Add a new section:

```bash
# ---------------------------------------------------------------------------
# Block D: AaC golden rule enforcement
# ---------------------------------------------------------------------------
```

**Pros**: No churn to existing blocks; consistent sequential labeling.

**Cons**: None.

### Option 2 — Rename existing Block C to "Block C: Diagram + Golden Rule"

Merge the golden-rule check into the existing Block C.

**Cons**: Block C currently has a single, clear purpose (diagram regeneration via the `diagram-regen-hook.sh`). Merging two distinct checks violates the one-purpose-per-block convention and would require updating the block comment. Rejected.

### Option 3 — Rename existing Block C to "Block D" and use "Block C" for the new check

**Cons**: Pure churn; the existing Block C label appears in the hook's own header comment and would require coordinated updates. No benefit. Rejected.

## Consequences

**Positive:**
- No churn to existing hook blocks.
- Sequential block labeling preserved (A → B → C → D).
- The new block follows the same comment-banner format as A, B, C.

**Negative:**
- The SYSTEMS_PLAN's "Block C" reference is technically wrong; reading it without this correction would cause the implementer to overwrite Block C. This ADR and the `Inputs Superseded` table in `IMPLEMENTATION_PLAN.md` correct the record.

**Operational:**
- The hook header comment (at the top of `git-pre-commit-hook.sh`) describes Block A and Block B. The implementer must add a one-line description of Block D to the header comment.
- The hook's existing Block C guard (`if [ -f "$DIAGRAM_HOOK" ] && [ -x "$DIAGRAM_HOOK" ]`) is the model for Block D's conditional guard.

## Prior Decision

This ADR re-affirms `dec-108`. The golden-rule enforcement design is correct; only the block label is corrected. The systemic cause (architect did not re-read the hook file after v1 landed) is noted so future architects can add "read hook file to verify block labels" to the AaC-related planning checklist.

**Retired by `dec-246`**, which replaced the bespoke `scripts/git-pre-commit-hook.sh` with the pre-commit framework. This decision's entire content is *which lettered block of that script* the golden-rule check occupies. The framework has no blocks, so `dec-246` did not choose a different slot — it abolished the concept of a slot. That is retirement rather than supersession: `dec-246` never weighed Block C against Block D, and a reader has no two answers to compare.

The enforcement it was correcting the placement of survives: `check_aac_golden_rule.py` runs as the `aac-golden-rule` pre-commit hook. Only the placement question died. This decision matters again only if ordered blocks return to the commit gate.
