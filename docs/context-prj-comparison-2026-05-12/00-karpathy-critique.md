# Grounding: What Andrej Karpathy Actually Said About LLM Coding Agents (and what people inferred for CLAUDE.md)

## Purpose & how to read this

This document is the evidential lens for the context-project comparison series. Its job is to separate what Karpathy demonstrably said — with a source and a tier tag — from what the developer community synthesized, extrapolated, or branded as "Karpathy-inspired." Every claim in the comparison that invokes Karpathy's authority should be traceable back to a tier here. Community synthesis labeled as such is still valuable design input; it just should not be treated as Karpathy's prescription. The tier tags are: **[VERBATIM]** (direct quote from a primary Karpathy source), **[CLOSE PARAPHRASE]** (accurately represents the stated position, possibly condensed), **[REPORTED]** (attributed to Karpathy by a secondary source without a direct quote link).

---

## Karpathy's primary positions (sourced)

### Vibe coding and its limits

- **Coined "vibe coding"**: Programming where you communicate desired outcomes in natural language, forget that code exists, and let the model generate. Code becomes "free, ephemeral, malleable, discardable after single use." [VERBATIM] — Karpathy, 2025 LLM Year in Review blog post (karpathy.bearblog.dev, 2026-01-02 approx)

- **Vibe coding raises the floor, agentic engineering preserves the ceiling**: "Vibe coding raised the floor" (democratizes software access); "Agentic engineering is about preserving the quality bar of what existed before in professional software." [CLOSE PARAPHRASE with partial verbatim] — Karpathy, Sequoia AI Ascent 2026 fireside chat (multiple secondary sources cite this framing; the Sequoia blog and bearblog.dev summary confirm it, ~May 2026)

- **Vibe coding ≠ production readiness**: Vibe coding is appropriate for throwaway scripts and single-use apps; it does not substitute for engineering judgment in software that others depend on. [CLOSE PARAPHRASE] — Karpathy, Sequoia Ascent 2026; consistent across multiple talks

### The coding workflow inflection point (January 2026 X post)

- **Workflow inversion**: "I rapidly went from about 80% manual+autocomplete coding and 20% agents in November to 80% agent coding and 20% edits+touchups in December." [VERBATIM] — Karpathy, X post, January 26, 2026 (x.com/karpathy/status/2015883857489522876)

- **Magnitude of change**: "This is easily the biggest change to my basic coding workflow in ~2 decades of programming and it happened over the course of a few weeks." [VERBATIM] — same X post, January 26, 2026

- **Programming in English**: "I really am mostly programming in English now, a bit sheepishly telling the LLM what code to write… in words." [VERBATIM] — same X post, January 26, 2026; consistent with Software 3.0 thesis

### LLM coding failure modes (January 2026 X post — the direct source for the CLAUDE.md repo)

- **Silent wrong assumptions**: "The models make wrong assumptions on your behalf and just run along with them without checking. They don't manage their confusion, don't seek clarifications, don't surface inconsistencies, don't present tradeoffs, don't push back when they should." [VERBATIM] — Karpathy, X post January 26, 2026

- **Overcomplication / hypertrophy**: "They really like to overcomplicate code and APIs, bloat abstractions, don't clean up dead code... implement a bloated construction over 1000 lines when 100 would do." [VERBATIM] — Karpathy, X post January 26, 2026

- **Collateral / orthogonal damage**: "They still sometimes change/remove comments and code they don't sufficiently understand as side effects, even if orthogonal to the task." [VERBATIM] — Karpathy, X post January 26, 2026

- **Goal-driven execution (positive prescription)**: "LLMs are exceptionally good at looping until they meet specific goals... Don't tell it what to do, give it success criteria and watch it go." [VERBATIM] — Karpathy, X post January 26, 2026

- **Net positive despite issues**: "Despite all these issues, it is still a net huge improvement and it's very difficult to imagine going back to manual coding." [VERBATIM] — same X post, January 26, 2026

### Software 3.0 / English-as-programming / LLM-as-OS (YC AI Startup School, June 2025)

- **Software version framing**: Software 1.0 = explicit code; Software 2.0 = neural networks; Software 3.0 = LLMs programmed in English. [CLOSE PARAPHRASE] — Karpathy, YC AI Startup School keynote, "Software Is Changing (Again)", June 2025. Talk video and X announcement at x.com/karpathy/status/1935518272667217925

