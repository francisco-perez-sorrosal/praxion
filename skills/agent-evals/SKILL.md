---
name: agent-evals
description: Designing and implementing evaluations (evals) for AI agents -- eval types,
  framework selection (Inspect AI, DeepEval, Promptfoo), golden datasets, LLM-as-judge,
  grader design, scoring, non-determinism handling, and CI/CD integration. Use when
  evaluating agent behavior, choosing an eval framework, designing eval suites, building
  golden datasets, implementing trajectory evaluation, setting up eval-driven development,
  or integrating evals into CI/CD pipelines. Python-focused with framework-agnostic patterns.
allowed-tools: [Read, Write, Edit, Glob, Grep, Bash]
compatibility: Claude Code
---

# Agent Evals

Evaluate AI agent behavior systematically. Agent evals differ fundamentally from traditional software tests -- they handle non-determinism, multi-dimensional scoring, and multiple valid solution paths. This skill covers the full eval lifecycle: design, implement, run, iterate, and integrate into CI/CD.

**Satellite files** (loaded on-demand):

- [references/framework-patterns.md](references/framework-patterns.md) -- framework comparison, Python code examples for Inspect AI, DeepEval, Promptfoo
- [references/eval-design-patterns.md](references/eval-design-patterns.md) -- golden datasets, LLM-as-judge, grader design, scoring, non-determinism
- [references/cicd-integration.md](references/cicd-integration.md) -- GitHub Actions workflows, deployment gates, regression tracking, cost management

## Gotchas

- **Non-determinism is not a bug, it's the medium.** Never expect exact output matching. Use rubrics, partial credit, and statistical aggregation. A single trial tells you almost nothing.

- **0% pass rate usually means broken eval, not broken agent.** Verify tasks are solvable by running them manually with a reference solution. Check grader fairness before blaming the agent.

- **Grading outcomes, not paths, is harder than it sounds.** An agent that uses 3 tools instead of your expected 2 may still be correct. Default to lenient trajectory matching (unordered or subset) unless ordering genuinely matters.

- **LLM-as-judge needs calibration, not blind trust.** Validate model graders against human judgments regularly. Few-shot prompting increases consistency from ~65% to ~78%. Use structured rubrics with explicit scoring criteria.

- **Cost surprises compound with trials.** Running 50 test cases x 5 trials x LLM grading = 250+ API calls per eval run. Budget upfront. Use tiered execution: full suite nightly, critical subset on PR.

- **`temperature=0` does not guarantee determinism.** Research confirms non-determinism persists even at zero temperature. Always run multiple trials and report both pass@k and pass^k.

- **Golden datasets rot.** As the agent improves, easy evals saturate and stop providing signal. Grow the dataset continuously and retire saturated cases to the regression suite.

- **Don't eval what you can assert.** If a check is deterministic (JSON schema validation, test suite execution, file existence), use a code-based grader. Reserve LLM grading for genuinely subjective or nuanced dimensions.

- **Sandboxing is not optional for tool-using agents.** Agents with file system or shell access can cause real damage during evals. Use Docker containers, temp directories, or git checkpoints.

- **Skip transcript review at your peril.** Graders can be wrong in both directions -- passing bad outputs and failing good ones. Regular transcript review builds intuition and catches grader drift.

## Why Agent Evals Differ from Traditional Tests

| Dimension | Traditional Tests | Agent Evals |
| --- | --- | --- |
| Determinism | Same input, same output | Non-deterministic: same input may produce different valid outputs |
| Success criteria | Binary pass/fail | Multi-dimensional scoring (completion, quality, efficiency, safety) |
| Valid solutions | Typically one correct answer | Many valid paths -- grade outcomes, not paths |
| Evaluation method | Assert equality | LLM-as-judge, rubrics, partial credit, statistical aggregation |
| Cost | Negligible per run | API costs per trial; cost tracking is itself a metric |
| Scope | Unit/integration/E2E on deterministic code | Multi-turn interactions, tool use sequences, reasoning chains |

**Evaluation-Driven Development (EDD)** extends TDD/BDD for non-deterministic systems. Define evals for planned capabilities before implementation, run them continuously, and use failures to drive improvement -- the same test-first philosophy, adapted for agents.

## Eval Types

### By Scope

| Type | What It Measures | When to Use |
| --- | --- | --- |
| **Final response** | Only input and final answer (black-box) | Simplest starting point; outcome-only validation |
| **Trajectory** | Actual vs. expected tool call sequences (glass-box) | Pinpoint where reasoning failed; debug agent logic |
| **Single step** | Individual decision-making in isolation (white-box) | Unit test for agent reasoning; ~50% of cases need only this |
| **Multi-turn** | Coherence across conversation turns | Conversational agents, stateful interactions |
| **End-to-end** | Full task completion in realistic environments | Production readiness validation |

