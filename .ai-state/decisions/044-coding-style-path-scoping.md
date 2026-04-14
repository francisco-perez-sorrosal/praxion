---
id: dec-044
title: Path-scope `rules/swe/coding-style.md` to code-file globs to reclaim always-loaded budget
status: accepted
category: configuration
date: 2026-04-13
summary: Add `paths:` YAML frontmatter to `rules/swe/coding-style.md` scoping load to code-file globs only, reclaiming ~1,900 tokens on non-code sessions; executes ROADMAP Phase 1B and funds the always-loaded cost of the behavioral contract layer (dec-043)
tags: [token-budget, path-scoping, rules, coding-style, phase-1b, budget-offset]
made_by: agent
agent_type: systems-architect
pipeline_tier: standard
affected_files:
  - rules/swe/coding-style.md
  - ROADMAP.md
affected_reqs: [REQ-BC-6]
---

## Context

`rules/swe/coding-style.md` is a 6,730-char / ~1,625-token rule containing language-independent structural and design conventions (function size, nesting depth, error handling, immutability, input validation, timestamp formatting, naming). It ships without `paths:` frontmatter and therefore loads at every session start, regardless of whether the session touches code.

ROADMAP Phase 1B (`ROADMAP.md:139`) identified this rule as the single largest available reclamation lever in always-loaded content: a `paths:` scope restricted to code-file globs would exclude it from planning-only, review-only, and documentation-only sessions — which is a large fraction of Praxion sessions, especially during pipeline coordination, ADR authoring, and skill/agent editing. The content remains in the repo and remains available; it just stops paying its cost when the session does not edit code.

The current always-loaded budget is 14,523 tokens / 96.8% of the 15,000-token ceiling (measured by sentinel T02 per `ROADMAP.md:54`). Zero headroom for new content. The behavioral contract layer (dec-043) requires ~498 tokens of new always-loaded content; shipping it without an offset would push utilization to 100.1% — exceeding the ceiling. The path-scoping of `coding-style.md` reclaims ~1,900 tokens, making dec-043 feasible and leaving ~1,400 tokens of net headroom for future growth.

