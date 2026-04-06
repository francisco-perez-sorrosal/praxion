---
description: Save current working changes to project memory with secret filtering
argument-hint: [description]
allowed-tools: [Bash(git:*), Read, Grep, Glob, mcp__memory__remember, mcp__memory__search, AskUserQuestion]
---

Capture the current uncommitted changes (staged + unstaged + untracked) and persist a sanitized snapshot to the project's memory system. Useful for preserving work-in-progress context across sessions.

## Process

### 1. Gather Changes

Run these in parallel:

- `git status` — overview of modified, staged, and untracked files
- `git diff` — unstaged changes
- `git diff --staged` — staged changes
- `git log -1 --format="%H %s"` — current HEAD for context

For untracked files that are not in `.gitignore`, read their contents (up to 200 lines each, skip binaries).

### 2. Filter Sensitive Files

**Exclude entirely** — never include content from these files in memory:

| Pattern | Reason |
|---------|--------|
| `.env`, `.env.*` | Environment secrets |
| `credentials.json`, `*credentials*` | Credential stores |
| `*.pem`, `*.key`, `*.p12`, `*.pfx` | Private keys and certificates |
| `*secret*`, `*token*` (in filenames) | Likely secret stores |
| `id_rsa`, `id_ed25519`, `*.pub` (SSH keys) | SSH credentials |
| `.netrc`, `.npmrc` (with auth) | Auth tokens |
| `*.sqlite`, `*.db` | Database files (binary + possible PII) |
| `.ai-state/memory.json` | Internal memory state |
| `.ai-state/observations.jsonl` | Internal observations |

If any excluded files appear in the changeset, report them to the user: "Skipped N file(s) matching sensitive patterns: [list]. These are never saved to memory."

### 3. Redact Secrets from Diff Content

Apply these regex patterns to all diff content before saving. Replace the entire match with `[REDACTED]`:

1. `(?i)(api[_-]?key|apikey)\s*[:=]\s*\S+` — API key assignments
2. `(?i)(secret|token|password|passwd|pwd)\s*[:=]\s*\S+` — Secret/token/password assignments
3. `(?i)bearer\s+\S+` — Bearer token headers
4. `sk-[a-zA-Z0-9]{20,}` — OpenAI API keys
5. `sk-ant-[a-zA-Z0-9]{20,}` — Anthropic API keys
6. `ghp_[a-zA-Z0-9]{36}` — GitHub PATs
7. `gho_[a-zA-Z0-9]{36}` — GitHub OAuth tokens
8. `github_pat_[a-zA-Z0-9]{22}_[a-zA-Z0-9]{59}` — GitHub fine-grained PATs
9. `xox[bpoas]-[a-zA-Z0-9\-]+` — Slack tokens
10. `AKIA[0-9A-Z]{16}` — AWS Access Key IDs

Also sanitize:

- Home directory paths (`/Users/<username>/`, `/home/<username>/`) — replace with `~/`
- Private IPv4 addresses (`10.x.x.x`, `172.16-31.x.x`, `192.168.x.x`) — replace with `<internal-ip>`

If any redactions were made, inform the user: "Redacted N secret pattern(s) from the saved content."

### 4. Build the Memory Entry

Construct a structured summary:

```
## Saved Changes — <branch> @ <short-sha>

**When**: <ISO 8601 timestamp>
**Branch**: <current branch>
**HEAD**: <short sha> — <commit subject>
**Description**: <$ARGUMENTS or auto-generated summary>

### Files Changed
- <file path> (modified|added|deleted|renamed) — <one-line summary of change>

### Diff Summary
<condensed diff — focus on what changed semantically, not raw patch lines>
<for large diffs (>200 lines total), summarize by file instead of including full diff>

### Skipped (sensitive)
<list of excluded files, if any>
```

### 5. Check for Existing Snapshots

Search memory for existing entries with tag `saved-changes` on the same branch:

- If found, ask the user: "A previous snapshot exists for branch `<branch>`. Overwrite it, or save alongside it?"
- If the user says overwrite, use the same key; otherwise generate a new timestamped key

### 6. Save to Memory

Call `remember()` with:

- **category**: `project`
- **key**: `saved-changes-<branch>` (or `saved-changes-<branch>-<timestamp>` if not overwriting)
- **value**: the structured summary from step 4
- **tags**: `["saved-changes", "wip", "<branch-name>"]`
- **importance**: 5
- **summary**: `WIP snapshot: <description or file count> on <branch>`
- **type**: `insight`

### 7. Confirm

Report to the user:

- Number of files captured
- Number of files skipped (sensitive)
- Number of redactions applied
- Memory key used
- Reminder: "Use `/cajalogic search saved-changes` to find saved snapshots later"
