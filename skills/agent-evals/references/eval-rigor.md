# Eval Rigor — Judge Calibration & Dataset-Split Discipline

Operationalizes two **dev-time, in-pipeline-gateable** disciplines that turn eval *metrics* into eval *gates*. Reference material for the [Agent Evals](../SKILL.md) skill.

Both disciplines run on the **project's own eval corpus** — no deployed production surface required. (Contrast the production/online grounding loop in [online-evals.md](online-evals.md), which needs a running deployment Praxion does not operate and so stays advisory.) That is what makes the two disciplines here enforceable *inside* the pipeline:

1. A **judge-calibration protocol** — a repeatable loop that earns the right to trust an LLM-as-judge score before it gates anything.
2. A **regression-vs-capability dataset split** — the regression suite is a frozen gate; the capability suite is a free-growing progress tracker.

**Consumers:** `test-engineer` authors the calibration set + the two-suite split at the paired implement+test stage and enforces them at the PR-level eval gate; `verifier` reads gate status at the pre-verification checkpoint.

**Boundaries (this file does not restate these):**

- LLM-as-judge patterns, rubric design, few-shot judge construction → [eval-design-patterns.md](eval-design-patterns.md).
- Held-out split *mechanics* (MANIFEST, sha256 versioning, contamination/answer-key isolation) → [data-governance.md](data-governance.md).
- CI wiring of the gate (GitHub Actions, PR comments, deployment gates) → [cicd-integration.md](cicd-integration.md).

---

## Why calibration is a gate, not a gotcha

The skill lists "LLM-as-judge needs calibration" as a gotcha. This reference promotes it to a **named loop with a pass bar**, because an uncalibrated judge is an *unmeasured instrument*: its scores cannot gate a PR when its agreement with ground truth is unknown. You would be blocking (or shipping) on a number whose error rate you never measured.

The dangerous failure is asymmetric. A judge that **false-passes** (scores a bad output as good) silently lets regressions through the gate; a judge that **false-fails** only annoys. A calibration protocol exists primarily to bound the false-pass rate.

## The Judge-Calibration Protocol

A repeatable, transcript-driven loop. Run it before trusting any LLM-graded metric for gating, and re-run it on the triggers below.

