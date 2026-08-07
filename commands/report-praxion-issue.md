---
description: File a Praxion-origin ecosystem-defect issue on the Praxion repo from a captured healing-sidecar candidate, with a human confirmation gate before every filing
argument-hint: "[fingerprint]"
allowed-tools: [Bash(gh:*), Bash(python3:*), Bash(uv run:*), Read, Grep, Glob, AskUserQuestion]
disable-model-invocation: true
---

File an `ecosystem-defect` issue on the Praxion repo for a *Praxion-origin* defect (root cause in a shipped `hooks`/`blocks`/`agents`/`scripts`/`skills` artifact) that a Praxion capture point already recorded in `.ai-state/praxion_feedback/PENDING.md`. This command is an instance of the [upstream-stewardship](../skills/upstream-stewardship/SKILL.md) skill's pipeline shape (dedup → draft → sanitize → security-gate → HITL file → track) with the target fixed to the Praxion repo. It never accepts a fresh bug description as input -- scope filtering and mechanical sanitization already happened at capture time; this command only renders, reviews, and files an *already-captured* candidate.

**This command never files autonomously.** Every filing requires an explicit human confirmation, riding the operator's own `gh` authentication -- no PAT, no GitHub App, no new secret in this project.

## Process

### 1. Validate

- Verify `gh` is authenticated: `gh auth status &>/dev/null`. On failure, report the error and stop.
- Resolve the target repo: `francisco-perez-sorrosal/praxion` (constant), overridable via the `PRAXION_UPSTREAM_REPO` environment variable (for forks).
- Resolve the candidate:
  - If `$ARGUMENTS` names a fingerprint (full or short), use it.
  - Otherwise, list pending candidates:
    ```bash
    python3 scripts/report_praxion_issue.py list
    ```
    (PATH-installed by `install_claude.sh` as `report_praxion_issue.py`; in the Praxion self-host checkout use `python3 scripts/report_praxion_issue.py`.) If there are none, report "No pending candidates in `.ai-state/praxion_feedback/PENDING.md`" and stop. If there is exactly one, use it. If there are several, present them and ask the user which fingerprint to file via `AskUserQuestion`.
- Read the candidate's `category` field (from the `list` output's `[category]` bracket, or by reading its `### <fingerprint>` block in `.ai-state/praxion_feedback/PENDING.md`) -- it is needed for the label in step 6.

### 2. Dedup

Search for existing issues covering the same defect **before** drafting -- a duplicate filing is worse than a missed one.

**Fingerprint + keyword search** (required):
```bash
gh search issues "<fingerprint-short> OR <key terms from the candidate's artifact/error>" \
  --repo francisco-perez-sorrosal/praxion --state open --json number,title,url --limit 15
```

**Local trackers** (required):
```bash
grep -i "<fingerprint>" .ai-state/UPSTREAM_ISSUES.md .ai-state/praxion_feedback/PENDING.md 2>/dev/null
```

Apply the skill's Deduplication Strategy decision tree (strong / partial / weak / no match). Present results and ask:

> I found these potentially related issues. Would you like to:
> 1. **Comment on an existing issue** (specify which one)
> 2. **File a new issue** (none of these match)
> 3. **Abort** (this is already covered)

On comment or abort, follow the user's direction and stop.

### 3. Draft

Render the candidate's fixed §5.2 markdown body:

```bash
python3 scripts/report_praxion_issue.py render --fingerprint <fingerprint> --body-file <tmp-file>
```

Derive a title from the candidate's category and artifact path (e.g. `[ecosystem-defect] <category>: <artifact-path> -- <short summary>`).

### 4. Sanitize (judgment pass)

The rendered body is already **mechanically** sanitized -- the candidate was sanitized at capture time, before it ever reached the git-committed `PENDING.md`. Apply the skill's *judgment*-level categories on top (proprietary content, internal names the mechanical pass would not recognize). Present a redaction summary and ask the user to approve, edit, or request changes.

### 5. Security Gate

Preserved verbatim from the upstream-stewardship skill's responsible-disclosure path -- this step is unconditional and always runs before filing:

- Does the defect involve authentication, authorization, or access control?
- Could it lead to data exposure or privilege escalation?
- Does it affect cryptographic operations or secrets handling?

**If security-sensitive**: stop. Do not file a public issue. Check the Praxion repo for a security policy and GitHub private vulnerability reporting, and inform the user of the private disclosure channel. Do not proceed to step 6.

**If not security-sensitive**: proceed to filing.

### 6. HITL File

Present the final draft for confirmation:

> Here is the issue I will file on **francisco-perez-sorrosal/praxion**:
>
> **Title**: {title}
> **Labels**: `bug`, `auto-filed`, `category:<slug>`, `from-managed-project`
>
> {body preview}
>
> Shall I file this issue?

The label set is always exactly these four -- **never** `ecosystem-feedback`. That label is the maintainer's own arming gate for the fix-triage subsystem on the Praxion side and must remain exclusively human-applied there; this reporter is structurally incapable of emitting it.

File **only** after the user's explicit confirmation:

```bash
gh issue create -R francisco-perez-sorrosal/praxion \
  --title "{title}" \
  --body-file <tmp-file> \
  --label "bug,auto-filed,category:<slug>,from-managed-project"
```

Capture the returned issue URL and number.

### 7. Track

```bash
python3 scripts/report_praxion_issue.py mark-filed --fingerprint <fingerprint> --issue-url <url>
```

Append a record to `.ai-state/UPSTREAM_ISSUES.md` (create with headers if it does not exist):

```markdown
| {date} | francisco-perez-sorrosal/praxion | [#{number}]({url}) | {title} | open |  | sidecar |
```

Report the filed issue URL to the user.
