---
description: Run a full-project security audit against all security-critical paths
argument-hint:
allowed-tools: [Read, Glob, Grep, Bash(git:*), Bash(find:*)]
---

# Full Security Scan

Perform a comprehensive security audit of the entire project by loading the
`context-security-review` skill in **full-scan mode**. Unlike the CI workflow
and verifier (which review only changed files), this command reviews ALL files
matching security-critical paths.

## Process

1. **Load the skill**: Activate the `context-security-review` skill in full-scan mode
2. **Enumerate targets**: Find all files matching the security-critical paths
   checklist from the skill (CLAUDE.md files, agents, skills, rules, commands,
   hooks, plugin manifest, pyproject.toml files, workflows, install scripts,
   settings)
3. **Assess each file**: For each file, apply all six vulnerability categories
   from the skill
4. **Check permission baseline**: Compare current agent permissions against the
   baseline in `references/permission-baseline.md`
5. **Check hook contracts**: Verify each hook's behavior against the contract in
   `references/hook-safety-contract.md`
6. **Scan for secrets**: Check all files for patterns from
   `references/secret-patterns.md`
7. **Produce report**: Generate a structured report with:
   - Executive summary (total files scanned, findings by severity)
   - Per-category findings (grouped by vulnerability category A-F)
   - Security posture grade (A-F based on finding severity distribution)
   - Recommended actions (prioritized by impact)
