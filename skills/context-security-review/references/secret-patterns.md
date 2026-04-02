# Secret Pattern Catalog

Regex patterns for detecting common secret types in code and configuration. These patterns are used by `send_event.py` for runtime redaction and by this skill for static review.

Back-link: [Context Security Review Skill](../SKILL.md)

## Pattern Table

Each pattern is a compiled regex used to detect and redact secrets. The `[REDACTED]` replacement is applied to the entire match.

| # | Pattern | Detects | Example Match |
|---|---------|---------|---------------|
| 1 | `(?i)(api[_-]?key\|apikey)\s*[:=]\s*\S+` | API key assignments | `api_key=sk_live_abc123` |
| 2 | `(?i)(secret\|token\|password\|passwd\|pwd)\s*[:=]\s*\S+` | Secret/token/password assignments | `password: hunter2` |
| 3 | `(?i)bearer\s+\S+` | Bearer token headers | `Bearer eyJhbGciOiJ...` |
| 4 | `sk-[a-zA-Z0-9]{20,}` | OpenAI API keys | `sk-proj-abc123def456ghi789` |
| 5 | `sk-ant-[a-zA-Z0-9]{20,}` | Anthropic API keys | `sk-ant-api03-abc123def456...` |
| 6 | `ghp_[a-zA-Z0-9]{36}` | GitHub Personal Access Tokens | `ghp_ABCDEFghijklmnop1234567890abcdef` |
| 7 | `gho_[a-zA-Z0-9]{36}` | GitHub OAuth tokens | `gho_ABCDEFghijklmnop1234567890abcdef` |
| 8 | `github_pat_[a-zA-Z0-9]{22}_[a-zA-Z0-9]{59}` | GitHub Fine-grained PATs | `github_pat_11ABCDE...` |
| 9 | `xox[bpoas]-[a-zA-Z0-9\-]+` | Slack tokens (bot, user, app) | `xoxb-123456-789012-abcdef` |
| 10 | `AKIA[0-9A-Z]{16}` | AWS Access Key IDs | `AKIAIOSFODNN7EXAMPLE` |

## Known Prefixes

Quick reference for identifying secret types by their prefix:

| Prefix | Service | Token Type |
|--------|---------|------------|
| `sk-` | OpenAI | API key |
| `sk-ant-` | Anthropic | API key |
| `ghp_` | GitHub | Personal Access Token (classic) |
| `gho_` | GitHub | OAuth token |
| `github_pat_` | GitHub | Fine-grained Personal Access Token |
| `xoxb-` | Slack | Bot token |
| `xoxp-` | Slack | User token |
| `xoxa-` | Slack | App token |
| `xoxo-` | Slack | OAuth token |
| `xoxs-` | Slack | Session token |
| `AKIA` | AWS | Access Key ID |

## Redaction Rules

### Replacement

All matched patterns are replaced with the literal string `[REDACTED]`. The entire regex match is replaced, not just the secret portion.

### Order of Operations

In `send_event.py`, redaction is applied **after** truncation. This order is intentional:
1. `_truncate()` limits the text to 4096 bytes
2. `_redact_secrets()` scans the truncated text for patterns

This ensures truncation does not split a secret pattern mid-match, which would cause it to survive redaction. The truncated text is what gets transmitted, so redacting it is sufficient.

### Case Sensitivity

- Patterns 1-3 use `(?i)` for case-insensitive matching (e.g., `API_KEY`, `api_key`, `Api_Key` all match)
- Patterns 4-10 are case-sensitive because they match specific token prefixes with known casing

### Partial Matches

Patterns match greedily on `\S+` (non-whitespace). This means the entire key-value pair or token string is replaced, not just the secret portion. This is intentional to avoid leaking partial secrets.

## Adding New Patterns

When a new secret type needs detection:

1. **Identify the pattern**: Find the token format from the service's documentation (prefix, character set, length)
2. **Write a regex**: Match the minimum distinguishing prefix plus the secret body. Use `\S+` for variable-length secrets or `[a-zA-Z0-9]{N}` for fixed-length ones
3. **Test for false positives**: Run the regex against a sample of non-secret text to verify it does not match common identifiers, variable names, or prose
4. **Add to `SECRET_PATTERNS`**: Append the compiled regex to the list in `.claude-plugin/hooks/send_event.py`
5. **Update this catalog**: Add a row to the pattern table and known prefixes table above
6. **Consider ordering**: More specific patterns (like `sk-ant-`) should appear before more general ones (like `sk-`) to ensure the specific pattern matches first. Currently `sk-ant-` is listed after `sk-` but both will match independently since regex substitution runs sequentially

## Limitations

- **Not a comprehensive secret scanner**: This catalog covers the most common secret types. It is not a replacement for dedicated tools like `gitleaks`, `truffleHog`, or `detect-secrets`.
- **No entropy detection**: These patterns match known formats only. High-entropy strings that could be secrets but do not match a known format will not be detected.
- **No context awareness**: The patterns match anywhere in the text. A string like `password: [already-redacted]` would not be re-redacted, but `password: test123` in a test file would be flagged.
