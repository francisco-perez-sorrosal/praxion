# Live scenario envelope fixtures

Eleven `*.stream.jsonl` files here are **verbatim** `claude -p --output-format
stream-json --verbose` captures recorded on **2026-09-24** with Claude Code
CLI **2.1.281**.

Four come from the isolation probes:

- `isolated_marker_preflight_sonnet.stream.jsonl`
- `spawn_selection_standard_opus.stream.jsonl`
- `ambient_control_sonnet.stream.jsonl`
- `subagent_implementer_background_sonnet.stream.jsonl`

Seven come from `eval/scripts/record_live_envelopes.py` (one run, $2.00 total) —
four scenario shapes on Opus and three error shapes on Sonnet:

- `ui_step_conformance.stream.jsonl`, `adr_authoring.stream.jsonl`,
  `commit_staging.stream.jsonl`, `lightweight_fix.stream.jsonl`
- `error_budget_stop.stream.jsonl` — `result` subtype `error_max_budget_usd`; the
  session was given `--max-budget-usd 0.01` and still cost $0.10, because the CLI
  checks the budget after a turn, not before it
- `error_invalid_credential.stream.jsonl` — `result` subtype `success` with
  `is_error: true`; the error is carried by `is_error`, not by the subtype
- `error_invalid_flag.stream.jsonl` — empty: an unknown option exits non-zero
  before any event is written

The four scenario captures also record real `permission_denials` (a compound
`cd … && pytest | tail` command, and reads of the plugin copy's skill files from
outside the session's working directory) — kept as recorded, because the parser
must handle them.

The recorder ran each session in its own sandbox under the system temp
directory, so these seven carry no home-directory paths and needed no
substitution.

## Command shape

Each was produced by one of the recording probe scripts, invoking `claude`
with the shape:

```
claude -p <prompt> --model <sonnet|opus> [--effort medium] \
       --output-format stream-json --verbose \
       --plugin-dir <materialized-copy> \
       --strict-mcp-config --mcp-config '{"mcpServers":{}}' \
       [--json-schema {tier, agents}] [--permission-prompts none] \
       --max-budget-usd <n> [--debug-file <path>]
```

`ambient_control_sonnet.stream.jsonl` is the one negative-control capture:
same prompt and same `--plugin-dir` copy, but run with the real ambient
`HOME` and environment instead of a per-session sandbox — it is expected to
show the isolation breach (extra plugins, live MCP servers) the isolation
checker must detect.

## Substitution applied

Exactly one shape-preserving substitution was applied to each of the four probe captures before
committing: the recording machine's absolute home-directory prefix
`/Users/fperez` was replaced with `/Users/operator`, and the bare username
token `fperez` appearing inside path strings derived from that prefix (both
the `/Users/fperez/...` slash form and the `-Users-fperez-...` dash-encoded
transcript-directory form) was replaced with `operator`. Nothing else was
edited — event ordering, session ids, nonce values, tool-use payloads, and
every other field are byte-for-byte as recorded.
