# Eval Design Patterns

Detailed guidance on designing effective agent evaluations -- golden datasets, LLM-as-judge, grader design, scoring, and non-determinism handling. Reference material for the [Agent Evals](../SKILL.md) skill.

## Golden Datasets

A golden dataset contains trusted inputs and ideal outputs, serving as the benchmark for agent quality. It is the foundation of any eval suite.

### Creation Approaches

| Approach | Source | Quality | Effort | When to Use |
| --- | --- | --- | --- | --- |
| **Production failures** | Real user-reported bugs and failures | Highest | Low (already exist) | Always start here |
| **Synthetic generation** | LLM-generated diverse test cases | Medium | Low | Expand coverage quickly |
| **Human-in-the-loop** | SME-reviewed and curated | High | High | Calibration, edge cases |
| **Hybrid** | Small human core + synthetic expansion | High | Medium | Best balance |

**Production failures first**: Anthropic's primary recommendation. Real failures are more representative than synthetic scenarios. Start with 20-50 tasks drawn from actual user issues.

### Synthetic Data Generation

Use LLMs to expand a small golden dataset:

```python
# DeepEval's Synthesizer for dataset expansion
from deepeval.synthesizer import Synthesizer

synthesizer = Synthesizer()
goldens = synthesizer.generate_goldens_from_docs(
    document_paths=["docs/api_reference.md"],
    max_goldens_per_context=3,
)

# Manual approach: use an LLM to generate variations
GENERATION_PROMPT = """
Given this eval task:
  Input: {input}
  Expected: {expected}

Generate 3 variations that test the same capability but with different:
- Input phrasing
- Edge cases
- Complexity levels

Output as JSON array of {{input, expected}} objects.
"""
```

### Dataset Management

