---
id: dec-452
draft_id: dec-draft-92a84d08
title: The skill frontmatter field set has one code source in the skill-crafting skill, and N03 derives from it
status: accepted
category: architectural
date: 2026-10-11
summary: "A new data-only module, skills/skill-crafting/scripts/frontmatter_contract.py, defines the accepted SKILL.md frontmatter keys by tier, the required keys, the name pattern and the length limits; the validator and the scaffold import it, the sentinel's N03 check loads it from its own plugin tree instead of keeping its own list, and a parity test pins the schema reference to it."
tags: [skill-crafting, validator, frontmatter, n03, single-source-of-truth, conformance]
made_by: agent
agent_type: systems-architect
branch: worktree-skill-crafting-refresh
pipeline_tier: standard
affected_files:
  - skills/skill-crafting/scripts/frontmatter_contract.py
  - skills/skill-crafting/scripts/validate.py
  - skills/skill-crafting/scripts/init_skill.py
  - scripts/check_artifact_conformance.py
  - skills/skill-crafting/references/schema.md
affected_reqs: [REQ-14, REQ-16, REQ-19, REQ-20]
supersedes:
superseded_by:
re_affirms:
re_affirmed_by:
dissent: "Three literal sets with a three-way parity test would add no file and no cross-tree load; the drift it allows is caught at test time either way."
---

## Context

The frontmatter keys a `SKILL.md` may carry are defined at three sites that had already diverged: the validator's `OPTIONAL_FIELDS` lacked nine keys Claude Code documents, while the schema reference and the sentinel's N03 key list (`_SKILL_FRONTMATTER_KEYS` in `scripts/check_artifact_conformance.py`, whose comment names the schema reference as its source) both lacked `background` and `disallowed-tools`. A skill could pass one Praxion check and fail another over the same key. The validator lives inside a shipped, packageable skill that must work standalone; N03 is a Praxion script the sentinel runs against any repository root.

## Decision

Add `skills/skill-crafting/scripts/frontmatter_contract.py`, stdlib-only and side-effect-free, holding `OPEN_STANDARD_FIELDS`, `CLAUDE_CODE_FIELDS`, `PRAXION_FIELDS` (pairwise disjoint), `REQUIRED_FIELDS`, `ACCEPTED_FIELDS` (their union), `NAME_PATTERN`, the length limits and a pure `name_errors(name)`. The validator and the scaffold import it as a sibling. N03 loads it with `importlib` from the plugin's own tree (`Path(__file__).resolve().parents[1]`), never from the inspected `--repo-root`; when it cannot load it, N03 is skipped with reason `contract-unavailable` and the path rather than reporting clean. The schema reference stays prose and is pinned to the module by a parity test using the acceptance driver's reading rule. The responsibility for the key list moves from N03 to the skill-crafting skill.

## Considered Options

### Three literal sets plus a three-way parity test

No new file and no cross-tree load. Every new field stays a three-site edit, and the sites are as far apart as a shipped skill and a Praxion-only script; the test catches drift only after someone has already made the partial edit.

### The validator module as the source, loaded by N03

No new file. N03 would execute a command-line module that is free to grow imports the ambient interpreter lacks, which is exactly the failure GL05 exists to catch, and N03 would know a CLI script's internals to read one constant.

### A data-only contract module (chosen)

One edit site per field, a dependency that points from a Praxion script toward the skill that owns the concept, and a module whose only job is the data N03 needs. Costs one file and one path-based load.

## Consequences

**Positive:** a key added to the module without its schema row, or the reverse, fails the suite; the validator and N03 cannot diverge because both read the module; the scaffold's duplicate name pattern goes away, so the precise consecutive-hyphen message has one author.

**Negative:** N03 now depends on a file in the skill tree; an install that ships `scripts/` without `skills/skill-crafting/` skips N03 (loudly). The agent-frontmatter key list in N03 keeps its separate literal source, out of scope here.

## Disconfirmation

- **Falsifier:** within two field additions after this lands, a key reaches the validator or N03 without the schema reference (or the reverse) and the suite stays green; or N03 is found skipped with `contract-unavailable` in a normal plugin install.
- **Steelmanned runner-up:** three literal sets plus a parity test. It keeps every site self-contained, adds no load path a reviewer must reason about, and drift is caught by the same test run. Its weakness is edit cost and distance, not correctness.
- **Reversal trigger:** the skill-crafting skill is split, renamed or distributed apart from `scripts/`, so the path load becomes fragile; then fall back to literal sets with a parity test.
