# Prompt Testing

Single-prompt regression testing in depth — Promptfoo end-to-end (see `../assets/promptfoo-prompt-suite.yaml`); pytest harness patterns; regression detection on prompt/model swap; non-determinism handling; LLM-as-judge bias mitigation at the single-prompt layer.

Back to: [../SKILL.md](../SKILL.md)

## When to Read This File

Load this deep dive when you are:

- Setting up prompt regression tests for the first time.
- Deciding between Promptfoo and DeepEval for your stack.
- Designing a test harness in pytest for structured-output prompts.
- Handling non-determinism (`temperature=0` does not guarantee exact match).
- Detecting regressions when either the prompt or the model changes.
- Writing LLM-as-judge assertions and wanting to know which biases to mitigate here vs. defer to `agent-evals`.

`SKILL.md` covers the assertion primitives and framework selection at a summary level. This file is the operational deep dive.

## Boundary: What This Skill Tests vs. `agent-evals`

| Scope | This skill | `agent-evals` |
|-------|-----------|---------------|
| Single prompt → single response assertion | Yes | No (defers here) |
| Structured-output schema conformance | Yes | No |
| Prompt-version regression detection | Yes | No |
| Multi-turn conversation grading | No (defer) | Yes |
| Trajectory-level agent eval | No (defer) | Yes |
| LLM-as-judge rubric engineering | Brief mitigation notes only | Full treatment |
| Grader reliability (κ / Krippendorff α) | No (defer) | Yes |
| Eval CI architecture (tiered execution, cost budgeting) | No (defer) | Yes |

The clean test: if the evaluation is one prompt → one response, it belongs here. Any multi-turn flow belongs in `agent-evals`.

## Assertion Primitives

### Cheap, deterministic guards

Prefer these when possible. They run fast, scale to CI, and give unambiguous pass/fail signals.

- **`contains` / `not-contains`** — substring presence or absence. Use for label classifiers, safety assertions, format markers.
- **`equals`** — exact match. Use when the output is highly constrained (classifier labels) and you have accepted the non-determinism risk.
- **`regex`** — pattern match. Use for format compliance (date strings, ID shapes) when structured output is not in play.
- **`starts-with` / `ends-with`** — prefix/suffix checks for envelope invariants.
- **Length bounds** — `min_length`, `max_length`. Use to catch truncation (model hit `max_tokens`) and blabber (model ignored the brevity instruction).

### Structured-output assertions

When the output is JSON/YAML/structured, deterministic assertions get richer:

- **JSON Schema conformance** — fail any schema drift. This is cheap and catches most silent regressions.
- **Property-level assertions** — extract a field and assert on it (e.g., `response.title` contains expected keyword; `response.tags` has length ≥ 3).
- **Type assertions** — beyond schema: assert `int` stays `int`, not a quoted numeric string.

Structured output + per-property assertions is the highest-signal test layer for extraction and classification prompts.

### LLM-rubric (judge) assertions

When the output is free-form natural language and deterministic checks fall short. Use sparingly:

- **Bias**: position bias, length bias, self-preference bias all skew the judge's verdict. See §LLM-as-Judge Pitfalls.
- **Cost**: each judge call is another model call. Budget accordingly.
- **Non-reproducibility**: judges are non-deterministic even at low temperature. Run paired-order and aggregate; see below.

For deep rubric engineering — inter-judge agreement measurement, analytic rubrics, scoring calibration — defer to `agent-evals`.

## Promptfoo End-to-End

### Why Promptfoo

- YAML-first, readable by non-engineers.
- CI-native (GitHub Actions, GitLab integration).
- Multi-provider in one file.
- Red-teaming / adversarial test generation built in.
- Maintained actively as of 2026; ecosystem momentum is strong.

Best fit: non-Python teams, cross-provider testing, teams already using YAML for eval config elsewhere.

### Minimal suite

See `../assets/promptfoo-prompt-suite.yaml` for the starter template.

```yaml
description: Single-prompt regression suite (starter)

providers:
  - id: anthropic:messages:claude-sonnet-4-x
    config:
      temperature: 0
      max_tokens: 512

prompts:
  - label: classifier-v1
    raw: |
      You classify the user message into exactly one of: bug, feature, question.
      Respond with the single lowercase label only.

      <user_message>
      {{input}}
      </user_message>

tests:
  - description: Bug report is classified as bug
    vars:
      input: "The login button throws 500 on Safari 17."
    assert:
      - type: contains
        value: bug
      - type: not-contains
        value: feature

  - description: Feature request is classified as feature
    vars:
      input: "Please add dark mode to the settings panel."
    assert:
      - type: contains
        value: feature
```

Run: `npx promptfoo@latest eval -c promptfoo-prompt-suite.yaml`.

### Advanced assertion types

