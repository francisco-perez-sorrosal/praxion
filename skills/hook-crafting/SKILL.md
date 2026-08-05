---
name: hook-crafting
description: >
  Creating, testing, and registering Claude Code hooks: hook events, registration
  lifecycle, output patterns (additionalContext, updatedInput, decision), gotchas,
  installer integration; automated code quality, observability, security gates,
  workflow enforcement. Triggers: creating new hooks, debugging hook execution,
  fixing hook registration, choosing hook types, why a hook is not firing.
allowed-tools: [Read, Write, Edit, Glob, Grep, Bash]
compatibility: Claude Code
staleness_sensitive_sections:
  - "Quick Reference: Events"
  - "Hook Types"
  - "Gotchas"
  - "Known Bugs"
staleness_threshold_days: 60
---

# Hook Crafting

Hooks are shell commands, prompts, or agents that Claude Code executes in response to lifecycle events (tool calls, session start, subagent spawn, etc.). They enable automated enforcement that doesn't depend on the LLM remembering to follow rules.

**Satellite files** (loaded on-demand):

- [../skill-crafting/references/context-engineering-foundations.md](../skill-crafting/references/context-engineering-foundations.md) -- the shared "why" (`additionalContext` is injected tokens — keep hook output minimal and high-signal)
- [references/event-reference.md](references/event-reference.md) -- the hook events with input schemas and blocking semantics
- [references/output-patterns.md](references/output-patterns.md) -- JSON output formats: additionalContext, decision, permissionDecision, updatedInput
- [references/registration-guide.md](references/registration-guide.md) -- Where hooks live, how they get loaded
- [references/testing-guide.md](references/testing-guide.md) -- Manual testing, debugging, environment setup

**Relationship to built-in skill**: Use `plugin-dev:hook-development` for writing hook scripts (prompt vs command types, security best practices, matcher patterns, bash validation examples). Use this skill for everything around the scripts: registration lifecycle, why hooks don't fire, output patterns (`additionalContext`, `updatedInput`, `decision`), the `if` conditional field, the many lifecycle events the built-in skill doesn't document, known bugs, and installer integration. The built-in skill tells you how to write a hook; this skill tells you how to ship one.

## When a Hook (vs a Rule)

The dividing line is **guarantee strength**, not topic:

- A behavior that must happen **100% of the time, with zero exceptions** → **hook**. Hooks are deterministic and lifecycle-executed: the harness runs them, not the model.
- A behavior the model **should generally follow** → **rule** (or a `CLAUDE.md` line). `CLAUDE.md` and rules are delivered as context, not enforced config — there's no guarantee of strict compliance.

