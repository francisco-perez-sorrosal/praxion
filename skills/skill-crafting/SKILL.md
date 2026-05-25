---
name: skill-crafting
description: >
  Creating, updating, and optimizing Agent Skills for Claude Code, Cursor, and
  compatible agents: skill anatomy, progressive disclosure, SKILL.md frontmatter,
  init/validate/package workflow. Triggers: creating new skills, updating or
  modernizing existing skills, converting memory files to skills, debugging skill
  activation, skill architecture and best practices.
allowed-tools: [Read, Write, Edit, Glob, Grep, Bash]
compatibility: Claude Code
staleness_sensitive_sections:
  - "Skill Content Lifecycle"
  - "Cross-Agent Portability"
  - "Context-Engineering Sources"
---

# Skill Creator

Guide for creating effective Agent Skills. Official specification at [agentskills.io](https://agentskills.io). Authoring guidance at [Anthropic's best practices](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices).

**Start here:** [references/context-engineering-foundations.md](references/context-engineering-foundations.md) -- the shared "why" behind every `*-crafting` skill (context rot, the attention budget, progressive disclosure, eval-first). Read once; it is cited, not restated, throughout the six skills.

**Satellite files** (loaded on-demand):

- [references/context-engineering-foundations.md](references/context-engineering-foundations.md) -- context-engineering foundations (shared spine for all six crafting skills)
- [references/cross-agent-portability.md](references/cross-agent-portability.md) -- discovery paths per tool, portability guidance
- [references/artifact-naming.md](references/artifact-naming.md) -- naming conventions for all artifact types
- [references/content-and-development.md](references/content-and-development.md) -- content type selection, feedback loops, evaluation-driven development
- [references/output-patterns.md](references/output-patterns.md) -- template and examples patterns for skill output
- [references/workflows.md](references/workflows.md) -- sequential and conditional workflow patterns
- [references/skill-categories.md](references/skill-categories.md) -- nine skill archetype categories from Anthropic's internal practice
- [references/plugin-and-troubleshooting.md](references/plugin-and-troubleshooting.md) -- plugin mechanics, anti-patterns, troubleshooting

## About Skills

Skills are modular, self-contained packages that extend agent capabilities with specialized workflows, tool integrations, domain expertise, and bundled resources. Each skill is a directory containing a `SKILL.md` file with instructions and optional scripts, references, and assets. Skills activate on-demand when the agent determines they are relevant, keeping the base context lean.

## Core Principles

These principles are the skill-authoring face of [context engineering](references/context-engineering-foundations.md) -- consult that reference for the empirical grounding (context rot, the attention budget, the four failure modes).

**The context window is a public good.** A skill shares the context window with system prompts, conversation history, other skills' metadata, and the user's request. Every token must earn its place.

**The agent is already smart.** Only include information the model does not possess. Challenge each piece: "Does the agent really need this?" If in doubt, leave it out.

**But not all agents are equally capable.** Skills may be consumed by agents with varying model capabilities. Avoid explaining universal knowledge (basic syntax, common idioms), but include enough context -- concrete examples, complete workflows, and explicit decision criteria -- so specific conventions can be followed correctly by less capable agents too. Examples and workflows are robust across the capability spectrum: they guide weaker agents without burdening stronger ones. Test with all models you plan to use -- what works perfectly for Opus might need more guidance for Haiku.

**Gotchas are the highest-signal content.** The most valuable part of many skills is the list of non-obvious failure points -- things the agent gets wrong by default. Build a gotchas section early and grow it as you observe failures. One targeted gotcha prevents more errors than a page of general instructions. Focus on information that breaks the agent's default reasoning, not on restating what it already knows.

**Conciseness.** Aim to keep SKILL.md concise (500 lines is a good guideline, not a hard limit). Use progressive disclosure -- split detailed content into separate files loaded on-demand. Every instruction added dilutes the weight of every other instruction, in the skill and in others.

**Appropriate Degrees of Freedom.** Match specificity to the task's fragility:

- **High freedom** (text instructions): Multiple valid approaches, context-dependent decisions
- **Medium freedom** (pseudocode/parameterized scripts): Preferred pattern exists, some variation acceptable
- **Low freedom** (exact scripts, no parameters): Fragile operations where consistency is critical

Think of it as a path: an open field (many valid routes, give general direction) vs. a narrow bridge over a cliff (one safe way, provide exact guardrails).

## Anatomy of a Skill

```text
skill-name/
├── SKILL.md              # Required: instructions + metadata
├── scripts/              # Optional: executable utilities
├── references/           # Optional: detailed docs loaded on-demand
└── assets/               # Optional: templates, schemas, data files
```

### SKILL.md

Every SKILL.md consists of two parts:

- **Frontmatter** (YAML): Required metadata. The `description` field is the PRIMARY triggering mechanism -- it is what the agent reads to decide whether to activate the skill. Include ALL "when to use" information in the description, NOT in the body. The body is only loaded after triggering, so "When to Use This Skill" sections in the body are not helpful.
- **Body** (Markdown): Instructions loaded AFTER the skill triggers.

Write the body in imperative/infinitive form ("Extract text", "Run the script", not "Extracting text" or "You should extract text").

#### Frontmatter Fields

Only `name` + `description` are required, and they are the **portable core** — the entire Agent Skills standard (the form Cursor, Codex, and other tools read) is just these two. Everything below is optional; the Claude Code superset (next subsection) adds more.

| Field           | Required | Constraints                                                              |
| --------------- | -------- | ------------------------------------------------------------------------ |
| `name`          | Yes      | 1-64 chars. Lowercase alphanumeric + hyphens. Must match directory name. No consecutive hyphens, no leading/trailing hyphens. |
| `description`   | Yes      | 1-1024 chars. What it does + when to use it + trigger terms.             |
| `license`       | No       | License name or reference to bundled file.                               |
| `compatibility` | No       | Max 500 chars. Environment requirements.                                 |
| `metadata`      | No       | Arbitrary key-value pairs for additional info.                           |
| `allowed-tools` | No       | Pre-approved tools the skill may use. (Experimental)                     |

##### Claude Code Frontmatter Superset

Claude Code reads the portable core **plus** these optional fields. Because custom commands merged into skills, the same fields apply to `commands/*.md` files too (see the `command-crafting` skill):

| Field | Purpose |
| --- | --- |
| `when_to_use` | Extra trigger phrases, appended to `description`. **Combined `description` + `when_to_use` is truncated at 1,536 chars in the skill listing** — put the key use case first. |
| `disable-model-invocation` | `true` = only the user can invoke (`/name`); the description leaves model context. Use for side-effecting actions (`/deploy`, `/commit`). |
| `user-invocable` | `false` = hide from the `/` menu (background knowledge Claude loads but users don't call). |
| `allowed-tools` | Tools pre-approved (no prompt) while active. Does NOT restrict — every tool stays callable. |
| `paths` | Glob patterns that scope auto-activation to matching files (same syntax as path-specific rules). |
| `context: fork` + `agent` | Run the skill body as the prompt for a forked subagent (`agent:` picks the type, e.g. `Explore`). Only meaningful for skills with an explicit task, not pure guidelines. |
| `model`, `effort` | Override model / effort while the skill is active (current turn only). |
| `argument-hint`, `arguments` | Autocomplete hint + named positional args for `$name` substitution. |
| `hooks`, `shell` | Lifecycle hooks scoped to the skill; `bash` (default) or `powershell` for `` !`cmd` `` blocks. |

These are Claude-Code extensions, **not** part of the portable standard — keep them out of skills meant to run cross-tool, or isolate them behind clear headings. Full field reference + interactions: [references/schema.md](references/schema.md).

#### Directory Name Constraints

The directory name is the skill's identity (Claude Code infers the name from it):

- Lowercase letters, numbers, and hyphens only
- No consecutive hyphens (`--`), no leading/trailing hyphens
- If `name` field is present, it must match the directory name
- Prefer gerund form (`processing-pdfs`) or noun phrases (`pdf-processing`)
- Avoid vague names: `helper`, `utils`, `tools`
- Reserved words `anthropic` and `claude` are not allowed anywhere in the name

--> See [references/artifact-naming.md](references/artifact-naming.md) for naming conventions across all artifact types.

#### Description Best Practices

The description is not a summary -- it is a trigger specification. Claude uses it to decide whether to activate the skill from potentially hundreds of candidates. Write in third person (injected into the system prompt). Focus on:

- **What the skill does**: the capability it provides
- **When to trigger it**: specific contexts, tasks, or user phrasings that should activate it
- **Key terms**: domain vocabulary the agent should match against

Avoid vague descriptions ("Helps with documents"). Include terms that challenge the agent's default reasoning -- if the agent would handle the task differently without the skill, the description should signal that difference.

### Bundled Resources

- **`scripts/`** -- Executable code, run via Bash (not loaded into context)
- **`references/`** -- Documentation loaded on-demand (one level deep, TOC for 100+ lines)
- **`assets/`** -- Files used in output (templates, images, boilerplate), not loaded into context

Run `scripts/init_skill.py` to scaffold a new skill with detailed guidance and examples for each resource type.

### What to Not Include

A skill should only contain essential files. Do NOT create:

- INSTALLATION_GUIDE.md, QUICK_REFERENCE.md, CHANGELOG.md
- Setup/testing procedures, user-facing documentation
- Files about the process that went into creating the skill

**Note on README.md**: The Agent Skills standard does not include README.md in skills. In this plugin ecosystem, each skill has a README.md as a human-facing catalog entry (not loaded into the agent's context). This is a project convention, not part of the standard. README section order: When to Use, Activation, Skill Contents, Quick Start (optional), Testing (optional), Related Skills (optional).

### Storage Locations

- **Personal**: `~/.claude/skills/` (user-specific)
- **Project**: `.claude/skills/` (shared via git)
- **Plugin**: `~/.claude/plugins/cache/<marketplace>/<plugin>/<version>/skills/` (installed via plugin)

## Progressive Disclosure

Three tiers of context loading:

1. **Metadata** (~100 tokens): `name` + `description` loaded at startup for all skills
2. **Instructions** (<5000 tokens recommended): Full SKILL.md body loaded on activation
3. **Resources** (as needed): Referenced files loaded only when required

### Skill Content Lifecycle
<!-- last-verified: 2026-05-25 -->

Two facts about Claude Code's runtime change how you write a skill body:

- **An invoked skill stays in context for the rest of the session.** Claude Code injects the rendered `SKILL.md` once and does not re-read it on later turns. Write **standing instructions** that hold across a task, not one-time steps that read as already-done after the first turn.
- **The skill *listing* (every skill's `name` + `description`) is always-loaded**, budgeted at ~1% of the model's context window. On overflow, the least-used descriptions drop first (`/doctor` shows this). This is why the description must be high-signal and why `description` + `when_to_use` is capped at 1,536 chars.
- **Auto-compaction re-attaches the most recent invocation of each skill**, keeping the first ~5,000 tokens of each within a combined ~25,000-token budget (newest first); older skills may drop entirely. Keep load-bearing instructions near the top of the body.

### Design Patterns

#### Pattern 1: High-level guide with references

```markdown
# PDF Processing

## Quick start
Extract text with pdfplumber: [code example]

## Advanced features
- **Form filling**: See [FORMS.md](FORMS.md) for complete guide
- **API reference**: See [REFERENCE.md](REFERENCE.md) for all methods
```

#### Pattern 2: Domain-specific organization

Organize by domain when a skill covers multiple areas. The agent only reads the relevant domain file:

```text
bigquery-skill/
├── SKILL.md (overview and navigation)
└── references/
    ├── finance.md, sales.md, product.md, marketing.md
```

#### Pattern 2b: Language/context-specific references

When a skill provides cross-cutting knowledge (e.g., testing strategy, API design), keep the SKILL.md body language-agnostic and place language-specific or context-specific content in separate reference files. The agent loads only the reference relevant to the active project:

```text
testing-strategy/
├── SKILL.md (language-agnostic strategy)
└── references/
    ├── python-testing.md     # pytest, hypothesis, coverage
    ├── typescript-testing.md  # vitest, jest, type-safe mocks (future)
    └── rust-testing.md        # cargo test, proptest (future)
```

The SKILL.md lists all available references as satellite files. New language support is added by creating a reference file — no changes to the core SKILL.md. Use illustrative examples from specific languages (e.g., `tmp_path` in pytest) but frame them as instances of a general principle, not as the only valid approach.

#### Pattern 3: Conditional details

Show basic content, link to advanced:

```markdown
## Creating documents
Use docx-js. See [DOCX-JS.md](DOCX-JS.md).

## Editing documents
For simple edits, modify XML directly.
**For tracked changes**: See [REDLINING.md](REDLINING.md)
```

--> See [references/plugin-and-troubleshooting.md](references/plugin-and-troubleshooting.md) for plugin-specific progressive disclosure mechanics (base path injection, permission caveats, debugging).

## Skill Creation Process

Creating a skill involves these steps:

1. Understand the skill with concrete examples
2. Plan reusable contents
3. Create the skill directory and SKILL.md
4. Write the skill content
5. Validate
6. Iterate based on real usage

Follow these steps in order, skipping only with clear reason.

**Evaluation comes first, not last.** Before writing extensive prose, establish *where the agent fails without the skill* and capture ≥3 realistic scenarios — including **negative** cases that must not trigger it — see [evaluation-first authoring](references/context-engineering-foundations.md#evaluation-first-authoring). Steps 1–2 feed those scenarios; Step 6 iterates against them.

### Step 1: Understand the Skill with Concrete Examples

Skip only when usage patterns are already clearly understood.

Identify which [skill category](references/skill-categories.md) the skill falls into -- this guides structural decisions (scripts vs. references vs. assets, verification approach, content type).

Understand concrete examples of how the skill will be used. Ask questions like:

- "What functionality should this skill support?"
- "Can you give examples of how it would be used?"
- "What would a user say that should trigger this skill?"

Avoid overwhelming -- start with the most important questions and follow up as needed. Conclude when there is a clear sense of the functionality to support.

### Step 2: Plan Reusable Contents

Analyze each example by:

1. Considering how to execute it from scratch
2. Identifying what scripts, references, and assets would help when executing repeatedly

Example analyses:

- Rotating PDFs requires rewriting the same code each time --> `scripts/rotate_pdf.py`
- Building webapps needs the same boilerplate --> `assets/hello-world/` template
- Querying BigQuery requires rediscovering schemas --> `references/schema.md`

### Step 3: Create the Skill

Run the initializer to scaffold the skill directory:

```bash
python scripts/init_skill.py <skill-name> --path <output-directory>
```

This creates the directory with a SKILL.md template containing the required frontmatter (`name`, `description`) and a minimal body with TODO placeholders. Complete the TODOs and add resource directories (`scripts/`, `references/`, `assets/`) as needed.

### Step 4: Write the Skill Content

Start with the reusable resources identified in Step 2 (scripts, references, assets). Test added scripts by running them. Then update the SKILL.md body.

Consult these guides for content patterns:

- **Output format requirements**: See [references/output-patterns.md](references/output-patterns.md) for template and examples patterns
- **Multi-step processes**: See [references/workflows.md](references/workflows.md) for sequential and conditional patterns
- **Content type selection**: See [references/content-and-development.md](references/content-and-development.md) for choosing between scripts, worked examples, and prose instructions

### Step 5: Validate and Package

Package the skill into a distributable `.skill` file (validates automatically before packaging):

```bash
python scripts/package_skill.py <path/to/skill-folder> [output-directory]
```

To validate without packaging, run `scripts/validate.py` directly. Then check the deployment checklist at the end of this document.

**Cross-reference validation.** Run `scripts/validate_references.py` to validate intra-repo Markdown links across the canonical skill/agent/rule/command/docs surface. Stdlib-only, no dependencies. Modes: `--file <path>` (single file) or `--all` (default include set). Per-class severity: broken relative paths and broken `.md` anchors are `FAIL`; ambiguous anchor slugs are `WARN`. Exit codes: `0` = clean (or only `WARN` under `--warn-only`), `1` = at least one `FAIL`, `2` = script error. Modifiers: `--warn-only` downgrades all `FAIL`s to `WARN` (exploratory runs); `--strict` upgrades all `WARN`s to `FAIL` (CI). Ignore mechanisms: inline `<!-- validate-references:ignore -->` suppresses links on that line; frontmatter `validate-references: off` suppresses all findings in the file.

### Step 6: Iterate

Use the skill on real tasks. Observe behavior -- where it struggles, succeeds, or makes unexpected choices.

**Author-tester workflow**: One instance (author) writes/refines the skill. Another instance (tester) uses it on real tasks in a fresh session. Grade outcomes, not paths -- agents may find valid approaches you did not anticipate.

**Observe navigation patterns**: Watch how the agent uses the skill. Unexpected file access order means structure is not intuitive. Missed references means links need to be more explicit. Overreliance on one file means content should be in SKILL.md.

--> See [references/content-and-development.md](references/content-and-development.md#evaluation-driven-development) for the full evaluation-driven development process.

## Skill Composition

Skills can reference each other by name when dependencies exist:

```markdown
For database schema conventions, see the `data-modeling` skill.
```

Keep cross-references lightweight -- name the skill, describe why to consult it. Avoid deep dependency chains between skills. The agent resolves these references through its own discovery mechanism.

## Skill Categories

Skills cluster into recurring archetypes. When creating a skill, consider which category it falls into -- this shapes its structure, content type, and testing approach.

--> See [references/skill-categories.md](references/skill-categories.md) for the nine categories with descriptions and structural guidance for each.

## Cross-Agent Portability
<!-- last-verified: 2026-05-25 -->

The [Agent Skills standard](https://agentskills.io) is adopted across the ecosystem — Claude Code, Cursor, VS Code/Copilot, OpenAI (ChatGPT + Codex CLI), Gemini CLI, Roo Code, Goose, Amp, and others — making `SKILL.md` a genuinely cross-tool format, not a Claude-only one. This is why the portable core (`name` + `description`) is worth preserving even when authoring for Claude Code.

**What's portable**: SKILL.md format, directory structure, progressive disclosure model.

**What's tool-specific**: `allowed-tools` names, MCP tool references, `compatibility` values, Claude Code extensions (`context: fork`, `disable-model-invocation`).

Keep SKILL.md body in standard markdown. Isolate tool-specific instructions behind clear headings.

--> See [references/cross-agent-portability.md](references/cross-agent-portability.md) for discovery paths per tool, portable vs. tool-specific breakdown, and skills vs. project instruction files.

## Resources

- [Agent Skills Specification](https://agentskills.io/specification) -- the portable open standard
- [Authoring Best Practices](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices) -- Anthropic-official
- [Claude Code Skills reference](https://code.claude.com/docs/en/skills) -- the Claude Code superset (merged commands, invocation control, dynamic context injection)
- [Example Skills](https://github.com/anthropics/skills) -- Anthropic's official reference implementations
- Context-engineering sources (context rot, attention budget, eval-first): see [references/context-engineering-foundations.md](references/context-engineering-foundations.md#context-engineering-sources)

## Checklist

Before deploying a skill:

### Core Quality

- [ ] `name` present, matches directory name (lowercase, hyphens only, 1-64 chars)
- [ ] Third-person description with specific trigger terms (what + when), 1-1024 chars
- [ ] SKILL.md is concise (aim for ~500 lines, use progressive disclosure for longer content)
- [ ] One-level-deep file references
- [ ] Consistent terminology throughout
- [ ] Concrete examples provided
- [ ] Progressive disclosure (metadata --> instructions --> resources)
- [ ] Gotchas section for common failure points (if applicable)
- [ ] No time-sensitive information (use collapsible "Old patterns" sections for deprecated content)
- [ ] No duplication between SKILL.md and reference files
- [ ] Writing uses imperative/infinitive form

### Code and Scripts (if applicable)

- [ ] Scripts handle errors explicitly (solve, do not punt)
- [ ] No magic constants -- all values justified
- [ ] Required packages listed and verified
- [ ] Forward slashes in all paths
- [ ] Validation/verification for critical operations

### Testing

- [ ] At least three evaluation scenarios created
- [ ] Tested across target models
- [ ] Real-world scenario validation
