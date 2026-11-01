---
id: dec-486
draft_id: dec-draft-d6800189
title: Read a capped report by how the session ended, and set grader changes apart in a run's identity
status: accepted
category: behavioral
date: 2026-10-31
summary: The write-early check judges a report's closing title only when the session ended on its own; C5 passes an unmarked capped verifier report only when it is finished (no [pending] section, a verdict); a run's measured identity gains a digest of the runner's grading sources so a run cannot be continued under changed checks.
tags: [eval, adherence, checks, c5, identity, td-545]
made_by: agent
agent_type: systems-architect
branch: worktree-eval-kit-repairs
pipeline_tier: standard
affected_files:
  - eval/src/praxion_evals/adherence/checks_roles.py
  - eval/src/praxion_evals/adherence/checks_common.py
  - eval/src/praxion_evals/adherence/output_forms.py
  - eval/src/praxion_evals/adherence/run_identity.py
---

## Context

The verifier's and the sentinel's write-early check (`title_marker_first_unmarked_last`) fails a title still carrying `[PARTIAL]` at the end, while C5 requires that title on a capped session. As a result, no capped session could pass both checks, and in run 20261031T203813Z-47ce6d, 14 of the 15 stopped verifier sessions passed exactly one of them.

C5 also fails every capped session with an unmarked title. Yet `agents/verifier.md` tells the verifier to close each section as `[not reached]`, set the verdict and remove `[PARTIAL]` as its last edit, and a session that does so on its last allowed turn still counts as stopped.

Separately, a run's identity digests the *checkout under test*, not the runner's grading code. The results show the checkout and the runner can differ (`run.checkout.path` names a separate worktree), so a recorded run could be continued under changed checks.

## Decision

- **Write-early check.** The opening half binds on every session. The closing half binds only when `role_ending` is `EndedOnItsOwn`, or absent because the task lowered no cap. It is skipped on `StoppedAtCap`. On `Unknown` the check is withheld, unless the opening already fails.
- **C5.** `output_forms` gains `FINISHED_FORMS`, holding only the verifier: no section still `[pending]` (`[not reached]` counts as closed) and a `## Verdict` naming `PASS`, `PASS WITH FINDINGS` or `FAIL`. On a capped session an unmarked title passes only for a finished report of a role in that table. Every other role keeps today's reading.
- **Canaries.** A check may carry several violations. The new canaries are:
  - the write-early check: one session that ended on its own and is still marked; one capped session that opened late or unmarked;
  - C5: one unmarked report with a `[pending]` section; one unmarked report with no verdict.
- **Identity.** `MeasuredIdentity` gains `checks`, a sha256 over the runner's own grading sources. These are the adherence modules that decide an outcome (`checks_*.py`, `catalog*.py`, `grade.py`, `output_forms.py`, `transcript.py`), read from the installed package. A recorded file lacking it reads as `None`, and `diff` names it, so continuing a pre-change run is refused. The confinement settings are deliberately outside `checks`: each session record carries its own confinement digest instead, so a settings fix after a confinement stop does not by itself block reusing finished pairs.

## Considered Options

1. **Relax only C5** (credit any unmarked title on a stop). Rejected. A lean session that strips `[PARTIAL]` from an unfinished report would pass.
2. **Drop the closing half of the write-early check.** Rejected. "Finish last" would go unmeasured wherever the role had the turns to finish.
3. **Rely on the existing tree digest to set runs apart.** Rejected. It digests the checkout under test, not the runner's grader.
4. **A hand-bumped catalog version.** Rejected. It is forgotten on the next semantic change; a digest cannot be.

## Consequences

- Positive: a capped session can pass both checks. C5 distinguishes a finished report cut off before its return from a stripped unfinished one. Recorded runs keep their outcomes and cannot be extended under new semantics.
- Negative: any edit to a grading module refuses continuation, even a cosmetic one. That is the conservative side of the trade.
- Activation: no. The change is a reading of existing evidence, reversible, and touches no recorded outcome.
