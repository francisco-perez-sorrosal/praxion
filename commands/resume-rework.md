---
description: "Dispatch the appropriate agent for a rework worktree. Reads VERIFIER_FINDINGS.md from the current worktree's .ai-work/ tree. Run inside a rework worktree created by the main agent from REWORK_MANIFEST.md."
allowed-tools: [Read, Glob, Grep, Bash(git:*), Agent]
argument-hint: ""
---

## Help

```
/resume-rework — dispatch the appropriate agent for a rework worktree

USAGE
  /resume-rework [options]

  Reads VERIFIER_FINDINGS.md from the current worktree's .ai-work/ tree,
  validates schema and manifest-match, then dispatches systems-architect
  as the first agent in the rework pipeline.

EXAMPLES
  # Default — auto-discover findings in the current worktree
  /resume-rework

  # Preview what would be dispatched without spawning
  /resume-rework --dry-run

  # Override the findings path (rare)
  /resume-rework --findings .ai-work/some-other-slug/VERIFIER_FINDINGS.md

OPTIONS
  --findings <path>   Explicit path to VERIFIER_FINDINGS.md (default: auto-discover)
  --dry-run           Parse findings, show dispatch plan, do not spawn
  --json              Emit dispatch plan as JSON on stdout
  --quiet, -q         Suppress informational output (errors still print to stderr)
  --help, -h          Show this help

EXIT CODES
  0   Success — agent dispatched (or --dry-run completed cleanly)
  1   General failure (agent spawn failed)
  2   Misuse — bad flags or multiple VERIFIER_FINDINGS.md candidates found
  3   VERIFIER_FINDINGS.md not found in current worktree
  4   VERIFIER_FINDINGS.md stale — rw-<hash> not in parent REWORK_MANIFEST.md
  5   VERIFIER_FINDINGS.md malformed — required section missing
```

## Auto-discovery

When `--findings` is not specified, the command resolves the findings file automatically:

1. Resolve worktree root: `git rev-parse --show-toplevel`
2. Glob for findings: `.ai-work/*/VERIFIER_FINDINGS.md` under the worktree root
3. Count matches:
   - Exactly one result → proceed to schema validation
   - Zero results → exit 3 (not found)
   - Two or more results → exit 2 (multiple candidates; use `--findings` to choose)

Each rework worktree contains exactly one findings file. When `--findings <path>`
is provided, auto-discovery is skipped; if the path does not exist, exit 3 applies.

## Schema validation

After locating `VERIFIER_FINDINGS.md`, the command verifies all seven required
sections are present in the file body. A valid findings file contains:

- `## Problem`
- `## Scope`
- `## Evidence`
- `## Success Criteria`
- `## Ledger Links`
- `## Suggested Tier`
- `## Provenance`

If any section is missing, the command exits with exit code 5 (malformed). Section
names must appear verbatim with the `##` heading marker.

## Manifest match

The `## Provenance` section of the findings file contains a `Rework ID` field of
the form `rw-<hash>`. The command reads this value and verifies it appears as a row
in the parent worktree's `REWORK_MANIFEST.md`.

Steps:
1. Extract `rw-<hash>` from `## Provenance` (field: `Rework ID: rw-<hash>`)
2. Locate the parent worktree's `REWORK_MANIFEST.md` via the `Parent worktree`
   pointer also in `## Provenance`
3. Search the manifest for the `rw-<hash>` ID
4. If not found → exit 4 (stale findings); the verifier may have re-run and
   produced a new manifest

On success, the command extracts the task slug and tier suggestion from the findings
file for use in the dispatch step.

## Dispatch

The architect-always-first routing invariant applies to all rework worktrees:
`systems-architect` is always the first agent dispatched, regardless of the
findings file's `class` field (`architecture` or `implementation`).

**Rationale**: both architecture-class and implementation-class rework rows route
through `systems-architect` first. The architect runs its standard Phase 1+ over
`VERIFIER_FINDINGS.md` and produces `SYSTEMS_PLAN.md`. For implementation-class
clusters, the standard pipeline then feeds `implementation-planner` via the
existing contract — the planner reads the architect-produced `SYSTEMS_PLAN.md`
as its primary input, which satisfies its Phase 1 invariant without any
internal planner change. The routing is deterministic and does not depend on
the verifier's classification.

Dispatch call:
```
Dispatch systems-architect with:
  Task slug: <rework-slug>          (from Provenance → Parent task slug)
  Findings:  <absolute-path>        (absolute path to VERIFIER_FINDINGS.md)
  Worktree:  <absolute-worktree>    (absolute path to worktree root)
```

Passing the absolute path is defense-in-depth: it prevents subagents from resolving
the file against an unexpected working directory.

## --dry-run mode

When `--dry-run` is passed, the command performs all validation steps (auto-discovery,
schema validation, manifest match) but does not spawn any agent.

The dispatch plan is printed to stdout and the command exits 0 without spawning:

```
Would dispatch: systems-architect
  task slug:    <rework-slug>
  rework id:    rw-<hash>
  tier:         <tier> (suggested)
  confidence:   <confidence>
  findings:     <path-to-VERIFIER_FINDINGS.md>
```

Status messages go to stderr; the stdout output is the dispatch plan only. With
`--quiet`, stderr status messages are suppressed but errors still appear.

## Error grammar

Each error exit code has a three-part what/why/how-to-fix structure:

**Exit 2 — multiple candidates:**

```
Multiple VERIFIER_FINDINGS.md candidates in this worktree:
  .ai-work/fix-auth-validation/VERIFIER_FINDINGS.md
  .ai-work/redesign-token-cache/VERIFIER_FINDINGS.md
Rework worktrees should contain exactly one findings file.
To fix: pass --findings <path> to choose explicitly.
```

**Exit 3 — not found:**

```
Cannot resume rework: VERIFIER_FINDINGS.md not found.
Searched: <worktree-root>/.ai-work/*/VERIFIER_FINDINGS.md (0 matches).
To fix: confirm you are inside a rework worktree (created by the main
  agent from REWORK_MANIFEST.md), or pass --findings <path> to point at
  the file explicitly.
```

**Exit 4 — stale findings:**

```
VERIFIER_FINDINGS.md is stale.
Rework ID rw-<hash> not found in parent worktree's REWORK_MANIFEST.md.
The verifier may have re-run and produced a new manifest.
To fix: re-create this rework worktree from the latest manifest, or
  run /resume-rework --findings <path> on a known-current file.
```

**Exit 5 — malformed findings:**

```
VERIFIER_FINDINGS.md is malformed.
Required section missing: ## <section-name>
Found sections: <comma-separated list of present sections>
To fix: re-create the rework worktree (the main agent's template is
  authoritative), or hand-edit the file to add the missing section.
```

## --json output

When `--json` is passed, stdout receives the dispatch plan as a JSON object;
status messages and errors go to stderr. Dispatch plan shape:

```json
{
  "action": "dispatched",
  "rework_id": "rw-3b9f6ba0",
  "target_agent": "systems-architect",
  "task_slug": "fix-auth-validation",
  "tier": "standard",
  "confidence": "high",
  "findings_path": ".ai-work/fix-auth-validation/VERIFIER_FINDINGS.md",
  "parent_worktree": "auth-flow"
}
```

For `--dry-run`, the `action` field is `"would-dispatch"` instead of `"dispatched"`.
The shape is identical otherwise, allowing scripts to parse both modes uniformly.
