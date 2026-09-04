---
schema_version: 1
report_id: skill-genesis-2026-09-04_15-12-10
generated_at: 2026-09-04T15:12:10Z
task_slug: sidecar-placement
agent_version: skill-genesis@a1dbf602
invocation_args: { since: null, scope: sidecar-placement, dry_run: false }
review_status: pending
disposition_count: { pending: 6, approved: 0, rejected: 0, refined: 0, deferred: 0 }
---

# Skill Genesis Report — 2026-09-04 15:12:10

## Summary

7 learning sources analyzed (LEARNINGS.md + 8 folded fixer fragments inline, ARCH_WT_RULING.md §1/§13-15, VERIFICATION_REPORT_P0.md area, sentinel log, ADR drafts), ~14 discrete learning items extracted, 6 proposals generated, 8 items deduplicated or judged too narrow to formalize. Review status: pending.

## Learning Sources Consumed

| Source | Path | Items Extracted | Status |
|---|---|---|---|
| LEARNINGS.md (current task, incl. Batch 21 + folded F1-F8/cells-A/B fragments) | `.ai-work/sidecar-placement/LEARNINGS.md` | 11 | Read |
| ARCH_WT_RULING.md §1, §13-15 | `.ai-work/sidecar-placement/ARCH_WT_RULING.md` | 2 | Read (dogfood finding on file-vs-directory symlink write refusal) |
| AUDIT_PHILOSOPHY.md | `.ai-work/sidecar-placement/AUDIT_PHILOSOPHY.md` | 0 | Skimmed — disposition table only, no new extractable pattern beyond what Batch 21 already surfaced |
| INTEGRATION_FINDINGS.md | `.ai-work/sidecar-placement/INTEGRATION_FINDINGS.md` | 0 | Skimmed — findings already folded into LEARNINGS.md Batch 21 §1-7 |
| VERIFICATION_REPORT_P0.md | `.ai-work/sidecar-placement/VERIFICATION_REPORT_P0.md` | 0 | Not separately mined — its patterns are already reflected in the Batch-21 canary/gate tables above |
| `.ai-state/decisions/drafts/*.md` (12 fragments) | `.ai-state/decisions/drafts/` | 0 (context only) | Read filenames; content already summarized in LEARNINGS.md "Decisions Made" entries, no independent extraction needed |
| `.ai-state/sentinel_reports/SENTINEL_LOG.md` | `.ai-state/sentinel_reports/` | 0 | Read — last run 2026-08-30, predates this task; no overlapping finding |
| Latest IDEA_LEDGER | `.ai-state/idea_ledgers/` | — | Not found / not checked (out of scope for a hook/worktree-mechanics harvest) |
| Calibration log Retrospective cells | `.ai-state/calibration_log.md` | — | Not checked this pass (task not yet at calibration-log-append step) |

## Triage Results

