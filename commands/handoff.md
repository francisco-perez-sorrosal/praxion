---
description: "Compose the pipeline's HANDOFF.md at a phase boundary so the next window inherits position, constraints and corrections."
allowed-tools: [Read, Edit, Glob, Grep, Bash(compose_handoff.py:*), Bash(python3:*), Bash(git:*)]
argument-hint: "<task-slug> [--boundary <enum>] [--dry-run] [--force]"
disable-model-invocation: true
---

## Help

```
/handoff — write the cross-window handoff for a pipeline

USAGE
  /handoff <task-slug> [options]

  Runs compose_handoff.py to write .ai-work/<task-slug>/HANDOFF.md: eight fixed
  sections, the mechanical half computed from the reconciler and the judgement
  half yours to fill. Refuses to write while a spawn is in flight or the current
  step's declared files are dirty — a handoff composed over a half-finished tree
  presents a false position with the authority of a generated document.

EXAMPLES
  /handoff auth-flow --boundary planning-to-implementation
  /handoff auth-flow --dry-run                       # compose, show, write nothing
  /handoff auth-flow --force                         # write over a refusal, on the record

OPTIONS
  --boundary <enum>  research-to-architecture | architecture-to-planning |
                     planning-to-implementation | implementation-to-verification |
                     mid-phase:<step-id>   (default: mid-phase at the current step)
  --dry-run          compose and print the report; write no file
  --force            compose despite a refusal; stamps `readiness: overridden`
  --help, -h         show this help

EXIT CODES
  0   handoff written (or composed, under --dry-run)
  1   refused — not ready: a spawn is in flight or step files are dirty. Nothing
      was written and the previous handoff, if any, is untouched. Clear the named
      condition and re-run, or pass --force to write over it on the record.
  2   nothing to compose: no pipeline for that slug (no .ai-work/<slug>/WIP.md)
  3   error: unparseable existing handoff, unknown boundary, bad slug, plugin-cache path
```

Exit `1` and exit `2` are different answers, not degrees of the same one. `1` means
the pipeline exists and this moment is not a boundary — the refusal is the feature,
and `--force` is the documented override. `2` means there is no pipeline here at all,
so no flag will help; check the slug. `3` means the composer could not do its job.

## Arguments

`$ARGUMENTS` holds the invocation. Parse it as: the first non-flag token is the **task slug**
(required), plus the optional `--boundary <enum>`, `--dry-run` and `--force` documented above.

- **Non-empty** — the slug names the pipeline: `<worktree_root>/.ai-work/<slug>/`. The boundary
  names *which* transition this handoff records; it is a closed enum, so an unrecognized value is
  an error rather than a free-text note. Omit it and the composer names the current step's
  mid-phase position.
- **Empty (no slug)** — do not guess. Writing a handoff under a slug the user never named puts a
  false document in another pipeline's directory. List the slugs under `<worktree_root>/.ai-work/`
  that have a `WIP.md`, ask for one, and exit 3.

## Why this exists

The plan on disk survives a lost orchestrator. The standing instructions the user
gave in conversation, the corrections already applied, and the digest of what was
just decided do not — they live only in the window. This command writes them down
while the window still holds them, next to a mechanically computed position, so the
next window starts from a document rather than a reconstruction.

It is written by the **orchestrator**, at a Conversation Checkpoint, *after* the
checkpoint digest is composed — section 3 of the handoff is that digest's delta. No
subagent writes it (none knows the cross-phase state) and no hook writes it
(composition needs judgement, and a mechanically written handoff would be a
mechanized claim about what the outgoing window knew).

## Procedure

1. **Resolve the slug and roots.** Parse the slug and flags out of `$ARGUMENTS` per
   **Arguments** above. `worktree_root = git rev-parse --show-toplevel`. The slug's
   pipeline lives at `<worktree_root>/.ai-work/<slug>/`.
2. **Compose.** Run the composer. It is installed on `PATH` by `install_claude.sh`
   (linked into `~/.local/bin/`); in the Praxion self-host checkout, use
   `python3 scripts/compose_handoff.py` instead:
   ```
   compose_handoff.py <slug> --repo-root <worktree_root> \
     [--boundary <enum>] [--dry-run] [--force] --json
   ```
   Read the exit code first, then the JSON report (`path`, `boundary`, `input_state`,
   `byte_count`, `over_8kib`, `conflicts`).
   - **Exit 1** — report the named conditions and their remedies to the user verbatim and
     stop. Do not re-run with `--force` on your own initiative: the override records a
     non-quiescent tree into the artifact and is the user's call.
   - **Exit 2 or 3** — report per **Error grammar** below and stop.
3. **Fill the judgement sections.** Open the written file and replace each
   `_[to fill at the checkpoint]_` placeholder that is still present:
   - **Decisions & assumptions in force** — the checkpoint digest's *delta* since the last
     handoff, plus any draft decision ids. Reset at every new boundary; do not re-paste
     what an earlier boundary already carried.
   - **Operating constraints from the user** — the ask-before list and every standing
     instruction this session is operating under (pushing, releasing, retiring a component,
     touching the environment or the fleet, pulling a deferred item forward), plus the tier
     and timing decisions already made.
   - **Corrections in force** — corrections the user made that must not be re-litigated.
   - **Do not re-inherit** — approaches already tried and rejected, and stale context the
     next window should ignore.

   On a re-composition these arrive already filled, **carried forward byte-for-byte**.
   Leave them exactly as they are unless the user changed the instruction — a reflowed
   constraint is a changed constraint.
4. **Report** the path, the boundary, the number of disagreements with ground truth, and
   whether the size advisory fired. Then tell the user the next window starts with
   `/resume-pipeline <slug>`.

## --dry-run mode

Compose, print the report and the rendered sections, and exit 0 without writing the file.
Use it to see what a handoff would say before committing to one.

## --force mode

`--force` converts a refusal into an override: the file is written, its header carries
`readiness: overridden`, and the conditions that were firing are listed in its State
section. The next window therefore learns it inherited a non-quiescent tree and must
re-derive the position from ground truth before trusting it. Never pass `--force`
silently — say that it was used, and why.

## Error grammar

**Exit 1 — refused, not ready:**
```
Handoff refused: <condition> — <remedy>.
Nothing was written; the previous handoff (if any) is untouched.
To fix: clear the condition and re-run, or /handoff <slug> --force to record the
override in the artifact.
```

**Exit 2 — no pipeline for the slug:**
```
Nothing to compose: no WIP.md at .ai-work/<slug>/WIP.md under this worktree.
To fix: confirm the task slug, or run from the worktree holding the pipeline.
```

**Exit 3 — unparseable existing handoff:**
```
Cannot compose: the existing .ai-work/<slug>/HANDOFF.md is missing required sections.
It was left untouched — a partial read would silently drop a carried instruction.
To fix: repair the file by hand, or move it aside and re-run.
```

**Exit 3 — no slug given:**
```
Cannot compose: no task slug. Pipelines with a WIP.md under this worktree:
  <slug>  (<N> steps, last modified <date>)
To fix: re-run as /handoff <task-slug>.
```
