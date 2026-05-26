# Code Review Skill

Structured code review methodology with finding classification, language adaptation, and report templates.

## When to Use

- Reviewing code for convention compliance
- Post-implementation verification (via the verifier agent)
- Reviewing pull requests
- Ad-hoc code quality assessments
- Any context where structured findings with severity classification are needed

## Activation

The skill activates automatically when the agent detects code review tasks: reviewing code quality, checking conventions, assessing test coverage, or producing review reports.

Trigger explicitly by mentioning "code-review skill" or referencing it by name.

## Skill Contents

| File | Purpose |
|------|---------|
| `SKILL.md` | Core reference: review workflow, finding classification, language adaptation, report modes |
| `references/report-template.md` | Canonical VERIFICATION_REPORT.md template (pipeline and standalone modes) |
| `README.md` | This file -- overview and usage guide |

## Related Skills

- [`coding-style` rule](../../rules/swe/coding-style.md) -- Convention definitions (WHAT to check)
- [`refactoring` skill](../refactoring/) -- Structural improvement patterns (complementary, not overlapping)
- [`verifier` agent](../../agents/verifier.md) -- Pipeline agent that loads this skill for post-implementation review
