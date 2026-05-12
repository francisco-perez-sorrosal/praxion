# Analysis: forrestchang/andrej-karpathy-skills

## 1. What it is

**Type:** Claude Code plugin / CLAUDE.md template / skills pack  
**Maturity signals:** 126,824 stars, 12,888 forks, 88 open issues, last push 2026-04-20, created 2026-01-27 (less than 4 months old at analysis date), 7 contributors (main author: forrestchang / Jiayuan), no explicit LICENSE file in repo root (plugin.json says MIT)  
**Authorship:** Forrestchang (GitHub: @jiayuan_jy on X), single primary author; community PRs welcome  
**License:** MIT (per plugin.json; no standalone LICENSE file in repo root)

This repo delivers a single, terse `CLAUDE.md` file — 60 lines of behavioral guidelines — that a developer drops into any project root (or installs as a Claude Code plugin via `/plugin marketplace add forrestchang/andrej-karpathy-skills`) to constrain Claude Code's worst failure modes. The file is author-stated to be "derived from Andrej Karpathy's observations on LLM coding pitfalls." It ships the same four principles in three synchronized formats: `CLAUDE.md` (Claude Code), `.cursor/rules/karpathy-guidelines.mdc` (`alwaysApply: true` for Cursor), and `skills/karpathy-guidelines/SKILL.md` (reusable skill). The plugin manifest (`plugin.json` + `marketplace.json`) makes it installable with one command. Despite its extreme simplicity — one opinionated file, no pipeline, no agents, no tooling — it has the highest star count of any CLAUDE.md-style repo as of May 2026.

---

## 2. Relationship to Karpathy's critique

### Direct Karpathy statements (sourced from his January 26, 2026 X post, as cited by the AlphaSignal article)

Karpathy identified three failure modes in LLM coding agents:

1. **Silent wrong assumptions:** "The models make wrong assumptions on your behalf and just run along with them without checking. They don't manage their confusion..."
2. **Over-complication:** "They really like to overcomplicate code and APIs, bloat abstractions, don't clean up dead code..."
3. **Orthogonal damage:** "They still sometimes change/remove comments and code they don't sufficiently understand as side effects..."
4. **On goal-framing (the positive flip):** "LLMs are exceptionally good at looping until they meet specific goals... Don't tell it what to do, give it success criteria..."

Karpathy separately (June 2025, widely quoted) defined context engineering as: "the delicate art and science of filling the context window with just the right information for the next step" — and: "Too little or of the wrong form and the LLM doesn't have the right context for optimal performance. Too much or too irrelevant, and the LLM costs might go up, and performance might come down."

### Community interpretation by forrestchang (NOT direct Karpathy statements)

The four principles in the CLAUDE.md file — Think Before Coding / Simplicity First / Surgical Changes / Goal-Driven Execution — are **forrestchang's operationalization** of Karpathy's failure-mode diagnosis. Karpathy did not write the file and has not publicly endorsed it. The AlphaSignal article is explicit: "Karpathy identified the problems; Chang built the remedy."

The "keep the model on a leash" framing is a community shorthand (seen in blog posts and discussions) for the overall pattern of behavioral constraint; Karpathy has not used this exact phrase in the sources reviewed.

---

## 3. Core competencies / dimensions

### D1 — Explicit assumption surfacing before action

The agent is instructed to state assumptions before implementing, present multiple interpretations rather than silently choosing one, and stop to name confusion rather than proceed under uncertainty.

**Snippet from CLAUDE.md §1:**
```
Don't assume. Don't hide confusion. Surface tradeoffs.

Before implementing:
- State your assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them - don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what's confusing. Ask.
```

### D2 — Minimum-viable-code discipline (anti-speculation)

The agent is prohibited from adding features, abstractions, configurability, or error handling that was not explicitly requested. The test is a senior engineer's perception of over-complication. The 200→50-line heuristic operationalizes "simplicity."

