---
diataxis: explanation
audience: developer
---

# Context-Engineering Comparison — Karpathy-Inspired CLAUDE.md Approaches vs. Praxion

> **Scope of this document.** Four external Claude Code / CLAUDE.md projects are compared against Praxion (the fifth "system") to find ideas Praxion can adopt. The four externals are *much* smaller than Praxion — three are single-purpose template/skill repos and one is a newsletter article. The goal is **not** to match their scope; it is to mine them for the handful of micro-techniques and framings that would give Praxion's project-management artifacts (agents, rules, skills, commands, CLAUDE.md) a real, low-cost lift. Companion documents in this folder: [`00-karpathy-critique.md`](00-karpathy-critique.md) (the evaluation lens — what Karpathy actually said vs. community extrapolation), [`sources/01..04`](sources/) (the per-project deep dives), [`06-not-comparable.md`](06-not-comparable.md) (what Praxion should explicitly *not* chase), [`07-praxion-roadmap.md`](07-praxion-roadmap.md) (the prioritized adoption roadmap), [`08-claude-code-behavior-verification.md`](08-claude-code-behavior-verification.md) (the empirical Claude Code behavior check — verified 2026-05-12 — that informed the roadmap and pruned the folklore numbers).

---

## 1. Executive summary

**The headline.** Praxion already covers the overwhelming majority of the *critical* dimensions these projects embody — and on most of them it is more rigorous (it has a behavioral contract enforced by a verifier, a tiered process-calibration model, a 25k-token budget, a 16-agent coordination pipeline, a memory protocol, a self-improvement loop spanning `LEARNINGS.md` → skill-genesis → sentinel). The external projects are not "ahead" of Praxion architecturally. **But** they are sharper than Praxion on a small, well-defined set of things, and those are exactly where the juicy gains live:

1. **Terse behavioral *phrasing* in the always-loaded surface.** forrestchang's 60-line CLAUDE.md operationalizes Karpathy's three failure modes with crisp, memorable micro-rules ("If multiple interpretations exist, present them — don't pick silently"; "If you notice dead code, mention it — don't delete it"; "If 200 lines could be 50, rewrite it"; "Would a senior engineer say this is overcomplicated?"). Praxion's behavioral contract has the *behaviors* but not these *handles*.
2. **Quantified token-economy calibration.** abhishekray's `principles.md` ships hard numbers Praxion's `rule-crafting` skill lacks: the ~150–200-instruction adherence ceiling, the rule re-injection multiplication (one 500-token rule costs 500 × tool-calls, not 500), a real session breakdown (43K initial / 93K re-injections / 50K conversation), and the **path-scoped-rules-fire-on-Read-not-Write/Edit gotcha** — which is an *undocumented failure mode* in Praxion's own rules system.
3. **The missing "workspace" context layer.** Both abhishekray (global/project/local) and danielrosehill (home → directory-of-repos → project) make the CLAUDE.md hierarchy explicit; danielrosehill goes further and *invents the middle layer* — a CLAUDE.md scoped to a directory that contains many repos. Praxion has user/project/path-scoped + skills/agents tiers, but no "workspace / portfolio" layer, and its placement model (`rules` vs `skills` vs `CLAUDE.md`) lives inside the `rule-crafting` skill rather than as a user-facing decision table.
4. **Intent / "common-tasks" orientation.** danielrosehill's templates lead with "what are you most likely to be asked to do here?" Praxion's CLAUDE.md is *discovery*-oriented ("here's how to find things") not *intent*-oriented ("here's what you'll likely do"). A 3–5-item "Frequent operations" section is cheap and high-signal.
5. **A few small authoring-discipline rules.** "Every `NEVER` prohibition must carry a positive `→ do this instead`"; "if a rule must fire 100% of the time it's a hook, not a CLAUDE.md line"; "after a correction, ask Claude to update its own instructions" — all are crisp, portable, and only *implicitly* present in Praxion.
6. **Per-tier coverage of the behavioral guardrails.** Praxion's strongest expression of "criteria-first / verify before done" lives in the Standard/Full pipeline (REQ-IDs, `traceability.yml`, the verifier agent). At **Direct and Lightweight tiers** — the most common ones — there is no lightweight "state what 'done' looks like before you touch code" micro-template and no "run typecheck → test → lint in this order" block. forrestchang/abhishekray fill exactly that gap.

**The bottom line for the roadmap.** None of the adoptable items is architectural. They are: ~6 micro-phrasings to fold into `agent-behavioral-contract.md` and its deep-dive reference; a quantified token-economy section + a Read-only gotcha note for `rule-crafting`; a "Frequent operations" + "Verification" stanza in the onboarded-project CLAUDE.md template; a `workspace-context` concept for `/onboard-project`; a couple of rule/hook-authoring rules; an optional `/depersonalise` command; a curated prompt-pattern reference. Total always-loaded budget impact: a few hundred bytes if done carefully (and *negative* if we use the occasion to tighten the always-loaded rules — see §6). Everything else these projects do is either already covered better, or out of scope by design (see [`06-not-comparable.md`](06-not-comparable.md)).

---

## 2. Lessons learned — per source

### 2.1 `forrestchang/andrej-karpathy-skills` (the 127k-star, 60-line CLAUDE.md)

**Take:** The *operationalization technique* — turning a diagnostic ("models overcomplicate") into a behavioral constraint with a self-test ("Would a senior engineer say this is overcomplicated?") and an observable outcome ("fewer rewrites due to overcomplication"). Praxion's behavioral contract states stances; this repo shows how to make a stance *checkable by the agent itself in the moment*. Lift the specific micro-rules (interpretations-not-silent-choice, dead-code-mention-not-delete, 200→50, senior-engineer test, the effectiveness-indicators footer, the speed-caution header).

**Leave:** The repo's *entire ambition* — it is intentionally a single-file nudge for solo developers, plus multi-tool format parity (CLAUDE.md ↔ Cursor `.mdc` ↔ SKILL.md kept in manual sync) and plugin packaging. Praxion already covers the same behavioral ground far more rigorously and has a deliberate (different) cross-assistant strategy. The 127k stars reflect Karpathy's amplification of a community looking for a one-file shortcut; competing on simplicity is a category error for Praxion.

**Caveat on attribution:** Karpathy did **not** write or endorse this file. The four-principle structure is Forrest Chang's synthesis of Karpathy's January 2026 X-post failure-mode list. When Praxion cites "Karpathy" as authority, cite the X post / the YC talk, not the repo (see [`00-karpathy-critique.md`](00-karpathy-critique.md) for tiered sourcing).

### 2.2 `abhishekray07/claude-md-templates` (the 203-star structured starter kit + 36 KB `principles.md`)

**Take:** The *quantified context-economy model* — this is the single most valuable artifact across all four projects for Praxion, because Praxion's 25k-token budget is currently a cap-with-a-principle and this kit supplies the *math* that justifies it (instruction-count ceiling, re-injection multiplication, real session breakdown, the Read-only path-scoped-rule trigger, hooks-vs-advisory boundary). Also worth lifting: the "CLAUDE.md is the index, `docs/` is the library" framing; the structured 7-section project template (`Project / Stack / Structure / Commands / Verification / Conventions / Don't`); the "every `NEVER` pairs with an alternative" rule-writing discipline; the anti-pattern table format; the auto-memory layer-4 mental model; the `## Skills` activation-mapping syntax for onboarded projects.

