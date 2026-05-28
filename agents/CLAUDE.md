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
| `baseline-audit` | `/onboard-project` Phase 8; `/new-project` greenfield invokes the same agent with full feature scope at gate 4b of the seed pipeline (baseline-audit is the existing-project counterpart) | SKIP (no feature → no pre-refactor) | `.ai-state/DESIGN.md` + `docs/architecture.md`; NO `SYSTEMS_PLAN.md`, NO `PRE_REFACTOR_PLAN.md` |
| `post-refactor-adaptation` | Orchestrator re-invocation after a pre-refactor mini-pipeline completes AND a `PRE_REFACTOR_PLAN.md` exists under the task slug's `.ai-work/<task-slug>/` | SKIP (recursion guard — prevents a second mini-pipeline) | Updated `SYSTEMS_PLAN.md` (re-read Components / Data Flow / Interfaces against the refactored code); `[CONSUMED]` marker appended to the existing `PRE_REFACTOR_PLAN.md` |

### Anti-instructions per mode

**`baseline-audit`**: no `SYSTEMS_PLAN.md`, no `PRE_REFACTOR_PLAN.md`, no Phase 2.5, no invented components (every diagram node + table row must be code-verified), no L2 detail, no source edits.

**`post-refactor-adaptation`**: no Phase 2.5 (one-pass recursion bound — same hard rule as baseline-audit mode), no second `PRE_REFACTOR_PLAN.md` for the same task slug, no spawning another mini-pipeline. The architect re-reads research findings + refactored codebase, re-runs Phase 1 + Phase 2, then proceeds through Phases 3–10 against the refactored shape; on completion, the orchestrator (or the architect) flips remaining `in-flight` tech-debt rows to `resolved` and emits the `[CONSUMED]` marker on the `PRE_REFACTOR_PLAN.md`.
