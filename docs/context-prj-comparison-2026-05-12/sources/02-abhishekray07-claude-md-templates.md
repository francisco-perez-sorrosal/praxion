# Analysis: abhishekray07/claude-md-templates

## 1. What it is

**Type:** A curated starter-kit repository of CLAUDE.md templates and accompanying reference documentation for Claude Code users.

**Maturity signals:**
- Stars: 203 (as of 2026-05-12)
- Forks: 24
- Contributors: 1 (solo author — Abhishek Ray, "Claude Code Camp" newsletter)
- Open issues: 0
- Created: 2026-02-04; last pushed: 2026-04-09; last updated (metadata): 2026-05-12
- License: None specified
- Subscribers: 3

**What it gives a user:** A zero-setup, copy-paste entry point into structured Claude Code configuration. The repo ships one global CLAUDE.md template, three project-level templates (generic, Next.js/TypeScript, Python/FastAPI), a local-override template, three path-scoped rule templates (testing, code-style, api-design), two workflow add-ons (self-improvement rules, prompting patterns), a one-page cheatsheet, and a comprehensive 36 KB `principles.md` reference. The entire kit can be dropped into any project in under 10 minutes. The underlying thesis: most Claude Code users leave performance on the table because CLAUDE.md files are either empty, too long, or badly structured — and this kit fixes that with minimal friction.

---

## 2. Relationship to Karpathy's critique

Karpathy's public positions on LLM coding agents span two phases: "vibe coding" (Feb 2025 — democratization, giving in to vibes, accepting AI output without reading it) and his later "agentic engineering" framing (Sequoia Ascent 2026 — discipline, oversight, orchestration as the professional successor).

Key Karpathy positions relevant to this repo (source credibility noted per item):

**Direct Karpathy quotes (sourced from Sequoia 2026 talk / attributed primary coverage):**
- "Agentic because the new default is that you are not writing the code directly 99% of the time, you are orchestrating agents who do and acting as oversight. Engineering because there is an art and science and expertise to it." [Direct — Morph/Sequoia summary]
- "vibe coding raises the floor for beginners; agentic engineering raises the ceiling for professionals" [Direct — MindStudio Karpathy framework article, sourced from Sequoia talk]
- "You're still responsible for your software just as before." [Direct — MindStudio]
- Agents are "spiky entities, a bit fallible, a little bit stochastic, but extremely powerful" [Direct]
- Code from vibe coding is "not super amazing code necessarily all the time — very bloaty, a lot of copy-paste, awkward abstractions that are brittle" [Direct]

**Karpathy positions attributed by credible secondary coverage (not direct quotes):**
- Models make "silent assumptions," proceed without clarifying ambiguity, overcomplicate solutions — requiring verification loops [Visual Studio Magazine / CompleteRPA, paraphrased]
- Agents must be kept on a "tight leash" with specific prompts and diff review; described AI as a "new over-eager junior intern savant with encyclopedic knowledge of software, but who also bull* you all the time, has an over-abundance of courage and shows little to no taste for good code" [Visual Studio Magazine, attributed — the "over-eager junior intern" phrase is widely reported but not available as a primary-source direct quote in materials I could access]
- The context window is "the main lever" in Software 3.0; you program LLMs through prompts, context, tools, examples, memory, and instructions [MindStudio, attributed from Sequoia talk]

**How this repo responds to Karpathy's critique (implicit, not explicit — the repo does not cite Karpathy):**

| Karpathy point | Repo response |
|---|---|
| Agents need tight leash / specific prompts | `prompting-patterns.md` — 11 concrete prompt templates for planning, verification, re-planning when stuck |
| Context window is the lever | `principles.md` §Attention Budget — explicit token economy; every rule carries multiplied cost; 3-5 rule files max |
| Models proceed without clarifying ambiguity | Matt Pocock's "unresolved questions" prompt pattern; Plan Mode rules that surface unknowns before coding |
| Verification before shipping | Dedicated `## Verification` section in every project template; "verify before done" in self-improvement rules |
| You're responsible for spec and design | Self-improvement workflow: plan first, check in with user before implementation |
| Agents produce bloaty/brittle code on vibes | Anti-pattern section explicitly bans personality instructions; enforces lean files under 60-80 lines |

The repo is a **community-level operationalization** of the tight-leash / context-discipline half of Karpathy's critique. It does not engage the deeper "agentic engineering as professional paradigm" framing — it stays squarely in the "configure Claude better" space.

---

## 3. Core competencies / dimensions

