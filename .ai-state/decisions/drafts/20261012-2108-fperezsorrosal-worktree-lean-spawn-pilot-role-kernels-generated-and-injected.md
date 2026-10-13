---
id: dec-draft-c967bd84
title: Role kernels are generated from one manifest and delivered by definition, spawn hook and Codex wrapper
status: proposed
category: architectural
date: 2026-10-12
summary: "A hand-authored audience manifest classifies every resident section; a generator emits committed kernel modules, a JSON index, the three universal blocks in every agent definition and the host-native preamble; a checker gates nine invariants; a synchronous SubagentStart hook injects the kernel rest and the project's CLAUDE.md for roles the adoption ledger marks trial or switched; the Codex wrapper embeds the same strings. Blocks stay in every definition as generated fallback; omitClaudeMd lands on a pilot role only with its adoption record."
tags: [agents, kernels, lean-spawns, startup-context-diet, subagent-start, codex, adoption-ledger, gate-liveness, behavioral-contract]
made_by: agent
agent_type: systems-architect
branch: worktree-lean-spawn-pilot
pipeline_tier: full
affected_files:
  - rules/_audience.yaml
  - claude/kernels/
  - scripts/kernel_model.py
  - scripts/generate_kernels.py
  - scripts/check_kernel_manifest.py
  - hooks/inject_kernel.py
  - hooks/hooks.json
  - hooks/inject_subagent_context.py
  - scripts/check_agent_shared_blocks.py
  - scripts/check_behavioral_contract.py
  - codex/config/export-codex-agents.py
  - eval/src/praxion_evals/adherence/
  - .ai-state/kernel_adoption.yaml
  - agents/
affected_reqs: [REQ-01, REQ-04, REQ-07, REQ-10, REQ-12, REQ-14, REQ-16, REQ-17, REQ-19, REQ-22]
supersedes: null
superseded_by: null
re_affirms: null
re_affirmed_by: null
retired_by: null
supersedes_in_part: dec-454
superseded_in_part_by: null
dissent: null
---

## Context

Phase 2 of the startup-context diet lets a spawned agent stop inheriting the instruction files (`omitClaudeMd`, about 18.3K tokens per spawn measured for the researcher and the verifier), but only if its process still reaches it. Today the process reaches agents by inheriting the orchestrator's whole rulebook, plus three universal blocks that dec-454 inlined into every definition, with their canonical texts held as constants in `scripts/check_agent_shared_blocks.py`. dec-454's reversal trigger names this stage. A lean verifier without a kernel read the user's instruction file by an inferred path in 3 of 3 smoke sessions of the dec-458 eval. Two of the user's principles (2026-10-12) bind the design: nothing is cut to meet a number, and the process is never substituted by memory. dec-453 made `rules/CLAUDE.md` an on-demand nested guide (whether a lean spawn still loads it is a spike); dec-455 keeps memory indexes as pointers, never a process channel; dec-458 and dec-459 are the eval and the flip rule this design feeds, and the eval is extended additively.

Activation: no -- the option set was fixed by the user-ratified scope and the orchestrator's recorded Spec Question decisions.

## Decision

Add five components and move one responsibility:

1. `rules/_audience.yaml`: every section, or part of a mixed section, of the six rule files with no path scope, `claude/config/CLAUDE.md.tmpl` and Praxion's `CLAUDE.md` gets exactly one closed scope (core; role, through a declared module; orchestrator-only; no-actor) and one form (verbatim, or condensed with a pinned sha).
2. `scripts/generate_kernels.py`: emits `claude/kernels/<module>.md`, `claude/kernels/index.json` (role to ordered strings, with adoption statuses projected), the three universal blocks inside every `agents/*.md`, and the host-native preamble constant. **The universal blocks' canonical text moves from the shared-block checker to the generator**; the checker now verifies identity with the generator's output.
3. `scripts/check_kernel_manifest.py`: invariants I1-I9, one canary each, as a pre-commit gate; a `--liveness` mode for the flip record.
4. `hooks/inject_kernel.py`: K synchronous `SubagentStart` slot entries inject the rest of the kernel (never what the definition already carries) and the project's root `CLAUDE.md`, for roles at `trial` or `switched`; one `kernel_injected` row per delivering spawn; no disable variable.
5. `.ai-state/kernel_adoption.yaml`: absent, then trial, then switched, forward only; `omitClaudeMd` only when switched; switched only for the five eligible pilot roles, with every run id, the probe readings and both user ratifications recorded.

The Codex exporter embeds the same strings and strips `omitClaudeMd`; Cursor is untouched; the adherence eval refuses to score a lean session whose kernel did not arrive.

## Considered Options

### Hook-only delivery, inline blocks deleted at the flip

Pros: one channel per agent; about 0.4K tokens less per switched spawn. Cons: a missing or failing hook leaves a switched agent with nothing, which the never-to-nothing constraint forbids. Rejected.

### Generated blocks plus the hook's delta (chosen)

Pros: a spawn always has the contract, the links rule and the return contract; every copy has one source; the hook adds only what the definition lacks. Cons: the verbatim contract enlarges every definition; two channels must stay consistent, which the generator and the freshness invariant handle.

### Whole kernel inline in every definition, no hook

Pros: no hook; works in every harness. Cons: role modules (up to about 6K tokens) and the project file inline would push definitions past their prompt-size ceilings, and could not vary with adoption status or with the working project. Rejected.

## Consequences

- Positive: the contract text has one source across definitions, kernels, the preamble and Codex; a lean spawn carries its process; flips are gated on a checked record; a silent hook failure cannot pass as a measured result.
- Negative: every agent definition grows by the verbatim contract; K process starts per `praxion:*` spawn; a ledger edit requires regeneration; the order of strings across hook entries is unverified until a spike settles it.
- The hook reads only the generated JSON index (stdlib-only in any project), never the YAML manifest or ledger.
- dec-454's clauses 2-4 stand: presence is computed without a roster, report producers carry markers, and the widened roster stays. Its clause 1's canonical home moves here.

## Disconfirmation

- **Falsifier:** a 20-pair adherence run for a pilot role in which the lean sessions carry kernel rows yet regress a mechanical check whose rule text the kernel carries; or a switched role whose measured first request is not below its baseline.
- **Steelmanned runner-up:** hook-only delivery with the blocks deleted is simpler and saves slightly more per spawn. It loses only because a hook can fail open, and a switched definition without blocks then starts with nothing.
- **Reversal trigger:** the harness gains a native per-agent context channel that cannot fail silently, or two consecutive releases show no `liveness-missing-row` for any switched role; then deleting the inline blocks from switched definitions is reconsidered.

## Prior Decision

dec-454 (partially superseded) inlined three universal blocks into every agent definition, kept their canonical texts as constants in `scripts/check_agent_shared_blocks.py`, and named this stage as its reversal trigger. What changes: the three blocks' canonical source moves to the kernel generator, and the blocks become generated output. They are kept, not deleted, so presence stays universal. This is a partial rather than a full supersession because dec-454's presence gate, its marker extension and its roster widening are unchanged.
