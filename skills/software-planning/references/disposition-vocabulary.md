# Disposition Vocabulary

Shared vocabulary for recording the outcome of a Continuous Improvement Signal (CIS) or a rework-loop finding. Both surfaces use the same three terms so the ecosystem speaks with one voice across forward-feeding (researcher → architect) and backward-feeding (verifier → architect/planner) flows. Back to [SKILL.md](../SKILL.md).

---

## switch-now

Act on the signal in the current task.

**Use when**: the cost of waiting exceeds the cost of incorporating the change
now; the improvement is directly in scope; or deferring would widen the blast
radius of the eventual switch.

The architect documents *why deferring would cost more than acting now* and
adds the migration work to the implementation plan.

---

## defer-with-rationale

Keep the incumbent for this task; schedule the change for later.

**Use when**: the signal is real but the switch is out of scope, the timing
is wrong, or an ecosystem milestone is needed first.

A deferred signal is the canonical input for a `.ai-state/TECH_DEBT_LEDGER.md`
row, filed by the verifier, sentinel, or orchestrator from the documented
rationale. The architect documents the criteria that would justify a future
switch (a performance threshold, an ecosystem milestone, a maintenance event).

---

## dismiss-with-rationale

Decline the signal with a stated reason.

**Use when**: the candidate does not improve on the axes the project actually
cares about, or the comparison the researcher drew does not hold under the
project's real constraints.

Silent dismissal is a behavioral-contract violation (Register Objection):
every dismissed signal requires a written reason. Dismissal is legitimate;
unexplained dismissal is not.

---

## Consuming surfaces

Two distinct surfaces use this vocabulary. Both record a disposition for each
signal or finding they receive; the vocabulary is the shared contract between them.

**Continuous Improvement Signals (CIS) — forward-feeding.**
The researcher surfaces a signal in `RESEARCH_FINDINGS.md § Continuous Improvement
Signals`. The systems-architect reads that section during Phase 7 (Trade-off
Analysis) and records a `switch-now`, `defer-with-rationale`, or
`dismiss-with-rationale` disposition in `SYSTEMS_PLAN.md` (and, for
load-bearing decisions, in an ADR fragment).

**Rework loop — backward-feeding.**
The verifier emits a `REWORK_MANIFEST.md` row for each clustered finding.
The systems-architect (always first in the rework routing chain) and the
implementation-planner apply the same vocabulary when deciding how to
address each manifest row. `/resume-rework` surfaces the disposition to
the user during the fresh-session dispatch.

---

## How to cite

Agent prompts and skill references should link here using a relative path:

```
See [disposition vocabulary](../skills/software-planning/references/disposition-vocabulary.md)
for the three options.
```

For files inside `skills/software-planning/references/`, use:

```
See [disposition vocabulary](disposition-vocabulary.md) for the three options.
```