### D1. Three-level CLAUDE.md hierarchy with clear placement rules

The repo establishes a canonical three-tier configuration model: global (`~/.claude/CLAUDE.md`, ~15 lines, personal preferences), project (`.claude/CLAUDE.md`, 40-60 lines, team context), and local (`CLAUDE.local.md`, ~10 lines, gitignored personal overrides). Explicit placement guidance: a decision table tells users exactly which rule goes where and why.

**Snippet (from cheatsheet.md):**
```
~/.claude/CLAUDE.md     Global     Your preferences          Every project    ~15 lines
.claude/CLAUDE.md       Project    Team context + rules      Committed        40-60 lines
./CLAUDE.local.md       Local      Your personal overrides   Gitignored       ~10 lines
```

### D2. Token economy / attention budget discipline

Quantified, empirical framing of instruction cost: frontier models follow ~150-200 total instructions before adherence drops uniformly. Claude Code's system prompt already consumes ~50 slots. Rule files re-inject on every tool call — 11 rule files consumed 93K tokens (46% of a 200K context window) in one documented session. Every line competes for limited attention budget. Recommendation: 3-5 rule files max, each under 30 lines, root CLAUDE.md under 60 lines.

**Snippet (from principles.md):**
```
| Component | Tokens | % of 200K |
|-----------|--------|----------|
| Initial load (system prompt + CLAUDE.md + rules) | ~43K | 21% |
| Rule re-injections (~30 tool calls) | ~93K | 46% |
| Actual conversation content | ~50K | 25% |
```

### D3. Progressive disclosure pattern

CLAUDE.md is an index, not a library. Task-specific docs live in `docs/`; CLAUDE.md tells Claude *when* to read them. `@import` syntax loads files every session (for files always needed); the "pitch" pattern (mention file only when relevant) keeps costly docs out of context except when needed.

**Snippet (from principles.md):**
```markdown
## References
- For auth flows or StripeErrors: see docs/stripe-guide.md
- For database migrations: see docs/migration-guide.md
- For deployment: see docs/deploy.md
```
"CLAUDE.md is the index. The docs/ folder is the library. Claude pulls books off the shelf when needed."

### D4. Self-improvement loop

The highest-impact habit documented: after every correction, say "Update CLAUDE.md so you don't make that mistake again." This transforms CLAUDE.md from static config into a living document accumulating institutional knowledge. The repo attributes this to Boris Cherny (Claude Code team).

**Snippet (from workflows/self-improvement-rules.md):**
```
1. Claude makes a mistake
2. You correct it
3. You say: "Update CLAUDE.md so you don't make that mistake again"
4. Claude writes a rule for itself
5. You review and edit the rule
6. Repeat
```

### D5. Verification loop as quality multiplier

Give Claude a way to verify its own work — described as the "single highest-leverage action," citing Boris Cherny: "If Claude has that feedback loop, it will 2-3x the quality." Every project template ships a `## Verification` section with ordered commands (typecheck → test → lint → build).

**Snippet (from project/generic.md):**
```markdown
## Verification
After every change, run in this order:
1. [Type check command] — fix type errors
2. [Test command] — fix failing tests
3. [Lint command] — fix lint errors
```

### D6. Modular rules with path-scoping

`.claude/rules/` files split instructions by topic; path-scoped rules (YAML `paths:` frontmatter) activate only when Claude reads matching files, limiting unnecessary re-injection. Distinction between `paths:` (conditional) vs `globs:` (unconditional) is explicitly documented.

**Snippet (from rules/testing.md):**
```yaml
---
description: Testing standards for test files
paths:
  - "tests/**"
  - "**/*.test.*"
  - "**/*.spec.*"
---
```

### D7. Structured project template skeleton

Every project CLAUDE.md follows a fixed 7-section order: Project, Stack, Structure, Commands, Verification, Conventions, Don't. This opinionated section ordering provides a cognitive scaffold — a user picking up any CLAUDE.md built with this kit knows exactly where to find commands or anti-patterns.

**Snippet (from cheatsheet.md):**
```markdown
## Project        <- Name + one sentence
## Stack          <- Language, framework, DB, deploy target
## Structure      <- Key directories only (5-7 lines)
## Commands       <- Copy-paste: dev, build, test, lint
## Verification   <- Steps to run before committing
## Conventions    <- 3-5 team rules
## Don't          <- Anti-patterns + what to do instead
```

### D8. "Don't X, Do Y" prohibition pattern

