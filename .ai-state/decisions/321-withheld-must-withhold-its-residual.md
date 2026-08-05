---
id: dec-321
title: A withheld class withholds its residual, and a plugin-owned oracle resolves from the plugin
status: accepted
category: behavioral
date: 2026-08-05
summary: 'When an oracle is unavailable, adr_health withholds the `vanished` residual as `unclassified` rather than emitting it as a retirement candidate, and resolves the lifecycle table from the project root first and the plugin second — because the table is plugin reference data no managed project installs.'
tags: [adr-health, decision-health, withholding, oracle, lifecycle-table, fleet, managed-projects, gate-liveness]
made_by: agent
agent_type: orchestrator
branch: main
pipeline_tier: standard
affected_files:
  - scripts/adr_health.py
  - scripts/test_adr_health.py
  - agents/sentinel.md
  - commands/decisions.md
---

## Context

`adr_health.py` classifies every `affected_files` reference that no longer resolves into one of
seven decay causes, because only one of them (`vanished`) means *retire* and a naive existence check
inverts the truth on every "remove X" decision. Its stated contract, repeated in the module
docstring, the script catalog, and the sentinel's own dimension text, is that when an oracle is
unavailable the classes depending on it are **withheld with a named reason rather than defaulted**.

Two facts, found together, showed the contract was not being kept.

**The residual was defaulted, not withheld.** The history oracle honours the contract: with no git
history, references return `unclassified` with no disposition. The lifecycle oracle did not. With
the artifact-inventory table unreadable, the `lazy-artifact` check was simply skipped and control
fell through to `vanished` / `retire-candidate` — the single highest-consequence disposition the
tool produces. Measured on the live corpus with the oracle stubbed out: 85 findings both ways, and
exactly the three `lazy-artifact` rows re-emerged as retirement candidates while `withheld` said
they had been suppressed. The report warned the reader in the opposite direction from the truth.

**And that state was permanent for the fleet.** The table was resolved only as
`repo_root / skills/software-planning/references/artifact-inventory.md`. No onboarding phase writes
that file into a managed project, so for every project except this repository the oracle was
unavailable on every run, forever — and by the first defect, every ADR citing an artifact whose
absence the inventory declares expected became a standing retirement candidate. The shipped
`/decisions` command is the surface that acts on those candidates.

The two compound: the first is a bug anywhere, the second makes it the *only* behaviour the fleet
ever sees, in the one environment where it is invisible to the author.

## Decision

**`vanished` is a dependent class, and is withheld with its oracle.** It does not mean "nothing
matched"; it means every repair class was *tried* and none matched, which is true only when every
oracle answered. A shared `_residual()` helper now returns `unclassified` / no disposition whenever
the lifecycle oracle is unavailable, mirroring what the history oracle already did. Positive
attributions (`renamed`, `removed-by-self`, `removed-by-later`) are unaffected: those carry
evidence and remain correct with or without the table.

**The lifecycle table resolves from the project root first, the plugin's own tree second.** The
decision corpus is consumer state and keeps resolving from `repo_root`. The table is *plugin
reference data* — it declares what each shipped artifact's absence means — so it resolves from
`SCRIPT_DIR.parent`, which is the plugin root for an installed copy and this repository for a
checkout. A project that ships its own table still wins.

`unclassified` gains the named reader it lacked: the sentinel's decision-health dispatch reports it
alongside the withheld note, and DH03 states that a run with a non-empty `withheld` has a *smaller*
candidate list rather than a cleaner corpus.

## Considered Options

### Withhold the residual (chosen)

Keeps the contract the three documents already assert. Costs one helper and one branch.
**Con:** an operator who reads only the class counts sees `vanished` drop without reading why —
mitigated by the sentinel and `/decisions` both being instructed to read `withheld` first.

### Keep emitting `vanished`, and rely on the `withheld` note to warn the reader

The status quo. Rejected: the note names the suppressed class while the finding names the
disposition, and the reader acts on the disposition. Asking every consumer to cross-reference two
fields to avoid a wrong retirement is a contract that will be broken the first time someone is in a
hurry.

### Ship the lifecycle shapes as a constant inside the detector

Would make the oracle unconditionally available everywhere, with no path resolution at all.
Rejected: it duplicates the inventory table into a second textual site, which the gate-liveness rule
names as an anti-pattern — the two would drift, and the drift would be silent.

### Install the inventory into every managed project during onboarding

Rejected as a larger contract change for no gain. The file describes artifacts the *plugin* defines;
a project has no reason to own a copy, and a copy is one more thing to keep in sync.

## Consequences

**Positive.** The contract now holds in both directions, and is pinned by an invariant test asserting
that no finding carries `retire-candidate` while `withheld` is non-empty — stated over the whole
report rather than one path, because the leak was in a shared residual. The fleet gains the class
outright: a managed project citing a threshold-lazy artifact now classifies it as `lazy-artifact`
with no disposition, where before it was a withheld-but-emitted retirement candidate.

**Negative.** The detector now reads a path outside `repo_root`, which is a resolution rule a future
reader could mistake for the `__file__` hazard the finalize chain warns against. The docstring
states the distinction explicitly, but it is a distinction that has to be re-read rather than
inferred. And `unclassified` remains a class no dimension escalates — deliberately, since its whole
meaning is "no conclusion available", but it does mean a badly-degraded run reports quietly.

## Disconfirmation

**Falsifier.** If an operator retires a decision that the lifecycle table would have marked
expected-absent, the withholding did not reach the surface that matters and the fix belongs in the
consuming command rather than the detector.

**Steelmanned runner-up.** Shipping the shapes as a constant is genuinely simpler and removes path
resolution entirely. The duplication objection assumes the table changes often enough to drift; if
it turns out to be near-static, the constant is the better trade and this decision is over-built.

**Reversal trigger.** Revisit if the plugin-relative lookup produces a wrong answer in any real
project — for instance if a managed project's own `.ai-state/` diverges enough from the shipped
inventory that the plugin's table mislabels its artifacts. That would show the table is not in fact
plugin-owned and belongs with the project after all.
