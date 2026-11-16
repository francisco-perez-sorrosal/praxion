---
schema_version: 1
report_id: skill-genesis-2026-11-15_17-12-36
generated_at: 2026-11-15T17:12:36
task_slug: skill-genesis-2026-11-15
agent_version: skill-genesis@unknown
invocation_args: { since: null, scope: null, sources: .ai-work/_harvest, batch: "9 of 11", dry_run: false }
review_status: pending
disposition_count: { pending: 4, approved: 0, rejected: 0, refined: 0, deferred: 0 }
---

# Skill Genesis Report — 2026-11-15 17:12:36

## Summary

2 queue sources analyzed (`wal-slug-attribution`, `process-economy-p0-7-live`), 26 items extracted, 4 proposals generated (all pending), 22 deduplicated or skipped. Most lessons were already carried by artifacts, by the eight earlier reports of this run, or are specific to one feature. Review status: pending.

## Learning Sources Consumed

| Source | Path | Items Extracted | Status |
|---|---|---|---|
| Queue source 1: LEARNINGS.md + LEARNINGS_s7_s8.md | `.ai-work/_harvest/wal-slug-attribution/` | 11 | Read |
| Queue source 1: VERIFICATION_REPORT.md | `.ai-work/_harvest/wal-slug-attribution/VERIFICATION_REPORT.md` | 4 | Read |
| Queue source 2: LEARNINGS.md | `.ai-work/_harvest/process-economy-p0-7-live/LEARNINGS.md` | 6 | Read |
| Queue source 2: VERIFICATION_REPORT.md (3 passes) | `.ai-work/_harvest/process-economy-p0-7-live/VERIFICATION_REPORT.md` | 5 | Read |
| CONSULT_*.md fragments | both sources | 0 | Not found |
| Sentinel / idea ledger / ADR index / calibration log | n/a | 0 | Not read: queue-mode batch, scope limited to listed sources |
| Earlier reports of this run | `SKILL_GENESIS_REPORT_2026-11-15_*.md` (8) | n/a | Read (titles and triage tables) for dedup |

## Triage Results

