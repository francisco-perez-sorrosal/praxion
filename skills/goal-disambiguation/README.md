# goal-disambiguation

Task-intake protocol that turns a fuzzy user request into an unambiguous, verifiable goal — and captures measurable outcome signals — before the pipeline commits to a direction.

## When to Use

At the start of any non-trivial task (Lightweight tier and above) when the request is vague, implementation-first, or has no observable success condition. Also whenever deciding *whether to ask the user a clarifying question or proceed with stated assumptions*. Direct-tier tasks skip it.

## Activation

- Auto: the orchestrator's always-loaded **Intake Clarity Gate** (in `rules/swe/swe-agent-coordination-protocol.md` § Conversation Checkpoints) points here for the full procedure.
- Contextual: triggers on intake disambiguation, clarifying questions, ambiguity, goal elicitation, acceptance-criteria-at-intake, definition-of-done capture.

## Skill Contents

- `SKILL.md` — the ask-vs-proceed decision rule (intent-clarity × reversibility 2×2), the five-step protocol (smell scan → XY test → reversibility gate → assumption surfacing → Mom-Test phrasing, 3-question cap), and the `Intent / Key Signals / Health Guards / Uncertainty Flag` capture shape with tier calibration.
- `references/worked-examples.md` — the `TASK_BRIEF.md` template, one worked example per 2×2 cell, and `AskUserQuestion` phrasing patterns.

## Related Skills

- `spec-driven-development` — calibration procedure (task **size**); this skill adds the orthogonal **clarity** axis and a goal-clarity signal.
- `software-planning` — the three-document model the captured Key Signals flow into.
- `multi-perspective-analysis` — the precedent thin-composition-layer pattern this skill follows.
