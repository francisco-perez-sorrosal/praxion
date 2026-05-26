# Sanitization Patterns

Extended pattern catalog for detecting internal information in upstream issue drafts. Credential patterns are maintained in the `context-security-review` skill's `secret-patterns.md` reference — this file covers upstream-specific categories. Back to [SKILL.md](../SKILL.md).

Back-link: [Upstream Stewardship Skill](../SKILL.md)

## Pattern Table

These patterns detect internal information that should be sanitized before filing a public upstream issue. Apply all categories; present the sanitized diff to the user for review.

### Home Directory Paths

| Pattern | Detects | Replacement |
|---------|---------|-------------|
| `/Users/[^/\s]+/` | macOS home directories | `~/` or `<home>/` |
| `/home/[^/\s]+/` | Linux home directories | `~/` or `<home>/` |
| `C:\\Users\\[^\\]+\\` | Windows user directories | `<home>\\` |

After replacing the home prefix, further sanitize project-specific paths:

| Pattern | Detects | Replacement |
|---------|---------|-------------|
| Known project root (e.g., `~/dev/praxion/`) | Internal project paths | `<project-root>/` |
| `.ai-state/memory.json` content | Memory system excerpts | `[internal state redacted]` |
| `.ai-state/observations.jsonl` content | Observation log excerpts | `[internal observations redacted]` |

### Internal Hostnames and IPs

| Pattern | Detects | Replacement |
|---------|---------|-------------|
| `(?i)[a-z0-9-]+\.(internal\|corp\|local\|private)\.[a-z]+` | Internal domain names | `<internal-host>` |
| `10\.\d{1,3}\.\d{1,3}\.\d{1,3}` | Private IPv4 (10.x.x.x) | `<internal-ip>` |
| `172\.(1[6-9]\|2[0-9]\|3[01])\.\d{1,3}\.\d{1,3}` | Private IPv4 (172.16-31.x.x) | `<internal-ip>` |
| `192\.168\.\d{1,3}\.\d{1,3}` | Private IPv4 (192.168.x.x) | `<internal-ip>` |

### Internal Identifiers

| Pattern | Detects | Replacement |
|---------|---------|-------------|
| Internal project codenames | Proprietary names | Generic description or `[internal project]` |
| Internal tool names | Non-public tooling | `[internal tool]` |
| Team names or org chart references | Organizational structure | `[team]` or omit |

These patterns require contextual judgment — they cannot be fully automated with regex. The user review gate handles edge cases.

### PII

| Pattern | Detects | Replacement |
|---------|---------|-------------|
| Email addresses not in commit metadata | Personal email in logs | `user@example.com` |
| Usernames in log output | System usernames | `<username>` |
| Full names in error messages | Personal names | `<user>` |

## Credential Patterns

For API keys, tokens, passwords, and cloud provider secrets, apply the 10 regex patterns defined in the `context-security-review` skill's [secret-patterns.md](../../context-security-review/references/secret-patterns.md). Those patterns cover: API key assignments, secret/token/password assignments, Bearer tokens, OpenAI keys, Anthropic keys, GitHub PATs, Slack tokens, and AWS access keys.

The replacement for all credential matches is `[REDACTED]`.

## Application Order

1. **Credentials first** — apply secret-patterns.md regexes (highest security impact)
2. **Paths second** — replace home directories, then project-specific paths
3. **Hostnames and IPs** — replace internal network identifiers
4. **PII** — replace personal information
5. **Internal identifiers** — contextual replacements (may need user input)

## Presenting the Sanitization Diff

After applying all patterns, show the user what was changed:

- Display the sanitized draft with redacted sections highlighted
- List each replacement made with the category and original context (without showing the full original value for credentials)
- Ask the user to review and approve or edit before proceeding

When in doubt, redact more. The user can add back context during review. It is easier to add information than to retract leaked details from a public issue.
