---
id: dec-214
title: Agent-readiness LLM judge uses a stdlib-urllib direct Messages API call, not the anthropic SDK nor a shell-out to eval
status: accepted
category: architectural
date: 2026-06-04
summary: The default-on agent-readiness LLM tier calls the Anthropic Messages API via a ~40-line stdlib urllib judge in scripts/project_metrics/collectors/readiness/judge.py, preserving the metrics package's zero-third-party-dependency contract; it never imports the anthropic SDK and never spawns the claude CLI (avoiding the dec-206 CLAUDECODE deadlock).
tags: [agent-readiness, project-metrics, judge-client, llm, stdlib, dependency-policy, anthropic-api]
made_by: agent
agent_type: systems-architect
branch: worktree-factory-agent-readiness-research
pipeline_tier: standard
affected_files:
  - scripts/project_metrics/collectors/readiness/judge.py
  - scripts/project_metrics/cli.py
re_affirms: dec-206
---

## Context

The agent-readiness capability rides `/project-metrics`. Its mechanical tier is a deterministic collector; its LLM-judged tier (~4 subjective criteria: naming-conventions, test-quality, readme-quality, docs-agent-friendliness) is **default-on** by user decision (2026-06-04). The LLM tier therefore needs to make Anthropic API calls from inside the `scripts/project_metrics/` package on a routine `/project-metrics` run.

Three verified constraints collide:

1. **The metrics package is stdlib-only.** `pyproject.toml` declares no `[project.dependencies]`; every module in `scripts/project_metrics/` imports only the Python standard library (plus `uvx` for optional external tools). This zero-dependency property is what lets the capability ship to every managed project purely via `claude plugin install` with **no `install.sh` edit and no per-project Python copy**.
2. **The only existing judge client lives in a separate uv environment.** `eval/src/praxion_evals/harness/judge_client.py` and its `anthropic` dependency live in `eval/`'s own uv project (`eval/pyproject.toml`, `requires-python >=3.13`, `dependencies = ["anthropic", "claude-agent-sdk", ...]`). The metrics package cannot import it without crossing the env boundary.
3. **dec-206 forbids the subprocess-`claude` route under `CLAUDECODE=1`.** `eval`'s factory `select_judge_client()` routes `CLAUDE_CODE_OAUTH_TOKEN → AgentSdkJudgeClient`, which spawns the bundled `claude` CLI and **refuses to construct** when `CLAUDECODE=1` (the nested-session deadlock guard, SDK issue #573). `/project-metrics` is normally invoked from inside a Claude Code session, where `CLAUDECODE=1` is set and inherited.

The question: how does a default-on, collector-adjacent LLM judge make Anthropic calls under these three constraints?

## Decision

The LLM judge is a **stdlib-`urllib` direct call to the Anthropic Messages API**, implemented in `scripts/project_metrics/collectors/readiness/judge.py` (~40 lines). It:

- POSTs to `https://api.anthropic.com/v1/messages` via `urllib.request`, using the `messages` + forced `tool_choice` ("verdict" tool) pattern to obtain structured `{passed, rationale}` output — the same tool-call-as-output shape `MessagesApiJudgeClient` uses, re-implemented in stdlib.
- Detects auth with the **same precedence as eval** but never delegates to it: `ANTHROPIC_API_KEY` → `x-api-key` header; `CLAUDE_CODE_OAUTH_TOKEN` → `Authorization: Bearer`; neither → raise `JudgeUnavailable`.
- **Never imports the `anthropic` SDK** and **never imports `claude_agent_sdk` / spawns the `claude` CLI** — so it cannot trip the dec-206 CLAUDECODE deadlock.
- Uses `claude-haiku-4-5` (eval's `_DEFAULT_MODEL`) for cost/latency, with a per-criterion timeout.
- Reads auth tokens at call time only; never logs or persists them. The emitted `readiness.llm` block records `model` and `grounded_on`, never credentials.

This is invoked from a `cli.py` `enrich_readiness` step that runs **outside** the runner's deterministic collect pass (see the sibling contract-shift ADR, `dec-215`).

## Considered Options

### Option (a) — Add `anthropic` to the metrics env

Import `eval`'s `MessagesApiJudgeClient`, or instantiate `anthropic.Anthropic()` directly, after adding `anthropic` to a runtime dependency group.

- **Pros**: reuses a battle-tested client; richer error handling; no re-implementation.
- **Cons**: makes a *previously pure-offline, stdlib-only* package carry a heavy transitive SDK (httpx, pydantic, …) on **every** `/project-metrics` run in **every** managed project — including mechanical-only/offline runs that never call it. Forces a `pyproject.toml` change + `uv sync` + an `install.sh` touch, destroying the near-zero-install pervasiveness property. Rejected.

### Option (b) — Stdlib-`urllib` direct Messages API call (chosen)

A ~40-line `judge.py` POSTing to the Messages API.

- **Pros**: preserves the zero-third-party-dependency contract; no install.sh edit; ships via `claude plugin install` alone; fully unit-testable by mocking `urllib.request.urlopen` (no network in CI); never touches the dec-206 subprocess hazard.
- **Cons**: re-implements a thin slice of `MessagesApiJudgeClient` (one POST + tool-input parse) — ~40 lines of acknowledged duplication; carries the risk of Messages-API request-shape drift.

### Option (c) — Shell into eval's uv env

`uv run --project eval python -m praxion_evals…judge`.

- **Pros**: reuses the real client without adding a dep to the metrics env.
- **Cons**: eval's default OAuth route spawns the `claude` CLI and is **refused by dec-206 under `CLAUDECODE=1`** — exactly the context `/project-metrics` runs in. Adds subprocess + uv-resolution latency and a new failure surface even on the API-key path. Re-introduces the nested-invocation hazard dec-206 closed. Rejected.

## Consequences

**Positive:**
- The metrics package stays stdlib-only; agent-readiness ships to every managed project with zero install.sh change (verifiable via the `--check` importability assertion).
- The LLM tier degrades gracefully offline (no auth → `JudgeUnavailable` → `llm_skipped`); offline CI still succeeds.
- The judge is trivially unit-testable (mock `urlopen`); CI stays deterministic and network-free.
- No re-entry of the dec-206 deadlock — this ADR `re_affirms` dec-206's reasoning by routing around the subprocess-claude path entirely.

**Negative / accepted:**
- ~40 lines duplicating `MessagesApiJudgeClient`'s request/parse logic. Mitigation: keep the request shape behind the `judge.py` seam; one focused unit test on headers + body; diff against eval's living reference if drift is suspected.
- Messages-API request-shape drift risk. Escape hatch: if drift recurs, swap to depending on `anthropic` (Option a) behind the same `judge.py` seam — a localized change.

## Prior Decision

This decision `re_affirms` **dec-206** (AgentSdkJudgeClient refuses to run under `CLAUDECODE=1`, no graceful degradation, no retry). dec-206 closed the nested-invocation deadlock for `/eval-praxion`; this ADR honors it by ensuring the agent-readiness judge never takes the subprocess-`claude` route in the first place. A future supersession would require evidence that either (1) the metrics package's stdlib-only contract has been deliberately abandoned, or (2) the Anthropic Messages API is no longer reachable via a plain HTTPS POST.
