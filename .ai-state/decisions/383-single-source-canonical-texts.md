---
id: dec-383
draft_id: dec-draft-d4692dce
title: The behavioural-contract rule is the sole author of the four definitions; a shape-extracting guard single-sources them without fences
status: accepted
category: architectural
date: 2026-09-12
summary: "The four behaviour definitions in rules/swe/agent-behavioral-contract.md become the only wording in the repository; five files (the shipped behavioral-contract canonical block, its onboarding embed, README.md, codex/config/AGENTS.md.tmpl and the generated root AGENTS.md) become byte-bound consumers and the hackathon block's restatement becomes a pointer. The binding mechanism is a new totalising BC05 check inside scripts/check_behavioral_contract.py that extracts and compares definition-shape bullet lines, NOT sync_canonical_blocks.py — because making the four bullets a sync unit forces the shipped canonical block to become a fenced consumer, and claude-md-blocks.md copies that body verbatim into every managed project's CLAUDE.md while hash_block_body does not strip HTML comments. The always-loaded task-slug paragraph becomes a pointer and the always-loaded return-contract clause is deleted after its orchestrator-facing clause moves into the rule row: net -613 B / -156 tokens governed."
tags: [process-economy, roadmap-p2-10, behavioral-contract, canonical-blocks, single-sourcing, byte-budget, sentinel, codex]
made_by: agent
agent_type: systems-architect
branch: worktree-process-economy-p2-10
pipeline_tier: standard
affected_files:
  - rules/swe/agent-behavioral-contract.md
  - rules/swe/swe-agent-coordination-protocol.md
  - claude/config/CLAUDE.md.tmpl
  - claude/canonical-blocks/behavioral-contract.md
  - claude/canonical-blocks/hackathon-mode.md
  - claude/aac-templates/hackathon-mode.md.tmpl
  - claude/canonical-blocks/block-history.json
  - skills/onboard-project/references/claude-md-blocks.md
  - README.md
  - AGENTS.md
  - codex/config/AGENTS.md.tmpl
  - scripts/check_behavioral_contract.py
  - scripts/test_check_behavioral_contract.py
  - agents/sentinel.md
  - agents/discipline-consultant.md
  - tests/test_sentinel_row_contract.py
  - .pre-commit-config.yaml
  - skills/software-planning/references/coordination-details.md
  - docs/rules-taxonomy.md
  - .ai-state/DESIGN.md
affected_reqs: [REQ-01, REQ-02, REQ-03, REQ-04, REQ-05, REQ-06, REQ-07, REQ-08]
dissent: "Praxion already owns a sync mechanism for this exact defect class; adding a second text-equality mechanism beside a working one is the sprawl P2.10 exists to reverse — the objection is answered only because the fenced direction would ship sync anchors into six repositories Praxion does not own."
---

## Context

Four distinct wordings of the four-behaviour agent behavioural contract coexist in the repository,
measured 2026-09-12 over every tracked file with no `--include` filter: the always-loaded rule
(`rules/swe/agent-behavioral-contract.md:11-14`, 771 B / 176 tokenizer tokens), the shipped
canonical block (`claude/canonical-blocks/behavioral-contract.md:5-8`, 628 B / 150 tok),
`README.md:94-97` (516 B / 123 tok) and `codex/config/AGENTS.md.tmpl` → the generated root
`AGENTS.md` (259 B / 67 tok each), plus a fifth partial wording in the hackathon block
(`claude/canonical-blocks/hackathon-mode.md`, its divergent aac template, and their embed in
`claude-md-blocks.md`, 357 B / 89 tok each). Of eight definition-carrying spans, exactly **one**
is under an executable guard today (`claude-md-blocks.md`, via `sync_canonical_blocks.py --check`).
Root `CLAUDE.md` already names the rule as canonical, so five of the six files are restating a text
they do not own.

