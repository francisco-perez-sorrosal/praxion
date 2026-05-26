# CLI UX Patterns

Help-text design depth, the three-part error message in full, interactive-vs-non-interactive handling, and exit codes. See `cli-output-and-ux.md` for output design rules and exemplar tools. Back to [SKILL.md](../SKILL.md).

---

## Help Text Design

### The Three Levels

Help is a form of progressive disclosure. Users encounter each level at a different point in their CLI journey:

**Level 1 — Short usage** (invoked on wrong/missing args):
- 3–5 lines maximum
- Command name + one-line description
- Required args with angle-bracket syntax
- Hint to `--help`

```
Usage: praxion adr <command> [options]

Commands: create, list, accept, reject, show

Run 'praxion adr --help' for details.
```

**Level 2 — `--help` / `-h`** (explicit help request):
- Full flag listing grouped by function
- **Examples first** — users skip prose and look for examples
- One-line description per flag
- Common use cases covered in examples
- Environment variables if any

```
praxion adr — Manage Architecture Decision Records

USAGE
  praxion adr <command> [options]

COMMANDS
  create <title>   Create a new ADR
  list             List all ADRs
  show <id>        Show an ADR's details
  accept <id>      Mark an ADR as accepted
  reject <id>      Mark an ADR as rejected

EXAMPLES
  # Create a new decision record
  praxion adr create "Use PostgreSQL for persistence"

  # List all accepted ADRs
  praxion adr list --status accepted

  # Show a specific ADR
  praxion adr show dec-NNN --json

OPTIONS
  --status string   Filter by status (proposed|accepted|superseded|rejected)
  --json            Machine-readable JSON output
  --quiet, -q       Suppress informational output
  --no-color        Disable colored output
  --help, -h        Show this help
```

**Level 3 — Man page / docs** (deep reference):
- All flags including obscure ones
- All exit codes with meanings
- All environment variables
- Edge cases and caveats
- Configuration file format
- Full examples including advanced usage

### The Examples-First Rule

Users read examples before prose. Every `--help` output should have an EXAMPLES section placed **before** the OPTIONS section. The examples should be:
- Runnable exactly as shown (no `<required>` placeholders in the example itself)
- Commented with `#` to explain what they do
- Ordered from simplest to most complex
- Representative of the most common use cases

**`jq` as the gold standard**: running `jq` without arguments shows:
```
jq - commandline JSON processor [version 1.7.1]

Usage:    jq [options] <jq filter> [file...]
          jq [options] --args <jq filter> [strings...]
          jq [options] --jsonargs <jq filter> [JSON_TEXTS...]

jq is a tool for processing JSON inputs, applying the given filter to
its JSON text inputs and producing the filter's results as JSON on
standard output.

The simplest filter is ., which copies jq's input to its output
unmodified (except for formatting, but note that IEEE754 is used
for number representation internally).

For the full manual, run:
  jq --help

Basic filters:
  .foo, .foo.bar, .foo?, .[2], .[], .[]?, .[2:7]            Object/array index
  ...
```

Short, oriented, actionable, with a pointer to more. Not a wall of text.

---

## The Three-Part Error Message (Full Treatment)

### Structure

Every error must answer exactly three questions:

```
[1. What went wrong — the direct statement]
[2. Why it failed — the cause]
[3. How to fix it — the exact action]
```

**Minimal well-formed error**:
```
Cannot connect to memory MCP server (localhost:7474).
The server is not running (connection refused on port 7474).
Start it with: memory-mcp start
```

**Extended error with alternatives**:
```
Cannot connect to memory MCP server (localhost:7474).
The server is not running (connection refused on port 7474).

To fix:
  Start the server:   memory-mcp start
  Or skip memory:     set PRAXION_DISABLE_MEMORY_MCP=1

Debug output: praxion --debug will log the full connection attempt.
```

### Grammar Rules

**1. Start with the cause, not the symptom.**

Bad (symptom first): `Failed to execute command.`
Good (cause first): `Cannot write to /var/log/app.log — permission denied.`

The symptom is "failed." The cause is "permission denied." Tell the user the cause.

**2. Use the user's vocabulary, not the system's.**

Bad: `ETIMEOUT: connect ETIMEDOUT 93.184.216.34:443`
Good: `Connection to example.com timed out after 30 seconds.`

The user does not know what `ETIMEOUT` means. They do know what "timed out" means.

**3. Be specific about what was being attempted.**

