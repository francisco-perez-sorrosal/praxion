---
description: >
  Create or refresh the project's test-group topology for scoped test execution.
  Run with --init to scaffold a new topology from DESIGN.md §3 Built components
  (spawns systems-architect + test-engineer), or without flags to reconcile drift
  in an existing topology (spawns implementation-planner). Use when setting up
  test segregation for the first time, when topology groups need refresh after
  architecture changes, or when the sentinel or systems-architect flags topology
  readiness. Activation terms: topology, test groups, segregation, refresh, init.
argument-hint: [--init]
allowed-tools: [Read, Glob, Grep, Task, AskUserQuestion]
---

Create or refresh the project's test-group topology. Determine the mode from `$ARGUMENTS`:

- **`--init`** — first-time topology creation
- *(no flag)* — drift-response refresh of an existing topology

---

## Mode: `--init` — First-Time Topology Creation

### Precondition Check

Read `.ai-state/DESIGN.md` §3 (Components) and count Built components.

If `.ai-state/DESIGN.md` is absent or §3 has fewer Built components than the structural-feasibility threshold defined in `skills/testing-strategy/references/test-topology.md` §"Growth-Trigger Policy", **decline gracefully**:

> "Cannot scaffold a topology: the project does not yet have enough distinct Built components in `.ai-state/DESIGN.md` §3. With fewer components than the structural-feasibility threshold, topology groups would recapitulate the whole project rather than map to real architectural subsystems — a topology anti-pattern. To proceed, first establish an architecture baseline by running `/onboard-project` (Phase 8) or the `/new-project` seed pipeline, then re-run `/refresh-topology --init` once the component model is populated."

If `.ai-state/TEST_TOPOLOGY.md` already exists, confirm with the user before overwriting — a topology already exists. They may want `/refresh-topology` (no flag) instead.

### Spawn Agents

When the precondition passes, spawn in sequence:

1. **`systems-architect`** — creates the `## Subsystems` cross-reference table in `.ai-state/TEST_TOPOLOGY.md` from the Built components in `.ai-state/DESIGN.md` §3. Prompt: "Create `.ai-state/TEST_TOPOLOGY.md` and populate its `## Subsystems` table from `.ai-state/DESIGN.md` §3 Built components. Each subsystem row maps a component name to its logical test group. You own this section; do not author the per-group YAML blocks (test-engineer-owned) or `integration_boundaries` (planner-owned, populated lazily). See `skills/testing-strategy/references/test-topology.md` for the section ownership model."

2. **`test-engineer`** — creates initial per-group YAML blocks. Prompt: "Read the `## Subsystems` table in `.ai-state/TEST_TOPOLOGY.md` just written by the systems-architect. For each subsystem row, create a per-group YAML block per the trunk schema in `skills/testing-strategy/references/test-topology.md`. Populate all required fields (`id`, `title`, `subsystems`, `tier`, `selectors`, `file_dependencies`, `parallel_safe`, `shared_fixture_scope`). Leave `integration_boundaries` empty — those populate lazily during subsequent normal pipelines. You own the per-group YAML blocks; do not edit the `## Subsystems` table (architect-owned)."

### Post-Spawn Summary

After both agents complete, report:
- The topology file location: `.ai-state/TEST_TOPOLOGY.md`
- The number of groups created
- Remind the user that `integration_boundaries` populate lazily: as the implementation-planner decomposes future pipeline steps and discovers cross-group coupling, it adds the missing links. No manual editing of `integration_boundaries` is needed at init time.
- Suggest running `/sentinel` to confirm TT01–TT05 pass on the new topology.

---

## Mode: Default (no flag) — Drift-Response Refresh

### Precondition Check

Confirm `.ai-state/TEST_TOPOLOGY.md` exists. If it does not exist, decline:

> "No topology found at `.ai-state/TEST_TOPOLOGY.md`. To create one for the first time, run `/refresh-topology --init`."

### Spawn Agent

Spawn **`implementation-planner`** in topology-only mode. Prompt: "Run in topology-only mode: reconcile `.ai-state/TEST_TOPOLOGY.md` against the current Built components in `.ai-state/DESIGN.md` §3 and any open `topology-drift` ledger rows in `.ai-state/TECH_DEBT_LEDGER.md`. Update group `file_dependencies` and `subsystems` entries where drift is detected. Open new `topology-drift` ledger rows for components that lack group coverage. Produce an updated `.ai-state/TEST_TOPOLOGY.md`. Do not generate an `IMPLEMENTATION_PLAN.md` or `WIP.md` — this is a topology-only reconciliation pass."

### Post-Spawn Summary

After the agent completes, report:
- A diff summary of what changed in the topology
- Any new `topology-drift` ledger rows opened
- Confirm the file location: `.ai-state/TEST_TOPOLOGY.md`