Two always-loaded restatements compound this in the governed token budget (16,730 / 25,000,
tokenizer over 9 files): `rules/swe/swe-agent-coordination-protocol.md:85` restates the task-slug
propagation convention defined one always-loaded rule over in
`agent-intermediate-documents.md` (549 B / **147 tok**), and `claude/config/CLAUDE.md.tmpl:57`
carries a third wording of the return contract whose canonical row sits at
`swe-agent-coordination-protocol.md:99` (the duplicated clause measures 278 B / **71 tok** — not
the 835 B / 185 tok of the surrounding paragraph, which also holds an unrelated, still-needed
delegation sentence). Both files are always-loaded in every session, so each token is paid by the
orchestrator and by every subagent spawn.

The user settled four points before design (TASK_BRIEF §8): the rule's four bullets become the one
text (D-b); the `CLAUDE.md.tmpl` clause is deleted outright with zero semantic loss, not pointered
(D-c); the hook preamble and the deep-dive reference keep their distinct prose (D-d); and the fleet
pass to managed projects stays deferred (D-a). The roadmap's W8 objection — that the fifteen
byte-identical `agents/*.md` task-slug sentences are *correctly* duplicated and already guarded by
`scripts/check_agent_shared_blocks.py` — stands and is not reopened. Left open for design: the
source direction, the consumer-vs-pointer treatment of each site, and the guard's mechanism and
home.

## Decision

**`rules/swe/agent-behavioral-contract.md:11-14` stays the source and is not modified.** Five files
become byte-bound consumers of its four bullet lines: `claude/canonical-blocks/behavioral-contract.md`,
`skills/onboard-project/references/claude-md-blocks.md`, `README.md`,
`codex/config/AGENTS.md.tmpl` and the generated-but-tracked root `AGENTS.md`. Each keeps its own
heading, intro and trailing prose — those are legitimately audience-specific — and only the four
definition lines are bound.

**The binding mechanism is a new `BC05` check inside `scripts/check_behavioral_contract.py`, not
`sync_canonical_blocks.py`, and no HTML-comment fence enters any file.** BC05 extracts, per file,
the lines matching a bullet-anchored definition shape
(`^[ \t]{0,8}[-*][ \t]+\*\*<Name>\*\*[ \t]*(—|:|-|\()`) and asserts byte-equality with the source's
four lines in canonical order. The same predicate supplies the totalising half: any file inside
BC05's declared scope carrying three or more behaviours in definition shape that is neither the
source, nor a registered consumer, nor allowlisted, is a finding. Detection and comparison are one
mechanism, so there is no gap between "registered" and "in sync".

**The hackathon restatement becomes a pointer** at all three sites. Verified, not assumed:
`skills/onboard-project/SKILL.md` §Mode × Phase Matrix shows Phase 6 running in `new`, `existing`
**and** `hackathon` modes, and `phases-core.md` lists `behavioral-contract` among the four blocks it
installs unconditionally — so a hackathon project's `CLAUDE.md` already carries `## Behavioral
Contract` above `## Hackathon Mode`, and the second wording is redundant forty lines from the first.

**The two always-loaded restatements are removed.** `swe-agent-coordination-protocol.md:85` becomes
a one-line pointer (−393 B / −103 tok). The `claude/config/CLAUDE.md.tmpl:57` return-contract clause
is deleted (−278 B / −71 tok) **after** its one non-redundant clause — the orchestrator-facing
"never ask for the full report inline", which the canonical row states only as a constraint on the
subagent's output — is appended to the Return-contract row (+58 B / +18 tok). Net governed delta
**−613 B / −156 tokens**, which is `−1,092` tokens per Standard pipeline at seven inheritors and
keeps `check_token_ratchet.py`'s `governed_delta_bytes ≤ 0` satisfied with margin.

