# Agent-Era Performance

Token budget, context-window efficiency, spawn cost, and pipeline wall-clock as first-class performance quantities for agentic systems -- with the same rigor this skill applies to latency and throughput. Back to [SKILL.md](../SKILL.md).

This file extends the skill's existing frames rather than re-deriving them: Amdahl's Law, Little's Law, and cost-per-unit-of-work already cover the mechanics -- what's new is *which resource* an agentic system spends, not a new theory of how systems behave under load.

## Token Budget as a Capacity Constraint

Reframe "always-loaded context" as a **fixed cost** and "on-demand context" as a **marginal cost** -- the direct agent-era analogue of fixed vs. variable cost in classical capacity planning:

- **Fixed cost**: content loaded on every invocation regardless of task -- system prompt, CLAUDE.md files, unconditional rules, the skill/agent name+description listing. Paid whether or not the task needs it.
- **Marginal cost**: content loaded only when relevant -- a skill body on activation, a reference file on demand, a subagent's own context window. Paid once, by the task that needs it.

**Progressive disclosure is the optimization technique for this constraint** -- structurally identical to caching's role for I/O cost. Just as a cache-aside strategy defers an expensive fetch until it's actually needed, progressive disclosure (metadata -> instructions -> resources, see the `skill-crafting` skill) defers token cost until content is actually relevant. Treat a bloated always-loaded surface as you would an unbounded cache: it pays a cost on every request whether or not that request needed it.

**The basis-dependent measurement gotcha.** A token budget claim is only as good as the basis it was measured against -- *which files are actually loaded, for whom, in what state*. Two failure modes:

1. **Wrong basis** -- measuring against a stale file list (a rule that was deleted, a skill that got merged) silently under- or over-counts. Re-measure the basis before trusting a cached figure; don't reuse a number from a prior session without re-deriving it.
2. **Ceiling adjacency** -- when a budget is already near its ceiling (e.g., a 25,000-token always-loaded budget sitting at 95%+ utilization), even a one-line addition can tip the total over. At that point, the marginal cost of *any* new always-loaded content dominates the decision -- prefer a cross-reference to existing content over restating it, and take the measurement (`scripts/measure_token_budget.py`) before deciding placement, not after. Do not estimate from a chars-per-token divisor: measured against a real tokenizer, the divisors in common circulation err by 5-8% in both directions, which is enough to invert a near-ceiling verdict.

The `rule-crafting` skill's "Why the Always-Loaded Budget Exists" and `skill-crafting`'s progressive-disclosure sections carry the mechanics of *how* to measure and stay under budget in this ecosystem -- this file only establishes that token budget is a capacity constraint in the same sense as connection-pool size or queue depth, subject to the same measure-before-optimize discipline.

## Context-Window Efficiency

Attention is the scarce resource, not context-window size. A token spent on irrelevant content is not neutral -- it **displaces** attention from relevant content (context rot: retrieval accuracy degrades as irrelevant tokens accumulate, independent of whether the window has room left). This reframes the optimization target:

- **Wrong metric**: raw context size ("we're at 40k of 200k tokens, plenty of room").
- **Right metric**: relevance-per-token -- the fraction of loaded content the task actually uses. A context window that is 30% full of irrelevant history has a worse effective signal-to-noise ratio than one that is 80% full of relevant content.

Practical consequence for design reviews: when a design introduces new always-loaded context (a rule, a CLAUDE.md block, an unconditionally-injected agent field), ask whether it will be relevant in the large majority of invocations. If not, it is a context-window efficiency cost even when the raw token count is small -- the same "every always-loaded token must earn its attention share" bar the ecosystem already applies to rules and CLAUDE.md, generalized to any performance review of an agentic design.

## Spawn Cost and Fan-Out

A subagent spawn is a **discrete, chunky cost unit** -- not a marginal increment like an extra loop iteration. It carries fixed overhead (new context window, tool-permission setup, prompt-cache miss on first call) before any useful work happens. This changes how fan-out should be evaluated:

- **Fan-out multiplies the discrete unit.** N independent subagents cost roughly N times the per-spawn overhead, on top of their actual work -- not free parallelism.
- **Concurrency caps bound the multiplication.** A cap (e.g., 2-3 concurrent agents) is the agent-era equivalent of a connection-pool size limit: it prevents fan-out from overwhelming the substrate (rate limits, coordination overhead, review burden on the human) the same way an oversized connection pool overwhelms a downstream database.
- **The right question is cost per useful outcome, not cost per call.** This is the skill's existing "measure cost per unit of work" framing (see [capacity-planning.md § Cost-Performance Optimization](capacity-planning.md#cost-performance-optimization)) applied verbatim: a cheap spawn that produces a discarded or redundant result is worse value than an expensive spawn that resolves the task in one pass. Don't optimize spawn count in isolation -- optimize spawns-per-resolved-task.

Before fanning out, apply the same multiplicity check any capacity decision would: does the work actually decompose into independent units, or is the fan-out manufacturing parallelism where a single pass would do?

## Pipeline Wall-Clock

**Amdahl's Law applies to multi-agent pipelines almost without modification** (see this skill's Core Principles): pipeline wall-clock latency is bounded by the serial fraction of the pipeline, not the sum of all agent work. Map the pipeline the same way you'd map any critical path:

- **Barriers serialize.** A stage that must wait for every upstream input before starting (e.g., a synthesis step that reads all fan-out results) is on the critical path regardless of how fast the fan-out stages ran individually.
- **Independent stages pipeline.** Stages with disjoint inputs and no ordering dependency can run concurrently -- this is the "parallelizable fraction" Amdahl's Law credits toward speedup.
- **The floor is the longest dependency chain**, not total agent-seconds. Adding more concurrent agents past the width of the widest independent stage does not reduce wall-clock -- it only adds spawn cost (see above) without shortening the critical path.

This is a direct restatement, not a new derivation: identify the critical path (Step 2 of this skill's methodology), classify each pipeline stage as sequential or parallelizable, and the existing Amdahl reasoning transfers. The only agent-era addition is that "serial fraction" now includes coordination artifacts (a synthesis document that must be fully written before the next stage can read it) alongside classical serial computation.

## Measurement Discipline

A performance budget that is never measured is an assertion, not a budget. State how each agent-era quantity is actually observed:

| Quantity | How it's observed | Recoverable after the fact? |
| --- | --- | --- |
| Token budget (always-loaded) | `scripts/measure_token_budget.py` — real tokenizer, file set encoded in the script | Yes -- static files, re-measurable anytime |
| Context-window efficiency | Harder to measure directly; proxy via task success rate as irrelevant content grows, or manual review of what a session actually referenced | Partially -- requires session transcripts |
| Spawn cost per agent | Wall-clock + token cost captured at spawn time (harness telemetry, `PROGRESS.md` timestamps) | **No, unless captured at the time** -- post-hoc reconstruction from logs is unreliable once the session ends |
| Pipeline wall-clock | Timestamp delta between pipeline start and terminal marker, cross-referenced against `PROGRESS.md` phase transitions | Yes, if phase-transition timestamps were logged; no, if they weren't |

The asterisk on spawn cost is the operative constraint: **per-spawn cost is unrecoverable unless captured at the time.** This makes instrumentation-before-optimization a prerequisite for this dimension specifically, not a general nicety -- the skill's "Measure Before Optimizing" principle already establishes profiling-before-optimizing as the default; for spawn cost, the window to measure is exactly the spawn itself, so instrumentation must be designed in before the first agent runs, not added retroactively once fan-out looks expensive.