**Rules shape behavior; hooks enforce it.** The robust pattern is often *both*: a rule documents the convention so the model understands *why*, and a `PreToolUse` / `PostToolUse` hook makes the load-bearing part non-negotiable so a forgetful or adversarial run can't skip it. Don't reach for a hook when a rule will do — hooks are heavier to maintain and a misfiring hook blocks the agent (see [Gotchas](#gotchas)). But when correctness depends on it firing every time, a rule is the wrong tool.

For the rules-vs-`CLAUDE.md`-vs-skills decision, see the [`rule-crafting`](../rule-crafting/SKILL.md) skill; for writing the hook script itself, `plugin-dev:hook-development`.

## Gotchas
<!-- last-verified: 2026-08-05 -->

Hard-won lessons from production use. Read these before writing or debugging hooks.

- **Exit 0 with no output is NOT approval.** It means "no decision, proceed normally." To actually block, `exit 2` or emit JSON `decision: "block"` / `permissionDecision: "deny"`. A gate that just `exit 0`s when it should block is a silent no-op. Exit-2 feedback is read from **stderr** — redirect there (`>&2`); error text sent to stdout on a block is dropped.
- **Exec form avoids injection.** A handler with an `args` array runs without a shell (no interpolation) — prefer it with `${...}` path placeholders for anything touching untrusted input. A bare `command` string runs in a shell; you own the quoting.
- **Plugin hooks auto-discover from the repo root.** Hooks placed at `<repo-root>/hooks/hooks.json` are auto-discovered by Claude Code when the plugin is installed. The `hooks.json` file at the plugin root is the single source of truth — do NOT also register hooks in `~/.claude/settings.json`, as that causes double-firing.

- **Async hooks cannot deliver feedback — unless they use `asyncRewake`.** A hook with `"async": true` runs in the background, and its output is delivered on the *next* conversation turn; if the session is idle it waits for the next user interaction. Use sync for anything that must inject context or block a tool call. The one exception: `"asyncRewake": true` (implies `async`) **wakes Claude on exit code 2**, showing the hook's stderr — or stdout if stderr is empty — as a system reminder, even when the session is idle. That is the tool for reporting a long-running background failure.

- **JSON decision output is only honored on exit 0.** `permissionDecision`, `decision`, and every other JSON output field are parsed only when the hook exits 0. On exit 2 Claude Code ignores stdout entirely and reads stderr instead. A hook that emits `permissionDecision: "deny"` *and* exits 2 has its JSON discarded — pick one mechanism: exit 2 with stderr text, or exit 0 with JSON.

- **Consume all stdin.** Every hook receives JSON on stdin. If the script doesn't read all of stdin, the pipe breaks and Claude Code logs an error. Pattern: `raw = sys.stdin.read()` at the top, even if you don't use the data.

- **Shell profile text corrupts JSON.** If `~/.zshrc` or `~/.bashrc` contains unconditional `echo` or `printf` statements, they inject text before the hook's JSON output. Guard startup text with `[[ $- == *i* ]]` (interactive shell check).

- **`if` field silently fails on non-tool events.** The `if` conditional (`"if": "Bash(git *)"`) is evaluated only on the five tool events: `PreToolUse`, `PostToolUse`, `PostToolUseFailure`, `PermissionRequest`, and `PermissionDenied`. Adding `if` to other events (SessionStart, Stop, etc.) prevents the hook from running entirely with no error.

- **`if` is best-effort and fails *open*.** When the Bash command can't be parsed, the filter runs your hook regardless of pattern. Never use `if` as a security boundary — upstream is explicit: "use the permission system rather than a hook to enforce a hard allow or deny."

- **`stop_hook_active` prevents infinite loops — and there is a hard backstop.** A Stop hook that returns `decision: "block"` creates a self-correcting loop: Claude responds → Stop fires → blocks → Claude continues → Stop fires again. Check `stop_hook_active` in the input JSON — when true, Claude Code is already continuing because of a stop hook, so exit 0 to let it stop. Independently, **Claude Code overrides the hook and ends the turn after 8 consecutive blocks**. `additionalContext` goes through the same protections (the `stop_hook_active` input and the 8-consecutive-continuation cap) but labels the transcript entry `Stop hook feedback` and shows no hook-error notice — prefer it when the hook is working as designed rather than reporting a fault.

- **Verify that a block actually blocked.** For critical gates, confirm the effect rather than trusting the exit code, and phrase stderr as actionable feedback. The four hook bugs this skill previously tracked are all now closed — see [references/event-reference.md](references/event-reference.md#known-bugs) for their dispositions and the one that turned out to be a documentation gap rather than a defect.

- **Single registration authority.** All hooks are registered in `hooks/hooks.json` at the repo root, using `${CLAUDE_PLUGIN_ROOT}` for portable paths. Claude Code auto-discovers this file. Do NOT duplicate hooks into `~/.claude/settings.json` — that causes double-firing and path portability issues.

## Registration Lifecycle

Hooks can be defined in 6 locations. They are additive (merged, not overridden):

| Location | Scope | When to Use |
|----------|-------|-------------|
| `<repo-root>/hooks/hooks.json` | Plugin enabled | **Auto-discovered** — single source of truth for plugin hooks |
| `~/.claude/settings.json` | All projects | User-wide hooks (formatting, observability) |
| `.claude/settings.json` | This project | Project-specific hooks (committed to git) |
| `.claude/settings.local.json` | This project | Local-only hooks (gitignored) |
| Managed policy | Organization | Org-enforced hooks |
| Skill/agent frontmatter | Component lifetime | Scoped to skill activation or agent spawn |

**For Praxion hooks**: All hooks live in `hooks/hooks.json` at the repo root and are auto-discovered by Claude Code. Do NOT also register in `~/.claude/settings.json`. See [references/registration-guide.md](references/registration-guide.md) for the hook structure.

## Hook Types
<!-- last-verified: 2026-08-05 -->

| Type | Async? | Feedback? | Use When |
|------|--------|-----------|----------|
| `command` | **Yes** | Yes | Running scripts, formatters, linters |
| `prompt` | No | Yes | LLM-based validation (style checks, safety) |
| `agent` | No | Yes | Complex multi-step verification (reads files, runs commands) — **experimental** |
| `http` | No | Yes | Forwarding events to an external endpoint (must return 2xx + `decision:block` in the body to block) |
| `mcp_tool` | No | Yes | Invoking an MCP tool as the hook handler |

**Only `type: "command"` supports `async`** (and therefore `asyncRewake`). Upstream is
explicit: "Prompt-based hooks can't run asynchronously." Marking an `http` or `mcp_tool` hook
async does not make it async. Note also that `SessionStart` and `Setup` accept only
`command` and `mcp_tool` handlers.

Prefer `command` for deterministic checks (formatting, linting). Use `prompt` when the check requires LLM judgment. Use `agent` when verification needs to read files or run commands — but it is documented as experimental and may change.

**Default timeouts are modulated per event, so the flat numbers mislead.** Base defaults are
600s (`command`/`http`/`mcp_tool`), 30s (`prompt`), 60s (`agent`). But `UserPromptSubmit`
lowers command/http/mcp_tool to **30s**, `MessageDisplay` to **10s**, and `SessionEnd` hooks
share a **1.5-second budget** (raised to match a longer per-hook `timeout`, up to 60s). A
`SessionEnd` hook written against a 600s expectation has 1.5s.

A `shell` field selects `"bash"` or `"powershell"` (defaults to bash, or powershell on Windows
without Git Bash). It is **ignored when `args` is set**, since the exec form spawns no shell.

## Design Patterns

### Fail-Open

Hooks must never block the agent due to their own bugs. Wrap the entire main function in try/except:

```python
if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass  # exit 0 — never block
```

### Auto-Fix Then Gate

For code quality hooks: fix what you can automatically, then only block on what's unfixable.

```
1. Run formatter in fix mode (ruff format)
2. Run linter in fix mode (ruff check --fix)
3. Re-stage fixed files (git add)
4. Run checks again — block only if violations remain
```

### Delegating Hook

Keep hook scripts thin — delegate to heavier packages:

```python
result = subprocess.run(
    ["uv", "run", "--project", package_path, "python", "-m", "module", "subcommand"],
    input=raw, capture_output=True, text=True, timeout=25,
)
sys.exit(result.returncode)
```

### Observability (Fire-and-Forget)

Async hooks that POST events to an HTTP API. Never fail, never block:

```python
try:
    urllib.request.urlopen(req, timeout=5)
except Exception:
    pass
```

### Self-Correcting Loop (Stop Hook)

Force Claude to continue working until a condition is met:

```python
data = json.loads(sys.stdin.read())
if data.get("stop_hook_active"):
    sys.exit(0)  # CRITICAL: prevent infinite loop
# ... check conditions ...
if not conditions_met:
    print(json.dumps({"decision": "block", "reason": "Tests not run"}))
    sys.exit(2)
```

## Quick Reference: Events
<!-- last-verified: 2026-08-05 -->

**31 events** grouped by phase — the surface keeps growing, so cross-check the live [hooks reference](https://code.claude.com/docs/en/hooks). See [references/event-reference.md](references/event-reference.md) for full schemas.

**Before tool execution**: PreToolUse, PermissionRequest (can block); PermissionDenied (no block)
**After tool execution**: PostToolUse, PostToolUseFailure (no block); PostToolBatch (can block)
**Session lifecycle**: Setup (**cannot block**), SessionStart, SessionEnd, Stop (can block), StopFailure, PreCompact (can block), PostCompact
**Subagent lifecycle**: SubagentStart, SubagentStop (can block)
**Task lifecycle** (can block): TaskCreated, TaskCompleted
**User interaction**: UserPromptSubmit (can block), UserPromptExpansion (can block), Notification, MessageDisplay (no block), Elicitation (can block), ElicitationResult (can block)
**Environment**: ConfigChange (can block), CwdChanged, DirectoryAdded (no block), FileChanged, InstructionsLoaded
**Worktree**: WorktreeCreate (can block on any non-zero), WorktreeRemove
**Team**: TeammateIdle (can block)

**`Setup` cannot block** — this is the one event whose blocking behavior is easy to get
backwards. Upstream: "Setup hooks can't block. Any non-zero exit code, including 2, surfaces
stderr to the user as a `<hook name> hook error` notice, and execution continues." Setup is
context-only; its `hookSpecificOutput.additionalContext` adds context with no decision
control. If you need a gate at session start, `Setup` is not it.

**`MessageDisplay`** (fires while assistant message text is displayed; carries its own
`hookSpecificOutput.displayContent` and a 10s default timeout) and **`DirectoryAdded`** (fires
when a working directory is added mid-session via `/add-dir` or the SDK
`register_repo_root` control request) are the two events most often missed — neither can block.

## Sync vs Async Decision

| Need | Use |
|------|-----|
| Block a tool call or commit | Sync (`"async": false`) |
| Inject context via `additionalContext` | Sync |
| Return `decision: "block"` | Sync |
| Fire-and-forget logging/observability | Async (`"async": true`) |
| Auto-format silently (no feedback) | Either — async avoids latency |

**Key rule**: If the hook's value depends on Claude seeing its output, it must be sync.
