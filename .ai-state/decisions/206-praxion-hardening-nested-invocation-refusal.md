---
id: dec-206
title: AgentSdkJudgeClient refuses to run from inside a nested Claude Code session — no graceful degradation, no retry
status: accepted
category: behavioral
date: 2026-05-26
summary: When CLAUDECODE=1 is set, AgentSdkJudgeClient raises RuntimeError at __init__ time with a three-part remediation message; the harness never silently falls back to MessagesApiJudgeClient and never retries the SDK call. Re-affirms dec-204's hybrid-auth seam and dec-205's flat module layout.
tags: [eval, eval-praxion, judge-client, nested-invocation, refusal-policy, behavioral-contract]
made_by: agent
agent_type: systems-architect
branch: eval-praxion-hardening
pipeline_tier: standard
affected_files:
  - eval/src/praxion_evals/harness/judge_client.py
re_affirms: dec-204
---

## Context

`/eval-praxion` v1 (shipped 2026-05-26 via dec-204 + dec-205) was invoked from inside an active Claude Code session on 2026-05-26. The harness hung with zero output for 6–22 minutes (multiple observation windows) before manual interruption. Process inspection and the researcher's pass identified the deadlock surface: `AgentSdkJudgeClient.judge()` calls `asyncio.run(_run())` over `claude_agent_sdk.query()`, which spawns the bundled `claude` CLI as a subprocess. The subprocess attempts a stdin-handshake initialization that conflicts with the outer Claude Code session's stdio management, producing an OS-level deadlock that neither side can break.

The deadlock pattern is acknowledged in the SDK source itself: `claude_agent_sdk v0.2.87`, `_internal/transport/subprocess_cli.py:428-430` strips `CLAUDECODE` from the *child* environment with a comment citing issue #573 (so SDK-spawned subprocesses don't mistakenly think they're nested). **But there is no guard on the Python caller side** — the SDK does not check for `CLAUDECODE=1` before opening the subprocess, and there is no documented Anthropic guidance forbidding nested invocation.

Environment inspection confirms `CLAUDECODE=1` and `CLAUDE_CODE_ENTRYPOINT=cli` are reliably set inside every Claude Code session and inherited by every subprocess (researcher captured this via `env | grep -i claude` from the live session).

The architectural question: when a Praxion-internal tool (`/eval-praxion`) detects this scenario, what should it do?

## Decision

`AgentSdkJudgeClient.__init__()` reads `os.environ.get("CLAUDECODE")`. If the value is `"1"`, it raises `RuntimeError` with a three-part message:

1. **What was tried** — "Cannot use Agent SDK route from inside an active Claude Code session."
2. **What failed** — "Detected CLAUDECODE=1 in the environment. The bundled `claude` CLI subprocess spawned by claude-agent-sdk attempts a stdin handshake that deadlocks when the parent's stdio is already managed by an outer Claude Code session (see https://github.com/anthropics/claude-agent-sdk-python/issues/573)."
3. **What to do** — "Run /eval-praxion from a plain shell (no active Claude Code session), or set `ANTHROPIC_API_KEY` to take the direct Messages API route."

The raise happens at construction time — before any corpus resolution, before any family iteration — so a misconfigured invocation fails in the first second after invocation, not after the operator has waited minutes for output that will never arrive.

`MessagesApiJudgeClient` is **not** modified: it routes through `anthropic.Anthropic()` and the HTTP layer, never spawns a `claude` subprocess, and does not deadlock under `CLAUDECODE=1`.

`select_judge_client()` is **not** modified: it does not detect or handle the nested case. The factory still routes via the documented precedence (`CLAUDE_CODE_OAUTH_TOKEN` → Agent SDK; `ANTHROPIC_API_KEY` → Messages API). When the OAuth path is selected from a nested context, the construction itself fails and `select_judge_client()` propagates the `RuntimeError` unchanged.

**The harness never silently falls back to `MessagesApiJudgeClient`** when the SDK route is unavailable. The operator who exported `CLAUDE_CODE_OAUTH_TOKEN` did so deliberately (to draw on subscription credit); switching them to `ANTHROPIC_API_KEY` without consent would charge their API account.

**The harness never retries** the SDK call after a nested-detection refusal. The deadlock is structural — no number of retries changes it.

## Considered Options

### Option 1 — Refuse at `__init__` (chosen)

`AgentSdkJudgeClient.__init__()` raises `RuntimeError` if `CLAUDECODE=1`. Three-part message names both remediation paths. Construction fails in milliseconds.

- **Pros**: fails before any work is done; respects operator's auth choice; surfaces the conflict explicitly; honors Behavioral Contract's "Surface Assumptions" — no silent semantic shift.
- **Cons**: introduces friction for the operator who casually runs `/eval-praxion` from inside their Claude Code session. Mitigated by the three-part message naming both remediation paths.

### Option 2 — Gracefully degrade to `MessagesApiJudgeClient`

When `CLAUDECODE=1` is detected, `select_judge_client()` silently switches to the Messages API path (assuming `ANTHROPIC_API_KEY` is also set; otherwise raise).

