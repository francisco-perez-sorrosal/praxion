---
schema_version: 1
report_id: skill-genesis-2026-10-10_00-49-38
generated_at: 2026-10-10T07:49:38Z
task_slug: likec4-diagram-craft
agent_version: skill-genesis@53244ce9
invocation_args: { since: null, scope: null, sources: ".claude/worktrees/likec4-diagram-craft/.ai-work/likec4-diagram-craft", batch: null, dry_run: false }
review_status: pending
disposition_count: { pending: 7, approved: 0, rejected: 0, refined: 0, deferred: 0 }
---

# Skill Genesis Report — 2026-10-10 00-49-38

## Summary

Post-pipeline harvest of the merged `likec4-diagram-craft` pipeline (merged at 53244ce9). 4 sources read; 24 discrete learning items extracted; 7 proposals (all pending; 5 skill/rule/doc-reference updates, 2 new-section proposals, 0 new skills, 0 CLAUDE.md); 12 items marked no-op because `skills/likec4-diagramming/` or an ADR already carries them; 5 deduplicated against harness memory or sibling pending reports. Review status: pending.

## Learning Sources Consumed

| Source | Path | Items Extracted | Status |
|---|---|---|---|
| LEARNINGS.md | `.claude/worktrees/likec4-diagram-craft/.ai-work/likec4-diagram-craft/LEARNINGS.md` | 20 | Read (260 lines; ~120 pipeline-specific implementer notes skimmed, not itemised) |
| VERIFICATION_REPORT.md | same dir, § Recommendations, § Convention Compliance | 4 | Read (those sections) |
| WIP.md | same dir, Orchestrator record sections | 2 | Read (sections only) |
| Prior reports | `.ai-state/skill_genesis_reports/` (2026-09-04, 09-23 x9, 09-27) | — | Grepped for overlap |
| Latest IDEA_LEDGER | `.ai-state/idea_ledgers/IDEA_LEDGER.md` | 0 | Not consulted (no ideation overlap) |
| ADRs | dec-438..444 | 0 | Cited via LEARNINGS (already ADR-recorded) |
| Calibration log / sentinel | — | 0 | Not consulted |

## Triage Results

