---
name: rule-crafting
description: Creating and managing rules -- contextual domain knowledge
  files loaded automatically based on relevance. Covers rule structure, path-specific
  rules, naming for relevance matching, content guidelines, and the rules-vs-skills-vs-CLAUDE.md
  decision model. Use when creating new rules, updating existing rules, debugging
  rule loading, organizing rule files, or deciding whether something belongs in a
  rule vs skill vs CLAUDE.md. Also covers Claude Code rule authoring, auto-loaded
  rule mechanics, and rule debugging techniques.
allowed-tools: [Read, Write, Edit, Glob, Grep, Bash]
compatibility: Claude Code
---

# Rules

Guide for creating effective, contextual rules.

**Satellite files** (loaded on-demand):
- [REFERENCE.md](REFERENCE.md) -- complete rule examples, path-specific patterns, migration strategies
- [../skill-crafting/references/artifact-naming.md](../skill-crafting/references/artifact-naming.md) -- naming conventions for all artifact types

## What Are Rules

**Rules** are contextual domain knowledge files that Claude loads automatically based on relevance — no explicit invocation needed.

- Loaded opportunistically by task, active files, and semantic matching
- **All-or-nothing loading** — when a rule is triggered, its entire file content is injected into context. There is no partial or progressive loading within a single rule file. This is why keeping each file focused matters
- Declarative (constraints and conventions), not procedural (workflows)
- One `.md` file per coherent domain area
- Project or personal scope
- Keep rules concise — they share the always-loaded token budget with CLAUDE.md

## File Locations

**Project rules** (shared with team):
```
.claude/rules/<rule-name>.md
```

**Personal rules** (across all projects):
```
~/.claude/rules/<rule-name>.md
```

| Scope | Path | Shared | Priority |
|-------|------|--------|----------|
| Project | `.claude/rules/` | Via git | Higher |
| Personal | `~/.claude/rules/` | No | Lower |

Project rules take precedence over personal rules with the same name.

## Codex Interop

Do **not** assume Codex native rules have the same semantics as Claude rules.
They do not.

| Surface | Claude / Praxion rule model | Codex native model |
|---|---|---|
| Primary artifact | Markdown rule in `.claude/rules/*.md` | Policy rule in `.codex/rules/*.rules` |
| Purpose | Semantic guidance and constraints | Command approval / sandbox policy |
| Loading | Relevance-based, optional `paths:` frontmatter | Evaluated against command prefixes in the active config layers |
| Scope | Task, active files, semantic matching | Command execution decisions |
| Best content | Conventions, constraints, domain knowledge | Outside-sandbox approval policy for known-safe commands |

For Praxion interop, treat Codex `.rules` as a **different primitive**, not as a
drop-in export target for `rules/**/*.md`.

### Translation Rubric

When adapting Praxion rules to Codex, map by semantics:

| Praxion rule content | Codex target |
|---|---|
| Command-prefix approval policy | `.codex/rules/*.rules` |
| Always-on semantic guidance | root `AGENTS.md` |
| Directory- or file-family-specific semantic guidance | nested `AGENTS.md` files near the matching paths |
| Prompt-time context injection or validation | hooks such as `SessionStart` and `UserPromptSubmit` |
| Tool/action guardrails | hooks such as `PreToolUse`, `PostToolUse`, and `PermissionRequest` |

### Automatic Codex Classification

Praxion's Codex bridge should pick up new canonical rules automatically on each
`install.sh codex ...` run. Do not maintain a separate Python allowlist for new
rules.

Default behavior:

- Rules with `paths:` become path-scoped Codex candidates.
- Rules without `paths:` become always-on Codex candidates.
- Clearly Claude-specific rules are excluded automatically.

When automatic classification needs an exception, annotate the canonical rule
with optional `codex:` frontmatter:

```yaml
---
codex:
  portability: portable     # or claude_only, auto
  load: always_on           # or path_scoped, exclude, auto
---
```

Use explicit Codex metadata sparingly:

- `portability: portable` when a rule should remain Codex-visible despite
  assistant-specific examples or references
- `portability: claude_only` when the rule is intentionally tied to Claude
  runtime semantics
- `load: exclude` when the rule is portable in principle but should stay out of
  Codex automatic loading

### What Not To Do

- Do not rewrite a declarative Markdown rule into a `.codex/rules/*.rules` file
  unless the rule is truly about command approval semantics.