- **Context window as programming surface**: "Your programming now turns to prompting, and what's in the context window is your lever over the interpreter that is the LLM." [VERBATIM or very close paraphrase, widely reported] — Karpathy, YC AI Startup School, June 2025

- **LLM as OS**: LLMs have properties of utilities, fabs, and operating systems; the LLM is the compute layer, the context window acts like memory, and tools/files/APIs are things it coordinates. [CLOSE PARAPHRASE] — Karpathy, YC AI Startup School, June 2025

- **LLMs as "people spirits"**: LLMs are "stochastic simulations of people" trained on human data with emergent psychology — superhuman in some ways, fallible in many others; possess "jagged intelligence." [CLOSE PARAPHRASE with partial verbatim "people spirits"] — Karpathy, YC AI Startup School, June 2025

- **LLMs have anterograde amnesia**: LLMs function "a bit like a coworker with Anterograde amnesia — they don't consolidate or build long-running knowledge" beyond their context window. [VERBATIM or very close] — Karpathy, YC AI Startup School, June 2025 (reported by latent.space)

- **Demo vs product gap**: "Demo is works.any(), product is works.all()" — partial autonomy is essential during the transition. [VERBATIM] — Karpathy, YC AI Startup School, June 2025

- **Autonomy slider concept**: AI tools should expose an "autonomy slider" for users to modulate agent control (e.g., Cursor: Tab → Cmd+K → Cmd+L → Cmd+I agent mode; Tesla Autopilot L1-L4). [CLOSE PARAPHRASE] — Karpathy, YC AI Startup School, June 2025; drawn from his Tesla Autopilot experience

- **Fast verification loops**: Human-AI loops work best when "the faster the loop the better" with fast verification and tight constraints on generation. [VERBATIM or very close] — Karpathy, YC AI Startup School, June 2025 (reported by latent.space)

### "Keep AI on a leash" (YC AI Startup School, June 2025)

- **Leash metaphor**: Karpathy urged "keep AI on a leash" — developers should exercise caution before deploying unsupervised agents at scale; argued that LLMs remain fundamentally unreliable without human supervision due to hallucination, context loss, and absurd errors. [CLOSE PARAPHRASE with verbatim "keep AI on a leash"] — Karpathy, YC AI Startup School, June 2025 (reported by TechTimes, AI21 blog, multiple secondary sources; specific talk timestamp not publicly pinned)

- **Small incremental approach**: Karpathy advocated for "small incremental requests and precise prompts rather than loose, exploratory vibe coding" to mitigate risks; "I always go in small incremental chunks." [REPORTED — attributed to Karpathy in secondary coverage; exact source tweet/talk not independently verified] — cited across TechTimes, AI21 blog, June 2025

- **Human responsibility for judgment, taste, oversight**: "You still have to be in charge of aesthetics, judgment, taste, and oversight." [VERBATIM or very close] — Karpathy, Sequoia Ascent 2026; consistent across multiple talks

- **You can outsource thinking but not understanding**: "You can outsource your thinking, but you can't outsource your understanding." [VERBATIM] — Karpathy, Sequoia Ascent 2026

### AutoResearch project design (March 2026 — concrete workflow evidence)

- **Single-file constraint for reviewable diffs**: In autoresearch, "The agent only touches `train.py`. This keeps the scope manageable and diffs reviewable." [VERBATIM from README] — Karpathy, karpathy/autoresearch GitHub repo, README, March 2026

- **Codebase fits in context window**: The ~630-line constraint ensures the entire codebase fits within the LLM's context window, "minimizing errors in code generation and allowing the agent to maintain a 'holistic' understanding." [CLOSE PARAPHRASE of README] — same repo

- **Fixed time budget = comparable incremental experiments**: 5-minute fixed training budget per experiment makes results attributable to specific changes. [CLOSE PARAPHRASE] — same repo

- **program.md as human-editable instruction layer**: A separate `program.md` file serves as the human-editable instruction layer, separated from code; the human guides agent behavior through documented constraints without modifying the execution environment. [CLOSE PARAPHRASE] — same repo

- **Indefinite autonomous loop**: The agent's program.md instructs it to "never pause or ask permission — continues experimenting indefinitely until manually stopped." [CLOSE PARAPHRASE of program.md] — karpathy/autoresearch, program.md, March 2026

### What Karpathy did NOT say (important boundary)

