---
id: dec-draft-ef6b8065
title: Hackathon mode — flexible-entry Hackathon Spine, activation, and process integration
status: proposed
category: architectural
date: 2026-05-15
summary: Hackathon mode replaces the 5-tier selector with a flexible-entry Hackathon Spine (fixed-order pipeline promethean -> researcher -> systems-architect -> implementation-planner -> implementer parallel test-engineer -> verifier) the user enters at a natural-language-inferred entry point, moves around in freely, and exits; everything upstream of the entry point is skipped, the verifier runs by default but is skippable, the auto-classifier is removed, and the safety net is skipped-rigor transparency (every skip and movement recorded in PROGRESS.md) rather than construction-guaranteed rigor. Activates through a four-channel signal (env var + CLAUDE.md block + praxion-rules preset + a praxion-hackathon CLI wrapper), keeps discovery full-strength while relaxing only delivery ceremony, and bundles the test-first relaxation into the same single switch.
tags: [hackathon-mode, process-calibration, flexible-entry-pipeline, pipeline-spine, onboarding, tier-system, context-budget, ceremony-reduction, cli-wrapper, test-discipline, discovery-delivery-split, skipped-rigor-transparency]
made_by: agent
agent_type: systems-architect
branch: worktree-hackathon-mode-design
pipeline_tier: standard
affected_files:
  - commands/onboard-project.md
  - commands/new-project.md
  - rules/swe/swe-agent-coordination-protocol.md
  - hooks/remind_adr.py
  - hooks/inject_process_framing.py
  - agents/sentinel.md
  - claude/canonical-blocks/hackathon-mode.md
  - claude/aac-templates/praxion-rules.hackathon-preset.yaml
  - claude/aac-templates/praxion-hackathon.sh.tmpl
  - claude/aac-templates/hackathon-directive.md.tmpl
  - claude/aac-templates/hackathon-settings.json.tmpl
  - tests/test_hackathon_mode.py
---

## Context

Praxion needs a project-scoped "hackathon mode" that significantly relaxes SDD/spec
and ADR ceremony for proof-of-concept projects, reduces the always-loaded context
surface, relaxes the test-first gating, and **preserves the *availability*** of the
systems-architect, implementation-planner, basic test execution, and basic verification.
The decision went through four architect passes; this ADR records the v4 outcome and why
it supersedes the v3 mechanism.

**The v2→v3 history (resolved, recorded for provenance).** v2 chose, as its
tier-integration mechanism, "a per-project default that biases the tier-selector toward
Lightweight." But the Lightweight tier is *defined* in `swe-agent-coordination-protocol.md`
as "2-3 files, single behavior; optional researcher; **no other agents**." So "bias toward
Lightweight" structurally means *no systems-architect and no implementation-planner* — the
direct opposite of the user's requirement to keep both available. The user's review of v2
caught this contradiction, and v3 resolved it by replacing the tier-bias with a *fixed,
named Hackathon Pipeline* in which the architect and planner are literal, guaranteed
pipeline stages.

**Why v4 supersedes v3.** v3 made hackathon mode a **fixed named pipeline** fronted by a
rule-based **2-path auto-classifier** (`Direct` for trivial fixes | the fixed
`Hackathon Pipeline` for everything else). After a full Q&A round on the v3 design, the
user made a structural change and two simplifying clarifications:

1. **Flexible entry, not a fixed pipeline.** Hackathon mode should be a pipeline *spine*
   the user **enters, moves around in, and exits** — fixed in *order*, not in
   *membership*. The user declares the entry point in natural language; the main agent
   infers it; everything upstream of the entry point is skipped (including the
   systems-architect and the implementation-planner). This restores the per-task process
   adaptivity v3's fixed pipeline gave up (v3's own Objection 2).
2. **The auto-classifier is removed entirely.** v3's rule-based 2-path selector is
   unnecessary — natural-language entry inference subsumes it. "Fix this typo" infers an
   entry at `implementer` just as well as a classifier did. One mechanism removed.
3. **No rigor-pass mechanism is built.** v3's brief floated an "after-the-task rigor pass";
   the user ruled there is no such thing — reviewing hackathon output is ordinary
   conversation with Claude, an existing capability. No `/hackathon-harden` command, no
   dedicated rigor pipeline.

