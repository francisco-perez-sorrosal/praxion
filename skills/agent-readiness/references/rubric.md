# Agent Readiness Rubric

Full criterion definitions for the 8 Factory pillars + Pillar 9 Manageability.
Back-link: [../SKILL.md](../SKILL.md).

Seeded from the kodus 39-check MIT list, mapped to the 8 Factory pillars.
The 4 LLM criteria mirror the kodus `--ai` flag split. The implementation is
`scripts/project_metrics/collectors/readiness/criteria.py`.

## Maturity Levels (L1–L5)

Levels are additive maturity tiers, not pillars. Each criterion is gated at one level:

| Level | Name | Meaning |
|-------|------|---------|
| L1 | Foundational | The essentials exist (linter, build manifest, tests, README, .gitignore, LICENSE, CLAUDE.md). |
| L2 | Consistent | Consistency & reproducibility (formatter, editorconfig, lockfile, env example, secrets policy, README quality). |
| L3 | Automated | Automation & enforcement (pre-commit, CI + CI-runs-tests, contributing, containerization, logging, dependency scanning, type-checking, git hooks). |
| L4 | Robust | Depth & quality (test quality, agent-friendly docs, health checks, complexity/coverage gate). |
| L5 | Exemplary | Best-in-class. **No mechanical criteria gate L5 yet** — reserved for future checks, so L4 is effectively the ceiling today. |

**Not every pillar has a criterion at every level** — this is expected, not a gap. A pillar's heatmap cell at a level with no criteria renders `–` ("no criteria at this level"), never a vacuous ✓. (The scorer treats an empty level as vacuously met for progression, but the dashboard distinguishes "passed" from "nothing to check" by counting applicable criteria per pillar-level.)

## The 80%-per-Level Gate

A project achieves **level N** when at least 80% of applicable criteria at
levels 1 through N (inclusive) pass collectively. Levels are additive — passing
all of level 3 is only possible after also passing 80% of levels 1 and 2.

Non-applicable criteria (`applicable: false`) are excluded from both numerator
and denominator. Pillar 9 (Manageability) criteria are **never included** in
the 8-pillar level computation — they appear only in `data.manageability`.

The `INFO_NOT_FAIL_CRITERIA` set (`frozenset({"c.manage.agents_md"})`) lists
criteria whose failure is informational: they are excluded from the pillar
denominator rather than counted as failed.

## Criterion Table

Format: `id | pillar | level | scope | llm-or-mech | rationale`

Scope: `repo` = whole-repo signal, `app` = per-app in a monorepo (root counts as
the single app for non-monorepo projects).

### Pillar 1: Style & Validation (`style_validation`)

| ID | Level | Scope | Type | Rationale |
|----|-------|-------|------|-----------|
| `c.style.linter_config` | 1 | repo | mechanical | a linter configuration is present |
| `c.style.formatter_config` | 2 | repo | mechanical | a formatter configuration is present |
| `c.style.editorconfig` | 2 | repo | mechanical | an `.editorconfig` is present |
| `c.style.precommit_config` | 3 | repo | mechanical | a pre-commit configuration is present |
| `c.style.naming_conventions` | 3 | repo | **LLM** | naming conventions are consistent and intention-revealing |

### Pillar 2: Build System (`build_system`)

| ID | Level | Scope | Type | Rationale |
|----|-------|-------|------|-----------|
| `c.build.manifest` | 1 | repo | mechanical | a build/dependency manifest is present |
| `c.build.lockfile` | 2 | repo | mechanical | a dependency lockfile pins versions |
| `c.build.ci_pipeline` | 3 | repo | mechanical | a CI pipeline configuration is present |

### Pillar 3: Testing (`testing`)

| ID | Level | Scope | Type | Rationale |
|----|-------|-------|------|-----------|
| `c.testing.test_directory` | 1 | repo | mechanical | a test directory or test files are present |
| `c.testing.ci_runs_tests` | 3 | repo | mechanical | CI configuration invokes the test suite |
| `c.testing.test_quality` | 4 | repo | **LLM** | tests are behavior-focused and meaningfully cover the code |

