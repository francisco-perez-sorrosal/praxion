---
description: Code review a pull request
argument-hint: [PR-number|branch|diff-target]
allowed-tools: [Bash, Read, Grep, Glob]
---

Review a pull request using the [code-review](../skills/code-review/SKILL.md) skill in **standalone mode**. Produces a structured report with finding classification (PASS/FAIL/WARN), convention compliance, and test coverage assessment.

## Process

1. **Resolve the review target** from `$ARGUMENTS`:

   - **PR number** (e.g., `123`): Fetch PR metadata and diff with `gh pr view` and `gh pr diff`
   - **Branch name** (e.g., `feat/auth`): Diff against the repo's default branch (`main` or `master`)
   - **No argument**: Use the current branch, diff against the default branch. If on the default branch, report that and ask for a target.

2. **Gather context**:

   - List changed files from the diff
   - Identify primary language(s) from file extensions
   - If a PR number was given, read the PR title, body, and linked issues for intent context
   - Check for existing review comments with `gh pr view --json reviews`

3. **Review changed files** by applying the code-review skill workflow:

   - **Scope**: Only changed lines and their immediate context — not entire files
   - **Convention check**: Apply coding-style rule sections to changed code
   - **Language adaptation**: Use language-specific idioms from the code-review skill's adaptation table
   - **Test coverage**: Check whether tests exist for critical paths introduced or modified in the diff. Note untested edge cases.

4. **Produce the report** using the standalone template from the code-review skill's [report template](../skills/code-review/references/report-template.md):

   - Verdict (PASS / PASS WITH FINDINGS / FAIL)
   - Convention Compliance table with file:line locations
   - Test Coverage Assessment
   - Recommendations (prioritized by severity)
   - Scope (files reviewed, commit range, timestamp)

5. **Output the report** directly in the conversation. For large PRs (20+ files), summarize findings by severity and list only FAIL and WARN items.