1. **Assemble a calibration set.** Draw a stratified sample of real transcripts — passes, fails, and ambiguous cases — and attach **human labels** as ground truth. Stratify so failures and edge cases are not swamped by easy passes (raw agreement inflates on imbalanced sets). Production failures are the best source (see [eval-design-patterns.md](eval-design-patterns.md#golden-datasets)).
2. **Run the judge blind.** Score the calibration set with the LLM judge, without exposing the human labels in the prompt.
3. **Measure agreement.** Report both:
   - **Raw agreement** (% of items where judge == human), and
   - **A chance-corrected metric** — Cohen's κ — because raw agreement overstates a judge on an imbalanced set.
   - For pass/fail gates, also report the **confusion split**: false-pass rate and false-fail rate. The false-pass rate is the gate-relevant number.
4. **Apply the gate bar.** Trust the judge for gating only when agreement clears a declared bar — a reasonable starting default is **κ ≥ 0.6 (substantial)** *and* a false-pass rate below the suite's tolerance. Below the bar, the judge's scores are **advisory, not gating**: revise the rubric / few-shot examples ([eval-design-patterns.md](eval-design-patterns.md#few-shot-calibration)) and re-run — do not ship the metric as a gate.
5. **Honor recalibration triggers.** Calibration is perishable. Re-run the protocol when **any** of these change: the judge model (or version), the rubric, the agent's output distribution (new capability shipped), or a fixed cadence elapses. A judge calibrated against last quarter's behavior is uncalibrated against this quarter's.
6. **Record the result.** Persist `{date, judge_model, raw_agreement, kappa, false_pass_rate, calibration_set_version}` alongside the eval suite so the verifier can read "judge calibrated as of `<date>`, κ=`<value>`" without re-deriving it.

| Calibration metric | What it answers | Gate relevance |
|---|---|---|
| Raw agreement | How often judge == human | Necessary, insufficient (inflates on imbalance) |
| Cohen's κ | Agreement beyond chance | Primary trust signal for the judge |
| False-pass rate | How often the judge waves a bad output through | The gate-safety number — bound this |
| False-fail rate | How often the judge blocks a good output | Friction signal — tune, but not a safety risk |

**Worked shape (illustrative):** on a 60-item stratified calibration set, a judge scoring raw agreement 0.92 but κ 0.41 with a false-pass rate of 0.15 is **not** gate-ready — the high raw agreement is carried by easy passes while one in seven bad outputs slips through. Revise the rubric and re-run before letting that judge gate.

## Regression vs Capability — the split that makes a gate

Two suites, two jobs. The skill already defines them by *purpose* (`SKILL.md` → Eval Types → By Purpose); the discipline this reference adds is the **gate behavior** of the split.

| Suite | Pass target | Gates the PR? | Grows? | Job |
|---|---|---|---|---|
| **Regression** | ~100% | **Yes — hard gate** | Frozen (append-only via promotion) | Catch backsliding on known-good behavior |
| **Capability** | Starts low | **No — tracked, not gated** | Grows freely | Measure progress on the "hill to climb" |

Three disciplines make this a real gate rather than a label:

- **The regression suite is frozen.** Cases enter *only* by promotion (below) and are never edited to make a currently-failing agent pass — editing a regression case to go green is gaming the gate, not fixing the agent.
- **The capability suite never gates.** It tracks work that is deliberately incomplete; gating on it would block every PR that touches an in-progress capability. It informs the trend line, not the merge decision.
- **Promotion is one-directional.** A capability case that holds ~100% across K consecutive runs **graduates** into the regression suite, where its job changes from "measure progress" to "prevent backsliding." Nothing demotes.

The split exists because it answers two genuinely different questions — *"did we break what worked?"* (regression gate) versus *"did we get better?"* (capability trend). Conflating them yields a gate that either blocks all forward progress or catches no regressions. Keep the regression set held out from the agent's few-shot / training exposure so a green gate is not contamination (see [data-governance.md](data-governance.md)).

## Living-dataset lifecycle

Calibration and the split stay predictive only if the underlying datasets are governed, not left to rot.

- **Ownership.** The eval suite is a living artifact with a named owner (the `test-engineer` for the feature), held to the same rigor as production code. It grows with every bug fix and every new capability — each production failure becomes a case.
- **Saturation detection.** When a capability suite's pass rate plateaus near ceiling across several runs, it has **saturated** — it no longer produces signal. Saturation is the prompt to act, not a victory to bank.
- **Retirement into regression.** A saturated capability case **retires into the regression suite** (it becomes a backsliding guard) rather than being deleted — its value shifts from "measure progress" to "prevent regression." Simultaneously, add harder variants to the capability suite to restore signal at the new frontier.

This loop — grow → saturate → retire-to-regression / harden-capability — is what keeps an eval corpus predictive as the agent improves, instead of decaying into a wall of easy green.

## Wiring the gate into the pipeline

- **Authoring:** `test-engineer` builds the calibration set and the two-suite split at the paired implement+test stage.
- **Enforcement (PR-level eval gate):** the regression suite must hold ~100% (hard gate); LLM-graded metrics gate **only** if the judge cleared its calibration bar, otherwise they post as advisory. See [cicd-integration.md](cicd-integration.md) for the GitHub Actions / PR-comment mechanics.
- **Verification:** `verifier` reads the recorded calibration result and gate status. The **pre-verification checkpoint** digest carries one line: *"judge calibrated against transcripts (κ=…); regression set held out as a gate."*

## Sources

- [Anthropic — Demystifying evals for AI agents](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents) — transcript-driven grader validation, separate regression (~100%) and capability suites, saturation-retirement, evals as living artifacts with explicit ownership. **[VERIFIED — Anthropic primary + corroborating 2026 write-ups]**
