---
name: id-decontamination
description: Detect and remove ephemeral identifier citations (REQ-*, AC-*, EC-X.X.X, Step N, req{NN}_ test naming) from project source code. Use when a project was managed with an older Praxion version before the id-citation-discipline rule shipped, when the `check_id_citation_discipline.py` detector reports violations, when the user asks to "clean up REQ citations", "decontaminate id references", or "remove pipeline residues from code", or after the `/decontaminate-ids` command is invoked.
compatibility: Claude Code
allowed-tools: [Read, Write, Edit, Glob, Grep, Bash]
---

# ID Decontamination

Detection and remediation methodology for removing ephemeral identifier citations from project source code. Operates in any project that has been managed with Praxion, whether Praxion's own tree or a downstream project that was built using Praxion before the `id-citation-discipline` rule was in force.

**Related artifacts:**

- [`rules/swe/id-citation-discipline.md`](../../rules/swe/id-citation-discipline.md) — the rule that defines what citations are forbidden and why
- `scripts/check_id_citation_discipline.py` — the detector (installed by Praxion; runs in any project)
- [`shipped-artifact-isolation.md`](../../rules/swe/shipped-artifact-isolation.md) — the outbound counterpart rule

## When to Apply This Skill

**Activate when:**

- The detector reports violations on a project's tree
- A user says "my project has REQ/AC citations from old pipelines — help me clean them up"
- A pre-commit gate blocks a commit with id-citation violations and the user wants bulk remediation rather than per-violation ignore markers
- Onboarding a legacy project (pre-discipline-rule) to Praxion

**Skip when:**

