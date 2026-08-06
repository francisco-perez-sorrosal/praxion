---
id: dec-326
title: Keep pre-merge architect-validator write-free and give its verdict a transport and a gate
status: accepted
category: behavioral
date: 2026-08-06
summary: The pre-merge validator stays without Write; its report gets a real transport (--json-schema structured output) and a real reader (a render-and-gate step that publishes the report and fails the job on a FAIL verdict).
tags: [architect-validator, gate-liveness, ci, aac, pre-merge, pipeline-contract]
made_by: agent
agent_type: orchestrator
branch: fleet-quality-remediation
pipeline_tier: standard
affected_files:
  - .github/workflows/architecture.yml
  - agents/architect-validator.md
dissent: Turning a never-blocking LLM verdict into a merge-blocking one ships an unproven gate — no canary test drives the jq expression, and a hallucinated FAIL now red-lines an architectural PR.
---

## Context

The `dsl-validate` job invokes `architect-validator` in `--mode=pre-merge` through
`claude-code-action` with an allowlist granting no `Write`. The agent's Phase 7 mandates writing
`.ai-work/<task-slug>/ARCHITECTURE_VALIDATION.md`, so the mode cannot produce the artifact its own
phase requires. That is the reported finding, and it reproduces exactly as described.

Investigating the finding surfaced a larger one that inverts the obvious fix. **Nothing consumed
the agent's output at all**, in any form:

- the step carried no `id`, so `steps.*.outputs.*` was unreachable even in principle;
- no `--json-schema` was passed, so `structured_output` was empty by construction;
- it was the last step in the job — no step read, rendered, or uploaded anything;
- the job holds `pull-requests: read`, so no comment was possible;
- and the prompt's instruction to *"fail (exit non-zero) only on CRITICAL or HIGH severity issues"*
  named a behavior the agent has no mechanism to perform. An agent has no exit code, and the
  allowlist grants no shell to fake one.

The consequence is that the job's only real signal was *"did the agent crash"*. A clean run
reporting `FAIL` produced a green check. Two of the workflow's three jobs are genuine hard gates;
this one was Opus spend with an unread result — indistinguishable from not running it, which is
precisely the gate-liveness clause **Existence is not operation**.

An adjacent decision (`dec-325`) had already made the agent definition *honest* about
the missing `Write`, naming the CI job and the PR review surface as the pre-merge readers. This
decision is what makes that naming true; it does not replace it.

## Decision

Keep `--mode=pre-merge` write-free, and build the two things that were actually missing.

- **Transport.** Pass `--json-schema` mirroring the report structure already documented in the
  agent (three sections, the finding fields, the three verdicts). The report becomes
  `steps.validator.outputs.structured_output` — a value that outlives the step, which a file on
  the runner never could.
- **Reader and gate.** Add a `Render verdict and gate on structural drift` step that renders the
  report into `$GITHUB_STEP_SUMMARY` (reachable from the PR's own check list) and exits non-zero
  when `.verdict == "FAIL"`.
- **Failure-mode separation.** The agent step becomes `continue-on-error: true`, and an *empty*
  output is handled as a loud advisory (`::warning::` plus a summary block saying the check did not
  happen) rather than a block. Exhausted quota is not structural drift and must not redden a PR;
  a `FAIL` verdict is and must.
- **Contract correction in the agent.** The frontmatter and the `Exit behavior` section claimed the
  agent exits non-zero. It cannot, and never could. Those become a verdict-to-gate mapping: the
  agent owns the verdict, the harness owns the exit code. Phase 7 gains the schema clause and an
  explicit instruction not to write the file anyway on a runner.

## Considered Options

### Option A — Keep the mode write-free; wire transport + reader (chosen)

- **Pro** — `structured_output` is the only channel that survives the step. A file written to
  `.ai-work/` on a runner has no task slug, no uploader, and no lifetime past teardown.
- **Pro** — no new capability for a CI-invoked agent, and no new token permission. The job summary
  is a PR-reachable surface, so `pull-requests: write` stays off a workflow that loads the plugin
  and runs Opus.
- **Pro** — makes the blocking posture that the agent frontmatter, the agent's own mode section,
  and the workflow prompt all already claimed into something that exists.
- **Con** — the jq gate ships without a canary test; the file scope of this change excludes
  `tests/` and `fitness/`, so the proof is a documented, runnable golden bad case rather than an
  executable one.
- **Con** — an LLM verdict can now block a merge. A false `FAIL` costs a re-run or an override.

### Option B — Grant `Write` scoped to `.ai-work/**`

- **Pro** — the mode would literally do what Phase 7 says, which is the shape the finding suggests.
- **Con** — it fixes the wrong half. Pre-merge has no task slug, no step uploads the artifact, and
  the runner is destroyed minutes later. The file would be written and immediately lost.
- **Con** — it is strictly worse than the structured-output path it would sit beside: same content,
  a transport that cannot leave the runner, plus a write capability granted to an agent running on
  PR-triggered CI.
- **Con** — pairing it with a named consumer (upload, comment, read-back step) means building the
  reader anyway, at which point the file is the redundant half.

### Option C — Keep write-free and mode-aware, and stop there

- **Pro** — the smallest possible change; the agent definition is already honest after
  `dec-325`.
- **Con** — leaves a *named* consumer that does not exist. Naming a reader that reads nothing is
  the exact failure the gate-liveness clause is about, one step more deceptive than naming none.
- **Con** — leaves the prompt instructing an impossible action, burning turns and misdescribing the
  gate to whoever reads the workflow next.

## Consequences

**Positive**

- The validator's findings reach a human on the PR, and a `FAIL` verdict now blocks a merge.
- The workflow header's claim to "enforce three independent properties" becomes true of all three.
- Infrastructure failure and structural failure are distinguishable in the job's output, which the
  previous fail-closed-on-crash behavior conflated.
- The agent stops promising a file it cannot write and an exit code it cannot set.

**Negative**

- A blocking gate ships without an executable canary. Recorded as the dissent above.
- The `--json-schema` blob in the workflow and the report structure in the agent are the same
  convention at two textual sites; they drift unless changed together. Cross-referenced in both.
- The empty-output path is a non-blocking warning — a gate whose failure prints as a warning. It is
  deliberate (quota exhaustion must not gate merges) but it is a real coverage hole.

## Disconfirmation

**Falsifier.** Watch the first architectural PRs after this lands. If the gate fires `FAIL` on
changes that a human review then judges clean — false positives from an Opus verdict on a
diff-scoped structural check — the blocking posture is wrong and the honest correction is to render
the report but not exit non-zero, leaving the two mechanical jobs as the only hard gates. Equally
falsifying in the other direction: if `structured_output` comes back empty on most runs, the
transport is the thing that does not work and the advisory branch is the whole behavior.

**Steelmanned runner-up (Option B).** The strongest case for granting `Write` is that it keeps
*one* output contract instead of two. The agent's Phase 7 then means the same thing in every mode,
a future reader cannot "fix" the mode-awareness back out, and the CI job could upload the file as a
build artifact — a durable, downloadable, 30-day-retained record that a job summary is not. That is
a genuine advantage: `context-security-review.yml` in this repo uploads exactly such an artifact
alongside its summary. Option B was rejected only because the file would have to be uploaded to be
worth anything, and once the upload step exists the file is a detour around a transport the action
already provides for free.

**Reversal trigger.** Revisit if either holds: the false-positive rate on the verdict makes the
gate a nuisance (drop to render-only, keep the reader), or the job grows a need for the report as a
downloadable record across runs (add the artifact upload, at which point Option B's steelman
applies to the *file*, not to `Write` inside `.ai-work/`).