**Snippet from CLAUDE.md §2:**
```
Minimum code that solves the problem. Nothing speculative.

- No features beyond what was asked.
- No abstractions for single-use code.
- No "flexibility" or "configurability" that wasn't requested.
- No error handling for impossible scenarios.
- If you write 200 lines and it could be 50, rewrite it.
```

### D3 — Surgical scope discipline (own-mess-only cleanup)

When editing existing code, the agent must not improve adjacent code, refactor unbroken things, or match its own style preferences. The critical split: the agent may remove orphans it *created*; it must *not* remove pre-existing dead code. Unrelated dead code is mentioned to the user, not deleted.

**Snippet from CLAUDE.md §3:**
```
Touch only what you must. Clean up only your own mess.

The test: Every changed line should trace directly to the user's request.
```

### D4 — Goal-driven execution with verifiable success criteria

Tasks are transformed into testable assertions before implementation begins. The canonical reframe pattern is explicit ("Add validation" → "Write tests for invalid inputs, then make them pass"). Multi-step tasks require a brief numbered plan with a verification check at each step.

**Snippet from CLAUDE.md §4:**
```
For multi-step tasks, state a brief plan:
1. [Step] → verify: [check]
2. [Step] → verify: [check]
3. [Step] → verify: [check]

Strong success criteria let you loop independently. Weak criteria ("make it work") require constant clarification.
```

### D5 — Self-evaluation effectiveness indicators

The file ends with three explicit behavioral signals the user can observe to know whether the guidelines are working: fewer unnecessary diff changes, fewer rewrites from overengineering, and clarifying questions arriving before implementation rather than after mistakes. This gives the *user* an audit handle.

**Snippet from CLAUDE.md (footer):**
```
These guidelines are working if: fewer unnecessary changes in diffs, fewer rewrites due
to overcomplication, and clarifying questions come before implementation rather than
after mistakes.
```

### D6 — Speed-caution tradeoff acknowledgment + escape hatch

The file explicitly acknowledges its own performance cost upfront: "These guidelines bias toward caution over speed. For trivial tasks, use judgment." This names the trade-off rather than pretending the constraints are free.

**Snippet from CLAUDE.md (preamble):**
```
Tradeoff: These guidelines bias toward caution over speed. For trivial tasks, use judgment.
```

### D7 — Multi-tool parity (one spec, three formats)

The same four principles are kept synchronized across `CLAUDE.md`, `.cursor/rules/karpathy-guidelines.mdc` (with `alwaysApply: true`), and `skills/karpathy-guidelines/SKILL.md`. The CURSOR.md explicitly tells contributors: "when updating the four core principles, you must keep all three files in sync." This is a distribution pattern, not a content pattern.

### D8 — Claude Code plugin packaging

The repo ships `plugin.json` + `marketplace.json` enabling one-command install: `/plugin marketplace add forrestchang/andrej-karpathy-skills`. This makes adoption zero-friction for Claude Code users without manual file editing.

**Plugin manifest fragment:**
```json
{
  "name": "andrej-karpathy-skills",
  "skills": ["./skills/karpathy-guidelines"]
}
```

---

## 4. Ranking + criticality boundary

Ranked most → least important:

1. **D1 — Explicit assumption surfacing** ← CRITICAL
2. **D2 — Minimum-viable-code discipline** ← CRITICAL
3. **D3 — Surgical scope discipline** ← CRITICAL
4. **D4 — Goal-driven execution with verifiable success criteria** ← CRITICAL

------- **CRITICALITY BOUNDARY** -------

5. **D5 — Self-evaluation effectiveness indicators** ← Supporting
6. **D6 — Speed-caution tradeoff acknowledgment** ← Supporting
7. **D7 — Multi-tool parity** ← Nice-to-have
8. **D8 — Plugin packaging** ← Nice-to-have

**Boundary justification:** D1–D4 are the four principles the repo was built to express; removing any one of them would mean the file no longer responds to one of Karpathy's four diagnosed failure modes. The file would fail its stated purpose. D5 and D6 are meta-layer additions (observability signal + escape hatch) that improve usability but do not change the behavioral contract. D7 and D8 are distribution mechanics — they affect reach, not substance.

---

## 5. Scope vs Praxion

