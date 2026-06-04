---
name: agent-readiness
description: >
  Interpret and act on the Agent Readiness score produced by /project-metrics:
  8 Factory pillars × 5 maturity levels × 80%-per-level gate + Praxion-native
  Pillar 9 Manageability sub-score. Read the readiness block from
  METRICS_REPORT_*.json, understand the LLM-judged criteria
  (naming_conventions, test_quality, readme_quality, docs_agent_friendliness),
  prioritize remediation by failing criterion → pipeline handoff, and interpret
  level-by-level progress. Triggers: reading or acting on an agent readiness
  report, understanding why a project scored a given level, deciding how to
  improve readiness, interpreting mechanical vs LLM criteria, running readiness
  without an API key, grounding a new readiness run on a prior report.
allowed-tools: [Read, Glob, Grep, Bash]
compatibility: Claude Code
---

# Agent Readiness

Interpretation and remediation skill for the `/project-metrics` Agent Readiness
capability — a Factory-aligned rubric that scores a project's readiness for
autonomous agent collaboration across 8 industry-standard pillars and one
Praxion-native sub-score.

**This skill does NOT have a standalone `/readiness` command.** Readiness runs
through `/project-metrics`, writing its results into the `readiness` block of
`METRICS_REPORT_*.json`.

**Satellite files** (loaded on-demand):

- [references/rubric.md](references/rubric.md) — full criterion table (id, pillar, level, scope, llm-or-mechanical), applicability predicates, kodus-seed attribution, 80%-per-level gate mechanics

## How Readiness Rides /project-metrics

The readiness engine is a `ReadinessCollector` embedded in the metrics runner.
It always resolves as `Available` (pure filesystem reads) and always runs by
default. The `readiness` block appears at the root of `METRICS_REPORT_*.json`
under `collectors.readiness.data`.

### Invocation patterns

| Goal | Command |
|------|---------|
| Full run with LLM scoring (default when auth present) | `/project-metrics` |
| Mechanical-only, fast, free, no API key needed | `/project-metrics --mechanical-only` |
| Hard-fail if LLM tier cannot run | `/project-metrics --require-readiness-ai` |
| Combine with coverage refresh | `/project-metrics --refresh-coverage` |

The `--mechanical-only` flag is the recommended mode for CI pipelines and
offline environments. It scores all 25 mechanical criteria and marks the
4 LLM-judged criteria as `llm_skipped` in the output.

### Auth detection

The judge checks environment variables in this order:
1. `ANTHROPIC_API_KEY` → API-key auth (`x-api-key` header)
2. `CLAUDE_CODE_OAUTH_TOKEN` → OAuth auth (`Authorization: Bearer` header)

When neither is set: the run still exits 0, all 4 LLM criteria are set to
`passed: null`, and `readiness.data.llm.status == "llm_skipped"`. The level is
computed from mechanical criteria only with `readiness.data.note == "mechanical-only"`.

### Grounding on prior reports

