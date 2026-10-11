# Evaluating Skills

How to test whether a skill produces good output: the open-standard `evals/evals.json` loop, and the case layout `claude plugin eval` runs. Reference material for the [Skill Creator](../SKILL.md) skill.

## Contents

- [Two Formats, Not Interchangeable](#two-formats-not-interchangeable)
- [The Open-Standard `evals/evals.json`](#the-open-standard-evalsevalsjson)
- [Plugin Eval Case Layout](#plugin-eval-case-layout)
- [Reading a Run](#reading-a-run)

## Two Formats, Not Interchangeable

| | Open standard | Plugin eval |
|---|---|---|
| Case file | `evals/evals.json` in the skill directory | one directory per case: `prompt.md` plus `graders/*.md` |
| Run by | an agent following the loop below (the `skill-creator` skill automates it) | the `claude plugin eval` command |
| Judged by | assertions graded with cited evidence | typed graders and a pass threshold |
| Fits | any skill, any agent that reads Agent Skills | a skill that ships in a plugin |

Neither tool reads the other's case files; the two formats are not interchangeable, so a skill that wants both keeps both. Both ask the same question — does the skill beat no skill, across varied prompts — and both answer it by running every case with and without the skill.

## The Open-Standard `evals/evals.json`

One file in the skill directory lists the cases:

```json
{
  "skill_name": "csv-analyzer",
  "evals": [
    {
      "id": 1,
      "prompt": "I have a CSV of monthly sales in data/sales_2025.csv. Find the top 3 months by revenue and chart them.",
      "expected_output": "A bar chart of the top 3 months by revenue, with labeled axes and values.",
      "files": ["evals/files/sales_2025.csv"],
      "assertions": ["The output includes a bar chart image file", "Both axes are labeled"]
    }
  ]
}
```

A skill name, then a list of evals; each has an `id`, a `prompt`, an `expected_output` (a human-readable description of success), optional input `files`, and `assertions`. Write the prompt as a user would type it, varying phrasing and detail, and include a boundary case.

**Keep evals few.** Start with two or three and expand after the first results: every eval costs two runs per iteration, and an eval that cannot say what it checks, or that the skill passes anyway, only adds noise. State why each one exists, so a later reader can tell which to drop. Add assertions after the first outputs, not before; you rarely know what good looks like until the skill has run.

**The loop**

1. Run each eval twice from a clean context: with the skill, and without it (or with a snapshot of the previous version, taken before editing). Save outputs, token count and duration per run.
2. Grade every assertion PASS or FAIL with cited evidence: quote or point at the output. Give no benefit of the doubt; a section titled "Summary" holding one vague sentence fails "includes a summary". Check mechanical assertions (valid JSON, row count) with a script, the rest with a model.
3. Aggregate per configuration into a benchmark and report the delta: with-skill minus without-skill pass rate, beside the extra time and tokens the skill costs. A 50-point gain for 13 seconds is worth it; a 2-point gain for double the tokens is not.
4. Read the pattern behind the numbers. Drop assertions that pass in both arms (they measure the model, not the skill); fix those that fail in both; study those that pass only with the skill; tighten instructions where results vary between runs.
5. Record human feedback per eval (`feedback.json`, empty when the output looked fine). "The chart is missing axis labels" is actionable; "looks bad" is not.
6. Hand failed assertions, feedback and run transcripts to a model with the current `SKILL.md`, apply the change and rerun in a new iteration. Stop when feedback is consistently empty or the delta stops improving.

When improving the skill, generalize from the failures rather than patching the one prompt, keep the instructions lean, and explain the reason behind each rule.

## Plugin Eval Case Layout
<!-- last-verified: 2026-10-11 -->

`claude plugin eval` loads a plugin and runs the suite under its `evals/` directory (override with `--eval-dir` or the manifest's `experimental.evals`):

```text
my-plugin/
├── .claude-plugin/plugin.json
├── skills/...
└── evals/
    ├── first-case/
    │   ├── prompt.md        # frontmatter: run limits and tools; body: the prompt
    │   ├── graders/
    │   │   ├── criteria.md  # frontmatter: type and options; body: the rubric
    │   │   └── skill-fired.md
    │   └── case.yaml        # optional: scaffold script, history, extra directories
    └── results/             # written by each run; gitignore it
```

A directory with a `prompt.md` or a `case.yaml` is a case, and a case with no grader fails to load. `claude plugin eval init` writes a suite by interview; `init --bare <name>` writes a blank case.

**Graders.** One file per check; the frontmatter names a `type`, an optional `weight` and an optional `arm`. Six types: `regex` (a pattern found in the last message, the trace or a produced file), `tool_used` (a tool called between `min` and `max` times, optionally matching an `input_match` pattern), `tool_order` (one call before another), `file_exists` (a file created during the run), `llm` (a judge votes on a rubric, two of three votes pass) and `baseline` (a judge compares against a reference transcript). The first four cost nothing; `llm` and `baseline` call a judge model (`--judge-model`). Prefer a `regex` over a produced file to an `llm` grader for long output, and give each case one grader on the result and one on the steps taken.

**Runs and arms.** Each case runs three runs by default (`--runs` overrides it); a run's score is the fraction of its graders that passed and the case's score is the mean across runs. When a plugin resolves, every case also runs in a no-plugin baseline arm, and the report shows `WITH`, `W/OUT` and `Δ`. `--ablation none` runs the with-arm only. The run is non-interactive, so a tool beyond the read-only set needs an `--allow-tools` grant, and the first run in a directory asks you to trust it (`--trust-plugin` answers it in CI).

**Threshold and exit status.** A case passes when its with-arm score meets `--threshold` (default `1.0`). Exit status 0 means every case met it and every case file loaded; 1 means a case fell below, a case failed to load or no case was found; 2 means a partial run (the `--max-cost-usd` ceiling hit, or the credential was rejected). The delta is reported but never changes the exit status. Pin `--model` and `--judge-model` in CI so a model rollout is not mistaken for a plugin regression.

**Results.** Each run writes `evals/results/<timestamp>/` with `aggregate-result.json` and a self-contained `report.html`; `--json [path]` prints the same document. When your account can publish, the report is also published as a private artifact; pass `--no-publish` to keep it local.

## Reading a Run

- **The plugin-fired indicator.** A `tool_used` grader on the `Skill` tool, and any grader marked `arm: with-only`, is excluded from the score in a two-arm run (it can never pass without the plugin) and shown as a pass/fail indicator only. A failing indicator means Claude never chose your skill: the next lever is its description.
- **A delta near zero.** With the indicator failing, the skill is not triggering on the prompt's phrasing; adjust the description and rerun. With the indicator passing and the delta still near zero or negative, suspect the judge before the skill: rerun with a larger `--judge-model` and tighten the rubric so formatting does not decide the verdict. A case that scores 1.0 in both arms shows the model needed no help.
- **No baseline column.** No plugin resolved for the case; set `plugins: ["../.."]` in its frontmatter.
- **Rate-limit runs score 0.** When the account hits a usage or rate limit mid-suite, each later run ends with that error and scores 0, yet the suite still finishes and is not marked partial. Check the notes column, or `cases[].arms.with[].error` in the JSON, before reading a drop as a regression, and rerun after the limit resets.
- **One run is noise.** Iterate on a case with `--case <name> --runs 1 --ablation none`, then confirm the change at the default three runs.
