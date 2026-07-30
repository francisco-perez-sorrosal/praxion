---
id: dec-draft-b5c319e0
title: One parameterized consultant agent; the discipline roster is data in a skill reference; bindings resolve at runtime via the Skill tool
status: proposed
category: architectural
date: 2026-07-30
summary: Ship a single discipline-parameterized consultant agent whose roster lives as a data table in skills/multi-perspective-analysis/references/discipline-registry.md and whose discipline-to-knowledge bindings load at runtime through the Skill tool, making description/skills/tools/rules/plugin.json all discipline-count-independent by construction and enforced by a committed fitness test.
tags: [multidisciplinary-identities, discipline-consultant, extensibility, progressive-disclosure, token-budget, fitness-function, agent-crafting, skill-tool, registry]
made_by: agent
agent_type: systems-architect
branch: worktree-multidisciplinary-identities
pipeline_tier: full
re_affirms: dec-243
affected_files:
  - agents/discipline-consultant.md
  - skills/multi-perspective-analysis/references/discipline-registry.md
  - skills/multi-perspective-analysis/SKILL.md
  - fitness/tests/test_discipline_registry_invariants.py
  - .claude-plugin/plugin.json
  - rules/swe/swe-agent-coordination-protocol.md
affected_reqs:
  - REQ-03
  - REQ-04
  - REQ-05
  - REQ-16
dissent: Praxion already declined a 17th agent for a comparably coherent domain (dec-243) on a three-part earns-its-place test, and the consultant fails one of those three parts by design — it has no hand-forward decision authority. A single always-loaded description plus a registry file is a real, permanent cost paid up-front for a mechanism whose value is unmeasured, and the same registry table read directly by the architect through a skill would have delivered the knowledge at zero agent cost; only the user's dialogue requirement, not the evidence, separates the two.
---

## Context

The design space had three candidates at intake: **A** N agents one per discipline, **B** N skills injected into
existing agents, **C** one parameterized agent plus discipline bindings. Measurement eliminated A before any
qualitative argument: domain-shadow agent descriptions run 371–556 tokens each (`interface-designer` 371,
`agentic-transactions-architect` 500, `roadmap-cartographer` 556 — the true repository maximum), so six
discipline agents would consume 95–130% of the entire 2,309-token always-loaded headroom. B was eliminated by
construction: a skill loaded into the architect's context *is the architect thinking with better knowledge* —
there is no second party, so there is nothing to disagree with, and the dialogue requirement is unsatisfiable.
The user's binding ruling selected C.

