# Hook Safety Contract

Behavioral contract for each hook in the Praxion plugin ecosystem. Documents what each hook reads, writes, contacts externally, and guarantees NOT to do. Use this contract to verify hook behavior during security reviews. Back to [SKILL.md](../SKILL.md).

## Contract Summary

| Hook | Event(s) | Reads | Writes | External Contact | Fail Mode |
|------|----------|-------|--------|-----------------|-----------|
| `send_event.py` | SessionStart, Stop, SubagentStart, SubagentStop, PostToolUse, PostToolUseFailure | stdin (JSON payload) | None (files) | localhost only (Chronograph HTTP) | Fail-open (exit 0) |
| `commit_gate.sh` | PreToolUse (Bash) | stdin (JSON payload) | None | None | Fail-open (exit 0) |
| `check_code_quality.py` | PreToolUse (Bash, commit-gated) | stdin, staged files via `git diff` | Staged files via `git add` | None | Fail-open (exit 0), blocks on unfixable violations (exit 2) |
| `adr_reminder.py` | PreToolUse (Bash, commit-gated) | stdin (JSON payload), `.ai-state/decisions/` (file listing) | None | None | Fail-open (exit 0) |
| `remind_calibration.py` | PreToolUse (Bash, commit-gated), Stop | stdin (JSON payload), `.ai-state/observations.jsonl`, `.ai-state/calibration_log.md` via `git diff` | `.ai-state/observations.jsonl` (one `gate_fire` row per Stop reminder) | None | Fail-open (exit 0); a Stop reminder forces one continuation turn, at most once per session |
| `format_code.py` | PostToolUse (Write\|Edit) | stdin, `_lang_tools.py` registry, target source file | Target source file (formatted) | None | Fail-open (exit 0) |
| `precompact_state.py` | PreCompact | stdin, `.ai-work/` pipeline docs | `.ai-work/PIPELINE_STATE.md` | None | Fail-open (exit 0) |
| `capture_observations.py` | PostToolUse (all tools; a fixed noise blocklist is skipped) | stdin (JSON payload), `.ai-state/` (existence + `stat`), `$TMPDIR` first-call markers (existence) | Observation log (`.ai-state/observations.jsonl`, its `.1` rotation archive, `.ai-state/observations.lock`); empty `0o600` digest-named first-call markers under `$TMPDIR` | None | Fail-open (exit 0), async |
| `capture_session.py` | SessionStart, Stop, SubagentStart, SubagentStop, PostCompact | stdin (JSON payload), observation-log tail, session and subagent transcripts (usage fields only), `.ai-state/observations_summary.jsonl` | Observation log (as above); committed `.ai-state/observations_summary.jsonl` (+ `.ai-state/observations_summary.lock`, transient `.tmp` sibling) | None | Fail-open (exit 0), async |
| `measure_context_surface.py` | SessionStart | stdin (JSON payload), always-loaded surface (project and `~/.claude` `CLAUDE.md` + unscoped rules, `settings.json` excludes, rules manifest), `ANTHROPIC_API_KEY` | Observation log (as above) -- one measurement row | `api.anthropic.com` token-count endpoint, only when `ANTHROPIC_API_KEY` is set | Fail-open (exit 0), async |

## Individual Hook Contracts

### `send_event.py`

**Purpose**: Forward Claude Code lifecycle events to the local Task Chronograph server for observability.

**Reads**:
- stdin: JSON hook payload (session_id, agent_id, tool_name, tool_input, tool_output, hook_event_name, cwd)
- Environment: `CHRONOGRAPH_PORT` (optional override), `CLAUDE_PROJECT_DIR` (fallback)

**Writes**:
- No file writes
- HTTP POST to `http://localhost:{port}/api/events` and `/api/interactions`
- stderr on failure (diagnostic messages)

**External contact**:
- `localhost` only -- port derived from project directory hash (range 8765-9764)
- Uses `urllib.request` (stdlib), no external network calls

**Guarantees NOT to do**:
- Never contacts any host other than `localhost`/`127.0.0.1`
- Never writes to the filesystem
- Never reads files from disk (only stdin)
- Never stores or logs the raw hook payload to disk
- Never blocks agent execution (exit 0 unconditionally on all errors)
- Redacts secret patterns from tool input/output summaries before transmission

### `commit_gate.sh`

**Purpose**: Fast-path filter for PreToolUse hooks. Checks if the Bash command is a `git commit` before delegating to Python hooks, avoiding ~200-500ms Python startup on non-commit commands.

**Reads**:
- stdin: raw JSON payload (consumed via `cat`)

**Writes**:
- None

