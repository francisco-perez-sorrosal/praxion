---
id: dec-draft-2fdf564d
title: Live context-layer scenario runner — isolated headless sessions produce the seeded scenarios' recorded values
status: proposed
category: architectural
date: 2026-09-24
summary: Adds the praxion_evals.live sub-package and its own opt-in console entry (praxion-evals-live), which runs each seeded scenario case k times, sequentially, in fresh sandboxed `claude -p` sessions over a read-only materialized target copy proven by a four-nonce preflight, captures recorded_* from telemetry or filesystem ground truth, grades through the seeded-scenario graders (spawn-selection amended to case-insensitive tier + required-agent subset), and writes a versioned baseline JSON incrementally; narrows dec-040 clause 3 ("never start agents") for isolated, operator-invoked sessions only.
tags: [eval, eval-praxion, process-economy, roadmap-p0-7, seeded-scenarios, context-layer, headless, measurement-instrument, canary]
made_by: agent
agent_type: systems-architect
branch: worktree-process-economy-p0-7-live
pipeline_tier: standard
affected_files:
  - eval/src/praxion_evals/live/
  - eval/src/praxion_evals/live/cli.py
  - eval/src/praxion_evals/live/materialize.py
  - eval/src/praxion_evals/live/session.py
  - eval/src/praxion_evals/live/scenarios.py
  - eval/src/praxion_evals/live/results.py
  - eval/src/praxion_evals/live/report.py
  - eval/src/praxion_evals/live/spend.py
  - eval/src/praxion_evals/live/fixture_repos/
  - eval/scripts/record_live_envelopes.py
  - eval/src/praxion_evals/harness/families/seeded_scenarios.py
  - eval/pyproject.toml
  - commands/eval-praxion.md
  - eval/EVAL_PLAN.md
supersedes_in_part:
  - dec-040
dissent: The whole signal may be noise at k=3 on a thin corpus — five scenarios, one of which (spawn-selection) carries the canary — so the runner could spend ~$15–40 per run to report a delta nobody can distinguish from sampling variance.
---

## Context

The five seeded scenarios (`eval/tests/fixtures/scenarios/01..05`) grade each fixture's frozen `recorded_*` field against `expected_*` in the same YAML. The family reads no rule, agent or skill file, so deleting the coordination protocol leaves all five green: a zero-variance instrument used as a quality guard (process-economy roadmap W7, P0.7). Every Phase 1 slice of that roadmap cites a P0.7 scenario as its guard, so the guard has to be able to fail.

Making it able to fail means producing `recorded_*` from a live session whose context layer is the checkout under test. Two constraints shape the component. First, the ambient environment cannot select a target: a `claude -p` launched here loads `~/.claude/CLAUDE.md` and `~/.claude/rules/*` (symlinks into the main checkout), the installed marketplace plugins, user MCP servers, and an inherited `CLAUDE_PLUGIN_ROOT` — a live control run showed the target copy's global-CLAUDE.md and rule nonces absent while nine other plugins and five MCP servers loaded. Second, dec-040 clause 3, preserved on this point by dec-204, says evals "never start agents".

## Decision

Add a producer component, the `praxion_evals.live` sub-package (`cli`, `materialize`, `session`, `scenarios`, `results`, `report`, `spend`, plus `fixture_repos/` package data), reachable only through its own console entry `praxion-evals-live [TARGET] [--k N] [--canary] [--judge] [--max-total-usd N] [--output PATH] [--dry-run] …`. A standalone recorder, `eval/scripts/record_live_envelopes.py`, captures verbatim envelopes for the parser tests and is never reachable from the runner's flags. As shipped:

1. **Materialize** the target (git ref via `git archive`; path/worktree via tracked + untracked-non-ignored files) into a copy per variant, then make it **read-only on disk** and record its tree digest. The canary variant removes the coordination protocol's `### Process Calibration` section and aborts if it is absent. After each variant the digest is re-checked; a mismatch turns every session of that variant into an `isolation_breach` error.
2. **Prove isolation** once per variant with a preflight session over an identically built copy carrying **four** fresh nonces — global CLAUDE.md, the coordination-protocol rule, a plugin agent description, and a hook-delivered rule — all of which must be echoed or the variant aborts; a HEAD preflight abort also skips the canary. Every scenario session's telemetry is checked: `init` plugins and MCP servers, and every tool_use input — an absolute path outside the sandbox and the copy is an `isolation_breach`. The isolation mechanism itself is recorded in the companion implementation ADR (dec-draft-0cbab284).
3. **Run** each of the nine cases `k` times (default 3, Opus, effort `medium`) **sequentially** — there is no worker pool — in fresh per-session sandboxes and fixture repos, with per-scenario permission allowlists (spawn-selection allowlists no tools), per-session `--max-budget-usd`, and a run-level spend cap (`--max-total-usd`, default $50) that charges each session's actual reported cost, because the CLI checks its budget only after a turn.
4. **Capture** `recorded_*` from ground truth — `result.structured_output`, tool_use inputs, the subagent's own forwarded events, or the fixture's filesystem delta — never from the model's account of itself.
5. **Grade** through two public functions added to `seeded_scenarios.py` (`grade_mechanical`, `judge_scenario`) that reuse the family's rubrics and judge schema. One grader changed: `_check_spawn_selection` now compares tiers case-insensitively and treats `expected_agents` as the **required core** (`set(expected) ⊆ set(recorded)` after stripping a `praxion:` prefix), because the protocol's researcher, interface-designer and test-engineer spawns are conditional and a correct superset must not fail. Frozen fixtures still pass (equal sets satisfy the subset). The other four checks are unchanged.
6. **Record** a discriminated outcome per session — `pass`, `fail` (`graded` | `not_elicited`), `error` (infrastructure, never a fail) — with per-session cost, tokens, turns, permission denials and resolved model, into a versioned baseline JSON (`.ai-state/eval_ledger/context_layer_baseline.json` for the post-merge run) plus an `EVAL_LOG.md` row draft. Each session runs inside its own exception boundary (a judge or fixture failure becomes that session's `error` record), and output is written incrementally with `run.complete: false` on any such failure, so an already-paid run is never discarded.

The runner never runs from a hook, a pipeline, CI, or `/eval-praxion`; `SeededScenarioFamily` still grades only its frozen fixtures.

## Considered Options

### Option A — separate sub-package with its own console entry (chosen)

Pros: the paid producer is unreachable from `/eval-praxion`'s parser and routine `--mechanical-only` runs; live-only flags (`--k`, `--canary`, `--max-total-usd`) do not sit beside flags that would be meaningless in live mode; `harness/` keeps its read-only-over-a-corpus character. Cons: a second executable next to `praxion-evals`; the `/eval-praxion` command doc must point at it.

### Option B — a `--live-scenarios` flag on the `praxion-evals` CLI

Pros: one binary, matching the "single eval entrypoint" phrasing. Cons: one parser carrying two modes whose flags do not intersect; the expensive mode sits one flag away from a command run after every slice.

### Option C — extend the standalone `eval/scripts/inheritance_probe.py` pattern

Pros: precedent for shelling out to `claude -p` from the eval surface. Cons: a script outside the package cannot share the graders without path hacks, and the probe deliberately measures the ambient environment — the opposite of what this component needs. (The fixture recorder does follow this pattern, because it is a one-shot tool rather than the production path.)

### Option D — let `SeededScenarioFamily` spawn sessions

Rejected: `/eval-praxion` would start paid sessions, breaking the opt-in constraint and dec-040's hook/pipeline guarantees in one move.

## Consequences

Positive: the five scenarios become able to fail when the layer changes; later slices get a recorded baseline to diff against; isolation is proven per run by unguessable content plus harness telemetry rather than asserted; infrastructure failures are kept out of pass rates by type. With the required-agent-subset check, the spawn-selection Standard and Full cases can pass at HEAD when the tier is right and the core agents are present, so the canary can move on all five spawn-selection cases rather than three.

Negative: ~44 Opus sessions (~$15–40, API-metered here) per run with the canary, run one after another, so a run takes tens of minutes, outlives the 10-minute Bash tool limit, and must be launched detached. The parser is coupled to Claude Code's stream-json shape (mitigated by verbatim fixtures and version recording). The subset check cannot detect an over-spawning orchestrator: extra agents never fail a case.

## Disconfirmation

- **Falsifier:** the canary run — the degraded copy without the tier section — does not lower the spawn-selection pass rate versus HEAD. That would mean the scenario does not detect removal of the rule it exists to guard, and the component measures noise. The telemetry corpus is thin: five scenarios, k=3, one prior live precedent (the two-session inheritance probe), no history of repeated runs; a single run cannot separate a real delta from sampling variance.
- **Steelmanned runner-up:** Option B. A single `praxion-evals` binary keeps one mental model and one install surface, the "single eval entrypoint" claim stays literally true, and argparse mutual-exclusion groups make the mode split explicit; the accidental-invocation risk is a typed flag either way.
- **Reversal trigger:** the canary. If the post-merge canary does not register (`lowered: false`), or if two consecutive runs at the same SHA disagree on a scenario's verdict more often than they agree, revisit — first the scenario design (expected sets, prompts, k), then whether a live producer is worth its cost at all.
- **Process evidence:** the verifier's FAIL showed the paid path was untested when the spawn budget dropped the test-engineer pairing on the steps that own the external side effect.

## Prior Decision

This ADR **narrows only clause 3** of dec-040 — specifically its guarantee that evals "never start agents" — and only for this component: the live runner starts headless Claude Code sessions, each confined to a per-session sandbox (`HOME`, config directory, temp directory) and a disposable fixture repo, loading nothing from the operator's configuration. Clause 3's other guarantees stand unchanged: the runner never mutates live pipeline state and never runs during a pipeline. dec-204's narrowing of clause 3's reading model (LLM-as-judge over completed artifacts) is unaffected and is reused for the optional judged pass.

Clauses 1, 2 and 4 are re-affirmed, and clause 1 is applied more strictly: the live runner is operator-invoked only — **no** CI job runs it, although clause 1 would permit an opt-in one — because every run spends real model usage. No hook imports `praxion_evals.live` or `praxion_evals.harness`.
