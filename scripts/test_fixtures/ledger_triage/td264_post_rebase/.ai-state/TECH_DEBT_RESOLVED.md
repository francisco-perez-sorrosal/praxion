# Resolved Tech Debt

<!-- Sibling of TECH_DEBT_LEDGER.md holding rows with terminal status (resolved / wontfix).
     Rows arrive via scripts/finalize_tech_debt_ledger.py migration when status transitions
     to a terminal value. Schema, lifecycle, and re-open semantics are defined canonically
     in skills/software-planning/references/tech-debt-ledger.md § Schema. Do not duplicate
     the schema here — the skill reference is the single source of truth (F-12). -->

**Schema**: 14 row fields + 1 structural `dedup_key`. See [`skills/software-planning/references/tech-debt-ledger.md`](../skills/software-planning/references/tech-debt-ledger.md) § Schema for field definitions.

**Rows arrive here automatically** when status transitions to `resolved` or `wontfix`. The pair forms one logical namespace with `TECH_DEBT_LEDGER.md`: `id` and `dedup_key` are unique across both files. Cross-file `dedup_key` matches trigger re-open (the historical resolved row moves back to LEDGER).

| id | severity | class | direction | location | goal-ref-type | goal-ref-value | source | first-seen | last-seen | owner-role | status | resolved-by | notes | dedup_key |
|----|----------|-------|-----------|----------|---------------|----------------|--------|------------|-----------|-----------|--------|-------------|-------|-----------|
