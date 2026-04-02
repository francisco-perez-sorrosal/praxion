# ADR Authoring Protocols

Procedural protocols for creating and maintaining Architecture Decision Records in `.ai-state/decisions/`. Reference material for the [Software Planning](../SKILL.md) skill. For the file format, frontmatter schema, and naming conventions, see the [adr-conventions rule](../../../rules/swe/adr-conventions.md).

## ADR Creation Protocol

Decision-making agents (systems-architect, implementation-planner) create ADR files whenever they document a decision in `LEARNINGS.md ### Decisions Made`:

1. **Scan** `.ai-state/decisions/` for the highest existing `NNN` in filenames
2. **Create** the ADR file at `.ai-state/decisions/<NNN+1>-<slug>.md` using the Write tool, following the format from the `adr-conventions` rule (YAML frontmatter + MADR body sections)
3. **Record** the same decision in `LEARNINGS.md ### Decisions Made` using the structured format
4. **Regenerate index** by running `python scripts/regenerate_adr_index.py` or writing `DECISIONS_INDEX.md` directly

The human-readable LEARNINGS.md entry and the persistent ADR file coexist -- LEARNINGS.md is the ephemeral authoring surface, the ADR file is the permanent record.

## Who Creates ADRs

Not all agents create ADR files. The division follows decision-making authority:

| Agent | Creates ADRs | Records in LEARNINGS.md |
|-------|-------------|------------------------|
| systems-architect | Yes | Yes |
| implementation-planner | Yes | Yes |
| implementer | No | Yes |
| test-engineer | No | Yes |
| verifier | No | Yes |
| sentinel | No | N/A |

Implementers and test-engineers record decisions in LEARNINGS.md only. The planner or architect persists significant decisions as ADR files.

## Supersession Protocol

When a new decision replaces a prior one:

1. Set `supersedes: dec-NNN` in the **new** ADR frontmatter
2. Set `superseded_by: dec-MMM` in the **old** ADR frontmatter (using the Edit tool)
3. Change the old ADR status to `superseded`
4. Add a `## Prior Decision` section in the new ADR body explaining what changed and why
5. Regenerate `DECISIONS_INDEX.md`

## Index Regeneration

After creating or modifying ADR files, regenerate the index to keep it consistent:

```bash
python scripts/regenerate_adr_index.py
```

The script reads all `.ai-state/decisions/[0-9]*.md` files, parses YAML frontmatter, and writes `.ai-state/decisions/DECISIONS_INDEX.md` as a markdown table. It handles zero ADR files gracefully (empty table).

Alternatively, agents can write the index directly using the Write tool if the script is unavailable.

## Spec Archival Cross-Reference

During end-of-feature spec archival, the implementation-planner cross-references decisions from `LEARNINGS.md ### Decisions Made` with ADR files in `.ai-state/decisions/`. The archived spec's `## Key Decisions` section should link to relevant ADR files for full context.

## End-of-Feature Decision Verification

During the end-of-feature workflow, verify consistency between:

- Decisions in `LEARNINGS.md ### Decisions Made`
- ADR files in `.ai-state/decisions/` covering the feature period

Check for decisions recorded in LEARNINGS.md but missing as ADR files (may indicate the creation protocol was not followed), and ADR files without corresponding LEARNINGS.md entries (unusual but not necessarily an error).
