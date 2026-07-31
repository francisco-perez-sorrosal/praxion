---
id: dec-307
title: Strip inert plugin-subagent frontmatter fleet-wide; no compensating permissions.allow
status: accepted
category: architectural
date: 2026-07-30
summary: Remove permissionMode/hooks/mcpServers from all 17 plugin-registered agents, guard against re-introduction, and decline any compensating session-wide permissions.allow grant in Praxion or onboarding.
tags: [agents, plugin, permissions, frontmatter, tech-debt, security, td-072]
made_by: agent
agent_type: systems-architect
branch: worktree-wave2-multidisciplinary
pipeline_tier: full
affected_files:
  - agents/agentic-transactions-architect.md
  - agents/architect-validator.md
  - agents/cicd-engineer.md
  - agents/context-engineer.md
  - agents/discipline-consultant.md
  - agents/doc-engineer.md
  - agents/implementation-planner.md
  - agents/implementer.md
  - agents/interface-designer.md
  - agents/promethean.md
  - agents/researcher.md
  - agents/roadmap-cartographer.md
  - agents/sentinel.md
  - agents/skill-genesis.md
  - agents/systems-architect.md
  - agents/test-engineer.md
  - agents/verifier.md
  - codex/config/export-codex-agents.py
  - scripts/test_export_codex_agents.py
  - skills/agent-crafting/SKILL.md
  - skills/context-security-review/references/permission-baseline.md
  - docs/claude-code-limitations.md
  - tests/test_agent_frontmatter_plugin_compat.py
dissent: A narrow `Edit(.ai-state/**)` grant would cost little and would remove real prompt friction for the seven pipeline agents that must write architecture and state documents unattended; refusing it on blast-radius grounds may be treating a session-scope config key as more dangerous than it is, given the user already runs most pipelines with a permissive parent session anyway.
---

# Strip inert plugin-subagent frontmatter fleet-wide; no compensating `permissions.allow`

**Activation:** no — the design-synthesis lens sweep was not run. The technology and boundary questions are settled by vendor documentation rather than by trade-off (see Context); the single genuinely open question is the compensation ruling, which is treated below through the Dialectical Inquiry sub-step rather than a full lens sweep. Tier-B cross-model challenge: **not invoked**. The stakes have a security dimension but the decision is a *decline to widen* — the post-change security posture is byte-identical to the pre-change posture, and the choice is reversible by a one-line config edit. Tier-B is reserved for one-way doors.

## Context

`td-072` records that all 17 Praxion agents declare `permissionMode` and 16 of them declare an identical `hooks:` block, while all 17 ship exclusively as plugin subagents via `.claude-plugin/plugin.json`. The Claude Code sub-agents page states verbatim:

> "For security reasons, plugin subagents don't support the `hooks`, `mcpServers`, or `permissionMode` frontmatter fields. These fields are ignored when loading agents from a plugin. If you need them, copy the agent file into `.claude/agents/` or `~/.claude/agents/`."

Every one of those declarations is therefore inert, and has been for the entire life of the fleet. Two harms follow: agents whose intended behaviour reads as depending on `acceptEdits` have never had it, and the declarations mislead every reader and every future agent author who copies the pattern — including from `skills/agent-crafting/SKILL.md`, whose copy-paste template still shows both fields.

The ledger row states the resolution "needs a decision, not just a delete." That is correct, but the decision it names — strip vs. copy to `.claude/agents/` — is largely closed by two verified facts. First, the `hooks:` half is pure redundancy: `hooks/hooks.json` registers `send_event.py` and `precompact_state.py` at plugin level for `Stop`/`SubagentStop`/`PreCompact` unconditionally, and 20,105 rows of `observations.jsonl` carrying `agent_start`/`agent_stop`/per-`agent_type` `tool_use` prove that path fires. Stripping costs zero behaviour. Second, the escape hatch is **asymmetric**: the same vendor page states a parent session in `acceptEdits`/`bypassPermissions` takes precedence over any subagent `permissionMode` and cannot be overridden — for project-level agents too. Praxion's 7 `permissionMode: default` declarations could never have bound a permissive parent by any route. The hatch grants permissiveness; it cannot restore restriction.

What remains genuinely open, and is the substance of this record, is the **compensation question**: once `acceptEdits` is stripped from 10 agents, do they need compensating `permissions.allow` rules? The vendor page names `permissions.allow` as the alternative while warning that *"these rules apply to the entire session, not only the plugin subagent"* — so the natural compensation is strictly wider than the field it replaces.

