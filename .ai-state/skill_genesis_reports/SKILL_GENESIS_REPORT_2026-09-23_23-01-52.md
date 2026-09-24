---
schema_version: 1
report_id: skill-genesis-2026-09-23_23-01-52
generated_at: 2026-09-23T23:01:52Z
task_slug: skill-genesis-2026-09-23
agent_version: skill-genesis@bfebf639
invocation_args: { since: null, scope: null, sources: ".ai-work/_harvest", batch: "8 of 13", dry_run: false }
review_status: pending
disposition_count: { pending: 6, approved: 0, rejected: 0, refined: 0, deferred: 0 }
---

# Skill Genesis Report — 2026-09-23 23:01:52

## Summary

3 learning sources analyzed (queue mode, batch 8 of 13: `process-economy-p3-2-adopt` main pipeline,
its `spike/` sub-directory, and `process-economy-p3-4`), ~28 discrete learning items extracted, 6
proposals generated, ~22 items deduplicated (already implemented in code, already covered by an
existing rule/skill, already captured in this run's sibling reports, or too narrow/transient to
formalize). Review status: pending.

## Learning Sources Consumed

| Source | Path | Items Extracted | Status |
|---|---|---|---|
| Queue source — main pipeline LEARNINGS.md | `.ai-work/_harvest/process-economy-p3-2-adopt/LEARNINGS.md` | ~18 | Read |
| Queue source — spike LEARNINGS.md | `.ai-work/_harvest/process-economy-p3-2-adopt/spike/LEARNINGS.md` | ~6 | Read |
| Queue source — P3.4 LEARNINGS.md | `.ai-work/_harvest/process-economy-p3-4/LEARNINGS.md` | ~4 | Read |
| VERIFICATION_REPORT.md | (not separately mined — batch scope named LEARNINGS.md only; `REWORK_MANIFEST.md` items folded into the LEARNINGS.md "Rework after verification" section already read) | 0 | Not read (in-scope items already covered via LEARNINGS.md) |
| Latest SENTINEL_REPORT_*.md | `.ai-state/sentinel_reports/` | — | Not read (queue-mode batch; scope limited to listed sources) |
| Latest IDEA_LEDGER_*.md | `.ai-state/idea_ledgers/` | — | Not read (queue-mode batch; scope limited to listed sources) |
| ADRs (recent) | `.ai-state/decisions/` | — | Pre-scanned on demand for overlap (dec-386, dec-389 referenced inline in sources, not independently queried) |
| Calibration log Retrospective cells | `.ai-state/calibration_log.md` | — | Not read (queue-mode batch; scope limited to listed sources) |
| Sibling reports (this run, batches 1–7) | `.ai-state/skill_genesis_reports/SKILL_GENESIS_REPORT_2026-09-23_22-{35-25,39-30,43-59,47-22,51-24,55-14,58-35}.md` | — | Read — grepped `## Proposals` headings; one overlap found (see Proposal 1) |
| Harness memory (dedup, not a harvest source) | `/Users/fperez/.claude/projects/-Users-fperez-dev-praxion/memory/` | — | Consulted for dedup only; 2 items already captured as personal-assistant memory (worktree skill visibility, reconciler last-line status) but not yet formalized as project artifacts — treated as candidates, not skipped |

## Triage Results

