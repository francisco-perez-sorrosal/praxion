# Spec: audience-split (a plugin role's spawn stops receiving the orchestrator-only text of the coordination protocol and the intermediate-documents rule)

**Task slug**: `audience-split`
**Created**: 2026-11-09
**Pipeline run**: 2026-11-08 to 2026-11-09
**Start date**: 2026-11-08
**End date**: 2026-11-09
**Archived**: 2026-11-09 (pre-merge, on branch feat/audience-split; the merge to main finalizes the draft named below)
**Status**: completed -- final verdict PASS WITH FINDINGS (the first pass FAILed at `54a75662` on one convention finding, closed by `da259208`)
**Tier**: Standard (planned 14 of 16 spawns; the verifier's calibration verdict reads `correct`: 12 production files and 12 requirements meet Full's size signals, but the work was one cohesive mechanism run in sequence, which needed none of Full's parallel or shadowing machinery)
**Complexity**: large by size (12 requirements, 10 plan steps, 42 files changed at the first verified head), medium by shape
**Base commit**: `f1f8adf1` · acceptance design `a7867bcd` (before the first production step) · first production commit `98e3aa8c` · first verified head `54a75662` · re-verified head `da259208` · archive head `f3f55f93`
**Pipeline branch**: `feat/audience-split`
**ADRs**: `dec-draft-25c1476d` (category: architectural -- a build-time spawn split of the two managed core rules; finalize rewrites the draft id to a stable `dec-NNN`)
**Evidence base**: the ADR draft above under `.ai-state/decisions/drafts/` (its `## Consumer Audit` is the record of REQ-09); the spec digest `sha256:14edd768ff33` of `SPEC_EXTRACT.md` (the verifier read the extract fresh); the branch's 19 commits from the base; the footprint log (`MEASUREMENTS.md`) and the free shed count (`SHED_COUNT.md`), both taken at `54a75662` and re-checked at `f3f55f93`; the verifier's report and its re-verification at `da259208`. No eval session ran. One approved before/after startup probe (two first-request sessions on the subscription) is recorded under Shed Count.

## Feature Summary

A plugin role's spawn sheds the orchestrator-only text of two rules, 15,166 characters (5,808 tokens) per spawn.

Before this change every inheriting spawn in a managed project received the three managed core units whole: the coordination protocol, the intermediate-documents rule and the ADR resident. The audience manifest `rules/_audience.yaml` already classifies parts of the first two as `orchestrator-only`, text addressed to the main session, which keeps both rules resident. Now a *split recipient* receives the two units without those spans. A split recipient is an inheriting spawn of a `praxion:<role>` agent whose definition is read from this plugin and does not set the lean flag; today that is thirteen roles. The ADR resident still arrives whole, and every kept byte arrives unchanged and in source order, under its unit's label and, for a section that loses only some of its parts, under that section's heading.

The channel is a build-time artifact. `scripts/generate_kernels.py` writes `claude/kernels/spawn_split.json` through one cutter, `scripts/kernel_spawn_split.py`, and the `SubagentStart` hook (`hooks/inject_rules.py` over the pure `hooks/_rule_delivery.py`) delivers a unit's stored split only when the digests of its body, of the audience manifest and of the split text all match the current tree; each unit is judged on its own and arrives whole otherwise, on the impaired floor too. A new kernel-gate invariant, I11, refuses a tree whose split-recipient delivery disagrees with its sources, a fallback to whole included, and the `kernel-manifest` commit hook and the root suite in CI run it. The verifier's `Calibration Verdict` sub-step reaches the tier signals in Process Calibration by a path in its own definition. `scripts/count_spawn_shed.py` counts the shed text at no cost.

Everything else is unchanged: the main session's `SessionStart` delivery byte for byte, every whole recipient (`general-purpose` and other built-ins, forks, project, user and other plugins' agents, and a `praxion:<role>` spawn whose definition cannot be read), lean spawns, `Explore` and `Plan`, and unmanaged scopes. Neither source rule lost a section or a part. No role was flipped, held or trialled, no adoption record changed, and no paid session ran.