Every negative constraint must include the positive alternative. "NEVER use `any`" is insufficient; "NEVER use `any` — use `unknown` and narrow the type with type guards" is actionable. This doubles as a rule-writing discipline for users authoring their own rules.

**Snippet (from principles.md):**
> "Bad: 'Don't use `any` in TypeScript' / Good: 'Don't use `any`—use `unknown` and narrow the type'"

### D9. Hooks as enforcement layer, rules as advisory layer

Explicit separation: CLAUDE.md is advisory (probabilistic, model may ignore). Hooks are deterministic (guaranteed lifecycle execution). Non-negotiable rules (auto-formatting, blocking writes to protected files, running linters) must be hooks, not CLAUDE.md lines.

**Snippet (from principles.md troubleshooting):**
> "If a rule must follow 100% of the time with zero exceptions, CLAUDE.md is wrong. CLAUDE.md is advisory. Hooks are deterministic."

### D10. Plan-before-act discipline with prompting patterns

Structured planning discipline codified into two artifacts: a `## Plan Mode` rule block (enter plan mode for any non-trivial task; surface unresolved questions before proceeding) and an 11-pattern prompt library covering planning, second-opinion review, re-planning when stuck, elegance demands, verification, and autonomous bug fixing.

**Snippet (from workflows/prompting-patterns.md):**
```
## 3. Surface unknowns before proceeding (Matt Pocock)
Make the plan extremely concise. At the end, give me a list of unresolved questions to answer before we start.
```

### D11. Auto-memory awareness and integration

Documents Claude Code's fourth (implicit) memory layer: `~/.claude/projects/<project>/memory/` where Claude auto-saves learnings. Users should not duplicate auto-memory content in CLAUDE.md. Provides a mental model distinguishing manual CLAUDE.md (shared, instructional) from auto-memory (personal, behavioral patterns, machine-local).

**Snippet (from principles.md):**
```
| Aspect | CLAUDE.md | .claude/rules/ | Auto Memory |
|--------|-----------|-----------------|------------|
| Writer | You | You | Claude |
| Content | Instructions, context | Scoped standards | Learnings, patterns |
| Loading | Once in messages[0] | Re-injected on tool results | First 200 lines at session start |
| Shared | Yes (project), No (local/global) | Yes | No — machine-local only |
```

### D12. Real-world benchmarks and anti-pattern catalog