| # | Item | Source | Decision | Rationale |
|---|---|---|---|---|
| 1 | `SubagentStart` carries no prompt; the join to a spawn's prompt is `PostToolUse(Agent).tool_response.agentId`; resume re-fires `SubagentStart`; order foreground vs resume | wal-slug LEARNINGS Verified Facts | Skill (update) | Searched `skills/hook-crafting/references/event-reference.md` (lists fields only, no join), `docs/observability.md`: not carried. Proposal 1 |
| 2 | Hooks must parse on 3.9 while the suite needs 3.11+; add `ast.parse(feature_version=(3,9))` to exit checks | wal-slug LEARNINGS planning gotchas | Skill (update) | `grep feature_version` over skills/rules/scripts/docs: none. Proposal 2 |
| 3 | A new unit test with the same basename as a read-only outer-loop test fails collection (rootdir-style imports, no `__init__.py`) | wal-slug LEARNINGS Step 1-2 | Skill (update) | `grep` for basename-collision wording in `skills/testing-strategy`: none. Folded into Proposal 3 |
| 4 | `seen["stdin"] == ""` assertion vacuous under pytest fd capture (mutant survives); a test wrote a scratch dir inside the repo | process-economy VERIFICATION warn-13, LEARNINGS | Skill (update) | `rules/swe/testing-conventions.md:76` covers `tmp_path` generally; the vacuous-capture case is not carried. Folded into Proposal 3 |
| 5 | Paid-runner pitfalls: a variant loop reusing per-task names collides, only an end-to-end run with a fake binary on `PATH` reaches it (`--dry-run` cannot) | process-economy VERIFICATION fail-1 | Skill (update) | `grep 'fake.?claude'` over skills/rules/docs: none; `skills/eval-praxion/SKILL.md:129-164` carries isolation, canary guard, spend cap, not this. Proposal 4 |
| 6 | `lowered` computed from pooled rates with no per-case guard | VERIFICATION fail-2 | Skip | Present: `skills/eval-praxion/SKILL.md:149-152` |
| 7 | `--max-budget-usd` is checked after a turn (a $0.01 cap cost $0.10); invalid credential returns `success` with `is_error: true`; `--add-dir` grants read AND edit | LEARNINGS Recording Checkpoint, fail-4 | Skill (update) | `grep` finds none in `skills/`, `eval/EVAL_PLAN.md`. Folded into Proposal 4 |
| 8 | A breach detector tested only on synthetic inputs misfired on 3 of 4 recorded envelopes (`/dev/null`, JSX `</ul>`, unresolved `/var` vs `/private/var`); run each detector over the committed verbatim clean envelopes | VERIFICATION refail-1 | Skill (update) | Not carried (no `verbatim` wording in agent-evals/testing-strategy). Folded into Proposal 4 |
| 9 | Committed fixtures carry the owner's local username; credential scan alone is not enough | VERIFICATION Security Review | Skill (update) | Folded into Proposal 4 |
| 10 | Never unpair the step that owns an external side effect (spawn-budget carve-out) | LEARNINGS orchestrator calibration | Skip | Present: `skills/software-planning/references/coordination-details.md:305` |
| 11 | Mutation sensor refuses `not-flat-layout`; script reaching `hooks/` via `SCRIPT_DIR.parent` fails in the sensor copy | wal-slug LEARNINGS | Skip | Already proposed in earlier reports ("Check that the sensor can reach a target...", "Tests written for the mutation sensor load the module by its real name") |
| 12 | Equivalent survivors (`encoding="UTF-8"`, `.get` defaults) | wal-slug LEARNINGS s7_s8 | Skip | Already proposed (earlier "Survivor triage" proposal) |
| 13 | Test named "joined by a line break" cannot distinguish a line break from a space | wal-slug VERIFICATION W2 | Skip | Already proposed ("A test can only claim what its harness can observe") |
| 14 | Source-text pin (`inspect.getsource`) stands in for behaviour; fake echoes any marker so the file cannot be pinned | process-economy rewarn-2 | Skip | Same class as 13; no separate proposal |
| 15 | Registry, writer-truth scenario and emitter land in one step | wal-slug planning gotcha | Skip | Already proposed ("A registration step reddens the registry-against-detector drift test") |
| 16 | Function-level ownership of outer-loop nodes checked by script; measure the baseline before planning | wal-slug planning | Skip | Baseline capture present at `agents/implementation-planner.md:244`; ownership script is feature-specific |
| 17 | Two steps sharing files cannot be committed apart after one spawn; commit then resume the same implementer | wal-slug planning | Skip | Present in substance: `coordination-details.md` spawn/resume rules and the "Disjoint files are not disjoint runtime" earlier proposal |
| 18 | Verifier's read-only `git log` with "commit" in the description tripped `commit_gate.sh` (matches the whole Bash payload) | wal-slug VERIFICATION scope | Skip | A gate defect, not a lesson: belongs in the tech-debt ledger (verifier writes it), not an artifact |
| 19 | Stale ADR drafts vs shipped behaviour (summary says "incrementally") | process-economy warn-8 | Skip | Same class as the earlier "A late Spec Question updates the records that restate the changed rule" |
| 20 | Real-log differential, base vs HEAD script, 45 cases 0 differences | wal-slug VERIFICATION | Skip | Technique, single instance, no generalisation beyond one change; seedling only |
| 21 | Design decisions (locate(), TOOL_AGENT_SPAWN, sandbox HOME, nonce preflight, SpendLedger, report.py split) | both LEARNINGS | Skip | Feature decisions already in the ADR drafts |
| 22 | Pre-existing red baseline (dec-040 tests red 3.5 weeks; CI red since 2026-08-07); ambient `python3` lacks PyYAML | process-economy LEARNINGS | Skip | Ledgered (td-243..246) |
| 23 | Worktree Bash guard refuses the word "eval" | process-economy LEARNINGS | Skip | Single environment quirk, ledger material |
| 24 | traceability.yml bookkeeping, TEST_RESULTS Result lines | VERIFICATION fail-5, warn-14 | Skip | Ephemeral pipeline artifacts |
| 25 | Calibration (`correct` / `under-calibrated`) | both VERIFICATION | Skip | Enum plus evidence, already in calibration log |
| 26 | Env allowlist silently dropped the fake binary's control variables | process-economy LEARNINGS | Skip | Narrow; covered by Proposal 4's fake-binary text if accepted |

