---
id: dec-480
draft_id: dec-draft-209743cc
title: The ADR rule loads by path scope on the decisions tree, with a declared resident projection at session start
status: accepted
category: architectural
date: 2026-10-31
summary: rules/swe/adr-conventions.md ships as the measured lean arm (path-scoped on .ai-state/decisions/**, kept always-on for Codex by its own codex load key) and a new rule rules/swe/adr-conventions-resident.md carries its title and opening sentence at session start; the resident declares resident_of, which scripts/_resident_of.py reads for the kernel tooling and which the Cursor exporter and the Codex bridge each check themselves to skip the resident (parity tests hold both checks equal to that reader), so no role kernel changes and the moved rule stays fully classified.
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
  - scripts/_resident_of.py
  - scripts/kernel_sources.py
  - scripts/check_kernel_manifest.py
  - scripts/regenerate_rules_manifest.py
  - cursor/config/export-cursor-rules.py
  - codex/config/rules_bridge_parsing.py
  - eval/src/praxion_evals/adherence/moves/arms.py
  - CLAUDE.md
affected_reqs: [REQ-01, REQ-02, REQ-03, REQ-04, REQ-05, REQ-06, REQ-07, REQ-08, REQ-09, REQ-10, REQ-19, REQ-20, REQ-21]
---

## Context

Paired run `20261030T153351Z-632ecb` (24 pairs, opus) found no regression within 10 points on decision draft placement and decision category when the ADR rule moved from always-loaded to path-scoped on `.ai-state/decisions/**` with a one-line resident. The arm's hand-edited manifest cannot be shipped (the generator owns `rules/_manifest.yaml`), and an unclassified always-loaded resident fails the kernel checker (I1); classifying it either duplicates text into four role kernels or fails I7.

## Decision

Ship the kit's rule bytes unchanged: `rules/swe/adr-conventions.md` gains `paths: [.ai-state/decisions/**]` and keeps `codex: load: always_on`, because Codex has no path scoping. Add `rules/swe/adr-conventions-resident.md`: the arm's 187-byte body under frontmatter `core: true`, `load: always_on`, `install: symlink`, `resident_of: rules/swe/adr-conventions.md`, and no other key.

`resident_of` is one fact. Each tool that must not treat the resident as an independent source honours it:

- **Kernel tooling.** `scripts/_resident_of.py` (`resident_parent`) is the shared reader. `scripts/kernel_sources.py` uses it to drop the resident from the always-loaded sources. It keeps the parent among the sources to classify although the parent is path-scoped, so totality holds. `scripts/check_kernel_manifest.py` reports, as `I1-unclassified`, any resident line that is no line of the parent.
- **Cursor and Codex exports.** The Cursor exporter (`cursor/config/export-cursor-rules.py`) and the Codex bridge (`codex/config/rules_bridge_parsing.py`, in `build_manifest`) each skip the resident through their own `is_resident` check, not an import. Each one runs from a copy that carries only its own config directory; the move instrument's narrowed checkouts are such copies, and an import of the shared reader broke every one of them. `tests/test_export_cursor_rules_resident.py` and `tests/test_codex_rules_bridge_parsing.py` hold each check equal to `resident_parent` on ten shapes, among them a non-rule value and a longer key name. The bridge's skip is what keeps the resident out of Codex, so the resident carries no `codex:` key; one that was there was never read and was dropped.
- **Manifest generator.** `scripts/regenerate_rules_manifest.py` does not read `resident_of`. It reads the resident's `core`, `load` and `install` keys like any rule's, and expects `swe/adr-conventions-resident` among its core ids.

The move instrument (`eval/src/praxion_evals/adherence/moves/arms.py`) refuses explicitly to build the lean arm over a tree where the move has landed.

Shipped versus measured: the rule is byte-identical. The resident's body is byte-identical, and the resident differs only by its 94 bytes of frontmatter. The two manifest rows match the measured rows on every compared key (`id`, `path`, `load`, `core`, `install`, `paths`); the generation stamp and the `chars` counts are not compared. The resident line was not grown: a larger kernel would be an unmeasured arm. FC-01 (always-loaded tokens under a scratch home) read 23,652 at base and 20,273 after the resident's unread `codex:` key was dropped (20,284 before), against a limit of 20,300: 3,379 tokens fewer.

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

### Every reader imports `scripts/_resident_of.py`
One parser, but `cursor/config/` and `codex/config/` sit far from `scripts/`, and the import broke every narrowed checkout copy. The two parts share only the key's presence, so a local check pinned by a parity test keeps that knowledge in balance with the distance. Rejected during execution.

## Consequences

- Positive: the measured arm ships; kernels and their index are byte-identical; Codex and Cursor keep today's reach (Codex loads the full rule always-on, Cursor exports it unchanged, and neither exports the resident); the parent keeps kernel totality.
- Negative: Claude Code ignores user-scope `paths:` on Windows, so a Windows session receives the resident line and the gate's refusals but never the path rule (declared limit). The new frontmatter key is read in three places: the shared reader and the two exporters' own checks, held equal only by the parity tests. The installer links rules file by file from the manifest, so the resident reaches a session only after the installer reruns. Until then, an install linked into a plugin version keeps that version's always-on rule, and an install linked into a checkout gets the path-scoped rule without the resident line. "Never read the index whole" now arrives late by path scope; the read guard in the companion decision (`dec-481`) closes that gap.

## Disconfirmation

- **Falsifier:** the component added is the rule `rules/swe/adr-conventions-resident.md`, and the ADR rule's delivery moves from session start to the path channel. Two exporters gain the responsibility of skipping a resident file. If the shipped tree delivered the full rule at session start, or the resident were not linked, nothing would have moved.
- **Steelmanned runner-up:** classify the resident `role/adr-author`. It needs no new key and no kernel-source or exporter change. The cost is about 45 duplicated tokens in four kernels that are not delivered today (no adr-author role is switched). It loses because it changes kernels the run did not measure and leaves the parent outside totality.
- **Reversal trigger:** a paired run of the shipped tree (lean plus gate) showing a regression beyond 10 points on either governed check, or the harness delivering resident frontmatter in a way that breaks the declared session-start lines.