One fact the upstream research pass did not surface, found during codebase assessment and material to the edit list: `codex/config/export-codex-agents.py` copies the agent frontmatter block **verbatim** into each exported Codex agent's `developer_instructions`, under a preamble asserting it is "authoritative for tool scope, permission mode, memory, hooks, …". Three assertions in `scripts/test_export_codex_agents.py` pin `permissionMode: default`, `hooks:`, and `async: true` into that capsule. Codex honours neither field, so the exporter was re-publishing the same false claim into a second assistant — but the strip turns that test red unless the repair lands in the same commit.

## Decision

**1. Strip fleet-wide.** Remove `permissionMode` from all 17 plugin-registered agents and the 13-line `hooks:` block from the 16 that declare it. `mcpServers` is declared by zero agents; it is covered by the guard as a forward assertion only. No agent is copied to `.claude/agents/`.

**2. No compensating `permissions.allow` — in Praxion or in onboarding.** Stripping an inert field removes no capability, so there is nothing to compensate for. A session-wide grant would not restore a lost capability; it would grant one that never existed, and grant it to the main agent and all 17 subagents — including `verifier`, `sentinel`, and `architect-validator`, which carry `disallowedTools: Edit` precisely because they must not edit. That is a unidirectional widening of the trust boundary bought to relieve a friction that, by construction, is unchanged from yesterday. The correct lever for a user who wants fewer prompts already exists at the parent-session level, is chosen per invocation, and is authoritative over everything downstream anyway; baking its equivalent into shipped config converts a visible per-session user choice into an invisible durable fleet-wide one.

This answer is the same for Praxion and for managed projects, but for different reasons worth stating separately. Praxion's `.claude/settings.json` carries `"allow": ["Write(.ai-work/**)"]`; managed projects do not — onboarding ships only `permissions.deny` (the Obsidian CLI block) and an `env` key. **No canonical-block file, `commands/onboard-project.md`, `commands/new-project.md`, or `new_project.sh` is modified by this decision.**

**3. Preserve documentation-of-intent where it can actually be read.** The `default` marker was the only written record of restrictive intent for `promethean` and `roadmap-cartographer` (both carry `Write` *and* `Edit` with no `disallowedTools`). That intent moves to `skills/context-security-review/references/permission-baseline.md`, whose `Permission Mode` column is relabelled *(intended)* and annotated as not machine-enforced. This repair is also *caused* by the strip: that file instructs reviewers that "any difference in `tools`, `permissionMode`, or `disallowedTools` is a finding", which after the strip would produce 17 false positives.

**4. `architect-validator`'s missing `hooks:` block is an authoring accident, not a design signal**, and the strip makes the question vacuous — afterwards all 17 agents are uniform at zero. Its observability was never affected: plugin-level `hooks.json` covers every subagent unconditionally, which is exactly why the other 16 blocks were redundant. No action.

**5. Guard against re-introduction.** A new `tests/test_agent_frontmatter_plugin_compat.py` asserts that no file listed in `plugin.json`'s `agents` array declares any of the three fields, with membership derived from `plugin.json` (not a `glob`), a `len(files) >= 17` floor against vacuous passes, and a committed negative fixture exercised through the **same** detector function so the assertion is provably failable once the fleet is clean.

## Considered Options

### A. Strip fleet-wide, no compensation (chosen)

- **Pro:** 17 files stop asserting a contract the runtime does not honour; the misleading template stops propagating; the security posture is unchanged; the Codex capsule stops re-exporting the false claim into a second assistant; the invariant becomes machine-checked for the first time.
- **Con:** the `default` marker's documentary value is lost from the files themselves (mitigated by Decision 3); this is first-of-kind in the repo — no precedent exists for removing inert agent frontmatter.

### B. Strip, plus a compensating session-wide `permissions.allow`

- **Pro:** removes real prompt friction for pipeline agents that write documents unattended; makes the shipped configuration self-sufficient rather than dependent on how the user launched the session.
- **Con:** grants a capability that never existed, to a wider audience than the field it replaces, at exactly the moment the change is being justified as behaviour-preserving. The vendor's own warning — "these rules apply to the entire session, not only the plugin subagent" — is the whole objection. It would also hand `verifier`/`sentinel`/`architect-validator` a standing edit allowance that their `disallowedTools` exists to deny.

### C. Copy a named subset into `.claude/agents/`

