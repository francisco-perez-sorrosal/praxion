---
diataxis: reference
audience: developer
---

# Context economy

This is the single documented home for three things, and it claims no enforcement of any of them: the measured
baseline of how much context Praxion pipelines actually use, a target for the orchestrator's window going forward
with the phase-boundary handoff (`/handoff`, see [`commands/handoff.md`](../commands/handoff.md)) named as the means
of reaching it, and the four operator-side controls that exist to lower the harness's own auto-compaction threshold.
Praxion sets none of those controls, ships no threshold, and reads no utilisation: a Praxion-set band was considered
and rejected, because forcing compaction at a token count does not preserve the orchestrator's judgement state (the
user's standing instructions, corrections in force, and spawns in flight) — only the handoff does that, by writing
it down while the window still holds it. The full rationale is recorded as a decision in `.ai-state/decisions/`.

## 1. Measured baseline

Source: **20 main-session transcripts and 296 subagent transcripts**, reproduced on the machine that produced this
doc (2026-08-25..09-14) with the documented command below. Context size per turn is
`input + cache_read + cache_creation` tokens; peak is the max over a transcript. Re-measure on any machine holding
its own transcripts with:

```
uv run python scripts/context_baseline.py --project-root <primary checkout> --json
uv run python scripts/context_baseline.py --project-root <primary checkout> --table   # human-readable form
```

**Name the primary checkout explicitly, or the guard sees less than the full corpus.** Claude Code keys a session's
transcript directory by the *current working directory's* mangled path at the time each turn is written.
Standard/Full-tier pipelines run from a git worktree (the coordination protocol's isolation convention), so any
portion of a session's transcript written while the cwd was inside a worktree is filed under that worktree's own
mangled project directory — invisible to a `--project-root` invocation that does not name the primary checkout, and
the guard reports no sessions at all if run with no `--project-root` flag from inside a worktree. The pipeline that
produced this document's original `BASELINE.md` scan globbed every sibling transcript directory by hand and counted
**21 main-session transcripts and 297 subagent transcripts**; the one-session, one-subagent difference from the
20/296 above is exactly one worktree-scoped transcript directory the documented single-`--project-root` command
cannot see. A full accounting across every sibling `~/.claude/projects/<repo-mangled-prefix>*` directory is out of
this guard's current scope.

Compaction has never fired on this corpus (`isCompactSummary` count: 0 in both main and subagent transcripts) — the
windows involved are 1M tokens wide.

**Orchestrator (main) windows:**

| metric | value |
|---|---|
| peak context p50 / max | ~420k / 754,514 |
| first-turn context, p50 | ~95k |
| context when spawning an implementer, p50 / p90 / max (n=155) | 317,992 / 485,035 / 675,178 |
| context when spawning the verifier, p50 / max (n=45) | 377,151 / 706,508 |
| context when spawning the planner, p50 / max (n=12) | 289,130 / 446,692 |
| context when spawning the architect, p50 / max (n=9) | 180,169 / 341,250 |

**Subagent windows (peak context, tokens):**

| type | n | first turn p50 | peak p50 | peak p90 | peak max |
|---|---|---|---|---|---|
| implementer | 86 | 91,718 | 174,706 | 260,805 | 439,364 |
| test-engineer | 23 | 76,463 | 174,731 | 253,046 | 272,946 |
| verifier | 18 | 89,240 | 153,233 | 285,020 | 291,183 |
| researcher | 15 | 68,137 | 168,385 | 231,870 | 234,519 |
| implementation-planner | 7 | 77,419 | 211,682 | 278,660 | 278,660 |
| systems-architect | 6 | 91,138 | 322,343 | 393,536 | 393,536 |
| sentinel | 47 | 67,032 | 202,942 | 277,584 | 325,652 |
| doc-engineer | 7 | 68,144 | 111,028 | 308,423 | 308,423 |
| context-engineer | 7 | 83,275 | 171,128 | 224,188 | 224,188 |

No subagent type has ever exceeded 439,364 tokens (the implementer's peak max). These numbers are a snapshot, not a
guarantee — they will drift as the fleet and the corpus grow. Re-measure rather than trust this table.

## 2. The target

**Orchestrator context at spawn below 250,000 p50, measured over the next three pipelines.** This is a target to be
judged after the fact, not a threshold Praxion enforces or reads at runtime — nothing in this repository compacts a
session, blocks a spawn, or reads a window's current size.

The means of reaching it is the phase-boundary handoff: the orchestrator runs `/handoff <slug>` at a Conversation
Checkpoint (phase transition or pre-verification), writing the mechanical and judgement state of the outgoing window
to `.ai-work/<slug>/HANDOFF.md` so the next window resumes from that document via `/resume-pipeline <slug>` rather
than re-accumulating the same context to re-derive its position. A lower spawn-time p50 is the expected effect of
handing off before a window grows unbounded across an entire pipeline, not of any mechanism that caps the window
itself.

Two heuristics accompany the target — offered as a rule of thumb for *when* to reach for `/handoff`, not as a spawn
budget or a rule anything enforces:

- **one window per phase** as a starting rhythm;
- inside a long implementation phase, **a handoff after roughly eight spawn-cycles**.

Neither changes a pipeline tier's spawn cap or its total spawn count (that remains out of this document's scope) —
they describe how many spawn-cycles might share one orchestrator window before a handoff, nothing more. Re-measure
the target itself with:

```
uv run python scripts/context_baseline.py --project-root <primary checkout> --json
```

and read `main.spawn_context.<agent-type>.p50` for each type spawned by a pipeline; judge the target against how
those percentiles trend across the next three pipelines' worth of measurements, not against a single run.

## 3. The operator's own compaction controls

Praxion sets none of these. They exist in the harness itself, and lowering one is the operator's own decision to
make — this section documents their verified names, forms, and precedence so that an operator who chooses to set one
does so correctly. No value below is a Praxion recommendation.

| control | form | scope | precedence |
|---|---|---|---|
| `CLAUDE_AUTOCOMPACT_PCT_OVERRIDE` | integer percentage, 1–100, lower-only | applies to both main conversations and subagents | — |
| `CLAUDE_CODE_AUTO_COMPACT_WINDOW` | absolute token count, 100,000–1,000,000, capped at the model's context window | main conversations | takes precedence over `/autocompact`, `--autocompact`, and the persisted `autoCompactWindow` setting |
| `/autocompact <n>` | interactive command | persisted per user as the `autoCompactWindow` setting | — |
| `--autocompact` | launch flag | current launch only | — |

All four are bounded by the model's own context window (Sonnet 5's API default window is ~967K tokens) — none of
them can raise a window past what the model supports.