**External contact**:
- None

**Guarantees NOT to do**:
- Never modifies any files
- Never contacts any network endpoint
- Never executes anything except `grep` and the delegated Python script
- Never blocks non-commit Bash commands (exit 0 immediately)

### `check_code_quality.py`

**Purpose**: Run `ruff format` and `ruff check --fix` on staged Python files before git commit. Re-stages auto-fixed files.

**Reads**:
- stdin: JSON hook payload
- Staged file list via `git diff --cached --name-only`
- Staged file content (for formatting)

**Writes**:
- Staged Python files (auto-formatted in place via `ruff format`)
- Git staging area (`git add` for reformatted files)
- stderr (diagnostic messages)

**External contact**:
- None

**Guarantees NOT to do**:
- Never contacts any network endpoint
- Never reads or writes files outside the git staging area
- Never modifies non-Python files
- Never blocks commits due to its own internal errors (bare except, exit 0)
- Only blocks commits (exit 2) when unfixable ruff violations remain

### `adr_reminder.py`

**Purpose**: Emit a warning when architectural files are committed without a corresponding ADR file dated today. Nudges agents to document decisions as ADR files.

**Reads**:
- stdin: JSON hook payload (includes command string)
- `.ai-state/decisions/` directory listing (checks for ADR files with today's date in frontmatter)
- Staged file list via `git diff --cached --name-only`

**Writes**:
- stderr (warning message when no matching ADR found)

**External contact**:
- None

**Guarantees NOT to do**:
- Never contacts any network endpoint
- Never writes to the filesystem (read-only check)
- Never modifies source code or ADR files
- Never blocks commits (exit 0 unconditionally)
- Never requires any API keys or external dependencies

### `format_code.py`

**Purpose**: Auto-format source files after Write or Edit tool use, dispatching on file extension through the `_lang_tools.py` registry (the registry names the formatter, how to resolve it on this machine, and its argv).

**Reads**:
- stdin: JSON hook payload
- The `_lang_tools.py` registry (in-process import, sibling module)
- Target source file (to snapshot before formatting)

**Writes**:
- Target source file (formatted in place by the registry-resolved formatter)
- stdout: JSON `additionalContext` message when formatting changes occurred

**External contact**:
- None

**Guarantees NOT to do**:
- Never contacts any network endpoint
- Never reads or writes files other than the specific file from the tool use
- Never processes files whose extension has no registry row (skips silently)
- Never errors when the registry-resolved formatter is unreachable on this machine -- an unresolvable tool is a silent no-op
- Never blocks agent execution (exit 0 unconditionally)

### `precompact_state.py`

**Purpose**: Snapshot pipeline document state before context compaction so agents can restore orientation.

**Reads**:
- stdin: hook payload (consumed to avoid broken pipe)
- `.ai-work/` directory tree: first 20 lines of each pipeline document

**Writes**:
- `.ai-work/PIPELINE_STATE.md` (condensed snapshot)

**External contact**:
- None

**Guarantees NOT to do**:
- Never contacts any network endpoint
- Never reads files outside `.ai-work/`
- Never writes files outside `.ai-work/`
- Never modifies pipeline documents (read-only access)
- Never blocks compaction (exit 0 unconditionally)

### `capture_observations.py`

**Purpose**: Append one observation row per completed tool call to the local observation log, classified by pattern matching (no LLM calls).

**Reads**:
- stdin: JSON hook payload (tool_name, tool_input, tool_response error/additionalContext, session_id, agent_id, agent_type, cwd)
- `.ai-state/` directory: existence check and `stat` (device + inode key the first-call marker)
- `$TMPDIR` first-call marker: existence check, subagent calls only
- Environment: `PRAXION_DISABLE_OBSERVABILITY`, `PRAXION_OBSERVATION_LOG` (recording mode), `TMPDIR` / `TEMP` / `TMP`

**Writes**:
- `.ai-state/observations.jsonl` -- one appended JSON line per recorded call, mode-gated
- `.ai-state/observations.jsonl.1` -- rotation archive; the active log is renamed onto it at 10 MiB
- `.ai-state/observations.lock` -- empty `fcntl` lock file
- `<tmp>/praxion-observation-log-first-call-<16 hex>` -- first-call marker: empty, created `O_CREAT | O_EXCL` with mode `0o600`; `<tmp>` is the first of `TMPDIR`, `TEMP`, `TMP`, else `/tmp` (created if absent); the name is a SHA-256 digest of the `.ai-state/` device, inode and agent id. Created only after a subagent's first tool-use row (or a file-changing one) has been written; never for the main agent, never in `off` mode

**External contact**:
- None

**Guarantees NOT to do**:
- Never contacts any network endpoint
- Never records file contents or tool output -- rows carry tool-input fragments truncated to 200 characters (Bash description or command text, file paths, Agent description or prompt preview, query / pattern / url values)
- Never redacts secrets from those fragments -- the raw log and its archive are local-only (gitignored), never committed
- Never writes marker content, and never opens or follows a pre-existing path at the marker location (`O_EXCL`)
- Never deletes its markers -- they are left to the OS temp-directory reaper
- Never blocks agent execution (async; exit 0 unconditionally)

### `capture_session.py`

**Purpose**: Record session, subagent and compaction lifecycle rows in the observation log, and upsert a per-session rollup into a committed summary file at every Stop.

**Reads**:
- stdin: JSON hook payload (hook_event_name, session_id, agent_id, agent_type, description, transcript_path, trigger, compact_summary length, cwd)
- Observation log: a bounded tail (512 KiB) for agent-type backfill and start pairing; at Stop, the current segment's rows for this session
- Transcripts: the Stop payload's `transcript_path` tail (1 MiB) for suspended-subagent notifications; at SubagentStop, the subagent's own transcript (parent transcript as fallback), streamed for usage, model and timestamps only
- `.ai-state/observations_summary.jsonl` (to upsert)
- Environment: `PRAXION_DISABLE_OBSERVABILITY`, `PRAXION_OBSERVATION_LOG`

**Writes**:
- `.ai-state/observations.jsonl`, its `.1` rotation archive, and `.ai-state/observations.lock` -- as for `capture_observations.py`: lifecycle rows, helper-stop rows, compaction rows, and backfilled stop rows for suspended subagents
- `.ai-state/observations_summary.jsonl` -- **committed**; one aggregate row per session, rewritten atomically via a `.tmp` sibling under `.ai-state/observations_summary.lock`; skipped in `off` mode

**External contact**:
- None

**Guarantees NOT to do**:
- Never contacts any network endpoint
- Never copies transcript or compaction-summary text into any row -- a compaction row records only the summary's length
- Never writes anything but aggregates to the committed summary (counts, token sums, model names, timestamps, pipeline slug) -- no commands, paths or summaries
- Never blocks agent execution (async; exit 0 unconditionally)

### `measure_context_surface.py`

**Purpose**: At session start, measure the always-loaded context surface and record it as one observation row.

**Reads**:
- stdin: JSON hook payload (hook_event_name, session_id, agent_id, agent_type, cwd)
- The always-loaded surface, via the sibling `scripts/measure_token_budget.py` (imported through `sys.path`): project `CLAUDE.md` and unscoped rules, `~/.claude/CLAUDE.md` and unscoped `~/.claude/rules/**`, `claudeMdExcludes` from project and user `settings.json`, the rules manifest and the hook-delivered rules it names
- Environment: `PRAXION_DISABLE_OBSERVABILITY`, `PRAXION_OBSERVATION_LOG`, `ANTHROPIC_API_KEY`, `CLAUDE_PLUGIN_ROOT`

**Writes**:
- `.ai-state/observations.jsonl`, its `.1` rotation archive, and `.ai-state/observations.lock` -- one measurement row (token and byte counts, basis, measured file paths)

**External contact**:
- Only when `ANTHROPIC_API_KEY` is set: HTTPS POST to `https://api.anthropic.com/v1/messages/count_tokens`, carrying the concatenated always-loaded text and the key. Without a key, or on any network error, it falls back to a local byte-ratio estimate

**Guarantees NOT to do**:
- Never contacts any endpoint other than the fixed token-count URL, and never contacts it without `ANTHROPIC_API_KEY`
- Never writes the token-budget baseline (that is the commit-gate ratchet's)
- Never blocks the session (async; exit 0 unconditionally)

## Verification Guidance

When reviewing a PR that modifies hooks, verify against these contracts:

1. **New external endpoints**: Any URL that is not `localhost` or `127.0.0.1` is a FAIL unless that hook's contract lists it under "External contact" (today only `measure_context_surface.py`'s token-count call)
2. **New file reads**: Compare against the "Reads" section -- new file access outside the documented scope is suspicious
3. **New file writes**: Compare against the "Writes" section -- new file writes are suspicious
4. **Removed fail-open**: Removing `exit 0` or bare `except` patterns that ensure fail-open behavior is a WARN
5. **New subprocess calls**: Any new `subprocess.run`, `os.system`, or `os.popen` should be reviewed for command injection
6. **New environment variable access**: Especially `ANTHROPIC_API_KEY`, `GITHUB_TOKEN`, or other credential variables