When the LLM tier runs, the judge loads the most-recent
`METRICS_REPORT_*.json` from `.ai-state/metrics_reports/`, extracts the
`readiness.data.criteria` block, and passes each criterion's prior verdict to
the LLM call as grounding context. `readiness.data.llm.grounded_on` names the
prior report file, or `null` on the first run. This grounding reduces scoring
variance from run to run (Factory's 7%→0.6% variance reduction).

## The Rubric — Two-Layer Score

### Layer 1: 8 Factory Pillars × 5 Levels (the comparable number)

| Pillar | ID | Description |
|--------|-----|-------------|
| Style & Validation | `style_validation` | Linter, formatter, editorconfig, pre-commit, naming conventions |
| Build System | `build_system` | Build manifest, lockfile, CI pipeline |
| Testing | `testing` | Test directory, CI runs tests, test quality |
| Documentation | `documentation` | README, contributing guide, README quality, agent-friendliness |
| Dev Environment | `dev_environment` | .gitignore, container config, .env.example |
| Debugging & Observability | `observability` | Logging config, health check |
| Security & Governance | `security` | Dependency scanning, secrets policy, license |
| Code Quality | `code_quality` | Type-checker config, complexity gate |

**Level gate**: a project achieves level N when ≥80% of applicable criteria
at levels 1 through N collectively pass. Non-applicable criteria are excluded
from both numerator and denominator. This is the number that compares to the
kodus/Factory benchmark.

**Level interpretation:**

| Level | Signal | Typical state |
|-------|--------|---------------|
| 1 | Minimal | Has test dir, build manifest, README, .gitignore, license |
| 2 | Structured | Adds lockfile, formatter, .env.example, secrets policy, README quality |
| 3 | Practiced | CI pipeline + tests, pre-commit, contributing guide, container, observability, type-checker, dep-scanning |
| 4 | Advanced | Health check, complexity gate, test quality, agent-friendly docs |
| 5 | Factory-ready | All criteria at or above 80% pass rate across all 8 pillars |

### Layer 2: Pillar 9 Manageability (the Praxion sub-score)

Pillar 9 is **never folded into the 8-pillar level**. It appears separately as
`readiness.data.manageability` so the Factory-comparable level stays clean.

| Criterion | Level | What it checks |
|-----------|-------|---------------|
| `c.manage.claudemd` | 1 | `CLAUDE.md` project block present |
| `c.manage.agents_md` | 2 | `AGENTS.md` present (INFO — not counted as failure if absent) |
| `c.manage.git_hooks` | 3 | Project git hooks installed |
| `c.manage.ai_state` | 3 | `.ai-state/` intelligence directory present |

`c.manage.agents_md` is an informational criterion: its absence is noted but
does not count as a failed criterion in the manageability denominator.

## The 4 LLM-Judged Criteria

These criteria require LLM scoring and carry `llm: true` in the output. They
are excluded from every denominator when `llm_skipped`.

| Criterion ID | Pillar | Level | What the judge evaluates |
|---|---|---|---|
| `c.style.naming_conventions` | `style_validation` | 3 | Naming conventions are consistent and intention-revealing across the codebase |
| `c.testing.test_quality` | `testing` | 4 | Tests are behavior-focused and meaningfully cover the code (not just line coverage) |
| `c.docs.readme_quality` | `documentation` | 2 | README explains setup, usage, and architecture clearly |
| `c.docs.agent_friendliness` | `documentation` | 4 | Documentation is structured for agent consumption (clear headings, CLAUDE.md, structured context) |

When LLM criteria are scored, the judge uses forced tool-calling to get a
structured `{passed: bool, rationale: str}` verdict. The model is
`claude-haiku-4-5` with a 30-second timeout.

## Reading the Readiness Block

The `readiness` namespace in the JSON report has this shape:

```json
{
  "readiness": {
    "status": "ok",
    "duration_seconds": 0.42,
    "issues": [],
    "data": {
      "level": 3,
      "pass_pct": 0.81,
      "note": null,
      "pillars": [
        {
          "id": "style_validation",
          "name": "Style & Validation",
          "level_pass": [1, 2],
          "pass_pct": 1.0,
          "numerator": 4,
          "denominator": 4
        }
      ],
      "manageability": {
        "id": "manageability",
        "name": "Praxion Manageability",
        "pass_pct": 0.75,
        "numerator": 3,
        "denominator": 4
      },
      "criteria": [
        {
          "id": "c.style.linter_config",
          "pillar": "style_validation",
          "level": 1,
          "scope": "repo",
          "applicable": true,
          "passed": true,
          "llm": false,
          "rationale": "a linter configuration is present"
        }
      ],
      "llm": {
        "status": "llm_skipped",
        "model": null,
        "grounded_on": null
      }
    }
  }
}
```

`note: "mechanical-only"` appears when LLM criteria were skipped.
`llm.status` is one of: `"pending"` (before enrichment), `"llm_skipped"`,
`"scored"`, or `"llm_error"`.

## Prioritized Remediation Workflow

When a project is at level N and you want to reach level N+1:

1. **Identify failing criteria** — filter `data.criteria` where `passed == false`
   and `level <= N+1`. These are the blockers for the next level.

2. **Sort by urgency** — mechanical criteria first (no API key needed; fast to
   fix); LLM criteria second.

3. **Assess pillar coverage** — if one pillar is dragging pass_pct below 80%,
   focus there before spreading effort.

4. **Handoff to the pipeline:**
   - For infrastructure / config gaps (missing lockfile, CI, pre-commit):
     hand off to `implementation-planner` with the failing criterion as a
     concrete acceptance criterion.
   - For quality improvements (naming conventions, test quality, README):
     hand off to `researcher` first to gather current state, then `systems-architect`
     to design the improvement.
   - For Praxion manageability gaps: use `/onboard-project` (idempotent) to
     install missing surfaces (`CLAUDE.md` block, git hooks, `.ai-state/`).

5. **Re-run and compare** — after fixes, run `/project-metrics` again. The
   new report grounds on the prior one if LLM criteria were scored.

## Gotchas

- **Pillar 9 is never in the level.** Do not interpret `manageability.pass_pct`
  as contributing to the 8-pillar level. It is a separate Praxion-specific
  signal.

- **Non-applicable criteria are excluded.** A monorepo may have `scope="app"`
  criteria that produce `applicable: false`; these never appear in any
  denominator, so a project with 0 apps that scores 100% on repo criteria is
  not being "cheated" — it simply has no app-scoped surface yet.

- **`--require-readiness-ai` hard-fails before any write.** If auth is absent
  and this flag is set, the process exits non-zero and no report is written.
  Do not use this flag in offline CI.

- **`llm.status == "pending"` means the collect pass completed but enrichment
  has not run yet.** This state should not appear in the written report — if it
  does, the enrichment step was skipped or errored without updating the block.

- **The 80% gate is cumulative through levels.** A project that passes 100% of
  level-1 criteria but only 50% of level-2 criteria scores level 1, not level 2,
  even if level-2 criteria represent the minority. The gate requires ≥80% of
  *all applicable criteria at level 1 and below* — levels are additive.

## Related Skills and Commands

- **`/project-metrics`** — the command that runs the readiness engine. All
  readiness flags are arguments to this command.
- **`doc-management`** — improves README quality and contributing guide
  presence (affects `c.docs.readme`, `c.docs.contributing`, `c.docs.readme_quality`).
- **`observability`** — improves logging config and health-check presence
  (affects `c.observability.logging_config`, `c.observability.healthcheck`).
- **`cicd`** — improves CI pipeline and test execution (affects
  `c.build.ci_pipeline`, `c.testing.ci_runs_tests`).
- **`architectural-fitness-functions`** — improves type-checker and complexity
  gate presence (affects `c.codequality.typecheck_config`,
  `c.codequality.complexity_gate`).
