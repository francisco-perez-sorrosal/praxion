# Multi-Session Workflows

Praxion ships **`praxion-parallel`** — a single-entry launcher for N parallel Claude Code sessions in native Warp tabs or iTerm2 tabs, each isolated in its own git worktree, each visually distinguished by per-tab color, optionally with per-session role assignment via `--append-system-prompt`. It comes with two surfaces: a **bash CLI** (the engine) and an **ephemeral web launcher** (`praxion-parallel --ui`) that composes the same engine via a form-driven UI with reusable recipes.

The launcher replaces the legacy `ccwt` (which was tmux-bound and limited to existing worktrees) and is complementary to — not a replacement for — `scripts/dispatch-reworks`, which serves a different purpose (verifier-loop rework dispatch with hook-based notifications).

## Contents

- [When to use it](#when-to-use-it)
- [Quick start](#quick-start)
- [The web launcher](#the-web-launcher)
- [Recipes](#recipes)
- [CLI reference](#cli-reference)
- [After launch](#after-launch)
- [Examples](#examples)
- [Troubleshooting](#troubleshooting)
- [Design rationale](#design-rationale)

## When to use it

Reach for `praxion-parallel` when:
- A task decomposes into 2+ independent streams (an implementer + a test-engineer; an auth feature + a billing feature + a docs pass).
- You want to compare alternative implementations of the same change in parallel worktrees.
- You're running unattended overnight work and need both a primary session and a watcher.

Skip it when:
- The work is sequential and a single Claude session is enough.
- You're dispatching the verifier rework loop — use [`scripts/dispatch-reworks`](rework-dispatch.md) instead.
- You're on a tier (Direct, Lightweight, Spike) where a single session captures the whole scope.

The practical ceiling is **2–3 concurrent sessions for most developers** ([per the community consensus](https://www.mindstudio.ai/blog/claude-code-git-worktrees-parallel-agents)); the launcher caps at 6.

## Quick start

```bash
# CLI: spawn 3 fresh worktrees in Warp, one tab each, auto-approve
praxion-parallel -n 3 -y

# Web UI: opens a localhost form with the recipe gallery
praxion-parallel --ui
```

The first form is for muscle memory; the second is for templating + per-session role assignment.

## The web launcher

`praxion-parallel --ui [PROJECT]` boots an ephemeral Python `http.server` on `127.0.0.1:<random-port>`, prints a single-use 32-byte URL token, opens your default browser, and self-terminates on first successful launch (or after 10 min idle).

The single page composes a multi-session launch:

| Section | What it sets |
|---|---|
| **Project & backend** | Project path, terminal (Warp / iTerm2), layout (Tabs / Windows), worktree mode (New / Existing / None), `worktree.baseRef`, `--yolo`, per-tab colors |
| **Recipe** | Pick a named template; preview its sessions inline (colored swatches + per-tab tasks); fork a built-in or save your current state as a new recipe |
| **Sessions** | Per-session row: worktree name, claude-session `/color`, initial task prompt (pre-typed), per-session `--append-system-prompt` (role pin) |
| **Run** | Dry-run (compose-and-print) or Launch |

After clicking **Launch**, the server exec's `praxion-parallel` with the composed argv, the terminal opens N tabs, and the launcher exits. Subsequent launches require a fresh `praxion-parallel --ui` invocation — there is no persistent daemon.

### Security model

- **Bound to `127.0.0.1` only** — never `0.0.0.0`. Cannot be reached from another host.
- **32-byte URL-safe single-use token** — every API endpoint enforces it; wrong token returns `401`.
- **Self-termination** — exits 1.5s after first successful launch, or after 10 min idle, or `^C` in the launching terminal.
- **No persistent daemon** — every invocation is fresh.

The launcher writes recipes to `~/.config/praxion-parallel/recipes.json`; project-local recipes live in `<project>/.praxion/recipes.json` (committed to the repo).

## Praxion-aware mode

When the launcher targets a **Praxion-managed project** (any directory with a committed `.ai-state/` tree), the UI switches to **Praxion-aware mode** and the recipe semantics simplify dramatically. Praxion-managed projects already have:

- All Praxion agents loaded (`@researcher`, `@implementer`, `@test-engineer`, `@verifier`, etc.) with their full contracts
- The behavioral-contract rule auto-loaded into every session
- The agent-coordination protocol auto-loaded
- The full skills/rules ecosystem

In that context, repeating a sliver of an agent's contract via `--append-system-prompt` (`"You are the implementer. Surface assumptions..."`) is **redundant** — the @implementer agent's full contract is already in scope. Praxion-aware mode replaces it with a per-session **agent identity**.

### How it works

A small **`Praxion-aware`** chip appears in the launcher header when `.ai-state/` is detected. Each session row gains an **Agent** dropdown listing all discovered agents (project `agents/*.md` > marketplace cache > hardcoded fallback of 15). The `system_prompt` field collapses behind an **"Advanced: custom system prompt"** disclosure — most users never need it.

When you pick an agent for a session:

1. **Worktree name auto-fills** from the agent name (`implementer`, `test-engineer`, ...). You can still override it by typing.
2. **System prompt auto-derives** at submit time using a stable template:
   ```
   Operate as the Praxion @<agent> agent for this session. Honor the agent's
   contract from agents/<agent>.md, including its tool-permission scope,
   output format, and pipeline boundaries. Apply the four behavioral-contract
   behaviors throughout.
   ```
3. **The Advanced override still wins.** If you put text in the Advanced disclosure, that wins and the agent template is ignored.

### Praxion-aware recipe schema

Add a top-level `praxion_aware: true` marker and a per-session `agent` field:

```json
{
  "name": "team-lead",
  "description": "Praxion mini-pipeline fan-out…",
  "praxion_aware": true,
  "terminal": "warp",
  "worktrees": "new",
  "sessions": [
    {"agent": "researcher",              "task": "Explore…",   "claude_color": "cyan"},
    {"agent": "implementation-planner",  "task": "Decompose…", "claude_color": "magenta"},
    {"agent": "implementer",             "task": "Execute…",   "claude_color": "blue"},
    {"agent": "verifier",                "task": "Review…",    "claude_color": "yellow"}
  ]
}
```

Note: `name`, `system_prompt` per session are optional when `agent` is present. The launcher fills them at submit time. Built-in recipes that are Praxion-pipeline-tied (`implement-and-test`, `team-lead`, `overnight-autonomous`) ship this shape; generic recipes (`solo-work`, `compare-implementations`, `feature-fan-out`) stay in the simpler shape and work on any project.

### Agent discovery

Agents are discovered at runtime in this order; the first directory with `*.md` files wins:

1. `<project>/agents/` — working on Praxion itself (or any project shipping its own agents).
2. `~/.claude/plugins/cache/i-am/agents/` — marketplace install.
3. `~/dev/praxion/agents/` — dev install via `praxion-claude-dev`.

If none are found, a hardcoded fallback of 15 well-known Praxion agents is used so the dropdown is never empty.

### When to use generic recipes anyway

Even on a Praxion-managed project, generic recipes (no `agent`, just `system_prompt` or nothing) still make sense for:
- **Comparing implementations** — three sessions with different *approach* prompts, none of which map to a pipeline agent role
- **Feature fan-out** — three independent feature streams that all use the same `@implementer` agent
- **Solo work** — a single session with no specific role
- **Custom roles** — when you want a role that doesn't match any Praxion agent (e.g., "you are an SRE on call")

## Recipes

A recipe is a named template that captures backend config plus N session definitions (name, task, system prompt, color). Recipes ship at three precedence layers:

```
builtin  <  user  <  project        (project wins on name clash)
```

| Layer | Path | Purpose |
|---|---|---|
| **Built-in** | `scripts/praxion_parallel_ui_assets/recipes-builtin.json` | Ships with Praxion; cannot be edited or deleted; can be shadowed |
| **User** | `~/.config/praxion-parallel/recipes.json` | Personal recipes, written by the **Save** button |
| **Project** | `<project>/.praxion/recipes.json` | Team-committed recipes; shared across the team via git |

The launcher labels each recipe with its origin (`[builtin]` / `[user]` / `[project]`) in the dropdown, and the Delete button refuses built-ins (Fork them instead) and project recipes (edit the file in-repo).

### Built-in recipes

| Name | Mode | Sessions | Use when |
|---|---|---|---|
| `solo-work` | generic | 1 | Quickest path to a clean Claude on a side task |
| `implement-and-test` | praxion-aware | 2 (@implementer + @test-engineer) | TDD-style pair on the same task slug |
| `team-lead` | praxion-aware | 4 (@researcher / @implementation-planner / @implementer / @verifier) | Mini-pipeline fan-out on a feature |
| `compare-implementations` | generic | 3 (A / B / C) | Explore alternative approaches to the same change |
| `feature-fan-out` | generic | 3 (auth / billing / docs) | Three independent feature streams |
| `overnight-autonomous` | praxion-aware | 2 (@implementer + @sentinel) | Unattended long-running work with read-only oversight |

### Recipe schema

```json
{
  "name": "implement-and-test",
  "description": "One impl + one test-engineer on the same task slug.",
  "terminal": "warp",
  "layout": "tabs",
  "worktrees": "new",
  "base_ref": "head",
  "yolo": false,
  "no_color": false,
  "sessions": [
    {
      "name": "impl",
      "task": "Read .ai-work/<slug>/WIP.md and implement the assigned step.",
      "system_prompt": "You are the implementer. Surface assumptions; stay surgical.",
      "claude_color": "blue"
    },
    {
      "name": "tests",
      "task": "Read .ai-work/<slug>/WIP.md and write the matching test cases.",
      "system_prompt": "You are the test-engineer. Behavior-driven, isolated, deterministic.",
      "claude_color": "green"
    }
  ]
}
```

### Project-local recipes

Drop a JSON array at `<project>/.praxion/recipes.json` and commit it. Your team picks up the recipes the next time anyone runs `praxion-parallel --ui` on that project. Same-named project recipes shadow user recipes and built-ins. Useful for company-specific role descriptions (e.g., a `team-lead` recipe with team-specific system prompts encoding internal conventions).

## CLI reference

The launcher engine is `scripts/praxion-parallel`. Symlinked into `~/.local/bin/` by the installer.

```
praxion-parallel [PROJECT] [OPTIONS]

ARGUMENT
  PROJECT                  Project directory. One of:
                             - absolute path (/path/to/proj)
                             - relative-with-slash (./proj)
                             - bare name (proj) → $PRAXION_DEV_DIR/proj
                                                  (default $HOME/dev/proj)
                           Default: current working directory.

OPTIONS
  -n, --count N            1..6 (default 2)
  -t, --terminal T         warp (default) | iterm2
  -y, --yolo               Pass --dangerously-skip-permissions to each session
  -w, --worktrees MODE     new (default) | existing | none
      --names a,b,c        Explicit worktree names (overrides --count)
      --base-ref REF       fresh (default origin/HEAD) | head (local HEAD)
      --tasks "T1|T2|..."           Per-session initial prompts (pipe-sep)
      --append-system-prompts "P1|P2|..."  Per-session role pins (pipe-sep)
      --ui [PROJECT]       Launch the web launcher instead
      --layout LAYOUT      tabs (default) | windows
      --no-color           Skip palette
      --dry-run            Print plan, no spawn
      --list               List existing worktrees and exit
  -h, --help               Show help
```

### Worktree modes

| Mode | Behavior |
|---|---|
| `new` (default) | One fresh worktree per session via `claude --worktree <name>`. Claude Code creates each under `.claude/worktrees/<name>/`. Auto-cleanup on empty exit. |
| `existing` | Discovers via `git worktree list`. One session per existing worktree. Caps `--count` at the actual number found. |
| `none` | All sessions in the project root. **Edit conflicts likely** — loud warning printed. Useful only for read-only or unrelated workloads. |

### Layouts

| `--layout` | Meaning |
|---|---|
| `tabs` (default) | One window, N tabs. Both backends. |
| `windows` | N separate windows, one session each. Both backends. |
| `panes` | One window, one tab, N rectangular split panes. **N=1..4 only** (denser panes become unreadable). Both backends. |

**Panes tilings:**
- N=2: side-by-side (vertical split)
- N=3: one tall left pane + two stacked panes on the right
- N=4: 2×2 grid

### Warp modes (`--warp-mode`)

The Warp backend has two paths because of upstream Warp bug [#9007](https://github.com/warpdotdev/warp/issues/9007) — `commands:` / `exec:` blocks are silently dropped when a Launch Configuration is invoked via `warp://launch/<name>` from the command line. Tabs/panes open at the right `cwd`, but the `claude --worktree …` command never runs.

| `--warp-mode` | What happens | Trade-off |
|---|---|---|
| `launch-config` (default) | Writes a YAML to `~/.warp/launch_configurations/`, opens `warp://launch/<name>`. Autonomous when it works. | Subject to #9007 (commands may silently fail). A fallback block is always printed with the exact manual command, the YAML path, and a workaround pointer. The YAML is preserved 30s by default; pass `--keep-config` to keep it indefinitely for debugging. |
| `tabs` | Opens `warp://action/new_tab?path=<cwd>` per tab. Reliably opens N tabs at the right cwds; prints the `claude --worktree …` command for each so you can paste-and-Enter. | Not fully autonomous — one paste per tab. But it always works. Does not support `--layout=panes`; falls back to flat tabs. |

If `launch-config` mode opens tabs but nothing runs in them, **switch to `--warp-mode=tabs`**. The iTerm2 backend is unaffected by #9007 — it uses AppleScript directly.

### What gets passed to each session

```bash
claude --worktree <name> \
       [--dangerously-skip-permissions] \
       --name <project-basename>/<name> \
       [--append-system-prompt "<role pin>"] \
       [<task prompt>]
```

The `--name` flag tags the session in `claude agents` so you can find it later in another pane.

## After launch

Once the tabs are open:

- **Tab switching** — Warp: `⌘1` / `⌘2` / …; iTerm2: `⌘1` / `⌘2` / … per tab, `⌘⇧[` / `⌘⇧]` to walk.
- **Second visual layer (auto-injected when task is empty)** — each session's `claude_color` is auto-injected as the first user message via Claude Code's `/color <name>` slash command (Claude Code v2.1.75+) **only when the task field is empty**. When both color and task are set, the launcher sends just the task. Rationale: `/color`'s argument parser is greedy (`$ARGUMENTS` captures everything after the command name including newlines), so a multi-line `/color blue\n<task>` sets color to the literal string `"blue\n<task>"` and is rejected as invalid — confirmed empirically against Claude Code 2.1.158. The launcher surfaces a yellow inline hint in any session row where both are set; type `/color X` yourself after claude starts. The swatch dot in the UI tracks the dropdown live regardless.
- **Auto-cleanup** — when you exit a session with no uncommitted changes, no untracked files, and no new commits, Claude Code removes the worktree and its branch automatically. Sessions with changes prompt you to keep or discard.
- **`.env` copying** — add `.worktreeinclude` (gitignore syntax) to your project root to have Claude Code copy gitignored config files (`.env`, `.env.local`, etc.) into each new worktree automatically.

## Examples

### TDD pair on a step

```bash
praxion-parallel -n 2 \
  --names impl,tests \
  --tasks "Read WIP.md step 7.3 and implement|Read step 7.3 and write tests" \
  --append-system-prompts "You are the implementer.|You are the test-engineer."
```

Equivalent in the web launcher: load the **implement-and-test** recipe, click Launch.

### Comparing three implementations

```bash
praxion-parallel -n 3 \
  --names approach-a,approach-b,approach-c \
  --tasks "Implement via refactor|Implement via new abstraction|Implement via extension" \
  --append-system-prompts "Bias toward minimal refactor.|Bias toward new abstraction.|Bias toward minimum change."
```

### Overnight autonomous

```bash
praxion-parallel -n 2 \
  --names primary,watcher \
  -y \
  --tasks "Continue the long-running task in WIP.md|Periodically run sentinel and report drift" \
  --append-system-prompts "Stop and report any operation you'd hesitate to do under supervision.|Read-only audits only."
```

⚠ Auto-approve combined with unattended sessions is a real risk — keep them on isolated worktrees with no shared resources (no shared DB, no shared ports). The recipe `overnight-autonomous` encodes these constraints.

### Attaching to existing worktrees

```bash
praxion-parallel --worktrees existing
```

Discovers via `git worktree list`, spawns one session per existing worktree. Useful when you've already created worktrees by hand or via `/create-worktree` and want to fan out Claude across them.

## Troubleshooting

<details>
<summary><strong>Warp: "Launched N sessions" printed but nothing visible / tabs opened with no claude running</strong></summary>

Two distinct failure modes, both rooted in Warp's URL-launch behavior:

**Failure mode A — nothing opens at all** (the "cold-start race"). `open` returns exit 0 the moment macOS hands the URL to LaunchServices; it does not wait for Warp to actually process it. If Warp was mid-startup, mid-update, or otherwise busy, the URL is dropped silently and the script's success message is misleading. The launcher already activates Warp via `open -a Warp` + a 400ms pause before sending the launch URL to minimize this, but a slow start can still miss.

**Failure mode B — tabs open at the right cwd but the `claude` command never runs**. This is upstream Warp bug [#9007](https://github.com/warpdotdev/warp/issues/9007): the `commands:` / `exec:` block inside a Launch Configuration YAML is silently dropped when the config is invoked via `warp://launch/<name>` from `open`. Manually invoking the same Launch Configuration from Warp's Command Palette works fine.

**Recovery, in order:**

1. **Manual relaunch**: the script always prints `open "warp://launch/<name>"` ready to copy. Run it again — Warp is now warm, so the URL usually lands.
2. **Open from Warp's UI**: ⌘P → "Launch Configuration" → pick the `praxion-parallel-…` entry. This path bypasses the URL handler and #9007 doesn't apply, so commands run.
3. **Switch modes**: `praxion-parallel --warp-mode=tabs …` — opens one tab per session via `warp://action/new_tab?path=…` (which doesn't have #9007) and prints the `claude --worktree …` command for you to paste-and-Enter. Reliable. Doesn't support `--layout=panes` (panes need the launch-config YAML path).
4. **Inspect the YAML**: use `--keep-config` to preserve the YAML indefinitely, then `python3 -c "import yaml; print(yaml.safe_load(open('<path>')))"` to verify it parses cleanly.

</details>

<details>
<summary><strong>"project '<name>' has no commits — <code>claude --worktree</code> cannot create a worktree"</strong></summary>

The pre-flight check caught a fresh `git init` with no commits yet. Claude Code's `--worktree` flag needs at least one commit in the project so it has a base ref to branch from; an unborn HEAD produces the cryptic upstream error "Failed to resolve base branch 'HEAD': git rev-parse failed".

Fix in the target project:

```bash
cd <project-root>
git commit --allow-empty -m 'init'
```

Then retry the launch. Alternatively, use `--worktrees=existing` (after creating worktrees by hand) or `--worktrees=none` (all sessions share the project root — no isolation).

</details>

<details>
<summary><strong>The web launcher returns <code>TypeError: Object of type bytes is not JSON serializable</code> (historical, fixed)</strong></summary>

Surfaced once during real-world testing; fixed in the same commit that added the pre-flight check. Root cause: the bash script's background cleanup subshell (the 30-second sleep that deletes the ephemeral Warp launch config) inherited the parent's stdout/stderr pipes, blocking the Python launcher's `subprocess.run` from seeing the script actually finish. That hit the launcher's 30-second `timeout=30`, raising `TimeoutExpired` whose `.stdout`/`.stderr` came back as bytes → `json.dumps` blew up.

Fix on the bash side: redirect every background subshell to `/dev/null` (`( sleep 30 && rm -f "$lc_path" ) >/dev/null 2>&1 &`) so the pipes close immediately when the script exits. Defensive fix on the Python side: `_ensure_str()` coerces bytes to str at the boundary so the JSON encoder is unconditionally safe.

If you see this error on a later version, capture the request body and file an issue.

</details>

<details>
<summary><strong>iTerm2 backend: "AppleScript syntax error"</strong></summary>

The launcher generates AppleScript via heredoc and feeds it to `osascript -e`. If you see a syntax error, dump the generated script by replacing `osascript` with a wrapper:

```bash
mkdir -p /tmp/probe && cat > /tmp/probe/osascript <<'SH'
#!/bin/bash
echo "$2" | tee /tmp/script.applescript
exec /usr/bin/osascript "$@"
SH
chmod +x /tmp/probe/osascript
PATH="/tmp/probe:$PATH" praxion-parallel -t iterm2 -n 2 --dry-run
```

Then validate the dumped script with `osacompile -e "$(cat /tmp/script.applescript)" -o /tmp/out.scpt`.

</details>

<details>
<summary><strong>The launcher's <code>/api/state</code> returned <code>401</code></strong></summary>

Every API endpoint requires the URL token from the launcher's stdout. If you're calling endpoints via `curl`, make sure the `?t=<token>` (or `&t=<token>` if you already have a query string) is present. The browser handles this automatically because it reads the token from the initial URL.

</details>

<details>
<summary><strong>"praxion-parallel-ui: assets dir missing"</strong></summary>

The launcher resolves its assets via `os.path.realpath(__file__)`. If you symlinked `praxion-parallel-ui` to `~/.local/bin/` and renamed the asset directory, the resolution will fail. The asset dir must remain `<scripts>/praxion_parallel_ui_assets/` next to the launcher's original location.

</details>

<details>
<summary><strong>Auto-approve in a parallel run made unrelated changes across worktrees</strong></summary>

`--yolo` passes `--dangerously-skip-permissions` to every session. Combined with unattended work, this can produce cross-worktree side effects via shared resources (databases on default ports, global config files, `~/.config/<tool>/` writes). Use `overnight-autonomous` only on isolated infrastructure — separate DB schemas, Docker container per worktree, per-tab `.env` overrides via `.worktreeinclude`.

</details>

## Design rationale

- **`claude --worktree <name>` owns worktree creation.** The launcher does not call `git worktree add` — Claude Code creates the worktree, applies `.worktreeinclude`, and cleans up empty exits. The launcher only orchestrates the terminal spawn.
- **Warp Launch Configuration vs URI scheme.** Warp's `warp://action/new_tab?path=...` can open a tab in a directory but **cannot run a command** ([upstream limitation](https://github.com/warpdotdev/warp/issues/5859)). The launcher writes an ephemeral [Launch Configuration](https://docs.warp.dev/terminal/sessions/launch-configurations/) YAML — which **can** carry a `commands:` block — and invokes `warp://launch/<name>` instead.
- **iTerm2 OSC-6 tab colors.** AppleScript [cannot set iTerm2 tab colors directly](https://gitlab.com/gnachman/iterm2/-/issues/6172). The launcher sends iTerm2-proprietary OSC-6 escape sequences (`\033]6;1;bg;...;brightness;<v>\a`) into each session's first `printf` after `claude` starts, achieving per-tab color via the session itself.
- **No daemon.** The launcher is ephemeral by design — one shot, one launch, one exit. Persistent dashboards (CloudCLI, claude-code-monitor) serve a different need (monitoring); the launcher is pre-flight configuration only.
- **One engine.** The web UI composes args and exec's `praxion-parallel` — there's no second copy of the spawn logic. Bugs are fixed in one place.

## Related

- [`scripts/praxion-parallel --help`](../scripts/praxion-parallel) — authoritative CLI reference
- [`scripts/praxion-parallel-ui`](../scripts/praxion-parallel-ui) — launcher source
- [`scripts/CLAUDE.md`](../scripts/CLAUDE.md) — scripts catalog
- [Claude Code worktree docs](https://code.claude.com/docs/en/worktrees) — `--worktree`, `.worktreeinclude`, `WorktreeCreate` hooks
- [Dispatching Reworks](rework-dispatch.md) — the verifier-loop dispatcher (`scripts/dispatch-reworks`), sibling to `praxion-parallel` for the rework-only case
