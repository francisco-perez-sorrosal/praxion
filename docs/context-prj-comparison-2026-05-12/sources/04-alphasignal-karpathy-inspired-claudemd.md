# Analysis: AlphaSignal — "Karpathy-Inspired CLAUDE.md"

## 1. What it is

**Type**: Newsletter article (Substack)
**Publisher**: AlphaSignal (alphasignalai.substack.com)
**Author**: Jim Clyde Monge
**Date**: April 22, 2026
**Paywall status**: Partially gated on Substack; the substantive content was accessible via WebFetch without login (title, four principles, installation methods, key limitations, external resources). No indication that significant advice was hidden behind a hard paywall — the article reads as a promotional/analysis piece for a public GitHub repo.
**Length**: Short-form newsletter piece, approximately 600-800 words (article body); structured around a single open-source artifact.

**Summary**: The article introduces and recommends the `forrestchang/andrej-karpathy-skills` GitHub repository — a 65-line `CLAUDE.md` file authored by Forrest Chang (Jiayuan Zhang) on January 27, 2026, one day after Karpathy's viral X post on LLM coding failures. The article explains the four behavioral principles in the file (Think Before Coding, Simplicity First, Surgical Changes, Goal-Driven Execution), describes three installation paths (curl download, Claude Code plugin, Cursor rules copy), gives an honest "Worth Watching / Not Production Ready" verdict, and flags the false-endorsement risk (Karpathy has not publicly endorsed the repo). Its concrete value proposition: add a 65-line file to any project and reduce Claude Code's worst coding behaviors in under 30 seconds.

---

## 2. Relationship to Karpathy's critique

**Faithfulness**: Good on the three failure modes; less precise on framing. The article accurately represents Karpathy's January 26, 2026 X post as the source material and correctly attributes the CLAUDE.md file to Forrest Chang, not Karpathy. It explicitly warns that "secondary coverage has misattributed the work to Karpathy himself."

**What it leans on**: The article relies primarily on Karpathy's three diagnostic claims (silent assumptions, overcomplication, collateral damage) and his single positive prescription ("give it success criteria and watch it go"). These are all [VERBATIM]-tier Karpathy from the January 2026 post (see `00-karpathy-critique.md`).

**Where it extrapolates**: The article does not invoke Karpathy's Software 3.0 thesis, the autonomy slider concept, the leash metaphor, or the autoresearch design principles. Its framing is narrower: Karpathy diagnosed problems → Chang encoded fixes → here is how to install them. The fourth principle (Goal-Driven Execution) is presented as Karpathy's "insight about LLM strengths," which is a [VERBATIM] position, but the specific structured format ("Step → verify: check") is Chang's operationalization.

**Gap**: The article does not distinguish between (a) what Karpathy described as a symptom and (b) what Chang prescribed as a fix. Readers may conclude that Karpathy recommended CLAUDE.md files specifically — he did not.

**Cross-reference to 00-karpathy-critique.md**: The article's four principles map cleanly to criteria #1 (assumption surfacing), #2 (complexity constraint), #3 (surgical scope), and #4 (verification criteria) in the implications checklist. It does not address criteria #5-12 (context economy, human oversight integration, instruction/code separation, scope bounding, loop speed, jagged intelligence awareness, anti-anthropomorphism, vibe-vs-production calibration).

---

## 3. Core competencies / dimensions

The article advocates for the following distinct dimensions, drawn from the CLAUDE.md file and its framing:

**Dimension 1: Explicit assumption surfacing before implementation**
The agent must state all assumptions, present multiple interpretations when ambiguous, and stop to ask rather than guess. The CLAUDE.md snippet: "Before implementing: State your assumptions explicitly. If uncertain, ask. If multiple interpretations exist, present them."

**Dimension 2: Minimum viable code (no speculative features)**
Deliver the smallest code that solves the stated problem. No features beyond what was asked, no abstractions for single-use code, no flexibility that wasn't requested. CLAUDE.md: "No features beyond what was asked. No abstractions for single-use code. If 200 lines could be 50, rewrite it."

**Dimension 3: Surgical scoping of edits**
Restrict edits to exactly what is necessary. Do not improve adjacent code, do not refactor unbroken things, match existing style. CLAUDE.md: "Don't 'improve' adjacent code or formatting. Don't refactor things that aren't broken. If you notice dead code, mention it — don't delete it."

**Dimension 4: Goal-driven / criteria-first execution**
Transform every task into a verifiable success criterion before beginning. CLAUDE.md: "Transform tasks into verifiable goals: 'Add validation' → 'Write tests, then make them pass'." For multi-step tasks, produce a brief plan with specific verification checkpoints.