| # | Item | Source | Decision | Rationale |
|---|---|---|---|---|
| 1 | File-level symlink Write/Edit refusal is distinct from directory-shadow symlinks (which succeed) — the harness refuses `CLAUDE.local.md`/`settings.local.json` file shadows even with realpath containment intact, but `.ai-state` directory shadows work | ARCH_WT_RULING.md §15 | Doc update (docs/claude-code-limitations.md) | Refines/corrects an existing but imprecise entry in my own persistent memory and the limitations doc has no entry at all for this yet; load-bearing for anyone building sidecar/shadow patterns |
| 2 | Hook/script git calls must scrub `GIT_DIR`/`GIT_INDEX_FILE`/`GIT_WORK_TREE` before targeting another repo — git exports these relative to hooks and they silently redirect a `git -C <other-repo>` call | LEARNINGS.md lines ~2125-2185 | Skill update (`hook-crafting` Gotchas) | Broadly generalizable to any hook or script that names a repository other than the one invoking it; killed a whole convergence channel silently while tests stayed green — exactly the "highest-signal gotcha" hook-crafting exists to hold |
| 3 | Ephemeral register/finding ids (`IF-nn`) leak into code comments and docstrings because `check_id_citation_discipline.py` has no class for them (24 hits missed on first sweep) | LEARNINGS.md line ~2836 | Skill update (`id-decontamination` Gotchas + Detection sweep) | Directly extends an existing skill's detection-sweep step with a concrete grep addition (`grep -rn 'IF-[0-9]' scripts hooks`) already proven in this task; a real gap in an existing check, not a one-off |
| 4 | ADR `dec-draft-<hash>` frontmatter id is hex-strict (`[0-9a-f]{8}`) but `adr-conventions.md` doesn't say so — a mnemonic draft id silently fails `finalize_adrs.py`'s regex and gets skipped | LEARNINGS.md cells-B fragment | Rule amendment, deferred to skill reference | `adr-conventions.md` is always-loaded at 24,574/25,000 tokens — no room for even a one-word addition without measuring; the precision gap is better absorbed by `adr-authoring-protocols.md` (on-demand skill reference), which the rule already points to for identity-derivation detail |
| 5 | Scenario-authoring lessons cluster: suppress `core.hooksPath` for a transient window rather than reasoning about which git trigger fires; `git init --bare -b main` for symref HEAD; rebuild a shared fixture (`D-00-setup.sh`) before trusting stale FAIL counts; frozen `git archive` extraction so fixers can edit while cells run | LEARNINGS.md Batch-21 §1, §4, F7/cells-A/B fragments | Skill update (`testing-strategy`) | Recurs across ≥4 distinct scenario fixtures in this task alone (F-G01-3, H-03, D-08, E-07); procedural, with concrete before/after evidence — qualifies as skill content, closest existing home is `testing-strategy`'s Gotchas/Fixture sections |
| 6 | "A row/assertion that cannot fail is noise" — every stale-after-a-design-change artifact in this task shared one shape (a health line, a PASS text, a docstring rationale, a design-doc claim) and the fix was always a test the artifact lacked, never more review | LEARNINGS.md line ~2647 ("hooks-chained" cross-ref), Batch-21 §2 | Skill update (`testing-strategy`) | Declarative principle with recurring evidence within this single task (doctor `placement` row design, `mount-conflict` reason string, `state-eligible` row) — fits Gotchas/Coverage Philosophy section as a named heuristic |
| 7 | `\b` word-boundary in grep is not a rename boundary when the new name extends the old with a hyphen (`.praxion` vs `.praxion-state`) | LEARNINGS.md F7 fragment | Skip | Single-occurrence grep-flavor detail, narrow and transient; the working fix (`grep -rnE '\.praxion([^-_a-zA-Z]|$)'`) is task-specific enough that a general shell-scripting skill doesn't exist to receive it, and creating one for this alone fails the "≥3 usage scenarios" bar |
| 8 | Subagent 80-turn `[PARTIAL]` returns are normal for wide mechanical work; re-derive completion from ground truth, resume with a scoped finish list | LEARNINGS.md F7 fragment ("stopped mid-way", "coordinator confirmed taking these over") | Already captured | `swe-agent-coordination-protocol.md`'s Completion Handshake rule and `docs/` truncation-recovery design already cover this pattern in full generality; no gap to close |
| 9 | Worktree-guard refuses any `bash -c`/heredoc containing enough git-adjacent text even with no git call, mitigated by per-file literal `sed -i` chains or the `Edit` tool | LEARNINGS.md F7 + cells-A fragments | Already captured | `docs/claude-code-limitations.md`'s worktree-guard entries and existing memory (`feedback_praxion_plugin_gate_release_chain`, worktree-guard eval-path false positive) already document the pattern class; this is one more instance of an already-documented gate behavior, not a new one |
| 10 | Two independent clones each need their own `install_git_hooks.py --install`; hooks don't share across clones the way they do across worktrees of one checkout | LEARNINGS.md cells-B fragment | Skip | Correctly-behaving, expected git semantics restated as a finding — not a gotcha the agent gets wrong by default; no default-reasoning break to prevent |
| 11 | `git status --porcelain` collapses a newly-untracked directory to `?? dir/`, not the file inside it | LEARNINGS.md cells-B fragment | Skip | Standard git behavior, not sidecar- or Praxion-specific; below the bar for a project skill/rule (general git knowledge the agent should already have, not project-specific convention) |
| 12 | Harness's `Write` tool refuses report/summary/findings/analysis-shaped filenames for subagents even for an explicit numbered deliverable; worked around via a `.sh` script that `cat`s a heredoc through Bash | LEARNINGS.md cells-B fragment | Already captured | This exact prohibition and its Bash-heredoc escape hatch is already the standing instruction in every agent's system prompt ("Do NOT Write report/summary/... files... Files written as input to another tool are fine") — restating it as a doc-limitation entry would duplicate existing, correctly-enforced guidance |
| 13 | Nested-session budget bookkeeping: `SKIP_SESSION2=1` env-gated bypass to stay within a 3-session budget after burning 2 on a fixture bug | LEARNINGS.md cells-B fragment | Skip | One-off script-level economization for this task's own scenario runner; too narrow/transient, no reuse surface beyond this task's `tmp/scenarios/` |
| 14 | `V AR=val fn` bash temp-assignment prefix works for shell *functions*, not just external commands, letting per-operator env vars scope to one call without a subshell | LEARNINGS.md cells-B fragment | Skip | General bash knowledge, not a project convention; below the bar per the same reasoning as item 11 |