- `javascript` / `python` — run a custom function on the output. Use for property-level structured-output checks that go beyond built-ins.
- `similar` — semantic similarity to an expected string, using embeddings. Useful when exact wording varies but meaning must stay stable.
- `is-json` — validates JSON parseability.
- `llm-rubric` — LLM-as-judge with a rubric string. Use last resort; mitigate bias.

### Fixtures keyed to prompt versions

Each prompt version should have its own fixture set. When you bump from `v2` to `v3`:

1. Copy `fixtures/v2.yaml` to `fixtures/v3.yaml`.
2. Add new fixtures covering the reason `v3` exists (new edge cases, new classes).
3. Run `v3` against both v2's fixtures (no regression allowed) and v3's fixtures (new cases must pass).

### Running against multiple providers

Promptfoo can run the same prompt against multiple providers in one suite. Useful for:

- Cross-model regression (does `v3` work on the backup provider in case of outage?).
- Model-upgrade evaluation (how does `v3` perform on the next-generation model?).

Do not combine in the same CI run as the primary regression suite — separate the dimension to keep signal crisp.

## DeepEval / Pytest End-to-End

### Why DeepEval

- Python-native, pytest-style. Integrates cleanly with existing Python test runs.
- 60+ built-in metrics (correctness, hallucination, toxicity, etc.).
- Strong CI integration with GitHub Actions.

Best fit: Python teams, mixed-code-and-prompt test suites.

### Minimal pytest pattern

```python
# tests/test_issue_classifier.py
import pytest
from deepeval import assert_test
from deepeval.test_case import LLMTestCase
from deepeval.metrics import AnswerRelevancyMetric

# The function under test — a single prompt call.
from myapp.prompts import classify_issue

@pytest.mark.parametrize("input_text,expected_label", [
    ("The login button throws 500 on Safari 17.", "bug"),
    ("Please add dark mode to the settings panel.", "feature"),
    ("How do I reset my API key?", "question"),
])
def test_classifier(input_text: str, expected_label: str) -> None:
    output = classify_issue(input_text)
    assert output.strip().lower() == expected_label
```

For this three-class classifier, an exact-match assertion is sufficient. Escalate to `AnswerRelevancyMetric` or LLM-rubric only when exact match is infeasible.

### Structured-output testing in pytest

When the prompt returns a Pydantic model, testing collapses to standard pytest:

```python
import pytest
from myapp.prompts import extract_fields
from myapp.schemas import ExtractedFields

def test_extraction_shape() -> None:
    output: ExtractedFields = extract_fields("Replace with real fixture text.")
    assert isinstance(output, ExtractedFields)
    assert output.title
    assert 0 < len(output.tags) <= 5
    assert len(output.summary.split()) <= 40
```

The Pydantic model already enforces types. The test adds semantic bounds (tag count, summary length) the schema alone cannot express.

### Pass@k for non-determinism

When you expect occasional non-determinism, run k trials and assert that `p` (success count) meets a threshold:

```python
def test_classifier_pass_at_k(input_text="The login button throws 500 on Safari 17.") -> None:
    trials = [classify_issue(input_text) for _ in range(5)]
    successes = sum(t.strip().lower() == "bug" for t in trials)
    assert successes >= 4, f"Expected >= 4/5 successes, got {successes}/5: {trials}"
```

Pick k = 3–5 for a reasonable cost/signal tradeoff.

## Non-Determinism Discipline

### `temperature=0` does not guarantee exact-match

Even at `temperature=0`, outputs can vary across:

- **Backend revisions**: provider upgrades the model endpoint; token sampling may shift.
- **Hardware**: different serving hardware produces different numerics at the logit layer.
- **Batch boundaries**: requests batched with other requests may differ from solo requests.
- **Structured-output constrained decoding**: the grammar can produce different token orderings for the same JSON.

Consequence: assertions that compare full output strings character-by-character are flaky even at `temperature=0`. Design assertions that tolerate drift on irrelevant dimensions.

### Strategies that tolerate drift

- **Semantic equivalence**: normalize whitespace, case, and field ordering before comparison.
- **Schema conformance + property-level checks**: structural equivalence instead of textual equivalence.
- **pass@k**: accept occasional misses if the rate stays below threshold.
- **Distribution testing**: for low-variance tasks (classifiers), sample k times and assert the majority class.
- **LLM-rubric with paired-order aggregation**: when judging, swap A/B order across two calls and aggregate.

### Flaky-test handling

When a test flakes intermittently:

1. **Do not add a retry loop to suppress flakiness.** This hides regressions.
2. **Do identify the non-determinism source.** Is it model drift (needs pass@k)? Provider drift (needs to be logged)? Genuine regression (needs investigation)?
3. **Do loosen the assertion once, deliberately.** If the test is too strict for genuine low-level variation, rewrite it at the semantic level.
4. **Do quarantine with a failing-test annotation**, not delete. A quarantined test still signals.

## Regression Detection on Prompt/Model Swap

### The independence rule

Treat these as **two independent experiments**, not one combined change:

