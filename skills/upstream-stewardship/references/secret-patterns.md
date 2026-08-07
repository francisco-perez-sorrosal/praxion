# Secret Patterns for Bug Reports

Patterns for identifying and sanitizing secrets and sensitive information in upstream bug reports. Back to [SKILL.md](../SKILL.md).

This file complements the `context-security-review` skill's [secret-patterns.md](../../context-security-review/references/secret-patterns.md), which provides the canonical regex catalog for credential detection. This reference focuses on the upstream reporting context: what to look for, how to sanitize it, and how to maintain reproducibility.

## Sanitization Hierarchy

Apply these checks in order. Each category can appear in error messages, stack traces, log output, configuration snippets, or environment descriptions.

### 1. Credentials and Tokens

These must be redacted before any draft is shown to the user or filed publicly.

| Pattern | Appears In | Sanitized Form |
|---------|-----------|----------------|
| API keys (`sk-`, `sk-ant-`, `AKIA`) | Environment variables, config files | `[REDACTED_API_KEY]` |
| Bearer tokens | HTTP headers in logs | `Bearer [REDACTED]` |
| Database connection strings with passwords | Error messages, config | `postgresql://user:[REDACTED]@host:5432/db` |
| OAuth tokens (`gho_`, `ghp_`, `github_pat_`) | Git config, API calls | `[REDACTED_TOKEN]` |
| SSH private keys | Stack traces, config dumps | `[REDACTED_SSH_KEY]` |
| JWT tokens (`eyJ...`) | HTTP headers, log output | `[REDACTED_JWT]` |
| Webhook secrets | Configuration files | `[REDACTED_WEBHOOK_SECRET]` |