### By Purpose

| Category | Pass Rate Target | Description |
| --- | --- | --- |
| **Capability** | Starts low | Defines the "hill to climb" for new features; tracks improvement |
| **Regression** | ~100% | Catches backsliding on known-good behavior |
| **Safety** | ~100% | Boundary adherence, prompt injection resistance, guardrail validation |
| **Cost/efficiency** | Budget-based | Token usage, API costs, latency per task |

As agents improve, high-performing capability evals **graduate** into regression suites. Monitor saturation -- when agents pass all solvable tasks, add harder variants.

## Getting Started: Zero to First Eval

Anthropic's roadmap from zero to reliable evals, condensed:

1. **Start with 20-50 tasks from real failures.** Production failures make better evals than synthetic scenarios. Don't wait for perfect datasets -- early evals gain traction quickly due to large effect sizes.

2. **Write unambiguous tasks with reference solutions.** Tasks must be solvable by competent agents. A 0% pass@100 usually signals broken tasks, not incapable agents.

3. **Build balanced problem sets.** Test both "should do" and "shouldn't do" cases. Avoid class imbalance -- test both undertriggering and overtriggering.

4. **Set up clean environments per trial.** Each run starts from a fresh state. Shared state between runs introduces correlated failures from infrastructure flakiness.

5. **Design thoughtful graders.** Prefer deterministic graders where possible; use LLM graders for flexibility; employ human graders for calibration. Grade outcomes, not paths.

6. **Read transcripts.** Review trial transcripts to verify graders work as intended. Surface genuine agent mistakes versus false rejections.

7. **Graduate capability evals to regression suites.** When a capability eval consistently passes, promote it to the regression suite where it must maintain ~100%.

8. **Maintain evals as living artifacts.** Same rigor as production code. Grow the dataset with every bug fix and capability addition.

## Framework Selection

Three primary Python-friendly frameworks, each with distinct strengths:

| Criterion | Inspect AI | DeepEval | Promptfoo |
| --- | --- | --- | --- |
| **Best for** | Research, reproducibility, sandboxing | Pytest-native workflow, rich metrics | Agent SDK eval, red-teaming, YAML config |
| **Language** | Python | Python | TypeScript (Python providers) |
| **Agent focus** | Built-in agents, composable solvers | Trace-based, ToolCorrectness metric | Direct Claude/Codex SDK providers |
| **Pytest** | No (CLI) | Native integration | No (CLI) |
| **Sandboxing** | Docker built-in | No | Config-based |
| **CI/CD** | Custom scripts | Via pytest runner | Dedicated GitHub Action |
| **Red-teaming** | No | No | Built-in |
| **License** | MIT | Apache 2.0 | MIT |

### Selection Guidance

| Scenario | Primary | Secondary |
| --- | --- | --- |
| Python-first, pytest workflow | DeepEval | Inspect AI |
| Agent SDK evaluation (Claude/OpenAI) | Promptfoo | DeepEval |
| Government/research/reproducibility | Inspect AI | -- |
| Enterprise CI/CD focus | Braintrust | Promptfoo |
| RAG-specific evaluation | Ragas | DeepEval |
| Red-teaming and security | Promptfoo | Custom harness |

--> See [references/framework-patterns.md](references/framework-patterns.md) for code examples and detailed comparison across all frameworks.

## Core Eval Concepts

### Grader Types

| Grader | Strengths | Weaknesses | Cost |
| --- | --- | --- | --- |
| **Code-based** | Fast, deterministic, reproducible | Brittle to valid variations | Near zero |
| **Model-based** | Flexible, captures nuance, scalable | Non-deterministic, needs calibration | API cost per call |
| **Human** | Gold standard quality | Expensive, slow, limited scale | $$/hour |

**Layered strategy**: Code-based first (cheap, deterministic), LLM fallback for what code cannot assess, human calibration to validate both. Mature teams combine all three.

### Scoring Approaches

| Approach | When to Use |
| --- | --- |
| **Binary (pass/fail)** | Deterministic outcomes (tests pass, JSON validates) |
| **Rubric-based (0-1)** | Quality assessment, multi-dimensional tasks |
| **Weighted composite** | Multi-criteria evaluation across dimensions |
| **Pairwise comparison** | A/B testing, model comparison without absolute scale |

### Non-Determinism Handling

The fundamental challenge: same input may produce different valid outputs across runs. Even `temperature=0` does not guarantee determinism.

- Run **3-5 trials** minimum per test case (10+ for high-variance outputs)
- Report **pass@k** (probability of success in k attempts, optimistic) and **pass^k** (probability all k succeed, pessimistic)
- Gaps up to 24.9 percentage points between pass@k and pass^k are documented
- Use **statistical aggregation** over individual assertions
- Implement **anomaly detection** for trend monitoring across runs