Measured at the first verified head `54a75662` against the baseline at `89052e66`: the shed per split recipient is 15,166 characters (22,920 whole, 7,754 split), 5,808 tokens by the tokenizer and 4,246 by the offline estimate (the design's spike estimate was about 3,200). The main session's always-loaded tokens are 19,918 before and after, the listing tokens 14,268 before and after, and the prompt-size findings 3 warn and 0 fail before and after. Of 111 inheriting spawns in this project's log since 2026-10-10, 109 were split recipients.

## What Was Built

- **Pure delivery layer** `hooks/_rule_delivery.py`: the agent-kind classification that separates split recipients from whole recipients (`parse_agent_kind`), the split values, `spawn_units` (each unit trusted alone on three digests), `distrusted_units`, the one rule-body reading (`rule_body`) and, after rework, the one source decoder (`decode_source`). It stays stdlib-only and does no I/O.
- **Hook edge** `hooks/inject_rules.py`: `_received_units` is the one substitution point before the plan, used by both the manifest path and the impaired floor, so slotted parts and the no-argument whole text carry the same split. A split that cannot be parsed or trusted leaves the unit whole, with one stderr line for a missing or unreadable artifact; a catch-all guarantees the floor never depends on the split.
- **Cutter, generator and artifact**: `scripts/kernel_spawn_split.py` (also the source of the shed count and of the gate's expectation), `scripts/generate_kernels.py` (`plan_kernels`), `claude/kernels/spawn_split.json`.
- **Gate**: `I11-spawn-split-drift` and `I11-spawn-split-unreadable` in `scripts/check_kernel_manifest.py`, with a canary test of five named plants, five unreadable plants and a restore; the `kernel-manifest` hook's read set in `.pre-commit-config.yaml` covers the hook modules the check now imports.
- **Definitions and manifest text**: a plugin-path pointer to Process Calibration in `agents/verifier.md` and `agents/skill-genesis.md`; one header comment and one `reason` string in `rules/_audience.yaml`. No classification changed.
- **Count**: `scripts/count_spawn_shed.py`, offline by default, with an opt-in `--tokenizer`.
- **Documents**: `scripts/CLAUDE.md`, `.ai-state/DESIGN.md`, `docs/architecture.md` and the `spawn-startup-tokens` paths in `.ai-state/FOOTPRINTS.md`.

## Requirements

### Observable Surface

- `SessionStart`, `SubagentStart`: the harness events at which the main session and a spawn receive hook-delivered context
- `hooks/hooks.json`: the hook registration. A spawn's rule delivery is the list of strings, in slot order, that the commands registered under `SubagentStart` print as `additionalContext` inside `hookSpecificOutput` and that open with the rule label below. Each command gets a payload on stdin that names `hook_event_name`, `agent_type` and `cwd`, and `CLAUDE_PLUGIN_ROOT` names the plugin root. Today these are the slots of `python3 hooks/inject_rules.py --slot N`. The main session's delivery is the same thing for `SessionStart`
- `## Praxion Rules (auto-injected): <unit>, part k of n`: the label each delivered string opens with, naming its unit and its place
- `swe/swe-agent-coordination-protocol`, `swe/agent-intermediate-documents`, `swe/adr-conventions-resident`: the three managed core units, delivered in that order, from `rules/swe/swe-agent-coordination-protocol.md` (the coordination protocol), `rules/swe/agent-intermediate-documents.md` (the intermediate-documents rule) and `rules/swe/adr-conventions-resident.md` (the ADR resident), each with its frontmatter removed
- `rules/_audience.yaml`: the audience manifest. It gives every section (heading level two to four) and every part of a mixed-audience section exactly one entry, with a scope of `core`, `role`, `orchestrator-only` or `no-actor`. The last two carry a `reason`, and a `condensed` form names authored kernel text. A `part` names the prefix that begins its first line
- `rules/_manifest.yaml`: the rules manifest, which says which rules are hook-delivered and to which scope
- `.claude/praxion-rules.yaml`: a project's rule blacklist. It cannot switch off a managed core unit
- `PRAXION_DISABLE_RULE_INJECTION`: the kill switch for rule injection
- `PyYAML`: the YAML parser the hook's interpreter may lack
- `.ai-state/`: the project state directory. A working directory it serves is a managed scope; any other is unmanaged
- `omitClaudeMd`: the agent-definition flag that makes a spawn lean when it is written as the literal word true
- `praxion:<role>`, `praxion:verifier`: a plugin role's agent type, and the verifier's. A role's definition is this plugin's `agents/<role>.md` under `CLAUDE_PLUGIN_ROOT`. `Explore`, `Plan` and `general-purpose` are host-native agent types, and `fork` is the `agent_type` a fork's `SubagentStart` payload carries
- `researcher`, `implementer`, `test-engineer`, `systems-architect`: today's lean roles
- `agentic-transactions-architect`, `architect-validator`, `cicd-engineer`, `context-engineer`, `discipline-consultant`, `doc-engineer`, `implementation-planner`, `interface-designer`, `promethean`, `roadmap-cartographer`, `sentinel`, `skill-genesis`, `verifier`: today's inheriting plugin roles
- `agents/verifier.md`: the verifier's definition. `Calibration Verdict` is its report sub-step for `Standard` and `Full` runs, and it fills the report's `## Calibration Verdict` section. It gives the `Retrospective` verdict, one of `correct`, `over-calibrated` or `under-calibrated`, plus a one-line evidence clause
- `Process Calibration`: the coordination protocol's section that holds the tier table. `Direct`, `Lightweight`, `Standard`, `Full` and `Spike` are its tiers, and each tier has its `Signals`
- `python3 scripts/check_kernel_manifest.py`: the kernel manifest gate. `kernel-manifest` is its commit-time hook
- `python3 scripts/generate_kernels.py --check`: the kernel generator's freshness check
- `python3 scripts/sync_canonical_blocks.py --check`, `ruff`, `pyright`, `python3 scripts/resolve_test_scope.py`: the shipped-block check, the linter, the type checker and the derived test scope
- `uv run pytest -q -p no:cacheprovider`: the root suite as continuous integration runs it, from the repository root
- `python3 scripts/measure_token_budget.py --json`, `python3 scripts/check_agent_prompt_size.py --json`: the instruments the footprint criteria name
- `python3 scripts/measure_startup_payload.py agent:<name> --strict-mcp-config --plugin-dir <checkout> --json`: the paid startup probe, which reads a spawned role's first-request tokens

### Terms

- **Inheriting spawn**: a spawn that loads the instruction hierarchy. It is decided exactly as at the pipeline base. Every plugin role whose definition does not set the lean flag counts, and so do `general-purpose`, a fork, a project or user agent, another plugin's agent, and a spawn whose definition cannot be read or spells the flag other than the literal word true
- **Split recipient**: an inheriting spawn of agent type `praxion:<role>` whose definition is read from this plugin and does not set the lean flag. Today these are the thirteen inheriting plugin roles listed on the Observable Surface
- **Whole recipient**: every other inheriting spawn. That means `general-purpose` and any other built-in apart from `Explore` and `Plan`, a fork (a payload `agent_type` of `fork`), a project or user agent, another plugin's agent, and a `praxion:<role>` spawn whose definition cannot be read. It receives the two units whole, as at the pipeline base
- **Lean spawn**: a spawn whose definition sets `omitClaudeMd` to the literal word true
- **The two units**: the coordination protocol and the intermediate-documents rule, as rule delivery reads them
- **Dropped span**: a section the audience manifest classifies `orchestrator-only`, from its heading line to the line before the next heading of level two to four; or a part so classified, from the line its prefix begins to the next part or its section's end. A subsection is a section of its own and is classified on its own
- **Split text** of a unit: its text with exactly its dropped spans removed (REQ-01)
- **Whole unit**: the unit's text as rule delivery reads it at that tree, delivered as it was at the pipeline base

### REQ-01: A split recipient receives the two units without their orchestrator-only text

**When** a split recipient starts in a managed scope
**and** the split text of a unit can be trusted (REQ-05)
**the system** delivers that unit as its split text. Every byte outside the dropped spans arrives unchanged and in source order, under the unit's label. A section or part the audience manifest gives a `condensed` form arrives as its source bytes, not as the authored text. The heading of a section that loses only some of its parts arrives, with the lines between it and its first part. A section all of whose text is dropped arrives not at all, heading included. The ADR resident arrives whole as today, and the three units arrive in today's order
**so that** the spawn sheds only what the manifest says is addressed to the main session, and keeps every other byte of both rules with the heading that places it

### REQ-02: Only orchestrator-only text is left out, whatever the recipient's role

**When** the audience manifest classifies a section or part of the two units `core`, `role` (for any audience) or `no-actor`
**the system** delivers that text to every split recipient, whichever role it is. No `orchestrator-only` text of the two units reaches any split recipient through rule delivery, unless REQ-05 falls back to the whole unit. Among split recipients, what is delivered never depends on which role is spawning
**so that** the change removes exactly what the manifest classifies as the main session's, and every split recipient sheds the same text

### REQ-03: The main session's delivery is unchanged

**When** the main session starts (`SessionStart`) in a managed or an unmanaged scope
**and** a project blacklist may or may not be present, and rule delivery may be unimpaired or impaired (REQ-06)
**the system** delivers byte for byte the same strings as at the pipeline base, with both units whole
**so that** the session that orchestrates keeps both rules in full, and its always-loaded budget does not move

### REQ-04: Every spawn outside the split is unchanged

**When** a whole recipient starts in a managed scope (among them a fork, whose payload `agent_type` is `fork`, and `general-purpose`), a lean spawn starts, an `Explore` or `Plan` spawn starts, or any spawn starts in an unmanaged scope
**the system** delivers to it, from every hook registered for `SubagentStart`, exactly what it received at the pipeline base. A whole recipient in a managed scope gets the three managed core units whole and in order, under any impaired condition too. Everyone else gets nothing from rule delivery, and a lean plugin role gets its kernel strings unchanged byte for byte
**so that** no agent whose content the audit cannot read loses any text, and the switched roles' measured delivery stays exactly as the evidence that justified it

### REQ-05: A split that cannot be trusted falls back to the whole unit

**When** a split recipient starts in a managed scope
**and** for either unit, the split text cannot be established as exactly REQ-01's text for the unit's current source and the current audience manifest. That happens when the audience manifest is absent, unreadable or cannot be parsed, when anything else the split depends on is absent, unreadable or malformed, or when what would be delivered does not reflect the unit's current source text and the manifest's current classification of it (a kept or dropped span edited, added, removed or reclassified)
**the system** delivers that unit whole. Each unit is trusted on its own. A fault that bears on one unit's source alone, such as an edit to the intermediate-documents rule's source, leaves the other unit arriving as its split text. A fault in the audience manifest, such as an edit, absence or damage, may make either unit fall back, or both. For each unit the spawn receives either exactly the split text for the current source and manifest, or the whole unit. It never receives a split taken from an older source or manifest, a unit with more removed than REQ-01 prescribes, or part of a unit
**so that** a fault in the split costs tokens, never text

### REQ-06: The impaired floor still delivers to an inheriting spawn

**When** rule delivery is impaired: the kill switch is set, the hook's interpreter cannot import `PyYAML`, or the rules manifest is missing, unreadable, malformed or cannot be applied
**and** an inheriting spawn starts in a managed scope
**the system** still delivers all three managed core units, in order. For a split recipient, each of the two units arrives either exactly as its split text or whole. Under any impairment either one is acceptable, and nothing else is: never a split taken from an older source or manifest, never more removed than REQ-01 prescribes, never part of a unit. For a whole recipient, both arrive whole. The ADR resident arrives whole for both. An unmanaged scope still receives nothing
**so that** no impaired state costs an inheriting spawn a core procedure, and a missing parser never strips text

### REQ-07: A drift check refuses a tree whose spawn delivery disagrees with its sources

**When** the kernel checks run, wherever they run today (the `kernel-manifest` commit-time hook and the root suite in continuous integration)
**and** at the tree under check, what a split recipient in a managed scope would receive for either unit is anything other than REQ-01's split text for that tree's source and audience manifest, including a tree at which that spawn would fall back to the whole unit (REQ-05)
**the system** fails with a non-zero exit. When the check can parse every input it reads (both sources and the audience manifest) and the delivery still disagrees, the failure names the rule whose delivery disagrees and what disagrees. When an input cannot be parsed, a non-zero exit is enough, and the failure need not name a rule. On a tree where the delivery agrees, it reports no finding of this kind. A canary test plants each kind of disagreement the delivery can carry, shows the check failing on each, and shows it passing once the tree is restored
**so that** no edit to a source or to a classification can ship a spawn delivery that disagrees with them, and the runtime fallback stays a safety net, never a committed state

### REQ-08: The verifier reaches the tier signals through its own definition

**When** a `praxion:verifier` spawn in a managed project reaches its `Calibration Verdict` sub-step for a `Standard` or `Full` pipeline, after the change, and its rule delivery holds no `Process Calibration` text
**the system** gives it the `Signals` of all five tiers (`Direct`, `Lightweight`, `Standard`, `Full`, `Spike`) from its own definition. The sub-step's text either carries the signals, or names one file that carries them by a path the verifier can resolve from that project. A plugin path resolves under the plugin root, the same way the definition's other plugin paths do, whether or not the project holds the file. Tier for tier, the signals it reaches are word for word the protocol's `Signals` cell for that tier at the same tree. If they are a copy, the kernel checks fail, at the sites named in REQ-07, on any tier whose copy differs, and a canary shows that failure. The sub-step's output contract does not change: one `Retrospective` verdict of `correct`, `over-calibrated` or `under-calibrated`, plus a one-line evidence clause
**so that** the verdict, the main consumer of this move, judges a run's tier against the same signals the main session chose it by, now that `Process Calibration` no longer arrives at spawn

### REQ-09: A content-level consumer audit is recorded

**When** the change is complete
**the system** keeps a record that outlives this pipeline's working files. For each `orchestrator-only` entry of the two units (source, heading, part where it has one, and its stated reason), and for each split-recipient role (every plugin role at the change's head whose definition does not set the lean flag), the record states whether that role acts on the entry's text. A role acts on an entry when its content tells it to do something whose correct execution needs that text: citing it by name or link, applying its table or vocabulary, or deciding on its rule. The judgment comes from reading the content, not from matching section names. That content is the role's whole definition and the skills its definition loads at spawn, and the record quotes the acting line where there is one. For every pair that acts, the record states how that role reaches the text after the change: its own artifacts, or the entry's reclassification in the audience manifest. No such pair is left without a way to reach the text
**so that** "no loss of semantics" rests on evidence a reviewer can re-check, and a later trial of a held role starts from what its full arm really receives

### REQ-10: The shed text is counted at no cost

**When** the text shed per split recipient is counted
**the system** reports the count from a command that makes no model request and spends nothing. For each of the two units and in total, it gives the characters of the strings a split recipient receives (labels included) whole and split, their difference, and a token figure labelled with its basis (counted by a tokenizer, or estimated). The split figure equals the length of what rule delivery gives a split recipient at that tree. The count is recorded with the pipeline's evidence
**so that** the saving is known before any paid reading, and a paid startup probe stays the user's choice

### REQ-11: Every planned string fits and reaches the spawn

**When** an inheriting spawn's rule delivery is planned, split or whole
**the system** keeps every string within the 10,000-character inline limit. The slots registered for `SubagentStart` carry every planned string, so none is left unprinted, and each string opens with its label naming its unit and its place
**so that** the harness never swaps a delivered string for a file path, and no planned text is silently lost

### REQ-12: Both source rules stay whole

**When** the change is complete
**the system** keeps every section and part of the coordination protocol and the intermediate-documents rule that existed at the pipeline base in its file. The audience manifest still classifies every section and part, and its classifications are those at the base, except where a REQ-09 finding reclassifies an entry
**so that** the main session and any reader of a rule file see it whole, and the split lives only in what a split recipient receives

## Spec Question Answers

Round 0 was answered by the orchestrator on 2026-11-08. Every question is closed, and the requirement text has been amended to match.

Assumptions taken while writing the spec. These were stated, not asked, and A1 to A7 were confirmed in round 0:

- **A1, headings.** The manifest's cutting puts a section's heading line in none of its parts. REQ-01 therefore keeps the heading, and the blank lines up to the first part, whenever any part of the section arrives, so a kept part is never read as part of the section before it. A section whose every part is dropped is left out whole. The per-role kernels render parts without their heading. The spawn delivery deliberately differs from them here.
- **A2, condensed forms.** A `condensed` entry reaches a split recipient as its source bytes (Key Signal 1, "byte for byte as in its source"), never as the kernel's authored text.
- **A3, fallback granularity.** Fallback is per unit, and a delivered unit is either exactly the split or exactly whole. Under an impaired condition (REQ-06) the spec does not fix which of the two a split recipient receives, because that depends on what the split needs at spawn time, which is a design choice. Acceptance tests should take either one as the oracle, never anything else. Each unit is trusted on its own (REQ-05).
- **A4, scope of the audit.** The audit reads each split-recipient role's whole definition and the skill bodies it preloads at spawn. References a role loads on demand are left out, since a role reaches them by path, which the split does not touch.
- **A5, audit lifetime.** The audit records the state at this change's head. A plugin role added later would become a split recipient with no audit row. Holding the record current for later roles or reclassified entries is out of scope and is a candidate follow-up.
- **A6, `no-actor`.** The two units hold no `no-actor` entries today. Following the brief, only `orchestrator-only` text is left out, so a future `no-actor` entry would still arrive.
- **A7, the registry gap.** The registry row for `spawn-startup-tokens` lists none of the rule-delivery hook files and not the audience manifest. It stays declared under Footprints Not Measured. The design phase adds those paths to the row so the planner's footprint check sees this change.

### SQ-01: Kept table rows arrive without their header row

- **Kind:** specification (fidelity under "no loss of semantics")
- **Question:** `Coordination Pipeline` keeps the part that begins at its return-contract row, which holds the return-contract and completion-handshake rows. The table's header row and separator sit in the `orchestrator-only` part, next to the pipeline-diagram pointer. Is a split recipient receiving those two rows without a header within "no loss of semantics"?
- **Status:** answered, round 0 (orchestrator, 2026-11-08): the provisional answer is accepted.
- **Answer:** yes. The two rows describe themselves and arrive under their section heading (A1). The part boundary does not move.

### SQ-02: Who receives the split

- **Kind:** intent
- **Question:** Should agents whose content cannot be audited (project, user and other plugins' agents, built-ins, forks) receive the split?
- **Status:** answered, round 0 (orchestrator, 2026-11-08). The provisional answer was CHANGED.
- **Answer:** no. Only split recipients get the split: this plugin's own inheriting `praxion:<role>` spawns whose definition is read from this plugin, the roles the audit covers. Every other inheriting spawn gets the two units whole, as at the base. That includes a `praxion:<role>` spawn whose definition cannot be read, since the safe direction is whole delivery. The reason: "no loss of semantics" cannot be shown for an agent whose content cannot be audited. The evidence: of 111 inheriting spawns in this project's log since 2026-10-10, 109 were plugin roles, with 1 `general-purpose` and 1 fork, so the safe direction gives up about 2 percent of the saving.
- **Amended:** the Goal, the Acceptance Criteria, the Terms (split and whole recipients), REQ-01, REQ-02, REQ-04 (whole recipients unchanged), REQ-05 to REQ-07, REQ-10 and REQ-12. REQ-09's audit set is narrowed to the split-recipient roles.

### SQ-03: Role-filtered delivery is excluded

- **Kind:** intent
- **Question:** One of the brief's Stated Assumptions would let the architect choose role-filtered delivery to close the verifier gap, while Key Signal 5 asks for the verifier's own artifacts. Should role-filtered delivery stay available?
- **Status:** answered, round 0 (orchestrator, 2026-11-08): closed as decided.
- **Answer:** no role-filtered delivery (REQ-02). The verifier makes 78 of the 109 plugin-role spawns, so its `Calibration Verdict` path is this move's main consumer. REQ-08 now states its observable outcome precisely: all five tiers' signals reached from its own definition, word for word equal to the protocol's, a copy held equal by the kernel checks with a canary, and the verdict's output contract unchanged.

### Acceptance-design questions (answered 2026-11-08, orchestrator)

The acceptance design (outer loop a7867bcd) raised four specification questions. All are answered, and each is closed by amending the requirement text:

- **AD-SQ-01, how a fork is announced:** a fork's payload carries `agent_type` set to `fork`, as this project's log records from the payload. It is named on the Observable Surface, in the Terms and in REQ-04 as a whole recipient.
- **AD-SQ-02, "by its own standing":** each unit is trusted on its own, which is A3's per-unit fallback. An edit to one rule's source alone leaves the other arriving as its split text, while an edit to the audience manifest may make either fall back (REQ-05).
- **AD-SQ-03, impaired floor:** the design phase keeps the choice. Under any impairment a split recipient may receive the split or the whole unit, never anything else, and whole is always safe (REQ-06).
- **AD-SQ-04, refusal on damaged input:** if an input cannot be parsed, a non-zero exit is enough. A parseable disagreement must name the rule (REQ-07).

## Footprint Readings

From the pipeline's footprint log. The baseline rows were taken at `89052e66` and the final rows at `54a75662`, on the same basis (a tokenizer reading for the two token footprints).

| Criterion | Footprint | Bound | Baseline | Final | Result |
|---|---|---|---|---|---|
| FC-01 | always-loaded tokens | equal to the baseline | 19,918 tokens (tokenizer, claude-sonnet-5-5) | 19,918 | PASS |
| FC-02 | agent and skill listing tokens | at or below the baseline | 14,268 | 14,268 | PASS |
| FC-03 | prompt-size findings | at or below the baseline count, no fail finding | 3 warn, 0 fail | 3 warn, 0 fail | PASS |

Commands: `python3 scripts/measure_token_budget.py --json` (FC-01, FC-02) and `python3 scripts/check_agent_prompt_size.py --json` (FC-03). The three commits after the final reading (`2574737e`, `da259208`, `f3f55f93`) touch only hook code, scripts and acceptance drivers, none an always-loaded, listing or prompt-size path, and `python3 scripts/check_footprint_criteria.py audience-split --stage verify --base-ref f1f8adf1` exits 0 with no finding at the archive head.

Declared as not measured, each with its reason: `spawn-startup-tokens` (every reading starts a role and spends subscription budget, so a paid probe stays the user's choice; the shed count stands in for it), `hook-latency` (no instrument; the spawn hooks keep their registered time limits) and `spawn-count` (the only command counts a pipeline already run, and this change alters no spawning policy).

## Shed Count

What one split recipient's `SubagentStart` delivery sheds, counted at no cost with no model request (`python3 scripts/count_spawn_shed.py --json`). Taken at `54a75662`; the character figures and the estimate were re-run at `f3f55f93` and are identical. The tokenizer column is the free `count_tokens` endpoint and was read once, at `54a75662`.

| Unit | Whole chars | Split chars | Shed chars | Shed tokens (tokenizer) | Shed tokens (estimate) |
|---|---|---|---|---|---|
| `swe/swe-agent-coordination-protocol` | 18,758 | 4,690 | 14,068 | 5,335 | 3,936 |
| `swe/agent-intermediate-documents` | 4,162 | 3,064 | 1,098 | 473 | 310 |
| total | 22,920 | 7,754 | 15,166 | 5,808 | 4,246 |

Reach: this project's log since 2026-10-10 shows 109 inheriting `praxion:` spawns, all split recipients, out of 111 inheriting spawns (the other two were one `general-purpose` and one fork). That is about 0.63M tokens a month no longer delivered (109 × 5,808). The protocol unit now fits one delivered part instead of two.

**Startup probe (approved by the user, 2026-11-09, subscription token, no API-key spend).** `measure_startup_payload.py agent:verifier --strict-mcp-config --cwd <main checkout> --plugin-dir <checkout> --json` was run once with the unmerged main checkout (`f1f8adf1`) and once with this branch (`f3f55f93`) as the plugin. It was not recorded to `startup_baseline.json`.

| Target | Before | After | Change |
|---|---|---|---|
| main session | 60,954 | 60,954 | 0 |
| `agent:verifier` (a split recipient) | 67,876 | 62,169 | -5,707 (-8.4%) |

The probe's drop agrees with the free count, 5,808 tokens, to within about 100 tokens: the labels and joins of the delivered parts.

## Traceability

Rendered from `traceability.yml` at archival. There were no un-reconciled fragments and no requirement carried `architectural_elements:`, so the matrix has four columns. A requirement counts as tested when its unit tests and its outer-loop (acceptance) nodes together are non-empty: the `Test(s)` cell lists both kinds, each grouped by file with the count and the node names. `Status` is the verifier's reading across the first pass and the re-verification, judged against the root run of 17,706 passed and 37 skipped (0 failed) at the first verified head and 17,719 passed and 37 skipped at `da259208`.

| Requirement | Test(s) | Implementation | Status |
|---|---|---|---|
| REQ-01 | unit: `scripts/test_kernel_spawn_split.py` (7: test_a_dropped_section_goes_from_its_heading_to_the_next_heading, test_a_dropped_part_runs_to_the_next_part_and_the_heading_stays, test_a_section_all_of_whose_parts_are_dropped_goes_heading_and_all, test_a_dropped_subsection_leaves_its_parent_and_the_section_after_it, test_a_heading_inside_a_fence_is_no_section_to_drop, test_a_condensed_form_changes_nothing_kept_text_is_source_bytes, test_the_expected_split_is_cut_from_the_body_the_hook_reads); unit: `scripts/test_generate_kernels.py` (1: test_a_unit_that_loses_a_dropped_section_is_written_with_the_digests_the_hook_checks); acceptance: `tests/acceptance/test_split_recipients_receive_the_rules_without_orchestrator_only_text.py` (6: test_a_split_recipient_receives_each_rule_as_its_split_text, test_no_orchestrator_only_section_heading_reaches_a_split_recipient, test_a_section_losing_only_some_parts_keeps_its_heading_and_its_kept_part, test_the_adr_resident_arrives_whole_after_the_two_rules, test_a_role_spelling_the_lean_flag_other_than_literal_true_is_a_split_recipient, test_a_project_blacklist_naming_the_core_rules_leaves_a_split_recipient_its_split_text); acceptance: `tests/e2e/test_a_rule_edit_reaches_each_audience_after_regeneration.py` (1: test_a_split_recipient_receives_the_edited_rule_as_its_split_text) | `scripts/kernel_spawn_split.py::split_text, expected_split`; `hooks/inject_rules.py::_received_units, _split_units, _read_rule_body, _read_bytes, _parsed_split, _floor_delivery, _manifest_delivery` | PASS |
| REQ-02 | acceptance: `tests/acceptance/test_split_recipients_receive_the_rules_without_orchestrator_only_text.py` (1: test_what_a_split_recipient_receives_does_not_depend_on_its_role) | `hooks/inject_rules.py::_received_units, _split_units, _read_rule_body, _read_bytes, _parsed_split, _floor_delivery, _manifest_delivery` | PASS |
| REQ-03 | acceptance: `tests/acceptance/test_every_delivery_outside_the_split_is_unchanged.py` (2: test_the_main_session_receives_the_same_rule_strings_as_at_the_base, test_an_impaired_main_session_receives_the_same_rule_strings_as_at_the_base); acceptance: `tests/e2e/test_a_rule_edit_reaches_each_audience_after_regeneration.py` (1: test_the_main_session_receives_the_edited_rule_whole) | `hooks/inject_rules.py::_received_units, _split_units, _read_rule_body, _read_bytes, _parsed_split, _floor_delivery, _manifest_delivery` | PASS (the first pass's CRLF finding closed by `2574737e`) |
| REQ-04 | unit: `hooks/test_rule_delivery_split.py` (3: test_only_a_read_plugin_definition_that_keeps_the_instruction_files_splits, test_both_recipient_kinds_are_planned_the_three_core_units, test_the_other_two_kinds_are_planned_nothing); acceptance: `tests/acceptance/test_every_delivery_outside_the_split_is_unchanged.py` (5: test_a_whole_recipient_receives_every_spawn_string_as_at_the_base, test_a_plugin_role_whose_definition_cannot_be_read_receives_every_spawn_string_as_at_the_base, test_an_impaired_whole_recipient_receives_every_spawn_string_as_at_the_base, test_a_spawn_without_instruction_files_receives_byte_for_byte_what_the_base_delivered, test_no_spawn_in_an_unmanaged_scope_receives_rule_text); acceptance: `tests/e2e/test_a_rule_edit_reaches_each_audience_after_regeneration.py` (1: test_a_whole_recipient_receives_the_edited_rule_whole) | `hooks/_rule_delivery.py::parse_agent_kind, _wanted_ids`; `hooks/inject_rules.py::_received_units, _split_units, _read_rule_body, _read_bytes, _parsed_split, _floor_delivery, _manifest_delivery` | PASS |
| REQ-05 | unit: `hooks/test_rule_delivery_split.py` (12: test_a_unit_whose_digest_disagrees_receives_its_whole_body_alone, test_a_manifest_that_changed_gives_every_unit_whole, test_a_body_that_changed_since_the_cut_receives_whole_while_the_other_keeps_its_split, test_a_unit_with_no_entry_receives_whole_while_the_other_keeps_its_split, test_every_unit_with_a_matching_entry_receives_its_split_text, test_an_artifact_that_is_not_the_schema_parses_to_none, test_no_artifact_gives_every_unit_whole, test_no_manifest_digest_gives_every_unit_whole, test_a_trusted_split_distrusts_no_unit, test_a_unit_whose_digest_disagrees_is_named_alone, test_a_split_cut_under_another_manifest_distrusts_every_unit_it_holds_in_order, test_a_unit_with_no_entry_is_never_named_while_a_stale_one_is); unit: `scripts/test_kernel_spawn_split.py` (3: test_the_hook_parses_the_artifact_and_trusts_a_split_cut_for_its_body, test_the_generator_reads_the_audience_manifest_the_hook_digests, test_a_crlf_source_is_digested_over_the_body_the_hook_reads); unit: `scripts/test_generate_kernels.py` (2: test_the_live_split_is_what_the_hook_trusts_for_every_unit_it_lists, test_check_bites_on_a_hand_edited_split_and_passes_once_regenerated); unit: `hooks/test_inject_rules_split.py` (11: test_an_artifact_that_cannot_be_read_or_parsed_leaves_each_unit_whole, test_an_artifact_cut_under_another_audience_manifest_leaves_each_unit_whole, test_a_wrong_unit_digest_leaves_that_unit_whole_and_the_other_split, test_a_rule_edited_after_the_split_arrives_whole_while_the_other_keeps_its_split, test_an_audience_manifest_changed_or_unreadable_leaves_each_unit_whole, test_the_shipped_artifact_is_trusted_for_the_shipped_rules_read_from_the_plugin_root, test_a_split_text_no_digest_can_be_taken_over_leaves_every_unit_delivered_whole, test_a_unit_whose_split_is_distrusted_is_named_on_stderr_and_the_other_is_not, test_a_missing_artifact_is_reported_for_a_managed_split_recipient, test_a_missing_artifact_is_not_reported_for_an_unmanaged_split_recipient, test_a_crlf_rule_is_trusted_by_the_digest_the_generator_takes_over_its_bytes); acceptance: `tests/acceptance/test_an_untrusted_split_falls_back_to_the_whole_unit.py` (5: test_a_damaged_split_input_leaves_each_rule_split_or_whole, test_an_unreadable_audience_manifest_leaves_each_rule_whole, test_an_audience_manifest_of_the_wrong_shape_leaves_each_rule_whole, test_an_edited_rule_or_classification_arrives_split_for_the_current_tree_or_whole, test_the_rule_an_edit_did_not_touch_still_arrives_as_its_split_text) | `hooks/_rule_delivery.py::spawn_units, distrusted_units, parse_spawn_split, rule_body`; `scripts/kernel_spawn_split.py::render_spawn_split, spawn_split_artifact`; `claude/kernels/spawn_split.json`; `hooks/inject_rules.py::_received_units, _split_units, _read_rule_body, _read_bytes, _parsed_split, _floor_delivery, _manifest_delivery` | PASS (the runtime-bind finding closed as a declared limit) |
| REQ-06 | unit: `hooks/test_rule_delivery_split.py` (3: test_choosing_mutates_neither_the_units_nor_the_split, test_a_split_text_goes_through_the_unchanged_framing, test_a_rule_body_is_the_file_without_its_leading_frontmatter); unit: `hooks/test_inject_rules_split.py` (4: test_a_split_recipient_on_the_impaired_floor_still_receives_the_split, test_a_whole_recipient_on_the_impaired_floor_still_receives_the_units_whole, test_a_split_text_no_digest_can_be_taken_over_leaves_every_unit_delivered_whole, test_a_split_recipient_receives_each_split_unit_as_its_stored_split_text); acceptance: `tests/acceptance/test_an_untrusted_split_falls_back_to_the_whole_unit.py` (2: test_an_impaired_split_recipient_still_receives_the_three_core_units_in_order, test_an_impaired_split_recipient_in_an_unmanaged_scope_receives_no_rule_text) | `hooks/_rule_delivery.py::spawn_units, rule_body`; `hooks/inject_rules.py::_received_units, _split_units, _read_rule_body, _read_bytes, _parsed_split, _floor_delivery, _manifest_delivery` | PASS |
| REQ-07 | unit: `scripts/test_check_kernel_manifest_spawn_split.py` (7: test_the_live_checkout_delivers_its_split_as_its_sources_give_it, test_a_disagreeing_split_is_refused_naming_each_unit_it_reaches, test_a_fallback_is_reported_as_the_whole_unit_from_its_source, test_a_trusted_wrong_split_is_reported_at_its_first_differing_line, test_an_artifact_that_cannot_be_read_is_refused_without_naming_a_unit, test_the_command_exits_non_zero_on_an_artifact_that_cannot_be_read, test_a_checkout_restored_after_a_plant_passes); acceptance: `tests/acceptance/test_the_drift_check_refuses_a_spawn_delivery_that_disagrees.py` (4: test_the_checks_verdict_on_this_checkout_agrees_with_what_a_split_recipient_receives, test_a_planted_disagreement_is_refused_naming_its_rule_and_an_agreement_passes, test_a_checkout_restored_after_a_plant_delivers_the_split_and_passes, test_a_damaged_split_input_that_makes_a_spawn_fall_back_is_refused); acceptance: `tests/e2e/test_a_rule_edit_reaches_each_audience_after_regeneration.py` (1: test_the_kernel_checks_pass_after_the_regeneration) | `scripts/check_kernel_manifest.py::spawn_split_findings, _drift_detail, _spawn_reading, _unit_reading, _read_spawn_split, check`; `.pre-commit-config.yaml::kernel-manifest` | PASS |
| REQ-08 | acceptance: `tests/acceptance/test_the_verifier_reaches_the_tier_signals_through_its_definition.py` (4: test_one_carrier_the_sub_step_reaches_holds_every_tiers_signals_word_for_word, test_the_verifiers_rule_delivery_holds_no_tier_table, test_a_copy_of_a_tiers_signals_that_differs_from_the_protocol_is_refused, test_the_calibration_verdicts_output_contract_is_unchanged) | `agents/verifier.md`; `agents/skill-genesis.md`; `rules/_audience.yaml` | PASS (the copy-drift nodes skip by design: the definition holds a pointer, not a copy) |
| REQ-09 | (none; see the note below the table) | `ADR dec-draft-25c1476d § Consumer Audit`; `agents/skill-genesis.md` | VERIFIED BY JUDGMENT (no test node; see the note below the table) |
| REQ-10 | unit: `scripts/test_count_spawn_shed.py` (12: test_a_unit_is_counted_whole_and_split_with_its_label, test_the_total_is_the_sum_over_the_units, test_only_units_with_a_stored_split_are_counted, test_a_unit_whose_split_is_distrusted_is_counted_whole_and_named, test_the_default_token_figure_is_the_offline_estimate, test_the_tokenizer_is_used_only_when_asked_and_labelled, test_the_tokenizer_without_a_key_is_an_input_error, test_an_unreachable_tokenizer_is_an_input_error_not_a_silent_estimate, test_plain_output_is_one_line_per_unit_then_the_total, test_the_json_report_has_the_contract_shape, test_a_missing_input_is_an_input_error_naming_it, test_an_unparseable_split_artifact_is_an_input_error); acceptance: `tests/acceptance/test_the_shed_text_is_counted_at_no_cost.py` (6: test_the_split_figure_is_what_a_split_recipient_receives, test_the_whole_figure_is_what_a_whole_recipient_receives, test_each_rules_difference_is_its_whole_less_its_split, test_the_total_is_the_sum_over_both_rules, test_the_token_figure_is_labelled_with_its_basis, test_counting_makes_no_model_request_and_needs_no_network) | `scripts/count_spawn_shed.py::main, shed_figures` | PASS |
| REQ-11 | acceptance: `tests/acceptance/test_an_untrusted_split_falls_back_to_the_whole_unit.py` (2: test_every_rule_string_a_spawn_receives_is_within_the_inline_limit, test_every_part_a_label_announces_reaches_the_spawn_once_and_in_order) | `hooks/inject_rules.py::_received_units, _split_units, _read_rule_body, _read_bytes, _parsed_split, _floor_delivery, _manifest_delivery` | PASS |
| REQ-12 | acceptance: `tests/acceptance/test_both_source_rules_stay_whole.py` (3: test_every_section_heading_at_the_base_is_still_in_the_rule, test_every_part_at_the_base_still_begins_a_line_of_the_rule, test_the_audience_manifest_still_classifies_every_section_and_part_of_the_base) | `scripts/generate_kernels.py::plan_kernels`; `claude/kernels/spawn_split.json` | PASS |

REQ-09 has no test node by design. It is not black-box testable: it asks for a content-level audit, a judgment read from the content of each split-recipient role. Its record is the spawn-split ADR's `## Consumer Audit` (13 `orchestrator-only` entries against 13 roles, two acting pairs found and closed by plugin-path pointers in the verifier's and `skill-genesis`'s definitions, and a recorded near miss for the implementation planner). The verifier re-read the two highest-volume recipients independently and agreed.

**Coverage**: all 12 requirements are covered. Eleven carry acceptance evidence and 6 of them also carry recorded unit evidence (65 unit entries and 44 acceptance entries in the map); REQ-09 is verified by judgment. No requirement is left without evidence.

## Key Decisions

One ADR draft carries the architectural decisions (`dec-draft-25c1476d`); the entries below are from `LEARNINGS.md § Decisions Made`, the step learnings and the verifier's rulings.

**[systems-architect] Build-time spawn split as the channel (architectural; `dec-draft-25c1476d`)**: `generate_kernels.py` writes `claude/kernels/spawn_split.json`. The hook reads it as JSON and uses a unit's split only when the digests of its body, the audience manifest and the split text match; the new kernel invariant I11 refuses drift. **Why**: it keeps one manifest reader and one section cutter, keeps the hook stdlib and pure, keeps the split when PyYAML is missing, and keeps the single regeneration step. **Alternatives**: hook-time filtering from the manifest (a second YAML reader and cutter inside a hook, loses the split without PyYAML, adds latency to every spawn); role-filtered delivery (rejected in round 0: it adds a dimension every later trial would have to measure).

**[systems-architect] Whole-file digests for currency**: the per-unit body sha256 plus the sha256 of the whole audience manifest. **Why**: stdlib and conservative; an unrelated manifest edit only costs savings until regeneration, which the gate refuses to commit. **Alternatives**: per-unit manifest-entry digests (they need YAML in the hook).

**[systems-architect] The fallback is exactly the split or exactly whole, per unit**: this gives the drift gate its oracle for free, since a stale split falls back to whole and the gate fails a fallback. The same rule applies on the impaired floor.

**[systems-architect] Verifier pointer over a copy**: the `Calibration Verdict` item links Process Calibration by plugin path. **Why**: one source of truth, nothing to drift, no new check. **Alternatives**: a copy held equal by a canaried check. The cost is that nothing mechanical shows the verifier follows the pointer; the ADR names this for the next verifier trial's notes.

**[systems-architect] Audited-role guard deferred**: no recorded audited-role set in this change. **Why**: it would change the recipient set after the committed acceptance design, and every current role is audited. **Alternatives**: in scope now. Carried as the ledger row `td-603`.

**[implementation-planner] Step ordering and light-review placement (process decisions, no ADR)**: manifest and definition text first, then the pure layer, the cutter and artifact, the hook edge, the gate and the count command, because the artifact digests the manifest, the generator imports the pure layer's body reader, and the gate's first scenario compares the real delivery with the check's verdict. `review: force` and `tier: H` went on the hook edge and the drift check only, the hook path every session runs through and the commit gate for everyone. **Alternatives**: the hook edge before the generator (it would sit unused with no artifact); also reviewing the pure layer (rejected: pure, unit-tested, and the delivery-unchanged guards run as a regression net).

**[implementation-planner] The count defaults to the offline estimate**: the counter's tokenizer path reaches the network when a key is set, so the estimate is the default and the tokenizer an opt-in `--tokenizer` flag that fails loudly without a key. **Why**: the command must need no network and make no model request. **Alternatives**: the tokenizer by default (one default in one file would change it).

**[implementer] One substitution point and a catch-all at the edge**: `_received_units` runs in both the manifest path and the floor, and wraps the split so that neither depends on it succeeding; `RecursionError` (the implementer's find) and a lone surrogate in the artifact (the Step 6 light review's first finding) are treated as an unusable artifact. **Why**: a split fault must cost tokens, never text.

**[rework] One source reading everywhere (after the verifier's CRLF finding)**: every edge now reads rule files through `decode_source`, which decodes UTF-8 and translates CRLF and lone CR to LF, the same as `read_text` did at the base, and digests are taken over the decoded text. **Why**: reading raw bytes for every audience changed the main session's bytes on a checkout with `core.autocrlf`, and sent every split recipient to whole delivery. **Alternatives**: pinning `eol=lf` for the rules in `.gitattributes`.

**[verifier] A declared limit: the stored text's digest does not bind it to its body**: `text_sha256` is an integrity check, so a consistent hand edit of the stored split and its digest is delivered at spawn; only I11, which re-derives the split from the sources, refuses it at commit. The ADR's Consequences now state this. **Why**: the plugin's own files are trusted at spawn, and the same writer can edit the rules.

## Verification and Rework

First pass at `54a75662` (16 commits): **FAIL** on one convention finding, with nine WARNs. F1: the new acceptance driver `tests/acceptance/drivers/audience_split.py` was 904 lines against the 800-line ceiling, and no gate saw it because the production size guards do not cover drivers. W1: on a CRLF checkout the main session's bytes changed and the split never applied. W2 to W9 covered a planner near miss for the Consumer Audit, a new pyright error, a `TEST_RESULTS.md` shape, duplicated trust and namespace logic, shallow-CI skips of the base-comparison guards, a journey-node mapping, an observation class and the runtime bind above.

Rework. `2574737e` closed W1 (one decoder for every edge) and W5 (`trusted_splits` is the single trust decision, `is_plugin_role` the single namespace test). `da259208` closed F1 by splitting the driver into a 151-line facade over `audience_split_{oracle,delivery,plants,shed}.py` (all under 800 lines, no test file changed) and closed W3. The ADR draft's Consequences and Consumer Audit absorbed W9 and W2. `f3f55f93` makes a non-UTF-8 audience manifest an input error (exit 2) in the shed count, the case the re-verification left as an advisory note.

Re-verification at `da259208`: **PASS WITH FINDINGS**. Root `17719 passed, 37 skipped`, eval `4296 passed`, task-chronograph `128 passed`, pyright 21 errors on the touched files, all present at the base (24 there), `check_state_ledgers.py` with no blocking violation. The verifier corrected one claim of its own first report: the planner's definition does name the spawn budget, so the planner acts on its own text, as the ADR reads it. `f3f55f93` came after the re-verification and was not re-read by the verifier; it adds one guard and its test to `scripts/count_spawn_shed.py`.

The pre-existing failure in the baseline, `scripts/test_mutation_sensor.py::TestRealMutmutSmoke::test_real_run_reports_survivors_and_leaves_repo_coverage_untouched`, was environmental (the worktree had no `.venv` when the baseline ran) and passes in the final root run. The 74 other baseline failures were this pipeline's own red outer-loop nodes, all green at the end.

## Open Findings

None blocks the merge. Rows are in `.ai-state/TECH_DEBT_LEDGER.md`; `td-607` is resolved by `da259208` and moves to the resolved ledger at post-merge.

- **`td-603`** (suggested, coverage-gap): a plugin role added after the split, or a split recipient whose definition changes, receives the split with no consumer audit behind it. Record the audited role set with a digest of each definition beside the split, so an unlisted or changed role receives the whole units until re-audited, and have the kernel gate name it.
- **`td-605`** (suggested): a `review: force` step whose blocked work the orchestrator commits outside the loop can never get its light review through the driver. Step 6's first review round ran outside the loop for this reason.
- **`td-606`** (suggested, coverage-gap): the acceptance designer never searched the existing outer-loop tests that pin the surface the spec changes; two older suites encoded the old contract and cost two blocked attempts and two Spec Questions. The same row asks whether running a base-commit entry point to observe its output is an allowed read (verifier W8).
- **`td-608`** (suggested, drift): the `.ai-state/DESIGN.md` decision checkpoint stays at `dec-390`, with 56 architecture-bearing ADRs after it not folded or dispositioned.
- **`td-609`** (suggested, coverage-gap): the guards that compare today's deliveries with the base commit's hooks skip in CI, because the `test-root` job clones shallow (verifier W6). They run only locally.
- **`td-604`** (suggested, orchestrator-raised): the step-loop Stop guard blocked a Stop eight times while a background `record` waited on its gate run.
- Two verifier WARNs end with the pipeline's working files and get no row: the `TEST_RESULTS.md` shape (nine findings in driver-written sections, and no section for the final full runs) and the journey nodes' `acceptance:` mapping against the scenario tags.

## Gotchas Worth Keeping

- Any edit to the audience manifest, or to either source rule, sends the matching unit (the manifest: both) to whole delivery until `python3 scripts/generate_kernels.py` is re-run, and the gate refuses to commit the stale tree. The step that edits sources must run before the step that writes the artifact.
- The `kernel-manifest` hook's `files:` read set is pinned by `_gate_code()` in `scripts/test_check_kernel_manifest.py`, which computes the gate's real imports at run time; a new import in the checker forces the `.pre-commit-config.yaml` edit in the same step.
- The gate gathers every reader's evidence before it judges an invariant, so a reader that cuts sections must defer a part-prefix error as a value; raised, it turns I1's finding (exit 1) into an input error (exit 2).
- Reading rule files as raw bytes is not the same as `read_text` on a CRLF checkout, and `.editorconfig` does not govern a git checkout. Any requirement of byte identity needs one shared decoder at every edge.
- A pocket command from `resolve_test_scope.py` takes extra flags inside its subshell; flags after the closing parenthesis are a shell parse error and the pocket silently does not run.
- `pyright` is not installed in the project environment; run it as `uv run --with pyright pyright <files>`. It was not green at the base (24 errors on the touched files), so a "stays green" guard needs to read "no new errors against the base".
- The base-comparison acceptance guards skip in a shallow CI clone. They hold the unchanged-delivery claim locally only until `td-609` is done.

## Follow-up

- **Release checklist**: add a note to `.ai-state/kernel_adoption.yaml` that a held role's full arm is now the split delivery, so a later trial of a held role starts from what its full arm really receives (planned at release, so not due in this pipeline).
- **Next verifier trial**: note that the Calibration Verdict reaches the tier signals through a pointer it has to follow, and that nothing mechanical shows it does.
- **Next planner trial**: note the near miss recorded in the ADR's Consumer Audit, the planner's `Spawn estimate` line, whose figures reach it through its own definition.
- The audited-role set and audit freshness (`td-603`) are the named follow-up of the audit's lifetime assumption.
