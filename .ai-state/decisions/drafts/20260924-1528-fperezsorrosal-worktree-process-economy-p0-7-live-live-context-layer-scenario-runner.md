---
id: dec-draft-2fdf564d
title: Live context-layer scenario runner — isolated headless sessions produce the seeded scenarios' recorded values
status: proposed
category: architectural
date: 2026-09-24
summary: Adds the praxion_evals.live sub-package and its own opt-in console entry (praxion-evals-live), which runs each seeded scenario case k times in fresh, sandboxed `claude -p` sessions over a chosen target checkout, captures recorded_* from telemetry and filesystem ground truth, grades through the unchanged seeded-scenario graders, and writes a baseline JSON; narrows dec-040 clause 3 ("never start agents") for isolated, operator-invoked sessions only.
tags: [eval, eval-praxion, process-economy, roadmap-p0-7, seeded-scenarios, context-layer, headless, measurement-instrument, canary]
made_by: agent
agent_type: systems-architect
branch: worktree-process-economy-p0-7-live
pipeline_tier: standard
affected_files:
  - eval/src/praxion_evals/harness/families/seeded_scenarios.py
  - eval/pyproject.toml
  - commands/eval-praxion.md
  - eval/EVAL_PLAN.md
supersedes_in_part:
  - dec-040
dissent: The whole signal may be noise at k=3 on a thin corpus — five scenarios, one of which (spawn-selection) carries the canary, and whose expected agent sets already disagree with the rules they grade — so the runner could spend ~$15 per run to report a delta nobody can distinguish from sampling variance.
---

## Context

The five seeded scenarios (`eval/tests/fixtures/scenarios/01..05`) grade each fixture's frozen `recorded_*` field against `expected_*` in the same YAML. The family reads no rule, agent or skill file, so deleting the coordination protocol leaves all five green: a zero-variance instrument used as a quality guard (process-economy roadmap W7, P0.7). Every Phase 1 slice of that roadmap cites a P0.7 scenario as its guard, so the guard has to be able to fail.

Making it able to fail means producing `recorded_*` from a live session whose context layer is the checkout under test. Two constraints shape the component. First, the ambient environment cannot select a target: a `claude -p` launched here loads `~/.claude/CLAUDE.md` and `~/.claude/rules/*` (symlinks into the main checkout), the installed marketplace plugins, user MCP servers, and an inherited `CLAUDE_PLUGIN_ROOT` — a live control run showed the target copy's global-CLAUDE.md and rule nonces absent while nine other plugins and five MCP servers loaded. Second, dec-040 clause 3, preserved on this point by dec-204, says evals "never start agents".

## Decision

Add a producer component, the `praxion_evals.live` sub-package, reachable only through its own console entry `praxion-evals-live TARGET [--k N] [--canary] [--judge] …`:

1. **Materialize** the target (git ref via `git archive`; path/worktree via tracked + untracked-non-ignored files) into a read-only copy per variant; the canary variant removes the coordination protocol's `### Process Calibration` section and aborts if it is absent.
2. **Prove isolation** once per variant with a preflight session over an identically built copy carrying fresh nonces in the global CLAUDE.md, the coordination-protocol rule and a plugin agent description; all three must be echoed or the variant aborts. Check every scenario session's `init` telemetry (plugins, MCP servers) and error any breach. The isolation mechanism itself is recorded in the companion implementation ADR (dec-draft-0cbab284).
3. **Run** each of the nine cases `k` times (default 3, Opus) in fresh per-session sandboxes and fixture repos, with per-scenario permission allowlists and per-session budget caps.
4. **Capture** `recorded_*` from ground truth — `result.structured_output`, tool_use inputs, the subagent's own forwarded events, or the fixture's filesystem delta — never from the model's account of itself.
5. **Grade** through two additive public functions in `seeded_scenarios.py` (`grade_mechanical`, `judge_scenario`) that reuse the unchanged checks, rubrics and judge schema.
6. **Record** a discriminated outcome per session — `pass`, `fail` (`graded` | `not_elicited`), `error` (infrastructure, never a fail) — into a versioned baseline JSON (`.ai-state/eval_ledger/context_layer_baseline.json` for the post-merge run), plus an `EVAL_LOG.md` row draft for the operator.