- Karpathy has **not publicly endorsed** the forrestchang/andrej-karpathy-skills repository. The AlphaSignal article explicitly notes this.
- The specific four-principle structure (Think Before Coding / Simplicity First / Surgical Changes / Goal-Driven Execution) is Forrest Chang's synthesis, not Karpathy's organization.
- "Context rot" as a named failure mode: widely cited in community coverage but no primary Karpathy source found using this exact term. The concept is consistent with his anterograde amnesia framing and context-window-as-lever statements.
- Specific CLAUDE.md design advice (terse length, anti-pattern lists, self-updating instructions): community extrapolation, not Karpathy prescription.

---

## What the community inferred for CLAUDE.md / agent config (clearly labeled as extrapolation)

These are design moves the developer community derived from Karpathy's observations. They are legitimate engineering responses to his critique — but they are community synthesis, not Karpathy's own prescriptions.

**1. Terse CLAUDE.md files** — Inferred from: Karpathy's context-window-as-lever framing + anterograde amnesia metaphor. If context is your lever, every token must earn its place. The community concluded: keep CLAUDE.md short, scannable, and dense. Karpathy never prescribed a specific length.

**2. Anti-pattern checklists** — Forrest Chang's direct operationalization of the three failure modes. The CLAUDE.md format turns Karpathy's diagnostic ("models overcomplicate") into a behavioral constraint ("no features beyond what was asked"). This translation step is Chang's work, not Karpathy's.

**3. Explicit verification gates** — Inferred from: Karpathy's "give it success criteria and watch it go" + "the faster the [verification] loop the better" + autoresearch's keep/discard loop. Community conclusion: build explicit test-pass checkpoints into every task. Karpathy described this as an LLM strength to exploit, not as a format prescription.

**4. Scoped / just-in-time context** — Inferred from: Karpathy's context-window-as-lever framing + anterograde amnesia. Community conclusion: load only what the model needs for the current task; avoid polluting context with stale or irrelevant information ("context rot"). The term "context rot" itself is a community coinage derived from his framing.

**5. Self-updating instructions** — Inferred from: Karpathy's autoresearch `program.md` pattern (human edits the instruction layer) + Software 3.0 thesis (system prompt as configuration surface). Community extension: allow the agent to propose updates to its own CLAUDE.md. Karpathy demonstrated human-edited instruction files; full agent self-modification is community extrapolation.

**6. Separate instruction layer from code** — Inferred from: autoresearch's explicit separation of `program.md` from `train.py`. Community conclusion: a dedicated config/instruction file is better than embedding behavioral constraints in code comments.

**7. "Would a senior engineer call this overcomplicated?" test** — Forrest Chang's formulation for operationalizing Karpathy's "overcomplicate" failure mode. The heuristic is Chang's; Karpathy described the symptom.

**8. Autonomy-aware workflows (graduated agent modes)** — Inferred from: Karpathy's autonomy slider concept. Community conclusion: design workflows with explicit human checkpoints rather than letting agents run unconstrained. Karpathy's prescriptions were at the product-design level; applying them to per-project CLAUDE.md is community extrapolation.

---

## Implications checklist for evaluating CLAUDE.md / context systems

These are the dimensions that follow from Karpathy's grounded positions. Use them as evaluation criteria for any CLAUDE.md-style context artifact.