The user's framing for the change was explicit: *"we need maneuverability in the process"*
and *"break the laws when needed."* The headline consequence — and the design's central
honest cost — is that v4 lets the user skip the architect, the planner, *and* the verifier,
and move work freely between stages. v3 could guarantee rigor by construction; v4 cannot.
v4's answer is not to re-impose the guarantee but to make skipped rigor **visible and
auditable** — every skipped stage and every mid-task movement is recorded.

Several coupled questions had to be answered together because they jointly determine how
the single `PRAXION_HACKATHON_MODE` switch behaves and propagates: what hackathon mode
*is*; how the entry point is chosen and what happens on ambiguity; how the
behavioral-contract's Register-Objection interacts with skipping the architect; how free
mid-task movement relates to v3's bounded creative-blocker loop-back; whether the verifier
is skippable; who produces Acceptance Criteria when the architect is skipped; how the
worktree-isolation rule maps onto a flexible-entry spine; and how skipped rigor is kept
visible. These are facets of one decision, recorded in one ADR.

Research and a CLI investigation established the constraints (carried forward, unchanged by
v4): Claude Code has no *per-skill or per-agent* disable mechanism, bounding rule-channel
context trimming at ~3,500 tokens via `praxion-rules.yaml`; the `claude` CLI exposes
`--disable-slash-commands` (an all-or-nothing skill nuke — skills still resolve via
explicit `/name`; `WebSearch`/`WebFetch` are tools, unaffected), `--append-system-prompt`,
`--settings`, and `--effort`, applicable only at `claude` launch time, so only a wrapper
script can deliver them. Every ceremony check in Praxion is already conditional or
advisory — no hard failures from absent ceremony. The established project-toggle pattern
is a `PRAXION_*` env var in `.claude/settings.json`. Token accounting (re-measured with
`wc -c` for the v3 pass, unchanged by v4 because flexible entry alters no token math): the
four `core` rules total ~10,246 tokens and both CLAUDE.md files ~7,102 — an immovable
~17,348-token always-loaded floor.

## Decision

**Mechanism — a flexible-entry Hackathon Spine replacing the tier selector.** When
`PRAXION_HACKATHON_MODE=1`, the main agent no longer runs the 5-tier
Direct/Lightweight/Standard/Full/Spike calibration, and no longer runs v3's 2-path
auto-classifier. Instead it places the task on the **Hackathon Spine** — a pipeline with a
**fixed order** but **variable membership**:

      promethean → researcher → systems-architect → implementation-planner
        → (implementer ∥ test-engineer) → verifier

- **Entry by natural language.** The user declares where to start in plain language; the
  main agent **infers** the entry point ("ideate X" → `promethean`; "research X" →
  `researcher`; "design X" → `systems-architect`; "plan and build X" →
  `implementation-planner`; "fix this typo" → `implementer`). The five valid entry points
  are `promethean | researcher | systems-architect | implementation-planner | implementer`.
  Everything **upstream** of the entry point is **skipped** — including the architect and
  the planner.
- **Ambiguity → ask.** When the prompt does not make the entry point clear, the main agent
  asks one cheap, specific clarifying question — it does not silently default to a stage.
- **No separate Direct path.** v3's `Direct` route (no agents, no verifier) collapses: a
  trivial fix is "enter at `implementer`," and the verifier still runs by default.
- **Free mid-task movement.** The user may, mid-task, move the work to any spine stage
  ("go back and research this," "move it to the architect," "skip ahead and build it").
  User-driven movement is **unbounded** — a human choosing to loop is not a hazard. It is
  orchestrator-mediated and recorded.
- **The creative-blocker case is folded into user-driven movement.** An agent that hits a
  genuine design dead-end appends a `CREATIVE-BLOCKER:` line to `PROGRESS.md`, **stops at
  that stage**, and surfaces the blocker to the user; the **user** decides whether to move
  the work back to ideation. The orchestrator does **not** auto-re-invoke promethean. v3's
  max-1 loop cap is removed *and the loop itself is removed* — the human in the loop is the
  termination condition, structurally stronger than a counter. The one preserved rule:
  raise → pause → human decides (a blocked agent does not push through or re-raise).