- Do not treat Codex hooks as a perfect substitute for Claude `paths:`
  frontmatter. Hooks can add or validate context, but they are event-driven,
  not native semantic rule files.
- Do not fork Praxion rule bodies into Codex-specific copies unless a hard
  platform boundary forces it. Keep `rules/**/*.md` canonical and generate or
  install Codex surfaces from that source.
- Do not add new hardcoded exporter allowlists just to make a rule visible to
  Codex. Prefer automatic classification, with canonical `codex:` metadata only
  when needed.

### Path-Scoped Rule Translation

Claude `paths:` frontmatter has no direct Codex-native equivalent for semantic
rules. The least-lossy Codex adaptation is:

1. Keep the canonical rule in `rules/**/*.md`.
2. Translate directory-scoped guidance into nested `AGENTS.md` files where the
   directory boundary matches the rule boundary.
3. Use hooks only when directory-local project docs are insufficient.

Examples:

- `tests/**` conventions -> `tests/AGENTS.md`
- `docs/**` writing conventions -> `docs/AGENTS.md`
- `dashboard_app/**` UI/dashboard conventions -> `dashboard_app/AGENTS.md`
- `skills/**` maintenance rules -> `skills/AGENTS.md`

### Design Principle

For Codex interop, preserve Praxion rule meaning before optimizing for native
surface area. A smaller number of faithful translations beats a broad but lossy
export.

## Context Hierarchy — What Loads, When, and Who Wins
<!-- last-verified: 2026-05-12 -->

