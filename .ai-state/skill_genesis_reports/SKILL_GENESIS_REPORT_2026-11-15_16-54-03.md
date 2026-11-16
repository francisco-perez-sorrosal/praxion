---
schema_version: 1
report_id: skill-genesis-2026-11-15_16-54-03
generated_at: 2026-11-15T16:54:03
task_slug: skill-genesis-2026-11-15
agent_version: skill-genesis@89e70d55
invocation_args: { since: null, scope: null, sources: /Users/fperez/dev/praxion/.ai-work/_harvest, batch: "5 of 11", dry_run: false }
review_status: pending
disposition_count: { pending: 4, approved: 0, rejected: 0, refined: 0, deferred: 0 }
---

# Skill Genesis Report — 2026-11-15 16:54:03

## Summary

3 queue sources analyzed (`acceptance-independence`, `quant-acceptance-criteria`, `test-refresh-core`), 26 learning items extracted, 4 proposals generated, 22 deduplicated or skipped. Each lesson was searched against `skills/`, `rules/`, `agents/`, `docs/`, root `CLAUDE.md` and `scripts/CLAUDE.md`, and against the five earlier reports of this run (`SKILL_GENESIS_REPORT_2026-11-15_16-39-41/42-24/45-03/51-16.md`) plus the 2026-11-05 report. Review status: pending.

## Learning Sources Consumed

| Source | Path | Items Extracted | Status |
|---|---|---|---|
| acceptance-independence LEARNINGS.md (incl. 8 merged implementer fragments) | `.ai-work/_harvest/acceptance-independence/LEARNINGS.md` | 9 | Read |
| acceptance-independence VERIFICATION_REPORT.md (incl. re-verification) | `.ai-work/_harvest/acceptance-independence/VERIFICATION_REPORT.md` | 5 | Read (lines 100-409; the Summary/Scope/Acceptance sections above line 100 were not read) |
| quant-acceptance-criteria LEARNINGS.md | `.ai-work/_harvest/quant-acceptance-criteria/LEARNINGS.md` | 5 | Read |
| quant-acceptance-criteria VERIFICATION_REPORT.md | `.ai-work/_harvest/quant-acceptance-criteria/VERIFICATION_REPORT.md` | 3 | Read |
| test-refresh-core LEARNINGS.md | `.ai-work/_harvest/test-refresh-core/LEARNINGS.md` | 7 | Read |
| test-refresh-core VERIFICATION_REPORT.md | `.ai-work/_harvest/test-refresh-core/VERIFICATION_REPORT.md` | 6 | Read |
| CONSULT_*.md fragments | the three source directories | 0 | Not found |
| Latest SENTINEL_REPORT / IDEA_LEDGER / ADR index / calibration-log Retrospective cells | `.ai-state/` | 0 | Not consulted: queue-mode batch; the lessons were deduplicated against shipped artifacts and earlier reports instead |

(Items are counted by first source; several lessons recur across sources and appear once in the triage.)

## Triage Results

