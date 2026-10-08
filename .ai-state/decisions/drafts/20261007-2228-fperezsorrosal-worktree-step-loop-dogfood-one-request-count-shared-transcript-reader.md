---
id: dec-draft-2dc56cc3
title: An agent's distinct-request count has one definition in hooks/_agent_transcript.py, read by the driver, the turn-budget reminder and the context instrument; JSON Lines split on newline only
status: proposed
category: architectural
date: 2026-10-07
summary: The context instrument's private distinct-request counter is retired; hooks/_agent_transcript.py's request_count(reading) becomes the one definition (distinct requestId over assistant records of a transcript whose every line parses, else no count), read by the step-loop driver's record and end evidence, the turn-budget reminder and context_baseline.py's cap-out count; the reader splits JSON Lines on newline only (str.splitlines cut real transcripts at raw U+2028/U+2029); the instrument gains --transcripts-dir as the stated surface for where it reads a project's sessions, its default unchanged.
tags: [transcript, request-count, context-baseline, turn-budget, step-loop, jsonl, measurement]
made_by: agent
agent_type: systems-architect
branch: worktree-step-loop-dogfood
pipeline_tier: full
affected_files:
  - hooks/_agent_transcript.py
  - scripts/context_baseline.py
  - scripts/_step_loop_record.py
  - scripts/_step_loop_files.py
  - hooks/remind_turn_budget.py
affected_reqs: [REQ-03, REQ-12]
dissent: []
---

## Context

Two counters of an agent's distinct API requests existed (tracked as td-350):

- the shared reader `hooks/_agent_transcript.py`, which the driver records turns from and the reminder will read;
- `context_baseline._parse_subagent_transcript`, private, counting only usage-bearing assistant records and skipping unparseable lines silently.

The spec requires one definition, and the same reading from every reader on clean, repeated, cut-off and malformed transcripts; a reader that cannot parse gives no count. A design-time comparison over the primary checkout's 437 subagent transcripts found the shared reader **defective**. It splits with `str.splitlines()`, which also cuts at U+2028 and U+2029, and Claude Code writes those raw inside JSON strings. Five transcripts (1 %), one an implementer's, read as unreadable. Split on `\n` only, all 437 parse and give exactly the instrument's count. No transcript in the corpus has requests without usage.

Separately, the instrument had no stated surface for where it reads a project's sessions (its directory is derived from a hard-coded home path and a mangled project path), so the designed scenario that binds it could not be written.

**Activation:** no. One candidate meets "one definition" without moving the instrument's measured population, and the corpus evidence decides the splitter.

## Decision

1. **The one definition is `request_count(reading) -> int | None`** in `hooks/_agent_transcript.py`: the number of distinct `requestId` values over the assistant records of a transcript whose every line parses. It is `None` for a missing file, an unparseable line, or an assistant record without an id. The driver's turns, the driver's end evidence, the reminder's `used` and the instrument's `requests` all read it.
2. **JSON Lines split on `"\n"` only** in `parse_transcript`.
3. **The instrument folds onto the reader.** It reads each subagent transcript once. Its tolerant pass keeps peak, turns, tools and compactions exactly as before. `requests` comes from the shared count. A row exists when the tolerant pass saw a usage-bearing turn or the count is at least 1. A row with no count is left out of `cap_outs`, with a named warning.
4. **`--transcripts-dir DIR`** is the instrument's stated surface for where it reads a project's sessions. Its default is derived from `--project-root` exactly as before, still blind to worktree sessions, so the falsifier readings keep their population.
5. **`locate` gains `search_all`** (default true). It also stops globbing every project unless the session arm misses. The per-call hook passes false, so it never searches the whole config directory.

## Considered Options

### Option 1 — Shared reader as the one definition, newline-only split, instrument folded (chosen)
- **Pros:** one count by construction; fixes a real defect on the driver's and the reminder's path before the driver runs live; the instrument's readings are unchanged on the measured corpus (437 of 437).
- **Cons:** the instrument now depends on the hooks directory for its count. A real transcript that does not parse leaves `cap_outs` instead of being counted tolerantly.

### Option 2 — Keep two counters and pin their agreement with a test
- **Pros:** no instrument change.
- **Cons:** "one definition" is not met; two implementations drift; the defect stays in one of them.

### Option 3 — Make the shared reader tolerant (skip unparseable lines, as the instrument did)
- **Pros:** fewer spawns lose their count.
- **Cons:** a cut-off final flush or a corrupt record would yield a plausible wrong count, and the driver records it as fact. The spec chooses "no count" over "a wrong one".

## Consequences

**Positive:** the turns the driver records, the threshold the reminder warns at and the cap-outs the instrument reports cannot disagree about one transcript. The driver reads the roughly 1 % of real transcripts it would have rejected. Any project can point the instrument at a worktree's sessions without changing the default reading.

**Negative:** the instrument's tolerant pass still uses `splitlines()` for its context-token numbers (left alone so the context falsifier does not move mid-window), so the module carries two line splitters for two different measurements. The worktree blindness remains.

## Disconfirmation

- **Falsifier:** after the change, the instrument's implementer cap-out reading or its median orchestrator context at verifier spawn differs from the reading taken immediately before it on the same primary corpus; or the three readers disagree on any transcript in a shared corpus.
- **Steelmanned runner-up:** Option 3. A measurement instrument that drops a 100-request implementer because one late line was cut mid-flush under-reports cap-outs exactly when agents die hard. A tolerant count with a named "partial" flag would keep those spawns visible.
- **Reversal trigger:** if real transcripts that do not parse as a whole exceed 1 % of a corpus after the newline fix, give the reader a tolerant count that is marked as such (a `partial` reading) and let each consumer choose, rather than dropping the spawn.