**The calibrated Register-Objection on skipping the architect.** Entering at `implementer`
skips the architect and the planner. When the user directs "just implement X," the main
agent complies — **unless** it has a genuinely strong, well-founded reason ("a really good
motive," not "a doubt") that skipping design is a real mistake. It **holds and asks** only
when the task touches a **security-sensitive surface** (auth, secrets, trust-boundary
input), carries **data-loss risk** (schema migration, destructive operation), or is
**visibly far beyond the user's framing** (many files / multiple subsystems / cross-cutting
structural change). For minor or speculative doubts it complies silently. This is
*calibrated* Register-Objection — proportionate judgment, not ceremony.

**Verifier — default-on, explicitly skippable.** The verifier runs by default as the
implementation harness, whatever entry point was chosen. It is skippable **only** when the
user explicitly says so. When skipped, the orchestrator emits a one-line terminal note
stating what process was (not) applied. This is slightly more permissive than v3, where
the verifier was a non-skippable tail.

**Acceptance Criteria without an architect.** If the architect was skipped but the planner
ran, the **planner emits light Acceptance Criteria** (plain-English bullets, no REQ IDs).
If both were skipped (entry at `implementer`), the **verifier derives what to check from
the diff**. Either way the default-on verifier has acceptance criteria to check against.

**Skipped-rigor transparency — v4's safety net.** Because the architect, the planner, and
the verifier are all skippable and movement is free, v4's safety net is **transparency,
not enforcement**: every skipped stage and every mid-task movement is **recorded** — in
`.ai-work/<slug>/PROGRESS.md` (entry/skip/movement lines, the existing phase-transition
format — no schema change) and in the `VERIFICATION_REPORT.md` header (or a one-line
terminal note when the verifier itself was skipped). A reviewer or a graduation audit can
always reconstruct exactly what process was applied to a given change. The chaos is
allowed; the chaos being invisible is not.

**Worktree policy by entry point.** Entry at `promethean`/`researcher`/`systems-architect`
→ the main agent creates a worktree (`EnterWorktree`) before spawning, consistent with the
existing Standard/Full isolation rule. Entry at `implementation-planner`/`implementer` →
the user decides (no-worktree, current-checkout allowed), mirroring the Direct/Lightweight
allowance. When mid-task movement crosses *up* into a worktree-requiring stage, the
orchestrator creates a worktree at that transition. This is a refinement of Praxion's
existing per-tier isolation rule, not a new mechanism.

**Discovery/delivery split.** Hackathon mode relaxes only the *delivery ceremony*. *When
they run*, promethean and researcher run at FULL depth — unbounded internet research,
multi-source synthesis, idea ledgers. v4 makes discovery *optional* (skippable by entry
point) but never *trimmed* when present. `--disable-slash-commands` disables *skills*, not
*tools*: `WebSearch`/`WebFetch` remain fully available; a wrapper-launched researcher loses
only skill *auto-trigger*.

**Activation — four channels** (unchanged from v3 — re-validated as mechanism-independent;
only the *content* of the CLAUDE.md block changes, not the channel set):

- `PRAXION_HACKATHON_MODE=1` in `.claude/settings.json` `env` — read by hooks; the
  **project-scoped source of truth**.
- A `## Hackathon Mode` block in the opted-in project's `CLAUDE.md` — read by every agent
  at session start; carries the **Hackathon Spine definition**, the entry-point inference
  guidance, the movement rules, the verifier default-on/skippable rule, the
  calibrated-objection hold-list, the skipped-rigor-transparency discipline, the slim
  artifact shapes, the relaxed test discipline, the discovery/delivery split, and the
  Behavioral Contract **restated verbatim**.
- A `hackathon` preset in `.claude/praxion-rules.yaml` suppressing three non-core
  hook-deliver rules — ~3,500 tokens of *ambient* reduction.
