---
diataxis: explanation
audience: developer
---

# Praxion Context-Engineering Roadmap — Derived from the 2026-05-12 Comparison Study

> **What this is.** The actionable output of the 2026-05-12 context-engineering comparison study in `docs/context-prj-comparison-2026-05-12/` ([`05-comparison.md`](../docs/context-prj-comparison-2026-05-12/05-comparison.md), grounded in [`00-karpathy-critique.md`](../docs/context-prj-comparison-2026-05-12/00-karpathy-critique.md) and the four source analyses, with Claude Code behavior verified in [`08-claude-code-behavior-verification.md`](../docs/context-prj-comparison-2026-05-12/08-claude-code-behavior-verification.md)). It lists **six headline items** plus a small parked appendix — the genuinely adoptable ideas, each scoped to a concrete Praxion artifact, with a "done when" and a budget impact. Everything the study explicitly *rejected* (scope mismatches, non-goals, things Praxion already covers as well or better) is in [`06-not-comparable.md`](../docs/context-prj-comparison-2026-05-12/06-not-comparable.md) — read it first if you're tempted to add something not on this list.
>
> **This is the working copy at `.ai-state/ROADMAP.md`** (cross-references below are re-pathed for this location); the source-of-truth is [`07-praxion-roadmap.md`](../docs/context-prj-comparison-2026-05-12/07-praxion-roadmap.md) in `docs/context-prj-comparison-2026-05-12/`. This roadmap is *narrower* than a full `/roadmap` audit (which the `roadmap-cartographer` would write at the project root): it covers project-management artifacts (agents, rules, skills, commands, CLAUDE.md) and context engineering, not the whole project.

---

## Principles governing this roadmap

1. **Enrich before adding.** The externals are tiny single-artifact repos; Praxion is an ecosystem. ~80% of these items are "enrich an existing skill / canonical block." New artifacts appear only where there's a genuine quality/guarantee gap — and they're in the *parked* appendix, not the top six.
2. **Verify before committing.** Two findings needed confirmation against the current Claude Code build before they could be trusted. Done — see [`08`](../docs/context-prj-comparison-2026-05-12/08-claude-code-behavior-verification.md). The folklore numbers (the "~150–200 instruction ceiling", the "43K/93K/50K" session breakdown) did **not** survive verification and are explicitly *not* imported (see [`06`](../docs/context-prj-comparison-2026-05-12/06-not-comparable.md) §3).
3. **Budget discipline = relocate, don't delete (the three-step cut protocol).** When trimming any always-loaded surface: **(1)** identify a compress-candidate → **(2)** try to compress it in-place → **(3)** if the compression gain is small, *relocate* the content to a progressive-disclosure surface (skill body, reference file, agent prompt) so **zero signal is lost**. Praxion's consistency, coherence, rigor, and guarantees rank above the "applied in >30% of sessions" heuristic — the scaffolding exists precisely as a guardrail against stochastic-model mistakes, so an over-aggressive cut is a regression, not a win. Target: **the net always-loaded delta from this entire roadmap is ≤ 0** (P6 pays for P2/P3).
4. **Don't mis-attribute Karpathy.** Behavioral items here cite the verbatim January 2026 X-post failure modes (which *are* Karpathy); they do not cite `forrestchang/andrej-karpathy-skills` (which Karpathy did not write or endorse). See [`00`](../docs/context-prj-comparison-2026-05-12/00-karpathy-critique.md).

## How to read an item

Each item carries: **Rationale** (why) · **Source** (which external + the dimension ID from [`05`](../docs/context-prj-comparison-2026-05-12/05-comparison.md)) · **Target** (which Praxion file(s)) · **Effort** (S/M/L) · **Depends on** · **Done when** (acceptance) · **Budget** (always-loaded delta) · **Strengthens** (which Praxion guarantee/process) · **Execution tier** (Praxion process calibration) · **Status** (checkbox).

---

## P1 — [Defensive · do first] Path-scoped-rule Read-only-trigger: document + mitigate · ☑ done (2026-05-12)

