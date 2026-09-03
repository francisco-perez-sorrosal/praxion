<!--
  Section ownership (per skills/testing-strategy/references/test-topology.md
  §"Topology Regeneration Policy"):

  - ## Subsystems (this section)      : systems-architect
  - Per-group YAML blocks             : test-engineer
  - integration_boundaries (in blocks): implementation-planner (populated lazily)

  This file is NOT auto-regenerated at any pipeline boundary. Refresh via
  `/refresh-topology` (drift reconciliation) or `/refresh-topology --init`
  (first-time scaffold). Whoever regenerates the whole file becomes the
  de-facto owner of every section, which is exactly what section ownership
  exists to prevent — so edit your own section in place.
-->

# Test Topology — Praxion

Maps Praxion's Built structural components to the logical test groups that cover them, so
that a change's test radius adapts to what actually changed instead of firing the full suite
every time.

**Trunk schema:** [`skills/testing-strategy/references/test-topology.md`](../skills/testing-strategy/references/test-topology.md)
— group schema, tier vocabulary, selector/parallel-runner registries, closure semantics, and
the reserved-name set. Python leaf: `references/python-testing.md` in the same skill.

**Section ownership.** The architect owns the `## Subsystems` section below (the
component→group binding). The test-engineer owns the per-group YAML blocks (`selectors`,
`file_dependencies`, `tier`, `parallel_safe`, `shared_fixture_scope`,
`expected_runtime_envelope`). The implementation-planner owns `integration_boundaries` inside
those blocks. Each editor edits their own section in place.

**`integration_boundaries` populate lazily** and are intentionally empty at init — cross-group
coupling is recorded when a real pipeline discovers it, not guessed up front.

**Adoption basis (measured 2026-08-07).** All three growth-trigger thresholds are crossed:
full-suite wall-clock ~119 s (≥90 s), 16 Built structural components in
[`DESIGN.md`](DESIGN.md) §3a (≥4), 2,912 tests in the canonical corpus (≥200). The canonical
corpus is `testpaths = ["tests", "scripts", "hooks"]`; `fitness/` sits outside it and runs as
a dedicated CI job (`.github/workflows/architecture.yml`).

---

## Subsystems

Every component in [`DESIGN.md`](DESIGN.md) §3a appears below. Component names are reproduced
**verbatim** from that table — group blocks must reference them exactly (sentinel TT01 checks
the binding, and §3b capabilities are explicitly not valid group boundaries).