| # | Item | Source | Decision | Rationale |
|---|---|---|---|---|
| 1 | `GIT_DIR` exported to hook processes redirects `git add` run from a subdirectory | WIP orchestrator record | Skill (update) | Pending sibling P (2026-09-04) covers `git -C <other-repo>`; this is the same-repo subdirectory variant, not in hook-crafting. Memory already holds the gotcha |
| 2 | Pre-staged deletion rides the next pathspec commit | LEARNINGS orchestrator | Skip (memory) | `feedback_prestaged_deletion_rides_next_pathspec_commit` exists; one-line addition to git-conventions optional, folded into P2 |
| 3 | Mutation survivor on subprocess cwd/env dismissed as unobservable | Verifier | Skill (update) | Generalises (3); links to #1 |
| 4 | Mutation sensor blind to scripts run as `__main__`; `__file__`-relative lookups break under `scripts/mutants/` | Step 24 | Skill (update) | Extends pending 09-23_23-05-46 P1 (mutation recipe for flat `scripts/`) |
| 5 | Retiring an identifier needs a template/example sweep in the same step | Verifier | Rule/skill ref (update) | Recurs with rename-grep deviations (Step 6, Step 9) |
| 6 | "No element name" style guards that search all text are vacuous | Verifier C-1 | Skill (update) | Generalises: guard must read the narrowest structure that can carry the claim |
| 7 | Text-decidable diagram checks are necessary, not sufficient (keep a raster look) | Verifier, W-03 | No-op / partly | `style-canon.md` and `review-checks.md` carry the checks; the raster-look done-criterion is not stated in the skill: folded into P7 |
| 8 | D2 emission recipes: legend sample, label background fill, whole-pixel strokes, quoted `icon:` data URIs, `el_` key prefix, grid-columns, ELK port spacing | Steps 13, 20-23 | Skill (update) | Praxion-renderer detail with a reusable D2 core |
| 9 | Read-only acceptance driver counts LikeC4 auto-ancestor frames as drawn elements | Steps 22-23 | Skill (update) | Folded into P6 (oracle-reading gotchas) |
| 10 | Integration-checkpoint inner suite must be the bare default, not a hand-listed set | Verifier | Skill (update) | testing-strategy / coordination-details |
| 11 | Mixed `resolve_test_scope` invocation: `tests` namespace collisions | Steps 7, 9, 17 | Skip | Repeated in the harness memory family (`feedback_ci_equivalent_test_invocation`) and resolver already widens; env-specific |
| 12 | Bare `git stash` in shared worktree | Steps 9/10 | Skip | Already in `rules/swe/vcs/git-conventions.md:23` |
| 13 | Heredoc `${var:+...}` loses quotes; zsh no word-split | Steps 17, 24 | Skip | zsh half is in memory `feedback_zsh_param_expansion_no_word_split`; heredoc half too narrow |
| 14 | Dead golden-rule path gate | Step 17 | Skip | Tech-debt ledger row; not a reusable pattern beyond gate-liveness (already a rule) |
| 15 | Plan shorthand vs Public Contract names (`c4_context` vs `c4_system_context`) | Step 11 | Skip | Pipeline-specific; cure is the existing "contract beats plan" practice |
| 16 | Dashboard e2e flaky under `-n auto` | Verifier | Skip | td-384 |
| 17 | Draft-id deleted draft / id removal from committed surfaces | Architect | Skip | ADR-protocol detail already in adr-authoring-protocols |
| 18 | Tools' update banners embed pin strings; version guards must compare stripped stdout, not "pin appears anywhere" | Step 14 | Skill (update) | Generalisable version-probe gotcha, folded into P4's neighbour P5 |
| 19 | Planner: a pin bump precedes consumers; version scanners read every tracked file | Planning | No-op | Recorded in dec-442 and `render-and-regen.md` |
| 20 | Listing-token headroom (99 tokens) forces description budgeting | Architect | No-op | Existing diet registry / budget tooling |
| 21 | Category encoding, view set, onboarding kit, tokens | Decisions | No-op | dec-438..444 |
| 22 | Legibility/proportion thresholds calibrated, not sourced | Architect | No-op | Stated in `review-checks.md` |
| 23 | Light-only, plain labels, no markdown labels in D2 | Architect | No-op | `render-and-regen.md` / `style-canon.md` |
| 24 | `sed -i` without suffix fails on macOS | doc-engineer | Skip | Environment-trivial; python replace already habitual |

## Discipline-Gap Signals

None recorded.

## Proposals

### Proposal 1: hook-crafting — a hook that runs git from a subdirectory must pin the work tree (extends a pending sibling)

- **Disposition**: pending
- **Type**: skill (update)
- **Maturity**: mature
- **Scope**: narrow
- **Priority**: P1 (next-cycle)
- **Source(s)**: WIP.md "Orchestrator record — hook-environment staging bug": "git exports `GIT_DIR` to hook processes and `stage()` ran `git add` from the diagram directory, which git then treated as the work tree"; Verifier merged candidate: "a mutation survivor dismissed as 'the test already stands in the repository root' ... is the exact class a git hook exposes (`GIT_DIR`)". Harness memory `feedback_git_dir_hook_env_subdir_git_calls` records the same lesson.
- **Description**: Add to hook-crafting Gotchas: when a hook-invoked script runs git from a subdirectory, run it from the top with `GIT_WORK_TREE` explicit (or scrub `GIT_DIR`/`GIT_INDEX_FILE`), and test it with the hook environment set. Tests that invoke the hook entry directly never see the defect, so a regression test must export `GIT_DIR` itself and be shown to fail on the old code.
- **Rationale**: Second independent occurrence (the 2026-09-04 report found the `git -C <other-repo>` variant). The skill carries neither today (grep of `skills/hook-crafting` finds no `GIT_DIR`). Cost of the miss here: 22 stray renders committed at the repo root.
- **Estimated scope**: one Gotchas entry (merge with the pending 2026-09-04 proposal 2 rather than adding a second)
- **Overlap check**: pending `SKILL_GENESIS_REPORT_2026-09-04_15-12-10.md` proposal on `GIT_DIR` scrubbing (same skill, adjacent failure); no existing artifact. Dedup verdict: extends, merge on disposition.
- **Recommended delegation**: context-engineer
- **Suggested artifact path**: `skills/hook-crafting/SKILL.md` (Gotchas)
- **Confidence**: high (two occurrences, one with a differential regression test).

