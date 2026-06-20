# Online Evals & Budget Gates

The production-grounding eval loop and budget-as-gate discipline. Reference material for the [Agent Evals](../SKILL.md) skill.

> **Advisory scope.** Online grounding needs a *running deployment* — telemetry from real traffic. A development OS like Praxion can **teach the pattern but cannot operate it**: it does not see the managed project's production runtime, so it cannot gate on signals it cannot observe. Everything in the "production grounding" sections below is **advisory** — the user wires it into their own deployment. The exception is the **budget-gate** section, which is partly dev-time and *can* be enforced in the eval CI on the project's own corpus.

**Boundaries (this file does not restate these):**

- Deployment/rollout *mechanics* — shadow deployment, canary rollout, A/B wiring, monitoring tools and signals → [cicd-integration.md](cicd-integration.md) (§ Production Monitoring, § Rollout Patterns).
- Dev-time **living-dataset lifecycle** (ownership, saturation → retirement-to-regression) → [eval-rigor.md](eval-rigor.md). This file adds only the *production-fed* angle.
- Judge calibration, regression-vs-capability split → [eval-rigor.md](eval-rigor.md).

---

## Production as ground truth

**Offline evals alone create false confidence.** An offline suite measures the agent against cases *you* chose; production measures it against reality. Production metrics are the authoritative signal for whether your offline evals were ever *predictive* — a green offline suite paired with rising production failures means the suite is measuring the wrong thing.

The discipline: treat production not as a place to *watch* (that is monitoring) but as the *ground truth that grades your eval suite*. The question online grounding answers is not "is the agent healthy?" but "**were my offline evals telling the truth?**"

## The offline ↔ production grounding loop

A closed loop that keeps the offline suite honest:

1. **Predict** — the offline suite forecasts a pass rate / failure profile before release.
2. **Observe** — production telemetry reports the *actual* failure profile (mechanics: [cicd-integration.md](cicd-integration.md)).
3. **Reconcile** — where production failures fall outside what the offline suite covers, the suite was blind. Where offline failures never appear in production, the suite may be over-indexing on unrealistic cases.
4. **Feed back** — each *real* production failure becomes a new eval case (the highest-value cases there are — see Production-fed datasets below), and the offline suite's coverage gaps close toward the production distribution.

The loop's success metric is **predictiveness**: offline pass-rate movements should track production failure-rate movements. Divergence is the signal that the suite needs grounding, not that the agent needs fixing.

## Swiss-cheese multi-layer detection

No single layer catches every failure; stack independent layers so each covers the others' holes:

| Layer | Catches | Speed |
|---|---|---|
| Automated offline evals | Known regressions, covered capabilities | Fast (CI) |
| Production monitoring | Drift, unseen failure shapes | Continuous |
| A/B testing | Whether a change *actually* improved real outcomes | Per significant change |
| Manual transcript sampling | Grader errors, subtle quality loss | Weekly |
| Systematic human studies | Calibration of the LLM graders themselves | Periodic |

The layers are **independent on purpose** — automated evals and manual sampling fail in different ways, so a failure that slips one is caught by another. (The *mechanics* of each layer — how to wire monitoring or A/B — are in [cicd-integration.md](cicd-integration.md); this is the defense-in-depth *rationale* for running all of them.) Manual sampling and human studies feed the judge-calibration protocol in [eval-rigor.md](eval-rigor.md).

## Production-fed datasets

The dev-time living-dataset lifecycle (grow → saturate → retire) lives in [eval-rigor.md](eval-rigor.md). Production grounding adds one input to it: **a real production failure is the highest-value new eval case** — it is, by definition, representative and not synthetic. The feedback step of the grounding loop is what continuously refreshes the capability suite at the *real* frontier, instead of at the frontier the eval author imagined. Optionally, record online-eval provenance (which production incident a case came from) alongside the run ledger — see [run-ledger-schema.md](run-ledger-schema.md).

## Budget gates (cost / latency / turn)

Praxion's `agent-evals` already *tracks* cost, latency, and turn count as metrics (see [eval-design-patterns.md](eval-design-patterns.md) and [cicd-integration.md](cicd-integration.md) § Cost Management). This section elevates them from tracked metrics to **enforced gates**, reusing the proven discipline in `rules/ml/gpu-budget-conventions.md`:

> **Declare a budget → the eval gate enforces it → budget exhaustion is a NORMAL termination (`status: budget_exhausted`), not a failure.**

- **Declare** per-eval-run cost / latency / turn budgets as acceptance criteria (e.g. `cost_per_task < $0.05`, `p95_latency < 8s`, `turns <= 12`).
- **Gate** the PR on them alongside the regression suite: a run that blows the cost or turn budget fails the gate the same way a correctness regression does — unit economics and latency are first-class reliability criteria, not afterthoughts.
- **Exhaustion is normal.** When an *agent run inside the eval* hits its turn/cost budget, that run terminates cleanly at its budget with state preserved — reported as `budget_exhausted`, never as a correctness failure. This is the same semantics the harness-runtime side uses (see the `agent-runtime-guardrails` skill, `references/deterministic-harness.md`); the two budget enforcement points — harness-runtime and eval-CI — mirror one discipline.

Treating exhaustion as a normal termination (not a FAIL) is what keeps the budget usable as a control rather than something authors over-provision to avoid red builds.

## Why this stays advisory (mostly)

Praxion architects, plans, verifies, and gates a managed project's *development*; it does not run the project's production deployment. The grounding loop, swiss-cheese layers, and production-fed datasets are therefore **taught, not enforced** — the user wires them into their own runtime. Only the budget-gate section crosses into enforceable territory, because eval-run budgets bind the project's *own* eval CI, which Praxion does drive.

## Sources

- [Anthropic — Demystifying evals for AI agents](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents) — production monitoring as ground truth, swiss-cheese multi-layer detection, offline-evals-create-false-confidence. **[VERIFIED — Anthropic primary]**
- [Anthropic — Effective harnesses for long-running agents](https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents) — budgets as enforced gates, exhaustion as a normal termination. **[VERIFIED — Anthropic primary]**
- `rules/ml/gpu-budget-conventions.md` — the budget-gate discipline (declare → enforce → exhaustion-is-normal) this section mirrors.
