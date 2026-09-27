---
id: dec-draft-78362649
title: The observation log gets one owner package and three registry-driven recording modes
status: proposed
category: architectural
date: 2026-09-27
summary: "A new hooks/_observation_log/ package (modes, registry, writer, reader) becomes the only write and read path for .ai-state/observations.jsonl; recording modes full / standard (default) / off are declared per recording class in the registry, every row carries log_mode, consumers declare their needs as tested contracts, and an explicit PRAXION_DISABLE_OBSERVABILITY=0 is neutral and resolves to standard (user decision 2026-09-26)"
tags: [observability, observations-jsonl, hooks, wal, recording-modes, registry, consumer-contracts, td-261]
made_by: agent
agent_type: systems-architect
branch: worktree-wal-modes-core
pipeline_tier: standard
affected_files:
  - hooks/_hook_utils.py
  - hooks/capture_observations.py
  - hooks/capture_session.py
  - hooks/measure_context_surface.py
  - hooks/remind_calibration.py
  - hooks/send_event.py
  - scripts/spawn_count.py
  - scripts/reconcile_pipeline_state.py
  - scripts/_handoff_readiness.py
  - scripts/check_agent_lifecycle_pairing.py
  - scripts/context_baseline.py
  - scripts/project_metrics/collectors/cost_collector_read.py
  - scripts/workflow_run_cost.py
  - scripts/query_memory_write_evidence.py
  - agents/sentinel.md
affected_reqs: [REQ-01, REQ-02, REQ-03, REQ-04, REQ-05, REQ-06, REQ-07, REQ-08, REQ-09, REQ-10, REQ-15, REQ-16, REQ-17, REQ-18, REQ-19, REQ-20]
dissent: "Five new files and a twelve-file migration to express one mode decision is ceremony; a shared reader plus a three-line mode check in each of four writers closes td-261 and ships the modes with a fraction of the blast radius."
---

## Context

The observation log (`.ai-state/observations.jsonl`, gitignored, rotated at 10 MiB to a single `.1`) has become load-bearing for the spawn budget, the completion handshake, sentinel P03/P04, the cost collector, the handoff gate and the calibration reminder. Its structure has not kept up:

- **Five writer sites, uneven gating.**
  - `capture_observations.py` and `capture_session.py` each check `PRAXION_DISABLE_OBSERVABILITY`.
  - `measure_context_surface.py` carries a private, non-rotating copy of the appender.
  - `_hook_utils.record_gate_fire`, called by six commit gates, **never checks the switch**, so today's "off" still writes `gate_fire` rows.
- **Ten code readers**, each re-implementing JSONL parsing. Four read the `.1` archive; six do not. td-261 names one of them.
- **Consumers known only by grep.** Two consumers the intake re-probe missed read the log as prose or through other means: sentinel P04 groups every `tool_use` row by agent, and `/resume-pipeline` hand-appends a `recovery` row.
- **Recording is all-or-nothing, and the volume is in one class.** Measured over 23,804 rows (2026-08-07 to 2026-09-26), `tool_use` is 73% of rows and 78% of bytes. The user asked for a `full` mode (today), a new default recording what Praxion's artifacts need, and an `off`.

## Decision

**1. One owner package, `hooks/_observation_log/`.** Every writer builds its row and calls the package's writer; every code reader calls the package's reader. `_hook_utils.record_gate_fire` moves into the writer and is re-exported, so the six gate call sites keep their import. The package has four modules:

| Module | Responsibility |
|---|---|
| `modes.py` | Resolves the mode from an env mapping; a pure function |
| `registry.py` | Recording classes, fields, per-mode recording, consumer contracts |
| `writer.py` | The only append path: mode gate, `log_mode` stamp, lock, rotation |
| `reader.py` | The only read path: segments, streamed reads with named degradation, bounded tail, legacy upcast |

**2. Recording modes over recording classes.** Three classes write `event_type: tool_use`: `TOOL_FILE_CHANGE` (Write / Edit / MultiEdit / NotebookEdit, any agent), `TOOL_FIRST_OF_SUBAGENT`, and `TOOL_OTHER`.
- `full` records every class. This is today's behaviour.
- `standard` records every class except `TOOL_OTHER`.
- `off` records nothing, including `gate_fire`.
- The rule `standard` follows: a class is recorded if a built consumer needs it at `standard`, or it is a session-grain measurement series a decision established (`skill_activation`, `compaction`, `context_surface_measurement`). Per-tool-call rows are recorded only where a consumer needs them.
- Measured effect: `standard` keeps 18% of `tool_use` rows and 39% of log bytes, so a 10 MiB rotation holds about 2.5–2.8× more history. The log hooks are async, so no latency claim is made.

**3. First tool call per subagent (Q1).** `standard` records each subagent's first tool call, whatever the tool.
- *Why:* sentinel P03 separates a lost stop (WARN) from an agent that did nothing (`no_tool_use`) by whether the agent has any `tool_use` row. `capture_session`'s own stop-time verdict separates `unobserved-start` from `unobserved-agent` the same way.
- *Mechanism:* "first" is decided by an empty marker file per (log directory identity, `agent_id`) under the user temp directory. The writer appends the row first and creates the marker second, so any failure yields a duplicate row, never a missing one.

