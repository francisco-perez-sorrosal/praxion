---
diataxis: explanation
audience: developer
---

# What Praxion Should *Not* Chase — Scope Mismatches & Non-Goals

> Companion to [`05-comparison.md`](05-comparison.md). The comparison surfaced a short list of genuinely adoptable ideas (→ [`07-praxion-roadmap.md`](07-praxion-roadmap.md)). This document is the other half of an honest analysis: the things these four external projects do that look like opportunities but aren't — because they conflict with Praxion's design, because Praxion already covers them as well or better, or because they only make sense at a scale Praxion isn't operating at. Naming these explicitly is what keeps the roadmap honest: a roadmap that quietly absorbs non-goals turns into busywork.

---

## 1. The whole-system comparison is asymmetric — "adopt their architecture" is a category error

Three of the four externals are **single-artifact repos**: a 60-line `CLAUDE.md` (`forrestchang/andrej-karpathy-skills`), a kit of copy-paste templates (`abhishekray07/claude-md-templates`), a personal library of directory-scoped `CLAUDE.md` files (`danielrosehill/Claude-Code-Repo-Managers-ClaudeMD`). The fourth is a newsletter article. Praxion is a Claude Code *plugin ecosystem* — 16 agents in a coordination pipeline, 52 skills with progressive disclosure, 22 rules, 35 commands, 30 hooks, a memory MCP server, a dashboard. There is no "their architecture" to adopt; Praxion *is* the architecture. The only thing transferable from these projects is **specific micro-techniques and framings**, lifted into Praxion's existing structures — never structural patterns, never scope.

**Implication:** any roadmap item phrased as "build a new X like project Y has" is suspect. The roadmap that came out of this study is ~80% "enrich an existing skill / canonical block" precisely because that's what the asymmetry demands.

## 2. "One perfect CLAUDE.md template" is *anti-Praxion*

The popular move — and the thing that earned `forrestchang/andrej-karpathy-skills` 127k stars — is a single, cleverly-worded `CLAUDE.md` that does everything. Praxion deliberately does the opposite: it **distributes knowledge** across always-loaded rules (declarative), on-demand skills (procedural), reference files (deep-dive), and a thin `CLAUDE.md` (navigation index) — governed by a `rules`-vs-`skills`-vs-`CLAUDE.md` decision model and a 25k-token always-loaded budget. Fattening Praxion's `CLAUDE.md` to resemble a popular template would **regress** the design. The right response to "your CLAUDE.md isn't as punchy as theirs" is "ours is an index by design; the punch lives in the rules and skills it points to" — not "let's add the missing 200 lines."

**Non-goal:** growing `CLAUDE.md` (or any always-loaded surface) to match an external template's content footprint. The roadmap's only `CLAUDE.md`-touching items are *pointers* and at most a one-sentence calibration notice — and they're paired with a compensating "cut" workstream.

## 3. Don't enshrine the folklore numbers

`abhishekray07/claude-md-templates`'s `principles.md` is a high-quality practitioner synthesis, but two of its headline figures are **not** Anthropic-documented and should not become Praxion canon:

- **"Frontier models follow ~150–200 total instructions before adherence drops uniformly; the system prompt consumes ~50 slots."** The official guidance is *"target under 200 **lines** per CLAUDE.md file; longer files reduce adherence"* and *"CLAUDE.md is context, not enforced config — specific/concise/structured wins"* — that's about lines per file, not a counted instruction ceiling. The ~150–200-*instruction* claim is a community estimate, possibly conflating the two. (Verified 2026-05-12 against `code.claude.com/docs/en/memory` — see [`08-claude-code-behavior-verification.md`](08-claude-code-behavior-verification.md) V4.)
- **The "43K initial / 93K re-injections / 50K conversation" session breakdown.** A single observed session, not a documented mechanism. Plausible *if* path-scoped rules re-inject on each matching Read, but the docs don't describe a per-tool-call multiplier (V5).

**Non-goal:** importing these numbers into `rule-crafting`, CLAUDE.md, or any rule. The roadmap imports the *discipline* (every always-loaded token earns its attention share; <200 lines per file; context-not-config) and the *citable doc language* — not the folklore.

## 4. Agent self-modification of always-loaded instructions — deliberately rejected