Claude Code assembles always-loaded instruction context from a layered hierarchy. Loading walks from least-specific to most-specific; **on conflict, the more specific layer wins** (the cwd's own file is read last). Ancestor `CLAUDE.md` / `CLAUDE.local.md` files are loaded **in full at launch** (walking cwd → filesystem root, parent before child); subdirectory `CLAUDE.md` files load **on-demand** when Claude reads a file in that subdir — *not* at launch.

| Layer (least → most specific) | Path(s) | Loading | What belongs here |
|---|---|---|---|
| Managed policy | macOS `/Library/Application Support/ClaudeCode/CLAUDE.md`; Linux/WSL `/etc/claude-code/CLAUDE.md`; `managed-settings.json` `claudeMd` key | Always at launch; **cannot be excluded** | Org-wide mandates only |
| User | `~/.claude/CLAUDE.md`, `~/.claude/rules/*.md` | Always at launch | Cross-project philosophy and conventions |
| Ancestor directories | any `CLAUDE.md` / `CLAUDE.local.md` between cwd and `/` | Loaded in full at launch (root-down) | Rare outside monorepos |
| Workspace (directory-of-repos) | a `CLAUDE.md` at e.g. `~/repos/<org>/`, the parent of several checkouts | Picked up as an ancestor when `claude` runs from a nested project — no special mechanism, just a convention + a file | Cross-repo norms ("everything under here is trunk-based dev"); a worktree-context banner |
| Project | `./CLAUDE.md` or `./.claude/CLAUDE.md`; `./.claude/rules/*.md` | Always at launch | Project baseline + path-scoped rules |
| Project-local override | `./CLAUDE.local.md` | Always at launch; **`.gitignore` it** | Private per-project prefs (supported, not deprecated). Worktree caveat: exists only in the worktree where created — to share across worktrees, `@~/.claude/...`-import instead |
| Subdirectory | `<subdir>/CLAUDE.md` | **On-demand** when Claude reads a file under `<subdir>/` — not at launch | Directory-local conventions (e.g. `scripts/CLAUDE.md`, `tests/CLAUDE.md`); keeps them off the launch-time always-loaded surface |

Path-scoped rules (`paths:` frontmatter, in project or user `rules/`) sit alongside the project / user layers but load **on Read of a matching file** — see [Path-Scoped Rules: Read-Only Loading Trigger](#path-scoped-rules-read-only-loading-trigger).

- **`claudeMdExcludes`** — real setting (array; set in `.claude/settings.local.json` etc.; merges across layers): skip specific `CLAUDE.md` / rules files by absolute-path glob. Useful for monorepos with irrelevant ancestor files. Managed-policy `CLAUDE.md` can't be excluded.
- **`InstructionsLoaded` hook** — the docs recommend it to log exactly which instruction files load, when, and why; it's the tool for debugging path-scoped rules and lazy-loaded subdirectory files. (`--add-dir` does *not* load `CLAUDE.md` from extra dirs unless `CLAUDE_CODE_ADDITIONAL_DIRECTORIES_CLAUDE_MD=1`.)
- Inspect what actually loaded in a live session with `/memory`.

Rules override user memory but yield to project memory and managed policy. Full coverage: `~/.claude/CLAUDE.md` and `rules/CLAUDE.md`.

## Why the Always-Loaded Budget Exists

`CLAUDE.md` files and unconditional rules are **context, not enforced config** — Claude Code delivers them as a user message after the system prompt, so there is no guarantee of strict compliance (per `code.claude.com/docs/en/memory`). Two consequences:

- **Specific, concise, well-structured wins.** Concrete constraints and a `| pattern | why it fails | what to do |` table are followed more reliably than long discursive prose. The docs' guideline: target **under 200 lines per `CLAUDE.md` / rule file** — longer files "consume more context and reduce adherence."
- **For a hard guarantee, use a hook.** A rule line is advisory and probabilistic; a hook (`PreToolUse`, `PostToolUse`, `SessionStart`, …) is deterministic and lifecycle-executed. If a behavior must happen 100% of the time, it isn't a rule — see the [`hook-crafting`](../hook-crafting/SKILL.md) skill's "When a Hook (vs a Rule)" criterion.

The ecosystem-wide budget for *all* always-loaded content (every `CLAUDE.md` plus every rule without `paths:` frontmatter) is **25,000 tokens** — a failure-mode guardrail, not a target. The operating principle: every always-loaded token must earn its attention share — applied in >30% of sessions, or unconditionally relevant. Anything below that bar belongs in a `paths:`-scoped rule or a skill. (Practitioner write-ups circulate specific per-session token breakdowns and "instruction-count ceilings"; those *numbers* aren't documented by Anthropic — treat the discipline as load-bearing and the figures as folklore.)

## Rule File Structure

Use `##` (h2) as the top-level heading — rules are injected into a larger context, so h1 would conflict with the surrounding document structure.

### Basic Rule

```markdown
## SQL Conventions

- Always use snake_case for column names
- No SELECT * — enumerate columns explicitly
- Explicit JOIN syntax only (no implicit joins)
- Foreign keys must be indexed
```

No frontmatter needed for rules that should load whenever their domain is relevant.

### Path-Specific Rule

Add `paths` frontmatter to restrict loading to specific file patterns:

```markdown
---
paths:
  - "src/api/**/*.ts"
  - "src/api/**/*.tsx"
---

## API Error Handling

- All API handlers must return structured error responses
- Use the ApiError class from `src/lib/errors.ts`
- Never expose internal error details to clients
```

The rule loads only when Claude is working on files matching the glob patterns.

**Glob syntax**:
- `**/*.ts` — all TypeScript files recursively
- `src/api/**` — everything under `src/api/`
- `*.{ts,tsx}` — brace expansion for multiple extensions
- `tests/` — all files under `tests/` directory

### Path-Scoped Rules: Read-Only Loading Trigger
<!-- last-verified: 2026-05-12 -->

A path-scoped rule injects **only when Claude reads a file matching the glob** — not when it `Write`s, `Edit`s, or `MultiEdit`s one. This is a real gap, not a corner case:

- **Symptom**: an agent that *creates* a new file via `Write` without first reading a matching sibling never sees that file type's conventions. A new `.py`/`.ts` misses `coding-style.md`; a new doc misses `readme-style.md` / `diagram-conventions.md` / `html-output-conventions.md`; a new `.github/*.md` misses `pr-conventions.md`; a new file misses `id-citation-discipline.md`, `staleness-policy.md`, etc. The miss is **silent** — nothing warns you the rule didn't load.
- **Why it's usually fine**: agents normally read existing files in a directory before working there, which incidentally loads the path-scoped rules. The gap bites on *greenfield file creation* in a directory the agent hasn't touched yet.
- **Mitigation**: before creating a new file in a directory, read an existing sibling first (or, if the directory is empty, a canonical example of that file type elsewhere) so the path-scoped rules load into context. Praxion's `implementer`, `doc-engineer`, and `test-engineer` agent prompts carry this instruction.
- **For a hard guarantee, use a hook** — a `PostToolUse(Write)` hook can re-inject the relevant rule deterministically. That's heavier to maintain; reach for it only if the prompt-level mitigation proves insufficient. (Rules shape behavior; hooks enforce it.)

Verified 2026-05-12 against `code.claude.com/docs/en/memory` + Claude Code issues [#23478](https://github.com/anthropics/claude-code/issues/23478), [#38487](https://github.com/anthropics/claude-code/issues/38487) (feature request — load path-scoped rules on Write/Edit), [#16853](https://github.com/anthropics/claude-code/issues/16853). **Windows note**: per [#21858](https://github.com/anthropics/claude-code/issues/21858), `paths:` frontmatter in `~/.claude/rules/` is ignored on Windows (closed-as-stale, not confirmed fixed; not reproduced on macOS/Linux) — on Windows, keep path-scoped rules under a project-level `.claude/rules/` instead.

## Directory Organization

Scale organization to project complexity. Choose the simplest tier that fits.

| Tier | When | Structure | Example |
|---|---|---|---|
| **Flat** | <10 rules, no language divergence | All rules directly under `.claude/rules/` | `sql.md`, `security.md`, `git-commit-format.md` |
| **Layered** | Multiple languages with divergent conventions | `common/` + `<language>/` subdirectories | See worked example below |
| **Path-Scoped** | Granular per-path targeting needed | Rules with `paths` globs (see [REFERENCE.md](REFERENCE.md)) | `paths: ["src/api/**/*.ts"]` |

Claude loads rules recursively from subdirectories. Language-specific files extend common ones — use the pattern: *"This file extends `common/coding-style.md` with TypeScript-specific conventions."*

**Layered worked example**:

```
.claude/rules/
├── common/              # Universal rules (always loaded when relevant)
│   ├── coding-style.md
│   ├── testing.md
│   └── security.md
├── typescript/          # Extend common with TS specifics
│   ├── coding-style.md
│   └── testing.md
└── python/
    ├── coding-style.md
    └── testing.md
```

## Naming Convention

Pattern: `<domain>-<rule-intent>.md`

The `<domain>` prefix aids Claude's relevance matching. The `<rule-intent>` suffix clarifies scope within the domain. Together they make rules discoverable across any field.

```
Software:     git-commit-format.md, sql-naming.md, api-error-handling.md
Security:     auth-token-handling.md, secrets-management.md
Writing:      technical-writing-style.md, documentation-tone.md
Business:     pricing-model-constraints.md, compliance-gdpr.md
Research:     citation-format.md, data-collection-ethics.md
```

**Naming principles**:
- Lowercase, hyphen-separated
- Domain-oriented — describe the subject area, not the action
- Specific — `git-conventions.md` not `commit.md`
- No generic names — `important.md`, `notes.md`, `stuff.md` hurt relevance matching

## Writing Rule Content

### Be Declarative

State what should be true, not steps to follow. Procedural content belongs in a Skill, not a rule.

| Good (constraints) | Bad (procedure — move to Skill) |
|---|---|
| `- Column names use snake_case` | `Step 1: Open the query editor` |
| `- Foreign keys must be indexed` | `Step 2: Write the SELECT statement` |
| `- No implicit joins` | `Step 3: Make sure to use snake_case` |

### Content Guidelines

- **Be specific** — "Use `snake_case` for column names" not "Use good naming"
- **Group by domain** — one file per coherent domain area
- **Include examples** — show correct and incorrect patterns when clarity demands it
- **Explain the _why_** — when a constraint isn't self-evident, briefly state the rationale
- **Pair every prohibition with a remedy** — a `NEVER` / `Don't` line must be followed by a `→ do this instead`. Document anti-patterns as a `| pattern | why it fails | what to do instead |` table (see [Anti-Patterns](#anti-patterns) below for the canonical shape), not a bare list of forbidden things — a rule that only says "don't" leaves the reader to guess the right move, which is exactly the moment a stochastic model improvises.
- **Token budget awareness** — rules are eagerly loaded within scope (personal = all projects, project = that project), adding to the baseline token cost of every conversation and agent spawn. The ecosystem budget is 25,000 tokens for all always-loaded content (CLAUDE.md files + rules) as a failure-mode guardrail — every always-loaded token must earn its attention share. Keep rules concise; if one grows too large, compress it (tables over prose, remove redundancy) or move procedural content to a skill — but never split into main + reference files (see Self-Containment Constraint below)

### Customization Sections

For rules that cover domains with project variation (coding style, testing, security, deployment), use `### [CUSTOMIZE] <Topic>` sub-sections — placed at the end after universal content — to separate universal conventions from project-specific overrides. Use HTML comment placeholders (`<!-- -->`) for author guidance so they don't affect rule semantics. Fully universal rules (e.g., commit format) omit customization entirely.

See [REFERENCE.md#customization-section-examples](REFERENCE.md#customization-section-examples) for worked patterns.

## Rules vs Skills vs CLAUDE.md

Ask: **"Is this something Claude should _know_, or something Claude should _do_?"**

| Question | Answer | Use |
|----------|--------|-----|
| Should Claude always remember this? | Yes | `CLAUDE.md` |
| Should Claude know this in certain contexts? | Yes | Rule |
| Should Claude perform this as a workflow? | Yes | Skill |

| Need | Wrong layer | Right layer |
|------|-------------|-------------|
| "Always use snake_case in Python" | Rule (too lightweight) | `CLAUDE.md` |
| "SQL column naming, join conventions" | `CLAUDE.md` (too verbose) | Rule |
| "How to create a git commit with conventions" | Rule (procedural) | Skill or Command |
| "Commit messages must use imperative mood" | Skill (not procedural) | Rule |
| "Security checklist for auth code" | `CLAUDE.md` (too detailed, not always relevant) | Rule |

## Creation Workflow

1. **Identify** — recognize recurring contextual knowledge Claude needs
2. **Decide layer** — is this CLAUDE.md, a rule, or a skill? (see decision table above)
3. **Name** — use `<domain>-<rule-intent>.md` pattern for relevance matching
4. **Organize** — choose flat, layered, or path-scoped placement
5. **Write** — declarative constraints, not procedures; include examples
6. **Place** — project `.claude/rules/` or personal `~/.claude/rules/`
7. **Verify** — use `/memory` to confirm the rule loads in the expected context
8. **Iterate** — refine based on Claude's behavior; adjust scope, naming, or content
   - **Split** when a rule file covers unrelated concerns (e.g., SQL naming + API auth in one file)
   - **Merge** when two files overlap heavily and are always loaded together
   - **Don't over-split** — closely related topics (commit format + commit rules) can coexist based on reuse patterns
   - Keep each file focused on a single coherent domain

## Self-Containment Constraint

**Rules must be fully self-contained.** Each rule file must carry all its content — never split a rule into a main file plus a reference/satellite file.

**Why:** Only `.md` files directly in `~/.claude/rules/` (and its subdirectories) are loaded by Claude. If a rule references a companion file (e.g., `references/details.md`) that isn't installed alongside it, that content is unreachable in every project except the source repository. The reference becomes a dangling link and the rule loses semantics.

**What this means in practice:**
- Do not create `references/` subdirectories under rules
- Do not use "see `<path>` for details" patterns that point to non-rule files
- If a rule is too large, compress it (tables over prose, remove redundancy) or split it into two independent rules by domain — never into main + supplement
- Skills can use reference files (they control their own loading); rules cannot

**Escape hatch:** Rules can point to skill reference files for supplementary depth. Skills have base path injection on activation, making their reference files resolvable cross-project. A rule can say "When working on UI components, load the `ui-change` skill" — the rule stays lean and the heavy instructions live in the skill's progressively-disclosed reference files. This is the recommended pattern when a rule needs supporting material that exceeds self-containment limits

## Anti-Patterns

| Anti-Pattern | Problem | Fix |
|-------------|---------|-----|
| Generic filenames (`rules1.md`, `stuff.md`) | Hurts relevance matching | Use `<domain>-<rule-intent>.md` |
| Procedural content (step-by-step) | Rules are knowledge, not workflows | Move to a Skill or Command |
| Overly broad rules (everything in one file) | Loads unnecessary context | Split by domain |
| Over-splitting (one constraint per file) | File proliferation, hard to maintain | Group related constraints |
| Splitting into main + reference file | Reference file won't be installed; content lost in other projects | Keep rules self-contained |
| "Always do X" directives | Belongs in always-loaded context | Move to `CLAUDE.md` |
| Duplicating CLAUDE.md content | Redundant, may conflict | Keep in one place only |
| Referencing rule filenames in commands | Filenames aren't invocable | Use semantic hints instead |

## Resources

- [Official Documentation](https://docs.anthropic.com/en/docs/claude-code/memory#rules) -- rules section of Claude Code memory docs
- [rules/README.md](../../rules/README.md) -- user-facing documentation for rules in this repository
- Extended examples: See [REFERENCE.md](REFERENCE.md) for complete rule patterns and migration strategies