### Pillar 4: Documentation (`documentation`)

| ID | Level | Scope | Type | Rationale |
|----|-------|-------|------|-----------|
| `c.docs.readme` | 1 | repo | mechanical | a README is present |
| `c.docs.readme_quality` | 2 | repo | **LLM** | the README explains setup, usage, and architecture clearly |
| `c.docs.contributing` | 3 | repo | mechanical | a contributing guide is present |
| `c.docs.agent_friendliness` | 4 | repo | **LLM** | documentation is structured for agent consumption |

### Pillar 5: Dev Environment (`dev_environment`)

| ID | Level | Scope | Type | Rationale |
|----|-------|-------|------|-----------|
| `c.devenv.gitignore` | 1 | repo | mechanical | a `.gitignore` is present |
| `c.devenv.env_example` | 2 | repo | mechanical | an environment-variable example file is present |
| `c.devenv.containerized` | 3 | repo | mechanical | a container or devcontainer configuration is present |

### Pillar 6: Debugging & Observability (`observability`)

| ID | Level | Scope | Type | Rationale |
|----|-------|-------|------|-----------|
| `c.observability.logging_config` | 3 | repo | mechanical | logging or observability configuration is present |
| `c.observability.healthcheck` | 4 | repo | mechanical | a health-check or monitoring surface is present |

### Pillar 7: Security & Governance (`security`)

| ID | Level | Scope | Type | Rationale |
|----|-------|-------|------|-----------|
| `c.security.license` | 1 | repo | mechanical | a LICENSE file is present |
| `c.security.secrets_policy` | 2 | repo | mechanical | a secrets-management policy or scanner is present |
| `c.security.dependency_scanning` | 3 | repo | mechanical | automated dependency scanning is configured |

### Pillar 8: Code Quality (`code_quality`)

| ID | Level | Scope | Type | Rationale |
|----|-------|-------|------|-----------|
| `c.codequality.typecheck_config` | 3 | repo | mechanical | a static type-checker configuration is present |
| `c.codequality.complexity_gate` | 4 | repo | mechanical | a complexity or quality gate is configured |

### Pillar 9: Praxion Manageability (`manageability`) — separate sub-score

Never folded into the 8-pillar level. Reported as `data.manageability`.

| ID | Level | Scope | Type | Applicability | Rationale |
|----|-------|-------|------|---------------|-----------|
| `c.manage.claudemd` | 1 | repo | mechanical | always | a `CLAUDE.md` project block is present |
| `c.manage.agents_md` | 2 | repo | mechanical | always | an `AGENTS.md` surface is present (**INFO** — not failure if absent) |
| `c.manage.git_hooks` | 3 | repo | mechanical | always | project git hooks are installed |
| `c.manage.ai_state` | 3 | repo | mechanical | always | an `.ai-state/` intelligence directory is present |

## LLM Judge Details

The 4 LLM criteria use the Anthropic Messages API directly via `urllib.request`
(no `anthropic` SDK import — consistent with the metrics package's stdlib-only
constraint). The judge uses forced `tool_choice` to get a structured verdict.

- **Default model**: `claude-haiku-4-5`
- **Timeout**: 30 seconds per criterion
- **Grounding**: each call receives the prior run's verdict for that criterion
  (from the most-recent `METRICS_REPORT_*.json`) to reduce inter-run variance

Auth precedence: `ANTHROPIC_API_KEY` (header `x-api-key`) → `CLAUDE_CODE_OAUTH_TOKEN`
(header `Authorization: Bearer`). Neither set → `llm_skipped`.

## Educational Content & Recommendations

Each `Criterion` (in `criteria.py`) carries two authored fields beyond `rationale`,
embedded in every report so consumers need not reach into the plugin:

