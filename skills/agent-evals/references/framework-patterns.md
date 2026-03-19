# Framework Patterns

Detailed comparison and code examples for the three primary Python-friendly eval frameworks, plus brief coverage of secondary options. Reference material for the [Agent Evals](../SKILL.md) skill.

## Framework Comparison Matrix

| Criterion | Inspect AI | DeepEval | Promptfoo |
| --- | --- | --- | --- |
| **License** | MIT | Apache 2.0 | MIT |
| **Language** | Python | Python | TypeScript (Python providers) |
| **Agent eval focus** | High (built-in agents, sandboxing) | High (trace-based, agent metrics) | High (agent SDK providers) |
| **Built-in metrics** | 10+ scorers | 30+ metrics | Assertions + LLM rubrics |
| **Pytest integration** | No (CLI: `inspect eval`) | Native (`pytest` + `deepeval`) | No (CLI: `promptfoo eval`) |
| **Sandboxing** | Docker built-in | No | Config-based |
| **CI/CD** | Custom scripts | Via pytest runner | Dedicated GitHub Action |
| **Red-teaming** | No | No | Built-in |
| **Visualization** | Web viewer + VS Code extension | Cloud dashboard | CLI + web UI |
| **Self-hostable** | Yes (fully OSS) | Yes (OSS core) | Yes (fully OSS) |
| **Maturity** | High (UK AISI, Anthropic, DeepMind) | High (active development) | High (acquired by OpenAI 2026) |
| **Learning curve** | Moderate (task/solver/scorer model) | Low (pytest-familiar) | Low (YAML config) |
| **Install** | `pip install inspect-ai` | `pip install deepeval` | `npm install -g promptfoo` |

## Inspect AI Patterns

### Architecture

Inspect AI uses a composable **Task = Dataset + Solver + Scorer** model:

- **Dataset**: collection of `Sample` objects (input, target, optional metadata)
- **Solver**: pipeline of steps the agent executes (system messages, tool use, generation)
- **Scorer**: evaluates the agent's output against the target

```python
from inspect_ai import task, Task
from inspect_ai.dataset import Sample
from inspect_ai.scorer import model_graded_fact
from inspect_ai.solver import generate, system_message, use_tools
from inspect_ai.tool import bash, python

@task
def coding_eval():
    return Task(
        dataset=[
            Sample(
                input="Fix the SQL injection vulnerability in auth.py",
                target="The parameterized query prevents SQL injection",
                metadata={"difficulty": "medium"},
            ),
        ],
        solver=[
            system_message("You are a security-focused coding agent."),
            use_tools([bash(), python()]),
            generate(),
        ],
        scorer=model_graded_fact(),
        sandbox="docker",
    )
```

Run with: `inspect eval coding_eval.py --model anthropic/claude-sonnet-4-6`

### Custom Scorers

Build scorers that combine deterministic checks with LLM grading:

```python
from inspect_ai.scorer import Score, Target, scorer, accuracy, CORRECT, INCORRECT

@scorer(metrics=[accuracy()])
def test_pass_scorer():
    async def score(state, target: Target) -> Score:
        # Extract the agent's generated code
        code_output = state.output.completion

        # Deterministic check: run the test suite
        result = await sandbox().exec(["pytest", "tests/", "-q"])

        if result.returncode == 0:
            return Score(value=CORRECT, explanation="All tests pass")

        return Score(
            value=INCORRECT,
            explanation=f"Tests failed:\n{result.stderr}",
        )

    return score
```

### Sandboxed Execution

Inspect AI provides Docker-based sandboxing for safe agent evaluation:

```python
@task
def sandboxed_eval():
    return Task(
        dataset=read_dataset("evals/coding_tasks.jsonl"),
        solver=[use_tools([bash(), python()]), generate()],
        scorer=test_pass_scorer(),
        sandbox=("docker", "eval-sandbox.dockerfile"),
        max_messages=30,  # Limit agent turns
    )
```