### Proposal 2: git-conventions — check the index for staged deletions before a pathspec commit

- **Disposition**: pending
- **Type**: rule (update)
- **Maturity**: sapling
- **Scope**: narrow
- **Priority**: P2 (someday)
- **Source(s)**: LEARNINGS orchestrator note: "A deletion staged with `git rm` by an implementer rides the next pathspec commit of a *different* step (the index already holds it): check `git diff --cached --name-status` for `D` rows before each lane commit, or commit the deleting step first. Here `scripts/normalize_d2_svg.sh`'s deletion landed in cbdc7690."
- **Description**: One bullet in `rules/swe/vcs/git-conventions.md`: before a pathspec commit, read every `git diff --cached --name-status` row; a pre-staged rename or deletion is not limited by the pathspec. Remedy: commit the owning step first or unstage.
- **Rationale**: Recurs in multi-lane pipelines with pathspec commits; currently only in harness memory (`feedback_prestaged_deletion_rides_next_pathspec_commit`), which is not visible to other users or to subagents.
- **Estimated scope**: single bullet in an existing rule (rule is path-scoped or lean; verify budget with `scripts/measure_token_budget.py`)
- **Overlap check**: git-conventions lines 23-24 cover stash and dirty-tree destructiveness, not pre-staged deletions. Dedup verdict: partial (adjacent), extend.
- **Recommended delegation**: context-engineer
- **Suggested artifact path**: `rules/swe/vcs/git-conventions.md`
- **Confidence**: medium (two sightings, the memory is the stronger record; reject if the user wants memory to remain the home).

### Proposal 3: testing-strategy — mutation survivors in subprocess and environment boundaries are test gaps, not equivalents