## Discipline-Gap Signals

None recorded.

## Proposals

### Proposal 1: Hook-crafting event reference: tie a subagent spawn's prompt to its agent id

- **Disposition**: pending
- **Type**: skill (update)
- **Maturity**: mature
- **Scope**: narrow
- **Priority**: P1 (next-cycle)
- **Source(s)**: wal-slug-attribution LEARNINGS "Verified Facts" (docs fetched 2026-09-30, live probe on Claude Code 2.1.285, 400 transcripts, ~1,370 `Agent` results)
- **Description**: Add to `event-reference.md` a short "Correlating a spawn with its prompt" block: `SubagentStart` carries only `agent_id`/`agent_type` (plus common fields); the prompt is on `PreToolUse(Agent).tool_input.prompt` and `PostToolUse(Agent).tool_response.{agentId,prompt}`; `agentId` equals the `SubagentStart` `agent_id`; `tool_use_id` links Pre to Post but not to Start; a resume (`SendMessage`) fires `SubagentStart` again for the same id; `prompt_id` is per user prompt, not per spawn. Mark with `last-verified` since it is a drift-prone external fact.
- **Rationale**: The line at `event-reference.md:98` lists the fields but not the join, and an attribution design built on a guess (order-based pairing) was the rejected alternative. Verified against docs and a live probe, so it saves the next hook author the same probe.
- **Estimated scope**: one section in an existing reference, plus a `staleness_sensitive_sections` entry
- **Overlap check**: `skills/hook-crafting/references/event-reference.md` (fields table only); `docs/observability.md` (mentions `agent_transcript_path` only).
- **Recommended delegation**: context-engineer then implementer
- **Suggested artifact path**: `skills/hook-crafting/references/event-reference.md`

### Proposal 2: Hook steps check the oldest supported interpreter, not the suite's

- **Disposition**: pending
- **Type**: skill (update)
- **Maturity**: sapling
- **Scope**: narrow
- **Priority**: P2 (someday)
- **Source(s)**: wal-slug-attribution LEARNINGS "Gotchas (planning phase)" ("pytest on 3.11+ cannot see 3.9 breakage in the hooks"); VERIFICATION Scope (`ast.parse(feature_version=(3, 9))` on 9 hooks)
- **Description**: One gotcha in `hook-crafting`: hooks run under the operator's `python3`, which may be older than the suite's required 3.11, so a green suite proves nothing about hook syntax; add `ast.parse(source, feature_version=(3, 9))` per changed hook to the step's exit checks.
- **Rationale**: Zero hits for `feature_version` across skills, rules, scripts and docs, while the planner added it to every hook step by hand. The 3.9 floor itself is not stated in a shipped artifact, so confirm it before writing (assumption: the floor is the macOS system interpreter).
- **Estimated scope**: one gotcha entry in SKILL.md or a hook-safety reference
- **Overlap check**: none (`CLAUDE.md:20` states the suite floor 3.11 only).
- **Recommended delegation**: context-engineer
- **Suggested artifact path**: `skills/hook-crafting/SKILL.md` (gotchas)

### Proposal 3: Pytest traps: basename collision, vacuous capture assertion, scratch dirs in the repo

