---
name: lens-fanout
description: >
  Launches an isolated multi-lens research fan-out for a question that has at least two
  plausible, genuinely rival answers: one Workflow-encoded run spawns N lens agents in
  parallel with construction-level isolation (no agent can read a sibling's output), then
  one aggregator reconciles the fragments into a Divergence Map. Refuses to launch when
  the question does not have rival answers, when the derived lens set falls outside the
  2-6 range, or when a findings artifact already exists at the target slug. User-invoked
  only -- never triggers from model judgement. Trigger terms: multi-perspective research,
  isolated lens fan-out, parallel research agents, Workflow-encoded lens collection,
  lens independence, divergence map.
argument-hint: "<question> [--lenses a,b,c] [--slug <task-slug>] [--sources a,b] [--proposer-model <name>|default]"
arguments:
  question:
    description: "The research question. Everything before the first ' --' token; quote it for the robust form."
    required: true
  lenses:
    description: "Comma-separated lens names (2-6, unique kebab-case). Omit to derive lenses from the question and confirm with the user."
    required: false
  slug:
    description: "Task slug. Artifacts land in .ai-work/<slug>/. Defaults to the session's active task slug."
    required: false
  sources:
    description: "Comma-separated repo-relative paths, shared identically across every lens."
    required: false
  proposer-model:
    description: "Model name for the lens agents, or 'default' to omit the option and inherit the session model."
    required: false
disable-model-invocation: true
allowed-tools: [Workflow, Read, Glob, Grep, AskUserQuestion]
---

Runs the honest-uncertainty gate, derives or accepts lenses, pre-flights the target artifacts, launches the fan-out via `Workflow`, and verifies the typed return against disk before reporting. Only a direct `/lens-fanout` invocation reaches this body -- `disable-model-invocation: true` keeps a model from ever choosing to fan out on its own.

## 1. Gate -- honest uncertainty

Before doing anything else, state at least two plausible, genuinely rival answers to the question. If fewer than two rival answers exist, refuse: report which limb of the gate failed (fewer than two plausible paths) and suggest the single-agent research path instead. A fan-out must never manufacture strawmen to justify itself -- this refusal fires before any tool call.

## 2. Derive -- lenses stay a session judgement

If `--lenses` is present, parse the comma-separated list into `{name, brief}` pairs (kebab-case names; write each `brief` as a one-line framing from the question, not from the flag). If `--lenses` is absent, derive 2-6 lenses from the question yourself -- name each with a kebab-case id and a one-line framing -- then confirm the set with `AskUserQuestion` before proceeding. The lens set is never invented by the script; deriving it is exactly the judgement this skill keeps in the session.

## 3. Pre-flight

Resolve `slug` (from `--slug`, or the session's active task slug) and `sources` (from `--sources`, comma-split, or empty list). Then, using `Read`/`Glob`:

- **Lens-count invariant**: refuse and name the offending set if the resolved lens set has fewer than 2 or more than 6 members, or if two lenses share a name.
- **Overwrite refusal**: refuse and offer a different `--slug` if `.ai-work/<slug>/RESEARCH_FINDINGS.md` already exists -- the aggregator has no way to check the filesystem before writing, so this is the only point that can catch a clobber.

Both refusals stop before any `Workflow` call; a script that has already launched cannot un-launch.

Resolve `proposer_model`: if `--proposer-model` names a model, use it verbatim; if `--proposer-model default` is given, set `proposer_model` to `null` (omit the option, inherit the session model -- a distinct legal value, not "unset"); if the flag is absent entirely, default `proposer_model` to `'sonnet'`.

Mint `timestamp` as an ISO-8601 UTC string (e.g. via a `date -u +%Y-%m-%dT%H:%M:%SZ` shell call -- this tool is deliberately not in `allowed-tools`, so it takes the normal one-time permission path rather than being pre-approved). Never call `Date.now()` or an argless `new Date()` inside the script; the timestamp always travels through `args`.

## 4. Launch

Call `Workflow` with:

- `scriptPath`: `${CLAUDE_PLUGIN_ROOT}/skills/lens-fanout/scripts/lens-fanout.js`. If this path does not resolve (a dev-linked, non-plugin-installed session), fall back to the absolute path from `git rev-parse --show-toplevel` plus `/skills/lens-fanout/scripts/lens-fanout.js`, and record which form worked.
- `args`: a real JSON value (never a JSON string) shaped `{question, lenses, slug, sources, timestamp, proposer_model}`.
- `resumeFromRunId`: never passed. It replays a cache, it does not re-run; recovery is a fresh launch plus `/resume-pipeline` reading fragments from disk.

`Workflow` runs in the background; the session stays responsive until the `<task-notification>` arrives.

## 5. Verify -- disk is ground truth, not the typed marker

When the notification arrives, read the typed return (`{marker, findings_path, divergence_count, lenses_read, lenses, dropped, timestamp}`) and, before reporting anything, confirm against disk:

- every `lenses[*].fragment_path` exists and is non-empty (`Read`/`Glob`);
- `findings_path` exists, is non-empty, and contains a `## Divergence Map` heading (`Grep` the file for the heading rather than trusting the marker);
- `lenses_read` equals the number of `lenses` rows returned, and `len(lenses) + len(dropped)` equals the number of lenses launched.

Report `[COMPLETE]` only when every check above holds. Report `[PARTIAL]` naming the specific missing or empty artifact otherwise -- a typed marker can never outrank what is actually on disk. Never re-launch automatically on a `[PARTIAL]`; recovery is a fresh `/lens-fanout` invocation or `/resume-pipeline` reading fragments from disk.

## 6. Report

Report the `findings_path` pointer, the per-lens markers and `claims_count`/`certainty` (never the lens `summary` or findings prose -- the return itself never carries them), the `dropped` list if non-empty, and the overall marker. The report is a pointer to `.ai-work/<slug>/RESEARCH_FINDINGS.md`, never a restatement of its content.

## Notes

- `Workflow` fans N lens agents into `.ai-work/<slug>/RESEARCH_<lens>.md`, each written by a `parallel()` closure that closes only over its own lens and the shared sources -- no agent can read or interpolate a sibling's in-flight result. One aggregator then reads every fragment from disk and reconciles them into the `## Divergence Map`; contradictions that survive isolation are preserved, never averaged.
- A dropped lens (user skip, or a terminal API error) is named in the run's `dropped` list, never silently absorbed; the run proceeds if at least two lenses survive.
- `Bash` is deliberately absent from `allowed-tools` -- pre-approving it for one `date -u` call would widen permissions for no gain; the call still works, it just takes the normal permission path.