- A `praxion-hackathon` **CLI wrapper script** (Shape B — "skill-nuclear") invoking
  `claude` with `--disable-slash-commands` (~5,000–8,000-token skill-surface trim),
  `--effort low`, `--append-system-prompt`, and `--settings`. **Complementary, not
  primary** — the mode is correct on any launch; only the extra skill-trim depends on the
  wrapper.

**Always-loaded footprint — the smallest of all options.** The spine definition lives
entirely in the per-project `## Hackathon Mode` CLAUDE.md block (opted-in projects only).
The only change touching *every* project is a **single ~25-token pointer sentence** in
`swe-agent-coordination-protocol.md`: *"If `PRAXION_HACKATHON_MODE=1`, the 5-tier selector
is replaced by the Hackathon Spine — a flexible-entry pipeline the user enters by natural
language — see that project's `## Hackathon Mode` CLAUDE.md block."* (v4 re-words v3's
pointer — it now points at a flexible-entry spine, not a 2-path selector — at unchanged
token count.)

**Independence guarantee.** With `PRAXION_HACKATHON_MODE` unset or `0`, every Praxion
behavior is **byte-identical** to today. The **single exception** is the ~25-token pointer
sentence: always loaded, but *behavior-inert* on a non-hackathon project.

**Test discipline.** The same `PRAXION_HACKATHON_MODE` switch carries a **single-switch
relaxation** of test-first gating — three relaxations bundled: (1) the
implementer/test-engineer *pairing* requirement is dropped — the implementer authors
production code and a happy-path smoke test in one single-writer step; (2) the test
*green-gate* becomes *advisory* — the verifier runs even on red tests and classifies a
failing test (and the absence of any smoke test for new behavior) as a WARN, not a FAIL;
(3) the *disjoint-file* discipline is dropped for single-writer steps. Lint, typecheck, and
behavioral-contract failures remain FAIL. Tests still run and `pytest` failures still
surface honestly.

**Light & fast verifier.** When it runs, the verifier covers Phases 1, 2, 3 (AC), 5
(lint/typecheck), 5.5 (Behavioral Contract — non-negotiable, FAIL-gating), 10 (test
status), 12 (report); Phases 4, 7, 8, 9, 11 auto-skip via existing conditional logic. No
verifier-code change.

**Three guardrails.** (1) Both process paths — the 5-tier default and the Hackathon Spine —
are exercised in Praxion's own CI via `tests/test_hackathon_mode.py`, including a flag-OFF
byte-identical independence regression (the test surface checks entry-point inference, not
a 2-path classifier — the classifier no longer exists). (2) An advisory sentinel
graduation check flags when hackathon mode is active on a project that has outgrown PoC
size. (3) The Behavioral Contract is restated verbatim in the `## Hackathon Mode` block.

**Onboarding.** A dedicated Phase 5b gate in `/onboard-project` (and a `--hackathon` flag
on `/new-project` chaining to the same gate) writes six artifacts together. The mode is
opt-in; the gate defaults to "Skip — keep full ceremony".

**Reversibility.** A documented four-step exit. No state damage. New in v4: a graduating
project uses the `PROGRESS.md` skip/movement record as a retro-apply checklist for the
process stages it skipped.

**Agent-code changes.** No agent prompt is modified. The single agent *file* that changes —
`agents/sentinel.md` — gains a new *additive*, flag-gated graduation check. All other
behavior (entry-point routing, free movement, the calibrated objection, the verifier
default-on/skippable rule, the AC-without-architect paths, the skipped-rigor transparency,
the worktree-by-entry-point policy) is delivered through instruction channels the agents
already read.

## Considered Options

### Option 1 — Tier-bias toward Lightweight (v2's choice — SUPERSEDED in v3)

A per-project default biasing the 5-tier selector toward Lightweight.

- **Con — fatal:** self-contradictory. Lightweight is *defined* as "no architect, no
  planner." A bias toward Lightweight structurally removes the two agents the user wanted
  available. Superseded by v3; recorded here for provenance.

### Option 2 — Fixed named Hackathon Pipeline behind a 2-path auto-classifier (v3's choice — SUPERSEDED)