- **Version datasets alongside agent code** -- datasets are eval code
- **Grow continuously**: add a new case with every bug fix and capability addition
- **Balance**: maintain both positive cases (should do) and negative cases (shouldn't do)
- **Monitor saturation**: when agents consistently pass all cases, add harder variants
- **Retire saturated cases**: move them to the regression suite where they guard against backsliding

### Dataset Format

Use JSONL for compatibility across frameworks:

```jsonl
{"input": "Fix the auth bypass in login.py", "target": "Parameterized queries prevent SQL injection", "metadata": {"difficulty": "medium", "category": "security"}}
{"input": "Refactor the payment module to use dependency injection", "target": "Constructor injection with interface abstraction", "metadata": {"difficulty": "hard", "category": "refactoring"}}
```

## LLM-as-Judge

The most common methodology for evaluating agent quality at scale. A judge model evaluates agent outputs against a rubric.

### Patterns

| Pattern | Description | When to Use |
| --- | --- | --- |
| **Direct assessment** | Judge evaluates a single response on a rubric (point-wise) | Default choice; simplest |
| **Pairwise comparison** | Judge selects the better of two responses | A/B testing, model comparison |
| **Multi-agent judging** | Multiple LLM judges debate; consensus scoring | High-stakes, ambiguous cases |
| **Chain-of-thought** | Judge outputs rationale before score | Improves quality and explainability |

### Rubric Design

Structure rubrics with explicit scoring criteria:

```python
RUBRIC_TEMPLATE = """
Evaluate the agent's code fix on these dimensions:

1. **Correctness** (0-1): Does the fix address the reported issue?
   - 1.0: Issue fully resolved, no regressions
   - 0.7: Issue resolved but minor edge case missed
   - 0.3: Partial fix, core issue remains
   - 0.0: Fix does not address the issue

2. **Code quality** (0-1): Is the fix well-written?
   - 1.0: Clean, idiomatic, follows project conventions
   - 0.5: Functional but style issues or minor anti-patterns
   - 0.0: Hacky, introduces tech debt

3. **Safety** (0-1): Does the fix introduce new vulnerabilities?
   - 1.0: No new vulnerabilities, follows security best practices
   - 0.0: Introduces a security issue

Agent input: {input}
Agent output: {output}
Expected behavior: {expected}

Score each dimension, then provide a final weighted score:
  final = 0.5 * correctness + 0.3 * quality + 0.2 * safety
"""
```

### Few-Shot Calibration

Few-shot prompting increases judge consistency from ~65% to ~78%:

```python
JUDGE_PROMPT = """
You are evaluating an AI coding agent's output.

## Examples

### Example 1 (Score: 0.9)
Input: "Fix the null pointer in user.py"
Output: "Added null check before accessing user.email..."
Rationale: Correct fix, clean code, handles edge case.

### Example 2 (Score: 0.3)
Input: "Fix the null pointer in user.py"
Output: "Wrapped entire function in try/except..."
Rationale: Masks the error rather than fixing root cause.

## Your Task

Input: {input}
Output: {output}

Provide your score (0.0-1.0) with rationale.
"""
```

### Anti-Patterns

- **Overly rigid grading**: penalizing "96.12" when "96.124991..." is equally correct
- **Single-dimension scoring**: using one number for multi-faceted tasks
- **No calibration**: trusting LLM judges without validating against human judgments
- **Ambiguous rubrics**: "Is the output good?" without explicit criteria
- **Judge model mismatch**: using a weaker model to judge a stronger model's output

## Grader Design

### Layered Grading Strategy

Apply graders in order of cost and determinism:

```text
1. Code-based graders (free, deterministic)
   - Test suite execution (pytest exit code)
   - JSON schema validation
   - String/regex matching
   - File existence checks
   |
   v  (only if code-based cannot assess)
2. Model-based graders (API cost, flexible)
   - LLM-as-judge with structured rubric
   - Factuality checking
   - Code quality assessment
   |
   v  (only for calibration or ambiguous cases)
3. Human graders (expensive, gold standard)
   - SME review of sample outputs
   - Calibration of model graders
   - Edge case adjudication
```

### Code-Based Graders

Deterministic checks for objective criteria:

```python
def grade_coding_task(agent_output: str, workspace_dir: str) -> dict:
    """Grade a coding agent's output by running the test suite."""
    import subprocess

    result = subprocess.run(
        ["pytest", "tests/", "-q", "--tb=short"],
        cwd=workspace_dir,
        capture_output=True,
        text=True,
        timeout=60,
    )

    return {
        "pass": result.returncode == 0,
        "score": 1.0 if result.returncode == 0 else 0.0,
        "explanation": result.stdout if result.returncode == 0 else result.stderr,
    }
```

### Model-Based Graders

Use structured output for reliable scoring:

```python
from pydantic import BaseModel, Field

class EvalScore(BaseModel):
    correctness: float = Field(ge=0.0, le=1.0)
    code_quality: float = Field(ge=0.0, le=1.0)
    safety: float = Field(ge=0.0, le=1.0)
    rationale: str
    final_score: float = Field(ge=0.0, le=1.0)

# Use structured output with your LLM of choice
# to get reliable, parseable scores
```

### Human-in-the-Loop Grading

Use human graders for:

- **Calibration**: validate LLM-as-judge accuracy (sample 10-20% of cases)
- **Edge cases**: ambiguous outputs where automated grading fails
- **Golden dataset creation**: label reference outputs for new eval scenarios
- **Periodic audit**: spot-check eval results to catch grader drift

## Scoring and Metrics

### Core Metrics Reference

| Metric | Type | Formula/Description | When to Report |
| --- | --- | --- | --- |
| **pass@k** | Consistency | P(at least 1 success in k trials) | Always (optimistic bound) |
| **pass^k** | Consistency | P(all k trials succeed) | Always (pessimistic bound) |
| **Task completion** | Outcome | % of tasks fully completed | Primary outcome metric |
| **Tool call accuracy** | Trajectory | Correct calls / total calls | Tool-using agents |
| **Faithfulness** | Quality | Claims grounded in context | RAG and research agents |
| **Cost per task** | Efficiency | Total tokens * price / tasks | Always (budget tracking) |
| **Latency p50/p95** | Efficiency | End-to-end timing percentiles | Production readiness |
| **Turn count** | Efficiency | Steps to solution | Efficiency optimization |

### Statistical Aggregation

Handle non-determinism with proper statistics:

```python
import numpy as np
from scipy import stats

def aggregate_eval_results(
    scores: list[list[float]],  # scores[task][trial]
    confidence: float = 0.95,
) -> dict:
    """Aggregate multi-trial eval results with confidence intervals."""
    task_means = [np.mean(trials) for trials in scores]

    mean_score = np.mean(task_means)
    ci = stats.t.interval(
        confidence,
        df=len(task_means) - 1,
        loc=mean_score,
        scale=stats.sem(task_means),
    )

    # pass@k: at least one trial succeeds per task
    pass_at_k = np.mean([any(t >= 0.5 for t in trials) for trials in scores])

    # pass^k: all trials succeed per task
    pass_pow_k = np.mean([all(t >= 0.5 for t in trials) for trials in scores])

    return {
        "mean": mean_score,
        "ci_lower": ci[0],
        "ci_upper": ci[1],
        "pass_at_k": pass_at_k,
        "pass_pow_k": pass_pow_k,
        "n_tasks": len(scores),
        "n_trials": len(scores[0]),
    }
```

### Composite Scoring

Combine multiple dimensions with explicit weights:

```python
def composite_score(
    correctness: float,
    code_quality: float,
    safety: float,
    efficiency: float,
    weights: dict | None = None,
) -> float:
    """Weighted composite score across eval dimensions."""
    w = weights or {
        "correctness": 0.4,
        "code_quality": 0.25,
        "safety": 0.25,
        "efficiency": 0.1,
    }
    return (
        w["correctness"] * correctness
        + w["code_quality"] * code_quality
        + w["safety"] * safety
        + w["efficiency"] * efficiency
    )
```

## Non-Determinism Deep Dive

### Why temperature=0 Is Not Deterministic

Research confirms that even with `temperature=0`, LLM outputs vary across runs due to GPU floating-point non-determinism, batching effects, and infrastructure changes. Gaps up to 24.9 percentage points between pass@k and pass^k have been documented in agentic evaluations.

**Practical implication**: a single trial is never sufficient. Always run multiple trials and report statistical metrics.

### Trial Strategy

| Scenario | Minimum Trials | Rationale |
| --- | --- | --- |
| Regression testing | 3 | Catch obvious regressions quickly |
| Capability evaluation | 5 | Balance cost with statistical signal |
| High-variance tasks | 10+ | Enough data for confidence intervals |
| Model comparison | 10+ | Statistical significance for A/B comparison |
| Publication/reporting | 20+ | Robust confidence intervals |

**Cost vs. coverage tradeoff**: 50 tasks x 5 trials x LLM grading = 250+ API calls per run. Use tiered execution to manage costs.

### Reporting Both Metrics

Always report pass@k and pass^k together:

```text
Task: Fix SQL injection vulnerability
  pass@5:  0.92  (at least 1 of 5 trials succeeds)
  pass^5:  0.68  (all 5 trials succeed)
  gap:     0.24  (indicates high variance -- investigate)
```

A large gap indicates the agent sometimes fails at a task it can solve. Investigate: is it a flaky grader, an edge case the agent handles inconsistently, or a genuine reliability issue?

## Agent Type Patterns

### Coding Agents

- **Primary grader**: test suite execution (deterministic, objective)
- **Secondary grader**: LLM-as-judge for code quality (style, maintainability)
- **Trajectory checks**: did the agent read relevant files before editing? Run tests after changes?
- **State artifacts**: verify generated/modified files, git diff analysis

### Conversational Agents

- **Multi-turn simulation**: generate diverse user personas, test across conversation flows
- **Interaction quality**: empathy, clarity, grounding in knowledge base
- **Boundary testing**: does the agent stay within its defined scope?
- **Verifiable outcomes**: check end-state (booking made, ticket created) alongside response quality

### Research Agents

- **Groundedness**: every claim must cite a source (deterministic check)
- **Coverage**: required facts present in the output
- **Source quality**: are sources authoritative and current?
- **Synthesis quality**: LLM-as-judge for coherence and insight

### Tool-Using Agents

- **Tool selection accuracy**: correct tool chosen from available options
- **Parameter construction**: correct parameters passed to tools
- **Ordering evaluation**: use strict matching only when ordering genuinely matters (e.g., read-before-write); default to unordered or subset matching
- **Failure recovery**: agent handles tool errors gracefully (retries, fallbacks)
- **Novel combinations**: allow valid tool paths the eval designer did not anticipate
