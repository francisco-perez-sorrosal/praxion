---
description: Convene a discipline consultant to challenge a target artifact
argument-hint: "<discipline> [--on <artifact>]"
allowed-tools: [Bash, Read, Write, Edit, Grep, Glob, Task, Skill]
---

Run a discipline consultation using the [discipline-consultant](../agents/discipline-consultant.md) agent, human-convened — the third path alongside a registry trigger predicate firing and a pipeline agent self-nominating. Produces independent reading, falsifiable challenges, and per-challenge disposition for exactly one discipline resolved against the roster at `skills/multi-perspective-analysis/references/discipline-registry.md` (e.g. `statistician`; the roster is discipline-generic and grows by adding rows, never by naming disciplines here).

## Process

1. **Resolve the discipline and target** from `$ARGUMENTS`:

   - `<discipline>` (required, first token) — pass it through **verbatim, unresolved**. This command performs no registry lookup of its own; resolution against the roster is the consultant's own Phase 1 contract, and duplicating it here would risk a second, drifting source of truth.
   - `[--on <artifact>]` (optional) — the file, PR, branch, or named surface to challenge. If omitted, default to the current branch diff against the repo's default branch.

2. **Seal the prior list, before spawning** — having decided to convene, load the matched registry row's `binds-to` skill via the `Skill` tool, work that row's `challenge-obligations` against the target, and append what the pass surfaces to `.ai-state/CONSULT_PRIORS.md § Sealed Priors` — one row per concern, or one explicit `NONE` row. **Commit the file before spawning**: the seal is the commit, not the working-tree write. Schema: `.ai-state/CONSULT_PRIORS.md § Column Definitions`.

3. **Invoke the discipline-consultant** via the Task tool as convener:

   - Spawn prompt carries `Discipline: <discipline>` and `Task slug: consult`, per the directive contract in `agents/discipline-consultant.md`
   - Pass the resolved target as the artifact to read at Round 1 — never expose it during the consultant's Round 0 independent reading
   - **Unresolvable discipline**: if the consultant returns `[BLOCKED]`, surface that verdict verbatim with the offending value named. Never substitute a neighboring discipline, never guess, never proceed with a degraded consult — the registry is the only roster.
   - **Round 2 disposition**: as convener, adjudicate each challenge and append one `.ai-state/CONSULT_LEDGER.md` row per challenge (`agents/CLAUDE.md § Who may convene`), **plus one `.ai-state/CONSULT_COSTS.md` row for the consult as a whole** — aggregate token count, model tier, difficulty class. Schema: `.ai-state/CONSULT_COSTS.md § Column Definitions`. **Classification is blind, not the convener's own call**: build a blind packet (sealed priors + their `prior-id`s, no disposition/rationale/classification; plus each challenge's id, claim, decision-at-stake and full text with its `Disposition:`/`Rationale:` lines removed — every field checked for disclosure first), spawn one `general-purpose` agent at `opus` told not to read `.ai-state/CONSULT_*.md` or the fragment, and record its `novel`/`matched` + `prior-id` call **verbatim** as one `.ai-state/CONSULT_PRIORS.md § Challenge Classification` row, with the consultant's `**Round-0 HEAD:**` sha as the seal witness. Never override the reader's call; the convener records no view of its own.

4. **Output the review** directly in the conversation:

   - Resolved discipline, skill(s) bound at runtime, round reached
   - Challenges (one per `### CH-NN`) — claim, decision it would change, confidence
   - Path to `.ai-work/consult/CONSULT_<discipline>.md`
   - Terminal marker: `[COMPLETE]` / `[BLOCKED]` / `[PARTIAL]`