- The project already passes `check_id_citation_discipline.py` — nothing to do
- The user wants to add the ignore marker to specific intentional citations (that's manual, not bulk remediation)
- The violations are in exempt paths (teaching material, test fixtures, vendored deps) — the detector already exempts these

## Gotchas

- **Don't delete REQ references without salvaging first.** If the project has archived specs in `.ai-state/specs/`, the REQ-to-test mapping in code is the only record of which tests validate which REQ. Extract that mapping into the archived SPEC's `## Traceability` matrix BEFORE deleting REQ citations. Most projects have no archived specs — in that case, remediation is pure deletion with nothing to salvage.
- **Test function renames can collide.** Dropping `test_req31_foo` to `test_foo` is usually safe; dropping two distinct tests to the same new name creates a pytest collection error. After renaming, run the suite — collisions surface immediately.
- **Bulk `replace_all` on docstring prefixes leaves lowercase first letters.** `"""AC-14: regular merge..."""` → `"""regular merge..."""`. Python docstring convention expects a capital. After bulk replacement, pass through the file and capitalize the first letters of affected docstrings.
- **Third-party vendored code can trip a permissive detector.** The detector already excludes `.venv/`, `node_modules/`, `site-packages/`, etc. If an unexpected vendored dir surfaces hits, widen the exclusion list in `scripts/check_id_citation_discipline.py::EXCLUDED_PATH_FRAGMENTS` rather than per-file ignore markers.
- **Installer-UI "Step N" labels look like pipeline citations.** `install_claude.sh` and similar use `header "Step N — phase"` as user-facing progress indicators. These are legitimate and exempt by filename. If the project has its own installer script with similar labels, add it to `EXEMPT_FILENAMES`.

## Six-Step Procedure

### Step 0 — Prerequisite check

Verify the detector is available:

```bash
which check_id_citation_discipline.py  # installed globally by install_claude.sh
# OR
ls "$CLAUDE_PLUGIN_ROOT/scripts/check_id_citation_discipline.py"  # plugin install path
```

If missing, run `install_claude.sh` from Praxion before proceeding. Without the detector in force, remediating a project means every future pipeline will immediately re-contaminate it.

### Step 1 — Detection sweep

Run the detector against the project root:

```bash
cd <project-root>
python3 "$CLAUDE_PLUGIN_ROOT/scripts/check_id_citation_discipline.py" > /tmp/citation-hits.txt 2>&1 || true
wc -l /tmp/citation-hits.txt
```

Categorize the hits:

- **Test-function/class names** carrying REQ/AC prefixes (`def test_req03_*`, `class TestAc14*`) — mechanical bulk renames
- **Docstring/comment prefixes** (`"""AC-14: ..."""`, `# REQ-SG-01 — ...`) — bulk prefix removal plus capitalization pass <!-- shipped-artifact-isolation:ignore -->
- **Parenthetical suffixes** (`describe behavior (REQ-ONBOARD-05)`) — targeted deletion of the parenthetical <!-- shipped-artifact-isolation:ignore -->
- **Narrative references** (`"per Step 10b"`, `"AC-20 of the concurrency-collab pipeline"`) — targeted rewrites that preserve meaning
- **Self-references** (a detector/rule file describing its own patterns) — add an `id-citation-discipline:ignore` marker or add the file to the detector's exemption list

### Step 2 — Salvage before deletion

Only required if archived specs exist. Skip otherwise (most common case).

```bash
ls .ai-state/specs/ 2>/dev/null
```

If archived specs are present, before deleting REQ references in code:

1. For each archived SPEC (`.ai-state/specs/SPEC_<name>_YYYY-MM-DD.md`), check whether its `## Traceability` section is populated
2. If not populated, reconstruct the matrix from the code's REQ references: for each REQ-NN cited in test files or docstrings, build a row mapping REQ → test path::test name → implementation path::function
3. Insert the matrix into the archived SPEC
4. Commit the salvaged matrices BEFORE starting the deletion pass — that way if remediation goes sideways, the traceability record survives in git history

### Step 3 — Triage and remediation

Choose execution mode by scale:

**Direct (≤ 3 files, ≤ 20 hits):** do it by hand, mirroring the technique shipped with Praxion's own remediation campaign:

1. Use `replace_all=true` for uniform patterns: `def test_req\d+_` → `def test_`, `class TestReq\d+` → `class Test`, `AC-NN: ` → ``, `# REQ-XX-NN — ` → `# `
2. Targeted `Edit` calls for module docstrings (multi-line rewrites), section separators, and narrative "Step N" residues
3. Fix docstring capitalization after the bulk pass — first letters that became lowercase
4. Run the full test suite after each file's remediation — tests should still pass (you edited docstrings + names, not logic)

**Pipeline (≥ 4 files, > 20 hits):** delegate to a Standard-tier pipeline. Task prompt template:

> "Decontaminate this project per `rules/swe/id-citation-discipline.md`. Scan for REQ-NN, AC-NN, EC-X.X.X, step-number citations, and test-name/class-name prefixes. Preserve `dec-NNN` references (finalized ADRs) and sentinel check IDs inside sentinel code. For each hit, rewrite to behavioral naming + remove the citation, ensuring function names and docstrings remain unique and readable. Run the full test suite after, confirm it passes, and produce commits grouped by file/module."

The pipeline produces SYSTEMS_PLAN.md, IMPLEMENTATION_PLAN.md with per-file steps, and verifier coverage — all the pipeline mechanics apply to the decontamination task the same way they would apply to any other feature.

### Step 4 — Verification

After remediation, confirm clean:

```bash
python3 "$CLAUDE_PLUGIN_ROOT/scripts/check_id_citation_discipline.py"
# Expected: "scanned N code file(s); 0 id-citation violations."
```

If hits remain:

- They may be in a file type the detector doesn't scan by default (extend `CODE_EXTENSIONS`)
- They may be in a path that needs an additional exempt entry (teaching material added by the project)
- They may be genuine residues requiring a second pass

Run the full test suite after remediation. Collisions surface as pytest collection errors (duplicate test names after prefix removal); disambiguate with descriptive suffixes that capture the specific scenario being tested.

### Step 5 — Regression prevention

Three levels of defense, increasing invasiveness:

1. **Hook is already in force.** The `check_id_citation_discipline.py` gate fires on every `git commit` routed through Claude Code, via Praxion's hooks.json. Zero extra setup per project.
2. **Optional CI check.** Add a step to the project's CI workflow:

   ```yaml
   - name: ID citation discipline
     run: python3 "$GITHUB_WORKSPACE/.claude/plugins/..../scripts/check_id_citation_discipline.py"
   ```

   This catches contributors who commit outside Claude Code (plain `git commit`) and bypass the Claude-Code hook.
3. **Git pre-commit hook.** For projects that want enforcement at the git layer (independent of Claude Code), install a git pre-commit hook that invokes the detector. Praxion does not ship this by default — it's an opt-in per-project install.

## Decontamination of Memory Entries

Often overlooked: the project's `.ai-state/memory.json` (if the Memory MCP is in use) may hold past learnings that reference stale REQ/AC/step identifiers. Scan and update alongside code:

```bash
grep -n "REQ-[A-Z0-9]\|AC-[0-9]\|Step [0-9]" .ai-state/memory.json 2>/dev/null
```

For each hit, edit the memory entry to describe the behavior instead of the identifier. Memory is project-local, so this is a one-time cleanup per project. The memory-protocol rule's discipline applies going forward — new memory entries should describe behavior, not cite ephemeral IDs.

## Reporting

After decontamination, produce a short summary:

- Total citations cleaned (by type: names / docstrings / comments / narrative)
- Files touched
- Any `id-citation-discipline:ignore` markers added (for self-describing files)
- Whether salvage was performed (and into which archived SPECs)
- Regression-prevention layer chosen (hook-only / +CI / +git-pre-commit)

This summary is the handoff to the user confirming the project's source code is clean and staying clean.
