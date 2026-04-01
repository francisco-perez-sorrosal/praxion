# Spec Health (SH) -- Sentinel Check Catalog

Defines the Spec Health dimension for the sentinel's check catalog. These checks apply only to persistent specs archived in `.ai-state/specs/`.

## Scope

- **Run** when `.ai-state/specs/` exists and contains at least one `SPEC_*.md` file
- **Skip** when no specs directory or no spec files exist. Log "Spec Health: skipped (no specs found)" in the report
- This dimension does NOT apply to ephemeral `.ai-work/<task-slug>/` documents -- only to archived persistent specs

When multiple spec files exist, the sentinel samples a representative subset consistent with its existing sampling approach for large artifact sets.

## Check Catalog

| ID | Tp | Rule | Pass |
|----|----|------|------|
| SH01 | A | Persistent specs reference files that exist | All file paths in specs resolve |
| SH02 | A | Persistent specs have traceability matrices | `## Traceability` section present and non-empty |
| SH03 | L | Spec requirements still reflected in code | Key behavioral claims match current implementation |
| SH04 | L | Traceability matrix has no UNTESTED entries | All requirements have at least one test |
| SH05 | L | Key Decisions section is substantive | Decisions include what, why, alternatives |
| SH06 | L | Spec delta claims match actual spec evolution | Added/modified/removed requirements in delta consistent with differences between prior and current archived specs |

## Check Evaluation Details

### SH01 -- File Path Resolution (Auto)

Extract all file paths referenced in `Implementation` column cells of the traceability matrix and any paths in the Requirements section. Resolve each path relative to the project root. A path that does not resolve to an existing file is a FAIL.

**Common failures**: renamed or deleted source files after spec archival, paths using old module structure after a refactoring.

### SH02 -- Traceability Matrix Presence (Auto)

Grep each `SPEC_*.md` for a `## Traceability` heading. The section must contain at least one table row beyond the header. An empty section or missing heading is a FAIL.

**Common failures**: spec archived before the verifier produced the traceability matrix, manual spec creation that omitted the section.

### SH03 -- Spec-Code Alignment (LLM)

For each requirement (`REQ-NN`) in the spec, read the referenced implementation location and assess whether the behavioral claim still holds. A requirement states the system does X; the code should still do X. Exact implementation details may change -- the check targets behavioral intent, not code structure.

**Evaluation**: read the requirement's `the system` clause, then read the referenced source location. If the behavior described is still present (even if refactored), PASS. If the source location no longer exists or the behavior has clearly changed, FAIL. When evidence is ambiguous, WARN and flag for human review.

**Common failures**: feature behavior changed without updating the archived spec, referenced function extracted to a different module.

### SH04 -- Traceability Coverage (LLM)

For each requirement in the traceability matrix, check that the `Test(s)` column references at least one test and that the `Status` column is not `UNTESTED`. Search test files for the referenced test names to confirm they exist.

**Evaluation**: every row with a non-empty `Test(s)` cell that references an existing test is PASS. A row with `UNTESTED` status or a test reference that no longer exists is FAIL.

**Common failures**: tests deleted during refactoring, test renamed without updating the archived spec.

### SH05 -- Decision Quality (LLM)

Read the `## Key Decisions` section. Each decision entry should include: what was decided, why (rationale), and what alternatives were considered. A decision that states only what was chosen without rationale or alternatives is insufficient.

**Evaluation**: decisions with all three elements (what, why, alternatives) are PASS. Decisions missing rationale or alternatives are WARN. A section with no decisions or only single-sentence entries is FAIL.

**Common failures**: decisions copied from LEARNINGS.md without the structured format, rushed archival that omitted rationale.

### SH06 -- Delta-Spec Consistency (LLM)

When a current archived spec was produced by a pipeline that included a `SPEC_DELTA.md`, compare the delta's claims against the actual differences between the prior and current archived specs. The delta stated that certain requirements were added, modified, or removed — the archived specs should reflect those changes.

**Evaluation**: for each delta section (Added/Modified/Removed), verify:
- **Added**: requirements listed as added in the delta should appear in the current spec but not the prior spec
- **Modified**: requirements listed as modified should show behavioral differences between prior and current specs consistent with the delta's before/after description
- **Removed**: requirements listed as removed in the delta should appear in the prior spec but not the current spec

If all delta claims are consistent with actual spec evolution, PASS. If a claim contradicts the evidence (e.g., delta says REQ was removed but it still appears in the current spec), FAIL. When behavioral comparison is ambiguous (requirement rephrased but intent unclear), WARN.

**Common failures**: delta produced from stale baseline (prior spec's behavior had already drifted from code), delta claims not updated after plan amendments changed scope, rushed archival that preserved the delta but modified the spec differently.

## Integration with Sentinel Methodology

**Pass 1 (Auto checks)**: SH01 and SH02 run alongside other A-type checks during the sentinel's automated pass. These are filesystem-level checks using Glob and Grep.

**Pass 2 (LLM judgment)**: SH03, SH04, SH05, and SH06 run as **Batch 5 -- Spec Health** (conditional). The sentinel loads this reference file on demand when `.ai-state/specs/` contains spec files. This batch follows the existing Batch 4 (Pipeline Discipline). SH06 is further conditioned on the current spec having a predecessor — skip SH06 when the spec is the first archived spec for its feature.

The sentinel's standard scoring applies: per-spec grades contribute to the ecosystem health grade. Spec health findings use the same severity tiers (Critical/Important/Suggested) as other dimensions.
