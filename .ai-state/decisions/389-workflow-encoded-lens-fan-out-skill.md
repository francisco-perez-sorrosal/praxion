---
id: dec-389
draft_id: dec-draft-81c7a00e
title: "Workflow-encoded lens fan-out: a user-invocable skill carrying its own workflow script, plus an instrument/guard pair — isolation by construction, prose stays canonical"
status: accepted
category: architectural
date: 2026-09-21
summary: "Adds skills/lens-fanout/ (a user-invocable, disable-model-invocation skill) and its scripts/lens-fanout.js Workflow script, which collects N lens agents as parallel() closures that cannot read a sibling and reconciles in one aggregator returning a pointer, never a payload; adds scripts/workflow_run_cost.py (per-run cost instrument, never gates) and scripts/check_lens_isolation.py (the dec-378 executable guard, exits 1 on contamination and 2 rather than passing vacuously) over a shared scripts/_workflow_run.py resolver. The prose fragment-file protocol stays canonical and portable; the workflow is an additional enforcement path for one assistant. agentType is deliberately omitted in v1."
tags: [process-economy, roadmap-p3-2, workflow-tool, lens-independence, fan-out, skills, measurement-instrument, quality-guard, opt-in, pointer-not-payload]
made_by: agent
agent_type: systems-architect
branch: worktree-process-economy-p3-2-adopt
pipeline_tier: standard
affected_reqs: [REQ-01, REQ-02, REQ-03, REQ-04, REQ-05, REQ-06, REQ-07, REQ-08, REQ-09, REQ-10, REQ-11, REQ-12, REQ-13]
re_affirms: dec-378
affected_files:
  - skills/lens-fanout/SKILL.md
  - skills/lens-fanout/scripts/lens-fanout.js
  - scripts/workflow_run_cost.py
  - scripts/check_lens_isolation.py
  - scripts/_workflow_run.py
  - skills/multi-perspective-analysis/SKILL.md
  - skills/multi-perspective-analysis/references/lens-independence.md
  - agents/researcher.md
  - .ai-state/DESIGN.md
dissent: "The mechanical guarantee is bought with a permanent human action and a second, Claude-Code-only path; the portable prose fan-out it protects stays the one every other assistant — and most sessions — actually use."
---

## Context

Praxion's lens-independence mandate says parallel lens agents must not read each other during collection. The
P3.2 spike established, by reading the code rather than by argument, that today's enforcement is **prompting
discipline only**: fragment files prevent a *mid-run read of the canonical path* because no sibling has written
it yet, but nothing mechanically stops an orchestrator from pasting a sibling's draft into a lens prompt. The
spike's H3 — a script that holds lens results in variables and reconciles in a final call satisfies the mandate
*by construction* — scored "confirmed, strongest of five", because `parallel()` thunks close only over
pre-fan-out values and have no mechanism to read a sibling's in-flight result.

The spike deferred adoption on one blocking reason: workflow-spawned agents were invisible to Praxion's cost
accounting, because the transcript resolver and the baseline glob both keyed on the Agent-tool path
(`subagents/agent-<id>.jsonl`) while workflow agents file one level deeper
(`subagents/workflows/<run>/agent-<id>.jsonl`). That named trigger was resolved as a Lightweight item and
verified live: a fresh run now produces `agent_stop` rows with `usage_source: subagent-transcript`, populated
tokens, model and duration. P3.2 adopt-for-research-lenses became unblocked, needing its own design.

Three facts from the spike constrain every option below and are not re-derived here: the Workflow tool runs only
on human opt-in (a model-invoked launcher fails the rule outright); the script has **no filesystem access**, so
every artifact write is an explicit instruction inside an `agent()` prompt and every filesystem check must move
before the launch or after the return; and the two recovery mechanisms do not compose — `resumeFromRunId` is a
same-session cache replay, `/resume-pipeline` reconciles from ground truth — so adopting the tool retires no part
of the existing machinery.

## Decision

Add one capability composed of five new files and three one-insertion prose seams.

1. **`skills/lens-fanout/SKILL.md`** — a user-invocable skill with `disable-model-invocation: true`, whose body
   runs, in the main session: an honest-uncertainty gate that *refuses* when it cannot name ≥2 plausible rival
   answers; lens derivation (2–6, `--lenses` overriding, confirmed with the user when derived); a pre-flight that
   resolves the slug and sources, **refuses to overwrite an existing `RESEARCH_FINDINGS.md`**, and mints the
   timestamp; the `Workflow` call; verification of every returned path against disk; and a report that is a
   pointer plus per-lens markers, never the findings body.
2. **`skills/lens-fanout/scripts/lens-fanout.js`** — referenced by `scriptPath`, never inlined in prose and never
   registered per-project. A pure `meta` literal with `Collect`/`Reconcile` phases; an envelope guard that refuses
   an invalid lens set without spawning; `parallel()` over one `agent()` thunk per lens, each prompt naming only
   its own lens and its own fragment path; `log()` of dropped lenses **by name** before `.filter(Boolean)`; one
   aggregator `agent()` that reads the fragments from disk and writes `RESEARCH_FINDINGS.md` with a
   `## Divergence Map`; and a typed return carrying paths, markers and counts but **no lens prose**.
