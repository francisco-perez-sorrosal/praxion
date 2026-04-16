# Rules

Rules are **contextual domain knowledge files** that AI assistants load automatically based on relevance. They encode constraints, conventions, and reference material to apply in specific contexts — without explicit invocation. **Tool-agnostic:** compatible with **Claude** (Code/Desktop) and **Cursor**; Claude uses `~/.claude/rules/`, Cursor uses `.cursor/rules/` (exported with frontmatter by `./install.sh cursor`).

## Current Rules

```
rules/
├── swe/
│   ├── adr-conventions.md
│   ├── agent-behavioral-contract.md
│   ├── agent-intermediate-documents.md
│   ├── coding-style.md
│   ├── memory-protocol.md
│   ├── staleness-policy.md
│   ├── swe-agent-coordination-protocol.md
│   ├── testing-conventions.md
│   └── vcs/
│       └── git-conventions.md
├── writing/
│   ├── diagram-conventions.md
│   └── readme-style.md
└── README.md
```

| File | Purpose |
| ---- | ------- |
| `swe/agent-behavioral-contract.md` | Four-behavior contract (Surface Assumptions, Register Objection, Stay Surgical, Simplicity First) for every write/plan/review agent. Always-loaded |
| `swe/agent-intermediate-documents.md` | Agent document locations (`.ai-work/` ephemeral, `.ai-state/` persistent), lifecycle tiers, cleanup |
| `swe/coding-style.md` | Immutability, function/file size, nesting, error handling, naming, validation |
| `swe/adr-conventions.md` | ADR file format (YAML frontmatter + MADR body), naming convention, supersession protocol, agent authoring guidance |
| `swe/staleness-policy.md` | Marker syntax and threshold protocol for drift-prone skill sections. Path-scoped: loads only when accessing `**/SKILL.md` |
| `swe/swe-agent-coordination-protocol.md` | Agent selection, coordination pipeline, parallel execution — detailed tables in `software-planning` skill reference |
| `swe/vcs/git-conventions.md` | Commit scope, staging discipline, secrets, exclusions, message format |
| `swe/memory-protocol.md` | When and how to use the memory MCP — `remember()` triggers, tag vocabulary, conflict resolution between memory systems |
| `swe/testing-conventions.md` | Test file placement, naming, coverage expectations, and test isolation. Path-scoped: loads only when accessing `tests/**` |
| `writing/diagram-conventions.md` | Mermaid syntax, layered decomposition (L0/L1/L2), diagram type selection. Path-scoped: loads only when accessing documentation-authoring surfaces (`docs/`, architecture docs, `.ai-state/`) |
| `writing/readme-style.md` | Precision-first technical writing and structural integrity conventions for README.md files. Path-scoped: loads only when accessing `**/README.md` or `**/README_DEV.md` |

## How Rules Work

### Loading Mechanism

Rules are **not invoked explicitly**. The tool scans its rules directory (e.g. Claude: `.claude/rules/`, Cursor: `.cursor/rules/`) and loads rules opportunistically based on:

1. **Current task** — what the user asked Claude to do
2. **Files being read or edited** — the code or config Claude is working with
3. **Semantic relevance** — filename and content matching against the current context

When you run a commit-related command, the assistant automatically picks up `git-conventions.md` when the task is semantically related. No `@`-reference or explicit import is needed.

### What Rules Are NOT

- Rules are **not callable** — there is no syntax to invoke a rule by name
- Rules are **not procedural** — they don't contain step-by-step workflows (that's what Skills are for)
- Rules are **not invoked** — there is no syntax to trigger a specific rule; the assistant loads them based on scope (personal = all projects, project = that project) and optional path/globs filters
- Rules are **not executable** — they contain knowledge, not code

## Rules vs Skills vs CLAUDE.md

Understanding when to use each configuration layer is critical for effective assistant setup (Claude, Cursor, or similar).

### Decision Model

Ask: **"Is this something Claude should _know_, or something Claude should _do_?"**

