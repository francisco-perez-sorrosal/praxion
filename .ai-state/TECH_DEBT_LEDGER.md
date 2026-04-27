# Technical Debt Ledger

<!-- Living, append-only ledger of grounded debt findings.
     Producers: verifier (per-change Phase 5/5.5), sentinel (repo-wide TD dimension).
     Consumers: systems-architect, implementation-planner, implementer, test-engineer, doc-engineer.
     Schema, owner-role heuristic, worktree-merge dedupe semantics, and lifecycle conventions
     are defined canonically in rules/swe/agent-intermediate-documents.md § TECH_DEBT_LEDGER.md.
     Do not duplicate the schema here — the rule is the single source of truth. -->

**Schema**: 14 row fields + 1 structural `dedup_key`. See [`rules/swe/agent-intermediate-documents.md`](../rules/swe/agent-intermediate-documents.md) § `TECH_DEBT_LEDGER.md` for field definitions, enum values, the owner-role heuristic, and the post-merge dedupe contract.

**Append new rows at the end of the table.** Consumers update `status`, `resolved-by`, and `last-seen` in place. Rows are never deleted.

| id | severity | class | direction | location | goal-ref-type | goal-ref-value | source | first-seen | last-seen | owner-role | status | resolved-by | notes | dedup_key |
|----|----------|-------|-----------|----------|---------------|----------------|--------|------------|-----------|-----------|--------|-------------|-------|-----------|
| td-001 | important | duplication | code-to-goals | commands/onboard-project.md, commands/new-project.md | code-quality |  | verifier | 2026-04-27 | 2026-04-27 | implementation-planner | resolved | 72d6db7 | Four canonical blocks (Agent Pipeline, Compaction Guidance, Behavioral Contract, Praxion Process) duplicated byte-identically across both onboarding commands; mirror discipline enforced by author + regex test, not by extraction. Proper fix: extract canonical blocks to a single source-of-truth (e.g., `claude/canonical-blocks/<name>.md`) consumed by both commands. User flagged during Step 11; refactor must cover all four blocks together to avoid mixed-state. Resolved by extracting to `claude/canonical-blocks/<slug>.md` with `scripts/sync_canonical_blocks.py` enforcing byte-identicality via pre-commit hook (build-time compilation per dec-draft-26a0b592). | 83fa92c1f787 |
| td-002 | important | other | code-to-goals | claude/canonical-blocks/agent-pipeline.md | code-quality |  | orchestrator | 2026-04-27 | 2026-04-27 | implementation-planner | open |  | Agent-pipeline canonical block is ~1818 bytes (~505 tokens), exceeding per-block ~250-token budget by ~2x; pre-existing condition surfaced during td-001 refactor, not introduced by it. Trimming changes downstream injection contract — needs content review and separate ADR. Currently xfailed in `hooks/test_onboard_praxion_block.py::test_block_stays_within_token_budget[agent-pipeline]`. Filed by orchestrator mid-pipeline (slight protocol stretch — canonical sources are verifier and sentinel); verifier may re-source. Class `other` because no enum slot covers content-size-budget violations. | deee2e5a8b62 |