- **Disposition**: pending
- **Type**: skill (update)
- **Maturity**: sapling
- **Scope**: narrow
- **Priority**: P1
- **Source(s)**: Verifier: "a mutation survivor dismissed as 'unobservable: the test already stands in the repository root' for a git subprocess's `cwd` or env is the exact class a git hook exposes"; Step 14 mutation reading (31 survivors classed unobservable incl. 8 git `cwd`); td-383.
- **Description**: Add a Gotchas bullet: before dismissing a survivor as equivalent, ask whether another caller environment (hook, CI, different cwd, case-sensitive FS) would observe it; if so write the test that sets that environment. Equivalence is a claim about every caller, not about the test machine.
- **Rationale**: The step-14 disposition was the proximate cause of the GIT_DIR defect reaching a commit. Generalises beyond git.
- **Estimated scope**: one bullet in `skills/testing-strategy/SKILL.md` (or the python-testing reference's mutation section)
- **Overlap check**: SKILL.md line 170 names mutation testing as a proxy; the mutation-recipe proposal in `SKILL_GENESIS_REPORT_2026-09-23_23-05-46.md` P1 covers layout, not survivor triage. Partial.
- **Recommended delegation**: context-engineer
- **Suggested artifact path**: `skills/testing-strategy/SKILL.md` or `references/python-testing.md`
- **Confidence**: high.

### Proposal 4: testing-strategy / mutation recipe — sensor blind spots with script-run subprocesses and `__file__` lookups

- **Disposition**: pending
- **Type**: skill (update)
- **Maturity**: sapling
- **Scope**: narrow
- **Priority**: P1
- **Source(s)**: Step 24: "mutmut's trampoline names a mutant by `orig.__module__`, which is `__main__` when the installer runs as a script, so a test that shells out to the installer passes against every mutant. Test behaviour in process (`kit.main([...])`)"; "tests that locate the checkout from `__file__` fail under the sensor ... one directory deeper"; Step 14: the sensor copies only top-level `*.py`, tests reading fixtures fail, and a slow real-toolchain test runs once per surviving mutant.
- **Description**: Extend the (pending) flat-`scripts/` mutation recipe with four sensor-compat rules: test in process, not by subprocess, for mutation credit; locate the repo by walking up to a marker, not by `__file__` arithmetic; build fixtures in code (no read of `tests/fixtures/`); gate slow real-tool tests off the sensor PATH.
- **Rationale**: Three independent implementer observations in one pipeline; any new script in `scripts/` hits them.
- **Estimated scope**: section of a single reference (merge into the pending proposal rather than adding another)
- **Overlap check**: `SKILL_GENESIS_REPORT_2026-09-23_23-05-46.md` P1 (pending) is the home; skills/ has no mutation sensor text. Dedup verdict: extends pending sibling.
- **Recommended delegation**: context-engineer
- **Suggested artifact path**: `skills/testing-strategy/references/python-testing.md`
- **Confidence**: medium-high (mutmut behaviour probed in-pipeline; version-specific).

### Proposal 5: software-planning — retiring an identifier requires a sweep over templates, examples and the rule text, in the same step

- **Disposition**: pending
- **Type**: skill (update)
- **Maturity**: sapling
- **Scope**: narrow
- **Priority**: P1
- **Source(s)**: Verifier F-01 / merged candidate: "Retiring an identifier (a view id, a file name) needs a grep over templates and examples in the same step: here Step 9 wrote the retired `context.svg` into two templates while the model step retired it." Related: Step 6 rename grep surfaced recorded fixtures; Step 11 plan/contract name mismatch.
- **Description**: Add a `Done when` phrasing for retire/rename steps: a repo-wide grep for the old identifier (excluding named history: ADR text, frozen snapshots, recorded fixtures) is empty, with the exclusion list stated in the step. Plan authors name the exclusions up front so the grep is greppable rather than negotiated at review.
- **Rationale**: A recurring plan-authoring gap: this pipeline needed three post-hoc exclusions (`eval/tests/fixtures`, ADR draft, metrics snapshots). The related pending proposal on greppable Done-when (09-23_23-05-46 P2) is the nearest home.
- **Estimated scope**: one paragraph in a software-planning reference
- **Overlap check**: pending sibling "Done-when phrasing must be greppable" in 2026-09-23_22-xx batch; partial. Consumer-check memory (`feedback_relocation_needs_structural_consumer_check`) covers relocation, not retirement.
- **Recommended delegation**: context-engineer
- **Suggested artifact path**: `skills/software-planning/references/` (the planning-pitfalls or step-schema reference; confirm)
- **Confidence**: medium (one strong incident, two supporting).

### Proposal 6: testing-strategy / verifier guidance — guards must read the narrowest structure that can carry the claim

- **Disposition**: pending
- **Type**: skill (update)
- **Maturity**: sapling
- **Scope**: narrow
- **Priority**: P2
- **Source(s)**: Verifier C-1/td-381: "A 'shows no element name' guard that searches all text is vacuous whenever a title or legend spells an element name; read the element groups instead." Steps 22-23: the read-only driver "counts LikeC4's auto-ancestor frames as drawn elements", so dissolving frames failed the labels node; Step 17a: a raw-substring assertion on SVG markup was the real oracle, not the reader.
- **Description**: Gotcha: a negative guard ("nothing shows X") passes vacuously if the searched region can legitimately contain X for another reason; scope the search to the structure that carries the claim, and write one bad-case fixture where X appears only in the decoy region. Companion: before building to an independent oracle, read what it actually counts.
- **Rationale**: Same shape as the gate-liveness family (a guard that cannot fire); a generalisation, not diagram-specific.
- **Estimated scope**: one bullet; or fold into `rules/swe/gate-liveness.md` examples
- **Overlap check**: gate-liveness rule covers gates that cannot fire in a given shape; this is the specific vacuous-scope case. Partial.
- **Recommended delegation**: context-engineer
- **Suggested artifact path**: `skills/testing-strategy/SKILL.md` (Gotchas) or `rules/swe/gate-liveness.md`
- **Confidence**: medium.

### Proposal 7: likec4-diagramming — D2 emission recipes and the one-raster-look done criterion

- **Disposition**: pending
- **Type**: skill (update)
- **Maturity**: sapling
- **Scope**: medium
- **Priority**: P2
- **Source(s)**: Step 13 visual probe ("unquoted `icon: data:...;base64` parses as a class field name; fractional `stroke-width` refused; a connection's `style.fill` is its label background; ELK ignores `direction` on top-level containers; `grid-columns: 4` lays the legend out compactly"); Step 22 "Legend fix recipe: tail dot to an unlabelled caption node ... `vertical-gap` doubles as bottom margin; nested `direction` is honoured one level only"; Steps 20-21 (ELK port spacing width/(n+1); layout hints ignored); Verifier: "keep one rasterized look per touched view in the done-criteria".
- **Description**: A short `references/d2-emission-recipes.md` (or an appendix to `render-and-regen.md`) holding D2 0.7.1 emission facts needed by anyone modifying or forking the renderer: whole-pixel strokes, quoted data-URI icons, label-background fill, unique legend recipe, ELK limits, unique-key prefixing, plus the rule that text-decidable checks are necessary not sufficient. Today the skill documents the command and its checks, not how to extend the emitter.
- **Rationale**: These are the facts that cost the most probing time. Because the same code is shipped as a project-local copy, extension is realistic. Keep P2: audience is a renderer maintainer, not every activation.
- **Estimated scope**: one reference file (~60 lines); SKILL.md link only
- **Overlap check**: `style-canon.md` (principles), `review-checks.md` (DRC thresholds), `render-and-regen.md` (command contract; "no network, icons vendored") cover none of the emitter facts. Partial no-op for whole-pixel strokes only if `render-and-regen.md` mentions them (not found in grep). Respect the listing-token headroom: no description change.
- **Recommended delegation**: context-engineer
- **Suggested artifact path**: `skills/likec4-diagramming/references/d2-emission-recipes.md`
- **Confidence**: medium (accurate to d2 0.7.1; version-bound, mark the pin).

## No-op items (already captured)

| Item | Where it already lives |
|---|---|
| Frames vs boxes, exact category wording, relationship identity | `skills/likec4-diagramming/references/style-canon.md`, dec-439 |
| Silent acceptance is a failure; four regeneration-failure kinds | `render-and-regen.md`, dec-442/443 |
| Thresholds (960 px, 10 px, 0.5-2.5, 9 arrows) calibrated not sourced | `review-checks.md` |
| Plain labels only, no dark mode | `render-and-regen.md`, `style-canon.md` |
| LikeC4 DSL placement rules (view tag first line, relationship style props, `extends` inherits tags), `<->` not asserted | `likec4-authoring-recipes.md` |
| MCP tool count (20), `preview-view` limits | `mcp-tool-recipes.md` |
| Pin bump atomic and first; version scanner reads every file | dec-442, `render-and-regen.md` |
| Orchestrator fan demoted at view level | dec-438 |
| Bare `git stash` in shared worktree | `rules/swe/vcs/git-conventions.md:23` |
| zsh `${var:+}` word split | harness memory, `feedback_zsh_param_expansion_no_word_split` |
| Dead golden-rule path gate | td ledger; gate-liveness rule |
| Version banner contains the pin (guard compares stripped stdout) | recorded as a Step 14 test; small enough to stay in LEARNINGS history (Triage #18 folded here, no separate proposal) |

## Recommended Delegations

| Proposal | Delegation Path | Notes |
|---|---|---|
| 1 | context-engineer | Merge with pending 2026-09-04 GIT_DIR proposal; load skill-crafting |
| 2 | context-engineer | Rule update; load rule-crafting; check token budget |
| 3 | context-engineer | Skill update |
| 4 | context-engineer | Merge into pending mutation-recipe proposal |
| 5 | context-engineer | Pair with pending Done-when greppable proposal |
| 6 | context-engineer | Skill or rule placement is ambiguous; context-engineer decides |
| 7 | context-engineer | New reference in an existing skill |

## Disposition Log

<!-- Populated by /skill-genesis-review. Empty on report creation. -->

| Timestamp | Proposal | Disposition | Notes |
|---|---|---|---|
| _(empty — pending review)_ | | | |

## Recommended Next Steps

- Run `/skill-genesis-review` to disposition the 7 pending proposals; P1, P4 and P5 extend pending siblings and should be merged on disposition.
- Harvest scope was bounded: ~120 pipeline-specific implementer notes (renderer internals, per-step mutation counts) were not itemised because they are history in dec-441..444 and the code.