### D1 — Explicit assumption surfacing

**(a) Does Praxion have it?**  
Yes. Praxion's `rules/swe/agent-behavioral-contract.md` (always loaded) encodes "Surface Assumptions" as the first named non-negotiable behavior: "list assumptions before acting; ask when ambiguity could produce the wrong artifact." This maps exactly to D1.

**(b) Is it expressed more sharply here?**  
Partially. The forrestchang version adds one concrete micro-rule Praxion's contract does not name explicitly: **"If multiple interpretations exist, present them — don't pick silently."** This disambiguation-presentation behavior is implied by Praxion's "Surface Assumptions" but not spelled out. The "stop. Name what's confusing. Ask." rhythm is also crisper as a directive sentence.

**(c) Not applicable at Praxion's scale?**  
No — fully applicable. The principle is scale-neutral.

### D2 — Minimum-viable-code discipline

**(a) Does Praxion have it?**  
Yes. "Simplicity First" is the fourth named behavior in the behavioral contract. CLAUDE.md principle "Incremental Evolution" also states: "The simplest thing that works is the seed, not the ceiling." The "Behavior-Driven Development" principle states: "the implementation should be the simplest thing that achieves it."

**(b) Is it expressed more sharply here?**  
Yes, in one specific way: the **200→50-line heuristic** and the explicit prohibition list ("No abstractions for single-use code," "No 'flexibility' or 'configurability' that wasn't requested") are more operationally concrete than Praxion's principle statements. Praxion's contract says "prefer the smallest solution that meets the behavior; every added line, file, or dependency must earn its place" — same concept, but without the enumerate-the-forbidden-categories structure.

**(c) Not applicable?**  
No — fully applicable.

### D3 — Surgical scope discipline

**(a) Does Praxion have it?**  
Yes. "Stay Surgical" is the third named behavior in the behavioral contract: "touch only what the change requires; if scope grew, stop and re-scope instead of silently expanding." CLAUDE.md methodology section adds "Only touch what the change requires — minimal scope, minimal blast radius."

**(b) Is it expressed more sharply here?**  
Yes. The **own-mess-only dead-code split** is precise in a way Praxion's contract is not: "Remove imports/variables/functions that YOUR changes made unused. Don't remove pre-existing dead code unless asked." Praxion's "Stay Surgical" covers this by implication but does not enumerate the dead-code case explicitly. The test heuristic ("Every changed line should trace directly to the user's request") is also a sharper operationalization than Praxion's phrasing.

**(c) Not applicable?**  
No — fully applicable.

### D4 — Goal-driven execution with verifiable success criteria

**(a) Does Praxion have it?**  
Partially. Praxion's methodology section has "Verify" as the third pillar: "Never mark a task complete without proving it works. Run tests, check logs, diff behavior." The Spec-Driven Development skill introduces REQ-IDs and acceptance criteria. The behavioral contract's "Register Objection" covers pushback. But Praxion does not have a canonical pattern for *transforming a vague task into a testable goal at intake* in an always-loaded surface.

**(b) Is it expressed more sharply here?**  
Yes, in one specific mechanic: the **task-reframe pattern** ("Add validation" → "Write tests for invalid inputs, then make them pass") is a concrete, memorable formula for intake disambiguation. The numbered step-plan with `→ verify: [check]` format is a simple, universally applicable micro-template. Praxion achieves the same outcome through `WIP.md` + `IMPLEMENTATION_PLAN.md` steps but at a much heavier process weight.

**(c) Not applicable at scale?**  
Partially. For Praxion's full pipeline (Standard/Full tier), goal-driven execution is handled by the planner + verifier stages with REQ-ID traceability — far more rigorous than this micro-template. For Direct and Lightweight tier tasks (single-file fix, config, typo, 2-3 file change) where the full pipeline is not invoked, Praxion has no in-place equivalent of this lightweight "define success criteria before you touch code" prompt. The micro-template is most valuable at those tiers.

---

## 6. Concrete artifacts worth copying

### 6.1 The full CLAUDE.md text (verbatim — the primary artifact)

