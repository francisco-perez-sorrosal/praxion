# Context Security Review

Security review methodology for Claude Code plugin ecosystems. Covers context artifact injection, hook compromise, dependency supply chain, script injection, secrets exposure, and GitHub Actions security — with two operating modes (diff and full-scan) and a PASS/FAIL/WARN classification system.

## When to Use

- Reviewing a PR that modifies CLAUDE.md, agent definitions, skills, rules, commands, or hooks
- Conducting a security audit of a Claude Code plugin
- Verifying agent permission baselines haven't been escalated
- Checking for secrets or sensitive data in committed files
- Assessing GitHub Actions workflow security
- Running a comprehensive posture scan via `/full-security-scan`

## Activation

Activates automatically when the task context matches security review patterns: reviewing PRs for security, auditing context artifacts, verifying hook scripts, checking for secrets, or assessing plugin security. Reference explicitly with "context-security-review skill."

## Skill Contents

| File | Purpose |
|------|---------|
| `SKILL.md` | Security-critical paths, six vulnerability categories (A-F), review methodology (5 steps), diff mode, full-scan mode, CI guidance, verifier integration |
| `references/permission-baseline.md` | Agent permission baseline with deviation detection guidance |
| `references/hook-safety-contract.md` | Hook safety contracts documenting reads, writes, and external contacts per hook |
| `references/secret-patterns.md` | Secret pattern catalog with regex patterns, known prefixes, and redaction rules |

## Related Skills

- [`code-review`](../code-review/SKILL.md) -- convention compliance review; both use the same PASS/FAIL/WARN classification
- [`cicd`](../cicd/SKILL.md) -- CI/CD pipeline design and GitHub Actions security hardening