- **Pros**: "Just works" for the operator who has both env vars set.
- **Cons**: charges the API key budget without consent when the operator deliberately chose the subscription path. The auth choice is a meaningful operator decision, not a fungible implementation detail. Silent semantic shifts are a behavioral-contract failure mode (Surface Assumptions): the operator should be told "your chosen path will deadlock — here's why — choose how to proceed." Fallback is also harder to test (the test must distinguish "OAuth selected" from "OAuth selected but silently demoted"). Rejected.

### Option 3 — Retry the SDK call with backoff

When the SDK call hangs past a timeout, retry up to N times.

- **Pros**: handles transient SDK errors uniformly with the deadlock.
- **Cons**: the deadlock is structural, not transient — retry will deadlock again every time. Conflates two different failure modes (transient API rate-limit / network errors vs. structural environment conflict) under one mitigation. Rejected.

### Option 4 — Defer the raise to `judge()` call time

Detect `CLAUDECODE=1` only when `judge()` is first called, not at `__init__`.

- **Pros**: marginally simpler than init-time guarding for tests that construct the client without invoking `judge()`.
- **Cons**: the operator waits for corpus resolution (`CorpusReader.resolve()` walks `.ai-state/specs/`, `.ai-state/decisions/`, etc.) and the first mechanical-check pass before seeing the failure. The whole point of failing fast is to fail before any user-visible work. Rejected on Stay Surgical / fail-fast grounds.

### Option 5 — Strip `CLAUDECODE` from `options.env` (mirror the SDK's child-side strip)

Instead of refusing, strip `CLAUDECODE` from the environment passed to the SDK's subprocess.

- **Pros**: would solve the deadlock at the subprocess-environment level, the same mechanism the SDK uses internally (#573).
- **Cons**: the SDK already strips `CLAUDECODE` from its child environment (`subprocess_cli.py:428-430`); the deadlock is *not* because the child sees `CLAUDECODE=1`, it's because the *parent* (our Python process) is already a child of an interactive Claude Code session and its stdio is being managed. Stripping `CLAUDECODE` does nothing about the stdio conflict. Rejected on factual grounds.

## Consequences

**Positive:**

- The deadlock scenario observed on 2026-05-26 is structurally impossible to reproduce silently. The first second of invocation either succeeds normally or produces an actionable three-part error message.
- The refusal preserves the operator's deliberate auth choice. No subscription credit gets silently rerouted to API-key billing or vice versa.
- The implementation surface is small: one `os.environ.get` call, one `if`, one `raise`. The behavior is testable in isolation via the existing `sys.modules`-injection idiom (no real SDK needed).
- The error message points at SDK issue #573 — a primary source any future maintainer can consult — and names two concrete remediation paths (`plain shell`, `ANTHROPIC_API_KEY`), giving the operator immediate options without filing a support request.
- Re-affirms dec-204's hybrid-auth seam: family code still never branches on auth mode; the `JudgeClient` adapter still encapsulates the decision.
- Re-affirms dec-205's flat module layout: the new guard is one constant + one block in the existing `judge_client.py`; no `checks/` sub-package needed, no new module needed.

**Negative:**

- Operators who routinely run `/eval-praxion` from inside an interactive Claude Code session must adjust their workflow (open a plain terminal, or export `ANTHROPIC_API_KEY` once). The three-part message tells them how, but the friction is real on the first encounter.
- The detection is environment-variable-based, which means a sufficiently confused environment (e.g., `CLAUDECODE` carried over from a long-dead session via shell rc files) could fire the guard spuriously. Mitigated: `CLAUDECODE=1` set in a non-Claude-Code shell is an environmental misconfiguration the operator can clear with `unset CLAUDECODE`; the error message tells them this exists.
- If Anthropic adds first-class nested-invocation detection to `claude_agent_sdk` in a future version (e.g., raising a `NestedSessionError` from `query()`), our guard becomes redundant. That is acceptable: removing redundant guards is a clean follow-up; today, the SDK has no such mechanism (verified against v0.2.87 source).

## Prior Decision

This ADR **re-affirms dec-204 and dec-205**. Neither is superseded; neither has any clause narrowed.

- **dec-204 (Praxion self-eval v1 — `/eval-praxion` adds LLM-as-judge over completed artifacts)**: the hybrid-auth seam (OAuth → Agent SDK; API key → Messages API; runtime env detection) is preserved verbatim. This ADR adds a *behavioral refinement to the OAuth branch only* — when that branch would deadlock, refuse. The seam structure itself, the family code's auth-mode-independence, and the out-of-band invocation pattern from clause 1 are all unchanged. The narrowed-clause-3 LLM-as-judge model continues to apply.
- **dec-205 (harness module layout — flat 2-level)**: no module structure changes. The guard is added inside the existing `AgentSdkJudgeClient.__init__()`; no new files, no new sub-packages.

A future ADR would be needed only if a maintainer proposes either (a) graceful degradation between auth routes (which dec-204's hybrid seam permits but this ADR's behavior forbids), or (b) silent retry of the SDK call after a structural refusal. Either change would supersede the refusal-policy half of this ADR.
