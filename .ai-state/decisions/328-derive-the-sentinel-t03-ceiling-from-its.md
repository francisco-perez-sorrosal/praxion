---
id: dec-328
title: Derive the sentinel T03 ceiling from its own check catalog span
status: accepted
category: configuration
date: 2026-08-06
summary: Replace the sentinel's fixed T03 warn 550 / fail 700 exception with warn S+300 / fail S+400, where S is the measured line span of its own Check Catalog; the verifier keeps the fixed thresholds.
tags: [sentinel, token-efficiency, t03, gate-liveness, thresholds, derived-limit]
made_by: agent
agent_type: orchestrator
branch: main
pipeline_tier: standard
affected_files:
  - agents/sentinel.md
  - agents/verifier.md
supersedes_in_part:
  - dec-203
---

## Context

`dec-203` granted `agents/sentinel.md` and `agents/verifier.md` a shared T03 exception of warn 550 / fail 700, on the reasoning that both agents' size is *intrinsic*: the sentinel's `## Check Catalog` is a table of distinct checks executed inline, and the verifier encodes a comprehensive Process plus a tested rework-spawn contract. Forcing either under the standard 300/500 thresholds risks a dead gate.

That reasoning holds. The **numeral** did not.

The 2026-08-06 sentinel run measured `agents/sentinel.md` at **675 lines against the fail ceiling of 700** — 3.6% headroom — and raised it as an Important finding. The catalog grows monotonically: every dimension added since `dec-203` consumed headroom that the fixed ceiling never replaced. The finding also collided with a second one from the same run, which prescribed adding substance clauses to four catalog rows (`AC01`, `AC08`, `P05`, `DL02`). Remediating that finding would have pushed the file toward the ceiling that the first finding was about.

A fixed numeral guarding a monotonically growing artifact is a countdown, not a limit. It was always going to be reached; the only question was which edit would be blamed.

## Decision

For `agents/sentinel.md`, express the T03 exception as a **derived** bound:

```
S    = line span of the `## Check Catalog` section
warn = S + 300
fail = S + 400
```

`S + 300` / `S + 400` are exactly the standard T03 thresholds applied to everything *outside* the catalog. The exception therefore introduces **no numeral of its own** — it states that catalog rows are not prose and should not be counted as prose, and nothing more. Each new check lifts the ceiling by precisely the lines it consumed.

At adoption: `S = 341`, so warn = 641, fail = 741, against a file of 675 lines — 66 lines of headroom, invariant under catalog growth.

`agents/verifier.md` **keeps the fixed 550 / 700**. It encodes no catalog, so there is no span to derive from; `dec-203`'s reasoning applies to it unchanged.

## Considered Options

### A. Raise the fixed ceiling (700 → 800)

- **Pro**: one-character change; immediately relieves the pressure.
- **Con**: reproduces the defect exactly. A larger countdown is still a countdown, and the next occurrence arrives with less institutional memory of why the number was chosen.

### B. Extract the catalog to a progressive-disclosure reference

- **Pro**: the orthodox Praxion remedy for an oversized artifact; would bring the file under the standard thresholds with no exception at all.
- **Con**: **the catalog is the gate.** A reference the agent fails to load is not a smaller gate, it is no gate — and this is the artifact whose entire function is detecting that class of failure. It would also require shipping a proof that the loaded copy is the executed one, which is a new gate guarding the removal of an old one.

### C. Derive the ceiling from the catalog span (chosen)

- **Pro**: removes the numeral rather than adjusting it; cannot re-drift on the next dimension addition; keeps the catalog inline, so the gate stays live; expressible as a two-line `awk` recipe stated in the row itself.
- **Con**: the ceiling is no longer readable at a glance — a reader must run the recipe to know it. Mitigated by stating the recipe and a golden bad-case in the row.

## Consequences

**Positive.** The finding cannot recur from growth the exception was written to accommodate. The two colliding findings decouple: substance clauses can now be added to catalog rows without consuming prose headroom. A stale "~260 rows" figure was removed in the same edit (the true count is 127), and the catalog's own preamble already forbids restating its size — the derived form honours that by measuring rather than quoting.

**Negative.** T03 must now execute a measurement before it can report, making it marginally more expensive and more fragile: the `awk` recipe depends on the `## Check Catalog` and `## Process` headings keeping their exact names. A rename would silently return `S = 0` and slam the ceiling to 400, failing the file instantly — loud, at least, rather than silent.

**Neutral.** `agents/sentinel.md` remains at WARN (675 > 641), as it was before (675 > 550). The margin narrowed from 125-over to 34-over. The Important finding concerned FAIL proximity, which is resolved; the WARN is accurate and should stay.

## Prior Decision

`dec-203` is **partially superseded**. Its shared fixed exception (550 / 700 for both gate-encoding agents) is replaced for `agents/sentinel.md` only.

Its **verifier clause survives unchanged and is re-affirmed**: `agents/verifier.md` encodes no catalog, so it has no span to derive from and the fixed thresholds remain the right instrument. `dec-203` should carry `re_affirmed_by` for that clause alongside `superseded_by` for the sentinel clause — the partial-supersession shape that `adr-conventions.md` DL06 describes, where one pair legitimately carries both relations.

What changed is not the *judgment* that these two agents warrant an exception — that judgment was correct and is preserved. What changed is the recognition that a fixed numeral cannot express an exception for an artifact designed to grow.
