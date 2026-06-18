# Goal Disambiguation — Worked Examples & TASK_BRIEF Template

Companion to [../SKILL.md](../SKILL.md). Loaded on demand when the orchestrator needs the full capture template or a worked example of the 2×2 decision in action.

## TASK_BRIEF.md template

Write to `.ai-work/<task-slug>/TASK_BRIEF.md` at intake (Standard/Full; inline for Lightweight; skipped for Direct). This is an ephemeral pipeline document — it follows the same lifecycle as `RESEARCH_FINDINGS.md` and is deleted at pipeline cleanup after its signals are merged into the archived spec / verification report.

```markdown
# Task Brief: <short title>

## Task Intent
<≤2 sentences. What behavior should change, and why does it matter? Outcome, not mechanism.>

## Key Signals
<Each is a binary, checkable predicate. Prefer leading signals (checkable during implementation).
 Use Given/When/Then where it sharpens the predicate. One signal per discrete acceptance criterion.>
- [ ] <Signal 1 — observable outcome + how it is checked, e.g. a test node id>
- [ ] <Signal 2>

## Health Guards
<Invariants that must remain true regardless of how the signals are met — the Definition of Done.>
- [ ] No new lint errors
- [ ] Type-checker passes
- [ ] No test regressions outside the changed module

## Uncertainty Flag
<Free-form note WITH an N/10 confidence on any signal you are unsure about.
 Below 7/10 → the planner should add a spike step before committing.>
- <e.g. "Signal 1: 6/10 — unsure an in-memory index hits 200ms at 1000 records">

## Stated Assumptions (load-bearing)
<Assumptions taken to fill gaps the user did not specify, revealed univocally so the user can halt.>
- <e.g. "Assuming existing auth provider stays; not introducing a new identity backend.">

## Open Questions Asked
<If any AskUserQuestion was raised at intake, record the question + the answer. ≤3 per the cap.>
```

Provenance rule: `Task Intent` and `Key Signals` capture the **user's** success definition verbatim where the user gave one — they are not the orchestrator's reinterpretation. The architect may *refine* them in `SYSTEMS_PLAN.md`, but the brief preserves the original.

## Worked examples — one per 2×2 cell

### Cell 1 — Intent clear, reversible → proceed, ≤1 inline assumption

> "Rename `getUserData` to `fetchUserProfile` across the `users` module."

Smell scan: clean. XY: outcome is explicit (consistent naming). Reversibility: a rename is trivially reversible. **Action:** proceed directly. One inline note: "Assuming call sites in tests update too." No `TASK_BRIEF.md` (likely Direct/Lightweight).

### Cell 2 — Intent ambiguous, reversible → proceed with stated assumptions, no blocking question

> "Add a quick cache to the settings loader so it's not slow."

Smell scan: "quick", "slow" (vague qualities). XY: partial — the outcome ("not slow") is unquantified. Reversibility: an internal additive cache is reversible/low-blast-radius. **Action:** proceed, but reveal assumptions univocally so the user can halt:
> "Proceeding under these assumptions — stop me if any is wrong: (1) in-process memoization keyed on file mtime, not a distributed cache; (2) 'slow' means repeated re-parsing on each access, which I'll eliminate; (3) no change to the loader's public signature."

Capture inline Key Signal: "Repeated `load_settings()` calls within a process parse the file at most once (test added)."

### Cell 3 — Intent clear, hard-to-reverse → proceed, but capture explicit Key Signals

> "Migrate the sessions table from integer ids to UUIDs; all existing sessions must keep working."

Smell scan: clean. XY: outcome explicit. Reversibility: a schema migration is hard to reverse / high blast radius. **Action:** no clarifying question needed (intent is clear), but write a full `TASK_BRIEF.md` so verification is unambiguous:
- Key Signal: "Given a pre-migration session row, When the migration runs, Then the session resolves by its new UUID and the old integer id maps forward (test_migration::test_forward_map)."
- Health Guard: "No session is dropped; row count is conserved across migration."
- Uncertainty Flag: "Rollback path: 7/10 — confirm down-migration restores integer ids."

### Cell 4 — Intent ambiguous, hard-to-reverse → ASK (1–3 Mom-Test questions)

> "Lock down the API so randoms can't hit it."

Smell scan: "lock down", "randoms" (vague actor + vague mechanism). XY: implementation-first ("lock down") with no stated outcome. Reversibility: auth/security behavior is hard to reverse and high blast radius. **Action:** this is the one cell that earns blocking questions. Ask via `AskUserQuestion`, Mom-Test phrased, ≤3:

1. "Who are the legitimate callers, and how do they authenticate today?" *(reveals the real actor — not leading)*
2. "What should happen to an unauthenticated request — rejected, rate-limited, or redirected?" *(outcome, not mechanism)*
3. "Is this protecting against anonymous public traffic, or also scoping which authenticated users may call it?" *(disambiguates authn vs authz — the load-bearing fork)*

Then write `TASK_BRIEF.md` with the answers as Key Signals.

## AskUserQuestion phrasing patterns

| Situation | Avoid (leading / solution-first) | Prefer (outcome / behavior) |
|---|---|---|
| Unknown consumer | "Use REST or GraphQL?" | "How will this be consumed, and by what client?" |
| Vague success | "Should it be fast?" | "What does 'done well' look like you could observe?" |
| Implementation-first ask | "Which caching library?" | "What problem does the cache solve — what's slow today?" |
| Scope unclear | "Want me to also refactor X?" | "Is X in scope, or out for this task?" |

Phrase options as concrete, mutually-exclusive outcomes. Always allow the user to halt — the "Other" path is automatic in `AskUserQuestion`.
