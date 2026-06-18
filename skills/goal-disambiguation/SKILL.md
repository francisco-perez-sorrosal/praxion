---
name: goal-disambiguation
description: >
  Task-intake protocol for turning a fuzzy user request into an unambiguous,
  verifiable goal before committing to a direction. Covers the ask-vs-proceed
  decision rule (the 2x2 of intent-clarity x reversibility), lexical ambiguity
  detection, the XY-problem test, assumption surfacing over interrogation,
  Mom-Test question phrasing with a hard 3-question cap, and capturing
  measurable outcome signals (Intent / Key Signals / Health Guards / Uncertainty
  Flag) into a TASK_BRIEF.md that seeds downstream architecting, planning,
  testing, and verification. Triggers: at the start of any non-trivial task when
  the request is vague, implementation-first, or its success is not measurable;
  deciding whether to ask the user a clarifying question or proceed with stated
  assumptions; capturing acceptance criteria / definition-of-done at intake;
  reducing rework from misread intent.
---

## Goal Disambiguation at Task Intake

The first move of every interaction: convert what the user *said* into what they *want*, made unambiguous and verifiable, **before** spawning agents or writing code. The discipline is **calibration, not interrogation** — ask only where a wrong guess is costly *and* hard to reverse; everywhere else, state an assumption and proceed.

This skill operationalizes Praxion's `Surface Assumptions` behavioral contract for the intake moment, and produces the outcome signals that become the verifier's rubric. It runs *alongside* tier calibration (which measures task **size**); this measures intent **clarity** — the two axes are orthogonal.

### When this fires

Run the protocol at intake for **Lightweight tier and above**, and whenever the request is vague, implementation-first, or has no observable success condition. **Direct tier skips it** — a typo fix needs no brief. The orchestrator's always-loaded Intake Clarity Gate (in `swe-agent-coordination-protocol.md`) decides whether the *blocking* question step fires; this skill is the procedure it points to.

### The decision rule — the keystone

Three independent traditions (decision-theory/AI-agent research on expected regret, requirements engineering, OKR testability) converge on one rule:

> **Ask the user only when intent is ambiguous AND a wrong guess is hard to reverse.** Neither condition alone justifies a blocking question.

This yields a 2×2. Intent-clarity × reversibility (blast radius):

| | **Intent clear** | **Intent ambiguous** |
|---|---|---|
| **Reversible / low blast radius** | Proceed. State ≤1 assumption inline. | **Proceed with stated assumptions** — reveal them *clearly and univocally* so the user can halt if misaligned. No blocking question. |
| **Hard-to-reverse / high blast radius** | Proceed, but capture explicit Key Signals so verification is unambiguous. | **Ask** — 1–3 Mom-Test questions before committing. Then capture the brief. |

Reversibility examples — *hard to reverse*: schema/data migrations, public API or contract changes, deletions, security/auth behavior, architectural commitments, anything touching money or external side effects. *Reversible*: naming, formatting, internal test structure, additive code behind a flag, anything caught cheaply on review.

### The five-step protocol

Run in order; most tasks exit early.

1. **Smell scan** — scan the request for lexical ambiguity markers (the cheap detector). Each hit is a *candidate* ambiguity, not yet a question:
   - Optionality: *can, could, may, might, should* (vs *must/shall*)
   - Vague quantifiers/qualities: *fast, reliable, better, clean, appropriate, robust, simple, scalable, sufficient*
   - Missing actor: no clear *who* performs or consumes the behavior
   - Vague referent: *it, this, that, them* with no clear antecedent
   - Superlatives/comparatives: *best, fastest, more X than*