| Question | Answer | Use |
| -------- | ------ | --- |
| Should Claude always remember this? | Yes | `CLAUDE.md` |
| Should Claude know this in certain contexts? | Yes | Rule |
| Should Claude perform this as a workflow? | Yes | Skill |

### Detailed Comparison

| Aspect | CLAUDE.md | Rules | Skills |
| ------ | --------- | ----- | ------ |
| **Purpose** | Global project context | Domain-specific knowledge | Task-specific workflows |
| **Loading** | Always loaded, every session | Loaded when contextually relevant | Metadata always loaded; full content on activation |
| **Content type** | Short, opinionated directives | Deep constraints and reference material | Step-by-step procedures, optionally with code |
| **Invocation** | Automatic (always present) | Automatic (relevance-based) | Automatic (context-triggered) or explicit |
| **Execution** | N/A (passive context) | N/A (passive knowledge) | Can execute code and scripts |
| **Verbosity** | Concise — keep it lean | Concise — shares token budget with CLAUDE.md | Progressive disclosure — metadata first |
| **Scope** | Project-wide | Domain-scoped (SQL, security, git, etc.) | Task-scoped (commit, deploy, scaffold, etc.) |

### Concrete Examples

| Need | Wrong layer | Right layer |
| ---- | ----------- | ----------- |
| "Always use snake_case in Python" | Rule (too lightweight) | `CLAUDE.md` |
| "SQL column naming, join conventions, migration rules" | `CLAUDE.md` (too verbose) | Rule |
| "How to create a git commit with conventions" | Rule (procedural) | Skill or Command |
| "Commit messages must use imperative mood, type prefixes" | Skill (not procedural) | Rule |
| "Security checklist for auth code" | `CLAUDE.md` (too detailed, not always relevant) | Rule |

### How They Interact

```
CLAUDE.md          ← always in context (global directives)
    ↓
Rules              ← loaded when relevant (domain knowledge)
    ↓
Skills/Commands    ← activated for specific tasks (workflows)
```

Skills and commands **implicitly benefit** from rules — Claude has the rules in mind if they're relevant to the task a skill is performing. There is no explicit binding between them.

## Writing Effective Rules

### Structure

Rules should be **declarative and constraint-oriented**, not procedural.

**Good** — states what should be true:
```markdown
## SQL Conventions

- Always use snake_case for column names
- No SELECT *
- Explicit JOIN syntax only
- Foreign keys must be indexed
```

**Bad** — describes steps to follow (this is a Skill):
```markdown
## SQL

Step 1: Open the query editor
Step 2: Write the SELECT statement
Step 3: Make sure to use snake_case
```

### Content Guidelines

- **Be declarative** — state constraints and conventions, not procedures
- **Be specific** — "Use `snake_case` for column names" not "Use good naming"
- **Group by domain** — one rule file per coherent domain area
- **Include examples** — show correct and incorrect patterns when clarity demands it
- **Explain the _why_** — when a constraint isn't self-evident, briefly state the rationale

### Customization Sections

Rules that mix universal conventions with project-specific needs can designate `[CUSTOMIZE]` sections — clearly marked zones where users add their own content.

**When to use**: Rules covering domains with inherent project variation (coding style, testing, security). Rules that are fully universal (e.g., commit message format) don't need them.

**Pattern**: Place `### [CUSTOMIZE] <Topic>` sections at the end of the rule, after all universal content. Include placeholder guidance in HTML comments:

```markdown
## Security Baseline

- Never log tokens, API keys, or session identifiers
- Validate token expiry server-side on every request

### [CUSTOMIZE] Project Security Requirements
<!-- Add project-specific security rules here:
- Required auth mechanisms
- Compliance constraints (SOC2, HIPAA, etc.)
- Approved cryptographic libraries
-->
```

Keep universal and custom content clearly separated — never mix `[CUSTOMIZE]` content into universal sections.

### File Organization

