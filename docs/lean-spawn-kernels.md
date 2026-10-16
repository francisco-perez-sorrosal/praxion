---
diataxis: explanation
audience: developer
---

# Lean spawn: role kernels and the adoption ledger

How a spawned Praxion agent can receive the process guidance it needs as a short, generated, per-role text instead of inheriting the whole project instruction surface. This page explains the parts and why they fit together. For the steps, see [Switch a role to its kernel](lean-spawn-how-to.md).

The mechanism makes no claim that a role does its work better or cheaper. It changes what a role is handed at spawn, and it is adopted one role at a time, only on the strength of a measured run and the user's ratification. A token figure appears in this documentation only as a startup-probe reading with its profile (`scripts/measure_startup_payload.py`), never as a claim.

## Table of contents

- [The problem the mechanism answers](#the-problem-the-mechanism-answers)
- [What a kernel is](#what-a-kernel-is)
- [How a kernel is assembled](#how-a-kernel-is-assembled)
- [How a role is switched](#how-a-role-is-switched)
- [What the spawn hook does](#what-the-spawn-hook-does)
- [Delivery evidence](#delivery-evidence)
- [Why the fallback is always present](#why-the-fallback-is-always-present)
- [Where each piece lives](#where-each-piece-lives)

## The problem the mechanism answers

A spawned agent inherits the project's root `CLAUDE.md`, the always-loaded rules and the memory index. Much of that text addresses the orchestrator (tier selection, spawn budgets, checkpoints) and a role that never acts on it still reads it. The agent frontmatter field `omitClaudeMd: true` makes a spawn skip that inherited surface, but dropping it alone would also drop the parts a role does need: the behavioral contract, the return contract, and the few rules specific to what the role writes.

The kernel mechanism pairs the two. A role that omits the inherited surface receives, from a plugin `SubagentStart` hook, a generated text holding the guidance its audience needs, followed by the project's own `CLAUDE.md`.

## What a kernel is

A kernel is the per-role text the spawn hook delivers. It is split into one or more *strings*, because the harness caps one injected string at 10,000 characters. Each role's kernel has the same shape:

1. the **core**, which opens with the three universal blocks (the behavioral contract with its self-test, the Praxion-links rule, the return contract with its terminal markers) and carries the rest of the guidance every agent needs;
2. the **modules** whose audience includes the role (for example the ADR-author module for the agents that create decision records, or the ledger-writer module for the agents that append tech-debt rows).

A kernel never contains text meant for the orchestrator alone, or text that no actor reads. Both classes stay resident in their sources and are excluded mechanically (see below).

## How a kernel is assembled

Nothing in `claude/kernels/` is written by hand except the authored texts under `claude/kernels/src/`.

- **The audience manifest** `rules/_audience.yaml` classifies every section of every always-loaded source (rules without a path scope, the user template, the project file) by *scope* (`core`, `role`, `orchestrator-only`, `no-actor`) and *form* (`verbatim`, the source bytes, or `condensed`, an authored text pinned to the source it stands for, so a changed source forces a review of the condensed text). It also declares the modules and the two role groups.
- **The generator** `scripts/generate_kernels.py` reads the manifest, the sources and the authored texts and writes the module files, `core-blocks.md`, `principles.md` and `index.json` under `claude/kernels/`. It packs each role's modules into the fewest strings under the cap, in order, without splitting a module; a module that is itself over the cap becomes numbered parts cut at paragraph ends. The same inputs always write the same bytes.
- **`index.json`** lists, per role, the modules in each string and the strings themselves, plus the kernel version and the number of hook slots (the largest string count of any role plus a reserve for the project's own `CLAUDE.md`). It holds no adoption status.
- **The generator also rewrites derived text elsewhere**: the three universal blocks inside every agent definition, and the short preamble put ahead of host-native spawns (`hooks/_kernel_preamble.py`). The blocks are generated output, byte-identical to `claude/kernels/core-blocks.md`.
- **The manifest checker** `scripts/check_kernel_manifest.py` is the commit gate. It fails on an unclassified or orphaned manifest entry, a kernel string over the cap, a stale pin, orchestrator-only text found in a kernel, committed kernels that differ from what the generator writes now, a hook registration that does not match the index, and the adoption-ledger rules in the next section. No setting disables it.

Agents, rules and sources are detected from the tree, not listed, so a new agent or rule is covered the day it exists.

## How a role is switched

A role's status is recorded in `.ai-state/kernel_adoption.yaml`:

| Status | What the spawn hook does | What the definition does |
|---|---|---|
| (absent) | Delivers nothing. | Keeps inheriting the project instructions. |
| `trial` | Delivers the kernel. | Unchanged: the role still inherits the project instructions, so a trial role receives both. |
| `switched` | Delivers the kernel. | Carries `omitClaudeMd: true`. |
| `held` | Delivers nothing: a trial closed without a flip. | Keeps inheriting the project instructions. |

The ledger lists the `eligible` roles (the pilot's five) and, per adopted role, a record: `since` (the ISO moment the record began, so earlier spawns are not judged) and its `runs`. A `switched` record also holds the flip evidence: the passing run (at least 20 complete pairs from the adherence eval, passing the flip rule), the startup probe's before and after readings, and two booleans for the user's ratification of the flip rule and of this flip. A `held` record keeps the closed trial's `since` and every run, and states a `reason`.

The commit gate holds each move:

- a role moves only from absent to `trial`, from `trial` to `switched` or `held`, or from `held` back to `trial` with a `since` later than the parent commit (a new trial, judged from its own start); nothing leaves `switched`, no record is removed, and a ledger present at the parent commit is never deleted;
- a recorded run is never dropped, reordered or rewritten, and none is added while a role stays `held`;
- `omitClaudeMd` is set on an agent only while its record is `switched`, and a `switched` record requires the flag;
- a `switched` record missing any piece of evidence, or for a role that is not eligible, and a `held` record with no reason, are refused by name.

The ledger is where the user's ratification is recorded, so a flag cannot reach a commit without it. The adherence eval (`praxion-evals-adherence`, which the gate names as data and never runs) supplies the run a flip rests on. A role that does not pass stays at `trial` with its runs recorded, or, once its trial closes, is `held`; `--liveness` judges only `trial` and `switched` roles.

## What the spawn hook does

`hooks/inject_kernel.py` is registered once per slot (`--slot 1` to the index's slot count) on `SubagentStart`, synchronously, under the matcher `^praxion:.*`. Each slot prints its own string. Stdout is empty or one JSON object, and the exit code is always 0, so the hook can never block a spawn.

Every slot computes the same whole delivery and prints its part:

1. **Who receives anything.** Only an agent of this plugin (`praxion:<role>`) whose status in the running plugin's ledger is `trial` or `switched`. A host-native agent, another plugin's agent of the same role name, a role at no status or `held`, a plugin without a ledger or an index, and an unknown index schema receive nothing. There is no disable variable: a switched role must never be silenced.
2. **Where things are found.** The plugin root comes from `CLAUDE_PLUGIN_ROOT`, never from the script's own location; the kernel and ledger are the running plugin's. The project comes from the payload's `cwd` through git. The hook needs only the standard library: it scans the ledger line by line for its generated shape and reads the index as JSON.
3. **The strings, in order.** The role's kernel strings first (with `${CLAUDE_PLUGIN_ROOT}` written out as the real path), then the project's root `CLAUDE.md` as numbered parts headed `[project CLAUDE.md, part N of M]`, cut at line ends. A line that is wholly `@<relative path>` is replaced by that file's text when it is a regular file inside the project after symlinks resolve. The expansion is narrower than the harness's own: one level deep, resolved from the project root, never inside a fenced code block (fences are tracked without their containers, so one left open inside a list item stays open to the end of the file), and at most 64 such lines tried; an inline `@path`, an import inside an imported file and anything past the limit stay as written. The read is bounded by what the reserved slots can carry, and a failure reading the file costs the file, never the kernel. If the parts exceed the free slots, the last delivered part says how many were left out and tells the role to read `CLAUDE.md` in the project root.
4. **Whole or nothing.** If any string would pass the cap, every slot refuses the whole delivery alike; a role never receives part of a kernel.
5. **The version marker.** Every string begins with its own one-line paragraph, `[praxion <8 hex> #<slot>]`.
6. **The row.** Slot 1 alone appends one `kernel_injected` row to the project's observation log, and only when a log serves the project. A spawn that receives nothing leaves no row.

The order in which strings arrive is the harness's, not the hook's; the marker names the slot and each project-file part names its place.

## Delivery evidence

Two channels record that a kernel arrived:

- **The marker**, in the role's context and recorded in the role's own transcript; the parent session's stream never carries a subagent's hook output. The adherence eval reads it from that transcript because its sandbox holds no observation log.
- **The `kernel_injected` row**, in the project's log: timestamp, session, `agent_type`, `agent_id`, `role`, the full `kernel_version`, the `strings` delivered (module, part and character count each) and a `project_file` summary (characters, parts, parts omitted). The how-to shows [how to read one](lean-spawn-how-to.md#read-a-kernel_injected-row).

A spawn of an adopted role with no row means the hook did not run for it. `check_kernel_manifest.py --liveness` reports exactly that.

## Why the fallback is always present

Switching depends on the hook, so every other channel keeps its own copy of what a role needs:

- **Claude Code, hook absent or silent.** Every agent definition keeps the three universal blocks inline as generated output. An agent that must read a file to learn how to finish has already failed when it skips the read, so the blocks stay in the definition.
- **Codex.** The generated Codex wrappers (`codex/config/export-codex-agents.py`) embed the role's kernel strings from the index in their instructions.
- **Cursor.** The rules export is unchanged and carries the guidance as before.

## Where each piece lives

| Piece | Path |
|---|---|
| Audience manifest | `rules/_audience.yaml` |
| Authored texts | `claude/kernels/src/` |
| Generated kernels and index | `claude/kernels/` |
| Generator | `scripts/generate_kernels.py` |
| Commit gate and liveness check | `scripts/check_kernel_manifest.py` |
| Adoption ledger | `.ai-state/kernel_adoption.yaml` |
| Spawn hook and its registration | `hooks/inject_kernel.py`, `hooks/hooks.json` |
| Codex wrappers | `codex/config/export-codex-agents.py` |
