---
diataxis: how-to
audience: developer
---

# Switch a role to its kernel

Recipes for the lean-spawn mechanism: regenerate the kernels, put a role on trial, flip it or hold it, read a `kernel_injected` row and run the liveness check. For what each part is and why, see [Lean spawn: role kernels and the adoption ledger](lean-spawn-kernels.md).

Run commands from the repository root.

## Regenerate the kernels after a rule or agent change

```bash
python3 scripts/generate_kernels.py          # write claude/kernels/, the agent blocks and the preamble
python3 scripts/generate_kernels.py --check  # write nothing; exit 1 when anything on disk is stale
python3 scripts/check_kernel_manifest.py     # the commit gate: manifest, kernels, ledger
```

A new section in an always-loaded source needs an entry in `rules/_audience.yaml`; the checker names the unclassified section. Never edit the generated files under `claude/kernels/` (only the authored texts under `claude/kernels/src/`) or the three universal blocks inside an agent definition by hand: the next regeneration overwrites them.

## Put a role on trial

1. Pick a role from the `eligible` list in `.ai-state/kernel_adoption.yaml`.
2. Add a record under `roles:`, in the block layout the hook reads line by line:

   ```yaml
   roles:
     researcher:
       status: trial
       since: 2026-10-14T09:00:00Z
       runs: []
   ```

   Use the current instant for `since`: spawns before it are not judged. Keep this layout (two-space role, four-space unquoted `status`): the gate refuses a record the hook would read differently (`I10-hook-misread`).
3. Commit through the gate. From this commit the hook delivers the role's kernel at every spawn, followed by the project's root `CLAUDE.md`, in which only a line that is wholly `@<relative path>` is expanded, one level deep, resolved from the project root and never inside fenced code (close every fence: one left open inside a list item stays open here to the end of the file, where the harness closes it with the item); an inline `@path` and deeper imports stay as written. The definition is unchanged, so the role also still inherits the project instructions.
4. Spawn the role once and confirm its row (below).

## Run the sessions on a subscription

A paired run launches dozens of headless sessions, and each bills whatever credential it finds. To bill a Claude subscription instead of API credits, make a long-lived token in your own terminal with `claude setup-token`, save it to a file only you can read (for example `~/.claude/praxion-session-token`, mode 600) and name that file on the run:

```bash
praxion-evals-adherence --role verifier --arm full --arm lean --required-pairs 20 --judge-golden \
  --session-oauth-token-file ~/.claude/praxion-session-token --max-total-usd 200
```

Every session then carries the token as `CLAUDE_CODE_OAUTH_TOKEN` and no API key; the runner's own process keeps the key for the judge, which runs on the Messages API and costs cents. A dry run shows the effect in each session's `env_names`. The cost figures a subscription session reports are Claude Code's estimates, not charges, so the run cap bounds an estimate; note that in the run's ledger comment. A subscription has usage windows: if a run is throttled mid-way its remaining sessions error out and the run is listed like any other, so run one role at a time and leave headroom.

## Record a run

After each adherence run, append it to the role's `runs` with its `id`, `complete_pairs`, `passes_flip_rule` and `entry`. A run that does not pass stays recorded and the role stays at `trial`. The list only grows: the gate refuses a commit that drops, reorders or rewrites a recorded run (`I9-ledger-runs-rewritten`).

## Flip a role to `switched`

Flip only on a run of at least 20 complete pairs that passes the flip rule, with the startup probe read before and after for the role's first request, and with the user's ratification in hand.

1. Take both readings with the same profile:

   ```bash
   python3 scripts/measure_startup_payload.py agent:researcher --strict-mcp-config --plugin-dir . --json
   ```

2. In one commit, change the ledger record and the definition together. The record:

   ```yaml
   researcher:
     status: switched
     since: 2026-10-14T09:00:00Z
     runs: [{id: <run id>, complete_pairs: 20, passes_flip_rule: true, entry: <entry>}]
     passing_run: <run id>
     probe_before_tokens: <reading>
     probe_after_tokens: <reading>
     flip_rule_ratified: true
     flip_ratified: true
   ```

   The definition: add `omitClaudeMd: true` to the frontmatter of `agents/researcher.md` and change nothing else.
3. The gate refuses the commit when the flag has no `switched` record, when a `switched` record has no flag, when an evidence field is missing or a ratification is not `true`, or when the move is not one the ledger allows (`switched` is reached only from `trial`). Fix the reported finding; no switch turns the gate off.