## Discipline-Gap Signals

No signal recorded this pass — no learning item named a decision that would have benefited from a specialist voice the consultant registry does not carry. (One `discipline-consultant` engagement occurred in this task — `CONSULT_data-structure-specialist.md` — which is exactly the registry working as designed, not a gap.)

## Proposals

### Proposal 1: docs/claude-code-limitations.md — file-vs-directory symlink Write/Edit refusal

- **Disposition**: pending
- **Type**: claude.md (docs addition — `docs/claude-code-limitations.md`, the project's existing limitations catalog, referenced from CLAUDE.md)
- **Maturity**: mature
- **Scope**: narrow
- **Priority**: P0 (this-cycle)
- **Source(s)**: `.ai-work/sidecar-placement/ARCH_WT_RULING.md` § 15 ("File shadows — loaded through the link, tool-written at the mount path"); live dogfood, Claude Code 2.1.258
- **Description**: A new bullet entry stating that `Write`/`Edit` refuse a **file-level** symlink target unconditionally (regardless of realpath containment) — e.g. `CLAUDE.local.md -> ../.praxion-state/CLAUDE.local.md` — while **directory**-level symlink shadows (e.g. `.ai-state -> .praxion-state/.ai-state`) are unaffected and writes through them succeed. Includes the harness's own remediation message shape ("Write to the link's target path instead") and notes that Claude Code still *loads* a symlinked file (only writes are refused).
- **Rationale**: The existing `docs/claude-code-limitations.md` has zero entries on symlink write refusal, and my own persistent memory (`feedback_worktree_isolation_symlink_write_refusal.md`) currently states the refusal applies to "a symlink whose realpath leaves the worktree" without the file-vs-directory distinction this dogfood proved — directory shadows succeed even when their realpath is in-worktree, and file shadows are refused even when their realpath is in-worktree. Left uncorrected, a future agent designing a shadow/mount pattern would wrongly conclude directory symlinks are equally risky, or file symlinks are safe if realpath-contained.
- **Estimated scope**: docs addition, ~1 bullet (~150 words) following the existing five-entry pattern in the file
- **Overlap check**: `docs/claude-code-limitations.md` entries on worktree-guard/Explore/subagent-Write/agents-refusal — none cover symlink write semantics. Partial overlap with my own agent memory file (will be corrected independently of this report's disposition).
- **Recommended delegation**: context-engineer (review placement) then implementer or direct edit
- **Suggested artifact path**: `docs/claude-code-limitations.md`

### Proposal 2: hook-crafting Gotchas — scrub git repo-scoping env vars before cross-repo git calls

- **Disposition**: pending
- **Type**: skill (update)
- **Maturity**: mature
- **Scope**: medium
- **Priority**: P0 (this-cycle)
- **Source(s)**: `.ai-work/sidecar-placement/LEARNINGS.md` lines ~2125-2185 (implementer gotchas, "git exports a *relative* `GIT_INDEX_FILE=.git/index` to commit hooks")
- **Description**: Add a Gotchas entry to `skills/hook-crafting/SKILL.md`: any hook or script that calls `git -C <other-repo>` (or otherwise targets a repository different from the one that invoked it) must scrub `GIT_DIR`, `GIT_INDEX_FILE`, and `GIT_WORK_TREE` from the environment first — git exports these to hooks as paths *relative to the invoking repo*, and an inherited relative `GIT_INDEX_FILE` silently poisons a `-C` call into a linked worktree (`fatal: .git/index: index file open failed: Not a directory`). Identity (`GIT_AUTHOR_*`/`GIT_COMMITTER_*`) and config vars are explicitly *not* part of the scrub — those are caller/fixture intent, not repo-scoping.
- **Rationale**: This killed an entire post-commit convergence channel silently while every existing test stayed green (no test exercised the chain under a real hook environment) — the highest-signal shape of gotcha hook-crafting exists to capture. It generalizes to any Praxion hook or script that fans out across repos (sidecar mounts, worktree convergence, multi-repo tooling), not just this task.
- **Estimated scope**: SKILL.md Gotchas section, ~4-6 lines
- **Overlap check**: `skills/hook-crafting/SKILL.md` Gotchas section exists (checked, no current entry on env scrubbing); no rule currently covers this. None.
- **Recommended delegation**: context-engineer
- **Suggested artifact path**: `skills/hook-crafting/SKILL.md` (Gotchas section)

### Proposal 3: id-decontamination — ephemeral register ids leak into comments/docstrings undetected

- **Disposition**: pending
- **Type**: skill (update)
- **Maturity**: sapling
- **Scope**: narrow
- **Priority**: P1 (next-cycle)
- **Source(s)**: `.ai-work/sidecar-placement/LEARNINGS.md` line ~2836 ("The register ids leaked twice")
- **Description**: Add a Gotchas/Detection-sweep entry to `skills/id-decontamination/SKILL.md` noting that `check_id_citation_discipline.py` has no class for ephemeral pipeline-register ids (`IF-nn`, and by extension other per-task register prefixes) — they leak into code comments and docstrings undetected because the citation gate only knows about REQ/dec/td-style ids. The proven remedy from this task: an explicit `grep -rn 'IF-[0-9]' <scope>` sweep as a commit-blocking line, not a reliance on the existing gate.
- **Rationale**: A real, demonstrated gap in an existing, actively-used check (24 of the total leaked hits were missed by the first automated pass and only caught by manual grep) — extends `id-decontamination`'s own Detection sweep step rather than requiring a new skill.
- **Estimated scope**: SKILL.md addition, ~3-4 lines in an existing section
- **Overlap check**: `skills/id-decontamination/SKILL.md` § Detection sweep exists and covers REQ/dec-style ids; no existing coverage of ephemeral per-task register prefixes. None conflicting.
- **Recommended delegation**: context-engineer
- **Suggested artifact path**: `skills/id-decontamination/SKILL.md` (Gotchas + Step 1 — Detection sweep)

### Proposal 4: adr-authoring-protocols.md — draft id hash is hex-strict

- **Disposition**: pending
- **Type**: skill (update) — deliberately routed to the skill reference, not the always-loaded rule
- **Maturity**: sapling
- **Scope**: narrow
- **Priority**: P2 (someday)
- **Source(s)**: `.ai-work/sidecar-placement/LEARNINGS.md` cells-B fragment (`finalize_adrs.py:72` `FRONTMATTER_ID_PATTERN` hex-strict regex)
- **Description**: One-word precision addition to `skills/software-planning/references/adr-authoring-protocols.md` § Identity Derivation: the `dec-draft-<8-char-hash>` hash is restricted to `[0-9a-f]` (lowercase hex), not an arbitrary mnemonic string — a hand-authored id like `dec-draft-stdp0001` silently fails `finalize_adrs.py`'s regex and gets skipped with a warning rather than promoted.
- **Rationale**: `rules/swe/adr-conventions.md` is at 24,574/25,000 always-loaded tokens per the token-budget rule cited in the source item itself — no room for even a one-word addition there without a fresh measurement. The identity-derivation mechanics already live in the on-demand skill reference this rule points readers to, which is the correct, budget-safe home for this precision gap. The source's own author explicitly declined to file it as a formal finding ("not filed as a formal `IF-nn`... but worth a one-word doc tightening") — low urgency, correctly triaged P2.
- **Estimated scope**: single-line addition to an existing reference file
- **Overlap check**: `rules/swe/adr-conventions.md` frontmatter table states the format without the hex constraint (the gap this closes); `adr-authoring-protocols.md` § Identity Derivation is the sibling doc that should carry it.
- **Recommended delegation**: context-engineer
- **Suggested artifact path**: `skills/software-planning/references/adr-authoring-protocols.md`

### Proposal 5: testing-strategy — scenario/integration-fixture authoring gotchas

- **Disposition**: pending
- **Type**: skill (update)
- **Maturity**: sapling
- **Scope**: medium
- **Priority**: P1 (next-cycle)
- **Source(s)**: `.ai-work/sidecar-placement/LEARNINGS.md` Batch-21 §1 (suppress `core.hooksPath`), §4 (fixture bugs found on re-run), F7/cells-A/B fragments (shared-fixture staleness, frozen `git archive` extraction)
- **Description**: A cluster of four related, evidence-backed authoring gotchas for bash/git-based integration scenario tests: (a) suppress `core.hooksPath` for a transient window rather than reasoning about which of several multiplexed git triggers will fire; (b) `git init --bare -b main` (not the default) to avoid an unborn-HEAD symref that silently defeats "did the branch advance" probes; (c) rebuild a shared fixture (e.g. via its own `*-setup.sh`) before trusting a FAIL count that might be measuring staleness, not the code under test; (d) frozen `git archive` extraction as a pattern for letting scenario cells run while a fixer concurrently edits the same source tree.
- **Rationale**: These four recurred across at least four distinct scenario fixtures within this single task (F-G01-3, H-03, D-08, E-07) — each with a concrete before/after evidence trail (FAIL counts, root-cause traces) already captured in `LEARNINGS.md`. `testing-strategy`'s existing Gotchas and Fixture-and-Test-Data-Patterns sections are the closest fit; no dedicated shell/scenario-testing skill exists in this ecosystem, and four recurring, non-obvious gotchas from one task already exceeds the "≥3 usage scenarios" skill-qualification bar for a reference addition (short of justifying a wholly new skill).
- **Estimated scope**: SKILL.md addition or new `references/scenario-fixture-gotchas.md`, ~30-40 lines
- **Overlap check**: `skills/testing-strategy/SKILL.md` Gotchas + Fixture and Test Data Patterns sections exist; no current coverage of git-hook-suppression, bare-repo symref, or shared-fixture staleness. None conflicting.
- **Recommended delegation**: context-engineer (review scope — SKILL.md body vs new reference file) then implementer (content)
- **Suggested artifact path**: `skills/testing-strategy/SKILL.md` or `skills/testing-strategy/references/scenario-fixture-gotchas.md`

### Proposal 6: testing-strategy — "a row that cannot fail is noise" heuristic

- **Disposition**: pending
- **Type**: skill (update)
- **Maturity**: sapling
- **Scope**: medium
- **Priority**: P1 (next-cycle)
- **Source(s)**: `.ai-work/sidecar-placement/LEARNINGS.md` line ~2647 ("A row that cannot fail is noise — the `hooks-chained` lesson"), Batch-21 § 2 (`gather()`/`status` split rationale)
- **Description**: A named heuristic for `testing-strategy`'s Coverage Philosophy or Gotchas section: when a design change makes a previously-accurate artifact (a health-check line, a PASS/status text, a docstring rationale, a design-doc claim) stale, the correct fix is a test the artifact lacked, not another review pass — because every stale-after-a-design-change artifact observed in this task shared exactly that shape (the `doctor` `placement` row design, the `mount-conflict` reason string, the `state-eligible` row all needed an assertion added, not more scrutiny of prose).
- **Rationale**: Declarative and recurring within a single task (≥3 independent instances cited above), and cuts against a natural but wrong instinct (re-reading the stale claim harder instead of adding the missing assertion) — exactly the kind of default-reasoning-breaking gotcha this skill's Gotchas section exists to hold.
- **Estimated scope**: SKILL.md addition, ~4-5 lines
- **Overlap check**: `skills/testing-strategy/SKILL.md` § Coverage Philosophy exists; no current heuristic phrased this way. None conflicting.
- **Recommended delegation**: context-engineer
- **Suggested artifact path**: `skills/testing-strategy/SKILL.md` (Coverage Philosophy or Gotchas section)

## Recommended Delegations

| Proposal | Delegation Path | Notes |
|---|---|---|
| 1 | context-engineer (review) then implementer or direct edit | Docs catalog addition; validate placement/token impact is negligible (docs/, not always-loaded) |
| 2 | context-engineer | Skill update; load `skill-crafting` for the Gotchas-section pattern |
| 3 | context-engineer | Skill update; extends an existing Detection-sweep step |
| 4 | context-engineer | Skill reference update; deliberately routed away from the budget-constrained always-loaded rule |
| 5 | context-engineer (review scope) then implementer (content) | Decide SKILL.md-inline vs new reference file before drafting |
| 6 | context-engineer | Skill update; short, single-heuristic addition |

## Disposition Log

<!-- Populated by /skill-genesis-review. Empty on report creation. -->

| Timestamp | Proposal | Disposition | Notes |
|---|---|---|---|
| _(empty — pending review)_ | | | |

## Recommended Next Steps

- Run `/skill-genesis-review` to disposition the 6 pending proposals.
- After approval, invoke `context-engineer` for the docs/skill updates; the agent will pick up the recommended delegations table.
- Before any always-loaded rule edit in this area, re-run `scripts/measure_token_budget.py` — the budget is already at 24,574/25,000 tokens per this task's own working context.
- Re-run `/skill-genesis` after `.ai-work/sidecar-placement/` accumulates further LEARNINGS.md content (VERIFICATION_REPORT_P0.md and AUDIT_PHILOSOPHY.md were skimmed but yielded no items beyond what Batch 21 already folded — a future pass on a later checkpoint of this same task may still surface new material if the pipeline continues).
