# Intra-Step Pair-Review

Optional, independent lightweight reviewer pass at each RISKY step boundary (implementer→planner seam). The reviewer is the existing `verifier` agent invoked in `Mode: light-review` — not a new agent type. For the light-review invocation contract, see [`agents/verifier.md` § Mode: light-review](../../../agents/verifier.md).

See also: [../SKILL.md](../SKILL.md) | [coordination-details.md](coordination-details.md) | [decomposition-guide.md](decomposition-guide.md)

---

## Trigger Predicate

A light-review pass fires at the step boundary when **any** auto-signal is active AND the planner has not suppressed it.

### Auto-signals

| Signal | Source | Meaning |
|--------|--------|---------|
| **Uncertainty Flag < 7** | `TASK_BRIEF.md § Uncertainty Flag` | The orchestrator's intake gate rated overall intent confidence below 7/10 at task start — downstream steps carry elevated risk of misalignment |
| **One-way-door** | Step tagged in `IMPLEMENTATION_PLAN.md` | The step's change is hard or impossible to reverse (schema migration, external service call, permission grant, data deletion) |
| **`tier: H`** | Step tag in `WIP.md` / `IMPLEMENTATION_PLAN.md` | Cross-cutting, high-complexity change (planner-assigned; see [decomposition-guide.md § Step Risk Tagging](decomposition-guide.md#step-risk-tagging)) |

### Planner Override (wins over every auto-signal)

The planner annotates any step's `review:` field to override:

| Value | Meaning |
|-------|---------|
| `review: force` | Pass runs regardless of auto-signals (use for steps the planner judges risky independent of the signal set) |
| `review: off` | Pass suppressed regardless of auto-signals (use for steps confirmed low-risk or where reviewer context is insufficient) |
| *(absent)* | Auto-signal logic applies |

Override precedence: planner field → auto-signals. A step with `review: off` never spawns a reviewer, even if all three auto-signals are active.

**Zero-cost for non-RISKY steps.** When no auto-signal is active and `review:` is absent (or `off`), no spawn occurs and no checkpoint is added. Non-RISKY steps are unaffected.

---

## Reviewer Input Contract

The orchestrator assembles exactly three inputs before spawning the reviewer. No pipeline-global documents are included — the reviewer is step-scoped.

| Input | Source | Why this one, not more |
|-------|--------|----------------------|
| **Step diff** | `git diff HEAD~1..HEAD -- <step-files>` scoped to the step's declared `Files` | The change the reviewer assesses |
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

The step is accepted. The orchestrator advances `WIP.md` to the next step.

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

**The reviewer does NOT produce a `VERIFICATION_REPORT.md`** in light-review mode. The output is a bounded inline response — no file artifact.

---

## Iteration Bound and Escalation

### Iteration bound (max 1 revise loop)

```
Step complete
  └─ [if RISKY] spawn verifier (Mode: light-review)
       ├─ verdict: accept → advance WIP.md
       └─ verdict: revise → implementer addresses findings → step re-runs
            └─ [reviewer re-spawned once]
                 ├─ verdict: accept → advance WIP.md
                 └─ verdict: revise (2nd) → ESCALATE
```

A second `revise` verdict escalates immediately — the loop does not repeat.

### Escalation procedure

On a second `revise` verdict:

1. Orchestrator surfaces the findings to the user: "Light-review returned `revise` twice on Step N. Findings: [list]. Escalating to user decision."
2. User decides: proceed-despite-findings, fix-and-retry, or defer-to-full-verifier.
3. **Residue recording:** regardless of the user's decision, findings that triggered the second `revise` are recorded in `LEARNINGS.md § Tech Debt` and handed off to the end-of-pipeline full verifier for evaluation. The full verifier's `VERIFICATION_REPORT.md` will include these as pre-flagged candidates.

---

## Composition Table

| Gate | Scope | Who runs | When | Output |
|------|-------|----------|------|--------|
| **Implementer self-review** | Single step — implementer checks own work against coding-style rule and `Done when` criteria | Implementer (self) | Always, every step, before marking COMPLETE | No artifact; inline check |
| **Intra-step pair-review (this gate)** | Single step — independent reviewer checks step diff + step ACs | `verifier` (Mode: light-review, sonnet) | RISKY steps only (auto-signals or `review: force`) | Bounded `accept`/`revise` verdict; no `VERIFICATION_REPORT.md` |
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
| `force` | Spawns reviewer regardless of auto-signals |
| `off` | Suppresses reviewer regardless of auto-signals |
| *(omit field)* | Auto-signal logic governs |

The `review:` field is a planner annotation. The implementer does not set it. The orchestrator reads it at step completion before deciding whether to spawn.
