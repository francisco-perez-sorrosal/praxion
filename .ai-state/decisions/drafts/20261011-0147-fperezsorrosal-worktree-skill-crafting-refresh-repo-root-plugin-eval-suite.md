---
id: dec-draft-246278b3
title: Praxion's plugin trigger evals live in the repository-root evals/ directory
status: proposed
category: architectural
date: 2026-10-11
summary: "A plugin eval suite is added at evals/ (the claude plugin eval default directory), outside every shipped skill directory, grouped under evals/skill-triggering/ with one directory per case (prompt.md plus graders/*.md); evals/results/ is gitignored and pipeline runs write their results under .ai-work/."
tags: [evals, plugin-eval, skill-triggering, verification, eval-framework]
made_by: agent
agent_type: systems-architect
branch: worktree-skill-crafting-refresh
pipeline_tier: standard
affected_files:
  - evals/skill-triggering/
  - .gitignore
affected_reqs: [REQ-25]
supersedes:
superseded_by:
re_affirms:
re_affirmed_by:
dissent: "evals/ sits one letter from Praxion's own eval/ framework package; a non-default directory under eval/ would group all evaluation in one tree at the cost of a flag on every run."
---

## Context

The skill-crafting refresh teaches an eval-first loop and must demonstrate it with `claude plugin eval` trigger probes on Praxion's own skills. The runner reads cases from a plain relative directory below the plugin root (default `evals/`, else `--eval-dir` or the manifest's `experimental.evals`; absolute paths and `..` are refused), writes results under that directory by default, and publishes the HTML report to claude.ai by default when the account supports it. Praxion's plugin root is the repository root, which already holds `eval/`, a Python LLM-as-judge framework with its own package and CI job. Cases must not sit inside any shipped skill directory.

## Decision

Add `evals/` at the repository root as Praxion's plugin eval suite, with trigger probes grouped under `evals/skill-triggering/<case>/` (`prompt.md` plus `graders/*.md`). A should-trigger case pairs a `tool_used` grader on `Skill` (the runner's plugin-fired indicator) with at least one scored free grader; a must-not-invoke case uses `min: 0`, `max: 0`, `arm: both`. `evals/results/` is gitignored; pipeline runs pass `--no-publish` and write `--output-dir`, `--json` and `--report` under `.ai-work/<task-slug>/`. The manifest is not changed. The responsibility for plugin-behavior evaluation joins the existing eval tooling as a separate directory, not inside the `eval/` package.

## Considered Options

### Repository-root `evals/` (chosen)

The runner finds it with no `--eval-dir` flag, from an installed plugin or from a directory holding the plugin's tracked files (a full checkout with dependency trees, such as this repository's root, holds more than the 20,000 entries the runner will scan and is refused; a live run therefore targets a trimmed copy of the tracked files), and it is the layout the official docs and `claude plugin eval init` produce. Costs a name close to `eval/`.

### `eval/plugin-cases/` with `--eval-dir`

Groups all evaluation under one tree. Every run needs the flag (or a manifest `experimental.evals` entry), and Markdown case files land inside a Python package with its own pyproject and CI matrix.

### `.ai-work/<task-slug>/evals/`

Keeps the plugin clone clean, but the cases are deleted at pipeline cleanup and cannot be re-run when a description changes, which is the point of trigger probes.

## Consequences

**Positive:** a durable home for trigger probes that future skill description changes can re-run; no `--eval-dir` flag needed once the runner can scan the plugin directory; results and reports kept out of the tree and private.

**Negative:** the suite ships in the plugin clone (never injected into a context window, so shipped-artifact isolation does not apply); the `eval/` versus `evals/` distinction must be named in the developer docs. The runner refuses a plugin directory over 20,000 entries and scores every run 0 with a zero exit, so running the suite from this repository's root needs a trimmed copy of the tracked plugin files; the authoring skill's evaluating page names the trap.

## Disconfirmation

- **Falsifier:** a run against the plugin's tracked files (or an installed plugin) does not find the cases, or writes results into the tracked tree, or the runner's default directory changes so that `evals/` needs a flag after all.
- **Steelmanned runner-up:** `eval/plugin-cases/` with the manifest's `experimental.evals` set, which keeps one evaluation tree and still runs without a flag; its cost is a manifest edit under an `experimental` key.
- **Reversal trigger:** the `experimental.evals` manifest key stabilizes, or a second eval tool claims `evals/`; then move the suite under `eval/` and record the directory in the manifest.