> **Done 2026-05-12.** Caveat documented in `rules/CLAUDE.md` (next to the `paths:` convention), `skills/rule-crafting/SKILL.md` (new "Path-Scoped Rules: Read-Only Loading Trigger" section + `<!-- last-verified -->` marker), `CLAUDE.md § Known Claude Code Limitations` (new bullet, issue links, `td-033` ref). "Read an existing sibling before creating a new file" mitigation added to the Constraints sections of `agents/implementer.md`, `agents/doc-engineer.md`, `agents/test-engineer.md`. Windows caveat (#21858) added to `docs/existing-project-onboarding.md § Limits and known issues`. Debt row `td-033` (important / `other` / owner-role `unassigned` — gated on upstream #38487) added to `.ai-state/TECH_DEBT_LEDGER.md`. Optional `InstructionsLoaded`/`PostToolUse(Write)` hook follow-up left unscheduled per the lean recommendation.

**Rationale.** Verified ([`08`](../docs/context-prj-comparison-2026-05-12/08-claude-code-behavior-verification.md) V1, official docs + GitHub issues [#23478](https://github.com/anthropics/claude-code/issues/23478)/[#38487](https://github.com/anthropics/claude-code/issues/38487)/[#16853](https://github.com/anthropics/claude-code/issues/16853)): path-scoped rules (`paths:` frontmatter) inject **only when Claude reads a matching file** — not on Write/Edit/MultiEdit. So an agent that *creates* a new file via Write without first reading a matching sibling misses the rule: a new `.py`/`.ts` misses `coding-style.md`; a new doc misses `readme-style.md` / `diagram-conventions.md` / `html-output-conventions.md` / `aac-dac-conventions.md`; a new `.github/*.md` misses `pr-conventions.md`; new files miss `id-citation-discipline.md`, `staleness-policy.md`, etc. This is the one finding that touches Praxion's *guarantee* surface — the rules-as-guardrails contract — directly. Moderate severity (agents usually read files in a directory before working there, which incidentally loads the rule), real for greenfield file creation.

**Source.** abhishekray07/claude-md-templates — dim B4. (Not a "Karpathy idea"; it fell out of a careful read of that repo's `principles.md` + corroborating GitHub issues.)

**Target.**
- `rules/CLAUDE.md` — add the Read-only-trigger caveat next to the existing `paths:` frontmatter note.
- `skills/rule-crafting/SKILL.md` (and/or a reference) — document the limitation, the symptom (silent miss on file creation), and the mitigation.
- `CLAUDE.md` § "Known Claude Code Limitations" — add a bullet (alongside the existing `Explore`/worktree entries), with the issue links and a `td-NNN` reference.
- `agents/implementer.md`, `agents/doc-engineer.md`, `agents/test-engineer.md` — add a one-line process mitigation: *"Before creating a new file in a directory, read an existing sibling (or, if none, a canonical example elsewhere) so path-scoped rules for that file type load into context."*
- `.ai-state/TECH_DEBT_LEDGER.md` — add a `td-NNN` row (writer: orchestrator or verifier per the ledger rule): "Path-scoped rules don't fire on Write/Edit — greenfield file creation misses `coding-style`/`readme-style`/etc.; mitigated by agent-prompt instruction; upstream issues open."
- Onboarding/install docs (`docs/existing-project-onboarding.md` or `rules/CLAUDE.md`) — a one-line **Windows caveat**: per [#21858](https://github.com/anthropics/claude-code/issues/21858), `paths:` frontmatter in `~/.claude/rules/` is ignored on Windows; Windows users should use project-level `.claude/rules/` symlinks. (Not reproduced on macOS/Linux — see [`08`](../docs/context-prj-comparison-2026-05-12/08-claude-code-behavior-verification.md) V2.)

**Effort.** S. **Depends on.** Nothing. **Budget.** ~neutral (a few lines in `rules/CLAUDE.md` and CLAUDE.md; the rest is on-demand or agent-prompt).

**Done when.** The caveat is documented in all five surfaces above; the three agent prompts carry the mitigation line; a `td-NNN` row exists; the Windows note is in the install/onboarding docs. *Optional follow-up (not blocking):* install an `InstructionsLoaded` hook in a sandbox to empirically log which path-scoped rules load in a typical pipeline run, and decide whether a `PostToolUse(Write)` "you just created `<file>` — `<rule>` applies, recall: …" hook is worth the maintenance cost (community workaround; lean: not unless the agent-prompt mitigation proves insufficient).

**Strengthens.** The rules-as-guardrails guarantee — closes a silent hole where Praxion's coding/testing/doc/PR conventions don't reach greenfield file creation.

**Execution tier.** Direct (per-file edits) — bundle the doc edits + agent-prompt edits into one focused change; the `td-NNN` row is a separate orchestrator/verifier write.

---

## P2 — [Thin-tier · high value] Direct/Lightweight behavioral micro-scaffolding + onboarded-CLAUDE.md template enrichment · ☑ done (2026-05-12)

> **Done 2026-05-12.** New `claude/canonical-blocks/project-essentials.md` block (registered in `scripts/sync_canonical_blocks.py`; `--check` green, 38 sync tests pass), mirrored across `commands/onboard-project.md` + `commands/new-project.md`: adds to onboarded projects' `CLAUDE.md` a `## Verification` ordered-check stanza, a `## Frequent operations` stanza, a "when I correct you, propose a durable rule for review" line, and the "this `CLAUDE.md` is the index; `docs/` and the skills it points to are the library" framing. `skills/software-planning/references/tier-templates.md` gained the criteria-first micro-template ("state 'done' in one line as a testable assertion; tag multi-step work with `→ verify: <check>`") in the Lightweight specifics. `docs/existing-project-onboarding.md` + `docs/greenfield-onboarding.md` now list all five `CLAUDE.md` blocks and carry the <200-lines-per-`CLAUDE.md`-file benchmark note (HumanLayer ~57 / typical good ~80–100 / over-long ~230). Praxion's own `CLAUDE.md` gained a `## Frequent operations` section (dogfooding; ~150 always-loaded tokens — flagged for reclamation by P6).

**Rationale.** Praxion's strongest expression of "criteria-first / verify-before-done" lives in the **Standard/Full** pipeline (REQ-IDs, `traceability.yml`, acceptance criteria, the `verifier`). At **Direct and Lightweight** tiers — the *most common* tiers, where no `WIP.md`/`IMPLEMENTATION_PLAN.md` exists — there is no in-place equivalent. forrestchang's `step → verify:` micro-template and abhishekray's `## Verification` stanza are exactly the right weight there. Separately, danielrosehill's "Common Tasks" pattern and abhishekray's "after a mistake, record a durable rule" habit are cheap, high-signal additions to the `CLAUDE.md` template `/onboard-project` writes into user projects. *(This is the gap the maintainer explicitly flagged as "a genuine problem in Praxion to address as a consequence of this research.")*

**Source.** forrestchang dim A4 (criteria-first); abhishekray dims A5/B2 (verification stanza, index-not-kitchen-sink), C3 (durable-rule habit), C4 (length benchmark); danielrosehill dim B5 (common-tasks orientation).

**Target.**
- `skills/software-planning/references/tier-templates.md` (the Lightweight snippet) and/or `rules/swe/swe-agent-coordination-protocol.md` (Lightweight specifics) — add a ~4-line **criteria-first micro-template**: *"Before touching code: state in one line what 'done' looks like (a testable assertion, not 'make it work'). For multi-step work, list the steps with a `→ verify: <check>` per step. This replaces the WIP.md/traceability machinery, which Direct/Lightweight tiers don't run."*
- `claude/canonical-blocks/` + `commands/onboard-project.md` + `commands/new-project.md` + `new_project.sh` (the source-of-truth chain — changes must mirror for byte-identical output; verify with `scripts/sync_canonical_blocks.py --check`) — add to the onboarded-project `CLAUDE.md` template:
  - a `## Verification` stanza: *"After every change, run in order: 1. `<typecheck>` 2. `<test>` 3. `<lint>` 4. `<build>` — fix at each step before moving on."* (filled by `/onboard-project`'s probe);
  - a `## Frequent operations` stanza: *"You'll most often be asked to: `<3–5 project-specific intents>`."* (filled by the probe; keep it ≤5 bullets);
  - a "**when I correct you, propose a durable rule** — a memory entry, a CLAUDE.md/rule edit, or a skill note — and let me review it" line (on-ramp to Praxion's `LEARNINGS.md`/`skill-genesis`/memory machinery);
  - the pithy framing line *"This `CLAUDE.md` is the index; `docs/` and the skills it points to are the library."*
- `docs/existing-project-onboarding.md` / `docs/greenfield-onboarding.md` — add a short **CLAUDE.md-length benchmark note**: *"target <200 lines per `CLAUDE.md` file; a project `CLAUDE.md` over ~150 lines is a smell — move detail to path-scoped rules or skills. Reference points: HumanLayer ~57 lines, a typical good team file ~80–100, an over-long one ~230."*

**Effort.** S–M. **Depends on.** Touches the canonical-block chain — coordinate so `sync_canonical_blocks.py --check` stays green; sentinel `EC06` checks the condensed delegation block byte-equivalence (unrelated, but be aware the chain is sentinel-watched). **Budget.** Small in *onboarded projects* (a few stanzas in their `CLAUDE.md`); ~neutral for Praxion itself (the Lightweight-tier snippet is in an on-demand reference).

**Done when.** The criteria-first micro-template is in the tier reference; the four stanzas are in the onboarded `CLAUDE.md` canonical block, mirrored across the source chain, `sync_canonical_blocks.py --check` passes; the benchmark note is in both onboarding companion docs; a fresh `/onboard-project` run produces a `CLAUDE.md` with the new sections.

**Strengthens.** Behavioral discipline at the tier that today is least scaffolded; reduces agent exploration cost in onboarded projects; gives onboarded projects an on-ramp to the learning loop.

**Execution tier.** Lightweight (2–3 files in the canonical-block chain + 2 doc files + 1 reference) — clear scope, no architectural decision.

---

## P3 — [Contract sharpening · low cost] Behavioral-contract phrasing handles + calibration notice · ☑ done (2026-05-12)

> **Done 2026-05-12.** `**Handles**` lines added under *Surface Assumptions* (present interpretations, don't pick silently / stop-name-ask), *Stay Surgical* (every changed line traces to the request / own-mess-only dead-code rule), and *Simplicity First* (forbidden-category list + senior-engineer overcomplication check + "200→50" mnemonic) in `skills/software-planning/references/behavioral-contract.md`; new `## Effectiveness Indicators` section there (fewer collateral diffs / fewer over-engineering rewrites / clarifying questions before mistakes) with a consolidated attribution paragraph (Karpathy Jan-2026 X post as source; AlphaSignal + `andrej-karpathy-skills` as community condensations, not Karpathy's work). One calibration sentence added to the always-loaded `rules/swe/agent-behavioral-contract.md` ("biases toward caution over speed; at Direct tier apply with proportionate judgment — Surface Assumptions and Stay Surgical always hold, don't ceremony-fy a typo"). Always-loaded delta: ~1 sentence (re-measure at P6 — net target ≤ 0).

**Rationale.** Praxion's behavioral contract (`Surface Assumptions / Register Objection / Stay Surgical / Simplicity First`) has the *behaviors* but not the *checkable handles* — the crisp, in-the-moment self-tests that make forrestchang's 60-line file effective. Adding them to the **deep-dive reference** (on-demand) costs ~zero always-loaded budget; adding one calibration sentence to the always-loaded rule closes the "is this overkill for a typo?" ambiguity. *(Flagged by the maintainer as a real Praxion gap to fix.)*

**Source.** forrestchang dims A1/A2/A3 (the micro-rules), D2 (speed-caution notice), D3 (effectiveness indicators); AlphaSignal article (the calibration header). Karpathy grounding: A1/A2/A3 map to the verbatim January 2026 X-post failure modes #1/#2/#3.

**Target.**
- `skills/software-planning/references/behavioral-contract.md` (the deep-dive ref the always-loaded rule already points to) — add, attributed to the source:
  - under *Surface Assumptions*: *"If multiple interpretations exist, present them — don't pick one silently. If something is unclear, stop, name what's confusing, and ask."*
  - under *Stay Surgical*: the own-mess-only dead-code rule — *"Remove imports/variables/functions that **your** changes orphaned. Don't delete pre-existing dead code unless asked — mention it."* — plus the audit heuristic *"every changed line should trace directly to the user's request."*
  - under *Simplicity First*: the forbidden-category list — *"no features beyond what was asked; no abstractions for single-use code; no 'flexibility'/'configurability' that wasn't requested; no error handling for impossible scenarios"* — plus the self-test *"would a senior engineer call this overcomplicated?"* (mnemonic: *"if 200 lines could be 50, rewrite it"*).
  - a closing *"The contract is working if: fewer collateral changes in diffs, fewer rewrites due to over-engineering, and clarifying questions arrive before mistakes rather than after."*
- `rules/swe/agent-behavioral-contract.md` (always loaded) — add **one sentence**: *"This contract biases toward caution over speed; at Direct tier, apply it with proportionate judgment — Surface Assumptions and Stay Surgical always hold, but don't ceremony-fy a typo. See the tier table in `swe-agent-coordination-protocol.md`."*

**Effort.** S. **Depends on.** Nothing (but logically pairs with P6 — the one new sentence is "paid for" by P6's relocations). **Budget.** ~1 sentence always-loaded; the rest is on-demand.

**Done when.** The handles are in `behavioral-contract.md` with attribution; the calibration sentence is in `agent-behavioral-contract.md`; `wc -c` re-measured (should be ~neutral after P6).

**Strengthens.** The behavioral contract's *bite* — turns stances into in-the-moment self-tests; the calibration notice acknowledges the tier system the contract already implies.

**Execution tier.** Direct.

---

## P4 — [Context-engineering enrichment] `rule-crafting` + `hook-crafting` overhaul · ☑ done (2026-05-12)

> **Done 2026-05-12.** `skills/rule-crafting/SKILL.md`: the thin "Memory Hierarchy" table replaced by a full seven-layer **Context Hierarchy** table (managed-policy → user → ancestor dirs → workspace/directory-of-repos → project → `CLAUDE.local.md` → subdirectory `CLAUDE.md`, with precedence + load-timing notes, `claudeMdExcludes`, the `InstructionsLoaded` debugging hook, and a `<!-- last-verified -->` marker); new "Why the Always-Loaded Budget Exists" section using citable framing only (`CLAUDE.md`/rules are context-not-enforced-config, <200 lines/file, use a hook for hard guarantees) plus the 25k guardrail + >30%-of-sessions principle and an explicit note that the circulating instruction-count / token-breakdown figures are folklore — not documented by Anthropic (see [`06`](../docs/context-prj-comparison-2026-05-12/06-not-comparable.md) §3); new "pair every prohibition with a remedy" authoring discipline (every `NEVER` → `→ do this instead`; anti-patterns as a `| pattern | why it fails | what to do instead |` table). `skills/hook-crafting/SKILL.md`: new "When a Hook (vs a Rule)" section (must-happen-100%-of-the-time → hook; general guidance → rule; the "both" pattern; a "don't over-reach for a hook when a rule will do" counterweight). Zero always-loaded cost (all skill-body content); both skills pass `skills/skill-crafting/scripts/validate.py`. The path-scoped Read-only-trigger caveat is shared with P1 — written once in `rule-crafting`, referenced from `CLAUDE.md` and `rules/CLAUDE.md`.

**Rationale.** Praxion's 25k-token budget is currently an *edict*; abhishekray's `principles.md` shows what a *reasoned* treatment looks like. Importing the **citable doc guidance** (not the folklore numbers — see [`06`](../docs/context-prj-comparison-2026-05-12/06-not-comparable.md) §3) turns the budget into a model. Several other small, portable disciplines belong here too: the explicit context-hierarchy table (including the workspace tier — see P5), the surfacing of `CLAUDE.local.md` / `claudeMdExcludes` / the `InstructionsLoaded` hook, the rule-authoring discipline ("every `NEVER` pairs with a `→ do this instead`"), and the hooks-vs-rules decision criterion. All of this is **on-demand** (skill bodies / references) — zero always-loaded cost.

**Source.** abhishekray dims B1 (context economy), B3 (hierarchy + placement), B4 (path-scoped + gotcha — cross-ref P1), C1 (Don't-X-Do-Y), C2 (hooks-vs-rules), C4 (benchmarks). Verified doc language: [`08`](../docs/context-prj-comparison-2026-05-12/08-claude-code-behavior-verification.md) V4/V5/V6/V7.

**Target.**
- `skills/rule-crafting/SKILL.md` + references — add:
  - a **"why the budget exists"** section using only citable framing: *"`CLAUDE.md` and always-loaded rules are delivered as context after the system prompt — they are context, not enforced config; specific/concise/structured wins; target <200 lines per file; longer reduces adherence; for hard guarantees use a hook."* (cite `code.claude.com/docs/en/memory`). Do **not** state the "~150–200 instructions" or "43K/93K/50K" numbers.
  - the **path-scoped Read-only-trigger caveat** (cross-ref P1) and the `paths:`-YAML-list-with-quoted-globs format (the documented, working format on macOS/Linux; note the Windows `~/.claude/rules/` caveat).
  - an **explicit context-hierarchy table**: `managed-policy → user (~/.claude/CLAUDE.md, ~/.claude/rules/) → ancestor dirs → workspace (directory-of-repos) → project (./CLAUDE.md or ./.claude/CLAUDE.md, ./.claude/rules/) → CLAUDE.local.md → subdirectory CLAUDE.md (on-demand)` — with the precedence note (more specific wins; ancestors loaded in full at launch; subdir files on-demand) and a one-line placement rule per tier. Surface `claudeMdExcludes` (monorepo ancestor suppression) and the `InstructionsLoaded` debugging hook here.
  - the **rule-authoring discipline**: *"every `NEVER`/`Don't` must pair with a `→ do this instead`; document anti-patterns as a `| pattern | why it fails | what to do instead |` table."*
- `skills/hook-crafting/SKILL.md` — add the **decision criterion**: *"If a behavior must happen 100% of the time with zero exceptions, it's a hook (deterministic, lifecycle-executed), not a CLAUDE.md/rule line (advisory, probabilistic). Rules shape behavior; hooks enforce it."*

**Effort.** M. **Depends on.** P1 (shares the path-scoped-rule caveat — write it once, reference it). **Budget.** **Zero** always-loaded (all skill-body / reference content).

**Done when.** `rule-crafting` has the budget section, the path-scoped caveat, the hierarchy table, the authoring discipline; `hook-crafting` has the decision criterion; no folklore numbers anywhere; `/sentinel` shows no new spec-compliance/coherence regressions on these skills.

**Strengthens.** Every future rule/hook-authoring decision; makes the budget a reasoned model rather than an edict; documents the workspace tier (enabling P5).

**Execution tier.** Lightweight (2 skills + their references; clear scope).

---

## P5 — [Worktree hygiene] Minimal worktree-context banner · ☑ done (2026-05-12)

> **Done 2026-05-12.** Mechanism **(b)** — `SessionStart` hook — chosen (ADR `dec-163`). New `hooks/inject_worktree_banner.py`: when the session cwd is inside a *linked* git worktree (detected via `git rev-parse --git-dir` ≠ `--git-common-dir`), emits an `additionalContext` banner naming the worktree root, the canonical (main) checkout, the `.ai-work/` (gitignored, worktree-local) vs `.ai-state/` (committed, reconciled at `/merge-worktree`) distinction, and a `pwd` reminder; fail-open, silent in the main worktree, `PRAXION_DISABLE_WORKTREE_BANNER=1` opt-out. Registered in `hooks/hooks.json` (`SessionStart`, sync). Cross-refs added: `rules/swe/swe-agent-coordination-protocol.md` (Pipeline Isolation — one line on the banner + the existing `worktree_guard.py`), `skills/software-planning/references/coordination-details.md#pipeline-worktree-lifecycle` (the banner+guard "heads-up vs backstop" pair), `commands/merge-worktree.md` (backlink note). Tests: `hooks/test_inject_worktree_banner.py` (11 cases — emits/silent/disable/fail-open/rendering); full `hooks/` suite green (247 passed, 1 pre-existing xfail); live smoke test in a throwaway `.claude/worktrees/` worktree confirmed the banner names the correct worktree + canonical paths and is silent from `main`. Always-loaded delta: ~1 line in `swe-agent-coordination-protocol.md` (banner self-announces only inside a worktree session — re-measure at P6). The `worktree_guard.py` PreToolUse hard-block (pre-existing) remains the backstop; carrying the banner via `inject_subagent_context.py` for subagents-after-`EnterWorktree` is noted as a follow-up in `dec-163`.

**Rationale.** Praxion already uses directory-scoped context informally (`scripts/CLAUDE.md`, `rules/CLAUDE.md`). The concrete, dogfood-able application of the "workspace / directory-of-repos" idea is **worktree hygiene**: more than once, a "lost" agent operating inside `.claude/worktrees/<name>/` has ended up writing into the parent (`main`) checkout, causing a mess. Claude Code loads ancestor `CLAUDE.md` files at launch (verified — [`08`](../docs/context-prj-comparison-2026-05-12/08-claude-code-behavior-verification.md) V6), so a banner can warn the agent which checkout it's in and where the canonical one is — and tie into Praxion's existing `.ai-state/` reconciliation-at-merge process. This is the only item that's a genuine *structural* addition (a context tier), and it's cheap and native — no new mechanism, just a convention + a small artifact.

**Source.** danielrosehill dims B3/D1/D9 (workspace layer / directory-level context / hierarchical layering) — scoped down from the "repo manager" concept to the one use case that dogfoods (see [`06`](../docs/context-prj-comparison-2026-05-12/06-not-comparable.md) §7 for what's left on the floor).

**Target / design options** (an architect picks the mechanism — see Execution tier):
- **(a)** A committed `.claude/worktrees/CLAUDE.md` (with a `.gitignore` exception, since `.claude/worktrees/*/` is ignored) — loaded as an ancestor when the session cwd is inside a worktree. Simple; risk: it only loads if the worktree dir is actually under `.claude/worktrees/` in the *main* repo's tree (it is, by Praxion convention).
- **(b)** *(lean)* A `SessionStart` hook that detects worktree context (`git rev-parse --git-common-dir` ≠ `--git-dir`, or the path matches `.claude/worktrees/`) and injects the banner via `additionalContext`. Most robust; doesn't diverge the worktree's own `CLAUDE.md` (which is a checkout of `main`'s, so editing it would create merge noise); composes with the existing hook set in `hooks/`.
- **(c)** `/create-worktree` and the `EnterWorktree` flow write a worktree-local note (e.g. `.ai-work/WORKTREE_CONTEXT.md` or a `<!-- ... -->` block) that pipeline agents re-read after compaction (like `PIPELINE_STATE.md`).

**Banner content (regardless of mechanism):** *"⚠️ You are operating inside a git worktree at `<this path>`. The canonical checkout is `<parent path>` — **do not create or edit files outside this worktree.** `.ai-work/` here is gitignored and worktree-local. `.ai-state/` changes are committed on this worktree's branch and reconciled into `main` at `/merge-worktree` (see `skills/software-planning/references/coordination-details.md#pipeline-worktree-lifecycle`). Run `pwd` if you're unsure which checkout you're in."*

Also update: `rules/swe/swe-agent-coordination-protocol.md` (Pipeline Isolation section) and `commands/merge-worktree.md` to reference the banner; `skills/software-planning/references/coordination-details.md#pipeline-worktree-lifecycle` to mention it.

**Effort.** M (the mechanism choice is the only non-trivial part). **Depends on.** P4 (the context-hierarchy table should document the workspace tier first). **Budget.** ~neutral (the banner only loads inside a worktree session; nothing added to the global always-loaded surface).

**Done when.** The chosen mechanism is implemented; opening a session inside `.claude/worktrees/<name>/` surfaces the banner; the coordination-protocol and `merge-worktree` docs reference it; a deliberate "agent tries to write to parent" scenario shows the banner is in context. *Acceptance includes:* the banner does not break the existing pipeline-worktree lifecycle or the `EnterWorktree`/`ExitWorktree` flow.

**Strengthens.** Worktree management and `.ai-state/` reconciliation discipline — closes a recurring "lost agent writes to main" failure; adds the missing workspace context tier.

**Execution tier.** **Standard (small)** — this is the one item that warrants a brief pipeline: a `systems-architect` picks among (a)/(b)/(c) and writes a 1-paragraph ADR; an `implementer` builds it; a `verifier` checks the acceptance scenario. ~4–6 files, one architectural decision.

---

## P6 — [Budget discipline] Conservative "relocate-don't-delete" pass on the big always-loaded rules · ☐ not started

**Rationale.** Doing this comparison surfaced that Praxion's own always-loaded surface is ~66.9 KB / ~19–21k tokens (under the 25k guardrail, but not by a lot), concentrated in four files: `swe-agent-coordination-protocol.md` (15.1 KB), `agent-intermediate-documents.md` (12.7 KB), `adr-conventions.md` (11.2 KB), and the project `CLAUDE.md` (11.2 KB). The 60-line forrestchang file is a useful mirror — but the lesson is *discipline*, not *brevity*: the 1M-token orchestrator context makes over-loading less painful, and the >30%-of-sessions heuristic is about **signal-to-noise in the model's attention**, which a bigger window doesn't fix. So this is a *conservative* pass — **relocate, never delete** — that "pays for" P2's and P3's small always-loaded additions.

**Source.** abhishekray dim B1 (the discipline); the maintainer's three-step cut protocol (see Principles §3). Not an external "feature" — an internal hygiene workstream the study prompted.

**Target / procedure.** For each of the four big always-loaded files, walk the **three-step protocol** (Principles §3) section by section:
1. **Identify compress-candidates** — sections that are (a) reference material an agent needs *only when doing a specific thing* (e.g. the full ADR finalize step-sequence in `adr-conventions.md`; the full `.ai-work/`/`.ai-state/` document inventory in `agent-intermediate-documents.md`; the deep parallel-execution / fragment-file mechanics in `swe-agent-coordination-protocol.md`), vs. (b) genuinely always-relevant (the tier table, the behavioral contract summary, the agent roster — these stay).
2. **Compress in-place** — tighten prose, collapse redundant restatements, fold examples into tables, where the meaning survives.
3. **Relocate where compression doesn't help** — move the candidate into a progressive-disclosure surface (a `skills/software-planning/references/*.md` file the rule already points to, or an agent prompt, or a new reference) and leave a one-line pointer. *No content is lost — it moves to where it's loaded when needed.* Where Praxion already has the relocation target (e.g. `coordination-details.md`, `adr-authoring-protocols.md`, `agent-pipeline-details.md`, `tech-debt-ledger.md`), prefer it over creating new files.

**Constraints.** Praxion's consistency/coherence/rigor/guarantees rank above the >30%-heuristic — if a section is load-bearing for a guarantee, it stays even if it's used <30% of the time. Anything that's currently shipped into managed projects (canonical blocks) must stay byte-synced (`sync_canonical_blocks.py --check`). Run `/sentinel` after to confirm no coherence/cross-reference regressions. Re-measure with `wc -c` after each file.

**Effort.** M–L. **Depends on.** Should land *after* P1/P3/P4 author their additions, so the relocations can absorb them and the net is measured against the final state. **Budget.** **Target: negative** — the goal is that `(P2 + P3 additions) + (P6 relocations) ≤ 0` net always-loaded delta.

**Done when.** Each of the four files has been walked through the protocol; relocated content has a pointer; `sync_canonical_blocks.py --check` passes; `/sentinel` shows no new cross-reference/coherence FAILs; the always-loaded surface re-measures at ≤ its pre-roadmap size; a short note records what moved where (a `LEARNINGS.md` entry or a paragraph in `docs/`).

**Strengthens.** The 25k-token budget headroom; the principle that always-loaded content earns its attention share — without losing any of the rigor that makes Praxion's scaffolding a guardrail.

**Execution tier.** **Standard** — multi-file, touches always-loaded surfaces and the canonical-block chain, benefits from `context-engineer` review and `/sentinel` after; a brief pipeline (no architect needed unless a relocation reveals a structural seam).

---

## Sequencing & dependencies

```
P1 (defensive, do first) ─┐
P3 (contract handles) ────┤
P4 (rule/hook-crafting) ──┤── P5 (worktree hygiene; depends on P4's hierarchy table) ── P6 (cut pass; depends on P1/P3/P4 having authored their additions)
P2 (thin-tier + onboarding template) ─┘   (P2 is independent; can run anytime)
```

Recommended order: **P1 → P3 → P2 → P4 → P5 → P6.** P1 first (it's defensive and shares text with P4). P3 next (tiny, high-leverage). P2 anytime (independent; high value at the thin tiers). P4 before P5 (P5 wants the documented workspace tier). P6 last (it absorbs P1/P3/P4's additions and lets the net delta be measured against the final state). None of these is large; P1/P3 are an afternoon each, P2/P4 a day or two, P5/P6 a short pipeline each.

## Budget discipline — running tally

| Item | Always-loaded delta (estimate) |
|---|---|
| P1 | + ~3–6 lines (`rules/CLAUDE.md` caveat, CLAUDE.md limitation bullet) |
| P2 | ~neutral for Praxion itself (Lightweight snippet is in an on-demand reference); + a few stanzas in *onboarded projects'* `CLAUDE.md` (their budget, not Praxion's) |
| P3 | + ~1 sentence (`agent-behavioral-contract.md` calibration notice) |
| P4 | **0** (all skill-body / reference content) |
| P5 | ~neutral (banner loads only inside a worktree session) |
| P6 | **negative** — target: enough relocation to make the net ≤ 0 |
| **Net** | **≤ 0** (P6 pays for P1+P3) — re-measure with `wc -c` at the end (see CLAUDE.md "Token Budget" for the measurement command). |

---

## Parked / optional appendix — not in the top six

These came out of the dimension set ([`05`](../docs/context-prj-comparison-2026-05-12/05-comparison.md)) but didn't make the cut — worth doing eventually, not now, and only if there's appetite. They go here so they're not lost and not silently absorbed.

| Item | Source | What it is | Why parked |
|---|---|---|---|
| `prompt-patterns` reference doc | abhishekray E6 | A `docs/` doc (or skill reference) with ~8–12 attributed user-facing prompt patterns: surface-unknowns (Pocock's "end with a list of unresolved questions"), second-opinion, re-plan-when-stuck, demand-elegance, autonomous-fix, etc. Cross-ref `command-crafting` (some patterns graduate to commands). | Genuinely useful but not a *gap* — it's a convenience. New artifact → enrich-first principle says park it. Low effort if/when wanted. |
| Project-archetype probe in `/onboard-project` | danielrosehill E4, abhishekray E4 | A light probe (web app / CLI / library / service / data-pipeline / ML — Praxion already detects ML and AaC) that selects a `CLAUDE.md` **skeleton** (which sections to prompt for) + a recommended skill set. | Real value, real complexity; `/onboard-project` is already 10 phases / 9 gates. Must be *skeletons*, not framework templates (see [`06`](../docs/context-prj-comparison-2026-05-12/06-not-comparable.md) §6). Medium effort — defer until P1–P6 land. |
| `/depersonalise` command | danielrosehill C6 | A command that, given a directory of config artifacts, replaces personal references (name, email, GitHub handle, machine paths) with placeholders or user-supplied generic values — for publishing one's `~/.claude/` or a project's `.claude/` setup. | Optional convenience; no quality/guarantee gap. Small command-crafting task if wanted. |
| Declarative onboarding manifest | danielrosehill C5 | An `onboarding-manifest.json` (artifact → destination → preconditions) replacing some imperative install logic. | Praxion's phased/gated/idempotent `/onboard-project` + `sync_canonical_blocks.py --check` is *more* robust already; a declarative manifest is a nice shape *if* onboarding ever gets refactored — not a gap. |

---

## Verification caveats (carry these into execution)

- The path-scoped Read-only-trigger behavior (P1) is verified against `code.claude.com/docs/en/memory` + GitHub issues as of **2026-05-12**; re-check if Claude Code resolves [#38487](https://github.com/anthropics/claude-code/issues/38487) (the feature request to load path-scoped rules on Write/Edit). If fixed, P1's mitigation can be relaxed.
- The Windows `~/.claude/rules/` `paths:`-ignored bug ([#21858](https://github.com/anthropics/claude-code/issues/21858)) is closed-as-stale (not confirmed fixed) and is labeled `platform:windows`; not reproduced on macOS/Linux. The P1 Windows note should say "if you're on Windows and your path-scoped rules don't seem to load, use project-level `.claude/rules/` symlinks" — not "this is broken."
- Do **not** import the "~150–200 instructions" or "43K/93K/50K" numbers (see [`06`](../docs/context-prj-comparison-2026-05-12/06-not-comparable.md) §3 and [`08`](../docs/context-prj-comparison-2026-05-12/08-claude-code-behavior-verification.md) V4/V5). P4 imports only the citable doc language.
- Full verification record: [`08-claude-code-behavior-verification.md`](../docs/context-prj-comparison-2026-05-12/08-claude-code-behavior-verification.md).

## Where the rest of the study lives

- [`00-karpathy-critique.md`](../docs/context-prj-comparison-2026-05-12/00-karpathy-critique.md) — what Karpathy actually said (the evaluation lens), tiered sourcing.
- [`05-comparison.md`](../docs/context-prj-comparison-2026-05-12/05-comparison.md) — exec summary, per-source lessons, the unified deduped dimension set, the 5-system matrix, dimension-by-dimension detail.
- [`06-not-comparable.md`](../docs/context-prj-comparison-2026-05-12/06-not-comparable.md) — scope mismatches and non-goals; the dimensions Praxion already covers as well or better.
- [`08-claude-code-behavior-verification.md`](../docs/context-prj-comparison-2026-05-12/08-claude-code-behavior-verification.md) — the empirical Claude Code behavior check that informed P1 and pruned the folklore.
- [`sources/01..04`](../docs/context-prj-comparison-2026-05-12/sources/) — the per-project deep dives.