| Component (`DESIGN.md` §3a) | Test group(s) | Binding rationale |
|---|---|---|
| Skills | `knowledge-projection`, `repo-gates`, `architecture-fitness` | Markdown surface with no unit tests of its own. Exercised indirectly: frontmatter/structure gates (`repo-gates`), the generators that project skills into shipped/derived form (`knowledge-projection`), and import/reference boundary contracts (`architecture-fitness`). |
| Agents (authored definitions) | `knowledge-projection`, `agent-orchestration`, `repo-gates`, `architecture-fitness` | Same indirect pattern as Skills, plus `agent-orchestration` for tests that assert a specific agent definition's contract (verifier manifest/findings schema, researcher redirect, skill-genesis). |
| Rules | `knowledge-projection`, `repo-gates`, `architecture-fitness` | Markdown surface. `knowledge-projection` covers the rules-manifest generator and the always-loaded token budget; `repo-gates` covers `paths:` frontmatter syntax and shipped-artifact isolation. |
| Commands | `knowledge-projection`, `agent-orchestration`, `repo-gates` | Markdown surface. Command *behavior* contracts (resume-rework, upgrade-project, skill-genesis-review) land in `agent-orchestration`; the onboarding commands' install effects land in `onboarding-contract` via the Installers row. |
| Agent runtime / Pipeline | `agent-orchestration`, `hooks-lifecycle` | Rework routing/spawn/dispatch, pipeline cleanup, checkpoint digest, background-session notification, hackathon-mode tiering. `hooks-lifecycle` because lifecycle enforcement and context injection are where the runtime is actually observable. |
| Hooks | `hooks-lifecycle` | The one component with a dedicated, self-contained group: ~623 tests over `hooks/`, 29.4 s, no fan-out needed. |
| Chronograph MCP | **— (separate runner)** | No coverage in the canonical corpus. Own uv project: `cd task-chronograph-mcp && uv run pytest` (7 test files). See [Components outside the canonical corpus](#components-outside-the-canonical-corpus). |
| `.ai-state/` | `state-ledgers`, `decision-records` | Split by lifecycle, not by directory: records with a finalize/promote edge (ADRs, specs index) go to `decision-records`; ledgers, reconciliation, retention, and freshness go to `state-ledgers`. |
| `.ai-work/` | `state-ledgers`, `agent-orchestration` | Cleanup safety and pipeline-state reconciliation (`state-ledgers`); task-slug-scoped artifact production and rework manifests (`agent-orchestration`). |
| Installers | `install-and-export`, `onboarding-contract` | Deliberately split by *what breaks*: `install-and-export` is the projection/deployment machinery (heavy, subprocess-bound); `onboarding-contract` is the end-state a managed project must have. An installer refactor fires both; an onboarding-block edit fires only the latter. |
| Scripts | `scripts-core`, `repo-gates`, `decision-records`, `state-ledgers`, `knowledge-projection`, `install-and-export`, `project-metrics`, `praxion-feedback`, `ci-workflows` | **Deliberate 9-way fan-out.** One `Scripts` group would be 88 test files and 66 s — the exact anti-pattern the topology exists to avoid. See [Why `Scripts` fans out](#why-scripts-fans-out). |
| Eval framework | **— (separate runner)** | No coverage in the canonical corpus. Own uv project: `cd eval && uv run pytest` (9 test files). Note the near-miss: `tests/test_append_eval_log.py` and `tests/test_run_store_backend.py` sit in `state-ledgers`, but they target the `agent-evals` **skill's** producer and a schema-convention doc — not `eval/`. See [Components outside the canonical corpus](#components-outside-the-canonical-corpus). |
| Tech-debt ledger | `state-ledgers` | Finalize script, ledger/resolved pair invariants, and the state-ledger gate all sit together; a ledger-schema change wants exactly this radius. |
| Pipeline Dashboard | **— (separate runner)** | No coverage in the canonical corpus and **not expressible under the current registry**: 43 vitest suites under `dashboard_app/`, run via `cd dashboard_app && ./node_modules/.bin/vitest run`. `vitest-projects` is an *indicative future* identifier in Registry 1, not a registered one. See [Objection](#objection--three-components-cannot-be-given-a-sound-group-today). |
| ADR fragments | `decision-records` | The draft→`dec-NNN` promotion lifecycle (finalize, chain, frontmatter promotion, reference validation, health) is one coherent edit surface. |
| Versioning | `ci-workflows` | Only surface with tests is release-staleness plus the release/CI workflow invariants. Small but real — this row exists so a Versioning change has a named radius rather than defaulting to the full suite. |

### Group index (architect-owned, non-normative)

The reverse view of the table above, with the measured facts that drove the cut. Test counts
are collect-only scrapes taken 2026-08-07 and are **indicative sizing**, not a contract — the
test-engineer's `selectors` and `file_dependencies` are authoritative on membership, and
`expected_runtime_envelope` is theirs to measure and declare.

| Group id | Covers (components) | Change-locality intent | Indicative size |
|---|---|---|---|
| `hooks-lifecycle` | Hooks; Agent runtime / Pipeline | A hook script edit. Self-contained by construction. | ~623 tests, 29.4 s |
| `decision-records` | `.ai-state/`; ADR fragments; Scripts | ADR/spec record lifecycle: finalize, promote, index, validate. | ~150 tests; carries `test_adr_health.py` (5.6 s) |
| `state-ledgers` | `.ai-state/`; `.ai-work/`; Tech-debt ledger; Scripts | Ledger append/finalize, `.ai-state`/`.ai-work` reconciliation, retention, freshness. | ~230 tests |
| `repo-gates` | Skills; Agents; Rules; Commands; Scripts | An edit to any `scripts/check_*.py` commit/CI gate. **The most common inner-loop group — and it carries none of the four heavy files.** | ~222 tests |
| `knowledge-projection` | Skills; Agents; Rules; Commands; Scripts | Generators that project the authored knowledge surface into shipped or derived form (canonical blocks, CLAUDE.md render, doc manifest, artifact registry, rules manifest, token budget). | ~175 tests |
| `install-and-export` | Installers; Scripts | Installer / Codex-export / dependency-pin machinery. **Isolation win: 25 s of `scripts/`'s 66 s in 86 tests** — `test_install_codex.py` (18.0 s) and `test_upgrade_project_pins.py` (7.0 s) both land here, so no other group pays them. | ~86 tests, ~25 s |
| `onboarding-contract` | Installers; Commands | The end state `/onboard-project` and `/new-project` must produce in a managed project. | ~123 tests |
| `agent-orchestration` | Agent runtime / Pipeline; Agents; Commands; `.ai-work/` | Rework routing/spawn/dispatch, pipeline cleanup, checkpoints, tier selection, per-agent contract assertions. | ~140 tests |
| `ci-workflows` | Versioning; Scripts | GitHub Actions invariants (autofix, cross-model review, issue intake, labels, finalize, architecture gate) plus self-healing metrics and release staleness. | ~335 tests |
| `project-metrics` | Scripts | The `scripts/project_metrics/` sub-package — collectors, readiness scoring, trends, reporting. Carries `test_integration.py` (8.3 s). | ~682 tests |
| `praxion-feedback` | Scripts | The `scripts/praxion_feedback/` sub-package plus the issue-report entry points. | ~106 tests |
| `scripts-core` | Scripts | Shared `scripts/` plumbing (`repo_root.py`, `_git_runner.py`) imported by nearly everything. Small on purpose: it exists so the planner has a node to hang wide `integration_boundaries` off, since a change here legitimately deserves a large radius. | ~38 tests |
| `architecture-fitness` | Skills; Agents; Rules | Import-boundary and structural-invariant suite under `fitness/`. **Outside `testpaths`** — runs as a dedicated job in `.github/workflows/architecture.yml`, so its selector must name `fitness/` explicitly rather than relying on the default corpus. | 138 tests, 6.1 s |

All 13 ids are kebab-case and clear of the reserved-name set (`unit`, `integration`,
`contract`, `e2e`, `parametrize`, `skipif`, `xfail`, `usefixtures`, `xdist_group`,
`parallel_unsafe`).

### Why `Scripts` fans out

`Scripts` is a single row in `DESIGN.md` §3a but 88 test files and 66 s of wall-clock — 55 % of
the canonical suite's runtime. Modelling it as one group would make every `scripts/` edit fire
every `scripts/` test, which is the full-suite behavior the topology exists to replace.

The fan-out is possible *because the cost is concentrated*: four files are 59 % of `scripts/`'s
66 s, and the cut places them where they fire rarely.

| Heavy file | Duration | Lands in | Fires when |
|---|---|---|---|
| `scripts/test_install_codex.py` | 18.0 s | `install-and-export` | Installer or Codex-export change |
| `scripts/project_metrics/tests/test_integration.py` | 8.3 s | `project-metrics` | Metrics sub-package change |
| `scripts/test_upgrade_project_pins.py` | 7.0 s | `install-and-export` | Installer or pin-upgrade change |
| `scripts/test_adr_health.py` | 5.6 s | `decision-records` | ADR lifecycle change |

Net effect: a typical edit to a `scripts/check_*.py` gate fires `repo-gates` (~222 tests) and
pays **none** of the four. That is the whole design goal, and it is achievable here only
because the expensive tests cluster into subsystems that change infrequently.

The cut is by *coherent edit surface*, not by directory. `scripts/test_check_*.py` files split
across `repo-gates`, `state-ledgers`, `project-metrics`, and `ci-workflows` according to what
each gate actually guards — a filename-prefix cut would have been tidier and less useful.

### Components outside the canonical corpus

Three components have **no** pytest coverage under `testpaths = ["tests", "scripts", "hooks"]`.
They are recorded here rather than omitted: a component absent from the table is
indistinguishable from one nobody thought about.

| Component | Suite location | Invocation |
|---|---|---|
| Chronograph MCP | `task-chronograph-mcp/tests/` (7 files) | `cd task-chronograph-mcp && uv run pytest` |
| Eval framework | `eval/tests/` (9 files) | `cd eval && uv run pytest` |
| Pipeline Dashboard | `dashboard_app/tests/` (43 files) | `cd dashboard_app && ./node_modules/.bin/vitest run` |

These are covered in CI (`.github/workflows/test.yml` for the two uv projects) but are not
addressable from a topology group today.

### Objection — three components cannot be given a sound group today

Registered under Registry 1 (§"Selector Strategy Registry") there is no strategy that can
express "invoke a different test runner in a different environment":

- `pytest-globs`, `pytest-markers`, `pytest-keywords` all materialize as a `pytest` invocation
  in the **root** environment. `task-chronograph-mcp/` and `eval/` are separate uv projects
  with their own dependency sets and `requires-python = ">=3.13"`; a root-interpreter `pytest
  task-chronograph-mcp/tests` would not resolve their dependencies.
- `vitest-projects` is listed in Registry 1 only as an **indicative future** identifier, with an
  explicit instruction that it "must not be used in `TEST_TOPOLOGY.md` files until the
  corresponding leaf file ships." The dashboard therefore has no legal selector at all.

Inventing group ids for these three would produce entries whose `selectors` cannot be
materialized — a fictional boundary that reads as coverage and delivers none. Per the trunk's
**Additive Leaf Escalation Clause**, the correct path is escalation, not a hardcoded workaround:
if these suites should join the topology, register a new selector strategy (an
`external-runner`-shaped identifier carrying a working directory plus a command, and/or the
TypeScript leaf's `vitest-projects`) via an ADR, then add the groups. Until then the honest
record is "no group; covered by X," which is what the table says.

This is a scoping objection, not a blocker: the 13 groups above cover all 16 components'
*canonical-corpus* surface, and the three separate-runner suites keep running in CI exactly as
they do today.

---

## Test Groups

<!--
  test-engineer-owned (per the section-ownership header at the top of this file).
  The architect owns everything above this line; the implementation-planner owns the
  `integration_boundaries` list inside each block below. Edit your own field, in place.
-->

### How these blocks were built

**Selector strategy is `pytest-globs` for every group — deliberately, not by default.** A
`pytest-markers` cut would require adding `@pytest.mark.<group>` to all 152 test files,
creating a second source of truth that drifts from the paths it duplicates. This corpus is
already path-aligned (`scripts/test_X.py` sits beside `scripts/X.py`), so globs are both
natural and precise. Two consequences worth knowing: no `[tool.pytest.ini_options] markers`
registration is needed for any group, and sentinel **TT05 correctly skips** (it constrains
marker-name collisions, and no group declares a marker selector) rather than passing
vacuously.

**Every group id is clear of the reserved-name set** (`unit`, `integration`, `contract`,
`e2e`, `parametrize`, `skipif`, `xfail`, `usefixtures`, `xdist_group`, `parallel_unsafe`) —
verified against both the trunk set and the Python leaf's superset.

**`subsystems` values are the `DESIGN.md` §3a Component-column names verbatim**, with the
markdown backticks of `` `.ai-state/` `` / `` `.ai-work/` `` stripped — the backticks are
table formatting, not part of the component's name.

**One group declares `integration_boundaries`.** `decision-records` names `knowledge-projection`,
populated by the `adr-living-view` pipeline: `rules/swe/adr-conventions.md` and
`skills/software-planning/references/adr-authoring-protocols.md` are `decision-records`
`file_dependencies` *and* match `knowledge-projection`'s `rules/**/*.md` / `skills/**/*.md`
globs, and `agents/sentinel.md`'s DL/DH rows are behavioural consumers of `scripts/adr_health.py`.
A change to the ADR schema therefore has a radius neither group's own selectors cover. Every
other group omits the field. It is planner-owned, optional in the
trunk schema ("0 or more entries"), and populates lazily when a real pipeline discovers actual
cross-group coupling — guessed boundaries would be indistinguishable from measured ones the
moment they were written. Omission, not `[]`, is how that zero state is written, for a
mechanical reason worth recording: `scripts/_topology_yaml.py::_flow_sequence` rejects *any*
empty flow sequence with the message "empty flow sequence is not a valid selector argument".
That rule is correct for a `pytest-globs`/`pytest-markers` `arg` (the trunk requires 1+ entries
there) but it is applied to every key, so the schema-legal `integration_boundaries: []` makes
the whole file unparseable by its own resolver. Omitting the key is equally schema-legal and
parses cleanly. **When the planner adds the first boundary it adds the key with entries in
it** — there is never a reason to write the empty form.

### Coverage invariant — 152 / 152, zero orphans

The canonical corpus (`testpaths = ["tests", "scripts", "hooks"]`) is **152 test files** — 88
under `scripts/`, 45 under `tests/`, 19 under `hooks/`. Every one is selected by exactly one
group's `selectors`. This was verified mechanically: `pytest --collect-only -q` was run per
group, the resulting file sets unioned, and the union diffed against pytest's own collector
output for the whole corpus. Result: **152 covered, 0 orphaned, 0 overlapping.**

A test file claimed by no group can never run under a scoped invocation — it would vanish
silently from every `step`- and `phase`-tier run while the full suite still passed. **Re-run
that diff whenever a group's `selectors` change or a test file is added or moved.** The
`architecture-fitness` group contributes 0 to this count by design: `fitness/` sits outside
`testpaths` and its 6 files are additional to the 152.

### About `expected_runtime_envelope`

Every group carries one, derived from **three consecutive sequential local runs** on a
developer machine (Darwin, warm caches, one `pytest` invocation per group). `p50_seconds` is
the median of those three; `p95_seconds` is the observed maximum rounded up to the next whole
second — a *measured local ceiling*, not a distributional p95 from a real sample.

That distinction matters for the M3 activation of sentinel TT04: these numbers are not CI
numbers, and a slower runner will exceed them. TT04's +50% tolerance absorbs ordinary
variance, but **these envelopes should be recalibrated from per-group metrics collected over
real pipeline cycles before TT04 is allowed to file `topology-drift` rows against them.** They
are recorded because measured-and-caveated beats absent; they are not yet a contract.

**Advisory status (2026-08-13, closing sentinel S-05's disclosure arm):** no instrument reads
these envelopes today — 0 of 10 metrics reports emit per-group timings, so sentinel TT04 has no
oracle and correctly reports SKIP rather than PASS. Until a per-group timing collector exists in
`scripts/project_metrics/` (the named prerequisite for TT04's M3 activation), every envelope in
this file is **advisory, undefended by any gate** — a reader planning against one should treat
it as a stale local measurement, not a monitored bound.

### About `parallel_safe`

`pytest-xdist` is **not installed in this project**, so no `-n auto` run was available to
validate the declarations empirically. In its place each group was probed by running two
independent `pytest` processes over the same group concurrently — an approximation that
exposes the hazard class xdist actually produces (races on a fixed filesystem path, a shared
git working tree, or an unlocked session-scoped rebuild). A probe failure is proof of
unsafety; a probe pass is evidence of no interference, not a proof of safety.

Eleven groups passed the probe and are declared `true`. Two failed and are declared `false`,
each with the specific shared resource named in its `notes`. One methodological note: three
groups initially appeared to race on `sqlite3.OperationalError: ... '.coverage'`. That is a
**probe artifact** — two separate `pytest` processes both writing the repo-root `.coverage`
file — and not a group property, since `pytest-cov` gives each xdist worker its own data file
within a single session. Re-probing with coverage disabled cleared all three. It is recorded
here so a future editor does not re-derive it, or worse, mistake it for a real finding.

---

### `hooks-lifecycle`

```yaml
id: hooks-lifecycle
title: Hook lifecycle — enforcement, injection, observability
subsystems:
  - Hooks
  - Agent runtime / Pipeline
tier: integration
selectors:
  - strategy: pytest-globs
    arg:
      - "hooks/"
      - "tests/test_notify_bg_session_state.py"
file_dependencies:
  - "hooks/*.py"
  - "hooks/*.sh"
  - "hooks/hooks.json"
  - ".claude-plugin/plugin.json"
parallel_safe: true
shared_fixture_scope: per-test
expected_runtime_envelope:
  p50_seconds: 29.3
  p95_seconds: 30
shared_state: tmp_path
notes: "Self-contained by construction -- 20 files, 623 tests, no fan-out.
  2026-09-03: hooks/test_inject_sidecar_banner.py and
  hooks/test_sidecar_autocommit.py added (sidecar-placement P1, RED-first
  against praxion-sidecar stub fixtures); both already match the hooks/
  selector glob above, no selector change needed."
```

The tier is `integration` rather than `unit` because 14 of the 20 files spawn real
hook subprocesses against a fake `HOME` built under `tmp_path`.
`tests/test_notify_bg_session_state.py` lives outside `hooks/` but targets
`hooks/notify_bg_session_state.py`, so it is named explicitly in the selector.

### `decision-records`

```yaml
id: decision-records
title: ADR and spec record lifecycle — finalize, promote, index, validate
subsystems:
  - .ai-state/
  - ADR fragments
  - Scripts
tier: integration
selectors:
  - strategy: pytest-globs
    arg:
      - "scripts/test_adr_health.py"
      - "scripts/test_check_adr_frontmatter_promotion.py"
      - "scripts/test_check_design_checkpoint.py"
      - "scripts/test_check_spec_archival_gap.py"
      - "scripts/test_check_spec_drift.py"
      - "scripts/test_finalize_adrs.py"
      - "scripts/test_finalize_chain.py"
      - "scripts/test_query_adrs.py"
      - "scripts/test_regenerate_adr_index.py"
      - "scripts/test_regenerate_specs_index.py"
      - "scripts/test_validate_adr_references.py"
      - "tests/test_adr_frontmatter_parseable.py"
      - "tests/test_criteria_spec_eval.py"
      - "tests/test_sh07_sentinel.py"
      - "tests/test_spec_drift.py"
file_dependencies:
  - "scripts/adr_health.py"
  - "scripts/finalize_adrs.py"
  - "scripts/finalize_adrs_backlinks.py"
  - "scripts/finalize_adrs_crossrefs.py"
  - "scripts/finalize_adrs_fragments.py"
  - "scripts/finalize_chain.sh"
  - "scripts/git-finalize-hook.sh"
  - "scripts/query_adrs.py"
  - "scripts/regenerate_adr_index.py"
  - "scripts/regenerate_specs_index.py"
  - "scripts/validate_adr_references.py"
  - "scripts/check_adr_frontmatter_promotion.py"
  - "scripts/check_design_checkpoint.py"
  - "scripts/check_spec_archival_gap.py"
  - "scripts/check_spec_drift.py"
  - "scripts/spec_drift.py"
  - "scripts/check_p06_task_brief.py"
  - "rules/swe/adr-conventions.md"
  - "skills/software-planning/references/adr-authoring-protocols.md"
  - "skills/spec-driven-development/**/*.md"
integration_boundaries:
  - knowledge-projection
parallel_safe: true
shared_fixture_scope: per-test
expected_runtime_envelope:
  p50_seconds: 10.3
  p95_seconds: 14
shared_state: filesystem
notes: "Carries test_adr_health.py (5.6 s), one of the four heavy files."
```

Integration tier because the finalize suite drives real `git` over repositories built
in `tmp_path`. `scripts/check_p06_task_brief.py` is a declared dependency even though
its own test file lives in `repo-gates` — `tests/test_criteria_spec_eval.py` drives
`run_p06` as link 1 of the criteria-to-spec chain, so a change there must fire this
group too.

### `state-ledgers`

```yaml
id: state-ledgers
title: Ledger append/finalize, state reconciliation, retention, freshness
subsystems:
  - .ai-state/
  - .ai-work/
  - Tech-debt ledger
  - Scripts
tier: unit
selectors:
  - strategy: pytest-globs
    arg:
      - "scripts/test_check_calibration_coverage.py"
      - "scripts/test_check_state_ledgers.py"
      - "scripts/test_clean_work_safety.py"
      - "scripts/test_finalize_tech_debt_ledger.py"
      - "scripts/test_prune_reports.py"
      - "scripts/test_reconcile_ai_state.py"
      - "scripts/test_reconcile_pipeline_state.py"
      - "tests/test_append_eval_log.py"
      - "tests/test_disposition_vocabulary.py"
      - "tests/test_principles_loader.py"
      - "tests/test_run_store_backend.py"
file_dependencies:
  - "scripts/check_state_ledgers.py"
  - "scripts/state_ledger_schema.py"
  - "scripts/finalize_tech_debt_ledger.py"
  - "scripts/reconcile_ai_state.py"
  - "scripts/reconcile_pipeline_state.py"
  - "scripts/prune_reports.py"
  - "scripts/clean_work_safety.py"
  - "scripts/check_calibration_coverage.py"
  - "scripts/principles_loader.py"
  - "scripts/merge_driver_observations.py"
  - "skills/agent-evals/scripts/append_eval_log.py"
  - "skills/agent-evals/references/run-ledger-schema.md"
  - "skills/software-planning/references/disposition-vocabulary.md"
  - "skills/software-planning/references/tech-debt-ledger.md"
  - "skills/software-planning/references/project-principles.md"
  - "rules/swe/agent-intermediate-documents.md"
parallel_safe: true
shared_fixture_scope: per-test
expected_runtime_envelope:
  p50_seconds: 5.1
  p95_seconds: 6
shared_state: tmp_path
notes: "225 tests in ~5 s -- cheap and broad, a good phase-tier companion."
```

Two members target the `agent-evals` skill's producer and its schema-convention
document rather than the `eval/` package (a separate runner outside this corpus); the
binding is by ledger lifecycle, not by directory.

### `repo-gates`

```yaml
id: repo-gates
title: Pre-commit and CI structural gates over the authored surface
subsystems:
  - Skills
  - Agents (authored definitions)
  - Rules
  - Commands
  - Scripts
tier: unit
selectors:
  - strategy: pytest-globs
    arg:
      - "scripts/test_check_aac_golden_rule.py"
      - "scripts/test_check_agent_shared_blocks.py"
      - "scripts/test_check_architecture_projection.py"
      - "scripts/test_check_frontmatter_parses.py"
      - "scripts/test_check_gate_liveness.py"
      - "scripts/test_check_html_authorship.py"
      - "scripts/test_check_p06_task_brief.py"
      - "scripts/test_check_paths_syntax.py"
      - "scripts/test_check_ruff_pin_drift.py"
      - "scripts/test_check_shipped_artifact_isolation.py"
      - "scripts/test_check_squash_safety.py"
      - "scripts/test_check_template_mirrors.py"
      - "tests/test_aac_fence_validator.py"
      - "tests/test_agent_frontmatter_plugin_compat.py"
      - "tests/test_check_id_citation_discipline.py"
file_dependencies:
  - "scripts/check_aac_golden_rule.py"
  - "scripts/aac_fence_validator.py"
  - "scripts/check_agent_shared_blocks.py"
  - "scripts/check_architecture_projection.py"
  - "scripts/check_frontmatter_parses.py"
  - "scripts/check_gate_liveness.py"
  - "scripts/check_html_authorship.py"
  - "scripts/check_id_citation_discipline.py"
  - "scripts/check_p06_task_brief.py"
  - "scripts/check_paths_syntax.py"
  - "scripts/check_ruff_pin_drift.py"
  - "scripts/check_shipped_artifact_isolation.py"
  - "scripts/check_squash_safety.py"
  - "scripts/check_template_mirrors.py"
  - "rules/**/*.md"
  - "skills/**/*.md"
  - "agents/*.md"
  - "commands/*.md"
  - "claude/aac-templates/**"
  - ".pre-commit-config.yaml"
  - "pyproject.toml"
parallel_safe: true
shared_fixture_scope: per-test
expected_runtime_envelope:
  p50_seconds: 7.0
  p95_seconds: 11
shared_state: filesystem
notes: "The inner-loop group -- 200 tests in ~7 s, carrying none of the four heavy files."
```

`file_dependencies` deliberately include the whole authored markdown surface, not just
the gate scripts: these gates exist to bite on rule / skill / agent / command edits, so
an edit there must fire them. Unit tier — each gate is a pure function over a
`tmp_path` mini-repo, invoked either in-process or through its own CLI entry point.

### `knowledge-projection`

```yaml
id: knowledge-projection
title: Generators projecting the authored surface into shipped or derived form
subsystems:
  - Skills
  - Agents (authored definitions)
  - Rules
  - Commands
  - Scripts
tier: unit
selectors:
  - strategy: pytest-globs
    arg:
      - "scripts/test_artifact_registry.py"
      - "scripts/test_build_doc_manifest.py"
      - "scripts/test_canonical_block_identity.py"
      - "scripts/test_claude_to_agents.py"
      - "scripts/test_measure_token_budget.py"
      - "scripts/test_refresh_claude_blocks.py"
      - "scripts/test_regenerate_rules_manifest.py"
      - "scripts/test_render_claude_md.py"
      - "scripts/test_sync_canonical_blocks.py"
file_dependencies:
  - "scripts/sync_canonical_blocks.py"
  - "scripts/canonical_block_identity.py"
  - "scripts/render_claude_md.py"
  - "scripts/refresh_claude_blocks.py"
  - "scripts/build_doc_manifest.py"
  - "scripts/artifact_registry.py"
  - "scripts/regenerate_rules_manifest.py"
  - "scripts/measure_token_budget.py"
  - "skills/adapt-claude-to-agents/scripts/claude_to_agents.py"
  - "claude/canonical-blocks/*.md"
  - "claude/config/CLAUDE.md"
  - "claude/config/CLAUDE.md.tmpl"
  - "rules/**/*.md"
  - "skills/**/*.md"
  - "agents/*.md"
  - "commands/*.md"
  - "docs/**/*.md"
parallel_safe: true
shared_fixture_scope: per-test
expected_runtime_envelope:
  p50_seconds: 5.2
  p95_seconds: 7
shared_state: filesystem
notes: "Generators only -- projection, not deployment."
```

`scripts/test_claude_to_agents.py` targets `skills/adapt-claude-to-agents/scripts/`, a
CLAUDE.md → AGENTS.md projection. It is bound here rather than to `install-and-export`
because the behavior under test is generation, not deployment — and because
`install-and-export` is the 24-32 s group, which this cheap generator should not pay.

### `install-and-export`

```yaml
id: install-and-export
title: Installer, Codex-export, and dependency-pin machinery
subsystems:
  - Installers
  - Scripts
tier: integration
selectors:
  - strategy: pytest-globs
    arg:
      - "scripts/test_export_codex_agents.py"
      - "scripts/test_export_codex_command_skills.py"
      - "scripts/test_export_codex_pipeline_adapter.py"
      - "scripts/test_export_codex_rules_bridge.py"
      - "scripts/test_export_codex_skills.py"
      - "scripts/test_install_codex.py"
      - "scripts/test_install_dev_link.py"
      - "scripts/test_manage_codex_mcp.py"
      - "scripts/test_upgrade_project_pins.py"
      - "scripts/test_install_git_hooks.py"
file_dependencies:
  - "install.sh"
  - "install_claude.sh"
  - "install_codex.sh"
  - "install_cursor.sh"
  - "lib/install_shared.sh"
  - "scripts/upgrade_project_pins.sh"
  - "scripts/git-finalize-hook.sh"
  - "scripts/install_git_hooks.py"
  - "scripts/assets/praxion-hook-wrapper.sh.tmpl"
  - "codex/config/**"
  - "claude/config/**"
  - ".claude-plugin/plugin.json"
integration_boundaries:
  - onboarding-contract
parallel_safe: true
shared_fixture_scope: per-test
expected_runtime_envelope:
  p50_seconds: 24.2
  p95_seconds: 32
shared_state: filesystem
notes: "The isolation win -- 72 tests but ~24 s, carrying two of the four heavy files."
```

`test_install_codex.py` (18.0 s) and `test_upgrade_project_pins.py` (7.0 s) both land
here, so every other group is free of them. Integration tier: real installer shell
scripts run against synthetic `HOME` trees under `tmp_path`.

This group deliberately does **not** declare `hooks/*.py`. The Codex rules bridge
references canonical hooks *by path*, not by content, so a hook body edit cannot break
these tests — declaring the glob would make every hook edit pay 24-32 s for nothing. A
hook *rename or deletion* can break them; if that becomes common, the planner should
hang an `integration_boundaries` entry from `hooks-lifecycle` here rather than widen
this glob.

### `onboarding-contract`

```yaml
id: onboarding-contract
title: The end state /onboard-project and /new-project must produce in a managed project
subsystems:
  - Installers
  - Commands
tier: contract
selectors:
  - strategy: pytest-globs
    arg:
      - "tests/commands/test_onboard_ci_autofix_install.py"
      - "tests/commands/test_onboard_consult_ledgers_install.py"
      - "tests/commands/test_onboard_labels_install.py"
      - "tests/commands/test_onboard_permissions_allow_install.py"
      - "tests/commands/test_onboard_praxion_feedback_install.py"
      - "tests/commands/test_upgrade_labels_baseline.py"
      - "tests/commands/test_upgrade_project_command.py"
      - "tests/consumer_layout/"
      - "scripts/test_onboard_project_placement.py"
      - "tests/commands/test_onboard_placement_phase_matrix.py"
      - "tests/test_onboard_project_detection.py"
file_dependencies:
  - "commands/onboard-project.md"
  - "commands/new-project.md"
  - "commands/upgrade-project.md"
  - "new_project.sh"
  - "claude/canonical-blocks/*.md"
  - "claude/project-baseline/**"
  - "scripts/refresh_labels_baseline.py"
  - ".github/labels.yml"
  - ".github/autofix-policy.yml"
  - ".github/workflows/ci-autofix.yml"
  - ".github/workflows/cross-model-review.yml"
  - ".github/workflows/labels-reconcile.yml"
  - "scripts/onboard-project"
  - "scripts/praxion-sidecar"
  - "skills/onboard-project/references/*.md"
parallel_safe: true
shared_fixture_scope: per-test
expected_runtime_envelope:
  p50_seconds: 2.5
  p95_seconds: 10
shared_state: filesystem
notes: "Tier is contract, not integration -- a deliberate call; see below.
  scripts/test_onboard_project_placement.py drives scripts/onboard-project and
  the real scripts/praxion-sidecar (Praxion's own already-tested collaborator,
  not an external boundary) via real subprocesses and real git worktrees under
  tmp_path -- the p95 bump over the pre-existing 4s reflects that; only
  `claude` is stubbed. test_onboard_placement_phase_matrix.py and
  test_onboard_project_detection.py extend this group with the placement-axis
  phase-matrix regression suite (prose contract + a real detect_state()
  subprocess check)."
```

`/onboard-project` is a Markdown slash command that pytest cannot invoke, so these
tests derive their expectations from the command's own text and assert the
producer↔consumer agreement it declares; the consumer-layout harness additionally
executes the command's real shell predicates against scratch trees. That is a boundary
agreement between Praxion and a managed project, not a wired-up multi-component run:
134 tests in ~2.5 s, with no installer subprocess anywhere in the group.

### `agent-orchestration`

```yaml
id: agent-orchestration
title: Rework routing/spawn/dispatch, pipeline cleanup, checkpoints, tier selection
subsystems:
  - Agent runtime / Pipeline
  - Agents (authored definitions)
  - Commands
  - .ai-work/
tier: integration
selectors:
  - strategy: pytest-globs
    arg:
      - "scripts/test_parse_pre_refactor_yaml.py"
      - "tests/agents/"
      - "tests/commands/test_resume_rework.py"
      - "tests/orchestration/"
      - "tests/test_checkpoint_digest.py"
      - "tests/test_dispatch_reworks_bg.py"
      - "tests/test_dispatch_reworks_manifest.py"
      - "tests/test_hackathon_mode.py"
      - "tests/test_skill_genesis_agent.py"
      - "tests/test_skill_genesis_review.py"
file_dependencies:
  - "agents/*.md"
  - "commands/resume-rework.md"
  - "commands/skill-genesis.md"
  - "commands/skill-genesis-review.md"
  - "scripts/dispatch-reworks"
  - "scripts/rework_manifest.py"
  - "scripts/parse_pre_refactor_yaml.py"
  - "scripts/sync_canonical_blocks.py"
  - "rules/swe/swe-agent-coordination-protocol.md"
  - "rules/swe/agent-intermediate-documents.md"
  - "skills/software-planning/references/*.md"
  - "claude/canonical-blocks/*.md"
  - "hooks/*.py"
parallel_safe: false
shared_fixture_scope: per-test
expected_runtime_envelope:
  p50_seconds: 6.5
  p95_seconds: 8
shared_state: filesystem
notes: "parallel_safe is false -- measured, not precautionary; see below."
```

`tests/test_dispatch_reworks_bg.py` and `tests/test_dispatch_reworks_manifest.py`
create and `rmdir` real directories under the main checkout at
`<repo>/.claude/worktrees/<name>` — a fixed shared path, not `tmp_path` — and dispatch
marker ids derive from the stub binary's PID. Running two concurrent invocations of
this group reproducibly fails 5 tests with wrong dispatch and marker counts, because
one process removes the worktree directory the other is still using. Rooting those
directories in `tmp_path` would let this flip to `true`.

`hooks/*.py` is declared because `tests/test_hackathon_mode.py` reads the hooks
directory and shells out to `sync_canonical_blocks.py` from the project root.

### `ci-workflows`

```yaml
id: ci-workflows
title: GitHub Actions invariants, self-healing metrics, release staleness
subsystems:
  - Versioning
  - Scripts
tier: unit
selectors:
  - strategy: pytest-globs
    arg:
      - "scripts/test_check_release_staleness.py"
      - "scripts/test_self_healing_metrics.py"
      - "tests/test_architecture_gate_canary.py"
      - "tests/test_ci_autofix_dogfooding_parity.py"
      - "tests/test_ci_autofix_hub_contract.py"
      - "tests/test_ci_autofix_hub_finalize.py"
      - "tests/test_ci_autofix_hub_js_runner.py"
      - "tests/test_ci_autofix_hub_pm_install.py"
      - "tests/test_ci_autofix_hub_surfaces.py"
      - "tests/test_ci_autofix_policy_template_schema.py"
      - "tests/test_cross_model_review_dogfooding_parity.py"
      - "tests/test_cross_model_review_hub_invariants.py"
      - "tests/test_cross_model_review_verdict_parser.py"
      - "tests/test_finalize_adrs_workflow_invariants.py"
      - "tests/test_issue_autofix_workflow_invariants.py"
      - "tests/test_issue_intake_assessment_invariants.py"
      - "tests/test_labels_manifest.py"
      - "tests/test_labels_reconcile_workflow.py"
file_dependencies:
  - ".github/workflows/*.yml"
  - ".github/labels.yml"
  - ".github/autofix-policy.yml"
  - "scripts/self_healing_metrics.py"
  - "scripts/check_release_staleness.py"
  - "scripts/refresh_labels_baseline.py"
  - "claude/canonical-blocks/*.md"
  - "commands/release.md"
  - "skills/versioning/**"
  - "pyproject.toml"
parallel_safe: true
shared_fixture_scope: per-test
expected_runtime_envelope:
  p50_seconds: 11.1
  p95_seconds: 18
shared_state: filesystem
notes: "335 tests in ~11 s -- cheap because the work is YAML parsing, not execution."
```

Unit tier despite the subject matter: the assertions are in-process structural checks
over shipped workflow files. The one exception is
`tests/test_architecture_gate_canary.py`, which parses the merge-blocking shell out of
`architecture.yml` and runs it for real rather than transcribing a copy.

### `project-metrics`

```yaml
id: project-metrics
title: Metrics collectors, readiness scoring, trends, reporting
subsystems:
  - Scripts
tier: integration
selectors:
  - strategy: pytest-globs
    arg:
      - "scripts/project_metrics/tests/"
      - "scripts/test_check_metrics_freshness.py"
      - "scripts/test_check_readiness_feedback.py"
file_dependencies:
  - "scripts/project_metrics/**/*.py"
  - "scripts/check_metrics_freshness.py"
  - "scripts/check_readiness_feedback.py"
parallel_safe: false
shared_fixture_scope: per-suite
expected_runtime_envelope:
  p50_seconds: 13.7
  p95_seconds: 19
shared_state: filesystem
notes: "The largest group at 691 tests; parallel_safe is false -- see below."
```

Carries `test_integration.py` (8.3 s). `parallel_safe: false` and
`shared_fixture_scope: per-suite` are the same fact:
`scripts/project_metrics/tests/conftest.py` declares a session-scoped autouse fixture
that rebuilds five git fixture repositories at fixed in-repo paths with `rm -rf` +
`git init`, and it has **no** filelock guard — only a short-circuit that skips the
rebuild when all five already exist.

That short-circuit hides the race on a warm tree, which is why the first concurrency
probe passed. Deleting the fixture repositories and re-probing fails hard with
`git -C .../minimal_repo` `CalledProcessError` from concurrent `rm -rf` + `git init`.
Adding the filelock recipe from the Python leaf would let this flip to `true` — the
leaf currently cites this very conftest as the example of that pattern, which it no
longer implements.

### `praxion-feedback`

```yaml
id: praxion-feedback
title: Feedback candidate store, fingerprinting, triage, issue reporting
subsystems:
  - Scripts
tier: unit
selectors:
  - strategy: pytest-globs
    arg:
      - "scripts/praxion_feedback/tests/"
      - "scripts/test_report_praxion_issue.py"
      - "scripts/test_report_praxion_issue_command.py"
file_dependencies:
  - "scripts/praxion_feedback/**/*.py"
  - "scripts/report_praxion_issue.py"
  - "commands/report-praxion-issue.md"
  - "hooks/surface_praxion_feedback.py"
  - "codex/config/export-codex-command-skills.py"
parallel_safe: true
shared_fixture_scope: per-test
expected_runtime_envelope:
  p50_seconds: 1.6
  p95_seconds: 3
shared_state: tmp_path
notes: "The cheapest group: 106 tests in ~1.6 s."
```

The Codex command-skills exporter is a declared dependency because
`scripts/test_report_praxion_issue_command.py` asserts the command survives that
export path.

### `scripts-core`

```yaml
id: scripts-core
title: Shared scripts/ plumbing — repo-root resolution and the git runner
subsystems:
  - Scripts
tier: integration
selectors:
  - strategy: pytest-globs
    arg:
      - "scripts/test__git_runner.py"
      - "scripts/test_repo_root.py"
      - "scripts/test_state_repo.py"
      - "scripts/test_sidecar_manifest.py"
      - "scripts/test_sidecar_mount.py"
      - "scripts/test_sidecar_link.py"
      - "scripts/test_sidecar_commit.py"
      - "scripts/test_sidecar_checks.py"
      - "scripts/test_praxion_sidecar.py"
      - "scripts/test_sidecar_identity.py"
file_dependencies:
  - "scripts/_git_runner.py"
  - "scripts/_repo_root.py"
  - "scripts/_script_cli.py"
  - "scripts/_state_repo.py"
  - "scripts/_sidecar_manifest.py"
  - "scripts/_sidecar_mount.py"
  - "scripts/_sidecar_link.py"
  - "scripts/_sidecar_commit.py"
  - "scripts/_sidecar_checks.py"
  - "scripts/_sidecar_git.py"
  - "scripts/_sidecar_cli.py"
  - "scripts/_sidecar_identity.py"
  - "scripts/_sidecar_init.py"
  - "scripts/_sidecar_inputs.py"
  - "scripts/_sidecar_render.py"
  - "scripts/install_git_hooks.py"
  - "scripts/praxion-sidecar"
integration_boundaries:
  - decision-records
  - state-ledgers
parallel_safe: true
shared_fixture_scope: per-test
expected_runtime_envelope:
  p50_seconds: 2.6
  p95_seconds: 4
shared_state: tmp_path
notes: "Small on purpose -- a node for the planner to hang wide boundaries off. sidecar-placement (P1) added _state_repo.py, _sidecar_manifest.py, _sidecar_checks.py, _sidecar_link.py, _sidecar_commit.py, praxion-sidecar and their test files as selectors/file_dependencies for the test-engineer to register in Steps 1b-7b; the integration_boundaries above widen because _state_repo.py is now a dependency of finalize_adrs.py (decision-records) and reconcile_ai_state.py/reconcile_aac_surfaces.py (state-ledgers)."
```

Nearly every other `scripts/` group imports this plumbing, so a change here
legitimately deserves a large radius — and that radius belongs in
`integration_boundaries`, not in a widened glob. Integration tier: the git-runner tests
drive real `git` (including a deliberately hanging stub) against repositories built in
`tmp_path`.

### `architecture-fitness`

```yaml
id: architecture-fitness
title: Import-boundary and structural-invariant fitness functions
subsystems:
  - Skills
  - Agents (authored definitions)
  - Rules
tier: contract
selectors:
  - strategy: pytest-globs
    arg:
      - "fitness/"
file_dependencies:
  - "fitness/**/*.py"
  - "fitness/import-linter.cfg"
  - "scripts/*.py"
  - "agents/*.md"
  - "rules/**/*.md"
  - "skills/**/*.md"
  - "eval/src/**/*.py"
  - ".claude-plugin/plugin.json"
parallel_safe: true
shared_fixture_scope: per-suite
expected_runtime_envelope:
  p50_seconds: 6.0
  p95_seconds: 7
shared_state: filesystem
notes: "Outside testpaths -- contributes 0 of the 152 canonical files."
```

The selector names `fitness/` explicitly rather than relying on the default corpus.
Runs today as a dedicated job in `.github/workflows/architecture.yml`.
`shared_fixture_scope` is `per-suite` because `conftest.py` declares session-scoped
fixtures, but they return path constants with no mutable state — which is why
`parallel_safe` stays `true`. Contract tier: import-linter contracts and the
meta-citation rule assert boundary agreements between modules, not the behavior of any
one of them.