The "self-improving CLAUDE.md" idea in the Karpathy-adjacent discourse, in its strong form, lets the agent *rewrite its own always-loaded instructions* after a mistake. Praxion deliberately externalizes learning instead: ephemeral `LEARNINGS.md` (per-pipeline) → `skill-genesis` (harvests recurring learnings into *new* skills/rules/memory, **interactively, with user approval**) → `sentinel` (independent ecosystem audit) → memory MCP / `/remember`. This is a *design choice*, not an oversight — letting agents silently mutate the surface every session in every project sees is exactly the kind of un-audited drift Praxion's whole structure exists to prevent. The most Praxion should take from "self-improving CLAUDE.md" is the **user-facing habit line** ("when I correct you, propose a durable rule — a memory entry, a rule edit, or a skill note") as an on-ramp to the machinery it already has (roadmap item 2).

**Non-goal:** an agent path that edits `CLAUDE.md` / always-loaded rules without human review.

## 5. Multi-tool format-parity sync is a chore, not a feature

`forrestchang/andrej-karpathy-skills` keeps three files in *manual* sync (`CLAUDE.md` ↔ `.cursor/rules/karpathy-guidelines.mdc` ↔ `skills/karpathy-guidelines/SKILL.md`), with a `CURSOR.md` instructing contributors to update all three. Praxion's cross-assistant story is structurally better: **shared substance, per-assistant projection** — assistant-agnostic `skills/`/`commands/`/`agents/` at the repo root; per-assistant config under `claude/`/`codex/`/`cursor/`; `AGENTS.md.tmpl` generation via the `adapt-claude-to-agents` skill; `install.sh cursor` to export. Importing a "keep N copies in sync" obligation would *worsen* Praxion's design.

