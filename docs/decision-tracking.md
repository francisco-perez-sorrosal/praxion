# Decision Tracking

AI-assisted development sessions produce many decisions -- architecture choices, implementation trade-offs, rejected alternatives, calibration judgments. Most are lost: buried in conversation transcripts, trapped in ephemeral documents, or visible only as unexplained code. This project captures decisions in a machine-readable audit log (`.ai-state/decisions.jsonl`) via two complementary paths, with tier-aware behavior that scales process to task complexity.

Standalone decision extraction tools (e.g. [plumb](https://github.com/dbreunig/plumb)) typically bolt onto the development workflow via git hooks, extracting decisions post-hoc from conversation transcripts. This project takes a different approach: decision tracking is native to the agent pipeline, with agents writing decisions at the point of highest context and a commit-time hook catching what they miss.

For the full schema definition and agent protocol, see `[rules/swe/decision-tracking.md](../rules/swe/decision-tracking.md)`.

## The Problem: Decision Loss

Before decision tracking, decisions were lost at five points in the pipeline:


| Loss Point              | Severity   | What Was Lost                                                                                                         |
| ----------------------- | ---------- | --------------------------------------------------------------------------------------------------------------------- |
| Session boundary gap    | Critical   | Direct/Lightweight tier decisions never entered any document -- rationale existed only in the conversation transcript |
| LEARNINGS.md deletion   | High       | End-of-feature cleanup merged selectively; granular decisions fell through the cracks                                 |
| Spec archival scope     | Medium     | Only medium/large features got archived specs; small features with important decisions got nothing                    |
| Architect trade-offs    | Medium     | The systems-architect's trade-off analysis lived in ephemeral `SYSTEMS_PLAN.md` with no systematic path to permanence |
| Implicit code decisions | Low-Medium | Naming choices, data structure selections, error handling strategies -- visible in diffs but never documented         |


Decision tracking addresses the first four directly and partially addresses the fifth via diff-based extraction.

## Dual-Path Architecture

Decisions reach `decisions.jsonl` via two complementary paths:

```
                    PRIMARY PATH                          SECONDARY PATH
               (agent direct writes)                    (commit-time hook)

Agent makes a decision                          PreToolUse fires on git commit
  |                                                |
  +-- Writes to LEARNINGS.md                       +-- Is this git commit? No -> exit 0
  |   (human-readable, working doc)                |
  |                                                +-- Read transcript + git diff --staged
  +-- Calls decision-tracker write CLI             |
  |   source: "agent"                              +-- Call Haiku (structured extraction)
  |   Full context: rationale,                     |
  |   alternatives, affected_reqs                  +-- Deduplicate against decisions.jsonl
  |                                                |   (skip what agents already wrote)
  v                                                |
decisions.jsonl                                    +-- Branch on tier:
  ^                                                |   +-- Direct/Lightweight/Spike: auto-log, exit 0
  |                                                |   +-- Standard/Full: pending file, exit 2
  +-- Hook appends only NOVEL decisions -----------+
      source: "hook"                               Agent presents decisions for user review
      Lower context (diff-derived)                         |
                                                   User approves/rejects -> re-commits
```

**Primary path (agent direct writes)**: Agents call the `decision-tracker write` CLI whenever they document a decision in `LEARNINGS.md`. This produces the highest-quality entries -- the agent has full context (rationale, alternatives, affected requirements) at the moment of decision.

**Secondary path (commit-time hook)**: A `PreToolUse` hook intercepts `git commit`, reads the conversation transcript and staged diff, sends them to Claude Haiku for structured extraction, and deduplicates against entries agents already wrote. This catches decisions agents missed -- implicit choices visible in diffs, undocumented trade-offs, and all decisions from lightweight tiers where agents skip `LEARNINGS.md`.

## Tier-Aware Behavior

The system respects the pipeline's process calibration tiers. Lightweight work flows unimpeded; substantive work gets decision review.


| Tier        | Extraction                     | Review Gate                            | Rationale                                |
| ----------- | ------------------------------ | -------------------------------------- | ---------------------------------------- |
| Direct      | Hook: silent auto-log          | None                                   | No overhead for single-file fixes        |
| Lightweight | Hook: silent auto-log          | None                                   | Minimal overhead for small changes       |
| Standard    | Agent writes + hook safety net | Hook blocks commit for novel decisions | Full SDD -- decisions deserve review     |
| Full        | Agent writes + hook safety net | Hook blocks commit for novel decisions | Heavy process -- marginal cost           |
| Spike       | Hook: silent auto-log          | None                                   | Exploratory -- decisions are preliminary |


Tier detection uses filesystem heuristics: presence of `SYSTEMS_PLAN.md` implies Standard+, the calibration log provides explicit tier data, and the default is Direct (silent, no gate).

## The JSONL Schema

Each line in `decisions.jsonl` is a self-contained JSON object with 22 fields. Required fields:


| Field       | Description                                                                         |
| ----------- | ----------------------------------------------------------------------------------- |
| `id`        | `dec-` + 12-char UUID fragment                                                      |
| `version`   | Schema version (currently `1`)                                                      |
| `timestamp` | ISO 8601 UTC creation time                                                          |
| `status`    | `pending` / `approved` / `auto-approved` / `documented` / `rejected`                |
| `category`  | `architectural` / `behavioral` / `implementation` / `configuration` / `calibration` |
| `decision`  | The choice that was made                                                            |
| `made_by`   | `user` / `agent`                                                                    |
| `source`    | `agent` (primary path) / `hook` (safety net)                                        |


Optional fields include `rationale`, `alternatives`, `agent_type`, `confidence`, `affected_files`, `affected_reqs`, `commit_sha`, `branch`, `session_id`, `pipeline_tier`, `supersedes`, `rejection_reason`, and `user_note`.

**Status semantics**: `documented` = agent wrote it directly (highest quality). `approved` = user reviewed and accepted (hook path, Standard/Full). `auto-approved` = silently logged (hook path, Direct/Lightweight/Spike). `rejected` = user rejected during review (still logged for audit trail). `pending` = extracted, awaiting review.

**Source semantics**: `agent` entries always have rationale, alternatives, and agent type. `hook` entries may lack these for implicit decisions extracted from diffs.

## Spec Auto-Update Protocol

When the hook blocks a commit during Standard/Full tiers and the user approves decisions that reference requirement IDs, the system checks whether those decisions warrant spec amendments:

1. The agent pipes approved decisions to `decision-tracker propose-amendment`
2. The tool parses `SYSTEMS_PLAN.md`, identifies affected requirements, and generates surgical amendments via Claude Haiku
3. The agent presents before/after diffs of each affected requirement
4. Approved amendments are applied to the spec; affected implementation plan steps receive `[SPEC AMENDED]` annotations
5. The commit includes code changes, spec amendments, and plan annotations atomically

This keeps specifications synchronized with implementation decisions without manual spec maintenance.

## Ecosystem Consumption

Four downstream agents consume `decisions.jsonl`:


| Consumer          | How It Uses Decisions                                                                                                       |
| ----------------- | --------------------------------------------------------------------------------------------------------------------------- |
| sentinel          | DL01-DL05 health checks: JSONL validity, field completeness, REQ ID cross-references, rationale quality, decision frequency |
| skill-genesis     | Recurring decision patterns across features become candidates for rules or skills                                           |
| verifier          | Cross-references `affected_reqs` against the traceability matrix during post-implementation review                          |
| systems-architect | Reads prior feature decisions as brownfield baseline for new architecture work                                              |


## Implementation

The decision-tracker is a Python package at the repo root (`decision-tracker/`) with its own `pyproject.toml`, invoked via `uv run`. Dependencies: `anthropic`, `pydantic`.


| Module          | Purpose                                                              |
| --------------- | -------------------------------------------------------------------- |
| `schema.py`     | Pydantic models for all decision types                               |
| `log.py`        | JSONL read/write with atomic appends                                 |
| `dedup.py`      | Exact text deduplication (normalized, case-insensitive)              |
| `transcript.py` | Claude Code session JSONL parsing with noise reduction               |
| `tier.py`       | Filesystem-based tier detection                                      |
| `extractor.py`  | Anthropic API call with structured tool schema (Claude Haiku 4.5)    |
| `amender.py`    | Spec amendment generation from approved decisions                    |
| `spec.py`       | `SYSTEMS_PLAN.md` parsing and in-place amendment                     |
| `plan.py`       | Implementation plan impact detection and annotation                  |
| `__main__.py`   | CLI entry point: `write`, `extract`, `propose-amendment` subcommands |


The hook entry point (`.claude-plugin/hooks/extract_decisions.py`) is a thin wrapper that delegates to the package via `uv run`, following the existing hook patterns (`send_event.py`, `precompact_state.py`). It reads hook payload JSON from stdin, checks for `git commit`, and forwards to the decision-tracker. The wrapper follows fail-open behavior: any internal error exits 0 (never blocks commits due to its own bugs).

## Comparison with Standalone Decision Extraction Tools

Standalone tools typically extract decisions from conversation transcripts at commit time via git hooks, using LLM-based extraction with frameworks like DSPy. They produce decision logs and can sync decisions back to specs or generate tests. The table below compares common patterns in standalone tools with this project's approach.

### Where This Project Differs

| Standalone Tool Pattern | This Project's Approach | Why |
| --- | --- | --- |
| Extraction-only (post-hoc LLM extraction from transcripts) | Dual-path: agents write at decision time (primary) + hook extraction (safety net) | Agent-written entries have full context -- rationale, alternatives, affected REQs -- that post-hoc extraction cannot reliably recover |
| Uniform application (every commit gets the same treatment) | Tier-aware: silent for Direct/Lightweight/Spike, gates for Standard/Full | Process scales to task complexity; lightweight work flows unimpeded |
| Standalone tool (bolted onto the workflow via git hooks) | Native pipeline integration (sentinel, skill-genesis, verifier, systems-architect consume the log) | Decisions feed ecosystem intelligence, not just an audit trail |
| Full spec rewrite + test generation on sync | Surgical `propose-amendment` with user approval per requirement | Precise, reversible changes instead of aggressive rewrites |
| DSPy or heavy extraction frameworks | Direct Anthropic API + tool schema (Claude Haiku) | Fewer dependencies, lower latency, sufficient for structured extraction |
| LLM-based semantic deduplication | Conversation scoping (primary) + exact text dedup (secondary) | Scoping eliminates most duplicates at source; no per-commit dedup API cost |
| Branch-scoped JSONL shards + SQL engine for cross-branch queries | Single file with `branch` field, standard line scanning | Simpler architecture; Python `json` module suffices at this scale |

### What This Project Adds

| Feature | Value |
| --- | --- |
| **Agent write protocol** | CLI for agents to record decisions with full context at the point of highest knowledge |
| **Spec auto-update protocol** | Surgical amendments to behavioral specs from approved decisions, with plan annotation |
| **Calibration tier integration** | Reads pipeline tier from filesystem signals, respects process calibration philosophy |
| **Source field** (agent vs hook) | Distinguishes high-context agent entries from extracted hook entries for quality signaling |
| **Pipeline consumption** | Four downstream agents consume decisions for health monitoring, learning harvest, verification, and architecture |

### Summary

Standalone decision extraction tools excel at capturing decisions with minimal setup -- install a git hook and decisions appear in a log. This project trades that simplicity for deeper integration: agents write decisions at the point of highest context, the hook catches what they miss, tier awareness prevents process overhead on lightweight work, and the ecosystem consumes the log for ongoing intelligence.