---
id: dec-draft-76021526
title: The flip gate takes a cited run's standing from its results files, keeps the run index as locator and digest only, and states what it still trusts
status: proposed
category: architectural
date: 2026-10-20
summary: "Narrows dec-461 clause 2. The gate parses a cited run's results files with the stdlib (new scripts/kernel_run_evidence.py): it derives the lineage from the files' continues links and counts complete pairs itself; it takes flip standing and scored checks from what the files record (a new per-role standing key written at finalize and close, or the legacy one-part verdict), refuses a run with no recorded whole-lineage standing, refuses any index or record figure that disagrees, and refuses a passing run that did not score the role's convention check. The index (schema 2, gaining scored_checks) only locates files and carries digests. The gate does not recompute the eval's statistics and trusts them, and the files' contents, as stated here and in docs/lean-spawn-how-to.md."
tags: [kernels, adoption-ledger, flip-gate, eval, adherence, run-index, trust-boundary, td-473, td-468]
made_by: agent
agent_type: systems-architect
branch: worktree-loop-gate-hardening
pipeline_tier: standard
affected_files:
  - scripts/kernel_run_evidence.py
  - scripts/kernel_run_index.py
  - scripts/kernel_ledger_checks.py
  - eval/src/praxion_evals/adherence/results.py
  - eval/src/praxion_evals/adherence/run_index.py
  - eval/src/praxion_evals/adherence/model.py
  - .ai-state/eval_ledger/adherence/index.json
  - docs/lean-spawn-how-to.md
affected_reqs: [REQ-12, REQ-13, REQ-14, REQ-15, REQ-16, REQ-17]
supersedes: null
superseded_by: null
re_affirms: null
re_affirmed_by: null
retired_by: null
supersedes_in_part: dec-461
superseded_in_part_by: null
dissent: null
---

## Context

dec-461 made the gate resolve every run a switched record cites through a digest-checked run index, and take each run's complete pairs and flip label from the index. The digests prove only that the index and the files agree on bytes, not that the index's standing agrees with the files, so a hand-edited index with intact digests and a forged label passes a switched record its results do not support (td-473). Separately, the index does not say which checks a run scored, so a run that never scored the role's project-convention check can still be switched (td-468). The gate must stay stdlib-only and offline; the eval's flip verdict is statistics over a whole lineage (dec-462) that only the eval computes.

Activation: fired — honest uncertainty (the brief rates the recomputation 6/10) on a security-relevant gate; the Dialectical Inquiry below argues the runner-up.

## Decision

1. **What the gate derives itself** (new `scripts/kernel_run_evidence.py`, stdlib): a cited run's lineage, from the results files' own `continues` links; the role's complete pairs, from the sessions the lineage's files record (per task, the latest session per arm across the parts, counted when both were measured, the eval's own pairing rule restated and pinned by a parity test); a closed ending, from the tip's recorded ending.
2. **What it cross-checks against recorded fields:** the flip standing and scored checks the tip file records for the whole lineage (a new top-level `standing` key the eval writes at finalize and close: lineage root, parts, complete pairs, flip label, scored checks), or, for a one-part file written before this change, the role's verdict it records (its flip label, else underpowered; its per-check verdicts not listed as not covered). It refuses: a run whose whole-lineage standing no file records; an index or record whose lineage, pairs, label or pass flag disagrees with the derived or recorded values; a recorded count that disagrees with its own sessions; a passing run not clear on 20 counted pairs; a passing run whose scored checks lack the role's convention check. Each refusal is its own finding kind with a canary.
3. **The index's role:** a locator and digest list (schema 2, now also carrying `scored_checks`). Its standing fields are redundant summaries that must agree; they are never the source of a verdict.
4. **What the gate still trusts, stated:** the per-check verdicts, allowances, intervals and flip label the eval computed (re-computing them would be a second implementation of dec-462's statistics); which checks a verdict covers; and the contents of a results file as such, so a results file rewritten together with its digest in the index is undetectable by the gate. The backstop for that trust is the two human ratifications every switched record carries (`flip_rule_ratified`, `flip_ratified`) and review of the commit that adds a results file. `docs/lean-spawn-how-to.md` states the same.

## Considered Options

### Derive what is countable, cross-check what is recorded, state the rest (chosen)

Pros: closes the index-only forgery; no second statistics implementation; the trust left is named. Cons: an additive results key, an index schema bump, and a restated pairing rule held equal by a parity test.

### Re-compute the flip verdict in the stdlib gate

Pros: no trust in recorded labels. Cons: duplicates dec-462's exact quantiles, coverage and judged-check rules in a second interpreter floor; two sources of truth that must move together on every flip-rule amendment.

### Keep the index as the source and document the limit

Pros: no code. Cons: leaves td-473's forgery open; the limit would be a gap, not a boundary.

### The gate shells out to the eval package

Pros: one implementation. Cons: rejected in dec-461 for the same reason: the gate must run offline under a bare `python3`.

## Consequences

- Positive: a switched record can rest only on standing its own results files record, with pairs the gate counted; an unscored convention check blocks a flip, so a lean role's project instructions are proven to reach it before it switches.
- Negative: the index must be regenerated (`--reindex`) in the commit that lands schema 2; a continued lineage whose tip predates the `standing` key can never be cited (none exists).
- The eval's flip verdict stays trusted as recorded; a coordinated rewrite of a results file and its digest is caught only by the ratifications and review.

## Disconfirmation

- **Falsifier:** a hand-edited index with intact digests that raises a run's pairs, regroups its lineage or relabels it clear, and passes; or a switched record whose passing run lacks a scored convention check, and passes; or the gate's pair count differing from the eval's on any committed results file.
- **Steelmanned runner-up (Dialectical Inquiry):** re-computing the verdict is the only way to remove trust in the eval's own output, and the statistics are a few hundred lines of exact binomial quantiles that the stdlib can express; a gate that trusts a recorded "clear" still lets a forged results file through, which is exactly the class td-473 is about. It loses here because a forged results file requires rewriting evidence that is reviewed when committed and re-ratified by a human at the flip, while a second implementation of the flip rule would have to change in lockstep with every amendment of dec-462 and would itself become the most likely source of a wrong verdict.
- **Reversal trigger:** a flip whose recorded standing is later found inconsistent with its sessions, or a decision to remove the human ratifications from the switched record; either makes re-computation (or a signed results file) worth its cost.

## Prior Decision

dec-461 (partially superseded) decided that the gate resolves cited runs through the run index and checks role, complete pairs, the pass flag against the flip label, and the passing run's 20 pairs and clear verdict, all from the index's recorded values. What changes: the source of those values (the results files, derived or recorded), the index's role (locator and digest only, schema 2 with scored checks), and two new refusals (unrecorded standing, unscored convention check). The eligibility pin, the parent-commit read, the stale-index check and the implementer's eligibility stand, so the supersession is partial. dec-462's lineage unit (a continued run is one run) is relied on unchanged.