2. **XY test** — is the request describing an *implementation* (X) rather than an *outcome* (Y)? If it prescribes a mechanism but never states the goal it serves, note the missing outcome. (The user asking for X may not have the best X for their real Y.)
3. **Reversibility gate** — for each candidate ambiguity from steps 1–2, ask: would guessing wrong be *hard to reverse*? Drop the rest. This is the throttle that prevents ceremony.
4. **Assumption surfacing** — state your top gap-filling assumptions **as defaults**, not questions ("I'll use the existing pytest setup and leave the public signature unchanged unless you say otherwise"). Reserve a *direct question* only for survivors of step 3 that are also high-importance **and** low-certainty (the SAST importance×certainty filter).
5. **Mom-Test phrasing** — when a question must be asked, phrase it toward the *outcome or past behavior*, never leading toward a solution you already hypothesize. Ask via `AskUserQuestion`. **Hard cap: 3 questions per intake.** A dialog cannot last forever; beyond the cap, state assumptions and proceed.

Good vs leading question:
- Leading: "Should I use REST or GraphQL?" (frames around your hypothesis)
- Mom-Test: "How will this endpoint be consumed, and by what?" (reveals the constraint)
- Outcome-seeking (XY): "What does success look like once this is done?"

### Capturing measurable outcome signals

Where success is non-obvious (the right column, or any Standard/Full task), capture the goal as outcome signals — the OKR/BDD residue that survives at task scale, **without OKR ceremony**. A Key Signal is a *binary, checkable predicate*: outcome, not output. "Ship the search feature" is output; "p95 search latency < 200ms over 1000 records (test_search::test_p95)" is outcome — only the latter lets a verifier close the loop.

The capture shape (the `TASK_BRIEF.md` artifact):

```markdown
### Task Intent          # Objective analog — ≤2 sentences: what behavior changes + why it matters
### Key Signals          # KR analog — binary-checkable outcome predicates; prefer leading (test-checkable). Given/When/Then where useful
### Health Guards        # Definition-of-Done analog — invariants that must not regress (lint, types, no out-of-module test breakage)
### Uncertainty Flag     # free-form note WITH an N/10 confidence; <7/10 on a signal => planner should add a spike step
```

Capture calibration rides the existing tier:

| Tier | What to capture |
|---|---|
| Direct | Nothing — skip the brief entirely |
| Lightweight | Intent + 1–2 Key Signals inline; Health Guards as a checklist |
| Standard / Full | Full shape in `.ai-work/<task-slug>/TASK_BRIEF.md`; one Key Signal per discrete acceptance criterion; explicit Uncertainty Flags |

Write `TASK_BRIEF.md` *before* spawning the researcher/architect so it is their first input. It carries the user's success definition **verbatim** — distinct from the researcher's synthesis (provenance hygiene). Downstream: the architect constrains designs to satisfy the Key Signals; the planner turns each into a step acceptance test and each Uncertainty Flag into a spike; the test-engineer maps each signal to a test node; the verifier uses Key Signals as its **primary rubric** (binary) and Health Guards as the regression checklist.

The full `TASK_BRIEF.md` template and a worked example per 2×2 cell live in [references/worked-examples.md](references/worked-examples.md).

### Gotchas

- **Don't ritualize the brief.** A clear, reversible task gets a one-line stated assumption, not a four-section document. Over-capture is the OKR ceremony this skill exists to avoid (Spotify dropped personal OKRs for exactly this overhead).
- **Surface ≠ ask.** Stated assumptions invite correction without blocking. Defaulting to a blocking question on every ambiguity violates Simplicity First and burns the user's attention.
- **Reveal assumptions univocally.** When proceeding under the ambiguous-but-reversible cell, list the load-bearing assumptions plainly enough that the user can stop the task — burying them in prose defeats the purpose.
- **Output KRs are the trap.** If a "Key Signal" describes work done rather than an observable outcome, it is not verifiable — rewrite it as a predicate a test can evaluate.
- **The cap is a feature, not a failure.** Hitting 3 questions without full clarity means: state remaining assumptions and proceed. The design-review checkpoint downstream catches what intake could not.
- **Clarity ≠ size.** A one-file change can be deeply ambiguous ("clean up the auth token handling"); a 10-file refactor behind a flag can be crystal-clear. Never infer intent-clarity from the tier score.