ROADMAP Phase 1B originally kept this work deferred pending "validation of Phase 1A + observation of sentinel T02 trend." The behavioral contract work provides both: a concrete, measured need for the reclamation (dec-043's 498-token cost cannot be absorbed any other way without trimming the contract below the research-validated minimum) and an enforcement fit (path-scoping is low-risk because coding-style content applies when editing code, which is already the trigger pattern for most structural conventions).

## Decision

Add the following `paths:` frontmatter to `rules/swe/coding-style.md`:

```yaml
---
paths:
  - "**/*.py"
  - "**/*.pyi"
  - "**/*.ts"
  - "**/*.tsx"
  - "**/*.js"
  - "**/*.jsx"
  - "**/*.mjs"
  - "**/*.cjs"
  - "**/*.go"
  - "**/*.rs"
  - "**/*.java"
  - "**/*.kt"
  - "**/*.kts"
  - "**/*.rb"
  - "**/*.swift"
  - "**/*.c"
  - "**/*.h"
  - "**/*.cpp"
  - "**/*.hpp"
  - "**/*.cc"
  - "**/*.m"
  - "**/*.sh"
  - "**/*.bash"
  - "**/*.zsh"
---
```

No change to the rule body. The rule loads on any session that edits a file matching one of these globs and is skipped on sessions that edit only Markdown, YAML, TOML, or other non-code surfaces.

**Glob choice rationale:**

- Covers the languages most commonly touched in Praxion and downstream projects (Python, TypeScript/JavaScript, Go, Rust, Java/Kotlin, Ruby, Swift, C/C++, Objective-C, shell).
- Excludes Markdown, YAML, TOML, JSON, and other configuration/documentation surfaces where the rule's function-size, nesting-depth, and error-handling directives do not apply.
- Conservative: better to load the rule when it is not strictly needed than to miss a code-editing session. Future globs may be added as new languages enter the codebase.

The exact glob list may be refined by the implementer during execution (e.g., adding `*.lua`, `*.dart` if Praxion or its downstream projects add those languages); the operative decision is "path-scope to code-file globs," and the specific list is an implementation detail of that decision.

## Considered Options

### Option 1 — Keep unscoped (status quo)

**Pros:** No change; no risk of misconfiguration or missed sessions.
**Cons:** Always-loaded budget remains at 96.8%. The behavioral contract (dec-043) cannot ship without exceeding the ceiling. Future always-loaded content has zero headroom.

### Option 2 — Path-scope to code-file globs (chosen)

**Pros:** Reclaims ~1,900 tokens on non-code sessions. Unblocks dec-043 and provides 12.5% net headroom. Rule still loads in exactly the sessions where its conventions apply.
**Cons:** Cross-language projects gain a maintenance burden — new languages require glob additions. Mitigated by the conservative default glob set and the low frequency of new-language adoption.

### Option 3 — Extract structural conventions into a skill

Move the content to `skills/coding-style/SKILL.md` and delete the rule.
**Pros:** Eliminates the always-loaded cost entirely; skill loads only when activated.
**Cons:** Structural conventions benefit from automatic application — a developer editing a 120-line function should see the 50-line ceiling directive without needing to activate a skill. Skills are for methodology and procedure; rules are for declarative constraints applied automatically. Migration to skill-only defeats the purpose. **Rejected.**

### Option 4 — Trim the rule (keep always-loaded but smaller)

Remove lower-priority sections (e.g., Timestamp Formatting, Ordered Operations) to reclaim ~800 tokens while staying always-loaded.
**Pros:** Preserves unconditional application for structural conventions.
**Cons:** Reclaims less than half of what Option 2 reclaims, with no change in behavior for the sessions that keep the content. The trimmed sections are genuinely useful and their removal would degrade convention coverage. **Rejected.**

## Consequences

**Positive:**

- Always-loaded utilization drops from 96.8% to ~84.9% (pre-contract) and ~87.5% (post-contract), with ~1,900 tokens reclaimed.
- The behavioral contract layer (dec-043) becomes feasible without exceeding the 15,000-token ceiling.
- The rule remains a rule — not a skill, not deleted — and continues to load automatically in code-editing sessions, preserving the "declarative convention" model.
- Precedent matches dec-028 (narrowing `rules/writing/diagram-conventions.md` path-scope) — same reclamation pattern, same ADR category (`configuration`), same budget-offset role.

**Negative:**

- Sessions that touch code indirectly (e.g., editing a shell script that wraps a Python tool) receive the rule only if the shell script is edited — glob pattern is by file extension, not by session intent.
- New language adoption in Praxion (e.g., Lua, Dart, Zig) requires a glob update. This is a low-frequency, low-impact maintenance obligation.
- If the Praxion sentinel's T02 scope measurement counts `coding-style.md` differently from the actual always-loaded scope (as noted at `ROADMAP.md:146`), post-change sentinel reporting may show a different utilization than the `wc -c` direct measurement. Mitigation: align sentinel T02 scope as a separate follow-up; the underlying reclamation is real regardless of how sentinel counts it.

**Operational:**

- **Commit ordering:** this is commit 1 of the behavioral-contract PR; dec-043's commit lands immediately after. Both in the same PR per the budget-coupling constraint documented in dec-043.
- **Rollback:** reverting this commit restores the rule to unscoped always-loaded. Only attempt rollback after dec-043's commit is already reverted, otherwise the always-loaded total exceeds the ceiling.
- **Verification:** implementer opens a pure-Markdown session (no code files touched) and confirms via `wc -c` on the measured always-loaded set that `coding-style.md`'s byte count is no longer in the total. Opens a Python-editing session and confirms the rule is present.
- **Relationship to sentinel T02:** sentinel T02 scope mismatch is a known follow-up (`ROADMAP.md:146`). This ADR does not depend on T02 alignment — the reclamation is measurable directly. T02 alignment can proceed on its own schedule.
- **Supersession:** future ROADMAP phases may introduce a broader path-scoping convention (e.g., all structural rules scoped to their decision-driving file types). If such a convention supersedes this ADR, the new ADR should cite dec-044 as prior art and preserve the code-file globs or explicitly widen/narrow them with rationale.
