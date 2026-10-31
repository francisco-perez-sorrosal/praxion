---
id: dec-draft-bee57879
title: A decision-record gate refuses misplaced, self-numbered, malformed or uncategorised records at write and commit time, and an unbounded read of the decisions index
status: proposed
category: architectural
date: 2026-10-31
summary: One stdlib-only rules module, scripts/check_decision_records.py, judges a pending change to .ai-state/decisions/ (placement, numbering, draft name and id, category) and an unbounded Read of DECISIONS_INDEX.md; a PreToolUse Write|Edit|Read hook behind a shell fast path refuses on time, quoting the rule's governing lines, and the commit gate plus Praxion's pre-commit refuse at commit; it ships through the plugin, so managed projects get it with no onboarding step.
tags: [gate, adr-conventions, hooks, pretooluse, commit-gate, gate-liveness, moves]
made_by: agent
agent_type: systems-architect
branch: apply-rule-moves
pipeline_tier: full
affected_files:
  - scripts/check_decision_records.py
  - scripts/_commit_scope.py
  - scripts/check_id_citation_discipline.py
  - hooks/decisions_gate.sh
  - hooks/guard_decision_records.py
  - hooks/hooks.json
  - .pre-commit-config.yaml
affected_reqs: [REQ-11, REQ-12, REQ-13, REQ-14, REQ-15, REQ-16, REQ-17, REQ-18, REQ-22]
---

## Context

In the paired run the path-scoped rule arrived after the session's first creating write in 4 of 24 lean sessions; one left a numbered, uncategorised record unrepaired. No existing gate refuses a numbered record on a non-main branch or a missing or invalid category; malformed drafts are caught only at finalize. The move also makes "never read the index whole" arrive with the read it forbids.

## Decision

A rules module (`scripts/check_decision_records.py`, stdlib-only, executable) parses a change into closed forms (record path, name, id, category) and returns `Allowed` or `Refused(defects)`; judging never reads rule text, composing the refusal does (from the plugin's copy of the rule, then `~/.claude/rules/`, else a fixed message). Existing files are judged only for a lost category. Adapters: `hooks/decisions_gate.sh` (shell fast path: Python starts only for a payload naming the decisions tree, or for a Read naming the index) in front of `hooks/guard_decision_records.py` (PreToolUse deny); `commit_gate.sh --blocking` and a Praxion pre-commit hook over the commit-to-be, where a numbered record is allowed on main or master and wherever the default branch already holds it. The same-call staging helpers move from the id-citation gate into `scripts/_commit_scope.py`. Canaries replay every shape through `hooks/hooks.json`.

Activation: no — the trigger points follow an accepted precedent (the memory-index gate) and the checkpoint fixed the read guard.

## Considered Options

### Grow the resident line
An unmeasured arm; does not stop a record written by a shell command.

### Commit-time gate only
Catches every write route but after the record exists; the measured miss is at write time.

### Write-time hook only
On time, but blind to heredoc, cp, mv and sed writes.

### Write-time hook plus commit backstop over one module (chosen)
On time where the miss happens, complete at commit.

## Consequences

- Positive: the measured residual is refused deterministically, with the rule's own lines in the refusal; managed projects get it through the plugin; hosts without hooks behave as before.
- Negative: two more PreToolUse registrations (a Read matcher on every Read, kept to a shell grep); a second encoding of record shapes beside the eval's grader, held equal by a parity test; commits outside a session in managed projects are not judged (declared limit).

## Disconfirmation

- **Falsifier:** the components added are `scripts/check_decision_records.py`, `hooks/guard_decision_records.py` and `hooks/decisions_gate.sh`, plus the extracted `scripts/_commit_scope.py`. If none of them existed after the change, the decision did not land.
- **Steelmanned runner-up:** extend `scripts/check_adr_frontmatter_promotion.py` and run it only at commit. It reuses a tested gate and adds no hook, but it is Praxion-only through pre-commit, reaches managed projects only through the commit gate, and refuses only after the defective record already exists in the session's tree.
- **Reversal trigger:** a measured false refusal of a conforming write in a managed project, or Read-matcher latency that the fast path does not keep under the existing hooks' cost.
