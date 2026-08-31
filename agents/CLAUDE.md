# Agents

Agent definitions for the software development pipeline. Each agent runs in its own context window as an autonomous subprocess.

## Conventions

- Each agent is a single `.md` file with YAML frontmatter (`description`, `tools`, `skills`, optional `model`, `color`)
- Flat structure — no subdirectories; one file per agent
- `description` drives delegation — Claude decides when to spawn based on this field, so it must be precise and differentiated
- Agents cannot spawn other agents; they can only recommend spawning in their output
- Skills listed in the `skills:` frontmatter are injected into the agent's context — agents do not inherit skills from the parent

## Registration

After adding or removing an agent, update `.claude-plugin/plugin.json` under the `agents` array. Agents require **explicit file paths** — directory globs are not supported.

## Modifying Agents

Load the `agent-crafting` skill before creating or modifying agent definitions. It covers prompt structure, tool selection, and frontmatter conventions.

## Pipeline Context

Agents communicate through shared documents in `.ai-work/` (ephemeral) and `.ai-state/` (persistent). See the `swe-agent-coordination-protocol` rule for pipeline ordering and boundary discipline.

## Architect Invocation Modes

The `systems-architect` agent supports three invocation modes, signaled by an explicit `Mode: <name>` directive in the spawn prompt (no frontmatter, no marker file). Phase 1 (Input Assessment) detects the directive on intake and logs the mode to `PROGRESS.md`. When updating `agents/systems-architect.md`, preserve compatibility with all three modes.

| Mode | Trigger | Phase 2.5 behavior | Output |
|---|---|---|---|
| `feature` (default — no directive needed) | Standard/Full pipeline with feature scope | Always runs | `SYSTEMS_PLAN.md` + optional `PRE_REFACTOR_PLAN.md` |
| `baseline-audit` | Onboarding Phase 8 (`skills/onboard-project`, capability `arch`); `new` mode's seed pipeline (Phase 0s) invokes the same agent with full feature scope in greenfield mode (baseline-audit is the existing-project counterpart) | SKIP (no feature → no pre-refactor) | `.ai-state/DESIGN.md` + `docs/architecture.md`; NO `SYSTEMS_PLAN.md`, NO `PRE_REFACTOR_PLAN.md` |
| `post-refactor-adaptation` | Orchestrator re-invocation after a pre-refactor mini-pipeline completes AND a `PRE_REFACTOR_PLAN.md` exists under the task slug's `.ai-work/<task-slug>/` | SKIP (recursion guard — prevents a second mini-pipeline) | Updated `SYSTEMS_PLAN.md` (re-read Components / Data Flow / Interfaces against the refactored code); `[CONSUMED]` marker appended to the existing `PRE_REFACTOR_PLAN.md` |

**Paired site — update both in the same commit.** The `Output` column above is authoritative on *whether* a mode writes a `SYSTEMS_PLAN.md`; `agents/systems-architect.md § Phase 10` is the single source of truth for *which `##` sections that document must carry*. Neither restates the other. **The section schema binds the path, not the author**: anything written to `.ai-work/<task-slug>/SYSTEMS_PLAN.md` uses those headings, including a plan the orchestrator authors directly in a no-fan-out run where the architect is never spawned. A bespoke schema under the canonical filename is a silent handoff failure — downstream consumers grep for the headings and report the document empty.

### Anti-instructions per mode

**`baseline-audit`**: no `SYSTEMS_PLAN.md`, no `PRE_REFACTOR_PLAN.md`, no Phase 2.5, no invented components (every diagram node + table row must be code-verified), no L2 detail, no source edits.

**`post-refactor-adaptation`**: no Phase 2.5 (one-pass recursion bound — same hard rule as baseline-audit mode), no second `PRE_REFACTOR_PLAN.md` for the same task slug, no spawning another mini-pipeline. The architect re-reads research findings + refactored codebase, re-runs Phase 1 + Phase 2, then proceeds through Phases 3–10 against the refactored shape; on completion, the orchestrator (or the architect) flips remaining `in-flight` tech-debt rows to `resolved` and emits the `[CONSUMED]` marker on the `PRE_REFACTOR_PLAN.md`.

## Discipline Consultant Directive

