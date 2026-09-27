# Technical Debt Ledger

<!-- Living, append-only ledger of grounded debt findings.
     Producers: verifier (per-change Phase 5/5.5), sentinel (repo-wide TD dimension).
     Consumers: systems-architect, implementation-planner, implementer, test-engineer, doc-engineer.
     Schema, owner-role heuristic, worktree-merge dedupe semantics, and lifecycle conventions
     are defined canonically in skills/software-planning/references/tech-debt-ledger.md
     (rules/swe/agent-intermediate-documents.md retains a 5-line summary + pointer).
     Do not duplicate the schema here — the skill reference is the single source of truth. -->

**Schema**: 14 row fields + 1 structural `dedup_key`. See [`skills/software-planning/references/tech-debt-ledger.md`](../skills/software-planning/references/tech-debt-ledger.md) § `TECH_DEBT_LEDGER.md` for field definitions, enum values, the owner-role heuristic, and the post-merge dedupe contract.

**Append new rows at the end of this active ledger.** Consumers update `status`, `resolved-by`, and `last-seen` in place; when status transitions to `resolved` or `wontfix`, the row migrates to the sibling [`TECH_DEBT_RESOLVED.md`](TECH_DEBT_RESOLVED.md) (cut + paste, in-commit or via `scripts/finalize_tech_debt_ledger.py`). The pair forms one logical namespace — see the rule for re-open semantics.

| id | severity | class | direction | location | goal-ref-type | goal-ref-value | source | first-seen | last-seen | owner-role | status | resolved-by | notes | dedup_key |
|----|----------|-------|-----------|----------|---------------|----------------|--------|------------|-----------|-----------|--------|-------------|-------|-----------|
| td-264 | suggested | other | code-to-goals | hooks/remind_calibration.py | code-quality |  | orchestrator | 2026-09-25 | 2026-09-27 | implementer | open |  | [orchestrator, process-economy-d] The commit-time calibration check has two remaining blind spots: it needs two landed commits since the newest row, and at PreToolUse the pending commit has not landed, so a session's first commit never counts; and its subject matcher uses startswith on bare types, missing scoped subjects such as fix(scripts): (about 40 percent of task commits since 2026-09-20). // [orchestrator, low-hanging batch 2026-09-27] Part fixed by 4b9e8462: the subject matcher now accepts scoped and breaking forms (type(scope)!:) and excludes chore(state) bookkeeping; the calibration reminder imports the exclusion list instead of copying it. Still open: a session's first commit is never counted at PreToolUse (the pending commit has not landed), which needs a design decision. | 898240af0a2e |
| td-257 | important | other | code-to-goals | hooks/remind_calibration.py | code-quality |  | orchestrator | 2026-09-25 | 2026-09-25 | systems-architect | open |  | [orchestrator, process-economy-d] The Stop-time calibration reminder learns that a session edited files only from tool_use rows in .ai-state/observations.jsonl, so it is inert wherever that log is absent or observability is disabled (fresh checkout before any tool call, opted-out projects, the live eval sandbox). Candidate: qualify from the Stop payload's transcript_path instead (verifier probe: 18 ms over a 4.2 MB transcript), which also removes the once-per-session marker. Trade-off to design first: it couples the hook to Claude Code's transcript format. Declared as a limit in the per-tier envelope ADR. | 687ceec89907 |