```dockerfile
# eval-sandbox.dockerfile
FROM python:3.13-slim
RUN pip install pytest httpx
COPY test_project/ /workspace/
WORKDIR /workspace
```

### Multi-Trial Runs

Handle non-determinism with multiple trials:

```bash
# Run 5 trials per task, report pass@k metrics
inspect eval coding_eval.py --model anthropic/claude-sonnet-4-6 -T 5
```

### Evals Library

Inspect AI includes 100+ pre-built evaluations. Browse at `inspect list tasks` or on the Inspect AI documentation.

## DeepEval Patterns

### Pytest Integration

DeepEval integrates natively with pytest:

```python
import pytest
from deepeval import assert_test
from deepeval.metrics import TaskCompletionMetric
from deepeval.test_case import LLMTestCase

@pytest.mark.parametrize(
    "task_input,expected_outcome",
    [
        ("Refactor the auth module to use dependency injection", "DI pattern applied"),
        ("Add retry logic to the API client", "Retry with backoff implemented"),
    ],
)
def test_agent_task_completion(task_input, expected_outcome):
    # Run your agent here
    agent_output = run_my_agent(task_input)

    test_case = LLMTestCase(
        input=task_input,
        actual_output=agent_output,
    )
    metric = TaskCompletionMetric(threshold=0.7)
    assert_test(test_case, [metric])
```

Run with: `deepeval test run tests/evals/ --verbose`

### Agent-Specific Metrics

**ToolCorrectnessMetric** -- evaluate tool call accuracy with configurable strictness:

```python
from deepeval.metrics import ToolCorrectnessMetric
from deepeval.test_case import LLMTestCase, ToolCall, ToolCallParams

metric = ToolCorrectnessMetric(
    threshold=0.7,
    evaluation_params=[
        ToolCallParams.TOOL,           # Correct tool selected
        ToolCallParams.INPUT_PARAMETERS,  # Correct parameters
    ],
    should_consider_ordering=True,     # Order matters
)

test_case = LLMTestCase(
    input="Look up our refund policy and summarize it",
    actual_output="Our refund policy allows returns within 30 days...",
    tools_called=[
        ToolCall(name="PolicySearch", input_parameters={"query": "refund policy"}),
        ToolCall(name="Summarize", input_parameters={"text": "..."}),
    ],
    expected_tools=[
        ToolCall(name="PolicySearch", input_parameters={"query": "refund policy"}),
        ToolCall(name="Summarize", input_parameters={"text": "..."}),
    ],
)
```

**TaskCompletionMetric** -- evaluate whether the agent completed the assigned task:

```python
from deepeval.metrics import TaskCompletionMetric

metric = TaskCompletionMetric(
    threshold=0.7,
    # Uses LLM-as-judge internally to assess completion
)
```

### Trace-Based Evaluation

Capture full agent execution traces for trajectory analysis:

```python
from deepeval.tracing import observe, update_current_span

@observe(name="agent_execution")
def run_agent_with_tracing(task: str) -> str:
    # Agent execution logic
    update_current_span(metadata={"task": task})
    result = my_agent.run(task)
    return result.output
```

### Synthetic Data Generation

DeepEval's `Synthesizer` generates diverse test cases from documents. See [eval-design-patterns.md](eval-design-patterns.md#synthetic-data-generation) for code examples and dataset management guidance.

## Promptfoo Patterns

### YAML Configuration

Promptfoo uses declarative YAML for eval definition:

```yaml
# promptfooconfig.yaml
description: "Agent coding task evaluation"

providers:
  - id: anthropic:claude-agent-sdk
    config:
      model: claude-sonnet-4-6
      working_dir: ./test-codebase
      append_allowed_tools: ["Write", "Edit", "Bash", "Read"]

prompts:
  - "Fix the following issue: {{task}}"

tests:
  - vars:
      task: "The login endpoint returns 500 when email contains unicode"
    assert:
      - type: llm-rubric
        value: "The fix correctly handles unicode in email addresses"
        threshold: 0.8
      - type: cost
        threshold: 0.25
      - type: latency
        threshold: 30000
      - type: javascript
        value: |
          const output = String(output);
          output.includes('def') || output.includes('function');
```

