---
name: upstream-stewardship
description: >
  Responsible upstream OSS contribution: issue deduplication, sensitive information
  sanitization, template compliance, contribution etiquette, responsible disclosure.
  Triggers: filing an upstream issue, reviewing a bug report draft for an external
  project, discovering an upstream bug during development, contributing a fix to an
  open-source dependency; filing issues on dependencies, reporting third-party bugs,
  OSS contribution workflow.
allowed-tools: [Read, Grep, Glob]
compatibility: Claude Code
---

# Upstream Stewardship

Methodology for being a responsible open-source citizen: reporting bugs effectively, protecting sensitive information, respecting project conventions, and contributing fixes upstream. The `/report-upstream` command drives the filing workflow; this skill provides the methodology that any agent or command can reference.

**Satellite files** (loaded on-demand):

- [references/sanitization-patterns.md](references/sanitization-patterns.md) -- extended pattern catalog for detecting internal information in issue drafts
- [references/issue-templates.md](references/issue-templates.md) -- YAML form parsing methodology and built-in bug report template
- [references/contribution-workflow.md](references/contribution-workflow.md) -- fork-and-PR workflow for contributing fixes upstream

## Gotchas

- **`gh issue create --template` only works with markdown templates.** YAML form-based templates (`.yml`) used by most modern repos are GitHub web-only. To file template-compliant issues via CLI, parse the YAML template and construct a `--body` that maps to each required field. See [references/issue-templates.md](references/issue-templates.md).
- **GitHub semantic search rate limit is 10 req/min.** The `search_type=hybrid` parameter on the REST API is not yet exposed in `gh` CLI — use `gh api` or `curl` directly. Keyword search via `gh search issues` (30 req/min) is the required baseline; semantic is a best-effort enhancement.
- **Some repos disable blank issues.** When `config.yml` has `blank_issues_enabled: false`, filing a free-form issue via `gh issue create --body` still works via the API but goes against the project's intent. Always check for templates first.
- **Community profile API reveals repo expectations.** `gh api repos/{owner}/{repo}/community/profile` returns whether the repo has CONTRIBUTING.md, code of conduct, issue templates, and a health score — use this for reconnaissance before filing.

## Deduplication Strategy

Search for existing issues **before** drafting a new one. Use a two-layer approach:

### Layer 1: Keyword Search (required)

```bash
gh search issues "<key terms from bug description>" --repo owner/repo --state open --json number,title,url,labels --limit 20
```

Extract 3-5 key terms: error messages, function/class names, behavioral keywords. Run 2-3 queries with different term combinations to cover lexical variations.

### Layer 2: Semantic Search (best-effort)

When keyword results are insufficient, use GitHub's hybrid search via REST API:

```bash
gh api -X GET '/search/issues' \
  -f q='repo:owner/repo is:issue is:open <natural language description>' \
  -f search_type=hybrid \
  --jq '.items[:10] | .[] | {number, title, html_url}'
```

This matches on meaning, not just keywords — finding issues with different wording but the same root cause.

### Decision Tree

After reviewing search results:

| Situation | Action |
|-----------|--------|
| **Strong match** — same root cause, same symptoms, same component | Comment on the existing issue with your additional evidence. Do not file a new issue. |
| **Partial match** — related area but different root cause or broader scope | File a new issue. Reference the related issue with "Related to #NNN" in the body. |
| **Weak match** — similar keywords but clearly different problem | File a new issue. No cross-reference needed. |
| **No match** | File a new issue. |

**Judgment call**: An existing issue that is too broad or incorrectly described does not make your finding a duplicate. If your report adds specificity, a concrete MRE, or identifies a distinct root cause, it deserves its own issue — even if the area overlaps.

## Sanitization Pipeline

Before presenting a draft for user review, scan for internal information that should not appear in a public upstream issue. For credential-specific patterns (API keys, tokens, cloud provider secrets), see the `context-security-review` skill's [secret-patterns catalog](../context-security-review/references/secret-patterns.md). This skill extends those patterns with upstream-specific categories.

### Categories

| Category | Example | Replacement |
|----------|---------|-------------|
| Home directory paths | `/Users/fperez/dev/praxion/src/...` | `<project-root>/src/...` |
| Internal hostnames | `db.internal.corp:5432` | `<internal-host>:5432` |
| Memory/observation content | `.ai-state/memory.json` excerpts | `[internal state redacted]` |
| Internal project names | Codenames, internal tool names | `[internal tool]` or generic description |
| Credentials | API keys, tokens, passwords | `[REDACTED]` (per secret-patterns.md) |
| PII | Email addresses, usernames in logs | `user@example.com`, `<username>` |

See [references/sanitization-patterns.md](references/sanitization-patterns.md) for the full regex catalog and replacement rules.

### Privacy-Reproducibility Tension