3. **`scripts/workflow_run_cost.py`** — a per-run cost *instrument* (never gates; exit 0 with data, exit 2 with a
   named reason). Joins `journal.jsonl` → `agent-<id>.meta.json` → `agent-<id>.jsonl` → WAL `agent_stop` rows →
   the main-session transcript, on `agent_id` throughout. Emits one row per workflow agent carrying both the
   transcript-derived and the WAL-derived figures plus an explicit `wal_agreement` verdict; a separate section for
   unattributable helper stops, labelled as a time-window heuristic; and an `orchestrator` section giving the
   main-session context at the launch turn and the next assistant turn. Workflow-generic: it knows about `phase`,
   not about lenses, so the next fan-out reads with the same instrument.
4. **`scripts/check_lens_isolation.py`** — the executable *guard*. Searches each `Collect` transcript for every
   sibling's **artifact identity** (fragment path, agent id, returned summary verbatim) — never bare lens labels,
   which are ordinary domain words — exempts the aggregator explicitly, exits 1 with an `LI01` per violating pair,
   and **exits 2 when it can see fewer than two `Collect` transcripts** rather than reporting "clean".
5. **`scripts/_workflow_run.py`** — the private sibling module owning run resolution (`--run <wf_id|latest>`),
   journal parsing, transcript iteration and the context-token convention, so the run-directory layout has exactly
   one definition.

`agentType` is **omitted** in v1. Proposer agents name `model` from `args` (defaulting to `sonnet`); the
aggregator omits `model` and inherits the session's frontier model, which satisfies the proposer/aggregator recipe
without naming a second model. `resumeFromRunId` is never passed.

The prose protocol is untouched and stays canonical: fragment files, `lens-independence.md`, the coordination
protocol's multiplicity paragraph and the Agent-tool fan-out all remain the portable path for every other
assistant. The workflow is an **additional** enforcement path for Claude Code, never the only one. The
always-loaded surface changes by zero bytes (measured: 16,606 / 25,000 tokens, unchanged); the three seams cost
734 bytes across files that are on-demand, gated, or per-spawn.

## Considered Options

### A. Workflow-encoded fan-out behind a user-invocable skill, prose retained (chosen)

- **Pros.** Isolation becomes a property of the program: `parallel()` closures have no mechanism to read a
  sibling, which is strictly stronger than the prompting discipline it supplements. The orchestrator's context
  stays flat regardless of N (the spike measured 205,762 → 208,358 for a two-agent run with a 175-byte return).
  Every run is now costed per agent by a shipped reader, so the economy claim is falsifiable. The guard makes the
  mandate checkable rather than merely stated.
- **Cons.** The launch is permanently a human action — the "orchestrator-mediated fan-out" the roadmap wanted to
  delete is *relocated*, not removed. Claude-Code-only, so the portable path must be maintained in parallel. Every
  artifact write is re-stated per prompt because the script cannot touch the filesystem. Adds a second, narrower
  recovery window that composes with nothing.

### B. Prose-only fan-out with fragment files (the steelmanned runner-up)

- **Pros.** Zero new components, zero new files, portable across Codex/Cursor, no launcher, no second recovery
  path, and the orchestrator can start a fan-out itself the moment it judges one warranted — which is precisely
  what a mechanically-isolated path *cannot* do. The isolation failure it permits is hypothetical: no recorded
  Praxion run has actually contaminated a lens prompt.
- **Cons.** The guarantee is unfalsifiable in both directions — there is nothing to check, so "we isolate our
  lenses" is an assertion no instrument can support or refute. Under `dec-378` that is exactly the class of claim
  that needs a measured cost and an executable guard, and the prose path can supply neither.

### C. Inline the script in the skill body, or register it under `.claude/workflows/`

- **Pros.** Inlining matches the tool's own "preferred on the first run" advice; a registered named workflow is
  invoked by name with no path resolution at all.
- **Cons.** Inline JavaScript in prose is unparseable by `node --check` and by CI, and carries ~4 KB into context
  on every invocation. A `.claude/workflows/` file is per-project state a plugin cannot install, forking the
  script per project. Both forfeit the single testable source of truth.

### D. Fold the per-run reader into `context_baseline.py` as a `--run` mode

- **Pros.** One fewer file; the transcript-walking code already lives there.
- **Cons.** A different estimand (one run, per-agent rows vs. project-wide percentiles) means a second report
  schema inside a 511-line module; and it would make the mutation sensor's target that module rather than the new
  code, diluting the survivor signal the `mutation: on` step exists to produce. Combining the instrument and the
  guard in one script was rejected for a sharper reason: the reader must never gate and the guard must gate, so one
  exit code would have to mean two things.