Run with: `promptfoo eval`

### Trajectory Assertions

Evaluate agent tool usage patterns:

```yaml
tests:
  - vars:
      task: "Run the test suite and fix any failures"
    assert:
      # Agent must run tests at least once
      - type: trajectory:step-count
        value:
          type: command
          pattern: "pytest*"
          min: 1
      # Agent must use the Edit tool
      - type: trajectory:tool-used
        value: Edit
      # Agent should read files before editing
      - type: trajectory:tool-sequence
        value:
          - Read
          - Edit
```

### Agent SDK Providers

Direct integration with agent SDKs:

```yaml
# Claude Agent SDK
providers:
  - id: anthropic:claude-agent-sdk
    config:
      model: claude-sonnet-4-6
      working_dir: ./workspace
      append_allowed_tools: ["Write", "Edit", "Bash", "Read", "Glob", "Grep"]
      max_turns: 20

# OpenAI Codex SDK
providers:
  - id: openai:codex-sdk
    config:
      model: codex-mini
      working_dir: ./workspace
```

### Red-Teaming

Built-in security evaluation:

```yaml
# promptfoo redteam configuration
redteam:
  plugins:
    - prompt-injection
    - pii
    - jailbreak
    - harmful:cybercrime
  strategies:
    - jailbreak:tree
    - prompt-injection:recursive
  numTests: 50
```

Run with: `promptfoo redteam run`

## Secondary Frameworks

### Braintrust

Best-in-class CI/CD integration with automatic PR score comments:

```python
from braintrust import Eval, init_dataset
from autoevals import Factuality

Eval(
    "agent-coding-eval",
    data=lambda: init_dataset("coding-tasks"),
    task=lambda input: run_my_agent(input),
    scores=[Factuality],
)
```

GitHub Action posts eval score breakdowns directly on PRs. Commercial platform with open-source `autoevals` library (`pip install autoevals`).

### AgentEvals (LangChain)

Focused trajectory evaluation with multiple matching modes:

```python
from agentevals.trajectory import create_trajectory_match_evaluator

# Strict: exact tool call sequence must match
strict_eval = create_trajectory_match_evaluator(
    trajectory_match_mode="strict",
    tool_args_match_mode="exact",
)

# Unordered: correct tools called, order irrelevant
flexible_eval = create_trajectory_match_evaluator(
    trajectory_match_mode="unordered",
    tool_args_match_mode="subset",
)

result = strict_eval(
    outputs=actual_trajectory,
    reference_outputs=expected_trajectory,
)
```

Install: `pip install agentevals`

### Ragas

Reference-free RAG evaluation (not general agent evals):

```python
from ragas import evaluate
from ragas.metrics import faithfulness, answer_relevancy, context_precision

result = evaluate(
    dataset=eval_dataset,
    metrics=[faithfulness, answer_relevancy, context_precision],
)
```

Use Ragas **only** for RAG-specific evaluation (retrieval quality, groundedness). For general agent evals, use the primary frameworks above.

## Selection Decision Tree

1. **Is this a RAG-specific eval?** --> Ragas
2. **Do you need red-teaming / security testing?** --> Promptfoo
3. **Are you evaluating a Claude or OpenAI agent SDK?** --> Promptfoo (direct SDK providers)
4. **Do you want pytest-native workflow?** --> DeepEval
5. **Do you need Docker sandboxing?** --> Inspect AI
6. **Is this for government/research reproducibility?** --> Inspect AI
7. **Do you need best CI/CD with PR comments?** --> Braintrust
8. **Do you only need trajectory matching?** --> AgentEvals
9. **Default for Python agents** --> DeepEval (lowest friction) or Inspect AI (most comprehensive)
