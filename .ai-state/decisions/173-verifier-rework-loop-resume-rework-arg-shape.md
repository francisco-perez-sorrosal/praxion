---
id: dec-173
title: /resume-rework takes no positional argument; reads VERIFIER_FINDINGS.md from cwd
status: accepted
category: architectural
date: 2026-05-14
summary: /resume-rework is a no-positional-arg slash command that reads VERIFIER_FINDINGS.md from the current worktree's root, with an explicit --findings <path> escape hatch and --dry-run / --help levels per clig.dev.
tags: [slash-command, resume-rework, cli-design, clig-dev, tui]
made_by: agent
agent_type: interface-designer
branch: worktree-verifier-rework-loop
pipeline_tier: standard
affected_files:
  - commands/resume-rework.md
---

## Context

The user invokes `/resume-rework` from a fresh Claude Code session opened inside a rework worktree. The command reads `VERIFIER_FINDINGS.md`, dispatches the appropriate agent, and surfaces a one-liner. The argument-shape choice has direct consequences for misuse risk and for the conversation-as-interface principle.

The natural candidates for the argument:
- `<worktree-name>` — explicit, but the user is already inside the worktree (cwd is the worktree root); passing the name again is redundant.
- `<rw-id>` — explicit, but requires the user to read the manifest first; hostile to the fresh-session entry point.
- `<findings-path>` — most explicit, but `.ai-work/<task-slug>/VERIFIER_FINDINGS.md` is a long string to type.
- No positional — relies on the convention that `VERIFIER_FINDINGS.md` lives at a known path inside the worktree.

## Decision

`/resume-rework` takes **no positional argument**. The default behavior is:

1. Resolve cwd → worktree root via `git rev-parse --show-toplevel`.
2. Locate `VERIFIER_FINDINGS.md` inside the worktree by walking `.ai-work/*/VERIFIER_FINDINGS.md` (one match expected; multiple = error; zero = error).
3. Read it, parse `target_agent` from the `## Provenance` section's `Rework ID`, look up the manifest row by `rw-<hash>`, dispatch the named agent with `Task slug: <slug>` from provenance.

The single escape hatch is `--findings <path>` (explicit override for advanced workflows: re-running on a moved file, debugging, etc.).

### Argument and flag shape (clig.dev)

```
USAGE
  /resume-rework [options]

OPTIONS
  --findings <path>   Explicit path to VERIFIER_FINDINGS.md (default: auto-discover in cwd)
  --dry-run           Parse the findings, show the dispatch plan, do not spawn the agent
  --json              Emit dispatch plan as JSON on stdout (data); status to stderr (default off)
  --quiet, -q         Suppress informational output (errors still print to stderr)
  --help, -h          Show this help

EXAMPLES
  # Default — auto-discover findings in the current worktree
  /resume-rework

  # Preview what would be dispatched without actually spawning
  /resume-rework --dry-run

  # Override the findings path (rare)
  /resume-rework --findings .ai-work/some-other-slug/VERIFIER_FINDINGS.md
```

### Stdout / stderr discipline

- **stdout**: the dispatch plan summary (a one-liner: `"Dispatching systems-architect with task slug 'fix-auth-validation' (rw-3b9f6ba0)"`). With `--json`, the structured dispatch payload.
- **stderr**: everything else — `Reading VERIFIER_FINDINGS.md…`, `Manifest matched: rw-3b9f6ba0`, error messages.

### Exit codes

| Code | Meaning |
|------|---------|
| `0` | Success — agent dispatched (or `--dry-run` showed the plan cleanly) |
| `1` | General failure (agent spawn failed, etc.) |
| `2` | Misuse — bad flags, multiple `VERIFIER_FINDINGS.md` files, unknown `target_agent` |
| `3` | `VERIFIER_FINDINGS.md` not found in cwd |
| `4` | `VERIFIER_FINDINGS.md` stale — `rw-<hash>` does not match any row in `REWORK_MANIFEST.md` of the parent worktree |
| `5` | `VERIFIER_FINDINGS.md` malformed — required section missing |

