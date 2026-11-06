---
id: dec-draft-f371452e
title: "The writer roles' kits run under dec-487's confinement; two named scripts get their executable bit"
status: proposed
category: configuration
date: 2026-11-06
summary: "The test-engineer and the systems-architect join CONFINED_ROLES with their own prescribed commands, under the unchanged dec-487 contract; check_design_checkpoint.py and query_adrs.py become 100755 so a bare-name call resolves to the plugin copy."
tags: [eval, adherence, sandbox, permissions, test-engineer, systems-architect]
made_by: agent
agent_type: systems-architect
branch: lean-writers
pipeline_tier: full
affected_files:
  - eval/src/praxion_evals/adherence/confinement.py
  - scripts/check_design_checkpoint.py
  - scripts/query_adrs.py
---

## Context

Both writer roles' definitions prescribe shell work: the test-engineer's test runner, formatter, linter and mutation sensor, and the architect's spec, footprint, design-checkpoint and ADR-query scripts, git identity and branch reads, and the id hash. Under the read-only grant every one of these is refused in both arms. In a materialized task sandbox, the plugin copy's `scripts/` is first on `PATH` and the copy keeps git file modes. `check_design_checkpoint.py` and `query_adrs.py` are the only named scripts committed `100644`, so neither resolves by bare name; every other bare-name prescribed script is `100755`.

## Decision

- `CONFINED_ROLES` gains `test-engineer` and `systems-architect`. The confinement builder, the settings, the dry-run places, the program order, the no-cost settings check and the fixture-git setting all follow from that one set, under `dec-487`'s contract unchanged.
- `PRESCRIBED_COMMANDS` gains each role's set:
  - test-engineer: `pytest`, `py.test`, `ruff`, `mutation_sensor.py` and the git reads;
  - architect: the four named scripts, the git reads, `git config` and `git rev-parse`.
- Both scripts become `100755` at the source.

## Considered Options

- **Join the existing contract and fix the modes at the source (chosen).**
- **A writer-specific grant.** Rejected: a second contract to keep in step with the first.
- **Set execute bits in the eval's plugin copy.** Rejected: the measured copy would differ from what ships, and real installs would keep the defect.

## Consequences

- Two more roles run sandbox-bounded shell commands in both arms.
- The two scripts are directly executable wherever the plugin's scripts directory is on `PATH`.
- Neither script's content changes, and no agent definition, rule, kernel or hook registration changes.