### E. Use `agentType: 'praxion:researcher'` for the lens agents

- **Pros.** Praxion's research discipline — evidence classes, per-claim confidence, fetched-content-as-data
  hardening — arrives with the agent instead of being cited.
- **Cons.** `agents/researcher.md` is 27,317 bytes of *pipeline* obligations: a ten-section `RESEARCH_FINDINGS.md`,
  five phases, a turn budget, a partial-output protocol. A lens agent wearing that prompt and then told "write only
  your own fragment" is a prompt at war with itself — and `RESEARCH_FINDINGS.md` is the file the **aggregator**
  owns, so a researcher-typed lens agent would plausibly write it and clobber the aggregator's artifact. Resolution
  of custom types inside a workflow was also unverified. Rejected in v1; the lens prompt cites the one discipline
  it needs instead.

## Consequences

**Positive.** Lens independence gains a mechanical enforcement path and, for the first time, a guard that can
refute it. Every workflow run — this fan-out and every future one — has an attributable per-agent cost, which is a
prerequisite for the cost dashboard regardless of this capability. The orchestrator's context cost of a fan-out
becomes independent of N. The instrument/guard split leaves two scripts whose exit codes each mean one thing, in
the naming families a reader already knows.

**Negative.** Praxion now maintains two enforcement paths for one mandate, and the mechanical one is
assistant-specific. A fan-out cannot be initiated by an agent — including the roadmap-cartographer, whose per-lens
fan-out stays on the Agent-tool path indefinitely. The workflow script is a behavioural surface no test executes:
`node --check` proves syntax only, and the sole behavioural evidence before merge is one live dogfood, which is why
both the script and the skill body carry `review: force`. Three assumptions remain live until that dogfood —
plugin-root `scriptPath` resolution, whether the always-on rules reach workflow agents, and whether `agent()`
accepts the `sonnet` model string — each with a named fallback that changes no structure.

**Neutral.** The prose protocol's byte footprint is unchanged apart from 734 bytes of seams on non-always-loaded
files; the always-loaded budget is measured unchanged. No dependency, no hook, and no rule changes.

## Disconfirmation

**Falsifier.** Name the components: `skills/lens-fanout/` (a new member of the `Skills` artifact family) with its
own `scripts/lens-fanout.js`, plus `scripts/workflow_run_cost.py`, `scripts/check_lens_isolation.py` and
`scripts/_workflow_run.py` as new members of the `Scripts` family; and the responsibility "guarantee that a lens
agent cannot read a sibling" moves from the orchestrator's prompting discipline to the workflow runtime, with
"prove it per run" moving from nobody to a named guard script. That is what makes this `architectural` rather than
`behavioral`. It adds **no** `DESIGN.md` §3a structural row and no LikeC4 element — both catalogs are enumerated by
filesystem scan, the same disposition taken for the ADR-checkpoint and mutation-sensor scripts.

The decision is **wrong** if any of three things is observed: (a) a `Collect`-phase transcript from a real run
contains a sibling's fragment path, agent id, or returned summary — the isolation claim is then false and the whole
rationale collapses, since the prose path is cheaper and portable; (b) `workflow_run_cost.py` shows the workflow
path costing more than the Agent-tool path for the same N and the same question, on two separate dogfoods — the
economy claim is then refuted and the capability is paying for a guarantee nobody needed; (c) the guard's first
real finding turns out to be a false positive — a guard that cries wolf gets disabled, and a disabled guard is
`dec-378` non-compliance wearing a green checkmark.

**Steelmanned runner-up.** Option B, prose-only fan-out with fragment files. Its strongest form is not "cheaper" but
*"the guarantee is not the bottleneck"*: in the entire recorded history of Praxion pipelines there is no instance of
a contaminated lens prompt, so the mechanism being purchased here protects against a failure that has never
occurred, at the price of a permanent human action in the launch path, an assistant-specific fork of the mandate,
and a script surface no test executes. Under Simplicity First, a guarantee with no observed violations is exactly
the kind of thing that should stay a convention. The counter that decided it is `dec-378`, not comfort: the prose
path cannot produce either a measured cost or an executable guard, so "we isolate our lenses" would remain an
assertion no instrument could check — and the same argument ("it has never happened") is what every zero-variance
self-graded instrument said before someone measured it.

**Reversal trigger.** Revisit when any of these fires: the harness lifts the human-opt-in rule or makes workflow
agents hook-reachable (the launcher's reason to exist changes, and an agent-initiated fan-out becomes possible); a
`disable-model-invocation` skill stops being user-only (the opt-in guarantee silently evaporates); two dogfoods show
the reader measuring the workflow path above the Agent-tool path at equal N (falsifier (b)); or the isolation guard
records zero findings across ten runs *and* the prose path records zero contamination incidents over the same window
— at which point the guard has demonstrated no variance and should be re-justified rather than kept on faith.