**4. Transport (Q4).** A new settings-`env` key, `PRAXION_OBSERVATION_LOG=full|standard|off`, governs only the log. Precedence, highest first:
1. `PRAXION_DISABLE_OBSERVABILITY` truthy means `off`. It stays the umbrella that also silences chronograph posting, `notify_bg_session_state` and the context measurement, exactly as today. The sentinel CI's `--settings` override and the hackathon template's `"1"` therefore keep working unedited.
2. A valid `PRAXION_OBSERVATION_LOG` value is used as given.
3. An invalid non-empty value means `full`, recorded as `log_mode_source: invalid-setting`, so a typo never loses evidence.
4. **(User decision, 2026-09-26)** An explicitly falsy `PRAXION_DISABLE_OBSERVABILITY` (`"0"`, which onboarding writes into managed projects) is neutral: it means "not disabled" and resolves to the default, `standard`. The rejected alternative mapped it to `full`, which would have kept the new default from reaching almost every onboarded project. `PRAXION_OBSERVATION_LOG=full` is the per-project escape hatch, and the release notes name it.
5. Otherwise, `standard`.

**5. Rows declare their mode.** Every appended row carries `log_mode`; the `session_start` row also carries `log_mode_source`. A row without `log_mode` predates modes and reads as `full`. The committed per-session summary carries `log_mode` and omits `tool_calls_by_tool` outside `full`, where the count would be partial.

**6. Consumer contracts are tests.** The registry declares every consumer (code or prompt), the recording classes and fields it needs, and its minimum mode. Three test gates, each with a canary:
- **Consumer-contract test:** fails when `standard` stops recording something a `min_mode: standard` consumer declared.
- **Writer-truth test:** drives every writer in every mode and fails when output disagrees with the registry, including an unregistered `event_type`.
- **Private-reader test:** fails when a Python module outside the package and its named file-level allowlist references the log's filename, and requires every reader importer to be a declared consumer.

**7. Sentinel P04** judges `standard` rows on its write-surface half only, and states that its grant half needs `full`. The harness enforces `tools:` grants for plugin agents, so that half is a backstop.

**Not in this decision:** retention and archives (the reader's `segments()` is the extension point for the following pipeline), worktree-log merge-in, and the log-health sentinel check. Routing `/resume-pipeline`'s prose-written `recovery` row through the writer is a follow-up; it is registered here and read as `full`.

Activation: fired — structural (≈15 production files across hooks, scripts and the sentinel definition, with multiple plausible paths for ownership, the Q1 signal and helper handling); lens set = Security, Performance, Simplicity, Testability; convergence = re-swept (helper handling moved from a count to an event type after measurement; REQs stable after the re-draft; blast radius exceeds the Standard file signal and was surfaced to the orchestrator rather than silently absorbed).

## Considered Options

### Option 1: Owner package with registry, modes, writer and reader (chosen)

- **Pros:** one enforcement point for mode, stamping, rotation and locking, so the `record_gate_fire` class of leak cannot recur. The registry is checked against the code that consults it. Readers cannot drift. The retention pipeline changes one place. Readers never import `fcntl`, and the per-tool-call path never imports the reader.
- **Cons:** five new files; a migration touching every reader in one pipeline; a new subpackage the plugin must ship.

### Option 2: Shared reader only, with a mode check in each writer

- **Pros:** closes td-261 literally with the smallest blast radius; the mode check is about three lines per writer.
- **Cons:** the recording table would exist only as tests over four independent writers, so the one-policy guarantee rests on test coverage rather than structure. This is exactly the pattern (each writer checks the switch itself) under which one writer silently stopped checking.

### Option 3: The same owner as a single file

- **Pros:** one file to find.
- **Cons:** about 550 lines with four reasons to change. Every importer, including scripts on hosts without `fcntl`, loads writer and reader alike.

### Q1 alternatives: transcript existence, or all subagent tool calls

- *Transcript existence:* moves the "did anything" signal into a harness-owned store with ~30-day expiry and no CI presence. It answers "was spawned" rather than "ran a tool", and it cannot serve the writer's stop-time verdict, which reads the log tail.
- *All subagent tool calls:* keeps 77% of tool rows (13,338 of 17,411), too small a saving to justify a mode.

## Consequences

**Positive**
- The log records what named consumers need in the default mode, and every row says so.
- Trimming or extending a mode becomes a registry edit that a test either accepts or refuses.
- Off is actually off.
- Bash and web-tool command summaries — the part of the log most likely to carry a secret — drop by about 82% on disk in `standard`.

**Negative**
- P04's grant half is no longer auditable in the default mode.
- The committed summary's `tool_calls_by_tool` disappears outside `full`.
- A temp-directory marker is the log's first out-of-log state.
- Every onboarded project changes recording granularity at the next plugin release. That is a fleet behaviour change the user approved on 2026-09-26; the release notes name the `full` escape hatch.

## Disconfirmation

- **Falsifier:** any of three findings would make this decision wrong:
  - a built, default-run consumer needs non-file tool rows at per-call grain (the `standard` cut would then be lossy for a live need);
  - the reader migration forces per-reader flags that amount to private readers under another name;
  - the per-tool-call hook's measured CPU rises after the change.
- **Steelmanned runner-up:** Option 2 is genuinely cheaper and closes the named debt.
  - The four writers change rarely, and a writer-truth test can drive all four against a test-only table, so the structural guarantee is partly reproducible by tests alone.
  - If the log's recording policy never grows beyond "drop `TOOL_OTHER` in `standard`", the package is five files guarding one `if`.
  - Its weakness is time. The next pipeline adds archives, merge-in and a health check, and every one of those would then re-open four writers and ten readers instead of one package.
- **Reversal trigger:** revisit if, across the next two log changes, the package's modules always change together (collapse it to one module); if a consumer registered at `min_mode: full` becomes a default-run check; or if a harness-level hook-filtering feature makes per-mode recording expressible in `hooks.json` without runtime code.