```markdown
Behavioral guidelines to reduce common LLM coding mistakes. Merge with project-specific
instructions as needed.

**Tradeoff:** These guidelines bias toward caution over speed. For trivial tasks, use judgment.

## 1. Think Before Coding

**Don't assume. Don't hide confusion. Surface tradeoffs.**

Before implementing:
- State your assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them - don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what's confusing. Ask.

## 2. Simplicity First

**Minimum code that solves the problem. Nothing speculative.**

- No features beyond what was asked.
- No abstractions for single-use code.
- No "flexibility" or "configurability" that wasn't requested.
- No error handling for impossible scenarios.
- If you write 200 lines and it could be 50, rewrite it.

Ask yourself: "Would a senior engineer say this is overcomplicated?" If yes, simplify.

## 3. Surgical Changes

**Touch only what you must. Clean up only your own mess.**

When editing existing code:
- Don't "improve" adjacent code, comments, or formatting.
- Don't refactor things that aren't broken.
- Match existing style, even if you'd do it differently.
- If you notice unrelated dead code, mention it - don't delete it.

When your changes create orphans:
- Remove imports/variables/functions that YOUR changes made unused.
- Don't remove pre-existing dead code unless asked.

The test: Every changed line should trace directly to the user's request.

## 4. Goal-Driven Execution

**Define success criteria. Loop until verified.**

Transform tasks into verifiable goals:
- "Add validation" → "Write tests for invalid inputs, then make them pass"
- "Fix the bug" → "Write a test that reproduces it, then make it pass"
- "Refactor X" → "Ensure tests pass before and after"

For multi-step tasks, state a brief plan:
1. [Step] → verify: [check]
2. [Step] → verify: [check]
3. [Step] → verify: [check]

Strong success criteria let you loop independently. Weak criteria ("make it work")
require constant clarification.

---

**These guidelines are working if:** fewer unnecessary changes in diffs, fewer rewrites
due to overcomplication, and clarifying questions come before implementation rather
than after mistakes.
```

### 6.2 Phrasings worth lifting into Praxion's behavioral-contract rule or references

- **"If multiple interpretations exist, present them — don't pick silently."** — sharpens "Surface Assumptions" in `agent-behavioral-contract.md`
- **"If you notice unrelated dead code, mention it — don't delete it."** — sharpens "Stay Surgical" dead-code handling
- **"The test: Every changed line should trace directly to the user's request."** — a one-line audit heuristic for "Stay Surgical"
- **"Would a senior engineer say this is overcomplicated?"** — a self-test question for "Simplicity First"
- **"Strong success criteria let you loop independently."** — explains the *why* of goal-driven framing, useful for the behavioral contract's deep-dive reference
- **The effectiveness indicators footer** — "These guidelines are working if: fewer unnecessary changes in diffs, fewer rewrites due to overcomplication, clarifying questions come before implementation rather than after mistakes." — an observable-outcomes frame that Praxion's contract lacks

### 6.3 Task-reframe micro-template

```
Transform tasks into verifiable goals:
- "[vague task]" → "[testable assertion or test-first reframe]"

For multi-step tasks, state a brief plan:
1. [Step] → verify: [check]
2. [Step] → verify: [check]
```
Applicable in Praxion's Direct/Lightweight tier process, where no WIP.md is maintained.

### 6.4 Speed-caution trade-off disclosure pattern

```
Tradeoff: These guidelines bias toward caution over speed. For trivial tasks, use judgment.
```
Praxion's behavioral contract could benefit from a similar explicit trade-off acknowledgment. Currently Praxion's always-loaded rules state constraints without naming the cost.

### 6.5 File tree shape

```
CLAUDE.md                              ← primary, drop-in, universal
skills/
  karpathy-guidelines/
    SKILL.md                           ← same content as CLAUDE.md, skill-packaged
.cursor/rules/
  karpathy-guidelines.mdc             ← Cursor port, alwaysApply: true
.claude-plugin/
  plugin.json                         ← Claude Code plugin metadata
  marketplace.json                    ← marketplace registration
EXAMPLES.md                           ← usage examples
```