Exit codes 3–5 are custom but discoverable via `--help` (a `EXIT CODES` block follows `OPTIONS`).

### Error grammar (three-part — what / why / how to fix)

When discovery fails:

```
Cannot resume rework: VERIFIER_FINDINGS.md not found.
Searched: <worktree-root>/.ai-work/*/VERIFIER_FINDINGS.md (no matches).
To fix: confirm you are inside a rework worktree (created by the
main agent from REWORK_MANIFEST.md), or pass --findings <path>
to point at the file explicitly.
```

When the file is stale:

```
VERIFIER_FINDINGS.md is stale: rework ID rw-3b9f6ba0 not found
in the parent worktree's REWORK_MANIFEST.md.
The verifier may have re-run and produced a new manifest.
To fix: re-create this rework worktree from the latest manifest,
or run /resume-rework --findings <path> on a known-current file.
```

## Considered Options

### Option A — `/resume-rework <worktree-name>`

Pros: explicit; mirrors `/merge-worktree <branch-name>` convention.

Cons: redundant — the user is already inside the worktree (cwd is the worktree root); requires the user to look up the name; introduces a misuse path (typo'd name fails with `worktree not found` rather than the more useful `findings not found`).

Rejected.

### Option B — `/resume-rework <rw-id>`

Pros: rework-ID is the stable identity surface.

Cons: forces the user to read the manifest before resuming (hostile to the "fresh session opens inside the worktree" flow); duplicates information already inside the worktree's `VERIFIER_FINDINGS.md`.

Rejected.

### Option C — `/resume-rework <findings-path>`

Pros: maximally explicit.

Cons: cwd already gives us everything we need; positional path defeats the conversation-as-interface principle ("the system tells you what to do next, not the other way around").

Rejected, but salvaged as the `--findings <path>` escape hatch.

### Option D — No positional, cwd-driven auto-discovery (chosen)

Pros: zero typing in the common case; the worktree IS the context; misuse is hard (you cannot run it accidentally outside a worktree because git-rev-parse fails); the SessionStart banner names the command, so the user lands inside the worktree and runs `/resume-rework` with no arguments and no thought.

Cons: relies on convention (one `VERIFIER_FINDINGS.md` per worktree). Mitigation: exit code 2 fires if multiple are found; explicit `--findings` overrides.

**Chosen.** Best Bloch trade: minimal surface area, hard-to-misuse, names matter ("resume" + "rework" + zero arguments reads as "do the thing the worktree was opened to do").

## Consequences

**Positive:**
- The fresh-session flow is friction-free: open Claude Code in the worktree → SessionStart banner names `/resume-rework` → user types it → agent dispatched. No memorization, no flag lookups in the common case.
- `--dry-run` gives a safe preview surface for power users and CI.
- clig.dev composability is preserved (`--json` for stdout, status to stderr).
- The exit-code table is custom but documented — scripts that wrap `/resume-rework` get useful classification (3 = no findings, 4 = stale, 5 = malformed).

**Negative:**
- Multi-findings worktrees (an edge case where two rework clusters got merged into one worktree) hit exit code 2 and require `--findings`. This is intentional — multi-findings worktrees should be rare and the explicit override is the right escape.
- No completion for `--findings` (paths must be typed). Acceptable given the rarity of that path.

**Banner enhancement (one-line addition to `hooks/inject_worktree_banner.py`):**
- When a `VERIFIER_FINDINGS.md` is detected anywhere under `.ai-work/` in the worktree at SessionStart, append exactly two lines to the existing banner:
  ```
  - Rework worktree detected (VERIFIER_FINDINGS.md found).
    Run `/resume-rework` to dispatch the appropriate agent.
  ```
  No color codes (banner is JSON-emitted markdown — terminal rendering is downstream). The two-line cap respects the existing banner's terseness.