--> See [references/eval-design-patterns.md](references/eval-design-patterns.md) for full patterns on golden datasets, LLM-as-judge, grader design, and metrics.

## Agent-Specific Challenges

### Tool Use Evaluation

Agent tool use requires evaluating correct selection, parameter construction, call ordering, and failure handling. Three approaches by strictness:

- **Strict trajectory match**: exact tool call sequence must match reference
- **Unordered match**: correct tools called, order does not matter
- **Subset/superset match**: agent may call additional valid tools or skip optional ones

Grade outcomes, not exact trajectories -- agents may find valid tool combinations the eval designer did not anticipate.

### Trajectory Evaluation

Choose the right scope for the behavior being tested:

- **Final response only**: when only the outcome matters (answer correctness)
- **Trajectory**: when the path matters (tool selection, reasoning quality, efficiency)
- **Single step**: when isolating one decision point (~50% of cases need only this)
- **Full end-to-end**: when environment interaction matters (file changes, API calls, state mutations)

### Cost and Latency Tracking

Track as first-class metrics alongside correctness:

- **Token usage per task**: total input + output tokens consumed
- **Cost per successful outcome**: total cost / successful completions
- **Latency percentiles**: p50, p95, p99 end-to-end and per-step
- **Turn count**: steps taken to reach solution (efficiency proxy)

Set budgets and alerts -- if an agent uses 10x expected tokens, something is wrong.

### Statefulness

Deep agents maintain state across interactions. For reproducible evals:

- Start each trial from a **clean environment** (temp directories, Docker containers, git checkpoints)
- Evaluate **state artifacts** (generated files, modified configs) alongside responses
- Use the **VCR pattern** (record/replay) for external API calls to improve speed and reproducibility

## CI/CD Integration

Integrate evals at three levels:

1. **Eval-on-commit**: regression suite on every relevant change (prompts, model configs, agent logic, tool definitions)
2. **PR-level reporting**: post eval results as PR comments with score breakdowns and baseline comparison
3. **Deployment gates**: block deployment if eval scores drop below thresholds

**Cost management**: run full suite nightly, critical subset on every PR, smoke tests on commit.

--> See [references/cicd-integration.md](references/cicd-integration.md) for complete GitHub Actions workflows and deployment gate patterns.

## Eval-Driven Development Workflow

Apply EDD alongside TDD/BDD in agentic projects:

1. **Identify the behavior** -- define what the agent should do (from acceptance criteria or user failures)
2. **Write the eval** -- create test cases with inputs, expected outcomes, and grading criteria
3. **Establish baseline** -- run against current agent, measure pass rate
4. **Implement the change** -- modify prompts, tools, or logic
5. **Run evals** -- compare against baseline, check for regressions
6. **Iterate** -- refine until target pass rates are met across trials
7. **Graduate** -- move passing capability evals to the regression suite

This mirrors the `spec-driven-development` skill's behavioral specification workflow, with evals replacing deterministic assertions.

## Cross-Skill References

- **`python-development`** -- pytest patterns, test organization, and code quality tools for eval implementations
- **`agentic-sdks`** -- agent building patterns (the systems you are evaluating); SDK-specific testing hooks
- **`spec-driven-development`** -- behavioral specifications and acceptance criteria inform eval design; REQ IDs thread into eval case naming
- **[`llm-prompt-engineering`](../llm-prompt-engineering/SKILL.md)** -- single-prompt regression-assertion design (Promptfoo YAML, DeepEval pytest, LLM-judge bias mitigations); see [`references/prompt-testing.md`](../llm-prompt-engineering/references/prompt-testing.md). This skill (agent-evals) owns the full eval harness and agent-level metric design; llm-prompt-engineering owns prompt-level test authoring

## Resources

### Primary References

- [Anthropic: Demystifying Evals for AI Agents](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents) -- comprehensive guide from zero to reliable evals
- [Anthropic: Building Effective Agents](https://www.anthropic.com/research/building-effective-agents) -- eval-driven development philosophy

### Framework Documentation

- [Inspect AI](https://inspect.aisi.org.uk/) -- UK AISI evaluation framework (used by Anthropic, DeepMind)
- [DeepEval](https://deepeval.com/docs/getting-started) -- pytest-native LLM evaluation
- [Promptfoo](https://www.promptfoo.dev/docs/intro/) -- agent eval with Claude/Codex SDK support

### Research

- [EDDOps: Evaluation-Driven Development](https://arxiv.org/html/2411.13768v3) -- process model for eval-driven LLM development
- [On Randomness in Agentic Evals](https://arxiv.org/pdf/2602.07150) -- statistical analysis of non-determinism
- [LangChain: Evaluating Deep Agents](https://blog.langchain.com/evaluating-deep-agents-our-learnings/) -- practical lessons from production
