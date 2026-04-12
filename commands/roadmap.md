---
description: Produce a project-audited ROADMAP.md via a project-derived evaluation lens set — strengths, weaknesses, deprecations, phased improvements — through the roadmap-cartographer agent
argument-hint: "[fresh|diff|<focus-area>]"
allowed-tools: [Read, Glob, Grep, Bash(git:*), Bash(wc:*), Task]
---

Produce a project-level `ROADMAP.md` via the [roadmap-cartographer](../agents/roadmap-cartographer.md) agent. The cartographer derives a **project-specific evaluation lens set** (4–8 lenses drawn from the project's own values + domain constraints + exemplar sets: SPIRIT, DORA, SPACE, FAIR, CNCF Platform Maturity, or Custom), orchestrates one researcher per lens in parallel, synthesizes findings, and emits a user-gated roadmap matching the 10-section exemplar structure (Executive Summary, What's Working, Weaknesses, **Opportunities / Forward Lines**, Improvement Phases, Deprecation, Quality Metrics, Guiding Principles, Methodology Footer, Decision Log).

Distinct from the [roadmap-planning](../skills/roadmap-planning/SKILL.md) skill — this command audits the project and generates fresh items; `roadmap-planning` prioritizes and sequences an existing backlog.

## Modes

Three modes parsed from `$ARGUMENTS`:

| Argument | Mode | Behavior |
|----------|------|----------|
| _(none)_ | **Fresh** (default) | Full audit from scratch; produces a new `ROADMAP.md` (or replaces sections of an existing one while preserving the Decision Log per dec-032) |
| `diff` | **Incremental** | Reads existing `ROADMAP.md`, re-runs audit, surfaces deltas, updates in place; Decision Log entries preserved verbatim |
| `<anything else>` | **Focused** | Narrows the audit to the given focus area (e.g., `testing`, `observability`, `docs`); still produces the full 10-section structure but weighted toward the focus |

## Process

### 1. Parse mode

Determine the mode from `$ARGUMENTS`:

- If empty: **Fresh mode**
- If `$ARGUMENTS` equals `diff`: **Incremental mode**
- Otherwise: **Focused mode** with `$ARGUMENTS` as the focus area

### 2. Pre-flight

- Verify this is a git repository (`git rev-parse --is-inside-work-tree`). If not, ask the user whether to proceed without git archival.
- Check for uncommitted changes to `ROADMAP.md`:

  ```bash
  git status --short ROADMAP.md
  ```

  If there are unstaged edits the user did not make via a previous cartographer run, stop and surface the conflict. The cartographer owns most sections but must not destroy in-flight user edits; the user decides whether to stash, commit, or proceed.
- For **incremental** mode: verify `ROADMAP.md` exists. If not, suggest switching to fresh mode.

### 3. Generate task slug

A kebab-case task slug of the form `roadmap-YYYY-MM-DD` (or append a short suffix if today's slug already exists under `.ai-work/`).

### 4. Delegate to the cartographer

Invoke the `roadmap-cartographer` agent via the `Task` tool. Pass in the prompt:

- Task slug
- Mode (`fresh` / `diff` / `<focus>`)
- Working directory is the project root
- Read the existing `ROADMAP.md` if in `diff` mode; preserve the Decision Log section

The cartographer will gate the user at three decision points (paradigm confirmation, deprecation confirmation, phase ordering). Do not auto-approve — the user's input is load-bearing per SPIRIT dimension 1.

### 5. Post-run

Surface:

- Path to the generated or updated `ROADMAP.md`
- One-sentence summary per phase (from the cartographer's output)
- Any open questions the cartographer flagged
- Any memory candidates the cartographer surfaced for persistence (these are for the main coordinator to evaluate via `remember()`)

## Notes

- The cartographer operates on any project type — **deterministic** (libraries, CLIs, services) or **agentic** (LLM apps, agent frameworks, plugins) or **hybrid**. Paradigm detection happens in Phase 1 and feeds the lens-set derivation (which exemplar fits, which sub-questions fire within each lens). SPIRIT is the exemplar Praxion uses for its own audits; other projects get other exemplars or Custom sets (see [`lens-framework.md`](../skills/roadmap-synthesis/references/lens-framework.md)).
- The audit involves external research (2026 state-of-the-art); expect several minutes for the parallel researcher fan-out.
- Every quantitative claim in the output is grounded to a file, command, or cited source per the [grounding-protocol](../skills/roadmap-synthesis/references/grounding-protocol.md). If you see an ungrounded claim, flag it as a bug in the cartographer's Phase 7 self-verify.
- For the roadmap lifecycle (living document, Decision Log preservation, per-run archival via git history), see [dec-032](../.ai-state/decisions/032-roadmap-md-location-and-lifecycle.md).
