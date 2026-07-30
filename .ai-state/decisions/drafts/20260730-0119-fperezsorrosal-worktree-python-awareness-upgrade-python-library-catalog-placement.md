---
id: dec-draft-6419af7d
title: "Python essential-library catalog: per-archetype files, architect-owned selection"
status: proposed
category: architectural
date: 2026-07-30
summary: >-
  Curated battle-tested Python library catalog lives as per-archetype reference files
  inside the python-development skill; systems-architect owns library selection,
  implementation-planner only cross-references it.
tags: [python, skills, library-catalog, agent-coordination, systems-architect, implementation-planner, staleness-policy]
made_by: agent
agent_type: orchestrator
branch: worktree-python-awareness-upgrade
pipeline_tier: standard
affected_files:
  - skills/python-development/SKILL.md
  - skills/python-development/README.md
  - skills/python-development/references/essential-libraries.md
  - skills/python-development/references/libraries-web-api.md
  - skills/python-development/references/libraries-cli.md
  - skills/python-development/references/libraries-data-ml.md
  - skills/python-development/references/libraries-async.md
  - skills/python-development/references/libraries-general.md
  - skills/python-development/references/libraries-scripting.md
  - agents/systems-architect.md
  - agents/implementation-planner.md
dissent: >-
  A separate `python-libraries` skill would have let library-catalog freshness decay
  independently of python-development's syntax/tooling guidance, and would have been
  discoverable via its own activation trigger instead of only through python-development's
  progressive disclosure.
---

## Context

Praxion's `python-development` skill taught type hints, testing, and pattern choices
(dataclasses vs Pydantic) but had no curated list of recommended third-party libraries, and
"Python Version Guidelines" was a 10-line stub ("target 3.13+") with no per-version idiom
detail. Separately, `systems-architect` and `implementation-planner` already had a "library
version and capability verification" step — but it only *verifies* a library already named;
neither agent had anything to help *select* one in the first place. The user asked for both
gaps closed, plus applicability to already-existing Praxion-managed projects (an architect
or planner recommending a library mid-project, not just at greenfield init), while
explicitly scoping out retrofitting Praxion's own Python source in this pass.

Two research passes (external: current CPython idiom landscape + library landscape by
project archetype; internal: Praxion's own skill/agent gaps and policy fit) preceded this
decision — see `.ai-work/python-awareness-upgrade/RESEARCH_FINDINGS_external.md` and
`RESEARCH_FINDINGS_internal.md` for full detail.

## Decision

1. **Placement**: the catalog lives inside the existing `python-development` skill as an
   index reference file (`references/essential-libraries.md`) plus six per-archetype files
   (`references/libraries-{web-api,cli,data-ml,async,general,scripting}.md`), not as a
   separate skill and not as a single monolithic file.
2. **Staleness tracking**: the whole catalog is tracked as one freshness unit via a single
   heading ("Library Catalog by Archetype") in the index file, registered in
   `python-development`'s `staleness_sensitive_sections:` frontmatter alongside the existing
   "Python Version Guidelines" entry. The skill's `staleness_threshold_days` is set to 90
   (down from the global default of 120) since both sections track fast-moving ecosystem
   state.
3. **Version-idiom guidance**: expanded in place inside `SKILL.md`'s existing "Python
   Version Guidelines" section (reusing its existing marker) as a compact per-version table,
   framing free-threading/JIT as a deployment concern rather than a coding idiom.
4. **Pipeline wiring**: `systems-architect.md` gets a new paragraph, placed immediately
   after its existing "Library version and capability verification" paragraph, directing it
   to consult the catalog before naming a candidate library — explicitly including
   brownfield/existing-codebase recommendations, not just greenfield selection.
   `implementation-planner.md` gets a lighter cross-reference appended to its equivalent
   step: if a step's own logic would reinvent something the catalog covers, raise the
   substitution to the architect rather than decomposing around it. The planner does not
   get a duplicate full paragraph — it verifies, the architect selects.

## Considered Options

### Option A (chosen): per-archetype files inside `python-development`

Six small archetype files plus an index, all under the skill's existing `references/`
directory, no new skill.

**Pros**: keeps the catalog discoverable through the skill agents already load for Python
work; per-archetype files stay small and load only when relevant (progressive disclosure);
no new skill-activation surface to maintain; consistent with `references/` already holding
`patterns-and-examples.md`/`testing-and-tooling.md`.

**Cons**: seven new files in one skill's `references/` directory is a meaningfully larger
surface than the two that existed before; the catalog's staleness cadence is now coupled to
whatever cadence the skill's other sections use (mitigated by the 90-day threshold override
applying skill-wide, not just to the catalog).

### Option B: single monolithic `essential-libraries.md`

One file with all six archetypes as sections.

**Pros**: fewer files, simpler to scan end-to-end.

**Cons**: rejected per explicit user redirect during the design checkpoint — loads the
entire catalog into context even when only one archetype is relevant, working against the
skill's own progressive-disclosure convention.

### Option C: separate `python-libraries` skill

A new top-level skill dedicated to library curation.

**Pros**: independent activation trigger; staleness cadence fully decoupled from
`python-development`'s syntax/tooling content; would scale cleanly if the catalog later
grows to cover more ecosystems.

**Cons**: fragments a single mental model ("how do I write Python here") across two skills
a user/agent must know to consult; the coordination-protocol pointer sites
(`systems-architect.md`, `implementation-planner.md`) would need to name a second skill
alongside `python-development`; not clearly justified at the current catalog size (6
archetypes, ~30 total library entries). Rejected as premature abstraction — Option A can
still evolve toward a standalone skill later if the catalog's scope outgrows
`python-development`.

## Consequences

**Positive**: `systems-architect` now has a concrete, vetted shortlist to reach for instead
of relying solely on training-data recall when naming a Python dependency, closing the gap
the user identified; the same shortlist is explicitly usable on already-existing
Praxion-managed projects, not just new ones; version-idiom guidance is now
version-differentiated instead of a flat "target 3.13+" statement.

**Negative**: the catalog is a snapshot of the Python ecosystem as of 2026-07-29/30 and will
decay — the 90-day threshold override is a mitigation, not a guarantee; `/refresh-skill
python-development` still requires a human or scheduled trigger to actually run.

## Disconfirmation

- **Falsifier**: if `python-development`'s `references/` directory grows substantially
  further (e.g. additional catalogs for other languages' equivalents get added by analogy,
  or the library catalog itself needs sub-splitting per archetype beyond six files), the
  "keep it inside one skill" premise weakens and Option C (standalone skill) becomes the
  better fit.
- **Steelmanned runner-up**: Option C (separate `python-libraries` skill) is the strongest
  alternative — it would let library-catalog freshness decay on its own cadence entirely
  independent of `python-development`'s syntax/tooling content, and would be independently
  discoverable rather than nested behind another skill's progressive disclosure. It was not
  chosen because the catalog's current size doesn't yet justify a second skill's activation
  and maintenance surface, and coupling the freshness cadence via `staleness_threshold_days`
  achieves most of the same benefit without the split.
- **Reversal trigger**: if a future sentinel pass or `/refresh-skill` run finds the catalog
  and the syntax/tooling content need meaningfully different verification cadences in
  practice (not just in theory), or if the catalog's archetype count grows past roughly
  double its current size, revisit toward Option C.