- **Disposition**: pending
- **Type**: skill (update)
- **Maturity**: sapling
- **Scope**: narrow
- **Priority**: P2 (someday)
- **Source(s)**: wal-slug LEARNINGS "Step 1-2 Learnings" (basename collision, "import file mismatch"); process-economy VERIFICATION warn-13 (`stdin` pin vacuous), LEARNINGS (test wrote `eval/tests/_plant_nonces_scratch/`)
- **Description**: Three entries in `python-testing.md`: (1) with rootdir-style imports and no `__init__.py`, two test files with the same basename fail collection, so pick a unique name when a read-only outer-loop file shares it; (2) an assertion that stdin is empty/null passes vacuously, because pytest's default fd capture already points fd 0 at `/dev/null`: prove it with a mutant or a subprocess; (3) a test that writes scratch inside the repo leaves an untracked dir when killed: use `tmp_path`.
- **Rationale**: Each cost an implementer or verifier a diagnosis cycle; none is carried (`testing-conventions.md:76` only says use temp mechanisms). Three scenarios make it a coherent gotcha list, though each is small, hence P2.
- **Estimated scope**: a short "Traps" section in one reference
- **Overlap check**: `rules/swe/testing-conventions.md` (tmp_path, partial); earlier reports' "Tests written for the mutation sensor load the module by its real name" (different).
- **Recommended delegation**: context-engineer then implementer
- **Suggested artifact path**: `skills/testing-strategy/references/python-testing.md`

### Proposal 4: Live-session runners: test with a fake binary and fix the CLI facts they rest on

- **Disposition**: pending
- **Type**: skill (update)
- **Maturity**: mature
- **Scope**: medium
- **Priority**: P1 (next-cycle)
- **Source(s)**: process-economy-p0-7-live VERIFICATION (#fail-1, #fail-4, #refail-1, Security Review, Candidate pattern in "Merge to LEARNINGS.md"); LEARNINGS "Recording Checkpoint" and "Coordinator fidelity addendum"
- **Description**: New reference `live-session-runners.md` for any harness that spawns paid `claude -p` sessions: (a) test the whole run loop against a stand-in `claude` on `PATH` driven by a control file; it costs nothing and is the only way to reach loops that `--dry-run` skips (a per-variant loop reusing a per-task directory name crashed every canary run after paying for the head variant); (b) CLI facts: `--max-budget-usd` is checked after a turn, so charge actual cost and never treat the budget as an upper bound; an invalid credential returns subtype `success` with `is_error: true`; `--add-dir` grants edit as well as read, so make the shared copy read-only and re-check its digest; (c) a breach or error detector is run over the committed verbatim clean envelopes before shipping (synthetic inputs let `/dev/null`, JSX closing tags and the `/var` vs `/private/var` spelling through as false breaches); (d) committed envelopes are scanned for local usernames and paths as well as credentials.
- **Rationale**: Each point produced a FAIL-grade finding in a paid-path feature, and the live-runner section of `eval-praxion` states the policy but none of these. The skill is generic over any session-spawning harness, so it belongs in `agent-evals`; `eval-praxion` would link to it.
- **Estimated scope**: SKILL.md pointer + 1 reference (~80 lines), one link added in `skills/eval-praxion/SKILL.md`
- **Overlap check**: `skills/eval-praxion/SKILL.md:129-164` (isolation preflight, canary per-case guard, spend cap: not re-proposed); `skills/agent-evals/references/simulation-testing.md` (conversational simulation, different).
- **Recommended delegation**: context-engineer then implementer
- **Suggested artifact path**: `skills/agent-evals/references/live-session-runners.md`

## Recommended Delegations

| Proposal | Delegation Path | Notes |
|---|---|---|
| 1 | context-engineer then implementer | Add `last-verified` marker and cataloged section per `staleness-policy.md` |
| 2 | context-engineer | Confirm the 3.9 floor first |
| 3 | context-engineer then implementer | Load `skill-crafting`; keep as a short traps list |
| 4 | context-engineer then implementer | Load `skill-crafting`; link from `eval-praxion` |

## Disposition Log

<!-- Populated by /skill-genesis-review. Empty on report creation. -->

| Timestamp | Proposal | Disposition | Notes |
|---|---|---|---|
| _(empty — pending review)_ | | | |

## Recommended Next Steps

- Run `/skill-genesis-review` to disposition the 4 pending proposals.
- After approval, invoke `context-engineer` for the skill updates.
- Item 18 (commit gate matches the whole Bash payload) is a defect for the tech-debt ledger, not a proposal.
