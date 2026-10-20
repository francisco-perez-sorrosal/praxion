---
id: dec-draft-42f62347
title: The flip gate holds the eligible roles in its own module and reads run evidence from a digest-checked run index; the implementer becomes eligible
status: accepted
category: architectural
date: 2026-10-17
summary: "Moves the eligible-roles pin out of the adoption ledger, which a flip commit writes, into a gate-owned module, scripts/kernel_eligibility.py, read at the parent commit. A commit that changes eligibility may change no adoption record and no flag. Adds the implementer to the five pilot roles (its trial record lands later, with its run). Adds a run index beside the adherence results, written by the runner and digest-checked by the gate, through which the gate resolves every run a switched record cites. Amends dec-460's clause 5 ('switched only for the five eligible pilot roles')."
tags: [kernels, adoption-ledger, flip-gate, lean-spawns, eval, adherence, gate-liveness, startup-context-diet]
made_by: agent
agent_type: systems-architect
branch: worktree-lean-spawn-continuation
pipeline_tier: full
affected_files:
  - scripts/kernel_eligibility.py
  - scripts/kernel_ledger.py
  - scripts/kernel_ledger_checks.py
  - scripts/check_kernel_manifest.py
  - .ai-state/kernel_adoption.yaml
  - eval/src/praxion_evals/adherence/run_index.py
  - .ai-state/eval_ledger/adherence/index.json
affected_reqs: [REQ-09, REQ-13, REQ-14]
supersedes: null
superseded_by: null
re_affirms: null
re_affirmed_by: null
retired_by: null
supersedes_in_part: dec-460
superseded_in_part_by: null
dissent: null
---

## Context

dec-460 made the adoption ledger hold both the eligible roles and each role's flip record, and the gate kept a second copy of the list as a constant that the ledger had to equal. A flip commit edits the ledger, so a single commit could widen eligibility and flip in the same change by editing both copies (td-435). The gate also never resolved a switched record's cited runs to their results (td-436). It cannot do so directly: verdicts are computed from session records by the eval package, which runs on another interpreter floor, and the gate must stay stdlib-only and offline. The implementer, the most-spawned role, has a full task kit and is to become eligible. Its trial record lands with its paid run (orchestrator decision, SQ-07 (b)), because a trial ships its kernel cost to every managed project.

Activation: no -- the pin's home followed the user's preference for the simplest home a flip commit never writes; the evidence path was the only option that keeps the gate offline without rewriting recorded results.

## Decision

1. **Eligibility moves to the gate.** The eligible roles live only in `scripts/kernel_eligibility.py`, a literal tuple: the five pilot roles plus the implementer. The adoption ledger's `eligible` key is removed in a migration commit that changes no role's eligibility, and the gate refuses it if it reappears. The gate reads the set at the parent commit from that module's HEAD blob (by `ast.literal_eval`, never by import). When the module is absent at the parent, it reads the parent ledger's list. A commit that changes the set and also changes any adoption record or any definition's `omitClaudeMd` is refused, so a move to switched is always judged against an eligible set its own commit did not change. The spawn hook does not read eligibility, so delivery is unchanged.
2. **Run evidence through an index.** The adherence runner writes `.ai-state/eval_ledger/adherence/index.json` at finalize and on `--reindex`. Per results file, the index records its sha256, lineage root, ending, and each role's complete pairs, flip label and identity; a continued run gets lineage-level figures, and a closed run's label is not clear. For every switched record, the gate refuses an index whose digests or file set disagree with the directory. It then resolves each cited run (`passing_run` included) to its lineage, and checks role, complete pairs, the pass flag against the flip label, and the passing run's 20 pairs and clear verdict.
3. **The implementer is eligible.** It gets no adoption status in this change.

## Considered Options

### Pin: a literal in a gate-owned module (chosen)

Pros: a flip commit never writes it; one source; the gate already held a copy. Cons: reading the parent's value needs a git blob read and a literal parse.

### Pin: a separate data file under `.ai-state/`

Pros: data, not code. Cons: a second ledger-like file next to the one a flip edits; it adds a reader and a schema for one list.

### Pin: keep the ledger's list and forbid it changing beside a move

Pros: no move. Cons: the gate's equality constant stays a duplicate; td-435 asks for the pin where a flip commit does not write.

### Evidence: the gate shells out to the eval package

Pros: no derived artifact. Cons: it breaks the gate's stdlib, offline and interpreter-floor contract; a gate that needs `uv` and a 3.13 environment does not run everywhere it guards.

### Evidence: write per-role summaries into each results file

Pros: no new file. Cons: it rewrites the eight recorded results files, and evidence must not be edited after the fact.

## Consequences

- Positive: eligibility is widened only by a reviewable commit of its own. A switched record cannot rest on a missing, foreign, mis-counted or non-passing run. The gate stays stdlib-only and offline.
- Negative: a derived index whose freshness must itself be gated (`I9-run-index-stale`, with canaries). A results file added without `--reindex` blocks the next commit that holds a switched record until the index is regenerated.
- The implementer's trial, its liveness spawn and its startup reading belong to the run-preparation commit after the merge.

## Disconfirmation

- **Falsifier:** a commit that both widens eligibility and moves a role to switched passes the gate; or a switched record whose passing run's results file was edited after indexing passes; or the parent-blob read misreports the eligible set on a real history.
- **Steelmanned runner-up:** keeping the list in the ledger with only a same-commit separation check is the smaller diff and keeps all adoption facts in one file. It loses because the gate's duplicate constant would stay a second source, and because td-435's defect is that the file a flip writes holds the pin.
- **Reversal trigger:** if managed projects come to need per-project eligibility, the pin moves back to a data file that the hook or an overlay reads. The same applies if the run index proves a recurring source of blocked commits (more than one stale-index refusal per paid run).

## Prior Decision

dec-460 (partially superseded) placed the eligible roles in the adoption ledger and limited a switch to the five pilot roles. What changes: the list's home (from the ledger to a gate-owned module), its membership (plus the implementer), and the gate's evidence check (cited runs resolved through an index). The kernel manifest, the generator, the spawn hook, the adoption statuses and the ledger's move relation are unchanged, so the supersession is partial.