When the flag is on, a rule-based 2-path selector picks `Direct` (trivial) or the fixed
`Hackathon Pipeline` (`promethean → researcher → systems-architect →
implementation-planner → implementer∥test-engineer → verifier`); the pipeline always runs
all stages.

- Pro: the architect and planner are guaranteed *by construction* — rigor is guaranteed; a
  contributor can trust that any non-trivial hackathon change went through architecture
  review, planning, and verification. Conceptually honest. Smallest always-loaded footprint
  (pointer sentence in the opt-in CLAUDE.md block).
- **Con 1 — a fixed pipeline is not adaptive.** v3's own Objection 2: a 5-file task and a
  30-file task run the *identical* pipeline shape. The 5-tier selector existed precisely to
  give different-sized work different process weight; the fixed pipeline collapses that. A
  small-ish task gets promethean + researcher whether it needs them or not; a large task
  gets no extra orchestration.
- **Con 2 — it carries a rule-based classifier.** The main agent must evaluate a
  "trivial vs. not" predicate on every task. That predicate is a real, if small,
  mechanism — one more thing to define, test, and keep coherent.
- **Why v4 supersedes it:** the user wanted maneuverability — to enter the process where
  the task needs it and move around mid-task. A fixed pipeline cannot offer that. And the
  classifier turned out to be redundant: natural-language entry inference does the
  classifier's job (and more — it picks among five entry points, not two paths) using a
  capability the main agent already has. v4 keeps everything v3 got right (the spine's
  *order*, the four-channel activation, the discovery/delivery split, the test relaxation,
  the onboarding flow) and changes only the *membership* mechanism: fixed → flexible.

### Option 3 — Flexible-entry Hackathon Spine (CHOSEN — v4)

When the flag is on, the task is placed on a fixed-*order* spine at a user-declared,
NL-inferred entry point; everything upstream is skipped; mid-task movement is free; the
verifier runs by default and is skippable.

- **Pro 1 — per-task adaptivity is restored.** The user enters low for a tiny task, high
  for a design-heavy one — calibrating process weight per task within a project-scoped
  mode. v3's Objection 2 is *resolved by the mechanism*, not merely mitigated.
- **Pro 2 — no classifier.** The 2-path rule-based selector is removed; NL inference (an
  existing capability) replaces it. One mechanism removed, nothing of comparable weight
  added — v4 is net-simpler than v3.
- **Pro 3 — every added behavior reuses an existing channel.** Entry inference is prompt
  comprehension; movement is orchestrator mediation; the skip/movement record is ordinary
  `PROGRESS.md` phase-transition lines; the worktree-by-entry-point policy is a refinement
  of the existing isolation rule. No new selector, no new signal channel, no new actor, no
  new artifact.
- **Pro 4 — honest about its cost.** v4 does not pretend skipping the architect/planner/
  verifier is free. It names the cost (the rigor guarantee is given up) and answers it with
  transparency (skipped rigor is recorded and auditable).
- **Con — the construction-guarantee of rigor is given up.** A v4 hackathon change can
  ship with little or no Praxion process applied (enter at `implementer`, skip the
  verifier). This is a genuine, material reduction in rigor compared to v3's hackathon mode
  and to every other Praxion tier. Accepted: the user chose maneuverability explicitly and
  with eyes open; hackathon mode is opt-in and project-scoped; and the cost is mitigated by
  the skipped-rigor-transparency safety net — skipping is a deliberate, recorded choice,
  never an invisible erosion. The mitigation makes the cost auditable, not zero — a
  graduating PoC must treat the `PROGRESS.md` skip-record as a retro-apply checklist.

### Option 4 — A sixth tier in the 5-tier table

Add a `Hackathon` row to Direct/Lightweight/Standard/Full/Spike.

- Con: **largest always-loaded blast radius** — a permanent new row plus a fast-path
  selector line plus a tier-selector branch every project evaluates (~120–150 always-loaded
  tokens, permanently, for *all* projects). Rejected.

### Option 5 — A per-task "hackathon profile" passed per pipeline run

The user tags individual tasks as hackathon.

- Con: the user's requirement is explicit — a *project-scoped* mode set up once at
  onboarding. A per-task tag has no propagation home (the env var is session/project
  scoped) and re-introduces a per-task decision. And flexible entry (Option 3) *already*
  gives per-task adaptivity — the entry point is a per-task choice *within* a
  project-scoped mode. Rejected.

