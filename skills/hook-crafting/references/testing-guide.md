# Hook Testing Guide

How to test hooks during development, debug registration issues, and verify hooks are firing.

## Manual Pipe Testing

Test hook scripts directly by piping JSON input:

```bash
# PreToolUse — simulate a git commit
echo '{"hook_event_name":"PreToolUse","tool_name":"Bash","tool_input":{"command":"git commit -m test"},"session_id":"test","cwd":"/tmp"}' | python3 .claude-plugin/hooks/check_code_quality.py
echo "Exit code: $?"

# PostToolUse — simulate a Python file write
echo '{"hook_event_name":"PostToolUse","tool_name":"Write","tool_input":{"file_path":"/tmp/test.py","content":"def foo( x,y ): pass"},"session_id":"test","cwd":"/tmp"}' | python3 .claude-plugin/hooks/format_python.py
echo "Exit code: $?"

# SessionStart
echo '{"hook_event_name":"SessionStart","source":"startup","session_id":"test","cwd":"/tmp"}' | python3 .claude-plugin/hooks/my_hook.py
```

**Environment variables** to set before testing:
```bash
export CLAUDE_PROJECT_DIR="/path/to/project"
export CLAUDE_PLUGIN_ROOT="/path/to/praxion"
```

## Debug Mode

Run Claude with debug output to see hook execution:

```bash
claude --debug
```

Debug output shows:
- Which hooks are registered and from which source
- Hook execution start/end with timing
- Input JSON sent to hooks
- Output JSON received from hooks
- Exit codes and stderr

## /hooks Menu

Inside a Claude session, type `/hooks` to see a read-only browser of all active hooks. Shows:
- Event → matcher → hook command
- Source (user settings, project settings, plugin)
- Configuration details (timeout, async, if condition)

## Verbose Mode

Toggle hook output visibility in the transcript with `Ctrl+O`. When enabled, stderr from hooks appears inline in the conversation.

## Common Debugging Scenarios

### Hook doesn't fire at all

1. **Check registration**: `grep hook_name ~/.claude/settings.json`
2. **Check plugin status**: `claude plugin list` — is the plugin enabled?
3. **Check matcher**: Does the matcher match the tool name? `"Write"` doesn't match `"Edit"`.
4. **Check `if` field**: Remove the `if` field temporarily to test without argument filtering.
5. **Check file exists**: Is the script path correct? `ls -la /path/to/hook.py`
6. **Check permissions**: `chmod +x hook.py` (not always needed for `python3 hook.py`, but check)

### Hook fires but has no effect

1. **Check async**: Async hooks can't deliver `additionalContext` or block. Set `"async": false`.
2. **Check exit code**: Exit 0 for success/feedback, exit 2 for blocking. Other codes are silent errors.
3. **Check JSON output**: Use `python3 -c "import json; json.loads(open('/dev/stdin').read())"` to validate.
4. **Check stderr vs stdout**: Blocking messages go to stderr. Context injection goes to stdout JSON.

### Hook blocks but Claude stops instead of fixing

1. **Known bug #24327**: Claude sometimes treats exit 2 as "stop" rather than "fix and retry".
2. **Try clearer stderr**: Make the error message actionable — tell Claude exactly what to fix.
3. **Verify the tool**: Some tools ignore exit 2 (#26923 for Task, #13744 for Write/Edit).

### Hook causes errors in unrelated tool calls

1. **Check matcher scope**: `"matcher": ""` matches ALL tools. Use specific matchers.
2. **Check fail-open**: Does the hook exit 0 on internal errors? Add try/except wrapper.
3. **Check stdin consumption**: The hook must read all stdin even if it exits early.

## Testing Checklist

Before committing a new hook:

- [ ] Manual pipe test with representative input JSON
- [ ] Verify exit code 0 on success path
- [ ] Verify exit code 2 on blocking path (if applicable)
- [ ] Verify exit 0 on internal error (fail-open)
- [ ] Verify stdin is fully consumed in all paths
- [ ] Test with non-matching input (wrong tool name, wrong file extension)
- [ ] Verify JSON output is valid (no stray print statements)
- [ ] Check no shell profile text leaks into output
- [ ] Run `claude --debug` with a real session to verify activation
