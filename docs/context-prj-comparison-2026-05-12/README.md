---
diataxis: explanation
audience: developer
---

# Context-Engineering Comparison Study — 2026-05-12

A point-in-time study comparing four external "Karpathy-inspired CLAUDE.md" projects against Praxion's own context-engineering setup, to find ideas Praxion can adopt for its project-management artifacts (agents, rules, skills, commands, CLAUDE.md). The four externals are much smaller than Praxion (single-artifact repos + one article); the point was to mine them for transferable micro-techniques and framings, not to match their scope.

**The actionable output is the roadmap** — [`07-praxion-roadmap.md`](07-praxion-roadmap.md), also copied to [`../../.ai-state/ROADMAP.md`](../../.ai-state/ROADMAP.md) as the working roadmap to follow. The rest of this folder is the supporting analysis: it's a dated snapshot, not a maintained document.

## What's here

| File | What it is | Read it for |
|---|---|---|
| [`00-karpathy-critique.md`](00-karpathy-critique.md) | What Andrej Karpathy *actually* said about LLM coding agents, with tiered sourcing ([VERBATIM]/[PARAPHRASE]/[REPORTED]), vs. community extrapolation. | The evaluation lens. Distinguishing Karpathy's words from "Karpathy-inspired" community engineering. |
| [`sources/01-forrestchang-andrej-karpathy-skills.md`](sources/01-forrestchang-andrej-karpathy-skills.md) | Deep dive: the 127k-star 60-line CLAUDE.md (Think Before Coding / Simplicity First / Surgical Changes / Goal-Driven Execution). | The behavioral micro-rules and phrasings worth lifting. |
| [`sources/02-abhishekray07-claude-md-templates.md`](sources/02-abhishekray07-claude-md-templates.md) | Deep dive: the 203-star structured starter kit + 36 KB `principles.md` (token economy, progressive disclosure, path-scoped rules, verification loop, hooks-vs-rules). | The context-economy discipline and the path-scoped-rules gotcha. |
| [`sources/03-danielrosehill-repo-managers-claudemd.md`](sources/03-danielrosehill-repo-managers-claudemd.md) | Deep dive: the "repo manager" template library — a CLAUDE.md scoped to a *directory of repos*. | The workspace context layer and the "common tasks" pattern. |
| [`sources/04-alphasignal-karpathy-inspired-claudemd.md`](sources/04-alphasignal-karpathy-inspired-claudemd.md) | Deep dive: the AlphaSignal article that popularized the forrestchang repo. | How faithfully the discourse represents Karpathy; the calibration-notice idea. |
| [`05-comparison.md`](05-comparison.md) | **The comparison.** Executive summary · per-source lessons · the unified deduped critical-dimension set · the 5-system matrix (4 externals + Praxion) · dimension-by-dimension detail · where Praxion is already ahead · the adoptable list. | The full picture. Start here. |
| [`06-not-comparable.md`](06-not-comparable.md) | Scope mismatches and non-goals — what Praxion should *not* chase (and why), plus the dimensions Praxion already covers as well or better. | Before adding anything not on the roadmap. |
| [`07-praxion-roadmap.md`](07-praxion-roadmap.md) | **The roadmap.** Six headline items + a parked appendix, each scoped to a Praxion artifact with a "done when" and a budget impact; the three-step "relocate-don't-delete" cut protocol; sequencing. | Execution. (Working copy: [`../../.ai-state/ROADMAP.md`](../../.ai-state/ROADMAP.md).) |
| [`08-claude-code-behavior-verification.md`](08-claude-code-behavior-verification.md) | The empirical Claude Code behavior check (path-scoped-rule triggering, rule re-injection, `CLAUDE.local.md`/`claudeMdExcludes`, the "~150–200 instruction" claim, ancestor/nested CLAUDE.md loading, auto-memory) — verified 2026-05-12 against the official docs + GitHub issues. | Why the roadmap's P1 exists and why the folklore numbers are *not* imported. |

## Headline findings

- **Praxion already covers ~80% of the critical dimensions** these projects embody — usually with more rigor (behavioral contract enforced by a verifier, tiered process calibration, a 25k-token budget, a 16-agent pipeline, a memory protocol, a `LEARNINGS.md → skill-genesis → sentinel` learning loop). The externals are not ahead architecturally; they're sharper on a small set of *micro-techniques and framings*.
- **The one near-bug:** path-scoped rules (`paths:` frontmatter) inject only when Claude *reads* a matching file — not on Write/Edit — so greenfield file creation silently misses `coding-style`/`readme-style`/etc. Verified; mitigated by an agent-prompt instruction (roadmap P1). (A separate `~/.claude/rules/` `paths:`-ignored bug is Windows-only; not reproduced on macOS/Linux.)
- **The "thin-tier" gap:** Praxion's criteria-first / verify-before-done discipline is concentrated at the Standard/Full pipeline; the Direct/Lightweight tiers (the most common) have no in-place equivalent — the externals' lightweight micro-templates fill exactly that hole (roadmap P2).
- **The one structural idea worth taking:** a "workspace / directory-of-repos" CLAUDE.md tier — scoped down to **worktree hygiene** (warning a "lost" agent which checkout it's in, so it stops writing into `main`) — is cheap and native to Claude Code's ancestor-CLAUDE.md loading (roadmap P5).
- **The folklore numbers** ("~150–200-instruction ceiling", a "43K/93K/50K" session breakdown) did *not* survive verification and are explicitly *not* imported; the roadmap imports the citable doc guidance instead.
