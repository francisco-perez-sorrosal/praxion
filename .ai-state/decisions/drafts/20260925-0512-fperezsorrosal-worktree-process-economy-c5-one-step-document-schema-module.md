---
id: dec-draft-7afa9ce3
title: One shared step-document schema module parses the Result line and step blocks for both the TEST_RESULTS shape gate and the pipeline reconciler
status: proposed
category: architectural
date: 2026-09-25
summary: "A new private stdlib-only sibling, scripts/_step_schema.py, owns the step-id grammar, the step-heading parse, the Result-line contract (Counts | NoRun | Malformed), the TEST_RESULTS step-block splitter and the WIP claim parser (checklist, status table, [x] heading); check_test_results_shape.py and reconcile_pipeline_state.py both import it instead of carrying parallel regexes that had already drifted (td-214). The contract it encodes: pass=0 is never green; preexisting= is additive and never affects status; 'Result: none' declares a no-run block; only step headings open a block."
tags: [process-economy, reconciler, test-results, schema, parse-dont-validate, pipeline-recovery]
made_by: agent
agent_type: systems-architect
branch: worktree-process-economy-c5
pipeline_tier: standard
affected_files:
  - scripts/_step_schema.py
  - scripts/check_test_results_shape.py
  - scripts/reconcile_pipeline_state.py
  - skills/software-planning/references/agent-pipeline-details.md
affected_reqs: []
dissent: "A new module and a cross-lane sequencing dependency to remove a drift that a cross-reader agreement test could also catch; the shared module may accrete reader-specific switches."
---

## Context

Two scripts read the same fixed-shape `Result: pass=<n> fail=<n> skip=<n>` line from
`TEST_RESULTS.md` (dec-386):

- the shape gate, `check_test_results_shape.py`, which bounds green sections for the verifier;
- the Tier-1 arbiter, `reconcile_pipeline_state.py` (dec-248), which decides whether a step's
  tests are red.

Each carried its own regexes, and they drifted. A rework fixed the reconciler's reading of an
all-zero line (`pass=0 fail=0` above a `### Failures` block) and left the gate's reading
unchanged. After that, a green shape-check no longer implied a green reconcile (td-214).

The same root cause shows up in both scripts: they key on document shape instead of on declared
structure.

- The gate treats every `## ` heading as a section, so a step organised into sub-headings
  reports one false `missing-result-line` per sub-heading: 29 on one real pipeline file (td-236).
- Neither script parses the `preexisting=` token that writers already use to record baseline
  failures.
- The reconciler reads any count-less `Result:` line as green.

Step identity has the same problem. It is encoded by four regexes in three shapes, none of
which recognises a letter-suffixed step id (`Step 1b`) that plans routinely use.

## Decision

Add one private sibling module, `scripts/_step_schema.py`. It is pure, does no I/O, is
stdlib-only, and sits in the underscore-prefixed family alongside `_handoff_inputs.py` and
`_repo_root.py`. It owns the grammar that more than one reader needs:

- **Step identity.** `STEP_ID` is `<digits><optional lowercase letter>`, with
  `step_id_from_heading` and `step_sort_key` alongside it.
- **The Result-line contract.** `parse_result_line(line)` returns a sum type
  `Counts | NoRun | Malformed`, or `None` for a line that is not a `Result:` line. `Counts.status`
  is derived and is red when `fail>0`, when `error>0`, or when `pass=0`.
  - `preexisting=` is parsed but never read by `status`. `fail=` counts failures outside the
    test baseline; `preexisting=` counts baseline failures still red.
  - `Result: none` is a declared no-run block.
  - A missing `pass=` or `fail=`, or a repeated known key, makes the line `Malformed`, and a
    `Malformed` line gives no evidence.
- **The step-block model.** `split_step_blocks(text)` opens a block only at a step heading.
  Every other heading belongs to the enclosing block. A file with no step heading becomes one
  block.

Both readers import these functions. Policy stays with each reader:

- the gate keeps its byte ceiling and finding kinds, and adds `no-run-over-ceiling`;
- the reconciler keeps `Files:` parsing, attribution and the arbitration of claims and test statuses against git. When it reached its size ceiling, two pure readings of a step document moved into the module by cohesion: the WIP claim parser (checklist, status table, `[x]` heading) and the per-step test-evidence reader (which recorded run speaks for a step). The charter is "what a step document declares, read without git or a filesystem"; a switch only one reader needs stays in that reader.

## Considered Options

### Option 1 — shared private sibling module (chosen)

- **Pro:** the two readers cannot disagree on a line, by construction.
- **Pro:** one grammar for step identity across the plan, the WIP and TEST_RESULTS.
- **Pro:** the gate stays free to change its policy without touching the arbiter.
- **Con:** one more file.
- **Con:** Lane B's grammar-dependent work is sequenced after the module lands.

### Option 2 — reconciler imports from the shape gate

- **Pro:** no new file; the gate is already the "shape" authority.
- **Con:** the Tier-1 arbiter would depend on a gate module that changes for gate reasons
  (ceiling, finding kinds, CLI). That is high integration strength across a large distance.

### Option 3 — keep two parsers, add a cross-reader agreement test

- **Pro:** zero structural change; drift becomes a red test.
- **Con:** it detects drift after the fact rather than removing it. The corpus must anticipate
  every line shape, and td-214 shows the kind of line a corpus misses. Two copies of one
  contract still need two edits per contract change.

## Consequences

- **Positive.** td-214 closes by construction. td-236(a) and td-236(b) get a declared token and
  a declared block model. The reconciler's latent "count-less `Result:` line reads green" bug
  disappears with the old regex.
- **Positive.** A letter-suffixed step id is recognised everywhere at once.
- **Neutral.** The module needs no id-citation exemption: its few step-shaped fixture literals
  carry the same-line escape, so the gate keeps guarding criterion ids there. (An exemption was
  tried and reverted after it let criterion ids through within one change.)
- **Negative.** Both topology groups (`state-ledgers`, `repo-gates`) must list the module in
  `file_dependencies`.

## Disconfirmation

- **Falsifier.** Either of these would show the decision is wrong:
  - the two readers turn out to need different parses of the same line, for example a gate that
    wants strictness the arbiter must not have;
  - the module grows caller-specific flags that change parsing per reader.
- **Steelmanned runner-up.** Option 3 keeps each script self-contained and readable in one file,
  with no import to follow. A table-driven agreement test over the real harvested lines is cheap,
  and it would have caught td-214's shape. For a contract this small (five keys and one keyword),
  a reader might reasonably prefer seeing the regex inline.
- **Reversal trigger.** Revisit and consider splitting per reader when either of these happens:
  - a change to `_step_schema.py` is made for one reader and has to be guarded against the other;
  - a third reader appears whose needs diverge.