BC05 is registered as a dec-382 family-form row in `agents/sentinel.md`'s BC dimension and joins the
existing Family dispatch row, so `run_check_families.py` picks it up without modification and the
Triangle (`tests/test_sentinel_check_triangle.py`) binds row, registry and declared `CHECK_IDS`.
Both relevant pre-commit `files:` regexes are widened to fire on consumer paths — including
`commands/co.md` and `commands/cop.md`, the existing `commit-process` consumers that no trigger
covers today.

## Considered Options

### Option 1 — Block-as-source, rule-as-consumer (extend `sync_canonical_blocks.py`)

The brief's own recommendation. `claude/canonical-blocks/behavioral-contract.md` keeps whole-file
sync; the rule gains the `commit-process` → `commands/co.md` HTML-comment prose fence.

- **Pro**: reuses a working, pre-commit-gated mechanism with `--write`, `--dry-run` and a refresh
  pipeline into six managed repos; the diff is two `BLOCKS` registry lines; no second mechanism.
- **Con, decisive**: the sync unit is a whole canonical file's body, so the rule would have to adopt
  the block's `## Behavioral Contract` heading and its managed-project intro ("including Claude
  itself"), losing the rule's own title — which `rules_bridge_parsing.extract_title()` and
  `rules/_manifest.yaml` both read — and contradicting D-b.
- **Con**: `codex/config/rules_bridge_parsing.py:196-217` (`extract_summary`) classifies body lines
  by prefix with branches for `## `, `- `/`* `, a code fence, `|` and `#` — and, when this
  decision was taken, **no branch for `<!--`**. Step 10b of this pipeline added a branch for a
  leading comment line or block and pinned it with a fixture test; the decision stands on the
  other reasons (the shipped block would still carry the anchor into every managed project).
- **Con**: +~138 B in an always-loaded rule, cutting the governed saving from −613 B to −475 B.

### Option 2 — Rule-as-source via a new bullets-only canonical file

A narrow canonical holding just the four bullets; every site including the existing shipped block
becomes a fenced consumer.

