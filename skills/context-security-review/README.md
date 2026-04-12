# Context Security Review Skill

Security review methodology for Claude Code plugin ecosystems -- context artifacts, hooks, dependencies, scripts, secrets, and CI workflows.

## Vulnerability Categories

- **A. Context Artifact Injection** -- malicious instructions in CLAUDE.md, skills, agents, rules, commands
- **B. Hook Compromise** -- hook scripts that exfiltrate data, escalate permissions, or contact unauthorized services
- **C. Dependency Supply Chain** -- untrusted dependencies, unpinned versions, typosquatting
- **D. Script and Configuration Injection** -- install scripts, plugin config, settings manipulation
- **E. Secrets and Data Exposure** -- hardcoded secrets, insufficient gitignore, log leakage
- **F. GitHub Actions Security** -- workflow injection, excessive permissions, unsafe action usage

## Operating Modes

- **Diff mode** (default) -- reviews only changed files in a PR or change set. Used by CI and the verifier agent.
- **Full-scan mode** -- reviews ALL files matching security-critical paths. Used by the `/full-security-scan` command.

## Consumers

| Consumer | Mode | Context |
|----------|------|---------|
| CI workflow (`.github/workflows/context-security-review.yml`) | Diff | Runs on PR open/synchronize, posts findings as PR comments |
| Verifier agent (Phase 6) | Diff | Loads alongside `code-review` during post-implementation verification |
| `/full-security-scan` command | Full-scan | On-demand comprehensive security audit with posture grade |

## Skill Contents

| File | Purpose |
|------|---------|
| [`SKILL.md`](SKILL.md) | Core reference: security-critical paths, vulnerability categories, review methodology, mode-specific guidance |
| [`references/permission-baseline.md`](references/permission-baseline.md) | Agent permission baseline with deviation detection |
| [`references/hook-safety-contract.md`](references/hook-safety-contract.md) | Hook safety contracts (reads, writes, external contacts) |
| [`references/secret-patterns.md`](references/secret-patterns.md) | Secret pattern catalog with regex patterns and redaction rules |