**Dimension 5: Behavioral guidance as a project artifact**
The insight that a plain-text markdown file in the project root is a viable mechanism for shaping agent behavior — version-controlled, shareable, and loaded automatically by Claude Code. The article frames this as a lightweight alternative to complex agent configuration.

**Dimension 6: Cross-tool portability**
The same behavioral principles can be expressed as a Cursor `.mdc` rules file, a Claude Code plugin, or a per-project download. The article presents all three installation paths, implying the principles transcend any single tool.

**Dimension 7: Explicit caution / friction tradeoff**
The article honestly notes: "These guidelines bias toward caution over speed. For trivial tasks, use judgment." It treats the file as a calibration tool, not a universal override.

---

## 4. Ranking + criticality boundary

Ranked most to least important based on direct impact on LLM coding quality:

1. **Explicit assumption surfacing** — Eliminates the highest-cost failure mode (silent wrong assumptions → rework)
2. **Surgical scoping** — Prevents collateral damage, the failure mode with highest blast radius on existing codebases
3. **Goal-driven / criteria-first execution** — Exploits the LLM's strongest modality (looping toward specific goals)
4. **Minimum viable code** — Addresses overengineering but has more natural self-correction (humans notice bloat)
5. **Behavioral guidance as a project artifact** — Meta-dimension enabling all others; the "how" not the "what"
6. **Cross-tool portability** — Operational convenience; valuable but derivative
7. **Explicit caution / friction tradeoff** — Honest caveat; prevents over-application of the file

---
**ABOVE = CRITICAL** (1–4): These directly address Karpathy's three failure modes plus his single positive prescription. They map 1:1 to behaviors that reduce rework and collateral damage in real codebases.

**BELOW = SUPPORTING** (5–7): These are meta-dimensions about how to deliver and calibrate the critical ones.

**Justification**: Dimensions 1–4 are derived from Karpathy's verbatim claims about LLM coding failures. Dimensions 5–7 are about packaging, portability, and application judgment — valuable but secondary to the core behavioral contract.

---

## 5. Scope vs Praxion

### Dimension 1: Explicit assumption surfacing

**(a) Does Praxion have it?** Yes — and more formally. The Behavioral Contract (always-loaded rule `rules/swe/agent-behavioral-contract.md`) mandates "Surface Assumptions — list assumptions before acting; ask when ambiguity could produce the wrong artifact." This is the first of four non-negotiable behaviors.

**(b) Sharper here?** Praxion is sharper in two ways: (1) it applies the constraint to all agents in the pipeline, not just the code-generating agent; (2) it is formalized as a named contract violation with a verification tag, not just a soft guideline. The CLAUDE.md version has no enforcement mechanism; Praxion's verifier checks for behavioral-contract violations.

**(c) Not applicable?** Not applicable — Praxion has this fully covered at higher rigor.

### Dimension 2: Surgical scoping

**(a) Does Praxion have it?** Yes — "Stay Surgical — touch only what the change requires; if scope grew, stop and re-scope instead of silently expanding" is the third Behavioral Contract clause.

**(b) Sharper here?** Comparable depth; Praxion adds the stop-and-re-scope escalation path that the CLAUDE.md file does not have.

**(c) Not applicable?** Not applicable — Praxion covers this.

### Dimension 3: Goal-driven / criteria-first execution

**(a) Does Praxion have it?** Partially. The Standard/Full tier pipeline requires acceptance criteria in the `IMPLEMENTATION_PLAN.md` and traceability in `traceability.yml`. The implementer operates against REQ-IDs with verifiable acceptance criteria. The verifier checks compliance against them.

**(b) Sharper here?** Praxion is sharper at the pipeline level (structured REQ-IDs, traceability matrix, dedicated verifier agent). The CLAUDE.md version targets per-task micro-scale ("write tests, then make them pass") — useful even at Direct/Lightweight tier where Praxion's full traceability is not warranted. **Gap**: Praxion's Direct and Lightweight tiers lack explicit verification-criteria formatting for small tasks. A simple "define success criteria before starting" nudge at the lowest tiers could add value.

**(c) Not applicable?** Not applicable at Standard/Full. Potentially underserved at Direct/Lightweight.

### Dimension 4: Minimum viable code

**(a) Does Praxion have it?** Yes — "Simplicity First — prefer the smallest solution that meets the behavior; every added line, file, or dependency must earn its place" is the fourth Behavioral Contract clause.