- **Pro**: honours D-b literally (the bullets are the unit) while still using the existing script.
- **Con, decisive**: `claude/canonical-blocks/behavioral-contract.md` becomes a *consumer*, so it
  must carry a `<!-- canonical-source: … -->` anchor and two fence lines in its body — and
  `claude-md-blocks.md` embeds that whole body inside a ```` ```markdown ```` fence which
  `/onboard-project` Phase 6 copies verbatim into every managed project's `CLAUDE.md`.
  `canonical_block_identity.hash_block_body()` normalizes whitespace and does **not** strip HTML
  comments, so the anchors would both ship into six repositories Praxion does not own and enter the
  block-identity hash that `REFRESHABLE_SLUGS` later rewrites.
- **Con**: introduces canonical-file-consumes-canonical-file nesting whose `--write` convergence
  depends on `sorted()` ordering of consumer paths — correct today by lexicographic accident.

### Option 3 — Rule-as-source via BC05 shape extraction (chosen)

- **Pro**: no fence enters any file, so none of the five parsers that read rule bodies or shipped
  block bodies meets a new shape, and no HTML comment ships to a managed project. Detection and
  comparison are one mechanism. Zero new gate surface: `check_behavioral_contract.py` is already a
  sentinel-delegated gate (`fitness/tests/test_gate_canary_coverage.py::_delegated_gates`), already
  has a canary, already has a pre-commit entry — dec-381 measured that per-script cost as the
  dominant one and this pays none of it. BC05 was required by the brief regardless, so the
  "second mechanism" objection prices a script that was being written anyway.
- **Pro, measured**: the bullet-anchored predicate selects exactly 6 files at ≥3 matches with zero
  false positives across 124 files that name at least one behaviour — so the predicate needed for
  detection is already a precise extractor.
- **Con**: no `--write` fixer (deliberate — the bullets have changed twice in the project's history;
  a missed consumer fails the gate immediately and the finding prints the expected line).
- **Con**: binds lines rather than a fenced span, so the regex *is* the contract; a site writing
  `**Surface Assumptions.**` escapes it. Stated in the declared-limits table rather than implied
  away.

## Consequences

**Positive.**

- One wording of the four definitions repo-wide, down from four (five counting the hackathon
  partial); eight of eight definition spans under an executable guard, up from one of eight.
- −613 B / −156 tokenizer tokens on the governed always-loaded corpus (16,730 → ~16,574), ≈ −1,092
  tokens per Standard pipeline at seven inheritors. The listing budget is unmoved at 9,243 —
  `measure_listing()` reads frontmatter descriptions and this change edits only agent bodies.
- Three restatement spans disappear entirely (the hackathon block, its aac template, their embed).
- A gap nothing guarded closes as a side effect: root `AGENTS.md` is tracked but no check bound it
  to the `codex/config/AGENTS.md.tmpl` it was rendered from (`MIRRORS` does not cover the pair, and
  only re-running `./install.sh codex` regenerates it). Both are now BC05 consumers.
- A pre-existing pre-commit gap closes: `canonical-block-sync`'s `files:` regex matched no consumer
  path, so a hand-edit to `commands/co.md`'s or `commands/cop.md`'s fenced span could land drifted.
- Codex sessions gain the authoritative contract. Verified at
  `codex/config/rules_bridge_static_modules.py:115`: the rules bridge emits only
  `"- {title} — {source_path}"`, never a rule body, so the compiled `AGENTS.md` is the only surface
  on which a Codex session reliably holds the text — and it held a four-word caricature
  ("**Surface Assumptions** before acting on them").

**Negative, and stated rather than minimised.**

- **The un-governed surface grows by ≈ +1,571 B.** The surviving wording is the longest one (the
  rule's 771 B, chosen by D-b), so every consumer grows: +143 B in the canonical block and its
  embed, +255 B in `README.md`, +512 B in each of the two Codex surfaces. The largest single
  component, +512 B / +109 tok in every Codex session, is the price of Codex holding the real
  contract. This change is not a byte reduction outside the governed corpus and must not be priced
  as one.
- **Cross-repo effect, certain and immediate.** The `behavioral-contract` and `hackathon-mode` block
  bodies change, so `block-history.json` is regenerated and all six managed repositories reclassify
  their live contract block `current` → `stale` on their next `refresh_claude_blocks.py --check`.
  D-a defers the *application* of the fleet pass, not this classification.
- **Two accepted semantic losses on the D-c deletion.** The framing sentence "This is context
  engineering applied to the pipeline itself." has no equivalent in the terse Pipeline Rules table
  and is dropped — connective tissue, not a testable convention. The orchestrator-facing clause is
  *not* accepted as a loss: it moves into the rule row first (strict reading, per the orchestrator's
  ruling), and a test greps the row for each clause keyword.
- **A third mechanism now governs text identity** (`sync_canonical_blocks.py` for whole blocks,
  `check_template_mirrors.py` for whole files, BC05 for a bullet span). The boundary is coherent —
  whole body, whole file, named lines — but it is three registries to keep honest, and each
  docstring must point at its two siblings.
- **An allowlist that cannot currently fire.** Every D-d entry scores 0 under the definition-shape
  predicate (the hook preamble is a Python string literal; the deep dive uses `###` headings), so
  the allowlist is kept for forward safety and its *mechanism* is tested by planting a matching copy
  at an allowlisted path, not by asserting the live entries match.
- **Out of scope, needs a ledger row from a ledger writer.**
  `claude/aac-templates/hackathon-mode.md.tmpl` is **not** byte-identical to
  `claude/canonical-blocks/hackathon-mode.md` as the brief states: 8,381 B vs 9,362 B, with a whole
  "Worktree policy by entry point" paragraph and a "PROGRESS.md is written by the orchestrator
  alone" paragraph absent and a superseded `CREATIVE-BLOCKER` wording retained. Only the contract
  bullets match. A `check_template_mirrors.MIRRORS` row — the natural whole-file home — is therefore
  unavailable without first reconciling 981 B of unrelated drift.
