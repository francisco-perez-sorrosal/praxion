# Agent Evals

Designing and implementing evaluations for AI agents. Covers eval types, framework selection, golden datasets, LLM-as-judge, grader design, scoring, non-determinism handling, and CI/CD integration. Python-focused with framework-agnostic patterns.

## When to Use

- Evaluating agent behavior (correctness, tool use, safety, efficiency)
- Choosing between eval frameworks (Inspect AI, DeepEval, Promptfoo)
- Designing eval suites and golden datasets
- Implementing trajectory evaluation for tool-using agents
- Setting up eval-driven development workflows
- Integrating evals into CI/CD pipelines
- Handling non-determinism in agent outputs

## Activation

Triggers on: agent evaluation, eval framework selection, golden dataset creation, LLM-as-judge design, agent testing methodology, eval-driven development, trajectory evaluation, agent grading.

## Skill Contents

| File | Purpose | Lines |
| --- | --- | --- |
| `SKILL.md` | Core eval guidance: types, framework selection, getting started, gotchas | ~250 |
| `references/framework-patterns.md` | Code examples for Inspect AI, DeepEval, Promptfoo; comparison matrix | ~410 |
| `references/eval-design-patterns.md` | Golden datasets, LLM-as-judge, grader design, scoring, non-determinism | ~370 |
| `references/cicd-integration.md` | GitHub Actions workflows, deployment gates, cost management | ~325 |

## Related Skills

- **[python-development](../python-development/)** -- pytest patterns and test organization for eval implementations
- **[agentic-sdks](../agentic-sdks/)** -- agent building patterns (the systems being evaluated)
- **[spec-driven-development](../spec-driven-development/)** -- behavioral specifications that inform eval design
- **[cicd](../cicd/)** -- CI/CD pipeline design for eval integration