| # | Item | Source | Decision | Rationale |
|---|---|---|---|---|
| 1 | `wc -c`/`git diff` byte-budget checks count the whole changed line, not the delta, for an appended sentence | main LEARNINGS Step 6 | Rule (update) | Recurring risk for any future prose-seam/byte-ceiling step; no existing coverage |
| 2 | "Done-when: both return sites" anchored the reviewer to counting sites instead of grepping every occurrence, letting a third site slip past light-review | main LEARNINGS, orchestrator note after Step 2/5 | Rule/skill (update) | General plan-authoring discipline, reusable beyond this pipeline; no existing coverage |
| 3 | Two occurrences in one pipeline of "a fixture built from the same reading as the code under test cannot disagree with it" (journal `event`/`type` key; `_orchestrator_stats`/`tool_result` fixture never written) | main LEARNINGS Steps 11-15 + rework | Skill (update), extends pending sibling proposal | Recurred twice independently in this pipeline alone — strong maturity signal; overlaps a pending Proposal 5 in `SKILL_GENESIS_REPORT_2026-09-23_22-55-14.md` (same principle, narrower framing: probe-fixture fidelity) — recommend merge at drafting time |
| 4 | Comparing ISO timestamps of differing precision/offset format (`…Z` ms vs `…+00:00` µs) lexicographically disagrees with chronological order; fixed by parsing to aware datetimes | main LEARNINGS, rework section | Rule (update) | General Python/timestamp gotcha; `coding-style.md`'s existing Timestamp Formatting section has no comparison guidance |
| 5 | A worktree-built, user-invocable skill is invisible to the pipeline session that built it unless launched with `claude --plugin-dir <worktree>`; brace-form `${CLAUDE_PLUGIN_ROOT}` substitutes at skill-load, shell `$CLAUDE_PLUGIN_ROOT` does not; `disable-model-invocation: true` skills never appear in the model's own listing | main LEARNINGS Step 10 + dogfood session notes | claude.md (docs addition) | Structural Claude Code limitation already captured as personal-assistant memory (`worktree-skill-not-visible-from-building-session`) but not yet in `docs/claude-code-limitations.md`, where the note itself flags it as a candidate row; formalizes it for every future worktree-built-skill pipeline, not just this session |
| 6 | Two prompt instructions stating the same fact in different words ("write only through absolute paths" + "write exactly `.ai-work/<slug>/…`") produced inconsistent output (2 relative + 1 absolute path on N=3) | main LEARNINGS, rework section | Rule/skill (update) | General prompt-authoring discipline for planner/context-engineer prose seams and delegation prompts; no existing coverage found |
| 7 | Workflow-encoded lens fan-out architecture (dec-389), workflow-agent transcript path fix, `_parse_ts` implementation, TEST_RESULTS.md fixed-shape schema folding (dec-386) | all three sources | Skip | Already implemented in shipped code/rules — not a proposal, it is the work itself |
| 8 | `check_gate_liveness.py --check uninvoked-gate` reported no finding for a genuinely-uninvoked new script mid-pipeline | main LEARNINGS Step 4 | Skip | Transient WIP-state observation, resolved once the doc step (Step 8/9) landed the catalog rows in the same pipeline; not a recurring gap |
| 9 | `_workflow_run.transcripts_dir` copying `context_baseline.py`'s `/`→`-`-only mangling missed the harness's `.`→`-` mapping, breaking worktree runs | main LEARNINGS Step 10 | Skip | Already fixed in this pipeline (`d09f42b2`); the general "test path-mangling conventions against real harness path shapes" lesson folds into Proposal 3's fixture-fidelity framing rather than standing alone |
| 10 | TEST_RESULTS.md `Result: pass= fail= skip=` schema has no pre-existing-failure slot, `reconcile_pipeline_state.py` reads the final line for every step | main LEARNINGS Step 10 rework | Skip | Already resolved by dec-386 and already captured verbatim as personal-assistant memory (`reconciler-last-line-test-status`); no gap remains to formalize |
| 11 | `scripts/validate_references.py` cited at the wrong path in multiple plan/Done-when texts (real path: `skills/skill-crafting/scripts/validate_references.py`) | main LEARNINGS Steps 5/6 | Skip | One-off path-typo correction, not a reusable pattern; already self-corrected in the pipeline's own prompts |
| 12 | P3.4: TEST_RESULTS.md schema pointer over restated prose (single source of truth vs. duplicating a fixed-shape block in 3 files) | P3.4 LEARNINGS | Skip | Already covered by `gate-liveness.md`'s existing "convention lives at two+ textual sites" anti-pattern row, cited verbatim in the source |
| 13 | P3.4: TT07 corpus is git-tracked-only (`git ls-files`), lags by exactly the untracked files until staged | P3.4 LEARNINGS | Skip | Narrow to one script's known-by-design behavior; not a general pattern |
| 14 | Spike: workflow transcripts nest one level deeper (`subagents/workflows/<run>/`), workflow agents take the harness's model not Praxion's routing, `resumeFromRunId` is not a re-run | spike LEARNINGS | Skip | Already fixed in shipped code (`hooks/capture_session.py`, `scripts/context_baseline.py`) and named in `skills/agent-crafting/SKILL.md` per the source's own "Trigger resolved" note |
| 15 | `--include-main`'s one-finding-per-most-specific-kind output masks payload-kind findings once a path-kind hit fires for the same sibling | main LEARNINGS Steps 11-15 | Skip | Narrow to `check_lens_isolation.py`'s own reporting granularity; a td-candidate for that script, not a cross-cutting pattern |

## Proposals

### Proposal 1: coding-style.md or gate-canaries.md — whole-line diff counting inflates byte-budget checks