- `explanation` — "what this measures and why it matters". Surfaced in dashboard
  hovers (per-criterion pip tooltips; per-pillar from `PILLAR_DOCS`) and in the
  JSON report. Instrument-level concepts (level, the 80%-gate, pass %, the
  radar/heatmap, Pillar 9) live in the dashboard's `readiness-docs.ts` and render
  through the shared `EducationalPopover`.
- `remediation` — "how to fix it", shown for **failing** criteria. The 25
  mechanical criteria carry deterministic, reproducible guidance. For the 4
  LLM-judged criteria, the enrichment step layers a **project-specific
  recommendation** from the same judge call (no extra API request) over the
  static text and flips the per-criterion `remediation_source` from `"static"`
  to `"llm"`. Offline (mechanical-only) runs fall back to the static guidance.

The judge `verdict` tool gained an optional `recommendation` field, requested
only when `passed` is false. The Markdown report renders the failing-criteria
recommendations under the readiness section; the dashboard renders them in the
"Recommendations" panel with an "AI-tailored" badge on LLM-sourced items.

This content (and `remediation_source`) is additive in schema **1.2.0**; reports
written under 1.1.0 simply omit the fields and degrade cleanly.

## Pillar Weighting (per-project relevance)

Not every pillar matters equally for every project — a research harness, a docs
site, or philosophy-as-infrastructure (like Praxion itself) may not need a
runtime service's observability or containerization. Equal-weighting then drags
the headline score down unfairly.

An optional committed config re-weights pillars:

```
.ai-state/readiness_config.json
{
  "pillar_weights": {
    "observability": 0,        // 0 excludes the pillar from the adjusted score
    "dev_environment": 0.5     // < 1 counts it less
  }
}
```

Rules: weights are floats `>= 0`; unlisted pillars default to `1.0`; only the
eight Factory pillars are weightable (Pillar 9 is always separate). Malformed
config degrades to a warning and is ignored — the run still succeeds. Stdlib
`json` only (loader: `collectors/readiness/config.py`).

**Two scores, both reported** (so comparability is never lost):

- **Canonical** (`level` / `pass_pct`) — always unweighted; the cross-tool-comparable Factory number.
- **Adjusted** (`adjusted_level` / `adjusted_pass_pct`) — the weight-aware project headline. Equal to canonical when no config is present (`weighting_active: false`).

Weighting is implemented as a per-criterion multiplier in the shared `_pass_pct`
primitive, so it threads uniformly through both the overall pass% and the level
gate, and reduces *exactly* to the canonical number when weights are uniform.
Each pillar record carries its `weight` and an `excluded` flag. Additive in
schema 1.2.0.

## Kodus Attribution

The mechanical criteria set is seeded from the
[kodus](https://github.com/kodus-ai/kodus) 39-check MIT-licensed rubric,
mapped to the 8 Factory pillars. The 4 LLM criteria mirror the kodus `--ai`
flag split: naming conventions, test quality, README quality, and
documentation agent-friendliness. Pillar 9 (Manageability) is Praxion-native —
it covers Praxion-specific surfaces (`CLAUDE.md`, `AGENTS.md`, git hooks,
`.ai-state/`) not present in the kodus rubric.

## Implementation Reference

```
scripts/project_metrics/collectors/readiness/
  __init__.py           — re-exports ReadinessCollector, enrich_readiness
  criteria.py           — CRITERIA tuple (29 criteria), PILLAR_NAMES, INFO_NOT_FAIL_CRITERIA
  checks.py             — mechanical check functions (filesystem, config-parse)
  score.py              — compute_level(), recompute() (80%-per-level gate, Pillar-9 separate)
  judge.py              — detect_auth(), judge_criterion() (stdlib urllib, no anthropic)
scripts/project_metrics/collectors/readiness_collector.py — ReadinessCollector(Collector)
scripts/project_metrics/cli.py                            — enrich_readiness() (outside collect pass)
```