**(b) Sharper here?** Comparable. Praxion's "simplicity first" is as strong; the CLAUDE.md's "would a senior engineer say this is overcomplicated?" test is a useful concrete heuristic that Praxion's formulation does not include verbatim.

**(c) Not applicable?** Not applicable — Praxion covers this.

---

## 6. Concrete artifacts worth copying

**The verbatim CLAUDE.md content** (65 lines; see below). This is the single most copy-worthy artifact — not for Praxion's always-loaded rules (where Praxion already has equivalent coverage via the behavioral contract), but as a model for what a minimal, high-signal, behaviorally-focused config file looks like. The CRITICAL value is in what it omits: no boilerplate, no extensive context, no procedural instructions — purely behavioral constraints.

```markdown
# CLAUDE.md

Behavioral guidelines to reduce common LLM coding
mistakes. Merge with project-specific instructions
as needed.

**Tradeoff:** These guidelines bias toward caution
over speed. For trivial tasks, use judgment.

## 1. Think Before Coding
**Don't assume. Don't hide confusion. Surface tradeoffs.**

Before implementing:
- State your assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them.
- If a simpler approach exists, say so.
- If something is unclear, stop. Name what's confusing.

## 2. Simplicity First
**Minimum code that solves the problem. Nothing speculative.**

- No features beyond what was asked.
- No abstractions for single-use code.
- No "flexibility" that wasn't requested.
- No error handling for impossible scenarios.
- If 200 lines could be 50, rewrite it.

## 3. Surgical Changes
**Touch only what you must. Clean up only your own mess.**

- Don't "improve" adjacent code or formatting.
- Don't refactor things that aren't broken.
- Match existing style, even if you'd do it differently.
- If you notice dead code, mention it — don't delete it.

## 4. Goal-Driven Execution
**Define success criteria. Loop until verified.**

Transform tasks into verifiable goals:
- "Add validation" → "Write tests, then make them pass"
- "Fix the bug" → "Reproduce it in a test, then fix"
- "Refactor X" → "Ensure tests pass before and after"
```

**The explicit caution/speed tradeoff header**: "These guidelines bias toward caution over speed. For trivial tasks, use judgment." This one-sentence meta-instruction is a model for how Praxion's behavioral contract could acknowledge its own cost. Currently, Praxion's contract has no such calibration notice — it applies universally without acknowledging that for Direct-tier tasks, some constraints add friction without proportional value.

**The "minimum code" heuristic**: "If 200 lines could be 50, rewrite it." This concrete numeric framing is more memorable than the abstract "simplicity first" principle. Could be incorporated into the behavioral contract's deep-dive skill reference.

**The dead-code handling nuance**: "If you notice dead code, mention it — don't delete it." This is a concrete disambiguation not present in Praxion's surgical scoping language. Praxion's "touch only what the change requires" does not distinguish between deleting dead code silently and reporting it — the CLAUDE.md version is more precise here.

---

## 7. Sources consulted

- [AlphaSignal article, Jim Clyde Monge, April 22, 2026](https://alphasignalai.substack.com/p/karpathy-inspired-claudemd-how-to) — primary source for this analysis; fetched 2026-05-12
- [forrestchang/andrej-karpathy-skills GitHub repo](https://github.com/forrestchang/andrej-karpathy-skills) — 127,000+ stars, repository README; fetched 2026-05-12
- [forrestchang/andrej-karpathy-skills CLAUDE.md file](https://github.com/forrestchang/andrej-karpathy-skills/blob/main/CLAUDE.md) — full verbatim content; fetched 2026-05-12
- [antigravity.codes — Karpathy Claude Code Skills Guide](https://antigravity.codes/blog/karpathy-claude-code-skills-guide) — full CLAUDE.md verbatim + attribution analysis; fetched 2026-05-12
- [miraflow.ai — Karpathy CLAUDE.md 100K Stars article](https://miraflow.ai/blog/karpathy-claude-md-100k-github-stars-ai-coding-2026) — attribution analysis; fetched 2026-05-12
- [Karpathy X post, January 26, 2026](https://x.com/karpathy/status/2015883857489522876) — primary source for the three failure modes; not directly fetched (X requires login) but content reconstructed from multiple high-fidelity secondary sources
- [treycausey.com commonplace entry](https://www.treycausey.com/commonplace/2026-01-26-x-com-karpathy-status-2015883857489522876/) — archive of Karpathy's X post content; fetched 2026-05-12
- [00-karpathy-critique.md](../00-karpathy-critique.md) — companion grounding document; all cross-references resolved there
