---
name: test-coverage
description: >
  Dispatcher/renderer for test coverage: locate, invoke, and render coverage
  via the project's own tooling (pytest-cov, vitest, etc.) — never installs
  tooling or mutates config. Triggers: reporting coverage percentages, running
  canonical coverage targets, rendering coverage tables, comparing against a
  prior run, wiring coverage into commands/agents/metrics pipelines.
  Per-language references for Python and TypeScript.
allowed-tools: [Read, Glob, Grep, Bash]
compatibility: Claude Code
---

# Test Coverage

Language-agnostic skeleton for locating, invoking, and rendering project test coverage. Language-specific mechanics (probe order, invocation flags, config block) live in the per-language reference loaded on demand.

**Content boundary.** This skill is a **dispatcher and renderer**, not a tool installer. Projects declare their own coverage tooling (`pytest-cov`, `c8`, `cargo-tarpaulin`, etc.) as real dependencies; the skill reads, invokes, and renders what the project already owns.

**Satellite files** (loaded on-demand, one per language):

- [references/python.md](references/python.md) — target-discovery probe order, invocation conventions, presentation notes, copy-pasteable default coverage config block
- [references/typescript.md](references/typescript.md) — Vitest + `@vitest/coverage-v8` setup, Istanbul reporter options, `vitest.config.ts` thresholds, Next.js/React coverage notes

Future language references (e.g., `references/go.md`, `references/rust.md`) are added here without body changes to this file. New rows go into the Language References table below.

## Language References

| Language   | Reference | Tooling (project-owned) |
|------------|-----------|-------------------------|
| Python     | [references/python.md](references/python.md) | `pytest` + `pytest-cov` |
| TypeScript | [references/typescript.md](references/typescript.md) | `vitest` + `@vitest/coverage-v8` |

When a caller activates this skill for a project, detect the language and load the matching reference. If no reference exists for the detected language, fall back gracefully — emit a clear "no language reference available" message and decline to invent a probe order.

## Three Responsibilities

The skill does exactly three things. Everything else is out of scope.

### 1. Locate

Find the project's canonical coverage target via a convention-based probe order. Each language reference declares the exact order. The skill checks sources in order and stops at the first hit.

The probe order is deliberate: package-manager task definitions come before raw tool invocations because projects that use a task runner (`pixi`, `uv`, `npm`, `cargo`) have almost always pinned the coverage recipe there, and running through the runner ensures the correct virtual environment is active.

If no target is discoverable, return a structured "no target found" result and surface the language reference's setup guidance. Do not attempt to bootstrap tooling — that is explicitly out of scope.

### 2. Invoke

Run the located target when the caller asks. The caller — not the skill — owns the freshness decision. Three callers drive the skill in Praxion:

| Caller | Ownership of freshness |
|--------|------------------------|
| `/project-coverage` command | Command (user explicitly asked) |
| `/project-metrics --refresh-coverage` flag | User (via flag) |
| `verifier` agent | Verifier (at its discretion, not a hard trigger) |

The skill never regenerates coverage on a schedule, on a commit, or as a side effect of any other operation. Regeneration is opt-in.

On invocation failure (missing tool, non-zero exit, no artifact produced), emit a clear error that names the target that was tried and the exit status. Callers that embed the skill into a larger pipeline (e.g., `/project-metrics --refresh-coverage`) are expected to downgrade skill failure to a warning and continue — the skill itself does not swallow errors.

### 3. Render

Produce one consistent presentation across every surface the caller chooses: terminal (ANSI table), Markdown section (drop-in for reports), verifier-report fragment. The rendering invariants are language-independent and enforced centrally (see Presentation Conventions below). A future rendering surface (HTML, JSON, web UI) inherits the same invariants by calling the same render functions — no surface re-implements formatting inline.

## Presentation Conventions

Three invariants apply to every surface the skill renders. They exist because reading a coverage number should mean the same thing whether it shows up in a terminal, a Markdown report, or a verifier fragment.

### Delta Format — Percentage Points

Deltas from a prior run are rendered as `+2.1pp`, `-0.4pp`, `+0.0pp`. The `pp` suffix is load-bearing and non-optional.

Never render as `+2.8%` or bare `+2.8` — both are ambiguous (is it two *points*, or two *percent* of the prior value?). Percentage-point form disambiguates.

### Threshold Bands — 60 / 80

| Band   | Range            | Typical styling |
|--------|------------------|-----------------|
| Red    | `< 60%`          | Warning — coverage likely insufficient |
| Yellow | `60% ≤ x < 80%`  | Caution — acceptable, monitor trend |
| Green  | `x ≥ 80%`        | Healthy |

Projects may override the cutoffs via a documented mechanism (e.g., constants exposed by the render functions, a project-level config dict the caller passes in). The defaults above are what ships; any override is explicit and per-project.

### Per-File Breakdown — Fixed Column Order

Every surface renders per-file breakdowns with columns in this exact order:

```
path | covered/total | % | delta
```

- `path` — repo-relative (never absolute).
- `covered/total` — raw line ratio (e.g., `412 / 518`), so absolute magnitudes are visible alongside the percentage.
- `%` — percentage with band-appropriate color or style applied.
- `delta` — percentage-point delta from the prior run; empty when no prior run exists.

The fixed order is not a suggestion. Reordering in one surface but not another is the exact drift this skill exists to prevent.

## Gotchas

- **Activating the skill on a project without coverage tooling produces a "no target found" result, not a bootstrap.** The skill is explicitly not a tool installer. If the project has no `pixi` task, no `pytest-cov` config, no `pytest --cov` fallback, and no Makefile target, the probe returns empty — and the correct remediation is to add the tool as a real project dependency (see the language reference for the copy-pasteable config block).
- **Stale artifacts are parsed, not rejected.** Downstream consumers (e.g., `scripts/project_metrics/collectors/coverage_collector.py`) classify artifacts as `current` vs `stale` based on git commit timestamps and surface the staleness informationally. The skill does not enforce freshness — callers that need fresh numbers must invoke the skill explicitly (the "freshness decision" the caller owns, see Responsibility 2).
- **Concurrent `pytest --cov` runs race on `coverage.xml`.** If a user triggers `/project-metrics --refresh-coverage` while their own `pytest --cov` is running in another shell, the two processes race on the output file. The skill delegates writes to the project's coverage tool (which owns the file); document the race rather than attempt to lock at the skill layer.
- **`pp` is unfamiliar to many readers.** The percentage-point suffix is unusual enough that a first-time reader of a rendered table may wonder what it means. Callers exposing the rendering to end users should mention "pp = percentage points" once in on-help output or a legend — no need to repeat on every row.
- **The Python reference prescribes `coverage.xml` at the project root.** Not `coverage/coverage.xml`, not `.coverage`. The repo-root Cobertura XML is what the existing metrics collector probes first, and the default config block produces exactly that path. Changing the output path breaks the metrics pipeline silently (the collector falls through to other candidates or reports "no artifact").

## Related Artifacts

- [`testing-strategy`](../testing-strategy/SKILL.md) skill — coverage philosophy (coverage as discovery tool, not target); this skill provides the *mechanics* for projects that have decided to measure.
- [`testing-conventions`](../../rules/swe/testing-conventions.md) rule — declarative constraints for test code (what must be true of tests themselves).
- [`test-engineer`](../../agents/test-engineer.md) agent — pipeline agent for test authoring and execution.
- [`verifier`](../../agents/verifier.md) agent — loads this skill at its own discretion when coverage assessment is worth the time.
