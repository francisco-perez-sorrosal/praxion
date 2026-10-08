---
id: dec-draft-304df110
title: The mutation line and tag grammar moves from scripts/_step_schema.py into the leaf scripts/_mutation_grammar.py, re-exported unchanged
status: proposed
category: architectural
date: 2026-10-07
summary: scripts/_step_schema.py (821 lines, over the 800 ceiling) is split by cohesion — the one-line grammar of the mutation contract (the MutationReading sum type, parse and render of the Mutation line, DECLARED_LIMIT_REASONS, mutation_block_reason, parse_mutation_tag) moves to a new stdlib leaf scripts/_mutation_grammar.py that imports nothing local; _step_schema keeps document structure (step grammar, block splitter, WIP claims, recorded runs, which step a mutation line or tag belongs to) and re-exports every moved name, so no importer or test changes.
tags: [step-schema, mutation-sensor, module-size, refactoring, re-export, cohesion]
made_by: agent
agent_type: systems-architect
branch: worktree-step-loop-dogfood
pipeline_tier: full
affected_files:
  - scripts/_step_schema.py
  - scripts/_mutation_grammar.py
affected_reqs: []
supersedes_in_part: [dec-421]
dissent: []
---

## Context

`scripts/_step_schema.py` is 821 lines, over the repository's 800-line hard ceiling (tracked as td-343). It holds four clusters:

- the step-document grammar (step ids, step headings, `Result:` lines, the block splitter);
- the WIP claim reader;
- per-step recorded runs;
- the mutation contract: the `Mutation:` line the sensor prints and the `mutation:` tag the planner writes.

Thirteen modules import it, among them the reconciler, the shape checker, the mutation sensor, the ledger and five driver modules. Its tests reach names through the module object, so every name must stay reachable as `_step_schema.<name>`, or tests would need editing. The pipeline forbids that edit. That forces any split to put a **leaf below** `_step_schema` that it re-exports. A module above it would make an import cycle.

**Activation:** no. A behaviour-preserving size split with one candidate cut that keeps the dependency graph acyclic.

## Decision

1. New `scripts/_mutation_grammar.py`. It is stdlib only, keeps the 3.9 floor and imports no local module. It holds:
   - `MutationRan`, `MutationRefused` and `MutationMalformed`, with the `MutationReading` alias;
   - `DECLARED_LIMIT_REASONS`;
   - `parse_mutation_line` and `render_mutation_line`, with their private helpers;
   - `mutation_block_reason`;
   - `parse_mutation_tag`, with its three regexes;
   - the last-reading helper over a block's lines.

   Its charter: the grammar of **one line** of the mutation contract, and the one policy over one reading.
2. `_step_schema.py` keeps **document structure**:
   - the step grammar, `StepBlock` and `split_step_blocks`;
   - the WIP claim reader and recorded runs;
   - `step_mutation_reading`, `mutation_tagged_steps` and `mutation_block_reasons`, which decide which step a line or tag belongs to.

   It imports from the leaf and re-exports every moved name in the explicit re-export form.
3. No importer and no test is edited. A new unit test asserts that every public name the module exported at the pipeline base is still reachable from `_step_schema` and is the same object as the leaf's.

## Considered Options

### Option 1 — The mutation-line leaf (chosen)
- **Pros:** a clean cohesion boundary (line grammar against document structure); the dependency graph `_step_schema → _mutation_grammar` is acyclic; about 180 lines move, leaving about 150 lines of headroom; the sensor, the producer of the line, needs only the leaf.
- **Cons:** two import paths for one name, through the facade or the leaf.

### Option 2 — The results-file reader apart from the plan and WIP reader (the ledger row's suggestion)
- **Pros:** splits by document.
- **Cons:** both halves need the step-id and heading primitives. Keeping the facade then forces a third module for the primitives (three or four modules instead of two), or a cycle, for the same size relief.

### Option 3 — The WIP claim reader as a leaf
- **Cons:** it needs the step-id grammar and the heading parse, which are `_step_schema`'s core. A leaf would either duplicate them or import its own parent.

## Consequences

**Positive:** the module is back under the ceiling with room for the goal mode's additions; every reader behaves exactly as at base; the sensor's wire format has a home of its own.

**Negative:** a re-export facade that a reader of `_step_schema` must follow to find the moved definitions; the facade's docstring says so.

## Disconfirmation

- **Falsifier:** any existing reconciler, shape-check, mutation-sensor, step-schema or driver suite needs an edit to pass; or `_step_schema.py` passes 800 lines again within the next two pipelines.
- **Steelmanned runner-up:** Option 2 is the cut the debt row named and the one a reader of the documents would expect, the results file against the plan. Its third primitives module would also give the goal mode's progress-record parser an obvious home.
- **Reversal trigger:** if a later change needs the results-file reader without the WIP reader (for example, a process that must not load WIP parsing), take Option 2 with a primitives leaf.

## Prior Decision

dec-421 is narrowed in one clause: "Grammar owner: `scripts/_step_schema.py`". The `Mutation:` line grammar, its reading sum type, the declared-limit set and the block-reason policy are now defined in `scripts/_mutation_grammar.py` and re-exported by `_step_schema.py`, so every reader still reaches them there. Everything else in dec-421 stands unchanged: the reconciler as the enforcement point, the `blocked` verdict, the readers' behaviour, the unchanged shape checker, and `step_mutation_reading`, which stays in `_step_schema.py`. dec-393 (one step-document schema module) is untouched: its listed contents all stay in `_step_schema.py`.
