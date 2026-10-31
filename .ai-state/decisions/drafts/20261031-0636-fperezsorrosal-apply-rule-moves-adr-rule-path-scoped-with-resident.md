---
id: dec-draft-209743cc
title: The ADR rule loads by path scope on the decisions tree, with a declared resident projection at session start
status: proposed
category: architectural
date: 2026-10-31
summary: rules/swe/adr-conventions.md ships as the measured lean arm (path-scoped on .ai-state/decisions/**, Codex kept always-on) and a new rule rules/swe/adr-conventions-resident.md carries its title and opening sentence at session start; the resident declares resident_of, which kernel source discovery, the Cursor exporter and the manifest generator read, so no role kernel changes and the moved rule stays fully classified.
tags: [rules, startup-context-diet, moves, adr-conventions, kernels, path-scope]
made_by: agent
agent_type: systems-architect
branch: apply-rule-moves
pipeline_tier: full
affected_files:
  - rules/swe/adr-conventions.md
  - rules/swe/adr-conventions-resident.md
  - rules/_manifest.yaml
  - rules/_audience.yaml
  - scripts/regenerate_rules_manifest.py
  - scripts/kernel_sources.py
  - cursor/config/export-cursor-rules.py
  - eval/src/praxion_evals/adherence/moves/arms.py
  - CLAUDE.md
affected_reqs: [REQ-01, REQ-02, REQ-03, REQ-04, REQ-05, REQ-06, REQ-07, REQ-08, REQ-09, REQ-10, REQ-19, REQ-20, REQ-21]
---

## Context

Paired run `20261030T153351Z-632ecb` (24 pairs, opus) found no regression within 10 points on decision draft placement and decision category when the ADR rule moved from always-loaded to path-scoped on `.ai-state/decisions/**` with a one-line resident. The arm's hand-edited manifest cannot be shipped (the generator owns `rules/_manifest.yaml`), and an unclassified always-loaded resident fails the kernel checker (I1); classifying it either duplicates text into four role kernels or fails I7.

## Decision

Ship the kit's rule bytes unchanged. Add `rules/swe/adr-conventions-resident.md`: the arm's 187-byte body under frontmatter `core: true`, `load: always_on`, `install: symlink`, `resident_of: rules/swe/adr-conventions.md`, `codex: {load: exclude}`. `resident_of` is one fact read by every classifier and exporter: kernel source discovery checks each resident line is a line of the parent and keeps the parent total; the Cursor exporter skips the resident, checking the key itself so it still runs from a copy that carries `cursor/config/` alone (a parity test holds that check equal to `scripts/_resident_of.py`, the reader the kernel tooling uses); the generator expects the resident's id among core rules. The move instrument refuses explicitly to build the lean arm over a tree where the move has landed.

Shipped versus measured: the rule is byte-identical; the resident differs only by its frontmatter (118 bytes, +51 counted tokens); the manifest differs only by its generation stamp and the resident row's character count. The resident line was not grown: a larger kernel would be an unmeasured arm. Always-loaded tokens fall from 23,652 to about 20,215 (bound: 20,300).

Activation: no — one load-bearing representation choice with measured evidence; no lens sweep needed.

## Considered Options

### Classify the resident in the audience manifest as role/adr-author
Passes I1/I7 but duplicates the title and sentence into four kernels and changes the kernel version.

### Classify it orchestrator-only or no-actor
Fails I7: the adr-author kernel already carries the same paragraph from the parent.

### Detect resident files by a name convention
Implicit knowledge each reader would re-derive.

### Projection key `resident_of` (chosen)
One explicit fact, validated against the parent; no kernel churn.

## Consequences

- Positive: the measured arm ships; kernels and their index are byte-identical; Codex and Cursor keep today's reach; the parent keeps kernel totality.
- Negative: Claude Code ignores user-scope `paths:` on Windows, so a Windows session receives the resident line and the gate but not the path rule (declared limit); a new frontmatter key three tools read through one parser; existing installs keep the old always-on link until refreshed (today's behaviour is the fallback); "never read the index whole" now arrives late by path scope, closed by the read guard in the companion decision.

## Disconfirmation

- **Falsifier:** the component added is the rule `rules/swe/adr-conventions-resident.md`, and the ADR rule's delivery moves from session start to the path channel. If the shipped tree delivered the full rule at session start, or the resident were not linked, nothing would have moved.
- **Steelmanned runner-up:** classify the resident `role/adr-author`. It needs no new key and no kernel-source change; the cost is about 45 duplicated tokens in four kernels that are not delivered today (no adr-author role is switched). It loses because it changes kernels the run did not measure and leaves the parent outside totality.
- **Reversal trigger:** a paired run of the shipped tree (lean plus gate) showing a regression beyond 10 points on either governed check, or the harness delivering resident frontmatter in a way that breaks the declared session-start lines.