**Leave:** The copy-paste project templates themselves (Next.js, FastAPI) — Praxion operates at ecosystem scale, not project-starter scale; shipping framework templates would be scope creep. The kit's "self-improvement loop" framed as a novelty — Praxion's `LEARNINGS.md` / skill-genesis / sentinel / memory-mcp machinery already subsumes it (though the *one-liner habit* is still worth surfacing — see §2.4).

**Note on rigor:** This is a practitioner synthesis (Anthropic docs + Boris Cherny's tips + HumanLayer research + community), not original research — but the synthesis is high quality and the numbers appear sound. Treat its empirical claims as "well-sourced community consensus", and verify the Read-only gotcha against the current Claude Code build before documenting it as fact.

### 2.3 `danielrosehill/Claude-Code-Repo-Managers-ClaudeMD` (the 2-star "repo manager" template library)

**Take:** Two genuinely new ideas. (1) The **workspace / directory-of-repos context layer** — a CLAUDE.md placed at `~/repos/github/` (not at a project root) that tells Claude what *class* of repos live there, what bulk operations are typical, what conventions apply across the collection. Praxion's hierarchy jumps straight from `~/.claude/CLAUDE.md` to project-root; this fills the gap, and it maps onto things Praxion already does (worktrees are sub-collections; `/onboard-project` runs over many projects). (2) The **"Common Tasks / Frequent Operations" section pattern** — every template front-loads anticipated intents instead of just describing what exists. Also note the `config.json` machine-readable template registry (`search_patterns` + `validation_rules`) and the `/depersonalise` slash-command concept.

**Leave:** Almost all the *content* — it is one person's Hugging-Face-heavy portfolio (Gradio code samples, HF hardware tiers, Space YAML frontmatter, work-vs-personal-vs-fork etiquette). The deploy script and `grab-slash-commands.sh` are personal-scale and unsophisticated; the *patterns* (registry + validate-before-deploy, gitignored-commands-synced-to-tracked-dir) are worth noting, the implementations are not worth lifting. At 2 stars / 1 contributor / last commit Oct 2025, treat this as an *idea source*, not a reference implementation.

### 2.4 The AlphaSignal article + the Karpathy grounding (`00-karpathy-critique.md`)

**Take:** From the *article*: not much beyond what the forrestchang analysis already gives — but it does add the **explicit calibration notice** ("these guidelines bias toward caution over speed; for trivial tasks, use judgment") as a first-class meta-instruction, and the **honest attribution** discipline (Karpathy diagnosed; Chang built the remedy; Karpathy never endorsed it). From the *grounding doc*: the 12-criterion implications checklist (assumption surfacing, complexity constraint, surgical scope, verification criteria, context economy, human-oversight integration, instruction/code separation, scope bounding, loop speed, jagged-intelligence awareness, anti-anthropomorphism, vibe-vs-production calibration) is the cleanest available distillation of "what to evaluate a CLAUDE.md / context system against" — it is the spine of this comparison's dimension set.

**Leave:** Treating "Karpathy-inspired" as a brand. Karpathy's actual prescriptions are at the *workflow* level (small incremental diffs, review every change, fast verification loops, keep the model on a leash, `program.md`-style instruction/code separation in autoresearch) and the *product-design* level (autonomy slider, "demo is works.any(), product is works.all()"). He never prescribed CLAUDE.md formats, lengths, anti-pattern lists, or self-updating instructions — all of that is legitimate community engineering, but it should be evaluated on its own merits, not adopted because it wears the label.

---

## 3. The unified critical-dimension set (deduped)

Each external project ranked its own dimensions and drew a "criticality boundary". Below is the **union of everything any source treats as critical**, plus a few high-recurrence supporting dimensions, with semantically-equivalent items merged. Each is tagged with which sources treat it as load-bearing and whether it traces to a Karpathy primary position (`[V]` verbatim / `[P]` close paraphrase / `[R]` reported / `[C]` community extrapolation — see `00-karpathy-critique.md`).

| ID | Unified dimension | Treated as critical by | Karpathy grounding |
|---|---|---|---|
| **A1** | Assumption surfacing — no silent guessing; present competing interpretations rather than picking one; stop and name confusion | forrestchang, AlphaSignal | `[V]` failure-mode #1 |
| **A2** | Minimum-viable-code — no speculative features/abstractions/configurability/impossible-case error-handling; enumerate the forbidden categories; self-test for over-complication | forrestchang, AlphaSignal | `[V]` failure-mode #2 |
| **A3** | Surgical scope — touch only what the request requires; *own-mess-only* dead-code rule (remove orphans you created; mention pre-existing dead code, don't delete it) | forrestchang, AlphaSignal | `[V]` failure-mode #3 |
| **A4** | Criteria-first task framing — transform a vague task into a testable assertion *before* coding; numbered step-plan with a `→ verify:` check per step | forrestchang, AlphaSignal | `[V]` "give it success criteria and watch it go" |
| **A5** | Verification-loop discipline — give the agent a feedback loop; run typecheck → test → lint → build in order; framed as the single highest-leverage action (2–3× quality) | abhishekray | `[P]` "the faster the loop the better"; autoresearch |
| **B1** | Context economy / attention budget — quantified: ~150–200-instruction adherence ceiling; rule re-injection multiplies cost; terse, high-signal always-loaded surface | abhishekray | `[P]` "context window is your lever"; `[P]` anterograde amnesia |
| **B2** | Progressive disclosure / CLAUDE.md-as-index — always-loaded content is an index; task-specific docs are pulled in on demand; skill/doc activation maps | abhishekray (and implicit in all) | `[C]` (derived from B1) |
| **B3** | Layered context hierarchy + explicit placement rules — user → **workspace/directory-of-repos** → project → path-scoped; a decision table for "which level does this rule belong to" | abhishekray, danielrosehill | `[C]` |
| **B4** | Modular path-scoped rules + their gotchas — `paths:` frontmatter to limit re-injection; **path-scoped rules trigger on Read, not Write/Edit** | abhishekray | `[C]` (operationalizes B1) |
| **B5** | Intent / "common-tasks" orientation — lead with "what are you most likely to be asked to do here", not just "what is this" | danielrosehill | `[C]` |
| **C1** | "Don't X → Do Y" rule-writing discipline — every prohibition must carry a positive replacement; anti-pattern tables (`pattern | why it fails | what to do instead`) | abhishekray | `[C]` |
| **C2** | Hooks (deterministic) vs rules (advisory) boundary — if a rule must fire 100% of the time with zero exceptions, it's a hook, not a CLAUDE.md/rule line | abhishekray | `[C]` |
| **C3** | Self-improvement / living-context loop — after a mistake + correction, the agent records a durable rule so it doesn't recur | abhishekray | `[C]` (derived from autoresearch `program.md`) |
| **C4** | Real-world calibration anchors — benchmark data for "how long should a CLAUDE.md be" (HumanLayer 57 lines; Boris Cherny's team ~83; Cloudflare 230 = too long) | abhishekray | `[C]` |
| **C5** | Machine-readable artifact registry + validate-before-deploy — declarative list of what gets installed where, with structural validation before writing | danielrosehill | `[C]` |
| **C6** | Depersonalization of shareable artifacts — a workflow to scrub identity (name, email, handle, paths) before publishing config | danielrosehill | `[C]` |
| **D1** | Process-rigor calibration matched to task risk — vibe-coding ↔ production-engineering spectrum; pick the process weight for the task | (all, weakly) | `[P]` "vibe coding raises the floor; agentic engineering preserves the ceiling" |
| **D2** | Speed-caution tradeoff acknowledgment — the config explicitly names its own friction cost ("biases toward caution; for trivial tasks use judgment") | forrestchang, AlphaSignal | `[C]` |
| **D3** | Observable-effectiveness indicators — a terse "you can tell this is working if … (fewer collateral diffs / fewer rewrites / questions before mistakes)" | forrestchang, AlphaSignal | `[C]` |
| **E1** | Subagent strategy as a first-class technique — parallelism, one-task-per-subagent, context hygiene | abhishekray (weakly) | `[C]` |
| **E2** | Multi-tool / cross-assistant portability — the same behavioral content works across Claude Code / Cursor / others | forrestchang, AlphaSignal | `[C]` |
| **E3** | Anti-anthropomorphism / design for context limits, not cross-session memory — compaction-aware, state-snapshot habits; don't assume the model "remembers" | abhishekray (auto-memory) | `[P]` anterograde amnesia |
| **E4** | Project-archetype taxonomy driving context generation — "what kind of project is this?" selects the CLAUDE.md template + skill set | danielrosehill, abhishekray (weakly) | `[C]` |
| **E5** | Auto-memory awareness — don't duplicate in CLAUDE.md what the assistant auto-saves; understand the manual-vs-auto memory split | abhishekray | `[C]` |
| **E6** | Plan-before-act + reusable prompt-pattern library — a curated set of user-facing prompts (surface-unknowns, second-opinion, re-plan-when-stuck, demand-elegance, verify, autonomous-fix) | abhishekray | `[R]` "small incremental requests and precise prompts" |
| **E7** | Bounded reviewable surface / small diffs — constrain the agent to a small, reviewable change footprint (autoresearch's single-file constraint is the extreme form) | (implicit) | `[V]` autoresearch README |
| **E8** | Instruction/code separation — behavioral guidance is a first-class editable artifact, not code comments (the `program.md` pattern) | (implicit) | `[P]` autoresearch `program.md` |

---

## 4. Comparison matrix — all five systems

Legend: ✅ present and robust (often *more* rigorous than the externals) · 🟡 partial / present but soft / not in the load-bearing surface · ❌ absent · ➖ out of scope by that project's design.

Columns: **F** = forrestchang/andrej-karpathy-skills · **A** = abhishekray07/claude-md-templates · **D** = danielrosehill/Repo-Managers-ClaudeMD · **S** = AlphaSignal article · **PRX** = Praxion.

### Group A — Behavioral guardrails (Karpathy's failure modes + verification)

| Dim | F | A | D | S | PRX | Praxion notes |
|---|---|---|---|---|---|---|
| A1 Assumption surfacing | ✅ | 🟡 | ➖ | ✅ | ✅ | `agent-behavioral-contract.md` "Surface Assumptions" (all agents; verifier-checked). **Gap:** missing the "present all interpretations — don't pick silently" micro-rule and the "stop · name what's confusing · ask" cadence. |
| A2 Minimum-viable-code | ✅ | 🟡 | ➖ | ✅ | ✅ | "Simplicity First" + "Incremental Evolution"/"Behavior-Driven Development" principles. **Gap:** no enumerated forbidden-category list, no "200→50" heuristic, no "would a senior engineer call this overcomplicated?" self-test. |
| A3 Surgical scope (+ own-mess dead code) | ✅ | 🟡 | ➖ | ✅ | ✅ | "Stay Surgical" + stop-and-re-scope escalation (which the externals lack). **Gap:** no explicit dead-code disambiguation; no "every changed line traces to the request" one-line audit heuristic. |
| A4 Criteria-first task framing | ✅ | 🟡 | ➖ | ✅ | 🟡 | Strong at Standard/Full (REQ-IDs, `traceability.yml`, acceptance criteria, verifier). **Gap:** nothing equivalent at **Direct/Lightweight** tiers — no "state what 'done' looks like before you touch code" micro-template, no `step → verify:` mini-format. |
| A5 Verification-loop discipline | 🟡 | ✅ | ➖ | 🟡 | ✅ | verifier agent; `## How to verify your work` in CLAUDE.md; `sync_canonical_blocks.py --check`; `/sentinel`; eval framework. **Gap:** the *per-task* "run typecheck → test → lint → build, in this order" copy-paste block isn't in the onboarded-project CLAUDE.md template. |

### Group B — Context economy & structure

| Dim | F | A | D | S | PRX | Praxion notes |
|---|---|---|---|---|---|---|
| B1 Token economy / attention budget | 🟡 | ✅ | 🟡 | 🟡 | ✅ | 25k-token hard budget + "every always-loaded token must earn its attention share (>30% of sessions)" + mandatory `wc -c` measurement. **Gap:** no quantified re-injection model, no ~150–200-instruction ceiling, no "1 rule × N tool-calls" cost framing in `rule-crafting`. |
| B2 Progressive disclosure / CLAUDE.md-as-index | 🟡 | ✅ | 🟡 | 🟡 | ✅ | Canonical 3-tier skill disclosure (metadata → SKILL.md body → `references/*`); CLAUDE.md is an explicit "navigation index" with a reading order. **Gap:** the pithy "index / library" framing and a `## Skills`-activation-map stanza aren't in the onboarded-project CLAUDE.md template. |
| B3 Layered hierarchy + placement rules (incl. **workspace layer**) | ❌ | ✅ | ✅ | ❌ | 🟡 | Has user-level / project-level / path-scoped + skills + agents tiers, and a `rules`-vs-`skills`-vs-`CLAUDE.md` decision model. **Gap:** no "workspace / directory-of-repos" layer; placement model is internal (inside `rule-crafting`), not a user-facing decision table; `CLAUDE.local.md` and `claudeMdExcludes` not documented. |
| B4 Modular path-scoped rules (+ Read-only gotcha) | ❌ | ✅ | ➖ | ❌ | ✅ | 15 path-scoped rules via `paths:` frontmatter; `paths:` mechanics documented in `rules/CLAUDE.md`. **Gap (real bug-risk):** the "path-scoped rules trigger on **Read**, not Write/Edit/MultiEdit" behavior is undocumented — agents that Edit a file without Reading it first silently miss the rule. |
| B5 Intent / common-tasks orientation | ❌ | 🟡 | ✅ | ❌ | 🟡 | Skills carry "common operations" sections; CLAUDE.md links to component catalogs. **Gap:** CLAUDE.md is *discovery*-oriented, not *intent*-oriented — no "Frequent operations: you'll most likely be asked to …" section. |

### Group C — Authoring & maintenance discipline

| Dim | F | A | D | S | PRX | Praxion notes |
|---|---|---|---|---|---|---|
| C1 "Don't X → Do Y" rule-writing discipline | 🟡 | ✅ | ➖ | ❌ | 🟡 | Praxion's rules generally do pair prohibitions with alternatives in practice (coding-style, etc.). **Gap:** not codified as a *rule-authoring rule* in the `rule-crafting` skill; no anti-pattern-table template. |
| C2 Hooks (deterministic) vs rules (advisory) boundary | ❌ | ✅ | ➖ | ❌ | ✅ | 30 hooks + memory-gate hook + observability hooks + `hook-crafting` skill; "rules are declarative, hooks enforce" is the de-facto practice. **Gap:** the crisp "if it must fire 100% of the time, it's a hook not a CLAUDE.md/rule line" decision criterion isn't stated in `hook-crafting` / `rule-crafting`. |
| C3 Self-improvement / living-context loop | ❌ | ✅ | ➖ | ❌ | ✅ | Structurally *richer*: `LEARNINGS.md` → skill-genesis → sentinel → memory-mcp + `/remember` + the "Learn / Recall / Apply" loop in `~/.claude/CLAUDE.md`. **Gap:** no surfaced one-liner habit ("when I correct you, propose a durable rule"); and for Praxion-the-repo, memory-mcp is disabled (`PRAXION_DISABLE_MEMORY_MCP=1`). |
| C4 Real-world calibration anchors | 🟡 | ✅ | ➖ | ❌ | 🟡 | Praxion measures its own surface (66.9 KB / ~19–21k tok). **Gap:** no external "CLAUDE.md length" benchmark table to calibrate onboarded projects against. |
| C5 Machine-readable registry + validate-before-deploy | ❌ | 🟡 | ✅ | ❌ | 🟡 | `/onboard-project` is phased / gated / idempotent (10 phases, 9 gates); canonical-blocks have `sync_canonical_blocks.py --check`. **Gap:** no single declarative manifest of "what gets installed where, with structural pre-checks". |
| C6 Depersonalization of shareable artifacts | ❌ | ➖ | ✅ | ❌ | 🟡 | `adapt-claude-to-agents` skill exists (CLAUDE→AGENTS template gen); onboarding writes user-specific bits (email, GitHub handle). **Gap:** no `/depersonalise` to scrub identity from a config set before publishing. |

### Group D — Calibration & meta-awareness

| Dim | F | A | D | S | PRX | Praxion notes |
|---|---|---|---|---|---|---|
| D1 Process-rigor calibration to task risk | 🟡 | 🟡 | ➖ | 🟡 | ✅ | **Strongest of the five.** Direct / Lightweight / Standard / Full / Spike tier table + Tier Selector + `calibration_log.md` + SDD complexity triage. The externals have at most a one-liner ("for trivial tasks, use judgment"). |
| D2 Speed-caution tradeoff acknowledgment | ✅ | 🟡 | ➖ | ✅ | 🟡 | The tier system *embodies* this. **Gap:** the always-loaded behavioral contract has no "these constraints bias toward caution; at Direct tier, use judgment" calibration notice — it reads as universal. |
| D3 Observable-effectiveness indicators | ✅ | ❌ | ➖ | ✅ | 🟡 | sentinel's 10-dimension audit + verification-report failure-mode tags are far *richer*. **Gap:** no terse, in-the-always-loaded-surface "the contract is working if: fewer collateral diffs, fewer over-engineering rewrites, clarifying questions before mistakes". |

### Group E — Orchestration & ecosystem (Praxion's home turf)

| Dim | F | A | D | S | PRX | Praxion notes |
|---|---|---|---|---|---|---|
| E1 Subagent strategy as first-class | ❌ | 🟡 | ➖ | ❌ | ✅ | **Dominant.** 16 agents, `swe-agent-coordination-protocol.md`, parallel execution, boundary discipline, model routing, background agents, fragment-file merges. |
| E2 Multi-tool / cross-assistant portability | 🟡 | ❌ | 🟡 | 🟡 | ✅ | **Dominant.** Assistant-agnostic shared `skills/`/`commands/`/`agents/`; per-assistant `claude/`/`codex/`/`cursor/` config; `AGENTS.md.tmpl` generation; `install.sh cursor`. (forrestchang's manual 3-file sync is the toy version.) |
| E3 Anti-anthropomorphism / context-limit design | ❌ | 🟡 | ➖ | ❌ | ✅ | PreCompact hook → `.ai-work/PIPELINE_STATE.md`; persistent `.ai-state/`; the three-document model; Compaction Guidance in CLAUDE.md. |
| E4 Project-archetype taxonomy → context | ❌ | 🟡 | ✅ | ❌ | 🟡 | ML/AI-training archetype detection (`/onboard-project` Phase 8c) + AaC tier (Phase 8b) + the ML skill family. **Gap:** no general "project archetype → CLAUDE.md template + skill set" selector for the common (non-ML) case. |
| E5 Auto-memory awareness | ❌ | ✅ | ➖ | ❌ | ✅ | `memory-protocol.md` covers the dual-system conflict (Claude auto-memory vs. memory-mcp) + a conflict-resolution order. Arguably the **sharpest** treatment among the five. |
| E6 Plan-before-act + prompt-pattern library | ❌ | ✅ | ➖ | ❌ | 🟡 | Plan mode in the methodology; `implementation-planner` agent; `command-crafting` skill. **Gap:** no curated *user-facing* prompt-pattern reference (surface-unknowns, second-opinion, re-plan-when-stuck, demand-elegance, autonomous-fix). |
| E7 Bounded reviewable surface / small diffs | ✅ | 🟡 | ➖ | 🟡 | ✅ | "Stay Surgical" + git-conventions ("one logical change per commit", "small, focused commits", "separate refactor from behavior change"). The `ml-training` skill literally documents Karpathy's `autoresearch` single-file constraint as a case study. |
| E8 Instruction/code separation (`program.md`) | 🟡 | 🟡 | ➖ | 🟡 | ✅ | CLAUDE.md / rules / skills are all separate from code; **ML projects ship a literal `program.md`** (the `ml-training` skill). |

---

## 5. Detailed analysis — dimension by dimension

For each dimension: what it means, how the externals do it, how Praxion does it, and the **verdict** — one of `🏆 Praxion ahead` (don't chase), `✨ adoptable gap` (feeds the roadmap), `🚫 not comparable` (see `06-not-comparable.md`).

### A1 — Assumption surfacing · ✨ adoptable gap (micro)
**What it means.** The #1 Karpathy failure mode `[V]`: models make wrong assumptions silently. The fix: before acting, list assumptions; if several interpretations exist, present them rather than pick one; if confused, stop and name it.
**Externals.** forrestchang §1 and the AlphaSignal article have the crispest version ("If multiple interpretations exist, present them - don't pick silently"). abhishekray approaches it via Plan Mode + Matt Pocock's "list of unresolved questions" prompt. danielrosehill: ➖ (descriptive templates, no behavioral contract).
**Praxion.** `agent-behavioral-contract.md` § "Surface Assumptions" — and Praxion goes further: it applies to *every* agent, the verifier tags violations, and the deep dive lives in `skills/software-planning/references/behavioral-contract.md`.
**Verdict.** Praxion has the behavior; it lacks the *handle*. **Adopt:** add the "present competing interpretations, don't pick silently" sub-rule and the "stop · name what's confusing · ask" cadence to `agent-behavioral-contract.md` (≈1 line) and the worked phrasing to the deep-dive reference.

### A2 — Minimum-viable-code / anti-overengineering · ✨ adoptable gap (micro)
**What it means.** Karpathy failure mode #2 `[V]`: bloated abstractions, 1000 lines where 100 would do, dead code left behind. The fix: enumerate the forbidden categories (no unrequested features / single-use abstractions / speculative configurability / impossible-case error handling) and give a self-test.
**Externals.** forrestchang §2 is the canonical version ("If you write 200 lines and it could be 50, rewrite it" + "Would a senior engineer say this is overcomplicated?"). abhishekray bans bloat via its anti-pattern catalog. AlphaSignal echoes forrestchang.
**Praxion.** "Simplicity First" (behavioral contract) + "Incremental Evolution" / "Behavior-Driven Development" (`~/.claude/CLAUDE.md`): "the implementation should be the simplest thing that achieves it"; "every added line, file, or dependency must earn its place."
**Verdict.** Same concept, less operational bite. **Adopt:** add the enumerated forbidden-category bullet list and the senior-engineer self-test to the behavioral-contract deep-dive reference (not the always-loaded rule — keep the rule terse). The "200→50" line is a good mnemonic for the reference too.

### A3 — Surgical scope (own-mess-only dead code) · ✨ adoptable gap (micro)
**What it means.** Karpathy failure mode #3 `[V]`: collateral edits to orthogonal code. The sharp version distinguishes *orphans your change created* (remove them) from *pre-existing dead code* (mention it, don't delete it).
**Externals.** forrestchang §3 and AlphaSignal: "If you notice dead code, mention it — don't delete it" + "The test: every changed line should trace directly to the user's request."
**Praxion.** "Stay Surgical" (behavioral contract): "touch only what the change requires; if scope grew, stop and re-scope" — *plus* the stop-and-re-scope escalation that the externals lack. Also `coding-style` / `git-conventions` ("separate refactoring from behavior changes", "delete dead code, don't preserve it in comments").
**Verdict.** Praxion is arguably *ahead* on the escalation path but *behind* on the dead-code disambiguation. **Adopt:** add the own-mess-only dead-code rule and the "every changed line traces to the request" audit heuristic to the behavioral-contract deep-dive reference.

### A4 — Criteria-first task framing · ✨ adoptable gap (Direct/Lightweight tier)
**What it means.** Karpathy `[V]`: "Don't tell it what to do, give it success criteria and watch it go." Operationalized: transform a vague task into a testable assertion *at intake*, and for multi-step work write a numbered plan with a `→ verify:` check per step.
**Externals.** forrestchang §4 has the reframe template ("Add validation" → "Write tests for invalid inputs, then make them pass") and the `step → verify:` mini-format. abhishekray covers it via acceptance criteria in Plan Mode.
**Praxion.** At **Standard/Full** tier this is *handled extremely well*: SDD with REQ-IDs, `traceability.yml`, acceptance criteria in `IMPLEMENTATION_PLAN.md`, the implementer working against REQ-IDs, the verifier checking compliance. At **Direct/Lightweight** tier — where no `WIP.md` / `IMPLEMENTATION_PLAN.md` exists — there is *no in-place equivalent*.
**Verdict.** **Adopt:** add a 4-line "before you touch code, state what 'done' looks like; for multi-step work, list steps with a verify check each" micro-template to the Direct/Lightweight tier guidance (in `swe-agent-coordination-protocol.md`'s Lightweight specifics, or the tier-templates reference). This is the single highest-value behavioral adoption because it covers the *most common* tier, which today is the *least scaffolded*.

### A5 — Verification-loop discipline · 🏆 Praxion ahead (with one onboarding gap)
**What it means.** Give the agent a way to verify its own work; run checks in a fixed order; treat this as the single highest-leverage action.
**Externals.** abhishekray ships a `## Verification` section in every project template (`typecheck → test → lint → build`) and quotes Boris Cherny's "2-3x quality" claim. forrestchang/AlphaSignal imply it via §4.
**Praxion.** The `verifier` agent; the `## How to verify your work` section in CLAUDE.md ("pair every claim a doc makes with a verification path"); `sync_canonical_blocks.py --check`; `/sentinel`; the eval framework; `eval-driven-verification` rule for ML. Far beyond a CLAUDE.md section.
**Verdict.** Praxion is well ahead at the ecosystem level. **One small adopt:** the onboarded-project CLAUDE.md *template* (what `/onboard-project` writes into user projects) should include a `## Verification` stanza with the project's own ordered commands — that's a project-level convenience Praxion has for *itself* (`pytest`, `--check`, `/sentinel`) but doesn't necessarily seed into onboarded projects' CLAUDE.md.

### B1 — Context economy / attention budget · ✨ adoptable gap (high value)
**What it means.** Treat context as a scarce lever: there's a ~150–200-instruction adherence ceiling; the system prompt already eats ~50 slots; **rule files re-inject on every tool call**, so a 500-token rule costs 500 × (tool-calls); keep the always-loaded surface terse and high-signal.
**Externals.** abhishekray's `principles.md` is the reference: the 43K/93K/50K session breakdown, the 3–5-rule-files / under-30-lines targets, HumanLayer's research citation.
**Praxion.** 25k-token hard budget on always-loaded content; "every always-loaded token must earn its attention share (applied in >30% of sessions, or unconditionally relevant)"; mandatory `wc -c` measurement before adding to the surface; the principle is stated in both `rules/CLAUDE.md` and the project CLAUDE.md. Praxion *lives* this — but it doesn't *explain the mechanism*.
**Verdict.** **Adopt:** add a quantified "why the budget exists" section to the `rule-crafting` skill (or a reference): the instruction-count ceiling, the re-injection multiplication math, a worked example. This strengthens every future rule-authoring decision and gives the 25k number a *reason* rather than an *edict*. (Verify the current numbers against Anthropic's docs before committing them.)

### B2 — Progressive disclosure / CLAUDE.md-as-index · 🏆 Praxion ahead (with a framing borrow)
**What it means.** Always-loaded content is an index; the bulk lives in on-demand docs/skills; CLAUDE.md says *when* to read them.
**Externals.** abhishekray: "CLAUDE.md is the index. The `docs/` folder is the library. Claude pulls books off the shelf when needed." Plus `@import` (always) vs the "pitch" pattern (mention-when-relevant) and a `## Skills` activation map.
**Praxion.** This is *the* load-bearing skill pattern: metadata at startup → SKILL.md body on activation → `references/*.md` on demand. CLAUDE.md is explicitly a "navigation index, not a kitchen sink" with a documented reading order. Auto-discovery ("components are never enumerated in always-loaded context") is a stated design principle.
**Verdict.** Praxion is ahead architecturally. **Adopt (cosmetic but useful):** lift the "index / library" one-liner into the onboarded-project CLAUDE.md template, and add a `## Skills` / `## When to read what` activation-map stanza to that template so onboarded projects start with the pattern visible.

### B3 — Layered hierarchy + placement rules (+ workspace layer) · ✨ adoptable gap (the workspace layer is genuinely new)
**What it means.** Context exists at multiple levels: user (`~/.claude/CLAUDE.md`) → **workspace / directory-of-repos** → project root → path-scoped. Each level has a clear "what belongs here" rule; the workspace layer (a CLAUDE.md describing a *collection* of repos) is the one most setups leave dark.
**Externals.** abhishekray: global / project / local + a placement decision table + `claudeMdExcludes` for monorepo ancestor suppression. danielrosehill: home → repo-base → project, and it *builds the middle layer* — 12 templates each placed at a directory-of-repos.
**Praxion.** Has user-level, project-level, path-scoped rules, plus skills and agents as further progressive tiers, plus a `rules` vs `skills` vs `CLAUDE.md` decision model — but all from a *single-project* vantage point. No "workspace" layer; no user-facing placement decision table; `CLAUDE.local.md` not documented.
**Verdict.** **Adopt:** (a) document the existing hierarchy as an explicit table in the `rule-crafting` / context-engineering docs, *including* the (currently absent) workspace tier; (b) add a lightweight `workspace-context` notion to `/onboard-project` — when run over a directory that contains many repos, offer to write a `CLAUDE.md` there describing the collection (what lives here, typical bulk operations, shared conventions). This is the one *structural* idea worth taking, and it composes cleanly with Praxion's worktree model.

### B4 — Modular path-scoped rules + the Read-only gotcha · ✨ adoptable gap (bug-risk — do this one)
**What it means.** `paths:` frontmatter scopes a rule so it re-injects only when matching files are in play — but it triggers on the **Read** tool, *not* Write/Edit/MultiEdit. An agent that edits a file without reading it first silently misses the rule.
**Externals.** abhishekray documents this explicitly.
**Praxion.** 15 path-scoped rules; the `paths:` mechanism is documented in `rules/CLAUDE.md` and `rule-crafting` — but **not the Read-only trigger caveat.** Praxion has rules like `coding-style.md`, `testing-conventions.md`, `pr-conventions.md` that *assume* they fire when relevant files are touched; if "touched" means Edit-without-Read, they don't.
**Verdict.** **Adopt (priority):** verify against the current Claude Code build, then document the caveat in `rules/CLAUDE.md` and `rule-crafting`, and — more importantly — audit Praxion's own path-scoped rules for any that would be missed under Edit-only access, and either widen their `paths:` or move the load-bearing parts elsewhere. This is the closest thing to an actual *latent bug* the comparison surfaced.

### B5 — Intent / common-tasks orientation · ✨ adoptable gap (cheap, high-signal)
**What it means.** Lead the context with "what are you most likely to be asked to do here?" rather than only "what is this?". Pre-loading probable intents cuts the agent's exploration cost.
**Externals.** danielrosehill: every template has a "Common Tasks" section. abhishekray's `## Skills` map is an intent-ish variant.
**Praxion.** Skills carry "common operations" sections; the project CLAUDE.md has a repo-layout table and "where to find more" links — *discovery*-oriented. No top-level "frequent operations" list.
**Verdict.** **Adopt:** add a short `## Frequent operations` section (3–5 bullets) to the onboarded-project CLAUDE.md template, and consider one for Praxion's own CLAUDE.md ("you'll most often be asked to: modify a skill/agent/rule → load the matching crafting skill; run the pipeline → calibrate the tier; …"). Keep it tight to respect the budget.

### C1 — "Don't X → Do Y" rule-writing discipline · ✨ adoptable gap (codify it)
**What it means.** Every prohibition must carry the positive replacement ("NEVER use `any` — use `unknown` and narrow with type guards"). Prohibitions-without-alternatives are systematically weaker. Anti-patterns are best documented as `pattern | why it fails | what to do instead` tables.
**Externals.** abhishekray states it as a principle and uses the anti-pattern table format throughout.
**Praxion.** Praxion's rules generally do this in practice, but it's not stated as a *rule-authoring rule*.
**Verdict.** **Adopt:** add "every `NEVER`/`Don't` pairs with a `→ do this instead`" and the anti-pattern-table template to the `rule-crafting` skill (and reference it from `command-crafting` / `agent-crafting` where they emit prohibitions).

### C2 — Hooks (deterministic) vs rules (advisory) boundary · 🏆 Praxion ahead (state the criterion)
**What it means.** Rules/CLAUDE.md are *advisory* (the model may not comply). Hooks are *deterministic* (guaranteed lifecycle execution). If something must happen 100% of the time, it's a hook, not a rule line.
**Externals.** abhishekray states the criterion crisply.
**Praxion.** Has 30 hooks, a memory-gate hook, observability hooks, and a `hook-crafting` skill; the de-facto practice already follows the boundary (rules are declarative, hooks enforce). Praxion is well ahead in *practice*.
**Verdict.** Mostly already-have. **Small adopt:** add the explicit decision criterion ("if it must fire 100% with zero exceptions → hook, not rule") to `hook-crafting` and `rule-crafting` so the boundary is *stated*, not just embodied.

### C3 — Self-improvement / living-context loop · 🏆 Praxion ahead (surface the habit)
**What it means.** When the agent makes a mistake and gets corrected, it should record a durable rule so the mistake doesn't recur — CLAUDE.md (or memory, or a skill) as a living document.
**Externals.** abhishekray: the Boris-Cherny pattern — "say: 'Update CLAUDE.md so you don't make that mistake again'."
**Praxion.** Structurally *far* richer: the "Learn / Recall / Apply" loop; `LEARNINGS.md` (ephemeral, per-pipeline) → `skill-genesis` (harvests recurring learnings into new skills/rules/memory) → `sentinel` (independent ecosystem audit) → `memory-mcp` + `/remember`. (For Praxion-the-repo, memory-mcp is intentionally disabled — `PRAXION_DISABLE_MEMORY_MCP=1` — but the loop still runs via LEARNINGS/skill-genesis.)
**Verdict.** Already-have, and better. **Small adopt:** surface the *user-facing one-liner habit* — e.g., a line in the onboarded-project CLAUDE.md / a `/remember`-adjacent prompt: "when you correct me, ask me to propose a durable rule (a memory, a rule edit, or a skill note)." It's the on-ramp to the machinery Praxion already has.

### C4 — Real-world calibration anchors · ✨ adoptable gap (minor)
**What it means.** Benchmark data ("HumanLayer's CLAUDE.md is 57 lines; Boris Cherny's team ~83; Cloudflare's 230 — too long for most") gives authors a sanity check.
**Externals.** abhishekray ships the benchmark table.
**Praxion.** Measures its *own* surface but has no external comparison points to calibrate onboarded projects against.
**Verdict.** **Adopt (low priority):** add a small benchmark table to the onboarding companion docs and/or `rule-crafting` — "a project CLAUDE.md over ~150 lines is a smell; see these reference points."

### C5 — Machine-readable registry + validate-before-deploy · 🟡 partly already-have
**What it means.** A declarative manifest of "what artifact gets installed where, with structural pre-checks" rather than imperative install logic.
**Externals.** danielrosehill: `config.json` with `search_patterns` + `validation_rules` per template.
**Praxion.** `/onboard-project` is phased / gated / idempotent (10 phases, 9 gates); `install.sh --check`; `sync_canonical_blocks.py --check`; canonical blocks have a source-of-truth chain. This is *more* robust than danielrosehill's `config.json` — but it's procedural, not declarative.
**Verdict.** Mostly already-have. **Optional adopt:** if the onboarding logic ever gets refactored, a declarative `onboarding-manifest.json` (artifact → destination → preconditions) would be a clean shape — but this is a *nice-to-have*, not a gap.

### C6 — Depersonalization of shareable artifacts · ✨ adoptable gap (small, optional)
**What it means.** Before publishing a config set, scrub identity — name, email, GitHub handle, machine-specific paths — to generic placeholders.
**Externals.** danielrosehill: a `/depersonalise` slash command.
**Praxion.** `adapt-claude-to-agents` generates an `AGENTS.md.tmpl` from a project's `CLAUDE.md` (which is adjacent — it strips Claude-specific operational detail); onboarding writes user-specific bits.
**Verdict.** **Adopt (optional):** a `/depersonalise` command that, given a directory of config artifacts, replaces personal references with placeholders or user-supplied generic values. Useful for people who want to publish their `~/.claude/` or a project's `.claude/` setup. Small command-crafting task.

### D1 — Process-rigor calibration to task risk · 🏆 Praxion ahead (by a wide margin)
**What it means.** Don't run a pipeline for a typo; don't vibe-code a payment system. Match process weight to task scale/risk.
**Externals.** At most a one-liner ("for trivial tasks, use judgment"). None has a tier model.
**Praxion.** The Direct / Lightweight / Standard / Full / Spike tier table, the Tier Selector fast-path, `calibration_log.md`, SDD complexity triage, the agent-coordination protocol. This is one of Praxion's defining strengths and a direct, structural answer to Karpathy's "vibe coding raises the floor; agentic engineering preserves the ceiling."
**Verdict.** Already-have, dominant. **Do not chase** anything here — but *do* use this as the frame for D2/D3 below (the gap is that the always-loaded behavioral surface doesn't *reference* the calibration model).

### D2 — Speed-caution tradeoff acknowledgment · ✨ adoptable gap (micro)
**What it means.** The config names its own friction cost: "these guidelines bias toward caution over speed; for trivial tasks, use judgment."
**Externals.** forrestchang's header; the AlphaSignal article highlights it.
**Praxion.** The tier system *is* this idea — but the always-loaded `agent-behavioral-contract.md` reads as universal; an agent doing a Direct-tier typo fix gets the full contract with no acknowledgment that some of it is overhead at that scale.
**Verdict.** **Adopt:** add one calibration sentence to `agent-behavioral-contract.md` (or its deep-dive): "This contract biases toward caution; at Direct tier, apply it with proportionate judgment — surface assumptions and stay surgical always, but don't ceremony-fy a typo." Cross-reference the tier table. Tiny token cost; closes the "is this overkill for a one-liner?" ambiguity.

### D3 — Observable-effectiveness indicators · ✨ adoptable gap (micro)
**What it means.** A terse "you can tell this is working if …" so the user has an audit handle.
**Externals.** forrestchang's footer: "fewer unnecessary changes in diffs, fewer rewrites due to overcomplication, clarifying questions before mistakes rather than after."
**Praxion.** The sentinel's 10-dimension audit and verification-report failure-mode tags are *much* richer — but they're internal/heavyweight. No lightweight signal in the always-loaded surface.
**Verdict.** **Adopt:** add a one-line "the contract is working if: fewer collateral diffs, fewer over-engineering rewrites, clarifying questions before mistakes" to the behavioral-contract deep-dive reference. (Don't put it in the always-loaded rule — keep that terse.)

### E1 — Subagent strategy · 🏆 Praxion ahead (dominant) → 🚫 not comparable
Praxion's 16-agent coordination pipeline, parallel execution, boundary discipline, model routing, and background agents are an order of magnitude beyond abhishekray's ~4-line "use subagents liberally" note. **Nothing to adopt.** This is squarely in [`06-not-comparable.md`](06-not-comparable.md).

### E2 — Multi-tool / cross-assistant portability · 🏆 Praxion ahead (dominant) → 🚫 not comparable
forrestchang keeps three files (`CLAUDE.md` / `.cursor/rules/*.mdc` / `SKILL.md`) in *manual* sync; danielrosehill has a depersonalize-for-sharing flow. Praxion has assistant-agnostic shared assets, per-assistant config trees, `AGENTS.md.tmpl` generation, and `install.sh cursor`. **Don't chase** "format parity" — Praxion's approach (shared substance, per-assistant projection) is the better design. (The only crossover idea — `/depersonalise` — is captured under C6.)

### E3 — Anti-anthropomorphism / context-limit design · 🏆 Praxion ahead → 🚫 not comparable
Praxion's PreCompact hook → `PIPELINE_STATE.md`, persistent `.ai-state/`, the three-document model, and Compaction Guidance directly address Karpathy's "anterograde amnesia" point. The externals at most note that auto-memory exists. **Nothing to adopt** beyond E5 below.

### E4 — Project-archetype taxonomy → context · ✨ adoptable gap (medium)
**What it means.** "What kind of project is this?" should select the starting CLAUDE.md template and skill set. danielrosehill: 12 repo categories. abhishekray: 3 project templates (generic / Next.js / FastAPI).
**Praxion.** Has ML/AI-training archetype detection (`/onboard-project` Phase 8c) + the AaC tier (8b) + the ML skill family. But for the *common* (non-ML, non-AaC) case, `/onboard-project` writes a fairly uniform CLAUDE.md regardless of whether the project is a web app, a CLI tool, a library, a data pipeline, etc.
**Verdict.** **Adopt (medium):** extend `/onboard-project` with a light archetype probe (web app / CLI / library / service / data-pipeline / ML — Praxion already detects some of these) that selects a CLAUDE.md *skeleton* and a recommended skill set. Don't ship per-framework templates (that's the scope-creep trap from §2.2) — ship *skeletons* that prompt for the right sections.

### E5 — Auto-memory awareness · 🏆 Praxion ahead (sharpest of the five)
`memory-protocol.md` already covers the dual-system conflict (Claude auto-memory in `~/.claude/.../memory/` vs. Praxion memory-mcp in `.ai-state/memory.json`) and a conflict-resolution order ("Praxion memory wins — it has timestamps"; "more recent wins"; "verify against code if ambiguous"). abhishekray's layer-4 model is good but Praxion's is more complete. **Nothing to adopt** — possibly something to *contribute upstream* (the conflict-resolution framing is reusable).

### E6 — Plan-before-act + prompt-pattern library · ✨ adoptable gap (medium)
**What it means.** A curated set of *user-facing* prompts: "make the plan concise; end with a list of unresolved questions" (Pocock); "give me a second opinion on this approach"; "you seem stuck — re-plan from scratch"; "is there a more elegant way?"; "fix this bug autonomously and report".
**Externals.** abhishekray's `prompting-patterns.md` (11 patterns).
**Praxion.** Has plan mode, the `implementation-planner` agent, `command-crafting` — but no curated *prompt library* a user can reach for. The methodology mentions "ask clarifying questions" but doesn't hand the user the phrasings.
**Verdict.** **Adopt (medium):** add a `prompt-patterns` reference (under a skill, or as `docs/prompt-patterns.md`) with ~8–12 patterns, attributed. Low risk, genuinely useful, and it complements the `command-crafting` skill (some patterns graduate to commands).

### E7 — Bounded reviewable surface / small diffs · 🏆 Praxion ahead
"Stay Surgical" + git-conventions ("one logical change per commit", "small, focused commits", "separate refactoring from behavior changes", "review `git diff --staged` before every commit"). The `ml-training` skill documents Karpathy's `autoresearch` single-file constraint as a case study and Praxion has experiment-mode branch semantics. **Nothing to adopt.**

### E8 — Instruction/code separation (`program.md`) · 🏆 Praxion ahead
CLAUDE.md / rules / skills / ADRs are all first-class editable artifacts separate from code; ML projects ship a literal `program.md` (the experiment-loop meta-prompt) — the exact pattern Karpathy uses in `autoresearch`. **Nothing to adopt.**

---

## 6. Where Praxion is already ahead — do *not* chase these

(Full treatment in [`06-not-comparable.md`](06-not-comparable.md); summary here so the roadmap stays honest.)

- **The whole-system comparison is asymmetric.** Three of the four externals are single-artifact repos; one is an article. "Adopt their architecture" is meaningless — Praxion *is* the architecture.
- **A2 / A3 (anti-overengineering, surgical scope), D1 (process calibration), E1 (subagents), E2 (cross-assistant), E3 (context-limit handling), E5 (auto-memory), E7 (small diffs), E8 (instruction/code separation)** — Praxion already covers these as well or (usually) better. The only work here is *phrasing borrows* into the behavioral-contract reference (A2/A3) — not new mechanisms.
- **"One perfect CLAUDE.md template"** is *anti-Praxion*. Praxion deliberately distributes knowledge across rules (declarative) + skills (procedural) + a thin CLAUDE.md (navigation) governed by the `rules-vs-skills-vs-CLAUDE.md` decision model and a token budget. Fattening CLAUDE.md to look like a popular template would *regress* the design.
- **Multi-tool format parity** (forrestchang's 3-file manual sync) — Praxion's "shared substance, per-assistant projection" is the better answer; don't import the sync chore.
- **Framework starter templates** (abhishekray's Next.js/FastAPI; danielrosehill's HF depth) — out of scope; Praxion is an ecosystem, not a project-starter marketplace.
- **A "repo manager" agent persona** — danielrosehill's "repo manager" concept is *content* (a workspace CLAUDE.md), not an *agent*; building a new agent for it would duplicate the existing orchestrator + `/onboard-project`. Take the workspace-CLAUDE.md idea (B3); skip the persona.
- **Chasing star counts** — irrelevant; different audience.

---

## 7. Where the juicy gains are — the adoptable list (feeds the roadmap)

Ranked by value-to-cost. Detail and sequencing in [`07-praxion-roadmap.md`](07-praxion-roadmap.md).

| # | Adoptable item | Source | Target artifact(s) | Effort | Why it's juicy |
|---|---|---|---|---|---|
| 1 | **Document the path-scoped-rule Read-only trigger gotcha + audit Praxion's own path-scoped rules** | abhishekray B4 | `rules/CLAUDE.md`, `rule-crafting` skill, audit of 15 path-scoped rules | S | Closest thing to a latent bug; cheap to document, important to audit |
| 2 | **Direct/Lightweight-tier "state success criteria before coding" micro-template** | forrestchang A4 | `swe-agent-coordination-protocol.md` Lightweight specifics / `tier-templates.md` ref | S | Covers the *most common* tier, which is today the *least scaffolded* |
| 3 | **Quantified context-economy section** (instruction ceiling, re-injection math, worked example) | abhishekray B1 | `rule-crafting` skill / new reference | S–M | Turns the 25k budget from an edict into a reasoned model; improves every future rule decision |
| 4 | **Behavioral-contract phrasing borrows** (interpretations-not-silent-choice; own-mess dead code; "every changed line traces"; senior-engineer self-test; forbidden-category list; "200→50"; effectiveness-indicators; calibration notice) | forrestchang A1–A3, D2, D3 | `agent-behavioral-contract.md` (1–2 lines), `behavioral-contract.md` deep-dive reference (the rest) | S | Sharpens the contract's *bite* with near-zero always-loaded cost |
| 5 | **`## Frequent operations` + `## Verification` stanzas in the onboarded-project CLAUDE.md template** | danielrosehill B5, abhishekray A5/B2 | `/onboard-project` canonical blocks, onboarding companion docs | S–M | Cheap, high-signal; reduces agent exploration cost in onboarded projects |
| 6 | **`workspace-context` concept** — a CLAUDE.md for a directory-of-repos | danielrosehill B3 | `/onboard-project` (new optional phase), context-engineering docs, hierarchy table | M | The one genuinely new *structural* idea; composes with worktrees |
| 7 | **Project-archetype probe in `/onboard-project`** → selects a CLAUDE.md skeleton + skill set | danielrosehill E4, abhishekray E4 | `/onboard-project` | M | Better onboarding for non-ML projects without shipping framework templates |
| 8 | **`prompt-patterns` reference** (~8–12 user-facing patterns, attributed) | abhishekray E6 | new `docs/` doc or skill reference; cross-ref `command-crafting` | S–M | Genuinely useful; some patterns graduate to commands |
| 9 | **Rule/hook-authoring discipline rules** ("every `NEVER` pairs with a `→ do this`"; "100%-rule → hook, not rule line"; anti-pattern-table template) | abhishekray C1, C2 | `rule-crafting`, `hook-crafting` skills | S | Codifies existing good practice; improves every future rule/hook |
| 10 | **`/depersonalise` command** | danielrosehill C6 | new command | S | Optional; useful for people publishing their config |
| 11 | **CLAUDE.md-length benchmark table** | abhishekray C4 | onboarding companion docs / `rule-crafting` | S | Minor; a sanity check for onboarded projects |
| 12 | **"When I correct you, propose a durable rule" habit line** | abhishekray C3 | onboarded-project CLAUDE.md template | S | On-ramp to Praxion's existing learning machinery |

**Net always-loaded budget impact:** items 1, 3, 8, 9, 11 touch *skills/references* (on-demand, no always-loaded cost). Items 2, 4, 6, 12 add at most a few hundred bytes to always-loaded surfaces — and item 4 should be paired with a tightening pass on the big always-loaded rules (`swe-agent-coordination-protocol.md` at 15.1 KB, `agent-intermediate-documents.md` at 12.7 KB, `adr-conventions.md` at 11.2 KB) so the net change is **neutral-to-negative**. See [`07-praxion-roadmap.md`](07-praxion-roadmap.md) §"Budget discipline".

---

*Generated 2026-05-12 from four parallel `researcher` agents (one per source) + synthesis. Source analyses: [`sources/01`](sources/01-forrestchang-andrej-karpathy-skills.md) · [`sources/02`](sources/02-abhishekray07-claude-md-templates.md) · [`sources/03`](sources/03-danielrosehill-repo-managers-claudemd.md) · [`sources/04`](sources/04-alphasignal-karpathy-inspired-claudemd.md) · grounding: [`00-karpathy-critique.md`](00-karpathy-critique.md).*