State a reading with its profile (model, setting sources, MCP mode, plugin directory). Readings compare only within one profile.

## Hold a role

Hold a role when its trial closes without a flip: its run failed the flip rule, or no run can reach 20 complete pairs. A held role receives nothing at spawn, keeps inheriting the project instructions and is not judged by `--liveness`, so it costs what it cost before the trial.

1. In one commit, change only the record's `status` and add a `reason` naming why the trial closed. Keep `since` (the closed trial's start) and every run, in order:

   ```yaml
   verifier:
     status: held
     since: 2026-10-14T02:32:49Z
     runs:
       - id: <run id>
         complete_pairs: 24
         passes_flip_rule: false
         entry: praxion-evals-adherence
     reason: the flip rule did not pass on the forced-stop check
   ```

   A role with no run may be held with `runs: []`. Quote a reason that contains `: `, or YAML cannot read the ledger and the gate stops with an input error. The definition is unchanged: a held role never carries `omitClaudeMd`.
2. The gate refuses a held record with no `reason` (`I9-record-incomplete`), a run added while the role stays held (`I9-ledger-held-run-added`), a move to `held` from anything but `trial`, and any move from `held` but back to `trial` (`I9-ledger-transition`).

To re-open a held role, set `status: trial` with a new `since`, keep every run and drop the `reason`. The `since` is the re-opened trial's own start: the gate refuses a re-opening with no `since` (`I9-ledger-reopen-no-since`), one at or before the commit it follows, the held record's old start included (`I9-ledger-reopen-before-parent`), and one later than the re-opening commit itself (`I9-ledger-reopen-after-commit`). Use the current instant. The liveness check judges a re-opened trial from the commit that re-opened it, so a spawn made while the role was held is never reported, whatever `since` the record carries; a plugin root without git history cannot place a re-opening, so its adopted roles are judged from their recorded start and named as unplaced in the report. Record the next run only after the re-open commit.

## Read a `kernel_injected` row

Each delivering spawn leaves one row in the project's observation log. Find the latest:

```bash
grep '"event_type":"kernel_injected"' .ai-state/observations.jsonl | tail -n 3
```

| Field | Meaning |
|---|---|
| `role`, `agent_type`, `agent_id`, `session_id` | which spawn received the kernel |
| `kernel_version` | the full version of the kernel text delivered |
| `strings` | one entry per string delivered, in slot order: `module` (a module label, or `project-claude-md`), `part` (the project-file part number, else `null`) and `chars` (UTF-16 units, the unit of the harness cap) |
| `project_file` | `{chars, parts, omitted}` for the project's `CLAUDE.md`, or `null` when none was delivered; a non-zero `omitted` means the role was told to read the file for the rest |

A spawn that received nothing leaves no row.

## Read the transcript marker

The first line of every injected string is `[praxion <8 hex> #<slot>]`. The hex is the first eight characters of `kernel_version`; the slot is the string's place. A role owed N strings shows markers `#1` to `#N` in its context, each once, in any order. Use the marker where no observation log exists, as in a sandboxed eval session.

The marker is recorded in the role's own transcript, `<config dir>/projects/<cwd, every / and . as ->/<session id>/subagents/agent-<agent id>.jsonl`, never in the parent session's `stream-json`. Look for the `attachment` record of type `hook_additional_context` with `hookEvent` `SubagentStart`: its `content` lists every delivered string. Each hook command also leaves a `hook_success` record whose `stdout` holds that hook's JSON output.

## Run the liveness check

```bash
python3 scripts/check_kernel_manifest.py --liveness
python3 scripts/check_kernel_manifest.py --liveness --since <rev> --json
```

It reads the observation log under the repository root and the plugin's ledger, then judges each spawn of a role at `trial` or `switched`. A spawn counts from its role's `since` (and from the commit time of `--since`, when given) and is an agent's first `agent_start`; a resume is never judged. A spawn with no `kernel_injected` row for its agent id is a `liveness-missing-row` finding: the hook did not run for it. `--plugin-root DIR` names the plugin checkout whose ledger lists the adopted roles.

The report states how many spawns of how many adopted roles it judged, so a clean report over zero spawns reads as such. A log it cannot find or read whole is an input error (exit 2), never a pass. Exit 0 clean, 1 findings.

## When the hook is absent

Agents keep working. Every definition still carries the three universal blocks, the Codex wrappers embed the kernel, and the Cursor rules export is unchanged. A role at `trial` or `switched` whose spawns leave no row is what `--liveness` exists to catch.