- **A consistency asymmetry the user may wish to close.** D-c's reasoning (a pointer between two
  always-loaded files is dead weight) applies verbatim to the task-slug paragraph, whose directive
  is nonetheless "one-line pointer". Deleting it instead would save a further ~35 tok × 7 ≈ 245
  tokens per pipeline. Followed the directive; flagged the asymmetry.

- **Hackathon-mode block is not refresh-tracked.** `hackathon-mode` is deliberately absent from `REFRESHABLE_SLUGS`, so the six managed projects keep their inlined four-bullet hackathon restatement with no stale signal until a later upgrade re-installs the block; the contract block itself refreshes. Accepted (user decision D-b: refresh later is fine); tracked with td-205.

- **The Codex template is no longer pure ASCII.** Byte-identity with the rule brings its em-dashes into `codex/config/AGENTS.md.tmpl` and the generated `AGENTS.md`; nothing in the Codex export path is ASCII-gated (verified by the exporter tests), so this is a record, not a risk.
- **One phrase left the always-loaded set.** The task-slug paragraph's "derived from the task description" now lives only in `coordination-details.md § Task Slug Propagation`, one hop from the always-loaded convention; the four binding conventions (kebab-case, 2–4 words, `Task slug: <slug>` in every prompt, `.ai-work/<task-slug>/`) stay resident. Accepted loss.

## Disconfirmation

**Falsifier.** Exhibit a fenced arrangement in which
`claude/canonical-blocks/behavioral-contract.md` is a `sync_canonical_blocks.py` consumer of the
four bullets **and** the `<!-- canonical-source -->` anchor plus fence lines do not reach
`claude-md-blocks.md`'s fenced span (and therefore do not reach a managed project's `CLAUDE.md` or
the block-identity hash). If that exists, Option 1 dominates on mechanism economy and this decision
is wrong. Secondarily: if the bullet-anchored predicate is shown to miss a definition-shape
restatement that a reasonable author would write, the totalising claim is weaker than stated and
the extraction should move to a span-based mechanism after all.

**Steelmanned runner-up.** Option 1 is the institutionally correct answer. Praxion already owns a
mechanism for exactly this defect class; it is pre-commit-gated, it has `--write`, `--dry-run`,
`--check-history` and a live refresh pipeline into six managed repositories, and the
`commit-process` → `commands/co.md`/`cop.md` precedent proves that prose-fenced embedding into a
*prompt body* works in production today. Adding two lines to the `BLOCKS` registry is a smaller,
more reviewable diff than a new check with a new registry and a new comparator. Building a second
text-equality mechanism beside a working one is precisely how an ecosystem acquires two ways to do
one thing — the sprawl P2.10 exists to reverse — and the `extract_summary` gap that Option 1 exposes
is a four-line fix in a function whose missing `<!--` branch is already located. On that reading,
the right move is: fence the rule, fix the parser, and accept three invisible comment lines in one
always-loaded file as the price of not inventing a mechanism. What defeats it is not elegance but
placement: in Option 1 the *shipped* block must be the consumer, and its body leaves Praxion's tree.
No amount of parser-fixing reaches that, because it is a property of where the fences must sit.

**Reversal trigger.** Revisit when any of three signals fires: (1) a second convention needs the
same treatment (one paragraph single-sourced across heterogeneous wrappers) — at that point extract
the registry-plus-comparator into a shared module rather than copying it, and re-examine whether
teaching `sync_canonical_blocks.py` a "source span" concept is the better home; (2) the BC05
consumer registry grows past roughly eight entries, or the four bullets change twice in one quarter
— either justifies the `--write` fixer this decision declines; (3) `sync_canonical_blocks.py` gains
the ability to exclude its anchor and fences from a consumer's *shipped* span, which would remove
the placement objection that is this decision's entire load-bearing argument.