The `discipline-consultant` agent carries no discipline of its own — it is parameterized at spawn time by an explicit `Discipline: <name>` directive in the spawn prompt (no frontmatter, no marker file; the same signaling mechanism as the architect's `Mode:` directive above). Phase 1 resolves the directive before any other work and logs the resolved discipline on the first `PROGRESS.md` line. When updating `agents/discipline-consultant.md`, preserve the resolution contract below.

| Directive | Required | Resolves against | Effect once resolved |
|---|---|---|---|
| `Discipline: <name>` | Yes — exactly one per instance | Exact match on the `discipline` column of `skills/multi-perspective-analysis/references/discipline-registry.md` | The matched row's `binds-to` skill(s) load at runtime through the `Skill` tool (never through `skills:` frontmatter); `challenge-obligations` become the consult's checklist; `difficulty-hint` drives the convener's model routing |
| `Task slug: <slug>` | Yes | — | Scopes every read and write to `.ai-work/<task-slug>/`; the fragment lands at `CONSULT_<discipline>.md` |
| `Round: 0 \| 1` | No — default is 0-then-1 in a single spawn | — | Round 0 (independent reading, no draft access) always precedes Round 1 (challenge) |

**The registry is the complete roster.** A discipline absent from that table does not exist, and `<name>` is a registry key rather than a free-text label. Adding a discipline is one registry row plus at most one new skill file — never a new agent file, manifest entry, consultant `tools:`/`skills:` entry, or always-loaded byte.

### When the directive does not resolve

An unresolvable directive is a hard stop, not a degraded run. If `<name>` matches no row, if the registry itself cannot be read, or if the matched row's `binds-to` skill exists **nowhere** — not in the installed plugin and not in the repository — the consultant writes no challenges and returns `[BLOCKED]` naming the unresolvable value and which of those failures occurred. A silently degraded consult is worse than no consult, because it looks like coverage.

**One exception, and it must be declared.** When the `Skill` tool fails but the bound skill *is* present at `skills/<name>/SKILL.md`, the consultant proceeds on that file via `Read` and states the fallback prominently. The content is identical; only the mechanism differs. This is the ordinary signature of a skill authored more recently than the installed plugin — routine while self-hosting, impossible in a managed project where the skill ships with the plugin that resolves it. An **undeclared** fallback is the silent degradation this rule forbids; a declared one lets the convener judge staleness instead of discovering it later.

### Anti-instructions

Never improvise a discipline — no plausible-sounding invention, no substituting a neighbouring one, no proceeding from memory when the registry is unreadable. Never widen one instance to two disciplines: a second discipline is a second spawn, and concurrent instances never read each other's fragments. Never name a discipline in an always-loaded surface (a `paths:`-less rule, a `CLAUDE.md`) — the registry row is the only roster, and naming disciplines elsewhere re-imposes the per-discipline structural cost the registry exists to remove. Never let the consultant disposition its own challenges, author ADR fragments, write plan steps or production code, or write the disposition ledger — all of those belong to the convener.

### Who may convene

The orchestrator spawns; agents nominate. A pipeline agent whose stage appears in the matched row's `attaches-to` column may nominate a discipline when a signal matches that row's `fires-when` predicate, and the nomination must cite **the triggering signal and the decision at stake** — a nomination naming no decision is noise the convener has to filter. Humans may also convene directly. The consultant is adversarial-only: it challenges and never decides, so the convener adjudicates each challenge individually (`switch-now` / `defer-with-rationale` / `dismiss-with-rationale`). Each adjudication lands in **two** places, never one: written back into that challenge's own `### CH-NN` entry in the `CONSULT_<discipline>.md` fragment — the consultant leaves `Disposition:` and `Rationale:` present and empty precisely so the convener can fill them, and sentinel P07 flags an entry left unfilled — **and** recorded as one `.ai-state/CONSULT_LEDGER.md` row per challenge **plus one `.ai-state/CONSULT_COSTS.md` row per consult** (tokens, model tier, difficulty — the cost series `td-071` opened). **Before spawning, the convener also seals a prior list.** Having decided to convene, it loads the matched registry row's `binds-to` skill itself, works that row's `challenge-obligations` against the draft, and appends what that pass surfaces to `.ai-state/CONSULT_PRIORS.md` — one row per concern, or one explicit `NONE` row saying the pass surfaced none — then commits that file **before** the spawn. At Round 2 it classifies every challenge against that sealed list. The order matters: deciding to convene first, then running the lens, keeps the consults where the lens already found everything inside the series instead of quietly dropping them. The seal is what turns "would the convener have caught this anyway?" into a set difference rather than a recollection. If the convener is a pipeline agent that may not commit, it authors the rows and the orchestrator commits them before the spawn; the spawn never precedes the commit. Full round protocol: `skills/software-planning/references/coordination-details.md § Discipline-Consultant Dialogue Protocol`.