C's hard constraint is the user-mandated extensibility criterion: adding discipline N+1 must cost **0**
always-loaded bytes, **0** always-loaded rule edits, **0** new agent files, **0** `plugin.json` edits, **0**
consultant `tools:` changes, **0** new pipeline stages, and touch **≤2** files — indefinitely. Two independent
Wave-A methods (construction analysis, and git archaeology on the `Mode:` directive's 1→2→3 growth) confirmed
zero is achievable but **not automatic**: mode #2 cost zero always-loaded bytes, while mode #3 cost four lines
across two always-loaded files *because it introduced a new artifact type*. The cost driver is "does this add a
new artifact type or loop-back mechanism", not "how many values exist".

Both Wave-A analyses also named the concrete way to violate the criterion: an always-loaded surface that
*enumerates discipline names* — either the coordination-protocol trigger bullet or the consultant's own
`description:` frontmatter. Nothing in the plugin or rules system prevents either.

The intake hypothesis and the context-engineer's review both placed the roster **inline in the agent body**,
reasoning that agent bodies load only when spawned so the roster is free. That is correct about the roster's
*token* cost and incomplete about its *readers*.

## Decision

**One agent, `discipline-consultant`. The roster is a data table in a skill reference file. Discipline
knowledge binds at runtime through the `Skill` tool.**

- **Registry location:** `skills/multi-perspective-analysis/references/discipline-registry.md`, a single
  enumerable table with seven columns (`discipline`, `fires-when`, `binds-to`, `challenge-obligations`,
  `difficulty-hint`, `attaches-to`, `lens-collision`). Zero always-loaded cost (an on-demand reference file),
  inside the skill already designated as the multi-perspective composition layer and already HARD-gated by the
  honest-uncertainty gate — so the gate the registry needs already exists and is already enforced.
- **`skills:` frontmatter is fixed forever** at `multi-perspective-analysis`. Discipline knowledge is **not**
  preloaded; the consultant invokes its bound skill at runtime via the `Skill` tool. Verified in current Claude
  Code documentation: *"Subagents can still invoke unlisted project, user, and plugin skills through the Skill
  tool."*
- **`description:` names the mechanism and the role shape, never the roster** — 735 bytes ≈ 204 tokens, 45%
  smaller than `interface-designer` and 59% smaller than `roadmap-cartographer`.
- **Enforcement is a committed fitness test**, not prose.

Two rulings, not aesthetics, force the registry out of the agent body:

1. **Multi-instance by design.** N concurrent instances each need a *different* discipline chosen **before**
   spawn. A roster readable only *after* spawn cannot inform pre-spawn selection, forcing either a wasted triage
   spawn or the orchestrator reading an agent-adjacent file — and `agent-crafting` documents that
   plugin-distributed agent-adjacent reads fail **silently** in other projects (the read returns "not found",
   the agent continues degraded, no visible error). The context-engineer itself named this exit: *"if Tier-2
   self-nominating agents need to read the registry directly… it must be a **skill** reference file."* The
   multi-instance ruling is the condition that triggers it.
2. **The ≤2-files invariant fails under the inline design for a gap discipline.** Inline roster + `skills:`
   frontmatter binding = registry row + frontmatter edit + new `SKILL.md` = **three** files. Runtime `Skill`-tool
   binding brings a gap discipline to exactly two files and a binding-only discipline to one — and as a free
   consequence the frontmatter becomes immutable across disciplines, so the prompt cache is never invalidated.

**The fitness test asserts the invariant that makes the drift unrepresentable, rather than detecting it after it
lands.** Six assertions, each mapping 1:1 onto a criterion row: exactly one agent file declares the consultant
role and no `agents/<registry-discipline>.md` exists; the `description:` contains no registry discipline name;
no `paths:`-less rule and no `CLAUDE.md` contains any registry discipline name; `skills:` and `tools:` equal
fixed literal sets; the registry is exactly one file with all seven fields populated on every row; the
`plugin.json` agents array count equals the `agents/*.md` count.

A proposed *additional* commit-window sentinel check (`T07`, auditing whether a registry change co-occurred with
an always-loaded edit) is **declined**: under this design the per-discipline always-loaded delta is not merely
detectable but unrepresentable, so `T07` would audit a violation the fitness test makes structurally impossible.
Existing sentinel `T02` remains the total-budget backstop. If the fitness test is ever waived, `T07` becomes
necessary.

**Measured cost.** Always-loaded rules budget: **~330 tokens** (14.3% of the 2,309-token headroom; new total
≈23,021). Skill/agent listing pool: **~344 tokens** (204 agent description + ~140 skill description). Combined
worst case **674 tokens ≈ 29% of headroom** — below the ≤1,100-token one-time threshold and below the Wave-A
925–1,050 estimate, the saving coming from dropping ADR authorship and from a 204-token rather than
371–500-token description. Per-discipline marginal: **0** on the rules budget always; **0** files beyond one
registry row for a binding-only discipline.

## Considered Options

### Option 1 — N agents, one per discipline

- **Pros:** maximally sharp per-discipline trigger language; each discipline gets an independent tool/skill grant.
- **Cons:** 2,200–3,000 always-loaded tokens, exceeding the entire headroom; N descriptions each needing precise
  differentiated trigger language is exactly MAST's "ambiguous role definitions / duplicate agent roles" failure
  category, quantified at ~42% of multi-agent failures. Eliminated by measurement.

### Option 2 — N skills injected into existing agents, no new party

- **Pros:** cheapest of all (~850 tokens for six); zero pipeline change; no MAST risk.
- **Cons:** no second party, therefore no possible challenge. A better-informed monologue is not a dialogue, and
  the dialogue requirement is a stated user goal. Also the empirical null the external lens surfaced (a
  strong-prompt single agent matches the best discussion approach, and discussion pays only in the
  *no-demonstration* regime, which Praxion is not) — so this option is not a straw man, it is the honest
  baseline that the build decision was taken *against* on requirement grounds rather than expected-lift grounds.

### Option 3 — One parameterized agent, roster inline in the agent body, bindings via `skills:` frontmatter

- **Pros:** simplest to read; no indirection; matches the intake hypothesis and the context-engineer's
  recommendation; zero token cost for the roster itself.
- **Cons:** breaks on two rulings. Pre-spawn multi-instance selection cannot read a post-spawn roster, and the
  workaround (orchestrator reads the agent file) fails silently in managed projects. And a gap discipline needs
  three files, violating the ≤2 invariant. Nearly right, and the failure is specific rather than stylistic.

### Option 4 — One parameterized agent, roster in a skill reference, bindings via runtime `Skill` tool (chosen)

- **Pros:** every always-loaded surface plus `plugin.json`, `tools:`, and `skills:` is discipline-count-independent
  **by construction**, not by editorial vigilance; the registry is readable pre-spawn by any convener in any
  project; prompt cache never invalidated; a gap discipline costs exactly two files; the registry lands in the
  skill whose HARD gate is already the right gate.
- **Cons:** one indirection, slightly more turns per consult (a runtime `Skill` load instead of preloaded
  content), and a new runtime failure mode — a `Skill` load can fail where a preloaded skill cannot.

## Consequences

**Positive:** the user-mandated extensibility criterion is met by construction and enforced by a red test rather
than by prose; unbounded binding-only disciplines at zero always-loaded cost; ~1,979 tokens of rules-budget
headroom left untouched by any future discipline; the registry doubles as the Tier-1 trigger table, so authored
routing costs nothing always-loaded; the declined `T07` keeps the sentinel catalog from growing for no signal.

**Negative:** a reader must follow one hop from the agent to the registry; runtime skill loading adds turns; a
17th agent enters a pipeline already carrying two adjacent sub-architects, which is standing MAST exposure
regardless of how sharply the boundary is written.

**Risks accepted:** the `Skill`-tool binding is a new failure surface, mitigated by a fail-loud contract (an
unresolvable binding returns `[BLOCKED]`, never a silently degraded consult) rather than by a fallback that
would hide it. And the fitness test constrains *names*, not *semantics* — a discipline could be described
generically in the `description:` in a way that still effectively enumerates it; that residual is accepted
rather than chased with a semantic check.

## Prior Decision

`dec-243` ("Agentic-app-reliability frontier practices land as skills, not a 17th agent") is **re-affirmed, not
superseded**. Applied honestly, its three-part earns-its-place test scores the consultant at roughly 1.5/3
against a stated rule of "fail 2/3 → skills": it **passes** the conflicting-decision-seam part — objecting *is*
its function, and Option 2's rejection above is precisely that absorbed knowledge produces no tension; it
**fails** hand-forward decision authority, deliberately and by design; and it only **partially** meets
irreversible blast radius — a wrong statistical threshold shipped as an acceptance criterion propagates into
every downstream measurement with nothing catching it today, which is this project's own self-identified
measurement blind spot. This ADR does not claim a clean pass.

What resolves the tension is that `dec-243` evaluated a **different role shape** — "agent as knowledge owner with
decision authority" — and its own `dissent:` field records the residue it left behind: *"a skills-only carrier
leaves no owner to object to an un-guard-railed architecture."* A discipline-parameterized consultant is the
**generic** answer to that dissent: it gives *any* existing skill standing to object without paying for a
per-domain agent. So `dec-243`'s skills-only verdict for reliability **still holds and is strengthened** —
reliability becomes a future registry row bound to the very skills `dec-243` created, never a 17th-agent
equivalent. A supersession of `dec-243` would require the opposite evidence: that reliability specifically needs
its own decision-authority agent, which nothing here shows.

## Disconfirmation

- **Falsifier:** the second discipline added costs more than one registry row plus at most one skill file.
  Concretely — if adding discipline #2 requires touching an always-loaded rule, the agent `description:`, the
  `skills:` frontmatter, or `plugin.json`, then the roster is structure rather than data and this design failed
  on its own stated criterion. The fitness test is written to make that failure a red test rather than a
  discovery.
- **Steelmanned runner-up:** Option 2 (skills only, no new party). It is the cheapest option by a wide margin,
  it carries zero MAST exposure, and the strongest single piece of external evidence retrieved — a peer-reviewed
  ACL result that a single agent with strong prompts matches the best discussion approach, and that discussion
  helps *only* when the prompt carries no demonstrations — lands squarely on Praxion's own configuration, which
  is demonstration-dense by construction. On the evidence alone, Option 2 is the favourite; the measured
  persona-accuracy tax on *coding* specifically (the worst-hit category in the one study that isolates persona
  content) makes it stronger still. Only the user's dialogue requirement, and the reconciliation-deficit
  argument that an internal society of thought is incomplete because it competes rather than ensembles,
  separate the chosen option from this one.
- **Reversal trigger:** a disposition ledger showing a high `dismiss-with-rationale` rate across ≥10 challenges
  spanning ≥3 tasks *while* the architect's unaided output with the same knowledge injected is indistinguishable
  in quality. That is the substitution hypothesis holding, and the correct response is to delete the agent and
  keep the skills — collapsing to Option 2 rather than tuning the mechanism.