1. **Assumption surfacing**: Does the configuration explicitly require the agent to surface ambiguous assumptions before acting? (Karpathy: silent assumptions are failure mode #1)

2. **Complexity constraint**: Does it constrain speculative features, unnecessary abstractions, and over-engineering? (Karpathy: overcomplication is failure mode #2)

3. **Surgical scope**: Does it limit changes to only what was requested, preventing collateral edits? (Karpathy: orthogonal damage is failure mode #3)

4. **Verification criteria**: Does it require tasks to be expressed as testable success criteria before execution begins? (Karpathy: "give it success criteria and watch it go")

5. **Context economy**: Is the always-loaded content minimal and high-signal? Does it treat context as a scarce lever rather than a kitchen sink? (Karpathy: context window is the lever; anterograde amnesia means stale context harms performance)

6. **Human oversight integration**: Does it define explicit human checkpoints, inspection points, or approval gates — not just autonomous completion? (Karpathy: "keep AI on a leash"; autonomy slider; "you still have to be in charge of oversight")

7. **Instruction / code separation**: Is behavioral guidance stored separately from code, as a first-class editable artifact? (Karpathy: autoresearch `program.md` pattern)

8. **Scope bounding**: Does it constrain the agent to a bounded, reviewable surface area? (Karpathy: "diffs reviewable" principle from autoresearch)

9. **Loop speed and verification feedback**: Does it design for fast feedback loops that catch errors before they propagate? (Karpathy: "the faster the loop the better"; autoresearch 5-minute budget)

10. **Jagged intelligence awareness**: Does it account for the model's uneven capabilities — trusting it for verifiable tasks, requiring human judgment for ambiguous ones? (Karpathy: "jagged intelligence"; "you can't outsource your understanding")

11. **Anti-anthropomorphism**: Does it avoid designing workflows that assume the agent builds cross-session memory or understanding? (Karpathy: anterograde amnesia; LLM-as-OS-not-colleague)

12. **Distinguishes vibe coding from production quality**: Is there a calibration mechanism that matches process rigor to task risk? (Karpathy: vibe coding raises the floor; agentic engineering preserves the ceiling)

---

## Sources

- [Karpathy X post, January 26, 2026](https://x.com/karpathy/status/2015883857489522876) — primary source for the three coding failure modes and 80/20 workflow inversion quote; the direct basis for forrestchang/andrej-karpathy-skills
- [karpathy.bearblog.dev — 2025 LLM Year in Review](https://karpathy.bearblog.dev/year-in-review-2025/) — vibe coding definition, Claude Code as "first convincing LLM agent demo", LLM coding democratization; accessed 2026-05-12
- [karpathy/autoresearch — README and program.md](https://github.com/karpathy/autoresearch) — March 2026; single-file constraint, reviewable diffs, context-window sizing rationale, autonomous loop design, instruction/code separation
- [Karpathy YC AI Startup School keynote, June 2025](https://x.com/karpathy/status/1935518272667217925) — Software 3.0, people spirits, anterograde amnesia, autonomy slider, context window as lever; talk notes at latent.space/p/s3 and ikyle.me blog
- [Karpathy Sequoia AI Ascent 2026](https://karpathy.bearblog.dev/sequoia-ascent-2026/) — agentic engineering vs vibe coding, December 2025 inflection point, "you can outsource thinking but not understanding"; accessed 2026-05-12
- [Karpathy "keep AI on a leash" — TechTimes coverage](https://www.techtimes.com/articles/310925/20250620/openais-andrej-karpathy-warns-against-unleashing-unsupervised-agents-too-soon-keep-ai-leash.htm) — June 2025 YC talk; REPORTED source for "leash" quote and small-incremental-chunks claim
- [AI21 blog: Karpathy's Leash](https://www.ai21.com/blog/karpathys-leash/) — secondary synthesis of the leash concept; useful for community framing but the direct Karpathy quote is only the three-word "keep AI on the leash"
- [AlphaSignal article](https://alphasignalai.substack.com/p/karpathy-inspired-claudemd-how-to) — Jim Clyde Monge, April 22, 2026; companion article to the forrestchang repo; explicitly notes Karpathy has not publicly endorsed the repo
- [forrestchang/andrej-karpathy-skills](https://github.com/forrestchang/andrej-karpathy-skills) — 127,000+ stars; the community CLAUDE.md file derived from Karpathy's January 2026 X post; created January 27, 2026
- [antigravity.codes — Karpathy Claude Code Skills Guide](https://antigravity.codes/blog/karpathy-claude-code-skills-guide) — contains the full verbatim CLAUDE.md text and clean attribution table; accessed 2026-05-12
- [miraflow.ai article](https://miraflow.ai/blog/karpathy-claude-md-100k-github-stars-ai-coding-2026) — secondary coverage; accurate attribution of Forrest Chang as author vs Karpathy as source; accessed 2026-05-12
- [Karpathy X post on Sequoia talk](https://x.com/karpathy/status/2049903821095354523) — Karpathy's own summary of Sequoia Ascent 2026 highlights
- [latent.space — Karpathy Software 3.0 coverage](https://www.latent.space/p/s3) — detailed notes from YC AI Startup School talk; "anterograde amnesia" and "demo is works.any(), product is works.all()" quotes; accessed 2026-05-12
- [Karpathy X post, November 2025](https://x.com/karpathy/status/2004607146781278521) — "I've never felt this much behind as a programmer"; context for the December workflow shift