---

## 7. Sources consulted

- [forrestchang/andrej-karpathy-skills — GitHub repo main page](https://github.com/forrestchang/andrej-karpathy-skills) — repo overview, README, stars/forks, fetched 2026-05-12
- [GitHub API: repo metadata](https://api.github.com/repos/forrestchang/andrej-karpathy-skills) — stars, forks, open issues, created/updated timestamps, fetched 2026-05-12
- [GitHub API: root contents](https://api.github.com/repos/forrestchang/andrej-karpathy-skills/contents/) — file tree, fetched 2026-05-12
- [GitHub API: skills/karpathy-guidelines contents](https://api.github.com/repos/forrestchang/andrej-karpathy-skills/contents/skills/karpathy-guidelines) — skill file listing, fetched 2026-05-12
- [GitHub API: .claude-plugin contents](https://api.github.com/repos/forrestchang/andrej-karpathy-skills/contents/.claude-plugin) — plugin manifest files, fetched 2026-05-12
- [GitHub API: .cursor/rules contents](https://api.github.com/repos/forrestchang/andrej-karpathy-skills/contents/.cursor/rules) — Cursor rule file listing, fetched 2026-05-12
- [GitHub API: contributors](https://api.github.com/repos/forrestchang/andrej-karpathy-skills/contributors) — contributor count and names, fetched 2026-05-12
- [CLAUDE.md — raw](https://raw.githubusercontent.com/forrestchang/andrej-karpathy-skills/main/CLAUDE.md) — full text, fetched 2026-05-12 (also via GitHub HTML view for verbatim confirmation)
- [CURSOR.md — raw](https://raw.githubusercontent.com/forrestchang/andrej-karpathy-skills/main/CURSOR.md) — multi-tool sync instructions, fetched 2026-05-12
- [skills/karpathy-guidelines/SKILL.md — raw](https://raw.githubusercontent.com/forrestchang/andrej-karpathy-skills/main/skills/karpathy-guidelines/SKILL.md) — skill-packaged version, fetched 2026-05-12
- [.cursor/rules/karpathy-guidelines.mdc — raw](https://raw.githubusercontent.com/forrestchang/andrej-karpathy-skills/main/.cursor/rules/karpathy-guidelines.mdc) — Cursor port with `alwaysApply: true`, fetched 2026-05-12
- [.claude-plugin/plugin.json — raw](https://raw.githubusercontent.com/forrestchang/andrej-karpathy-skills/main/.claude-plugin/plugin.json) — plugin manifest, fetched 2026-05-12
- [.claude-plugin/marketplace.json — raw](https://raw.githubusercontent.com/forrestchang/andrej-karpathy-skills/main/.claude-plugin/marketplace.json) — marketplace registration, fetched 2026-05-12
- [README.md — raw](https://raw.githubusercontent.com/forrestchang/andrej-karpathy-skills/main/README.md) — author, motivation, installation instructions, fetched 2026-05-12
- [AlphaSignal article: "Karpathy-Inspired CLAUDE.md: How to..."](https://alphasignalai.substack.com/p/karpathy-inspired-claudemd-how-to) — attribution clarification (Karpathy diagnosed, Chang operationalized; Karpathy did not write the file), Karpathy X post quotes (Jan 26 2026), fetched 2026-05-12
- [Karpathy 2025 LLM Year in Review](https://karpathy.bearblog.dev/year-in-review-2025/) — context engineering definition, Claude Code assessment, agent architecture views, fetched 2026-05-12
- [PureAI: Karpathy Puts Context at the Core of AI Coding](https://pureai.com/articles/2025/09/23/karpathy-puts-context-at-the-core-of-ai-coding.aspx) — direct Karpathy quotes on context engineering, fetched 2026-05-12
- [WebSearch: Karpathy LLM coding agents critique, vibe coding, context window discipline 2024–2026] — background on "vibe coding" coinage (Feb 2025), "agentic engineering" shift (2026), context engineering framing (Jun 2025), fetched 2026-05-12