Stripping internal details can make the bug harder to reproduce. Resolution strategies:

1. **Build a parallel MRE** — create a minimal example using only public information that triggers the same bug
2. **Use the project's own test fixtures** — if the bug reproduces with the upstream project's own test data, that is ideal
3. **Abstract and validate** — sanitize, then verify the sanitized version still reproduces. If it does not, iteratively add back context in generic form
4. **When in doubt, redact more** — the user review gate is the final safety net. It is easier to add back context than to retract leaked information

## Template Compliance

Respecting a project's issue template is a quality signal. See [references/issue-templates.md](references/issue-templates.md) for the full methodology.

### Quick Reference

1. **Fetch templates**: `gh api repos/{owner}/{repo}/contents/.github/ISSUE_TEMPLATE --jq '.[].name'`
2. **Read the bug report template**: `gh api -H "Accept: application/vnd.github.raw" repos/{owner}/{repo}/contents/.github/ISSUE_TEMPLATE/{template_name}`
3. **Parse required fields** from YAML `body:` array — each item with `validations.required: true`
4. **Map your content** to each field, using the field's `label` as a section header
5. **If no template exists**, use the built-in structure from references/issue-templates.md

## Issue Draft Structure

When composing the issue body, follow the "Ten Simple Rules" framework:

1. **Title**: Specific, descriptive. Include the affected component and the behavior. Bad: "Something is wrong". Good: "SubagentStart hooks not fired for background agents (run_in_background: true)"
2. **Description**: What happened vs. what should happen. One paragraph, direct.
3. **Steps to Reproduce**: Numbered, sequential, deterministic. Include the minimal reproducible example (MRE).
4. **Evidence**: Quantitative data when possible (counts, timings, error messages). Use collapsible sections for lengthy logs.
5. **Environment**: Version, OS, platform, relevant configuration.
6. **Impact**: Why this matters — what downstream behavior is affected.

The MRE is the single most important element. Invest time crafting one that is minimal, complete, and self-contained.

## Responsible Disclosure Path

When the discovered bug has security implications (vulnerability, data exposure, authentication bypass):

1. **Never file a public issue.** Security-sensitive bugs must go through private channels.
2. **Check for SECURITY.md**: `gh api -H "Accept: application/vnd.github.raw" repos/{owner}/{repo}/contents/SECURITY.md`
3. **Check for GitHub private vulnerability reporting**: Navigate to the repo's Security tab → "Report a vulnerability" (or check community profile for `security_advisories` field)
4. **Follow the project's stated process.** If no security policy exists, contact maintainers via email if available.
5. **Include**: clear description, reproduction steps, impact assessment, affected versions, suggested mitigation
6. **Do NOT include**: internal infrastructure details, exploit code beyond proof of concept
7. **Timeline**: The industry standard is 90 days for coordinated disclosure. State your expectation clearly.

## Agent Discovery Protocol

When a pipeline agent (researcher, implementer, verifier) encounters behavior that appears to be a bug in an upstream dependency during its normal work:

1. **Document the evidence** in the agent's output document (RESEARCH_FINDINGS.md, WIP.md, or VERIFICATION_REPORT.md)
2. **Include**: the affected dependency, version, observed behavior, expected behavior, and reproduction context
3. **Flag for the user**: recommend invoking `/report-upstream owner/repo "description"` for formal filing
4. **Do not file autonomously.** Upstream issue filing requires human judgment and approval.

## Context-Hub Verification

Before filing, optionally verify the bug is not a misunderstanding of the documented API:

1. Search context-hub: `chub search "<upstream project name>"`
2. If docs are available: `chub get <package-name>` to fetch curated API documentation
3. Compare the reported behavior against the documented contract
4. If the behavior matches documentation, it is not a bug — it may be a feature request or a documentation gap

This step is optional but reduces false reports, especially for complex APIs.

## Contribution Etiquette

- **Be patient.** Many maintainers are volunteers with limited bandwidth.
- **One bug per issue.** Do not combine unrelated findings.
- **Stay engaged.** Respond promptly to maintainer questions. Remote debugging requires collaboration.
- **Think of yourself as part of the team.** Investigate causes, suggest fixes, submit PRs when possible.
- **Offer, don't demand.** "I'd be happy to submit a PR for this" is better than "Please fix this."
- **Respect rejection.** Sometimes the direction does not fit the project's roadmap.

See [references/contribution-workflow.md](references/contribution-workflow.md) for the full fork-and-PR workflow.

## Persistent Tracking

All filed issues are recorded in `.ai-state/UPSTREAM_ISSUES.md` — an append-only log committed to git. Any agent or session can read this file to check:

- Whether we have already filed an issue for a given problem
- What local workarounds are in use for open upstream issues
- The current status of previously filed issues

The tracker is written by the `/report-upstream` command workflow. Agents should grep it before recommending a new filing.
