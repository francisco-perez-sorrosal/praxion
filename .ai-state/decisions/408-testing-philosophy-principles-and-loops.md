---
id: dec-408
draft_id: dec-draft-057153ec
title: Testing philosophy — ten principles, scope × size axes, outer/inner-loop ownership, five feedback loops
status: accepted
category: behavioral
date: 2026-09-28
summary: "testing-strategy opens with ten ordered principles. Scope and size are separate axes. Tests beyond the unit level belong to the outer loop and are read-only for the implementer. Five named loops (inner, phase, integration, pre-merge, scheduled) each have one defined test set. Coverage is a periodic measurement whose CI floor is a ratchet, not a target."
tags: [testing, philosophy, test-suite-refresh, coverage, feedback-loops, ownership, parallelism]
made_by: agent
agent_type: systems-architect
branch: worktree-test-refresh-core
pipeline_tier: full
affected_files:
  - skills/testing-strategy/SKILL.md
  - rules/swe/testing-conventions.md
  - skills/test-coverage/references/python.md
  - skills/python-development/references/testing-and-tooling.md
  - pyproject.toml
affected_reqs: [REQ-01, REQ-02, REQ-03, REQ-14, REQ-15]
---

## Context

Praxion's testing guidance described selection in great detail and organization hardly at all. The selection side was a 32.7 KB trunk, a 58 KB topology instance, a 29 KB resolver and about 11 KB of agent prose. The organization side was a few paragraphs. The guidance also contradicted itself:

- **Coverage gates.** The skill said "do not set coverage targets as gates", while CI enforces `--cov-fail-under=80`.
- **Coverage runs.** The test-coverage skill says coverage is never regenerated as a side effect, yet the default it ships to managed projects puts `--cov` in `addopts`.
- **`addopts`.** Three different `addopts` values were recommended.
- **Test layout.** The testing-conventions rule required a mirrored layout. `gate-canaries.md`, and Praxion's own corpus, co-locate tests.
- **Markers.** The rule required a marker on integration tests; the corpus has zero uses.

dec-405 made Praxion's own suite parallel by default and moved coverage out of the default run, but the doctrine never caught up. The user approved the ten principles and the two axes in the test-suite-refresh proposal. This record captures them as the policy the other testing artifacts must conform to.

## Decision

1. **The ten principles, in order.** They open `skills/testing-strategy/SKILL.md`:
   1. Every feedback loop has a latency budget.
   2. Make the whole suite cheap before making it selective.
   3. Parallel safety is a property of every test, enforced by running in parallel.
   4. Selection is derived from the code, never hand-kept, and anything unmapped widens the run.
   5. Scope and size are separate axes: scope says who designs a test, size says when it runs.
   6. Beyond the unit level, tests are designed independently of the design; the implementer runs outer-loop tests and never edits them.
   7. Structure communicates, tooling computes.
   8. Measurement is periodic, not a side effect, and a coverage floor is a ratchet, not a target.
   9. Flakiness is a defect with an owner: no local retries, CI reruns only to classify, and a ledger row.
   10. Test output is an interface for agents: failures first, bounded, no noise.
2. **Organization.**
   - **Scope axis:**
     - Unit and internal integration: owned by the implementer, following the inner-loop layout convention.
     - Boundary integration, acceptance: owned by the test-engineer in acceptance mode, in `tests/acceptance/`.
     - End-to-end: owned by the test-engineer in acceptance mode, in `tests/e2e/`.
   - **Size axis:**
     - small: in-process.
     - medium: subprocess, local files, git, localhost.
     - large: live external services. `large` is the only required marker and is deselected by default.
   - **Inner-loop layout** follows the project's declared convention, co-located or mirrored, stated in its `## Testing` CLAUDE.md block. The resolver derives selection under either convention.
3. **Ownership.** The outer-loop directories are read-only for the implementer. This record states the principle and the layout only. The acceptance-design mechanics belong to the follow-up pipeline.
4. **The five loops.**

   | Loop | What runs |
   |---|---|
   | Inner | Derived selection |
   | Phase checkpoint | Selection over the pipeline-base diff |
   | Integration checkpoint | Full suite, per dec-084 |
   | Pre-merge CI | Full suite with coverage and the 80% ratchet floor |
   | Scheduled | `large` tests, the selection audit, flaky classification, slow-test report |

5. **Coverage.**
   - It is a periodic measurement taken in CI and by the canonical coverage target (dec-067's dispatcher, kept).
   - No shipped `addopts` carries `--cov`.
   - The floor records the level already reached. It never drops, and tests are not written to hit it.
6. **Debug escape.** To debug a single test, use `-n 0`. `-p no:xdist` fails when `addopts` carries `-n`. This corrects the escape dec-405 documented.

## Considered Options

### Keep the pyramid-only framing and patch the contradictions one by one

- Pro: fewer edits.
- Con: every new artifact would repeat the same contradictions. With no ordered principles there is nothing to decide conflicts against.

### A single "level" axis (unit / integration / e2e) with markers

- Pro: it is familiar.
- Con: it mixes who designs a test with when it runs, which is why the integration-marker rule never took hold. Google separates size from scope for the same reason. A marker kept by hand drifts without anyone noticing.

### Ten principles plus two separate axes (chosen)

- Pro: each artifact conflict is settled by pointing to a principle.
- Pro: scope drives ownership and size drives scheduling, with no manual tagging beyond `large`.

## Consequences

- Positive:
    - A single doctrine that the rule, the references, the coverage skill and the agent prompts all conform to.
    - Managed projects no longer inherit coverage in their inner loop.
- Negative:
    - Principle 6 names an owner mode (test-engineer, acceptance mode) that does not exist until the follow-up pipeline ships. Until then the outer-loop directories hold only READMEs.
    - Changing the skill body means managed projects re-learn the layout rule. The mirrored layout remains legal as a declared convention.
- Coverage floor: Praxion keeps 80 in CI as a ratchet. The shipped template fills the floor at onboarding:
    - `new` projects get 80;
    - `existing` projects get their measured coverage, rounded down;
    - with no measurement, the floor is 0 and onboarding prints a ratchet instruction.
