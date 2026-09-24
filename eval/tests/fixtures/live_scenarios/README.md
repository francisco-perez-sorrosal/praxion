# Live scenario envelope fixtures

Four `*.stream.jsonl` files here are **verbatim** `claude -p --output-format
stream-json --verbose` captures recorded on **2026-09-24** with Claude Code
CLI **2.1.281**:

- `isolated_marker_preflight_sonnet.stream.jsonl`
- `spawn_selection_standard_opus.stream.jsonl`
- `ambient_control_sonnet.stream.jsonl`
- `subagent_implementer_background_sonnet.stream.jsonl`

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

Exactly one shape-preserving substitution was applied to every copy before
committing: the recording machine's absolute home-directory prefix
`/Users/fperez` was replaced with `/Users/operator`, and the bare username
token `fperez` appearing inside path strings derived from that prefix (both
the `/Users/fperez/...` slash form and the `-Users-fperez-...` dash-encoded
transcript-directory form) was replaced with `operator`. Nothing else was
edited — event ordering, session ids, nonce values, tool-use payloads, and
every other field are byte-for-byte as recorded.
