---
id: dec-481
draft_id: dec-draft-bee57879
title: A decision-record gate refuses misplaced, self-numbered, malformed or uncategorised records at write and commit time, and an unbounded read of the decisions index
status: accepted
category: architectural
date: 2026-10-31
summary: A stdlib-only pure core, scripts/_decision_records.py, judges from values alone a pending change to .ai-state/decisions/ (placement, numbering, draft name and id, category) and an unbounded Read of DECISIONS_INDEX.md, and scripts/_decision_record_refusal.py renders the refusal with the rule's governing lines; hooks/guard_decision_records.py behind the shell fast path hooks/decisions_gate.sh refuses on time (PreToolUse Write|Edit and Read), and scripts/check_decision_records.py refuses at commit under the commit gate and Praxion's decision-records pre-commit hook; it ships through the plugin, so managed projects get it with no onboarding step.
tags: [gate, adr-conventions, hooks, pretooluse, commit-gate, gate-liveness, moves]
made_by: agent
agent_type: systems-architect
branch: apply-rule-moves
pipeline_tier: full
affected_files:
  - scripts/_decision_records.py
  - scripts/_decision_record_refusal.py
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

**Core.** A pure core, `scripts/_decision_records.py` (stdlib-only, 3.9-safe), parses a change into closed forms (record path, name, id, category) and returns `Allowed` or `Refused(defects)`. It reads no file, rule, branch or clock. Existing files are judged only for a lost category. A duplicated key is read the way its reader reads it: the first `id`, as finalize takes it, and the last `category`, as the index generator and PyYAML take it.

**Refusal text.** `scripts/_decision_record_refusal.py` composes the refusal: the correct form plus the rule lines that govern the defect, capped near 700 characters. It reads `rules/swe/adr-conventions.md` from `CLAUDE_PLUGIN_ROOT`, else from the checkout the module ships in, else from `~/.claude/rules/`. When none reads, it falls back to a one-line message with the same correct form. It never reads the project tree being judged, and the verdict never depends on it.

**Adapters.**

- **Write and read time.** `hooks/decisions_gate.sh` is a shell fast path in front of `hooks/guard_decision_records.py`. It forwards the payload with `printf '%s\n'`, never `echo`, and starts Python only for a `Write` or `Edit` payload holding both `.ai-state` and `decisions`, or a `Read` payload naming `DECISIONS_INDEX.md`. The guard builds the text the `Write` or `Edit` would leave and judges it on a non-main context. It also refuses a `Read` of the index that carries no `limit` (the read guard). Both are PreToolUse denies. The guard fails open: one that cannot start lets the call through.
- **Commit time.** `scripts/check_decision_records.py` (executable) gathers the values from git and renders the verdict. It runs as `commit_gate.sh --blocking` on the Bash matcher, judging the commit-to-be from the payload including same-call `git add` staging. It also runs as the `decision-records` pre-commit hook (`--staged`, the true staged set). A numbered record is allowed on `main` or `master`. It is also allowed wherever the default branch already holds it, local or remote-tracking (`refs/remotes/<remote>/main|master`), so merging `origin/main` while local `main` lags passes.
- **Commit scope.** The same-call staging helpers move from the id-citation gate (`scripts/check_id_citation_discipline.py`) into `scripts/_commit_scope.py`, which both commit gates import.

**Registration.** `hooks/hooks.json` gains three PreToolUse entries: the Bash commit-gate entry, a `Write|Edit` entry and a new `Read` matcher. `.pre-commit-config.yaml` gains the pre-commit entry. Canaries replay every shape through `hooks/hooks.json`. The gate's record shapes are a second encoding beside the eval grader's (`praxion_evals.adherence.moves.checks_adr`), and `eval/tests/test_decision_gate_parity.py` holds the two equal.

Activation: no — the trigger points follow an accepted precedent (the memory-index gate) and the checkpoint fixed the read guard.

## Considered Options

### Grow the resident line
An unmeasured arm; does not stop a record written by a shell command.

### Commit-time gate only
Catches every write route but after the record exists; the measured miss is at write time.

### Write-time hook only
On time, but blind to heredoc, cp, mv and sed writes.

### Write-time hook plus commit backstop over one core (chosen)
On time where the miss happens, complete at commit; the core judges, the refusal module and the adapters only gather and render.

## Consequences

- Positive: the measured residual is refused deterministically, with the rule's own lines in the refusal; managed projects get it through the plugin; hosts without hooks behave as before.
- Negative: three more PreToolUse entries, one of them a `Read` matcher on every Read, kept to a shell grep. A second encoding of record shapes lives beside the eval's grader, held equal by a parity test.
- Declared limits:
  - Commits made outside a session in a managed project are not judged; the pre-commit hook is Praxion's own.
  - From the commit payload, a record the same call writes through the shell (heredoc, `cp`, `mv`, `sed -i`) is not seen.
  - `git add -u` names no pathspec, so the tracked edits it stages are not judged.
  - A commit spelled through a single `|` or `&`, `bash -c`, `xargs`, `$(...)` or a quoted environment prefix is not recognised. The id-citation gate shares this blind spot; td-528 tracks catching both. Praxion's pre-commit hook still judges the true staged set.
  - `git -C DIR commit` judges the payload's cwd repository.
  - A default branch named other than `main` or `master` is not recognised, so a numbered record is refused on every branch of such a repository.
  - At write time, a path reached through the state mount's real path, not lexically through `.ai-state`, is not judged.
  - At write time, an existing draft whose id is rewritten from a valid draft id to a bad one is not caught.
  - On Windows, where user-scope `paths:` is ignored, these refusals and the resident line are the rule's only on-time delivery (companion decision `dec-480`).

## Disconfirmation

- **Falsifier:**
  - The components added are:
    - the core, `scripts/_decision_records.py` and `scripts/_decision_record_refusal.py`;
    - its adapters, `scripts/check_decision_records.py`, `hooks/guard_decision_records.py` and `hooks/decisions_gate.sh`;
    - the extracted `scripts/_commit_scope.py`, whose same-call staging responsibility moved out of `scripts/check_id_citation_discipline.py`.
  - If none of them existed, or neither `hooks/hooks.json` nor `.pre-commit-config.yaml` registered the gate, the decision did not land.
- **Steelmanned runner-up:** extend `scripts/check_adr_frontmatter_promotion.py` and run it only at commit. It reuses a tested gate and adds no hook. It loses on three counts:
  - it is registered only in Praxion's pre-commit, so reaching managed projects would need a commit-gate entry anyway;
  - it would judge only at commit;
  - it refuses only after the defective record already exists in the session's tree.
- **Reversal trigger:** a measured false refusal of a conforming write in a managed project, or Read-matcher latency that the fast path does not keep under the existing hooks' cost.