**Non-goal:** N-way manual format parity. (The one genuinely useful crossover idea — a `/depersonalise` command for publishing config sets — is in the roadmap's *parked* appendix, not because it's bad but because it's optional.)

## 6. Framework starter templates are not Praxion's job

`abhishekray07/claude-md-templates` ships Next.js/TypeScript and Python/FastAPI project templates; `danielrosehill/Repo-Managers-ClaudeMD` ships Hugging-Face-Spaces depth (Gradio code samples, hardware-tier tables, Space YAML frontmatter). Praxion operates at *ecosystem* scale — it provides the *machinery* (`/new-project`, `/onboard-project`, the AaC tier, the ML-training conventions, the language skills) that helps a project build *its own* CLAUDE.md. Shipping a marketplace of per-framework `CLAUDE.md` templates would be scope creep into a different product category, and a maintenance liability (templates rot fast). The roadmap's `/onboard-project` archetype-probe item (parked) is explicitly scoped to *skeletons* — "which sections to prompt for" — not framework templates.

**Non-goal:** a library of per-framework / per-platform `CLAUDE.md` templates.

## 7. A "repo manager" *agent* persona — content, not an agent

`danielrosehill`'s "repo manager" concept is genuinely interesting, but it is **content** (a `CLAUDE.md` describing a directory of repos), not an **agent**. Building a new Praxion agent for "managing a portfolio of repos" would duplicate the existing orchestrator + `/onboard-project` + `/create-worktree`/`/merge-worktree` + `clean-work`/`clean-auto-memory` machinery, and add another agent to the 16 Praxion already maintains. The roadmap takes the **workspace-`CLAUDE.md` idea** (roadmap item 5, scoped to worktree hygiene — the concrete, dogfood-able use case) and leaves the persona on the floor.

**Non-goal:** a `repo-manager` agent.

## 8. Star counts, virality, "simplicity" as a competitive axis

`forrestchang/andrej-karpathy-skills`'s 127k stars reflect Karpathy's amplification of a community looking for a one-file shortcut. Praxion's audience is developers (and teams) who want a structured, guaranteed, auditable SDLC — not a one-file nudge. Competing on "fewest lines to drop in" is a category error: Praxion's value is in the *guarantees the scaffolding provides* (the verifier, the tier calibration, the behavioral contract, the traceability, the ADR trail), and those guarantees cost structure. The comparison should never become "why don't we have as few lines as the popular repo."

**Non-goal:** treating brevity or adoption metrics of single-file repos as a Praxion success criterion.

## 9. Citing "Karpathy" loosely

Half the "Karpathy-inspired" design moves in the discourse — terse CLAUDE.md, anti-pattern checklists, explicit verification gates, scoped/just-in-time context, self-updating instructions — are **community engineering**, not Karpathy prescriptions. Karpathy's *actual* statements (the January 2026 X-post failure modes; the YC 2025 "context window is your lever" / "anterograde amnesia" / autonomy-slider talk; the `autoresearch` single-file-constraint / `program.md` pattern; "keep AI on a leash") are at the *workflow* and *product-design* level — see [`00-karpathy-critique.md`](00-karpathy-critique.md) for tiered sourcing. When a Praxion artifact invokes Karpathy's authority, it should cite the X post / the talk / the repo, **not** `forrestchang/andrej-karpathy-skills` (which Karpathy did not write or endorse). This isn't a "don't adopt" — it's a "don't mis-attribute."

**Non-goal:** "Karpathy says X" claims that trace only to community synthesis. (The roadmap's behavioral-contract items cite the verbatim X-post failure modes, which *are* Karpathy.)

## 10. Dimensions Praxion already covers as well or better — already-have, don't re-implement

These appeared as "critical dimensions" in one or more external analyses, but Praxion already has them — usually with more rigor. Listed with where, so nobody re-builds them:

| Dimension | Praxion already has it at | Verdict |
|---|---|---|
| Minimum-viable-code / anti-overengineering | `agent-behavioral-contract.md` "Simplicity First"; `~/.claude/CLAUDE.md` "Incremental Evolution"/"Behavior-Driven Development" | already-have (roadmap adds only *phrasing handles* to the deep-dive ref) |
| Surgical scope | `agent-behavioral-contract.md` "Stay Surgical" + stop-and-re-scope escalation; `coding-style`/`git-conventions` | already-have (ditto) |
| Process-rigor calibration to task risk | `swe-agent-coordination-protocol.md` tier table (Direct/Lightweight/Standard/Full/Spike) + Tier Selector + `calibration_log.md` + SDD complexity triage | already-have, **dominant** — none of the externals come close |
| Subagent strategy | `swe-agent-coordination-protocol.md`; 16 agents; parallel execution; model routing; background agents | already-have, **dominant** |
| Cross-assistant portability | assistant-agnostic `skills/`/`commands/`/`agents/`; `claude/`/`codex/`/`cursor/` config; `AGENTS.md.tmpl` gen; `install.sh cursor` | already-have, **dominant** (and *better* than N-way manual sync — see §5) |
| Anti-anthropomorphism / context-limit handling | PreCompact hook → `.ai-work/PIPELINE_STATE.md`; persistent `.ai-state/`; three-document model; Compaction Guidance in CLAUDE.md | already-have |
| Auto-memory awareness | `memory-protocol.md` (dual-system conflict + conflict-resolution order) | already-have, **sharpest of the five** — possibly worth *contributing upstream*, not adopting |
| Bounded reviewable surface / small diffs | `agent-behavioral-contract.md` "Stay Surgical"; `git-conventions.md` (one logical change per commit, small focused commits, review staged diff); experiment-branch semantics | already-have |
| Instruction/code separation (`program.md`) | CLAUDE.md/rules/skills/ADRs all separate from code; ML projects ship a literal `program.md` (`ml-training` skill) | already-have |
| Verification loop (ecosystem level) | `verifier` agent; "How to verify your work" in CLAUDE.md; `sync_canonical_blocks.py --check`; `/sentinel`; eval framework | already-have (roadmap adds only a per-project `## Verification` *stanza* in the onboarded-CLAUDE.md template) |
| Hooks-vs-rules boundary | 30 hooks + memory-gate + observability; `hook-crafting` skill; de-facto practice | already-have (roadmap adds only the explicit decision *criterion* to `hook-crafting`/`rule-crafting`) |
| Machine-readable artifact registry + validate-before-deploy | `/onboard-project` (10 phases, 9 gates, idempotent); `install.sh --check`; `sync_canonical_blocks.py --check`; canonical-block source-of-truth chain | already-have (more robust than `config.json`; a declarative manifest is a *nice-to-have*, not a gap) |

---

## Summary

Of the ~28 dimensions catalogued in [`05-comparison.md`](05-comparison.md), roughly half are **already covered as well or better** (§10), and a handful are **active non-goals** that conflict with Praxion's design or scale (§1–9). The genuinely adoptable remainder — six headline items + a small parked appendix — is in [`07-praxion-roadmap.md`](07-praxion-roadmap.md). The discipline this document enforces: when you're tempted to add something because a popular project has it, check it against §1–10 first.