**Detection strategy**: Use the regex patterns from the [context-security-review catalog](../../context-security-review/references/secret-patterns.md#pattern-table). Apply them against the entire draft body, including code blocks and collapsible sections.

### 2. Infrastructure Details

Internal infrastructure details can reveal attack surface or organizational structure.

| Pattern | Example | Sanitized Form |
|---------|---------|----------------|
| Internal hostnames | `api.staging.internal.corp` | `<internal-host>` |
| Internal IP addresses | `10.0.3.42`, `192.168.1.100` | `<internal-ip>` |
| Internal URLs | `https://jira.company.com/PROJ-123` | `[internal tracker]` |
| Cloud account IDs | `arn:aws:iam::123456789012:...` | `arn:aws:iam::<ACCOUNT_ID>:...` |
| Container/pod names | `myapp-deployment-7d9f8b-abc12` | `<container-name>` |
| Internal DNS zones | `*.internal.company.io` | `*.<internal-domain>` |

### 3. User and System Paths

Paths reveal usernames, organizational structure, and system configuration.

| Pattern | Example | Sanitized Form |
|---------|---------|----------------|
| macOS home directories | `/Users/jsmith/dev/project/` | `<project-root>/` |
| Linux home directories | `/home/jsmith/.config/` | `~/.config/` |
| Windows user directories | `C:\Users\JSmith\` | `<home>\` |
| Workspace-specific paths | `/opt/company/apps/myapp/` | `<project-root>/` |
| Virtual environment paths | `/Users/jsmith/.venvs/myapp/` | `<venv>/` |
| Package manager caches | `/Users/jsmith/.cache/pip/` | `<cache>/pip/` |

### 4. Personal Identifiable Information (PII)

| Pattern | Example | Sanitized Form |
|---------|---------|----------------|
| Email addresses | `john.smith@company.com` | `user@example.com` |
| Full names in paths/logs | `John Smith` | `<user>` |
| Phone numbers | `+1-555-123-4567` | `<phone>` |
| IP addresses (external) | `203.0.113.42` | `<external-ip>` |
| Session IDs/cookies | `session=abc123def456` | `session=[REDACTED]` |

### 5. Internal State and Configuration

Praxion-specific patterns that should not appear in upstream issues.

| Pattern | Example | Sanitized Form |
|---------|---------|----------------|
| `.ai-state/` content | Observations, ADRs, ledgers | `[internal state redacted]` |
| `.ai-work/` content | Pipeline intermediates | `[internal workflow redacted]` |
| Agent prompts | System prompt excerpts | `[agent prompt redacted]` |
| Plugin cache paths | `~/.claude/plugins/cache/...` | `<plugin-cache>/...` |

Praxion carries no curated cross-session memory store — the in-house memory subsystem (`memory-mcp`, `.ai-state/memory.json`, `remember()`/`recall()`) has been removed, so no memory-tool payload can appear in a draft. Internal state now surfaces through `.ai-state/` artifacts, covered by the first row above.

## Sanitization Workflow

### Step 1: Automated Scan

Apply regex patterns against the entire draft. Flag all matches for review.

```python
# Conceptual pattern application order
patterns = [
    credential_patterns,       # From context-security-review
    infrastructure_patterns,   # Internal hosts, IPs, URLs
    path_patterns,             # Home dirs, project paths
    pii_patterns,              # Emails, names, phones
    internal_state_patterns,   # .ai-state, .ai-work content
]

for pattern_group in patterns:
    for pattern in pattern_group:
        draft = pattern.sub(replacement, draft)
```

### Step 2: Contextual Review

Some patterns have legitimate uses in bug reports:

| Pattern | Legitimate When | Redact When |
|---------|----------------|-------------|
| File paths | Using `<project-root>/src/module.py` | Full path reveals username |
| IP addresses | Reporting a network-related bug | IP is internal or personal |
| Version numbers | Bug is version-specific | Version reveals internal build system |
| Error messages | Core of the bug report | Message contains credentials or PII |

### Step 3: Reproducibility Validation

After sanitization, verify the report still makes sense:

1. **Read the sanitized version** as if you are the upstream maintainer
2. **Check the MRE** -- can it be followed without the redacted information?
3. **Verify error messages** -- are the relevant parts preserved?
4. **Test if possible** -- run the sanitized MRE to confirm it reproduces

### Step 4: User Review Gate

Present the sanitized draft to the user with a diff showing what was changed:

```
[SANITIZATION REPORT]
- 3 credential patterns redacted
- 2 home directory paths generalized
- 1 internal hostname replaced

Review the draft below. The original values have been replaced with
placeholders. Verify no sensitive information remains before filing.
```

## Common Hiding Places

Secrets and sensitive data often appear in unexpected locations within bug reports:

| Location | What to Check |
|----------|--------------|
| **Stack traces** | File paths, connection strings in error messages |
| **Environment dumps** | `env` output, `process.env` logs |
| **Configuration examples** | `.env` file contents, `config.yaml` snippets |
| **HTTP request/response logs** | Authorization headers, cookies, query parameters |
| **Docker/Compose snippets** | `environment:` sections, volume mount paths |
| **Git output** | Remote URLs with tokens, author emails |
| **Error screenshots** | Terminal prompts showing username, paths in title bar |
| **Collapsible sections** | Often used for "full output" -- easy to miss during review |

## Edge Cases

### Connection Strings

Database connection strings often contain embedded credentials:

```
# Before sanitization
postgresql://admin:s3cr3t_p4ss@db.internal.corp:5432/production

# After sanitization
postgresql://user:[REDACTED]@<internal-host>:5432/<database>
```

Preserve the **driver**, **port**, and **general structure** -- these are relevant to the bug. Redact the **username**, **password**, **hostname**, and **database name**.

### Stack Traces with Paths

Preserve the **file name** and **line number** (essential for debugging). Remove the **directory prefix** that reveals system structure:

```
# Before
/Users/jsmith/dev/company/myapp/src/handlers/auth.py:42 in verify_token

# After
<project-root>/src/handlers/auth.py:42 in verify_token
```

### Multi-Line Secrets

Some secrets span multiple lines (PEM certificates, JSON credentials files):

```
# Before
-----BEGIN RSA PRIVATE KEY-----
MIIEowIBAAKCAQEA... (multiple lines)
-----END RSA PRIVATE KEY-----

# After
[REDACTED_PRIVATE_KEY]
```

Detect multi-line secrets by their delimiters (`BEGIN`/`END` blocks, JSON objects with known credential fields like `"private_key"`).
