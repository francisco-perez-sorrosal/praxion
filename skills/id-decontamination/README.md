# id-decontamination

Detection and bulk remediation of ephemeral identifier citations (REQ-*, AC-*, EC-X.X.X,
Step N, req{NN}_ test naming) left in project source code from pre-discipline Praxion
pipelines. Covers detection, optional traceability salvage, bulk rename/deletion, and
regression-prevention setup.

## When to Use

- `check_id_citation_discipline.py` reports violations on a project tree
- A user asks to "clean up REQ citations", "decontaminate id references", or "remove pipeline residues from code"
- Onboarding a legacy (pre-discipline-rule) project to Praxion
- A pre-commit gate blocks commits with id-citation violations and the user wants bulk remediation

## Activation

Auto-triggered by the trigger phrases in the skill description or when `/decontaminate-ids`
is invoked. Also activates when `check_id_citation_discipline.py` is run and reports hits.

## Skill Contents

- `SKILL.md` — six-step remediation procedure: prerequisite check, detection sweep, salvage, triage, verification, regression prevention
- No reference files — the procedure is fully self-contained

## Quick Start

```bash
# 1. Run the detector
python3 "$CLAUDE_PLUGIN_ROOT/scripts/check_id_citation_discipline.py" > /tmp/citation-hits.txt 2>&1
wc -l /tmp/citation-hits.txt

# 2. Follow the six-step procedure in SKILL.md
# 3. Verify clean
python3 "$CLAUDE_PLUGIN_ROOT/scripts/check_id_citation_discipline.py"
# Expected: "scanned N code file(s); 0 id-citation violations."
```

## Related Skills

- [`software-planning`](../software-planning/SKILL.md) — for pipeline delegation when decontamination spans many files (≥4 files, >20 hits)
