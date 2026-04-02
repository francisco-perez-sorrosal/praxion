# Hook Safety Contract

Behavioral contract for each hook in the Praxion plugin ecosystem. Documents what each hook reads, writes, contacts externally, and guarantees NOT to do. Use this contract to verify hook behavior during security reviews.

Back-link: [Context Security Review Skill](../SKILL.md)

## Contract Summary

| Hook | Event(s) | Reads | Writes | External Contact | Fail Mode |
|------|----------|-------|--------|-----------------|-----------|
| `send_event.py` | SessionStart, Stop, SubagentStart, SubagentStop, PostToolUse, PostToolUseFailure | stdin (JSON payload) | None (files) | localhost only (Chronograph HTTP) | Fail-open (exit 0) |
| `commit_gate.sh` | PreToolUse (Bash) | stdin (JSON payload) | None | None | Fail-open (exit 0) |
| `check_code_quality.py` | PreToolUse (Bash, commit-gated) | stdin, staged files via `git diff` | Staged files via `git add` | None | Fail-open (exit 0), blocks on unfixable violations (exit 2) |
| `extract_decisions.py` | PreToolUse (Bash, commit-gated) | stdin (JSON payload) | `.ai-state/decisions.jsonl` (via decision-tracker) | Anthropic API (via decision-tracker) | Fail-open (exit 0) |
| `format_python.py` | PostToolUse (Write\|Edit) | stdin, target Python file | Target Python file (formatted) | None | Fail-open (exit 0) |
| `precompact_state.py` | PreCompact | stdin, `.ai-work/` pipeline docs | `.ai-work/PIPELINE_STATE.md` | None | Fail-open (exit 0) |

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

### `extract_decisions.py`

**Purpose**: Extract architectural/implementation decisions from the conversation context at commit time. Delegates to the `decision-tracker` package.

**Reads**:
- stdin: JSON hook payload (includes command string)
- Environment: `CLAUDE_PLUGIN_ROOT` (to locate decision-tracker)

**Writes**:
- `.ai-state/decisions.jsonl` (via decision-tracker subprocess)
- stderr (diagnostic messages)

**External contact**:
- **Anthropic API** (via the decision-tracker's `anthropic` SDK) -- sends git diff and conversation context for LLM-based decision extraction
- Requires `ANTHROPIC_API_KEY` in environment

**Guarantees NOT to do**:
- Never contacts any endpoint other than Anthropic's API
- Never stores or logs the API key
- Never modifies source code files
- Never blocks commits due to extraction failure (fail-open)
- Skips entirely if `uv` or `ANTHROPIC_API_KEY` is not available

### `format_python.py`

**Purpose**: Auto-format Python files after Write or Edit tool use via `ruff format`.

**Reads**:
- stdin: JSON hook payload
- Target Python file (to snapshot before formatting)

**Writes**:
- Target Python file (formatted in place via `ruff format`)
- stdout: JSON `additionalContext` message when formatting changes occurred

**External contact**:
- None

**Guarantees NOT to do**:
- Never contacts any network endpoint
- Never reads or writes files other than the specific file from the tool use
- Never processes non-Python files (skips silently)
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

## Verification Guidance

When reviewing a PR that modifies hooks, verify against these contracts:

1. **New external endpoints**: Any URL that is not `localhost` or `127.0.0.1` is a FAIL
2. **New file reads**: Compare against the "Reads" section -- new file access outside the documented scope is suspicious
3. **New file writes**: Compare against the "Writes" section -- new file writes are suspicious
4. **Removed fail-open**: Removing `exit 0` or bare `except` patterns that ensure fail-open behavior is a WARN
5. **New subprocess calls**: Any new `subprocess.run`, `os.system`, or `os.popen` should be reviewed for command injection
6. **New environment variable access**: Especially `ANTHROPIC_API_KEY`, `GITHUB_TOKEN`, or other credential variables