- **Disposition**: pending
- **Type**: rule (update)
- **Maturity**: sapling
- **Scope**: narrow
- **Priority**: P1 (next-cycle)
- **Source(s)**: `.ai-work/_harvest/process-economy-p3-2-adopt/LEARNINGS.md` § "Learnings — Step 6 (C7 prose seams)"
- **Description**: A short gotcha for any rule/skill that guides byte-ceiling or diff-size measurement: `git diff | grep '^+' | wc -c` (or equivalent) counts the *entire* new line for any line that changed, not just the appended delta — appending a sentence to an existing paragraph line inflates the measured "addition" by the whole pre-existing sentence (787 B measured vs. ~95 B true addition in the source pipeline). State the fix as a convention: insert new content as its own line/paragraph when a byte ceiling is in play, so any `wc -c`-based check stays proportional to what actually changed.
- **Rationale**: The source pipeline's own O1 byte-budget objection (`swe-agent-coordination-protocol.md`-adjacent prose-seam ceiling) was measured this way; the gotcha is directly reusable by any future prose-seam, byte-ceiling, or diff-size step across the ecosystem (e.g. `gate-canaries.md`'s byte-ceiling guidance, `dec-386`'s TEST_RESULTS.md byte ceiling). No existing rule states this.
- **Estimated scope**: single rule file, 3-4 line addition
- **Overlap check**: none — `coding-style.md`'s Timestamp Formatting and general style sections do not cover diff/byte measurement; `gate-canaries.md` covers mutation-probe canaries, not byte-ceiling arithmetic
- **Recommended delegation**: context-engineer
- **Suggested artifact path**: `rules/swe/coding-style.md` or `skills/testing-strategy/references/gate-canaries.md` (context-engineer to decide placement — cross-cutting measurement gotcha vs. gate-authoring specific)

### Proposal 2: software-planning references — Done-when phrasing must be greppable, not countable

- **Disposition**: pending
- **Type**: skill (update)
- **Maturity**: sapling
- **Scope**: medium
- **Priority**: P1 (next-cycle)
- **Source(s)**: `.ai-work/_harvest/process-economy-p3-2-adopt/LEARNINGS.md` § "Orchestrator notes after Step 2 / Step 5 review"
- **Description**: A short authoring convention for `IMPLEMENTATION_PLAN.md` Done-when clauses and `intra-step-review.md`'s light-review guidance: phrasing a Done-when as "both return sites" (a count) anchors the reviewer to enumerate a fixed number, so a third, unanticipated occurrence of the same pattern silently escapes review. Phrase Done-when clauses over a repeated pattern as "every return site carrying `X`" (a predicate a grep can verify exhaustively), not as an enumerated count.
- **Rationale**: Directly caused a missed finding in this pipeline's own Step 5 light-review (the third `lenses`-carrying return site went unprojected) — a concrete, attributable failure mode with a cheap textual fix. Reusable by the implementation-planner and by any Done-when clause covering a repeated code pattern.
- **Estimated scope**: single reference file, one short callout (3-5 lines) in either `decomposition-guide.md` (plan authoring) or `intra-step-review.md` (light-review guidance)
- **Overlap check**: none — neither reference file currently addresses Done-when phrasing against enumerable patterns
- **Recommended delegation**: context-engineer
- **Suggested artifact path**: `skills/software-planning/references/decomposition-guide.md` or `skills/software-planning/references/intra-step-review.md`

### Proposal 3: testing-strategy — ground-truth fixture fidelity for harness-shaped code (extends pending sibling proposal)