- **Pro:** the fields would actually be honoured for those agents.
- **Con:** illusory for the restrictive half — a permissive parent overrides subagent `permissionMode` for project-level agents too, so the 7 `default` declarations gain nothing. Unjustified for the permissive half — no agent body and no coordination-protocol document contains a workflow presupposing silent edit application, so `acceptEdits` buys nothing that repays abandoning single-path distribution. And it forks the fleet across two shipping paths, which every managed project would then have to reproduce.

### D. Leave as-is, document the inertness

- **Pro:** zero change, zero risk.
- **Con:** does not address td-072's second harm. `skills/agent-crafting/SKILL.md` already carries the caveat at line 74 while still showing the fields in its copy-paste template at lines 41 and 44 — documentation alone has already been tried and has already failed to stop the pattern.

## Consequences

**Positive**

- The frontmatter stops making claims the runtime does not honour; readers and future agent authors get an accurate surface.
- The security posture after the change is byte-identical to the posture before it — no grant, no widening, no new exposure introduced by a cleanup commit.
- Uniformity across all 17 agents removes the `architect-validator` asymmetry for free.
- A fleet invariant that was previously unenforced becomes a test, with red-first evidence and a permanent negative fixture.
- `permission-baseline.md` stops mixing an enforced signal (`tools`/`disallowedTools`) with an unenforced one (`permissionMode`) in the same table without distinction.

**Negative**

- Files no longer state their intended permission posture. Recoverable only via `permission-baseline.md`, which is a second lookup and is itself stale by 5 agents (named for the ledger; deliberately not fixed here).
- Six files outside `agents/` must change in lockstep; missing any one of them either reddens the suite or leaves a stale claim behind.
- If Claude Code later honours these fields for plugin subagents, Praxion re-adds them deliberately rather than inheriting them.

**Neutral**

- Historical ADRs `dec-100` and `dec-149` describe agents by their `permissionMode`. Those records are immutable and are not edited; the descriptive drift is noted here instead.

## Disconfirmation

**Falsifier.** A concrete, reproducible workflow failure attributable to the absence of `acceptEdits` — a named pipeline agent, on a named path, blocked by a permission prompt it cannot answer, in a session the user has *not* deliberately put into a restrictive mode. That would show the field's inertness has an operational cost after all, and that Option B's grant is compensation rather than expansion. Its absence to date is the load-bearing evidence: 20,105 observation rows and the entire lived history of the pipeline, with these fields inert throughout, and no such failure on the ledger. Symmetrically, evidence that Claude Code has begun honouring `permissionMode` for plugin subagents would falsify the premise of the strip itself.

**Steelmanned runner-up.** The strongest case is not Option C (documentation-of-intent), which is weak — an inert field that *claims* enforcement is strictly worse than no field, because a reader who trusts it is misled about what constrains the agent, and `tools`/`disallowedTools` already carry the enforceable half of the intent. The genuinely strong runner-up is **Option B with a tightly path-scoped grant** — specifically `Edit(.ai-state/**)` and `Write(.ai-state/**)` rather than a blanket `Edit`/`Write`. Argued on its own terms: the seven pipeline agents that must maintain `DESIGN.md`, `TECH_DEBT_LEDGER.md`, and `decisions/drafts/` unattended are doing exactly the work Praxion exists to automate, and a prompt in the middle of a background subagent's run is not merely friction — a background agent cannot answer it, which is the documented root of `td-035`. A grant scoped to `.ai-state/**` is narrow, its contents are versioned and reviewable in every diff, and it is arguably *less* dangerous than the `Write(.ai-work/**)` grant Praxion already ships to itself without controversy. Against that: `.ai-state/` is committed and durable, where `.ai-work/` is gitignored and ephemeral — the asymmetry in blast radius is real and runs the wrong way for this argument — and the grant would still reach `verifier` and `sentinel`, whose `disallowedTools: Edit` is a deliberate boundary that a session-scope `allow` would quietly step around. The runner-up loses on that last point, not on scope. It is close enough that I would revisit it immediately on the falsifier above, and it is recorded verbatim in the `dissent:` field.

**Reversal trigger.** Revisit when any of: (a) the Claude Code release notes or the sub-agents page state that plugin subagents honour `permissionMode`/`hooks`/`mcpServers` — at which point re-adding them becomes a deliberate design act, not an inherited default; (b) a `td-NNN` row lands describing a background subagent blocked by an unanswerable permission prompt on a non-`.ai-work` path; (c) Praxion adds a headless or CI-driven pipeline mode where no human is present to answer prompts, which changes the cost of friction from "annoying" to "fatal" and reopens Option B's narrow-scope variant on its merits.
