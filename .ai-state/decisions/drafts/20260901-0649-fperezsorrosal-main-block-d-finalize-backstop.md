---
id: dec-draft-4383a145
title: Broken-Block-D repair rides the finalize hook chain as a self-delivering fleet backstop
status: proposed
category: architectural
date: 2026-09-01
summary: The finalize chain gains a branch-independent, marker-guarded step that repairs the fail-open Block D fragment in any managed project's pre-commit hook, because the finalize hooks are the only channel that executes current plugin code fleet-wide without operator action; /upgrade-project remains the manual/immediate path.
tags: [self-healing, finalize-chain, block-d, aac, fleet-delivery, backstop, managed-projects]
made_by: agent
agent_type: orchestrator
branch: main
pipeline_tier: lightweight
affected_files:
  - scripts/finalize_chain.sh
  - scripts/reconcile_aac_surfaces.py
  - scripts/test_finalize_chain.py
  - scripts/test_reconcile_aac_surfaces.py
dissent: "Git hooks silently rewriting other git hooks is a trust boundary most tooling refuses to cross; even loud and marker-guarded, an operator who diffs .git/hooks/ after an unrelated commit will find a mutation they did not request."
---

## Context

The upgrade-path review (see the upgrade-path-consolidation decision) found
that every Block D fragment installed from the pre-fix template fails open:
its `PLUGIN_ROOT` resolution never matched the real
`installed_plugins.json` shape, so the AaC golden-rule gate silently skipped
on every commit in every onboarded project. The fix shipped in the template
plus a repair surface in `/upgrade-project` — but that path requires each
operator to (a) update the plugin and (b) remember to run the command in each
project. A defect whose whole nature is *silent* fail-open is the worst
candidate for a repair that depends on someone noticing.

One delivery channel reaches managed projects without operator memory: the
three finalize hooks are symlinks into the live plugin install, so after a
plugin update, every post-merge/post-commit/post-checkout in every project on
that machine executes current chain code. The finalize backstop precedent
(dec-284) established repairs riding this channel.

## Decision

`finalize_chain.sh` gains `_finalize_chain_repair_broken_block_d`, invoked at
the top of all public entry points, before any on-main gate (hooks are not
branch-scoped). It is guarded by a two-marker grep — `check_aac_golden_rule`
(Block D present) AND the `data.items()` literal unique to the broken
resolution (the fixed template deliberately avoids that string) — then invokes
`reconcile_aac_surfaces.py --mode apply --no-stage --surface block-d` and
announces the repair loudly. The `--surface` flag exists for this caller: a
git hook must never mutate tracked files, so the workflow-namespace re-point
stays exclusively with `/upgrade-project`.

Properties: healthy projects pay one grep per hook fire; the repair removes
its own trigger marker, so it fires at most once per project ever;
non-blocking like every chain step; a no-op on Praxion itself (whose
pre-commit is the pre-commit-framework shim).

## Considered Options

### Leave delivery to /upgrade-project alone (rejected)

- Pro: no hook mutates another hook; single documented repair path.
- Con: repairs only the projects whose operators run it — a silent fail-open
  defect stays unfixed exactly where nobody knows it exists. This is the
  tech-debt shape the backstop eliminates.

### Advisory-only backstop (print, do not repair) (rejected)

- Pro: respects the hooks-don't-rewrite-hooks boundary.
- Con: the nag fires on every git operation until the operator acts — louder
  in aggregate than one repair, and projects that ignore terminal output keep
  a dead gate indefinitely. The repair is byte-exact against the shipped
  template of a Praxion-owned fragment, which is the narrow case where
  auto-repair is defensible.

### Repair at plugin-install time (rejected)

- Pro: one-shot, no per-commit guard.
- Con: `claude plugin update` runs no Praxion code in project context; there
  is no per-project install hook to attach to. The finalize chain is the only
  in-project execution point Praxion owns.

## Consequences

- Positive: the fleet heals itself — plugin update plus any git activity in a
  project repairs its gate, no memory required; the guard's marker is removed
  by the repair, so steady-state cost is one grep.
- Negative: the finalize chain now mutates `.git/hooks/pre-commit`, widening
  its write surface beyond `.ai-state/`; the loud announcement mitigates the
  surprise but cannot eliminate it (see dissent).
- The chain's composition comment and `scripts/CLAUDE.md` record the new
  step; the backstop is scoped to this one historical defect and is not a
  general hook-content sync mechanism — future template evolution still flows
  through onboarding predicates and `/upgrade-project`.

## Disconfirmation

- **Falsifier**: a managed project surfaces where the `data.items()` marker
  matches a hand-written (non-Praxion) pre-commit fragment alongside a
  `check_aac_golden_rule` mention — the region matcher would then either
  bail (structure absent) or replace text the project owns; one confirmed
  instance of the latter invalidates the marker-precision premise.
- **Steelmanned runner-up**: the advisory-only variant preserves the
  hooks-don't-rewrite-hooks boundary and still surfaces the defect on every
  commit; if operators reliably act on loud nags, auto-repair buys little.
- **Reversal trigger**: a second defect class tempts a new chain-riding
  repair — if this becomes a pattern rather than a one-shot backstop, stop
  and design a general, declarative hook-reconciliation mechanism instead of
  accreting per-defect repairs in the chain.