The runner never runs from a hook, a pipeline, CI, or `/eval-praxion`; `SeededScenarioFamily` still grades only its frozen fixtures.

## Considered Options

### Option A — separate sub-package with its own console entry (chosen)

Pros: the paid producer is unreachable from `/eval-praxion`'s parser and routine `--mechanical-only` runs; live-only flags (`--k`, `--canary`, `--workers`) do not sit beside flags that would be meaningless in live mode; `harness/` keeps its read-only-over-a-corpus character. Cons: a second executable next to `praxion-evals`; the `/eval-praxion` command doc must point at it.

### Option B — a `--live-scenarios` flag on the `praxion-evals` CLI

Pros: one binary, matching the "single eval entrypoint" phrasing. Cons: one parser carrying two modes whose flags do not intersect; the expensive mode sits one flag away from a command run after every slice.

### Option C — extend the standalone `eval/scripts/inheritance_probe.py` pattern

Pros: precedent for shelling out to `claude -p` from the eval surface. Cons: a script outside the package cannot share the graders without path hacks, and the probe deliberately measures the ambient environment — the opposite of what this component needs.

### Option D — let `SeededScenarioFamily` spawn sessions

Rejected: `/eval-praxion` would start paid sessions, breaking the opt-in constraint and dec-040's hook/pipeline guarantees in one move.

## Consequences

Positive: the five scenarios become able to fail when the layer changes; later slices get a recorded baseline to diff against; isolation is proven per run by unguessable content plus harness telemetry rather than asserted; infrastructure failures are kept out of pass rates by type.

Negative: ~44 Opus sessions (~$14–19, API-metered here) and 20–40 minutes per run with the canary; the run outlives the 10-minute Bash tool limit and must be launched detached; the parser is coupled to Claude Code's stream-json shape (mitigated by verbatim fixtures and version recording); spawn-selection's exact agent-set grading will sit at a floor for the Standard/Full cases unless the fixture's expected sets are revisited before the first run.

## Disconfirmation

- **Falsifier:** the canary run — the degraded copy without the tier section — does not lower the spawn-selection pass rate versus HEAD. That would mean the scenario does not detect removal of the rule it exists to guard, and the component measures noise. The telemetry corpus is thin: five scenarios, k=3, one prior live precedent (the two-session inheritance probe), no history of repeated runs; a single run cannot separate a real delta from sampling variance.
- **Steelmanned runner-up:** Option B. A single `praxion-evals` binary keeps one mental model and one install surface, the "single eval entrypoint" claim stays literally true, and argparse mutual-exclusion groups make the mode split explicit; the accidental-invocation risk is a typed flag either way.
- **Reversal trigger:** the canary. If the post-merge canary does not register (`lowered: false`), or if two consecutive runs at the same SHA disagree on a scenario's verdict more often than they agree, revisit — first the scenario design (expected sets, prompts, k), then whether a live producer is worth its cost at all.

## Prior Decision

This ADR **narrows only clause 3** of dec-040 — specifically its guarantee that evals "never start agents" — and only for this component: the live runner starts headless Claude Code sessions, each confined to a per-session sandbox (`HOME`, config directory, temp directory) and a disposable fixture repo, loading nothing from the operator's configuration. Clause 3's other guarantees stand unchanged: the runner never mutates live pipeline state and never runs during a pipeline. dec-204's narrowing of clause 3's reading model (LLM-as-judge over completed artifacts) is unaffected and is reused for the optional judged pass.

Clauses 1, 2 and 4 are re-affirmed, and clause 1 is applied more strictly: the live runner is operator-invoked only — **no** CI job runs it, although clause 1 would permit an opt-in one — because every run spends real model usage. No hook imports `praxion_evals.live` or `praxion_evals.harness`.