- **One file per domain** — `sql.md`, `security.md`, `frontend.md`, not `rules1.md`
- **Split when domains diverge** — if a file covers unrelated concerns, split it
- **Don't over-split** — two closely related topics (e.g., commit format + commit rules) can coexist or split based on reuse patterns
- **Skip generic names** — `important.md`, `notes.md`, `stuff.md` hurt relevance matching

### Reference Files (Progressive Disclosure)

Rule directories may contain `references/` subdirectories for on-demand supplementary material. Files in `references/` are **not** installed as always-loaded rules -- they are loaded on-demand when a rule explicitly points to them.

This supports progressive disclosure for rules: core constraints live in the rule file (loaded automatically by relevance), while detailed protocols, examples, and extended reference material live in `references/` (loaded only when the rule or a skill directs Claude to read them).

The installer (`install.sh`) symlinks rule files but skips `references/` directories -- they remain accessible via relative paths from the rule files that reference them.

### Naming Conventions

Naming directly affects Claude's relevance scoring. Use:

- **Lowercase**, hyphen-separated
- **Domain-oriented** names that describe the subject area
- **Task-neutral** wording (rules describe _what_, not _how_)

| Good | Bad | Why |
| ---- | --- | --- |
| `sql.md` | `rules1.md` | Domain name aids relevance matching |
| `security.md` | `important.md` | Specific domain, not subjective importance |
| `git-conventions.md` | `commit.md` | Precise scope, not ambiguous |
| `frontend.md` | `stuff.md` | Meaningful, discoverable |
| `design-system.md` | `company_rules.md` | Domain-scoped, not org-scoped |

### What NOT to Put in Rules

| Content | Where it belongs |
| ------- | ---------------- |
| Temporary instructions | Prompt / conversation |
| One-off tasks | Prompt / conversation |
| User preferences | `CLAUDE.md` or `userPreferences.txt` |
| Output formatting directives | `CLAUDE.md` |
| "Always do X in every response" | `CLAUDE.md` |
| Multi-step automation workflows | Skill |
| Repeatable procedural recipes | Skill or Command |

## How Rules Reach Claude

Two mechanisms, each serving a different purpose:

### Personal rules (global baseline)

`install.sh` symlinks all rules from this repo to `~/.claude/rules/`. Personal rules load automatically for **every project** when contextually relevant — no per-project setup needed.

```
rules/swe/agent-behavioral-contract.md        →  ~/.claude/rules/swe/agent-behavioral-contract.md
rules/swe/agent-intermediate-documents.md      →  ~/.claude/rules/swe/agent-intermediate-documents.md
rules/swe/coding-style.md                     →  ~/.claude/rules/swe/coding-style.md
rules/swe/adr-conventions.md                  →  ~/.claude/rules/swe/adr-conventions.md
rules/swe/staleness-policy.md                 →  ~/.claude/rules/swe/staleness-policy.md
rules/swe/swe-agent-coordination-protocol.md  →  ~/.claude/rules/swe/swe-agent-coordination-protocol.md
rules/swe/vcs/git-conventions.md              →  ~/.claude/rules/swe/vcs/git-conventions.md
rules/writing/diagram-conventions.md          →  ~/.claude/rules/writing/diagram-conventions.md
rules/writing/readme-style.md                 →  ~/.claude/rules/writing/readme-style.md
```

Adding a new rule file here and re-running `install.sh` is all that's needed.

### Project rules (customized overrides)

When a project needs project-specific conventions (filled-in `[CUSTOMIZE]` sections, modified thresholds, domain-specific constraints), copy the rule into the project's `.claude/rules/` directory. The project copy takes precedence over the personal one.

The `/add-rules` command automates this:

```bash
/add-rules coding-style                     # Copy one rule for customization
/add-rules coding-style git-conventions     # Copy several
/add-rules all                              # Copy all rules
```

After copying, fill in the `[CUSTOMIZE]` sections with project-specific content and commit to git.

**Do not copy rules you don't intend to customize** — personal rules already load for every project. Copying without customizing just wastes tokens (both copies load into context).