- **Disposition**: pending
- **Type**: skill (update)
- **Maturity**: mature
- **Scope**: medium
- **Priority**: P0 (this-cycle)
- **Source(s)**: `.ai-work/_harvest/process-economy-p3-2-adopt/LEARNINGS.md` § "Steps 11-15" and § "Rework after verification" (two independent occurrences in the same pipeline); overlaps `SKILL_GENESIS_REPORT_2026-09-23_22-55-14.md` Proposal 5 ("re-verify a synthetic probe fixture against the real artifact before trusting its result")
- **Description**: State the discipline explicitly in `gate-canaries.md` (or `python-testing.md`'s fixture-builder guidance): a test fixture that is built from the same reading of an external contract (a harness JSON schema, a journal file shape, a tool-result correlation key) as the code under test **cannot disagree with that code**, however green the suite reads — both share one interpretation, so a wrong shared assumption is invisible to both. Two independent instances hit this in one pipeline: (a) both the fixture writer and `read_journal`/`_journal_results` used the key `event` where the live harness actually writes `type`, so 32/32 green certified a key no real journal has ever carried; (b) the mutation-sensor-flagged `_orchestrator_stats`/`_tool_result_bytes` functions stayed "unobservable-by-contract" because no fixture ever wrote a `tool_result` record at all. The fix pattern: when writing a fixture for code that reads an external/harness-produced artifact, seed at least one fixture from a verbatim excerpt of a *real* instance of that artifact (not a helper built from the same spec reading), and prefer a differential (remove the fix, confirm RED against the verbatim fixture, restore, confirm GREEN) over trusting a synthetic-only green suite.
- **Rationale**: This is the pipeline's single most costly and most recurrent lesson — it caused two live-run failures (dead-on-arrival instruments, a verifier FAIL) that a mutation sensor's own "unobservable-by-contract" classification had already pointed at without being acted on. It overlaps in principle with the pending sibling proposal from an earlier batch of this same harvest run, which frames the same insight narrower (probe-fixture fidelity specifically); recommend the context-engineer merge the two at drafting time into one broader "ground-truth fixture" guidance passage rather than shipping two overlapping callouts.
- **Estimated scope**: single skill reference file, one substantive subsection (~15-20 lines) covering both the probe-fixture framing (sibling proposal) and the harness-artifact framing (this proposal)
- **Overlap check**: `SKILL_GENESIS_REPORT_2026-09-23_22-55-14.md` Proposal 5, pending — same underlying principle, narrower source; merge recommended, not duplicate
- **Recommended delegation**: context-engineer (review scope against the sibling pending proposal) then implementer (content)
- **Suggested artifact path**: `skills/testing-strategy/references/gate-canaries.md`

### Proposal 4: coding-style.md — mixed-precision ISO timestamps must be parsed before comparison, never compared as strings

- **Disposition**: pending
- **Type**: rule (update)
- **Maturity**: sapling
- **Scope**: narrow
- **Priority**: P2 (someday)
- **Source(s)**: `.ai-work/_harvest/process-economy-p3-2-adopt/LEARNINGS.md` § "Rework after verification"
- **Description**: A short addition to `coding-style.md`'s existing Timestamp Formatting section: two ISO 8601 timestamps from different producers can carry different precision and offset notation (e.g. `…Z` with milliseconds from a transcript vs. `…+00:00` with microseconds from a WAL row) and their string forms can disagree with true chronological order under lexicographic comparison. Any time-window heuristic or ordering logic over timestamps from more than one source must parse to an aware `datetime` (or language equivalent) before comparing, never compare the raw strings.
- **Rationale**: A concrete, attributable bug in this pipeline (`_parse_ts` was added specifically to fix this); the existing Timestamp Formatting section documents *how to produce* ISO 8601 timestamps but says nothing about the comparison hazard when consuming timestamps from multiple producers — a small, high-signal gap.
- **Estimated scope**: single rule file, 2-3 line addition to the existing Timestamp Formatting section
- **Overlap check**: `coding-style.md` § Timestamp Formatting exists but covers production format only, not cross-source comparison
- **Recommended delegation**: context-engineer
- **Suggested artifact path**: `rules/swe/coding-style.md`

### Proposal 5: docs/claude-code-limitations.md — worktree-built user-invocable skill dogfood protocol

- **Disposition**: pending
- **Type**: claude.md
- **Maturity**: mature
- **Scope**: medium
- **Priority**: P1 (next-cycle)
- **Source(s)**: `.ai-work/_harvest/process-economy-p3-2-adopt/LEARNINGS.md` § "Step 10 (orchestrator, pre-dogfood confirmation)" and § "Steps 11-15, dogfood session 7edc5d0d"
- **Description**: Add a row to `docs/claude-code-limitations.md` documenting three empirically-verified facts about dogfooding a worktree-built, user-invocable skill: (1) the session's skill listing is snapshotted at launch from whichever plugin root was registered — a worktree-built skill is invisible to the pipeline session that built it unless that session is launched with `claude --plugin-dir <worktree>`; (2) Claude Code substitutes the brace form `${CLAUDE_PLUGIN_ROOT}` inside a skill body at load time with the active plugin's root, but the shell form `$CLAUDE_PLUGIN_ROOT` is never substituted and the Bash env var of the same name stays pinned to the main checkout via `~/.claude/settings.json` — a skill body must rely on the brace form, never the shell variable, for this to work under `--plugin-dir`; (3) a skill with `disable-model-invocation: true` never appears in the model's own listing by design (same as `/resume-pipeline`), so "confirm the skill appears in the session's listing" is only answerable via the user's own `/` autocomplete, never by the orchestrator — a plan step written as an orchestrator-side check for such a skill is structurally unsatisfiable.
- **Rationale**: This is exactly the kind of empirically-verified, non-obvious Claude Code runtime behavior `docs/claude-code-limitations.md` exists to catalog (per CLAUDE.md's own "Known Claude Code Limitations" section) — the source's own recovery note explicitly names it "worth a `docs/claude-code-limitations.md` note if it recurs," and the same lesson is already captured as personal-assistant memory but not yet in the project-level catalog that future pipelines and other contributors would actually consult.
- **Estimated scope**: single doc file, one new catalog row (5-8 lines) with the three sub-facts and the recommended workaround (dogfood as a user action from a `--plugin-dir` session; test which plugin root is live by loading a model-invocable skill that differs on the branch, rather than by grepping the listing)
- **Overlap check**: none in `docs/claude-code-limitations.md` — existing rows cover worktree nesting on the Agent tool and subagent `Write` denials, not skill-listing snapshotting or `${CLAUDE_PLUGIN_ROOT}` substitution semantics
- **Recommended delegation**: context-engineer (review) then implementer or direct edit
- **Suggested artifact path**: `docs/claude-code-limitations.md`

### Proposal 6: software-planning / agent-crafting — one fact per prompt, stated once

- **Disposition**: pending
- **Type**: rule (update)
- **Maturity**: seedling
- **Scope**: narrow
- **Priority**: P2 (someday)
- **Source(s)**: `.ai-work/_harvest/process-economy-p3-2-adopt/LEARNINGS.md` § "Rework after verification"
- **Description**: A short authoring convention for delegation prompts, skill bodies, and agent instructions: two instructions stating the same underlying fact in different words (e.g. "write only through absolute paths" alongside "write exactly `.ai-work/<slug>/…`") do not reinforce each other — they read as two independent, potentially-conflicting constraints to the executing agent, producing inconsistent output (measured: 2 relative + 1 absolute path form returned across 3 lens agents given both instructions in one pipeline). State the fact once, in the form the consumer must act on, rather than restating it from a second angle for emphasis.
- **Rationale**: A concrete, measured failure in this pipeline's own lens-fanout skill prompt, with a clean fix (state the root path once, give paths relative to it). Generalizes to any prompt-writing context across the ecosystem's delegation checklists.
- **Estimated scope**: single reference file, one short callout (3-4 lines)
- **Overlap check**: none found in `agent-behavioral-contract.md`, `coordination-details.md`, or agent-crafting's prompt-writing guidance
- **Recommended delegation**: context-engineer
- **Suggested artifact path**: `skills/software-planning/references/coordination-details.md` (delegation-checklist prompt-writing guidance) or `skills/agent-crafting/` prompt-writing references (context-engineer to decide placement)

## Recommended Delegations

| Proposal | Delegation Path | Notes |
|---|---|---|
| 1 | context-engineer | Rule update; load rule-crafting; decide `coding-style.md` vs. `gate-canaries.md` placement |
| 2 | context-engineer | Skill reference update; load skill-crafting; decide `decomposition-guide.md` vs. `intra-step-review.md` placement |
| 3 | context-engineer then implementer | Skill reference update; context-engineer must first reconcile against the pending sibling proposal in `SKILL_GENESIS_REPORT_2026-09-23_22-55-14.md` Proposal 5 before drafting |
| 4 | context-engineer | Rule update; small addition to existing Timestamp Formatting section |
| 5 | context-engineer then implementer or direct edit | Docs catalog addition, not a rule/skill; context-engineer validates placement and phrasing, implementer or direct edit adds the row |
| 6 | context-engineer | Rule/skill update; decide `coordination-details.md` vs. agent-crafting placement |

## Disposition Log

<!-- Populated by /skill-genesis-review. Empty on report creation. -->

| Timestamp | Proposal | Disposition | Notes |
|---|---|---|---|
| _(empty — pending review)_ | | | |

## Recommended Next Steps

- Run `/skill-genesis-review` to disposition the 6 pending proposals (note: Proposal 3 requires reconciling against a pending sibling proposal from `SKILL_GENESIS_REPORT_2026-09-23_22-55-14.md` before drafting).
- After approval, invoke `context-engineer` for skills/rules/docs; the agent will pick up the recommended delegations table.
- Re-run `/skill-genesis` after the next pipeline completes if `LEARNINGS.md` accumulates further items.
