# Spec-Driven Development Skill

Behavioral specification methodology with requirement traceability for medium and large features. Provides spec format, complexity triage, REQ ID conventions, traceability threading, decision documentation, and spec archival.

## When to Use

- Medium or large features that need behavioral specifications with requirement IDs
- Threading requirement traceability through architecture, planning, testing, and verification
- Archiving completed specs to `.ai-state/specs/` for future reference
- Reviewing behavioral changes in brownfield features against prior archived specs (spec deltas)
- Understanding complexity triage (trivial through spike) to decide spec depth

For trivial, small, or spike tasks, skip this skill entirely.

## Activation

Load explicitly with `spec-driven-development` or reference behavioral specifications, REQ IDs, or requirement traceability. Composes with `software-planning` -- the planner loads both for medium/large features.

## Skill Contents

| File | Purpose |
|------|---------|
| `SKILL.md` | Core skill: complexity triage, spec format, REQ ID conventions, traceability threading, decision documentation, spec archival, spec delta format |
| `README.md` | This file -- overview and usage guide |
| `references/spec-format-guide.md` | Full spec format examples, EARS/GWT comparison, traceability matrix template, persistent spec template, spec delta template |
| `references/sentinel-spec-checks.md` | Spec Health dimension checks for the sentinel agent |

## Quick Start

1. **Assess complexity**: use the 5-tier triage table to determine spec depth
2. **Write specs** (medium/large): use the `When/and/the system/so that` format with REQ IDs
3. **Diff specs** (brownfield): the architect produces `SPEC_DELTA.md` showing added/modified/removed requirements vs prior archived specs
4. **Thread IDs**: the implementation-planner threads REQ IDs into test steps
5. **Name tests**: prefix test names with `req{NN}_` for traceability
6. **Verify**: the verifier produces a traceability matrix linking requirements to tests
7. **Archive**: the planner archives the spec to `.ai-state/specs/` at end-of-feature

## Related Skills

- [`software-planning`](../software-planning/) -- three-document planning model; SDD composes as a peer methodology
- [`code-review`](../code-review/) -- the verifier uses code-review for convention checks alongside spec conformance