- **Prompt version bump** with the model held constant: isolates the prompt's effect.
- **Model version bump** with the prompt held constant: isolates the model's effect.

A single commit that changes both is a scientific method failure — you cannot attribute a regression (or an improvement) to either dimension.

In practice: land one, run the suite, promote; land the other, re-run, promote. Two deploys, two eval runs.

### Regression suite composition

- **Golden fixtures**: hand-curated inputs with expected outputs. Cover all classes and known edge cases. These never change; they are the stable baseline.
- **Failure-mode fixtures**: every production-observed failure has a fixture demonstrating the correct handling. Grows over time; each fixture is cheap insurance against the same regression recurring.
- **Adversarial / red-team fixtures**: inputs designed to stress the prompt (prompt-injection attempts, edge-case formatting, out-of-distribution classes). See `./prompt-injection-hardening.md`.

### Regression dashboard

For a prompt with a nontrivial suite, a regression dashboard shows:

- Pass rate per prompt version.
- Pass rate per fixture (which fixtures are the canaries?).
- Cost per request per version (did `v3` regress on cost?).
- Latency per version.

Most prompt-management platforms (`./versioning.md`) ship this view.

## LLM-as-Judge at the Single-Prompt Layer

`agent-evals` owns the full rubric-engineering treatment. At the single-prompt layer, the minimum mitigation set is:

### Position bias

Swap the order of the two outputs being compared. On average across both orderings, the verdict is less biased. Bias magnitude can flip >10% of verdicts — meaningful.

```text
# Call 1
Compare A and B; A = {output_from_prompt_v1}, B = {output_from_prompt_v2}.
Which is better?

# Call 2
Compare A and B; A = {output_from_prompt_v2}, B = {output_from_prompt_v1}.
Which is better?

Verdict: aggregate across both calls; a "better" output wins both.
```

### Length / verbosity bias

Judges prefer longer, more fluent outputs. Control for length in the rubric: instruct the judge to disregard length and to penalize unnecessary verbosity.

### Self-preference bias

Judges tend to prefer outputs from their own family (GPT judging GPT, Claude judging Claude). Use a different-family judge or ensemble.

### Agreeableness bias

In class-imbalanced settings, judges can have TPR > 96% and TNR < 25% — they agree with the "yes" verdict too readily. Balance the fixture classes and use a calibrated rubric.

### When the mitigations are insufficient

Escalate to `agent-evals`: paired-order aggregation, inter-judge agreement measurement (Cohen's κ, Krippendorff α), analytic rubrics, multi-judge ensembles. This skill's job ends at the "I know these biases exist and I apply the simple mitigations" level.

## CI Integration

### Minimal CI job

1. Checkout repo.
2. Install dependencies.
3. Run the eval suite against the prompt version in the branch.
4. Compare results to the baseline (main branch prompt version).
5. Fail the job on regression (pass rate below threshold).
6. Upload artifacts (full eval JSON, HTML report).

For Promptfoo: a single CLI invocation + artifact upload step.

For DeepEval / pytest: a pytest invocation tagged as `@pytest.mark.llm_eval`, runnable separately from fast unit tests, wired to a scheduled-or-PR trigger.

### Cost budgeting

Prompt evaluations run real model calls; cost can blow up. Guardrails:

- **Split fast and slow suites**. Fast = deterministic assertions, small fixture set; slow = LLM-rubric, large fixture set. Run fast on every PR; slow on merge or nightly.
- **Token-budget per PR**. Cap the total token cost of the eval suite; fail the job if exceeded.
- **Cache model responses** for deterministic-only suites when the prompt hasn't changed. Invalidate on prompt version bump.

Deeper cost-tiering architecture belongs in `agent-evals`.

## Cross-References

- `../SKILL.md` — overview of assertion types and framework selection.
- `./versioning.md` — regression suites gate promotion to `prod`.
- `./structured-output.md` — property-level assertions on Pydantic/Zod-validated output.
- `./few-shot-patterns.md` — exemplar changes trigger regression runs.
- `./reasoning-and-cot.md` — non-determinism interplay with reasoning effort.
- `./prompt-injection-hardening.md` — adversarial fixtures as part of the regression suite.
- `../assets/promptfoo-prompt-suite.yaml` — starter Promptfoo suite.
- Sibling skill: `agent-evals` — multi-turn eval design, rubric engineering, grader reliability, eval CI architecture.
- Sibling skill: `external-api-docs` — fetch current SDK signatures for test harness.

## External Sources

- Promptfoo — https://github.com/promptfoo/promptfoo and https://www.promptfoo.dev/docs/.
- DeepEval — https://deepeval.com/.
- Inspect AI — offline / reproducibility-focused evaluation.
- OpenAI Evals — OpenAI-centric framework.
- *Systematic Study of Position Bias in LLM-as-a-Judge* (IJCNLP 2025).
- *Survey on LLM-as-a-Judge* (arxiv 2411.15594).
- Arize LLM-as-a-Judge primer.
