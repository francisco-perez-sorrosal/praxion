---
description: Detect and remediate REQ/AC/step citations in the current project's source code
allowed-tools: [Bash, Read, Edit, Write, Grep, Glob]
---

Run the `check_id_citation_discipline.py` detector on the current project and remediate any findings following the methodology in the [`id-decontamination`](../skills/id-decontamination/SKILL.md) skill.

`$ARGUMENTS` — optional flags:
- (empty) — detect and interactively remediate
- `detect-only` — run detector, report findings, stop before remediation
- `pipeline` — delegate remediation to a Standard-tier pipeline regardless of violation count

## Procedure

1. **Load the skill.** Read `skills/id-decontamination/SKILL.md` for the six-step methodology.

2. **Run the detector.**

   ```bash
   python3 "$CLAUDE_PLUGIN_ROOT/scripts/check_id_citation_discipline.py"
   ```

   If `$CLAUDE_PLUGIN_ROOT` is unset (running from the Praxion source checkout rather than an installed plugin), fall back to `scripts/check_id_citation_discipline.py`.

3. **Classify findings.**
   - 0 violations → report "clean" and stop.
   - 1–20 violations → propose Direct-tier remediation (in-session edits).
   - > 20 violations OR > 3 files → propose delegating to a Standard-tier pipeline.
   - User passed `pipeline` → always delegate.
   - User passed `detect-only` → print the report and stop.

4. **Check for salvage need.** If `.ai-state/specs/` contains archived SPEC files and the tree has REQ references, warn the user that REQ-to-test mappings should be salvaged into archived SPEC matrices before deletion. Offer to do this step first.

5. **Remediate.** Follow the skill's Step 3 procedure (direct or pipeline) based on classification.

6. **Verify.** Re-run the detector. Expected: 0 violations. If residues remain, diagnose (unexpected file types, new exempt paths needed, or genuine misses).

7. **Summarize.** Produce the report described in the skill's "Reporting" section: citations cleaned by type, files touched, ignore markers added (if any), salvage performed (if any), regression-prevention layer.

## Constraints

- **Do not rename test functions without running the test suite.** Collisions surface as pytest collection errors; ignoring them silently leaves the suite broken.
- **Do not delete REQ references in code when archived specs exist.** Salvage first (skill Step 2). If the user declines salvage, note it in the final summary.
- **Preserve `dec-NNN` references** (finalized ADRs — persistent, allowed by the rule).
- **Preserve sentinel check IDs** (`F07`, `T03`, `EC06`, `SH03`, `BC02`, etc.) inside sentinel's own files.
- **Exempt teaching material by path**, not by per-file ignore markers. If a new teaching-material path surfaces, extend the detector's `EXEMPT_PATH_PREFIXES` rather than adding `id-citation-discipline:ignore` markers line-by-line.
