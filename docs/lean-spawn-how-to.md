---
diataxis: how-to
audience: developer
---

# Switch a role to its kernel

Recipes for the lean-spawn mechanism: regenerate the kernels, put a role on trial, flip it, read a `kernel_injected` row and run the liveness check. For what each part is and why, see [Lean spawn: role kernels and the adoption ledger](lean-spawn-kernels.md).

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

## Record a run

After each adherence run, append it to the role's `runs` with its `id`, `complete_pairs`, `passes_flip_rule` and `entry`. A run that does not pass stays recorded and the role stays at `trial`.

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
3. The gate refuses the commit when the flag has no `switched` record, when a `switched` record has no flag, when an evidence field is missing or a ratification is not `true`, or when the move skips a rung. Fix the reported finding; no switch turns the gate off.

State a reading with its profile (model, setting sources, MCP mode, plugin directory). Readings compare only within one profile.

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

## Read the in-stream marker

The first line of every injected string is `[praxion <8 hex> #<slot>]`. The hex is the first eight characters of `kernel_version`; the slot is the string's place. A role owed N strings shows markers `#1` to `#N` in its context, each once, in any order. Use the marker where no observation log exists, as in a sandboxed eval session.

## Run the liveness check

```bash
python3 scripts/check_kernel_manifest.py --liveness
python3 scripts/check_kernel_manifest.py --liveness --since <rev> --json
```

It reads the observation log under the repository root and the plugin's ledger, then judges each spawn of a role at `trial` or `switched`. A spawn counts from its role's `since` (and from the commit time of `--since`, when given) and is an agent's first `agent_start`; a resume is never judged. A spawn with no `kernel_injected` row for its agent id is a `liveness-missing-row` finding: the hook did not run for it. `--plugin-root DIR` names the plugin checkout whose ledger lists the adopted roles.

The report states how many spawns of how many adopted roles it judged, so a clean report over zero spawns reads as such. A log it cannot find or read whole is an input error (exit 2), never a pass. Exit 0 clean, 1 findings.

## When the hook is absent

Agents keep working. Every definition still carries the three universal blocks, the Codex wrappers embed the kernel, and the Cursor rules export is unchanged. A role at `trial` or `switched` whose spawns leave no row is what `--liveness` exists to catch.