Empirical anchor data from real projects (HumanLayer at 57 lines, Boris Cherny's team at ~83 lines, Cloudflare at 230 lines — too long) gives users calibration points. Anti-pattern catalog is explicit and comprehensive (12 named patterns with Why It Fails / What To Do Instead columns).

**Snippet (from principles.md benchmarks):**
```
| Source | Lines | Key Pattern |
|--------|-------|-------------|
| HumanLayer | 57 | ASCII diagrams, TODO priority, progressive disclosure |
| Boris Cherny's team | ~83 | Self-improvement, plan mode, verification loop |
| Cloudflare | 230 | Enterprise monorepo—too long for most projects |
```

### D13. Skill activation mapping (progressive disclosure signal)

From ChrisWiles: tell Claude which skill (document, guide, pattern) to load for which task type. Lightweight syntax in CLAUDE.md that costs almost nothing in context.

**Snippet (from principles.md):**
```markdown
## Skills
- Creating tests -> use `testing-patterns` skill
- Building forms -> use `formik-patterns` skill
- GraphQL operations -> use `graphql-schema` skill
```

### D14. Subagent strategy codified

Explicit subagent guidance: use subagents to keep main context window clean; one task per subagent; offload research, exploration, and parallel analysis. Treats subagent usage as a first-class technique, not an advanced feature.

**Snippet (from workflows/self-improvement-rules.md):**
```
### 2. Subagent Strategy
- Use subagents liberally to keep main context window clean
- Offload research, exploration, and parallel analysis to subagents
- For complex problems, throw more compute at it via subagents
- One task per subagent for focused execution
```

---

## 4. Ranking + criticality boundary

### CRITICAL (load-bearing — the kit fails without these)

1. **D2 — Token economy / attention budget** — The mechanism that makes everything else coherent. Without understanding that rules multiply with tool calls, a user builds a CLAUDE.md that silently degrades.
2. **D3 — Progressive disclosure** — The CLAUDE.md-as-index, docs-as-library mental model. Without it, files grow into kitchen sinks that violate D2.
3. **D1 — Three-level hierarchy with clear placement rules** — The structural foundation. Without placement clarity, users duplicate rules across levels, creating conflicts and wasted tokens.
4. **D6 — Modular rules with path-scoping** — The scaling mechanism. Without path-scoped rules, large codebases have no way to limit rule injection to relevant contexts.
5. **D5 — Verification loop** — The quality multiplier. Without it, Claude operates open-loop; the "2-3x quality" claim is empirically grounded by the source.

### SUPPORTING (valuable reinforcement, but not independently load-bearing at this kit's scope)

6. D4 — Self-improvement loop (high-value habit, but depends on D1-D3 being right first)
7. D7 — Structured project template skeleton (opinionated scaffold; accelerates adoption; depends on D1)
8. D8 — "Don't X, Do Y" prohibition pattern (rule-writing discipline; reinforces D6)
9. D9 — Hooks vs. advisory rules (conceptually important; docs only — no hooks shipped)
10. D10 — Plan-before-act / prompting patterns (practical workflow; no structural coupling)
11. D11 — Auto-memory awareness (advanced; most users don't need this until intermediate stage)
12. D12 — Real-world benchmarks (useful calibration; does not change behavior)
13. D13 — Skill activation mapping (progressive disclosure signal; lightweight)
14. D14 — Subagent strategy (mentioned; not elaborated at Praxion's depth)

**Boundary justification:** D1-D5 are critical because they address the root failure mode this kit solves — CLAUDE.md files that grow unconstrained until adherence silently degrades. A CLAUDE.md without these five properties is structurally broken even if all supporting dimensions are beautifully executed. D6-D14 make the kit better but do not fix the root failure mode.

---

## 5. Scope vs Praxion

### D2 — Token economy / attention budget

**(a) Does Praxion have it?** Yes. `rules/CLAUDE.md` documents a 25,000-token always-loaded budget cap with `wc -c` measurement guidance. The "every always-loaded token must earn its attention share (>30% of sessions)" principle is explicitly articulated. `principles.md` independently documents the 150-200 instruction limit and rule re-injection multiplication.

**(b) Sharper here?** The external repo provides more concrete empirical anchors: the exact token breakdown table (43K initial / 93K re-injections / 50K conversation in one session), the "3-5 rule files max" and "under 30 lines each" hard targets, and the 150-200 instruction frontier with HumanLayer's research citation. Praxion's budget is a cap with a principle; this kit is a budget with empirical calibration data.

**(c) Not applicable?** The re-injection cost math applies equally to Praxion. The numbers are directly relevant.

### D3 — Progressive disclosure

**(a) Does Praxion have it?** Yes, as a core load-bearing pattern. Praxion's skill system (metadata at startup / SKILL.md body on activation / references/*.md on demand) is a three-tier progressive disclosure architecture. `CLAUDE.md` is documented as a navigation index explicitly.

**(b) Sharper here?** The external repo articulates the CLAUDE.md-as-index / docs-as-library mental model with a clean, quotable two-sentence formulation: "CLAUDE.md is the index. The docs/ folder is the library." Praxion has this behavior but not this pithy framing in its own CLAUDE.md.

**(c) Not applicable?** Fully applicable.

### D1 — Three-level hierarchy

**(a) Does Praxion have it?** Yes, with more layers: `~/.claude/CLAUDE.md` (user-level), project `CLAUDE.md` (committed), path-scoped rules. Praxion extends this with skills and agents as additional progressive tiers.

**(b) Sharper here?** The local override (`CLAUDE.local.md`) and the explicit `claudeMdExcludes` mechanism for monorepo ancestor rule suppression are explicitly documented with user guidance. Praxion's `CLAUDE.md` does not document local override usage.

**(c) Not applicable?** Fully applicable.

### D6 — Modular rules with path-scoping

**(a) Does Praxion have it?** Yes. Praxion's `rules/` directory uses YAML `paths:` frontmatter. The `rules/CLAUDE.md` documents the same conditional loading mechanism.

**(b) Sharper here?** The external repo calls out a critical gotcha Praxion does not document: path-scoped rules trigger on **Read tool only** — not Write or Edit. If Claude edits a file without reading it first, path-scoped rules won't load. This is an undocumented failure mode in Praxion's rules system.

**(c) Not applicable?** Directly applicable and actionable.

### D5 — Verification loop

**(a) Does Praxion have it?** Yes. Praxion's `CLAUDE.md` has a `## How to verify your work` section (`pytest`, `sync_canonical_blocks.py --check`, `/sentinel`). The behavioral contract's "Verify" phase is structural.

**(b) Sharper here?** The external repo ships a concrete copy-paste `## Verification` section for every project template and frames it as the "single highest-leverage action" with the 2-3x quality claim. Praxion's verification is pipeline-level (verifier agent); this kit's is CLAUDE.md-level (self-directed verification commands in context). The two operate at different scopes.

**(c) Not applicable?** Complementary, not redundant.

---

## 6. Concrete artifacts worth copying

### Artifact A — Token re-injection budget table

Directly liftable as a principles reference in Praxion's `rules/CLAUDE.md` or `skills/rule-crafting`:

```markdown
| Component | Tokens | % of 200K |
|-----------|--------|----------|
| Initial load (system prompt + CLAUDE.md + rules) | ~43K | 21% |
| Rule re-injections (~30 tool calls) | ~93K | 46% |
| Actual conversation content | ~50K | 25% |

Takeaway: Every rule file addition carries multiplied cost.
One 500-token rule file costs 500 × (number of session tool calls), not just 500 tokens.
Keep rule count low (3-5 files max) and each file focused.
```

### Artifact B — Rule placement decision table (cheatsheet)

```markdown
| Rule | Location | Reasoning |
|------|----------|-----------|
| Run tests after changes | Global | Desired across all projects |
| Use shadcn/ui components | Project | Team convention |
| Ghostty terminal preference | Local | Personal-only setup |
| Never use TypeScript `any` | Project | Team standard |
| Ask before committing | Global | Personal preference |
| Context7 MCP configuration | Local | Individual setup |
| Keep code simple | Global | Universal preference |
```

### Artifact C — Path-scoped rule Read-only gotcha

```
Path-scoped rules activate when Claude READS a file matching the glob pattern.
Critical: Write, Edit, and MultiEdit do NOT trigger path-scoped rules.
If Claude edits a file without reading it first, the rule won't load.
```
This should be documented in Praxion's `rules/CLAUDE.md` or `skills/rule-crafting`.

### Artifact D — "CLAUDE.md as index" framing

```
Mental model: "CLAUDE.md is the index. The docs/ folder is the library.
Claude pulls books off the shelf when needed."
```

### Artifact E — Structured project CLAUDE.md section order

```markdown
## Project        <- Name + one sentence
## Stack          <- Language, framework, DB, deploy target
## Structure      <- Key directories only (5-7 lines)
## Commands       <- Copy-paste: dev, build, test, lint
## Verification   <- Steps to run before committing
## Conventions    <- 3-5 team rules
## Don't          <- Anti-patterns + what to do instead
```

### Artifact F — Matt Pocock's unresolved-questions prompt pattern

```
Make the plan extremely concise. Sacrifice grammar for concision.
At the end of each plan, give me a list of unresolved questions to answer, if any.
```
Pairs well with Praxion's `implementation-planner` delegation pattern.

### Artifact G — Anti-pattern table structure

The `| Anti-pattern | Why it fails | What to do instead |` three-column format is a clean template for Praxion's own anti-pattern documentation in `skills/rule-crafting` or equivalent.

### Artifact H — Skill activation mapping syntax

```markdown
## Skills
- Creating tests -> use `testing-patterns` skill
- Building forms -> use `formik-patterns` skill
```
Lightweight version of Praxion's progressive disclosure; could be a seed pattern for onboarded projects' CLAUDE.md.

### Artifact I — "NEVER rule must pair with alternative" principle

> "NEVER use `any` in TypeScript — use `unknown` and narrow the type with type guards or assertions"

Useful formulation for Praxion's `rule-crafting` skill: every `NEVER` prohibition requires a positive replacement.

### Artifact J — CLAUDE.md vs rules vs hooks distinction checklist

```
CLAUDE.md: advisory (probabilistic), loaded once, cheap
.claude/rules/: advisory (probabilistic), re-injected on every tool call, multiplied cost
Hooks: deterministic, guaranteed lifecycle execution
```
If a rule must fire 100% of the time — it is a hook, not a CLAUDE.md line.

---

## 7. Sources consulted

All URLs fetched on 2026-05-12.

1. [abhishekray07/claude-md-templates (GitHub repo homepage)](https://github.com/abhishekray07/claude-md-templates) — overview, file tree, star/fork/issue counts
2. [GitHub API — repo metadata](https://api.github.com/repos/abhishekray07/claude-md-templates) — stars, forks, dates, license, description
3. [GitHub API — root contents](https://api.github.com/repos/abhishekray07/claude-md-templates/contents/) — directory structure
4. [GitHub API — project/ contents](https://api.github.com/repos/abhishekray07/claude-md-templates/contents/project) — template file listing
5. [GitHub API — global/ contents](https://api.github.com/repos/abhishekray07/claude-md-templates/contents/global) — global template file
6. [GitHub API — rules/ contents](https://api.github.com/repos/abhishekray07/claude-md-templates/contents/rules) — rule templates listing
7. [GitHub API — workflows/ contents](https://api.github.com/repos/abhishekray07/claude-md-templates/contents/workflows) — workflow templates listing
8. [GitHub API — local/ contents](https://api.github.com/repos/abhishekray07/claude-md-templates/contents/local) — local template listing
9. [raw: README.md](https://raw.githubusercontent.com/abhishekray07/claude-md-templates/main/README.md) — full README content
10. [raw: principles.md](https://raw.githubusercontent.com/abhishekray07/claude-md-templates/main/principles.md) — comprehensive 36KB principles reference
11. [raw: cheatsheet.md](https://raw.githubusercontent.com/abhishekray07/claude-md-templates/main/cheatsheet.md) — one-page reference
12. [raw: project/generic.md](https://raw.githubusercontent.com/abhishekray07/claude-md-templates/main/project/generic.md) — generic project template
13. [raw: project/python-fastapi.md](https://raw.githubusercontent.com/abhishekray07/claude-md-templates/main/project/python-fastapi.md) — Python/FastAPI template
14. [raw: project/nextjs-typescript.md](https://raw.githubusercontent.com/abhishekray07/claude-md-templates/main/project/nextjs-typescript.md) — Next.js/TS template
15. [raw: global/CLAUDE.md](https://raw.githubusercontent.com/abhishekray07/claude-md-templates/main/global/CLAUDE.md) — global preferences template
16. [raw: local/local.md](https://raw.githubusercontent.com/abhishekray07/claude-md-templates/main/local/local.md) — local overrides template
17. [raw: rules/testing.md](https://raw.githubusercontent.com/abhishekray07/claude-md-templates/main/rules/testing.md) — testing rule template with path-scoping
18. [raw: rules/code-style.md](https://raw.githubusercontent.com/abhishekray07/claude-md-templates/main/rules/code-style.md) — code style rule template
19. [raw: rules/api-design.md](https://raw.githubusercontent.com/abhishekray07/claude-md-templates/main/rules/api-design.md) — API design rule template
20. [raw: workflows/self-improvement-rules.md](https://raw.githubusercontent.com/abhishekray07/claude-md-templates/main/workflows/self-improvement-rules.md) — self-improvement workflow
21. [raw: workflows/prompting-patterns.md](https://raw.githubusercontent.com/abhishekray07/claude-md-templates/main/workflows/prompting-patterns.md) — 11 prompting patterns
22. [Visual Studio Magazine — "Vibe Coding Pioneer Advises 'Tight Leash'"](https://visualstudiomagazine.com/articles/2025/04/25/vibe-coding-pioneer-advises-tight-leash-to-rein-in-ai-bs.aspx) — Karpathy tight-leash attribution (403; content sourced via search summary)
23. [MindStudio — "Vibe Coding vs Agentic Engineering: Karpathy Framework"](https://www.mindstudio.ai/blog/vibe-coding-vs-agentic-engineering-karpathy-framework) — direct Karpathy quotes, framework extraction
24. [Complete RPA Bootcamp — "Karpathy: from vibe coding to agentic engineering"](https://completerpabootcamp.com/blogs/andrej-karpathy-from-vibe-coding-to-agentic-engineering) — agentic engineering positions, oversight necessity
25. [Morph LLM — "Agentic Engineering: The Post-Vibe-Coding Paradigm"](https://www.morphllm.com/agentic-engineering) — direct Karpathy quote on agentic engineering definition
26. [karpathy.bearblog.dev — "2025 LLM Year in Review"](https://karpathy.bearblog.dev/year-in-review-2025/) — vibe coding origin, democratization direct quotes
27. [ToDatBeyond Substack — "Turning Karpathy's LLM Coding Thoughts into Claude.md"](https://todatabeyond.substack.com/p/turning-andrej-karpathys-llm-coding) — community interpretation of Karpathy's workflow shift
28. [MindStudio — "Software 3.0 Explained: Karpathy Context Window as RAM"](https://www.mindstudio.ai/blog/software-3-0-explained-karpathy-context-window-ram-model-weights-cpu) — context window lever attribution
