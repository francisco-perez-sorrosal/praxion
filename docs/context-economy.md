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

Source: 21 main-session transcripts and 297 subagent transcripts on the machine that produced this doc
(2026-08-25..09-14), scraped by `scripts/context_baseline.py`. Context size per turn is
`input + cache_read + cache_creation` tokens; peak is the max over a transcript. Re-measure on any machine holding
its own transcripts with:

```
uv run python scripts/context_baseline.py --json
uv run python scripts/context_baseline.py --table   # human-readable form of the same data
```

Compaction has never fired on this corpus (`isCompactSummary` count: 0 in both main and subagent transcripts) — the
windows involved are 1M tokens wide.

**Orchestrator (main) windows:**

| metric | value |
|---|---|
| peak context p50 / max | ~420k / 754,514 |
| first-turn context, p50 | ~95k |
| context when spawning an implementer, p50 / p90 / max (n=156) | 317,992 / 485,035 / 675,178 |
| context when spawning the verifier, p50 / max (n=45) | 377,151 / 706,508 |
| context when spawning the planner, p50 / max (n=12) | 289,130 / 446,692 |
| context when spawning the architect, p50 / max (n=9) | 180,169 / 341,250 |

**Subagent windows (peak context, tokens):**

| type | n | first turn p50 | peak p50 | peak p90 | peak max |
|---|---|---|---|---|---|
| implementer | 87 | 91,718 | 174,706 | 260,805 | 439,364 |
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
uv run python scripts/context_baseline.py --json
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
uv run python scripts/context_baseline.py --band 500000 --json
```

On the corpus in §1, a 500,000-token band fires on **7 of 21** main sessions (peak p50 ≈ 420k, max 754,514) and
**0 of 297** subagent transcripts — no subagent type has ever crossed it. The number is analysis an operator can
reproduce against their own transcripts, never a value this repository ships or applies.

**A known limit of this counterfactual, stated plainly.** Standard/Full-tier pipelines run from a git worktree
(per the coordination protocol's pipeline-isolation rule), and Claude Code keys a session's transcript directory by
the *current working directory's* mangled path at the time each turn is written — a session whose cwd moves into a
worktree mid-session gets that portion of its transcript filed under the worktree's own mangled project directory,
invisible to a single `--project-root` pointed at the primary checkout. Reproducing the counterfactual above with
`--project-root` naming the primary checkout on this machine returns **6 of 20** main sessions, not 7 of 21 — one
worktree-run session is simply not visible from that vantage point. This is a limit of the instrument (`--project-root`
is deliberately singular; a full accounting would need to glob every sibling `~/.claude/projects/<repo-mangled-prefix>*`
directory), not a parsing defect, and it does not change the invariant the counterfactual is cited for: at every band
this instrument can measure, no subagent type has ever crossed 500,000 tokens. It also does not change the design
decision this documents — the counterfactual is retained as reference material for an operator's own analysis, never
as a value Praxion enforces, so the exact count is illustrative rather than load-bearing.

## 4. After-measurement plan

This pipeline (the one that added `/handoff` and this document) is the first data point toward the target in §2. No
judgement is made on fewer than three pipelines' worth of measurements — re-run
`uv run python scripts/context_baseline.py --json` after each of the next three pipelines and compare
`main.spawn_context.<agent-type>.p50` against the 250,000 target. If the practice of handing off at phase boundaries
is not moving that number down, that is itself the signal to revisit this document, not a reason to add a
Praxion-set band.
