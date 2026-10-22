---
id: dec-draft-87eed51f
title: "The flip gate's run readers share one stdlib standing leaf, results files are gathered before judging, and an unreadable earlier part is named"
status: proposed
category: architectural
date: 2026-10-22
summary: "New scripts/kernel_run_standing.py holds the one Standing value and typed-read helpers for both run readers; check_kernel_manifest.gather reads the results files into run evidence the judging takes as an argument; an unreadable part of a continued run's lineage gets I9-run-part-unreadable naming the file"
tags: [kernel, flip-gate, adherence, purity]
made_by: agent
agent_type: systems-architect
branch: worktree-loop-gate-followups
pipeline_tier: full
affected_files:
  - scripts/kernel_run_standing.py
  - scripts/kernel_run_evidence.py
  - scripts/kernel_run_index.py
  - scripts/kernel_ledger_checks.py
  - scripts/check_kernel_manifest.py
affected_reqs: [REQ-16, REQ-17, REQ-18]
---

# The flip gate's run readers share one stdlib standing leaf, results files are gathered before judging, and an unreadable earlier part is named

## Context

td-482, td-483, td-485. `kernel_run_evidence` and `kernel_run_index` each defined a standing type and copies of the typed-read helpers, because the gate's reader may not import `kernel_model`. An unreadable results file was dropped silently, so a continued run whose earlier part was unreadable read as a lineage disagreement. The cited-run judging opened the results files itself.

## Decision

1. A new stdlib leaf, `scripts/kernel_run_standing.py`, holds the one standing value and the typed-read helpers with one shape error naming field and reason; both readers import it and delete their copies. It imports nothing from the eval package or `kernel_model`.
2. Reading returns the parsed files and the unreadable ones with their reasons. A cited run whose `continues` chain reaches an unreadable part gets `I9-run-part-unreadable` naming that file, and no lineage-disagreement finding.
3. `check_kernel_manifest.gather` reads the results directory into run evidence; the cited-run judging takes it as an argument and opens no file.

## Considered Options

### One leaf, gathered evidence (chosen)

### Let the index reader import the evidence reader's types

Rejected: couples the locator to the evidence reader and keeps the helpers in a module with a different reason to change.

### Leave the read inside judging and inject a reader function

Rejected: the judging still performs I/O through the injected function; gathering keeps it a pure function of values.

## Consequences

- Positive: the two readings cannot drift; the judging is testable without a filesystem; a broken part is named.
- Negative: one more module; a new finding kind the how-to must name.

## Disconfirmation

- **Falsifier:** if a value one reader accepts is refused by the other, or the judging opens a file, the design failed.
- **Steelmanned runner-up:** keep two copies under a parity test; fewer modules. Rejected because a parity test pins today's fields, not tomorrow's, and the duplication is the defect the row names.
- **Reversal trigger:** if the run index stops reading standings (a schema that drops them), the leaf has one consumer and folds back into the evidence reader.
