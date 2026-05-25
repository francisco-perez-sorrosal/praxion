---
description: File a well-formed bug report on an upstream open-source project
argument-hint: <owner/repo> [description or context]
allowed-tools: [Bash(gh:*), Bash(curl:*), Read, Grep, Glob, AskUserQuestion]
disable-model-invocation: true
---

File a bug report on an upstream open-source repository using the [upstream-stewardship](../skills/upstream-stewardship/SKILL.md) skill. Guides the user through deduplication, sanitization, template compliance, and filing — with a human approval gate before every filing.

## Process

### 1. Parse and Validate

Resolve `$ARGUMENTS` to an `owner/repo` target and optional bug description.

- If no arguments: ask the user for the target repository
- Verify `gh` CLI is authenticated: `gh auth status &>/dev/null`
- Verify the repository exists: `gh repo view {owner/repo} --json name &>/dev/null`
- On failure: report the error and stop

### 2. Reconnaissance

Gather intelligence about the upstream project's expectations:

```bash
# Community health profile
gh api repos/{owner}/{repo}/community/profile

# List issue templates
gh api repos/{owner}/{repo}/contents/.github/ISSUE_TEMPLATE --jq '.[].name' 2>/dev/null

# Fetch bug report template (if it exists)
gh api -H "Accept: application/vnd.github.raw" \
  repos/{owner}/{repo}/contents/.github/ISSUE_TEMPLATE/bug_report.yml 2>/dev/null
```

Note: the template filename varies — scan the template list and pick the one most relevant to bug reports.

Check for `CONTRIBUTING.md` and `SECURITY.md`. Report what you find to the user.

### 3. Deduplication

Search for existing issues that may cover the same bug. Follow the skill's Deduplication Strategy:

**Keyword search** (required):
```bash
gh search issues "<key terms>" --repo {owner/repo} --state open --json number,title,url --limit 15
```

Run 2-3 queries with different term combinations.

**Semantic search** (best-effort, when keyword results are insufficient):
```bash
gh api -X GET '/search/issues' \
  -f q='repo:{owner/repo} is:issue is:open <natural language description>' \
  -f search_type=hybrid \
  --jq '.items[:10] | .[] | {number, title, html_url}'
```

**Also check the local tracker** for previously filed issues:
```bash
grep -i "{owner/repo}" .ai-state/UPSTREAM_ISSUES.md 2>/dev/null
```

Present results to the user ranked by relevance. Ask:

> I found these potentially related issues. Would you like to:
> 1. **Comment on an existing issue** (specify which one)
> 2. **File a new issue** (none of these match)
> 3. **Abort** (this is already covered)

If the user chooses to comment or abort, follow their direction and stop.

### 4. Draft

Construct the issue body:

- **If a template was found** in step 2: parse the YAML form fields (see the skill's [issue-templates reference](../skills/upstream-stewardship/references/issue-templates.md)) and map the user's description to each required field
- **If no template exists**: use the built-in bug report structure from the issue-templates reference

Incorporate:
- The user's bug description and any context from the conversation
- A minimal reproducible example (MRE) if available
- Environment details (version, OS, platform)
- Evidence (error messages, logs, quantitative data)

### 5. Sanitize

Apply the sanitization pipeline from the skill:

1. Scan the draft for credential patterns (secret-patterns.md)
2. Scan for home directory paths, internal hostnames, internal project names, PII
3. Replace matches with safe placeholders
4. Show the user a summary of what was redacted
5. Present the sanitized draft for review

Ask the user to approve, edit, or request changes.

### 6. Security Gate

Assess whether the bug has security implications:

- Does it involve authentication, authorization, or access control?
- Could it lead to data exposure or privilege escalation?
- Does it affect cryptographic operations or secrets handling?

**If security-sensitive**: switch to the responsible disclosure path from the skill. Do not proceed with public filing. Check for SECURITY.md and GitHub private vulnerability reporting. Inform the user of the private channel options.

**If not security-sensitive**: proceed to filing.

### 7. File

Present the final draft (title + body + labels) to the user for confirmation:

> Here is the issue I will file on **{owner/repo}**:
>
> **Title**: {title}
> **Labels**: {labels}
>
> {body preview}
>
> Shall I file this issue?

On user confirmation:

```bash
gh issue create -R {owner/repo} \
  --title "{title}" \
  --body "{body}" \
  --label "{labels}"
```

Capture the returned issue URL and number.

### 8. Track

Append a record to `.ai-state/UPSTREAM_ISSUES.md`:

```markdown
| {date} | {owner/repo} | [#{number}]({url}) | {title} | open | {workaround if any} | steward |
```

Create the file with headers if it does not exist. Report the filed issue URL to the user.
