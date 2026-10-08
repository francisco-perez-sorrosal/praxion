# Intra-Step Pair-Review

Optional, independent lightweight reviewer pass at each marked step boundary (implementer→planner seam). Inside the step loop the driver requests the pass and the orchestrator spawns the reviewer; outside the loop the orchestrator decides and spawns. The reviewer is the existing `verifier` agent invoked in `Mode: light-review` — not a new agent type. For the light-review invocation contract, see [`agents/verifier.md` § Mode: light-review](../../../agents/verifier.md).

See also: [../SKILL.md](../SKILL.md) | [coordination-details.md](coordination-details.md) | [decomposition-guide.md](decomposition-guide.md)

---

## Trigger Predicate

A step carrying `review: force` or `tier: H` is reviewed unless it carries `review: off`. The plan alone decides: no signal is read when a step completes.

| Annotation | Effect |
|------------|--------|
| `review: force` | Reviewed |
| `tier: H` | Reviewed (cross-cutting, high-complexity change; see [decomposition-guide.md § Step Risk Tagging](decomposition-guide.md#step-risk-tagging)) |
| `review: off` | Not reviewed, even with `review: force` or `tier: H` also present |
| *(none)* | Not reviewed |

The planner marks `review: force` on the steps an Uncertainty Flag below 7 in `TASK_BRIEF.md` bears on, and on the steps a one-way door (schema migration, external service call, permission grant, data deletion) bears on. Neither reaches the trigger any other way.

**Zero-cost for unmarked steps.** A step with none of the three annotations is never reviewed: no spawn occurs and no checkpoint is added.

---

## Reviewer Input Contract

The review request names exactly three inputs; the orchestrator hands them to the reviewer. No pipeline-global documents are included — the reviewer is step-scoped.

| Input | Source | Why this one, not more |
|-------|--------|----------------------|
| **Step diff** | The step's commit range, as the review request names it: `git diff <first>^..<last> -- <files>` over the step's declared `Files` | The change the reviewer assesses |
| **Step acceptance criteria** | `IMPLEMENTATION_PLAN.md § Step N: Done when` | The specific behavioral contract for this step |
| **Key Signals** | `TASK_BRIEF.md § Key Signals` (if the file exists) | The user's verbatim success predicates; ensures reviewer alignment with original intent |

The reviewer does NOT receive: `SYSTEMS_PLAN.md`, prior step diffs, traceability matrices, or `VERIFICATION_REPORT.md` history. Those are the full verifier's domain.

---

## Reviewer Output Contract (Bounded Verdict)

The reviewer returns **one of two outcomes** — no other forms are valid:

### `accept`

```
verdict: accept
notes: <optional one-line observation, if any>
```

The step is accepted and the loop advances to the next step.

### `revise` with findings list

```
verdict: revise
findings:
  - id: F1
    severity: FAIL | WARN
    location: <file:line or file range>
    evidence: <what was observed>
    criterion: <which step AC or convention was violated>
  - ...
```

Each finding must reference either the step's acceptance criteria or a documented convention (coding-style rule or behavioral contract). Findings without a traceable anchor are not valid.

**The reviewer does NOT produce a `VERIFICATION_REPORT.md`** in light-review mode. It writes the bounded verdict block to `.ai-work/<task-slug>/LIGHT_REVIEW_step-<N>.md` early, as `verdict: [PARTIAL]`, appends findings as it confirms them, sets the verdict last, and returns the same block inline. A capped reviewer therefore leaves its findings so far, and a file still reading `verdict: [PARTIAL]` is an unfinished review, never an `accept`.

---

## Iteration Bound and Escalation

### Iteration bound (max 1 revise loop)

```
Step complete
  └─ [if marked] spawn verifier (Mode: light-review)
       ├─ verdict: accept → advance WIP.md
       └─ verdict: revise → implementer addresses findings → step re-runs
            └─ [reviewer re-spawned once]
                 ├─ verdict: accept → advance WIP.md
                 └─ verdict: revise (2nd) → ESCALATE
```

A second `revise` verdict escalates immediately — the loop does not repeat.

### Escalation procedure

On a second `revise` verdict:

1. The orchestrator surfaces the findings to the user: "Light-review returned `revise` twice on Step N. Findings: [list]. Escalating to user decision."
2. User decides: proceed-despite-findings, fix-and-retry, or defer-to-full-verifier.
3. **Residue recording:** regardless of the user's decision, findings that triggered the second `revise` are recorded in `LEARNINGS.md § Tech Debt` and handed off to the end-of-pipeline full verifier for evaluation. The full verifier's `VERIFICATION_REPORT.md` will include these as pre-flagged candidates.

---

## Composition Table

| Gate | Scope | Who runs | When | Output |
|------|-------|----------|------|--------|
| **Implementer self-review** | Single step — implementer checks own work against coding-style rule and `Done when` criteria | Implementer (self) | Always, every step, before marking COMPLETE | No artifact; inline check |
| **Intra-step pair-review (this gate)** | Single step — independent reviewer checks step diff + step ACs | `verifier` (Mode: light-review, sonnet) | Marked steps only (`review: force` or `tier: H`, unless `review: off`) | Bounded `accept`/`revise` verdict; no `VERIFICATION_REPORT.md` |
| **Pre-mortem gate** | Whole plan — forward-looking risk imagining | Orchestrator (interactive) | At planner→implementer boundary, before any step runs | Failure modes recorded in `WIP.md` |
| **Full verifier** | Whole feature — acceptance criteria, conventions, test coverage, traceability | `verifier` (Mode: default, opus) | Post-implementation, before merge | `VERIFICATION_REPORT.md` |

Key distinctions:
- **Intra-step vs self-review**: independent spawn vs implementer re-reading own diff — independence is the signal value.
- **Intra-step vs pre-mortem**: backward-looking diff check vs forward-looking risk exercise — complementary, not duplicates.
- **Intra-step vs full verifier**: step-scoped and cheaper (sonnet) vs feature-scoped and quality-critical (opus). Intra-step residue feeds the full verifier, not the reverse.

---

## `review:` Field Schema

Add to a step's block in `IMPLEMENTATION_PLAN.md` (optional):

```markdown
### Step N: [description]

**Implementation**: ...
**Files**: ...
**review**: force | off
**Done when**: ...
```

| Value | Effect |
|-------|--------|
| `force` | Reviewed |
| `off` | Not reviewed, even with `tier: H` |
| *(omit field)* | Reviewed only if the step carries `tier: H` |

The `review:` field is a planner annotation. The implementer does not set it. The driver (inside the loop) or the orchestrator (outside it) reads it from the plan.
