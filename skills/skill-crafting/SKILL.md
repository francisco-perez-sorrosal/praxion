---
name: skill-crafting
description: "Authoring Agent Skills for Claude Code, Cursor, and compatible agents: invocation modes, SKILL.md frontmatter, eval-first authoring. Triggers: creating new skills, updating or modernizing existing skills, converting memory files to skills, debugging skill activation, skill architecture and best practices, user-invoked skills, argument-hint, argument substitution, converting command files to skills, skill evals, description optimization."
allowed-tools: [Read, Write, Edit, Glob, Grep, Bash]
compatibility: Claude Code
staleness_sensitive_sections:
  - "Invocation Modes: Who Invokes, Who Reads"
  - "Skill Content Lifecycle"
  - "Cross-Agent Portability"
  - "Claude Code Frontmatter Superset"
  - "Arguments and Dynamic Context"
  - "Plugin Eval Case Layout"
  - "Trigger Cases for Plugin Eval"
  - "Discovery and Live Reload"
  - "Permission Management"
  - "Context-Engineering Sources"
---

# Skill Creator

Guide for creating effective Agent Skills. Official specification at [agentskills.io](https://agentskills.io). Authoring guidance at [Anthropic's best practices](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices).

**Reference pages** (loaded on demand, each one hop from here):

- [references/context-engineering-foundations.md](references/context-engineering-foundations.md) -- the shared "why" behind every `*-crafting` skill (context rot, attention budget, progressive disclosure, eval-first); read once
- [references/user-invoked-skills.md](references/user-invoked-skills.md) -- skills a person types as `/name`: description length, `argument-hint`, argument substitution, converting a command file
- [references/description-optimization.md](references/description-optimization.md) -- writing a description that triggers, and the measured tuning loop
- [references/evaluating-skills.md](references/evaluating-skills.md) -- the open-standard `evals/evals.json` loop and the `claude plugin eval` case layout
- [references/skill-categories.md](references/skill-categories.md) -- nine skill archetypes and the structure each implies
- [references/content-and-development.md](references/content-and-development.md) -- content types, gotchas, output templates, workflow patterns, structuring content across files
- [references/scripts-for-agents.md](references/scripts-for-agents.md) -- when to bundle a script and the contract an agent-facing script keeps
- [references/schema.md](references/schema.md) -- every frontmatter field, its constraints, and what the validator checks
- [references/artifact-naming.md](references/artifact-naming.md) -- naming conventions for all artifact types
- [references/plugin-and-troubleshooting.md](references/plugin-and-troubleshooting.md) -- plugin mechanics, discovery and reload, permissions, troubleshooting
- [references/cross-agent-portability.md](references/cross-agent-portability.md) -- discovery paths and field support per host, skills vs. project instruction files

## Invocation Modes: Who Invokes, Who Reads
<!-- last-verified: 2026-10-11 -->

Decide first who may invoke the skill: that decides who reads its description, and so how long it may be and what it must say.

| Mode | Key(s) | Who invokes | Description in the always-loaded listing |
| --- | --- | --- | --- |
| Default | none | the user (`/name`) and the model | yes |
| User-only | `disable-model-invocation: true` | the user only | no -- it shows only in the `/` menu |
| Hidden from the menu | `user-invocable: false` | the model only | yes |
| Forked | `context: fork`, with `agent` and `background` | as the keys above set it | as the keys above set it |

- **User-only** also keeps the skill from being preloaded into subagents and from running when a scheduled task names it.
- **Hidden from the menu** suits background knowledge the model loads but nobody types; it does not stop the model, so add `disable-model-invocation: true` to stop both.
- **Forked** runs the rendered body as the prompt of a new subagent of the `agent` type (`general-purpose` when omitted); the subagent does not see the conversation. `background: false` waits for its result in the invoking turn instead of running it in the background (the default). Fork only a skill that carries an explicit task, never pure guidelines.

### Writing for That Reader

- **A model-invocable description is a trigger specification.** Write it in the third person (it is injected into the system prompt) and state when to use the skill, focused on the user's intent -- what the person is trying to do and the words they would use -- rather than the skill's mechanics.
- **Never a summary of the procedure.** The body carries the procedure; a summary in the listing tempts the agent to act on it without loading the body.
- **Put all "when to use" information in the description, none in the body**: the body loads only after the skill triggers.
- **A user-only description is one plain line.** The person reading it in the `/` menu has already chosen the skill.
- **Guard every side-effecting skill as user-only** (deploy, commit, release, anything that writes outside the working tree): the model should never fire it on a guess.

Tuning a description against measured trigger rates: [references/description-optimization.md](references/description-optimization.md). Slash-invoked skills in depth: [references/user-invoked-skills.md](references/user-invoked-skills.md).

## Creating a Skill: the Eval-First Loop

Write a skill against failures you observed, not ones you imagine, and measure it against the agent working without it.

1. **Record the failures.** Run the agent on representative tasks without the skill and write down where it goes wrong or asks for context. Identify the skill's [category](references/skill-categories.md); it shapes scripts vs. references vs. assets.
2. **Write the scenarios.** Turn those failures into at least three evaluation scenarios, including near-miss queries that should not trigger the skill.
3. **Write the smallest body that closes the recorded gaps.** Scaffold with `python scripts/init_skill.py <skill-name> --path <output-directory>`, then add only what a recorded failure calls for. Content patterns: [references/content-and-development.md](references/content-and-development.md).
4. **Validate** (see [Validate and Package](#validate-and-package)).
5. **Re-run the scenarios against the no-skill baseline and iterate.** Keep a change only when the scenarios improve. For a plugin-shipped skill, `claude plugin eval` runs the cases with and without the plugin and reports the difference. Formats and grading: [references/evaluating-skills.md](references/evaluating-skills.md).

Iterate with two instances: one (author) refines the skill, a fresh one (tester) uses it on real tasks; grade outcomes, not paths. The why behind eval-first: [references/context-engineering-foundations.md](references/context-engineering-foundations.md#evaluation-first-authoring).

## Degrees of Freedom and Gotchas First

A skill shares the context window with the system prompt, the conversation, every other skill's listing entry and the request, so each token must change what the agent does. Include only what the model does not already know -- but give concrete examples and explicit decision criteria, which carry weaker models without burdening stronger ones; test with every model you plan to use.

**Match specificity to the task's fragility:**

- **Prose** for open choices -- several approaches are valid and context decides (a code review).
- **A parameterized pattern** (pseudocode, a template, a script with options) where a preferred default exists and some variation is fine.
- **Exact commands** where one safe path exists -- a narrow bridge over a cliff (a migration that must run in order: "run exactly this, add no flags").

**Offer one default with an escape hatch, not a menu.** "Use pdfplumber; for scanned PDFs needing OCR, use pdf2image with pytesseract" beats a list of five libraries.

**Lead the body with gotchas.** The highest-signal content is the list of non-obvious failure points the agent gets wrong by default. Start the list from the failures recorded in the eval loop and grow it from failures you observe in use; one targeted gotcha prevents more errors than a page of general guidance. Format: [references/content-and-development.md](references/content-and-development.md#gotchas-sections).

**Put load-bearing instructions near the top of the body.** After compaction only the start of an invoked skill survives (see [Skill Content Lifecycle](#skill-content-lifecycle)), and every added instruction dilutes the others.

Write the body in imperative form ("Run the script", not "You should run the script"), with consistent terminology and no time-sensitive statements (put deprecated material in a collapsible "Old patterns" section).

## Scripts Designed for Agents

Bundle a script for deterministic work -- validation, conversion, extraction -- and for a helper the agent keeps rewriting from scratch. Do not bundle one otherwise: a step that needs judgment belongs in prose, and a one-off command belongs in the instructions.

A bundled script is run by an agent that reads its output and cannot answer a prompt, so it:

- runs without interactive prompts (every input as an argument or flag, `--help` documenting them);
- solves its error cases rather than deferring them -- an error says what was wrong and what was expected;
- justifies its constants -- no unexplained timeout or retry count.

Say in the instructions whether the agent should run the script (the usual case; only its output enters context) or read it as reference. The full contract -- output streams, exit codes, re-runnable and bounded output, dependencies -- is in [references/scripts-for-agents.md](references/scripts-for-agents.md).

## Skill Content Lifecycle
<!-- last-verified: 2026-10-11 -->

Claude Code's runtime decides what a body may rely on. Each fact below shapes how to write it:

- **The listing is always loaded, under a budget.** Every model-invocable skill's name and description sits in context on every turn; the listing's budget scales at 1% of the model's context window, and on overflow the least-used skills lose their descriptions first (`/doctor` estimates the cost).
- **Description plus `when_to_use` is truncated at 1,536 characters** in the listing, whatever the budget -- put the key use case first.
- **An invoked body stays in context for the rest of the session and is not re-read.** Write standing guidance that holds across the whole task ("run the tests after every edit"), not one-time steps that read as done after the first turn.
- **Compaction keeps only the start of a skill.** After compaction Claude Code re-attaches the most recent invocation of each skill, keeping its first 5,000 tokens, within a combined 25,000 tokens for all of them, newest first; older skills can drop out entirely.
- **Plugin skills are discovered when a session starts** (and on `/reload-plugins`), from the registered plugin root. A skill added or built mid-session elsewhere -- for example in a worktree -- is invisible until a fresh session started on that tree (`claude --plugin-dir <path>`).
- **An unknown frontmatter key is ignored silently.** A misspelled key (`disable-model-invokation`) draws no error and has no effect; run the validator.
- **Per-skill override settings do not apply to plugin skills.** `skillOverrides` changes how a personal or project skill is listed; manage a plugin's skills through `/plugin`.

Discovery and reload by location: [references/plugin-and-troubleshooting.md](references/plugin-and-troubleshooting.md#discovery-and-live-reload).

## Anatomy and Layout

```text
skill-name/
├── SKILL.md              # Required: metadata + instructions
├── scripts/              # Optional: executable utilities
├── references/           # Optional: detailed docs loaded on demand
├── contexts/             # Optional: runnable language/runtime variants (one per session)
└── assets/               # Optional: templates, schemas, data files
```

`SKILL.md` has two parts: YAML **frontmatter** (`name` and `description` required; every field, its constraints and the Claude Code superset in [references/schema.md](references/schema.md)) and a Markdown **body** loaded only after the skill triggers. Keep the body under 500 lines and move depth into references.

### Bundled Resources

- **`scripts/`** -- executable code, run via Bash; only its output enters context (see [Scripts Designed for Agents](#scripts-designed-for-agents)).
- **`references/`** -- documentation loaded on demand. Link every reference directly from `SKILL.md` (one hop; never a reference reachable only through another), and open any reference over 100 lines with a contents list so a partial read still shows its scope.
- **`contexts/`** -- runnable language/runtime variants (`contexts/python.md`, `contexts/typescript.md`), mutually exclusive within a session. Content that compiles, runs or installs goes here; content whose claims are language-agnostic goes in `references/`. A spec-permitted Praxion extension; the full decision rule, naming and extension protocol: [Pattern 2c](references/content-and-development.md#pattern-2c-polyglot-skill-mutually-exclusive-contexts).
- **`assets/`** -- files used in output (templates, images, boilerplate), never loaded into context.

Ways to split content across files (high-level guide, domain split, per-language references, conditional details): [references/content-and-development.md](references/content-and-development.md#structuring-content-across-files).

### Naming

The directory name is the skill's identity, and `name` must match it: lowercase letters, digits and hyphens, 1-64 characters, no leading, trailing or consecutive hyphens, and neither `anthropic` nor `claude` anywhere in it. Prefer a gerund (`processing-pdfs`) or noun phrase (`pdf-processing`); avoid vague names (`helper`, `utils`). Conventions across artifact types: [references/artifact-naming.md](references/artifact-naming.md).

### What Not to Include

Only essential files: no INSTALLATION_GUIDE.md, QUICK_REFERENCE.md or CHANGELOG.md, no setup or testing procedures, no notes on how the skill was made. **README.md** is not part of the standard; in this plugin most skills carry one as a human-facing catalog entry (user-invoked workflow skills carry none), never loaded into the agent's context (sections: When to Use, Activation, Skill Contents, then optional Quick Start, Testing, Related Skills).

### Storage Locations and Composition

- **Personal**: `~/.claude/skills/` (user-specific)
- **Project**: `.claude/skills/` (shared via git)
- **Plugin**: `~/.claude/plugins/cache/<marketplace>/<plugin>/<version>/skills/` (installed via plugin)

A skill may name another when it depends on it ("for schema conventions, see the `data-modeling` skill"): name the skill and say why to consult it, and keep such chains shallow.

## Validate and Package

```bash
python scripts/validate.py <path/to/skill-folder>   # one skill
python scripts/validate.py --all                    # every skills/<name>/ under the repo root
python scripts/package_skill.py <path/to/skill-folder> [output-directory]
```

The validator reports **errors** (the skill is malformed: missing or invalid `name` or `description`, a field outside the accepted set) and **warnings** (an authoring hazard: a body over 500 lines, an empty or unquoted `argument-hint`, a multi-line user-only description, declared `arguments` with no placeholder). Only errors fail the run. The packager validates first and builds a distributable `.skill` file.

`scripts/validate_references.py --all` checks intra-repo Markdown links and anchors across skills, agents, rules and docs (stdlib only); `--help` lists its modes (`--all`, `--file`, `--strict`, `--warn-only`), and the skill's [README.md](README.md) its per-class severities, exit codes and ignore markers.

## Cross-Agent Portability
<!-- last-verified: 2026-10-11 -->

`SKILL.md` is an open standard ([agentskills.io](https://agentskills.io)) read by Claude Code, Cursor, VS Code / Copilot, Codex, Gemini CLI and many others, so its portable core is worth keeping even when writing for Claude Code alone.

- **`name` and `description` are read by every host**, along with the directory layout and progressive disclosure.
- **Cursor** also reads `metadata`, `paths` and `disable-model-invocation`; **Codex** reads only `name` and `description` from the frontmatter, keeping invocation policy and UI metadata in a sibling `agents/openai.yaml`.
- **An upload to claude.ai rejects any field outside `name`, `description`, `license`, `compatibility`, `metadata` and `allowed-tools`**, so a skill meant for upload carries none of the Claude Code extensions.
- **Claude Code ignores a key it does not recognize**, so another host's field does it no harm -- and a misspelled Claude Code key fails silently.

Keep the body in standard Markdown and put tool-specific instructions behind a clear heading. Field-by-host matrix and discovery paths: [references/cross-agent-portability.md](references/cross-agent-portability.md).

## Resources

- [Agent Skills Specification](https://agentskills.io/specification) -- the portable open standard
- [Authoring Best Practices](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices) -- Anthropic-official
- [Claude Code Skills reference](https://code.claude.com/docs/en/skills) -- the Claude Code superset (invocation control, dynamic context, lifecycle)
- [Example Skills](https://github.com/anthropics/skills) -- Anthropic's official reference implementations
- Context-engineering sources (context rot, attention budget, eval-first): [references/context-engineering-foundations.md](references/context-engineering-foundations.md#context-engineering-sources)

## Checklist

Before shipping a skill, confirm each item:

- [ ] `name` matches the directory name (lowercase, hyphens, 1-64 characters)
- [ ] The description is written for its reader: a model-invocable one in the third person, on user intent, never a summary of the procedure; a user-only one in one plain line
- [ ] Every side-effecting skill is user-only (`disable-model-invocation: true`)
- [ ] `SKILL.md` is under 500 lines, with every reference page linked directly (one hop)
- [ ] Every reference over 100 lines opens with a contents list
- [ ] A gotchas section leads the body, grown from observed failures
- [ ] Load-bearing instructions sit near the top of the body and hold as standing guidance
- [ ] At least three evaluation scenarios exist, including should-not-trigger cases, run against a no-skill baseline
- [ ] Every bundled script meets the agent-facing contract: non-interactive, solves its errors, justifies its constants
- [ ] Each section stating a drift-prone external fact is cataloged for staleness and marked with a `last-verified` date
- [ ] Consistent terminology, no time-sensitive statements, forward slashes in every path
- [ ] `scripts/validate.py` reports no error