| # | Item | Source | Decision | Rationale |
|---|---|---|---|---|
| 1 | A link to `#slug` resolves only from a heading's slug, never from an `<a id>`; `&` and `/` in a heading change the slug (`Acceptance-Design Stage & the Spec-Question Loop` slugged to `...stage--the-spec-question-loop`; `BDD/TDD` to `bddtdd`) | acceptance-independence LEARNINGS implementer-3, implementer-7; plan "anchor ordering" | Skill (update) | Proposal 1. `skills/doc-management/references/advanced-markdown-patterns.md:123-131` gives the slug table but not these cases; `validate_references.py` docstring lists "Anchor same-file (#slug)" only; grep `<a id` finds two reference files that use it as if it were a target |
| 2 | A wall-clock figure used as a baseline or limit must be taken with nothing else running: the 360 s research baseline read 125.6 s serial (`-n 0`) once measured; a 20% margin (~17 s) sat inside shared-machine noise; the test-engineer measured at load average ~13 on 12 cores | test-refresh-core LEARNINGS (Step 13, orchestrator descope of REQ-21); quant-acceptance-criteria LEARNINGS (planner assumptions, gotcha on the 85 s suite) | Skill (update) | Proposal 2. `footprint-criteria.md` "Reading a result" covers reading kind, staleness and baseline head, not load; grep `elapsed`, `load average`, `loaded host`, `uptime` in `skills/spec-driven-development`, `document-templates.md` and `testing-strategy/references` found no match |
| 3 | `validate_references.py` lives at `skills/skill-crafting/scripts/`; plans and designs cite `scripts/validate_references.py --all` and it does not exist | test-refresh-core LEARNINGS (planner, `SYSTEMS_PLAN.md § Risk Assessment`); acceptance-independence LEARNINGS implementer-5, implementer-6 | CLAUDE.md | Proposal 3. grep `validate_references` in `agents/`, `rules/`, root `CLAUDE.md`, `scripts/CLAUDE.md`, `README_DEV.md`, `docs/*.md` finds nothing; three pipelines each lost a step to the wrong path |
| 4 | A changed-set read from `git diff --name-only` has blind spots a gate must canary: a rename lists only the new path (old test neither selected nor widened, and the audit's `suggested_edge` carries a deleted file); `REF...HEAD` omits uncommitted tracked edits (false all-clear on the shipped "selected run"); a plain diff omits untracked files; a deleted test self-selects and `pytest <missing>` aborts `sh -e` | test-refresh-core VERIFICATION F1, F2, W1; quant-acceptance-criteria LEARNINGS (Step 6 `ls-files --others`, `--no-renames` decision) | Skill (update) | Proposal 4. The fixes are in code (`resolve_test_scope.py:569`, `check_footprint_criteria.py:609-621`) and `test-selection.md:92` documents the resolver contract, but no skill or rule states it for the next gate; grep `no-renames`, `exclude-standard`, `untracked` in `skills/testing-strategy`, `gate-liveness.md`, `testing-conventions.md` found only `test-selection.md:92` and an unrelated fixture line |
| 5 | Harness worktree isolation refuses Bash by command text (`git`/`eval` substrings, heredocs, compound commands, shell variables as operands) | all three LEARNINGS, about ten entries | Skip | Present: `docs/claude-code-limitations.md:11` lists the refused shapes and the scratch-script workaround |
| 6 | Commit only when no agent is running (pre-commit stash race); never edit a file a sibling lane owns mid-run | quant-acceptance-criteria LEARNINGS (orchestrator Gotchas) | Skip | Present: `agent-pipeline-details.md:52` ("One committer at a time"), `rules/swe/vcs/git-conventions.md:23-24` |
| 7 | A new FAIL-level presence check needs a transition for pipelines that started before it; a marker whose absence exempts is not a transition | acceptance-independence VERIFICATION WARN-10, RV-WARN-10 | Skip | Present after rework: `agents/verifier.md:121` ("the exemption is the artifact, never an inferred marker"), `coordination-details.md:238` |
| 8 | Extractor matched only the exact `## Key Signals` heading and rendered `_None_` with exit 0; the step's smoke "0 findings" was vacuous; table parsers dropped malformed rows without a finding | acceptance-independence VERIFICATION FAIL-1; quant-acceptance-criteria VERIFICATION W-01 | Skip | Present: `rules/swe/gate-liveness.md:36` (prefer a totalising check); the smoke-proof half is pending in 16-51-16 Proposal 4 |
| 9 | Path-scoping globs (`*_spec.*`) reused as a classifier put production `extract_spec.py` in the test class and silenced the commit-order bad-case | acceptance-independence VERIFICATION FAIL-2 | Skip | One occurrence, fixed in the stage text; `gate-liveness.md:17` (scope fidelity) names the class. A seedling: a loading glob over-includes harmlessly, a classifier does not |
| 10 | Shipped prompt named `python3 scripts/...` paths that exist only in Praxion; a script without the exec bit is not linked onto `PATH` | test-refresh-core VERIFICATION F6 | Skip | Fixed and carried: `agents/implementer.md:69` (PATH form plus self-host), `python-testing.md:284`, `scripts/CLAUDE.md:27` (exec bit is the installer's filter); `audit_tests.py` is mode 755 |
| 11 | `pnpm test -- --reporter=junit` forwards `--`; vitest ignores flags after it and writes no junit | test-refresh-core VERIFICATION F3 | Skip | Present: `phases-optional.md:640` (the value must invoke the runner directly, `pnpm exec vitest run`), `testing-strategy/SKILL.md:96`; Praxion's own workflow was a code fix |
| 12 | An edit to an always-loaded rule changes its `chars` in `rules/_manifest.yaml`; the step's `Files:` omitted the manifest | acceptance-independence LEARNINGS implementer-8 | Skip | Partly present: `rule-crafting/SKILL.md:192,266` (regenerate), `stop-recoveries.md:24` (the drift hook refuses a driver commit). A seedling for the next plan that edits a rule |
| 13 | A "Done when" byte threshold (>= 9 KB) was marked complete with no measurement | test-refresh-core VERIFICATION F5 | Skip | Present for footprints: `footprint-criteria.md` (measurement step and verifier grade); the re-derive half is pending in 16-51-16 Proposal 3 |
| 14 | Mutation sensor runs a flat sandbox copy: a subprocess test of the mutated module fails `run-failed`; keep it out of `--tests`, call `main([...])` in-process | quant-acceptance-criteria LEARNINGS (implementer, Steps 5-6) | Skip | Pending: 16-39-41 Proposal 4 and 16-45-03 Proposal 2; `scripts/CLAUDE.md:76,90` describe the flat layout |
| 15 | Bare `python3 -m pytest` lacks xdist; `-p no:xdist` errors under the parallel `addopts`, use `-n 0` | acceptance-independence LEARNINGS (planner), test-refresh-core LEARNINGS | Skip | Present: `agents/implementer.md:69` ("Debug with `-n 0`, never `-p no:xdist`"); `README_DEV.md` per 16-51-16 item 12 |
| 16 | A step's `Files:` omitted a consumer (unwired adapter module; `_topology_yaml.py` deletion deferred a step) | test-refresh-core LEARNINGS (implementer Steps 4, 5) | Skip | Pending: 16-39-41 Proposal 1 and 16-42-24 Proposal 1 |
| 17 | Fragment names per step (`traceability_step<N>.yml`) so same-role spawns in one wave cannot collide | test-refresh-core LEARNINGS (planner) | Skip | One occurrence; acceptance-independence later used `-implementer-N` suffixes, the convention in `agent-intermediate-documents.md` |
| 18 | GL07 scans the filesystem and goes red on gitignored `tmp/disarm/` copies | test-refresh-core VERIFICATION W2 | Skip | Pending: 16-51-16 Proposal 1 |
| 19 | The acceptance-design commit froze spec text into a fixture that tripped the retired-namespace invariant, leaving the bare suite red | quant-acceptance-criteria LEARNINGS (planner Gotchas) | Skip | One occurrence; `coordination-details.md:173,245` already collect the suite after the AD commit; fixed by an allowlist entry |
| 20 | A bare YAML key loads as `None` (`tests + impl + edges.get("acceptance", [])` raises); coerce with `or []` at the parse boundary | acceptance-independence VERIFICATION WARN-8 | Skip | Ordinary parse-boundary discipline, fixed in code with a parametrized canary |
| 21 | Tool availability is not a `PATH` question for npm (`node_modules/.bin`); Maven/Gradle/Turbo/Pants mappings are heuristics | test-refresh-core LEARNINGS (implementer Step 5) | Skip | Code and module docstring carry it |
| 22 | Python 3.9 contract scan: `frozenset(a) \| frozenset(b)`, `zip(strict=)`, `re.I \| re.S`; ruff UP rewrites need `from __future__ import annotations` | quant-acceptance-criteria and acceptance-independence LEARNINGS (implementers) | Skip | Module-local, pinned by `test__footprint_grammar.py`; no recurrence outside these modules |
| 23 | `REQ-NN` literals trip the id-citation gate even in messages and fixtures; build ids with a helper or add the ignore marker | acceptance-independence LEARNINGS implementer-1, implementer-2 | Skip | The gate ships an ignore marker (used at `tests/test_spec_drift.py:516` per the re-verification); one pipeline |
| 24 | Spec-question routing and `tests:` writer named differently across five sites; mandatory pairing survived in a rule row | acceptance-independence VERIFICATION WARN-2, 3, 5 | Skip | Cross-site drift of this change, fixed in rework; the convention is `gate-liveness.md:43` |
| 25 | Planner prompt still said 8/16 spawn budgets while the protocol says 16/32 | quant-acceptance-criteria LEARNINGS (planner) | Skip | Restated figure fixed in `be01269f`; `gate-liveness.md:43` |
| 26 | Registry scope wider than the measured quantity (`agents/*.md` vs listing descriptions); FP01 has no named consumer at plan stage; REQ-01/04 inert without a registry | quant-acceptance-criteria VERIFICATION W-05, W-10, W-16 | Skip | Design and prompt findings of one change, routed to the architect; `gate-liveness.md` carries "a named consumer for every gate output" |

## Discipline-Gap Signals

None recorded.

## Proposals

### Proposal 1: Anchor links resolve from heading slugs only, never from `<a id>`

- **Disposition**: pending
- **Type**: skill (update)
- **Maturity**: sapling
- **Scope**: narrow
- **Priority**: P1 (next-cycle)
- **Source(s)**: acceptance-independence `LEARNINGS.md` implementer-3 ("`validate_references.py` resolves anchors from heading slugs only, never from `<a id>`"; heading renamed to `## Acceptance-Design Stage`), implementer-7 ("Link as `#bddtdd-execution`... `#bdd-tdd-execution` FAILs"), planner "Anchor ordering is enforced by wave".
- **Description**: In `advanced-markdown-patterns.md` § Anchor slug rules, add the two cases that bit: `&` and `/` are dropped without collapsing the neighbouring hyphens (`A & B` slugs to `a--b`, `BDD/TDD` to `bddtdd`), and a link target is a heading that slugs to the anchor, because the validator ignores `<a id="...">` (GitHub honours it, the checker does not). Add one sentence: before a step links a new anchor, run `validate_references.py --file <path>` on the file that carries it.
- **Rationale**: Three implementers in one pipeline each hit the dangling anchor, one of them by planning against `<a id>`. The repository itself uses `<a id>` in two reference files, which teaches the wrong model. The fix costs two table rows and a sentence.
- **Estimated scope**: two table rows and one paragraph in an existing reference.
- **Overlap check**: `skills/doc-management/references/advanced-markdown-patterns.md:123-131` (slug rules, lowercase and strip punctuation, no `&`, `/` or `<a id>` case); `validate_references.py` docstring (anchor classes only). No pending proposal touches it.
- **Recommended delegation**: context-engineer (review scope), then implementer (content)
- **Suggested artifact path**: `skills/doc-management/references/advanced-markdown-patterns.md`

### Proposal 2: A wall-clock reading is a baseline only if taken on a quiet machine

- **Disposition**: pending
- **Type**: skill (update)
- **Maturity**: sapling
- **Scope**: narrow
- **Priority**: P2 (someday)
- **Source(s)**: test-refresh-core `LEARNINGS.md` (test-engineer Step 13: research baseline ~360 s vs 125.56 s measured serial, `uptime` load ~13 on 12 cores; orchestrator 2026-09-28 descope of REQ-21 on that evidence); quant-acceptance-criteria `LEARNINGS.md` (planner: "no agent or suite runs concurrently (elapsed seconds is a footprint)", the 85 s xdist suite with a 17 s margin inside shared-machine noise).
- **Description**: In `footprint-criteria.md` § Reading a result, add two bullets for an elapsed-time footprint: take the baseline and the final row with no agent and no suite running and note the load (`uptime`) in the reading; a figure taken on a loaded host is an upper bound, so re-take it before a target is sized against it, and state in the criterion when its margin is narrower than run-to-run noise.
- **Rationale**: A requirement was descoped because a baseline taken under load had overstated the cost threefold, and a second pipeline wrote the same hazard into its plan as an assumption. The guidance belongs where the criterion is authored, which today says nothing about the machine.
- **Estimated scope**: two bullets in an existing reference.
- **Overlap check**: `footprint-criteria.md` "Reading a result" (reading kind, staleness, baseline head); 2026-11-05 Proposal 4 (grammar check after the baseline rows, plugin root beside a token reading), which is about other defects in the same measurement step. `agent-era-performance.md` § Pipeline Wall-Clock discusses pipeline latency, not instrument load.
- **Recommended delegation**: context-engineer (review scope), then implementer (content)
- **Suggested artifact path**: `skills/spec-driven-development/references/footprint-criteria.md`

### Proposal 3: Name where `validate_references.py` lives

- **Disposition**: pending
- **Type**: claude.md
- **Maturity**: sapling
- **Scope**: narrow
- **Priority**: P1 (next-cycle)
- **Source(s)**: test-refresh-core `LEARNINGS.md` planner ("`validate_references.py --all` does not exist in this repository"; `SYSTEMS_PLAN.md § Risk Assessment` cited it as the dangling-reference mitigation, steps 8 and 15 substituted another script); acceptance-independence `LEARNINGS.md` implementer-5 and implementer-6 ("lives at `skills/skill-crafting/scripts/`, not `scripts/`").
- **Description**: One line in root `CLAUDE.md` under "How to verify your work": `python3 skills/skill-crafting/scripts/validate_references.py --all` checks intra-repo Markdown links and anchors. Alternative if the always-loaded budget is tight: write the full repo path in `skills/skill-crafting/SKILL.md` § Validate and Package, where the text says `scripts/validate_references.py` relative to the skill.
- **Rationale**: The architect wrote a mitigation around a path that does not exist, and two implementers re-discovered the real one. The script is named in no file a planning agent loads, so the same miss will recur. One line closes it; its token cost must be measured with `scripts/measure_token_budget.py` before adding.
- **Estimated scope**: CLAUDE.md edit (one line), or a one-line path fix in `SKILL.md`
- **Overlap check**: none for the path; `skills/skill-crafting/README.md:46` names the script without a repo-relative path.
- **Recommended delegation**: user (claude.md); context-engineer to review placement and token impact
- **Suggested artifact path**: `CLAUDE.md` (alternative `skills/skill-crafting/SKILL.md`)

### Proposal 4: A gate fed by `git diff --name-only` needs changed-set canaries

- **Disposition**: pending
- **Type**: skill (update)
- **Maturity**: sapling
- **Scope**: narrow
- **Priority**: P1 (next-cycle)
- **Source(s)**: test-refresh-core `VERIFICATION_REPORT.md` F1 (rename hides the old path; the audit then proposed an edge naming a deleted file), F2 (`--changed-from REF` excluded uncommitted tracked edits, a false all-clear in the shipped `## Testing` block), W1 (a deleted test self-selects, `pytest <missing>` exits 4 and aborts `sh -e`); quant-acceptance-criteria `LEARNINGS.md` (implementer: `git diff --name-only <ref>` omits untracked files, unioned with `git ls-files --others --exclude-standard` and pinned by a temp-repo test; `--no-renames` "so a file renamed out of a footprint's paths still moves it").
- **Description**: In `gate-canaries.md`, add a short section "A gate fed by a git-derived changed set": the input must be built with `--no-renames`, must include untracked files and (for a branch comparison) uncommitted tracked edits, and must drop deleted paths from any emitted target; the gate ships one canary per blind spot (rename, untracked, uncommitted edit, deleted file) built from a temporary git repository. Name the two shipped instances as worked cases: `resolve_test_scope.py` and `check_footprint_criteria.py`.
- **Rationale**: Two pipelines found three of these four blind spots independently in two different gates; one cost a FAIL in verification and the other was caught by a careful implementer. Each is a silent under-selection, the failure the gate-liveness rule's scope-fidelity clause exists for, but the clause does not name git's changed set, so the next gate (a selector, a footprint check, a drift check) will start from the bare `git diff`.
- **Estimated scope**: one section (about 10 lines) in an existing reference
- **Overlap check**: `test-selection.md:92` documents rename and deletion handling for the resolver only; `gate-liveness.md:17` (scope fidelity, general); pending 16-51-16 Proposals 1 and 4 also edit `gate-canaries.md` at other sections (disarm scratch copies, real-data intermediates), so apply the three together to avoid conflicting edits.
- **Recommended delegation**: context-engineer (review scope), then implementer (content)
- **Suggested artifact path**: `skills/testing-strategy/references/gate-canaries.md`

## Recommended Delegations

| Proposal | Delegation Path | Notes |
|---|---|---|
| 1 | context-engineer then implementer | Load `skill-crafting`; run `validate_references.py --file` on the edited reference |
| 2 | context-engineer then implementer | Keep to two bullets; the reference is read at planning time |
| 3 | user (claude.md), context-engineer review | Measure the token delta with `scripts/measure_token_budget.py`; fall back to the `SKILL.md` path fix |
| 4 | context-engineer then implementer | Apply with 16-51-16 Proposals 1 and 4, which edit the same file |

## Disposition Log

<!-- Populated by /skill-genesis-review. Empty on report creation. -->

| Timestamp | Proposal | Disposition | Notes |
|---|---|---|---|
| _(empty — pending review)_ | | | |

## Recommended Next Steps

- Run `/skill-genesis-review` to disposition the 4 pending proposals.
- After approval, invoke `context-engineer` for skills/rules; the agent will pick up the recommended delegations table.
- Seedlings to watch for a second occurrence: path-scoping glob reused as a classifier (item 9), a rule edit that moves `rules/_manifest.yaml` `chars` without the manifest in the step's `Files:` (item 12).