### Sub-options carried forward unchanged (re-validated as mechanism-independent)

- **Wrapper shape — Shape B ("skill-nuclear"), CHOSEN.** Shape A omits the skill-surface
  trim; Shape C (`--bare` re-injection) is brittle for a marginal saving over B.
- **Activation channel count — four channels, CHOSEN.** Env var alone reaches hooks but not
  agents; env var + CLAUDE.md block reaches both but trims no context; + the rule preset
  trims ~3,500 ambient tokens; + the CLI wrapper adds the launch-time skill trim only a CLI
  flag can deliver.
- **Test-discipline — single-switch relaxation bundled into `PRAXION_HACKATHON_MODE`,
  CHOSEN.** Independently tunable flags create eight combinations and an onboarding
  decision the user cannot make on a fresh PoC; dropping tests entirely contradicts
  "still maintaining some of the harnesses."

### Folding the creative-blocker into user-driven movement — the sub-decision

v3 had a separate agent-driven creative-blocker loop-back, capped at one re-invocation. v4
folds it into user-driven movement: the agent raises a signal and *pauses*; the *user*
decides whether to loop.

- **Considered — keep both with an actor-based distinction** (user-driven = unbounded,
  agent-driven = capped at 1). Workable, but it keeps two movement mechanisms and an
  orchestrator loop counter.
- **Chosen — fold them.** The agent raises `CREATIVE-BLOCKER:` and stops; the user decides.
  Simpler (one mechanism, no counter, no auto-re-invocation logic) and the termination
  guarantee is *stronger*, not weaker: v3's cap bounded an autonomous agent loop, whereas
  v4 *removes* the autonomous loop — a human gates every loop. The single preserved rule —
  a blocked agent stops and yields rather than pushing through or re-raising — is what
  makes the fold safe.

## Consequences

**Positive:**

- Per-task process adaptivity is restored — v3's Objection 2 (fixed pipeline shape) is
  resolved by the mechanism. The user enters the process where the task needs it.
- The rule-based 2-path auto-classifier is removed — one fewer mechanism to define, test,
  and keep coherent. NL entry inference does the same job with an existing capability.
- No rigor-pass mechanism is built — reviewing hackathon output is ordinary conversation,
  not new machinery.
- Every v4 behavior reuses an existing channel — NL inference, `PROGRESS.md`
  phase-transition lines, the orchestrator as mediator, the existing worktree-isolation
  rule. No new selector, signal channel, actor, or artifact. v4 is net-simpler than v3.
- Zero behavioral change for non-opted-in projects — one env-var read at hook startup and
  one ~25-token behavior-inert pointer sentence. The independence guarantee holds with one
  named exception.
- Discovery runs full-strength when it runs; only delivery ceremony is relaxed.
- The smallest always-loaded blast radius of all mechanism options.
- ~2,975 always-loaded tokens saved ambiently on opted-in projects; ~8,000–11,000 on a
  wrapper launch; plus variable per-pipeline savings from skipped ceremony artifacts.
- The relaxed test discipline removes paired-step ceremony for trivial smoke tests and
  stops a known-red test from freezing PoC iteration.
- The verifier is default-on — the fast "no verification" path requires a deliberate
  opt-out, not an accident.
- Skipped rigor is auditable — a reviewer or a graduation audit can reconstruct exactly
  what process was applied to any change; a graduating PoC has a ready-made retro-apply
  checklist.
- No agent-prompt changes; the one agent file that changes (`agents/sentinel.md`) gains
  only an additive, flag-gated check.

**Negative:**

- **The construction-guarantee of rigor is given up** — a v4 hackathon change can ship
  with little or no Praxion process applied (architect + planner + verifier all skipped).
  This is the central honest cost (Objection 1 in `SYSTEMS_PLAN.md`). Mitigated, not
  eliminated, by the skipped-rigor-transparency safety net: skipping is recorded and
  auditable; the residual risk — that the record shows *that* rigor was skipped, not *what*
  it would have caught — is named and accepted, with the upgrade-recovery retro-apply
  checklist as the recovery path.
