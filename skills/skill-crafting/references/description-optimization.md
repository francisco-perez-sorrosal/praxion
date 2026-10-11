# Description Optimization

How to write a skill description that triggers, and how to measure and tune it instead of guessing. Reference material for the [Skill Creator](../SKILL.md) skill.

## Contents

- [Who Reads the Description](#who-reads-the-description)
- [Writing a Description That Triggers](#writing-a-description-that-triggers)
- [The Measured Tuning Loop](#the-measured-tuning-loop)
- [Trigger Cases for Plugin Eval](#trigger-cases-for-plugin-eval)

## Who Reads the Description

The model reads the description, and only the description, when it decides whether to load a skill; the body is read after that decision. Which invocation modes put the description in the always-loaded listing, and the listing's character cap, are on the [entry page](../SKILL.md). The description carries the whole burden of triggering, so tune it against evidence.

## Writing a Description That Triggers

- **Say when, in the user's terms.** Describe the intent behind a request ("the user wants to turn a data file into a chart"), not the skill's internal mechanics. The model matches against what the user asked for.
- **Open the trigger half with "Use when" or `Triggers:`.** Plain Agent Skills hosts read "Use this skill when..."; Praxion skills put the capability first and then a `Triggers:` list of the situations that should load it. Either way the description is an instruction to act, not a summary.
- **Be assertive.** List the contexts that apply, including the ones where the user never names the domain ("even if they don't mention CSV"). Undertriggering is the common failure.
- **Mark the boundary.** One clause on what the skill does not cover keeps a near-miss request from loading it.
- **Keep it short and front-loaded.** A few sentences. The listing truncates at the cap on the entry page, so put the key use case first; descriptions grow during tuning, so recheck the length after every revision.

A skill is consulted for work that needs knowledge or capability beyond what the model has unaided. A one-step request the model handles with basic tools may not trigger even a perfect description; test with tasks the skill helps with.

## The Measured Tuning Loop

Wording that reads well is not evidence. Measure the trigger rate on a fixed query set, then change the description on the part you tune against and judge it on the part you do not.

**The query set.** Write about twenty realistic queries, each labelled should-trigger or should-not-trigger. Roughly half are should-trigger, varied in phrasing (formal, casual, typos), explicitness (names the domain, or only describes the need), detail and number of steps. The other half are near-miss queries: they share keywords or concepts with the skill but need something else. "Write a fibonacci function" tests nothing; a request that shares the skill's vocabulary and wants a neighbouring skill tests the boundary. Put in what real prompts carry: file paths, a manager's request, column names.

**One measurement.** Run each query three times with the skill installed and record whether it was invoked. The trigger rate is the fraction of those three runs that invoked it. A should-trigger query passes at a rate above the threshold of 0.5; a should-not-trigger query passes below it. The pass rate over a set is the fraction of its queries that pass.

**The split.** Shuffle once and fix the split: 60 percent of the queries for tuning, 40 percent held out, each part with the same mix of should-trigger and near-miss queries. Keep the split fixed across iterations, and never let held-out results inform a revision.

**The loop.** At most five iterations:

1. Measure the current description on both parts.
2. Read the failures on the tuning part: should-trigger queries that did not fire, near-misses that did.
3. Revise. Broaden the scope or add the context of use when the first kind fails; add what the skill does not do when the second does. Generalize from the failures: find the category the failing queries share and describe that, rather than adding the failing query's keywords, which only fits the description to the set. When refinement stalls, try a structurally different framing.
4. Stop when the tuning part passes or improvement stops.

Choose the winning description by its pass rate on the held-out part. The best description is often not the last one; a later iteration may have fit the tuning queries and lost the held-out ones. If five iterations do not move the held-out rate, suspect the queries (too easy, too hard, mislabelled) before the description. Then write five to ten fresh queries that never entered the loop and run them once as a final check.

## Trigger Cases for Plugin Eval
<!-- last-verified: 2026-10-11 -->

A plugin-shipped skill can keep its trigger queries as `claude plugin eval` cases (layout and run options: [Evaluating Skills](evaluating-skills.md#plugin-eval-case-layout)). Each query becomes a case directory under `evals/`: a `prompt.md` holding the query as a user would type it, and a grader file for the verdict. The grader checks the transcript for a call to the `Skill` tool, so it costs no judge model.

**A should-trigger case.** `evals/triggers-new-skill/prompt.md`:

```markdown
---
max_turns: 10
allowed_tools: [Read, Glob, Grep, Skill]
---

I want to teach the agent our release checklist so it follows it every time. Can you set that up?
```

`evals/triggers-new-skill/graders/skill-fired.md`:

```markdown
---
type: tool_used
tool: Skill
input_match: '"skill"\s*:\s*"(?:[\w-]+:)?skill-crafting"'
---
```

It passes when the model invoked `skill-crafting`, by its plain or namespaced name, at least once. In a two-arm run (the plugin and a no-plugin baseline) a `tool_used` grader on `Skill` can never pass without the plugin, so it is excluded from the score and shown as a plugin-fired indicator only. A failing indicator is the finding: the model never chose the skill on that phrasing, and the description is the lever.

**A must-not-trigger case** is a near-miss query with a zero ceiling on the call count. `evals/near-miss-edit-skill-prose/prompt.md`:

```markdown
---
max_turns: 10
allowed_tools: [Read, Glob, Grep, Skill]
---

Fix the typo in the second paragraph of docs/release-notes.md.
```

`evals/near-miss-edit-skill-prose/graders/skill-not-fired.md`:

```markdown
---
type: tool_used
tool: Skill
input_match: '"skill"\s*:\s*"(?:[\w-]+:)?skill-crafting"'
min: 0
max: 0
arm: both
---
```

`min: 0` and `max: 0` assert the skill was never called. `arm: both` scores the grader in both arms; without it, a grader on `Skill` is only an indicator and a false trigger would go unnoticed. Grant `Skill` in `allowed_tools` for every trigger case, or a skill that could not fire proves nothing.

A case runs three runs by default and scores the fraction of its graders that passed. At the default `--threshold` of `1.0` a should-trigger case that fired in two of three runs still reports a failing indicator; read the per-run results and apply the 0.5 trigger-rate rule above, not the suite's exit status. Iterate on one case with `--case <name> --runs 1 --ablation none`, then confirm at the default.