Bad: `File not found.`
Good: `Config file not found: ~/.praxion/config.yaml`

**4. Give the exact command to fix when possible.**

Bad: `Please configure your API key.`
Good: `API key not set. Run: export PRAXION_API_KEY=<your-key>`

**5. Never print a stack trace as the primary error surface.**

Stack traces belong in debug output (`--debug` flag or a log file). The user who runs `praxion deploy` and sees a 40-line Python stack trace will:
1. Not know what the error is
2. Not know how to fix it
3. Lose confidence in the tool

Log the stack trace. Show the user the three-part error.

### Bad vs Good Examples

| Bad | Good |
|-----|------|
| `Error: 1` | `Config file validation failed: 'output_dir' must be an absolute path.` |
| `ENOENT: no such file or directory, open '/home/user/.config'` | `Config directory not found: /home/user/.config\nCreate it with: mkdir -p /home/user/.config` |
| `TypeError: Cannot read property 'id' of undefined` | `Project not found: 'my-project'. Check 'praxion list' to see available projects.` |
| `Failed.` | `Deployment failed: health check timed out after 60s. The server returned no response. Check logs: praxion logs --tail 50` |

---

## Interactive vs Non-Interactive

### Detection

Always check whether the program is running interactively before using interactive features:

| Language | Check |
|----------|-------|
| Python | `import sys; sys.stdin.isatty()` |
| Node.js | `process.stdin.isTTY` (undefined in non-TTY) |
| Go | `isatty.IsTerminal(os.Stdin.Fd())` |
| Shell | `[ -t 0 ]` — exit 0 if stdin is a TTY |

### Rules in Non-Interactive Mode

**Never prompt**: if the program is run in a script, CI environment, or with piped input, it must not block waiting for user input. Hanging silently is the worst failure mode — the script hangs indefinitely, the CI job times out, and the user has no idea why.

**Fail fast on missing required input**:
```
Error: Required argument <environment> not provided.
       Pass --environment <production|staging|development>
       or set the PRAXION_ENV environment variable.
```

**`--no-input` flag**: provide an explicit way to disable all interactive prompts. This is especially important for tools that might be run interactively by humans but also in CI by scripts.

**Auto-confirm in non-interactive mode**: some tools have a `--yes` / `-y` flag to automatically confirm destructive actions. This is an acceptable pattern for scripts; document it clearly.

### Never Block a Pipe

If your program reads from stdin in interactive mode (e.g., a prompt), it must detect whether stdin is a pipe and handle it appropriately.

Bad behavior: `echo "myfile.txt" | my-tool` → hangs forever waiting for interactive input that will never come

Good behavior: detects non-interactive stdin, falls back to required-arg behavior, fails with a useful error if no arg is provided.

---

## Exit Codes

### Standard Codes

| Code | Meaning |
|------|---------|
| `0` | Success — the command completed its task without errors |
| `1` | General error — an error occurred that doesn't fit a specific code |
| `2` | Misuse — wrong arguments, unrecognized flags, usage error |
| `126` | Permission error — command found but not executable |
| `127` | Command not found |
| `130` | Interrupted — user pressed Ctrl+C (SIGINT) |

### Custom Codes

Custom codes are acceptable and useful — but they **must be documented** in `--help`, the man page, and any CI integration documentation.

| Example Code | Meaning |
|-------------|---------|
| `3` | Nothing to do — command is idempotent and the desired state already exists |
| `4` | Config error — configuration file invalid or missing |
| `5` | Auth error — API key missing or invalid |
| `6` | Not found — specified resource does not exist |

**Convention**: codes 3–9 are unallocated by POSIX and safe for custom use. Avoid codes >100 (they overlap with signal-caused exits: signal N causes exit code 128+N).

### Why Exit Codes Matter

Scripts check exit codes:
```bash
praxion adr accept dec-NNN
if [ $? -ne 0 ]; then
  echo "ADR acceptance failed" >&2
  exit 1
fi
```

A tool that returns `0` on failure is a trap for every script that calls it. A tool with undocumented custom codes is equally treacherous.

### Signal Handling

On SIGINT (Ctrl+C), SIGTERM (graceful shutdown signal):
1. Clean up in-progress operations (delete temp files, close connections)
2. Print a brief message if in TTY: `^C Interrupted.`
3. Exit with code `130` (for SIGINT) or `143` (for SIGTERM = 128+15)

Do not let Ctrl+C cause unclean exits that leave partial state behind.