- The main agent's entry-point inference is a judgment, not a rule — it can mis-infer.
  Mitigated by ask-on-ambiguity, by recording the inferred entry in `PROGRESS.md` (the user
  sees and can correct it), and by free mid-task movement (one-sentence re-route).
- The calibrated Register-Objection hold-list (security surface / data-loss risk / hidden
  scope) is a heuristic — the main agent can miss a hold-worthy case or hold on a
  non-hold-worthy one. Mitigated by the concrete signal list and by the skip-transparency
  record (a missed hold is at least visible afterward).
- The advisory green-gate means a red or absent test no longer blocks the pipeline; a PoC
  can graduate carrying test debt. Mitigated — every red test and zero-test gap is a
  prominent WARN, the exit path prompts a coverage pass, the sentinel graduation check
  prompts upgrade-recovery.
- The mode's state lives in three persistent artifacts plus one launch-time behavior;
  drift is possible. Mitigated by the Phase 5b installer writing all six artifacts together
  and a SessionStart consistency check.
- The wrapper is bypassable — `claude --resume` and a direct `claude` launch get the mode
  but not the skill-surface trim, with no error. Mitigated by the `[hackathon]` PS1 marker,
  documentation, and graceful degradation (the mode itself still works).
- Context trimming has a hard floor — the four `core` rules (~10,246 tokens) and both
  CLAUDE.md files (~7,102) are immune to every hackathon mechanism. Larger reductions need
  upstream Claude Code changes or surgery on Praxion's own core rules — filed as a
  tech-debt follow-up, out of scope here.
- Hackathon mode is a second behavioral path; every future pipeline change must keep both
  paths coherent. Mitigated by Guardrail 1 — both paths exercised in Praxion's CI.

## Prior Decision

This v4 ADR **supersedes the v3 mechanism within the same draft** — the fragment id
`dec-draft-ef6b8065` is retained across revisions because the decision is the same
*decision* (how hackathon mode is activated and integrated), re-resolved. v2 chose a
*tier-bias toward Lightweight* (self-contradictory — it removed the architect and planner);
v3 replaced it with a *fixed named Hackathon Pipeline behind a 2-path auto-classifier*; v4
replaces *that* with a *flexible-entry Hackathon Spine the user enters by natural language,
moves around in freely, and exits*.

The reason for the v3→v4 change: a fixed pipeline, while it guaranteed rigor by
construction, gave up the per-task process adaptivity the 5-tier selector existed to
provide (v3's own Objection 2), and it carried a rule-based 2-path classifier that
natural-language entry inference makes redundant. After a full Q&A round on v3, the user
chose maneuverability — the ability to enter the process where a task needs it and move
between stages mid-task — accepting, explicitly and with eyes open, that this gives up the
construction-guarantee of rigor. v4 resolves the resulting safety question not by
re-imposing the guarantee but by making skipped rigor visible and auditable (every skip and
movement recorded in `PROGRESS.md`).

The four-channel activation, the wrapper (Shape B), the discovery/delivery split, the
test-discipline relaxation, the onboarding Phase 5b, the independence guarantee, the
reversibility model, the subagent model preset, and the three guardrails are **carried
forward from v3 unchanged** — re-validated as mechanism-independent (they depend on the
`PRAXION_HACKATHON_MODE` switch and the `## Hackathon Mode` CLAUDE.md block, not on how the
pipeline's membership is determined). The Spike-absorption position is carried forward, its
argument strengthened (a spike-shaped task's NL framing naturally infers an entry at the
discovery front). **New in v4:** the flexible-entry-spine mechanism; natural-language entry
inference with ask-on-ambiguity; the removal of the 2-path auto-classifier; the calibrated
Register-Objection on skipping the architect; free user-driven mid-task movement with the
creative-blocker case folded in as raise-and-pause; the verifier default-on/skippable rule;
the Acceptance-Criteria-without-an-architect paths; the worktree-policy-by-entry-point
refinement; and the skipped-rigor-transparency safety net. The explicit non-decision: no
rigor-pass mechanism is built.