### The retained counterfactual (analysis, not a setting)

`scripts/context_baseline.py --band <tokens>` answers, for an operator considering one of the controls above, "how
many past windows would a threshold of *N* tokens have compacted":

```
uv run python scripts/context_baseline.py --project-root <primary checkout> --band 500000 --json
```

On `BASELINE.md`'s original hand-globbed scan, a 500,000-token band fires on **7 of 21** main sessions (peak p50 ≈
420k, max 754,514) and **0 of 297** subagent transcripts. Reproducing it with the documented command above — the
same single-`--project-root` visibility described in §1 — returns **6 of 20** main sessions and **0 of 296**
subagents on this machine: one fewer main session than the original scan, for the same worktree-scoped-directory
reason, and the subagent invariant holds under either count. No subagent type has ever crossed the band at either
count. The number is analysis an operator can reproduce against their own transcripts, never a value this repository
ships or applies; the exact count is illustrative, not load-bearing — what is load-bearing is that no subagent type
has ever crossed it.

## 4. After-measurement plan

This pipeline (the one that added `/handoff` and this document) is the first data point toward the target in §2. No
judgement is made on fewer than three pipelines' worth of measurements — re-run
`uv run python scripts/context_baseline.py --project-root <primary checkout> --json` after each of the next three
pipelines and compare
`main.spawn_context.<agent-type>.p50` against the 250,000 target. If the practice of handing off at phase boundaries
is not moving that number down, that is itself the signal to revisit this document, not a reason to add a
Praxion-set band.

## 5. Two learning stores, by audience (D5)

Praxion keeps two stores on purpose and does not merge them (roadmap §10 D5, settled 2026-09-07):

- **Personal, machine-local** — the harness's own auto-memory directory (`~/.claude/projects/<project>/memory/`,
  `MEMORY.md` index + one file per fact). Gotchas, environment facts, corrections the operator gave. Never committed,
  never shipped; it is the operator's, and it survives sessions without costing the repo a byte of always-loaded
  context.
- **Shareable, committed** — `.ai-work/<slug>/LEARNINGS.md` in flight, promoted by `/skill-genesis` into skills, rules
  and ADRs, dispositioned by `/skill-genesis-review`. This is the only half a teammate or a managed project can see.

The rule of thumb: if a second person would need it, it goes through LEARNINGS and the harvest; if only this machine
would, it stays in memory. No MCP memory tools are registered (`dec-225`); nothing in Praxion reads the personal
store programmatically.
