# Audit Methodology

How the `roadmap-cartographer` agent (via the `roadmap-synthesis` skill) conducts a project audit, from lens selection through fragment reconciliation.

> Back to the skill: [../SKILL.md](../SKILL.md). Companion references: [`lens-framework.md`](lens-framework.md), [`paradigm-detection.md`](paradigm-detection.md), [`grounding-protocol.md`](grounding-protocol.md).

---

## Parallel Deep-Dives Pattern

Praxion's exemplar `ROADMAP.md` was produced via six parallel deep-dive audits, each examining the project through a distinct lens. That pattern is the direct reason the exemplar achieves its depth: a single-agent sweep cannot produce equivalent breadth within one context window without saturating attention.

The cartographer reproduces this pattern for **any** project by spawning N researcher agents in parallel via the `Task` tool, where **N = the size of the derived lens set** (typically 4-6; hard-capped at 6). Each researcher operates with one narrow lens, writes a fragment to `.ai-work/<task-slug>/AUDIT_<lens>.md`, and returns. The cartographer then synthesizes all fragments in its Phase 4.

The underlying principle is universal: parallel researchers with distinct lenses produce structurally diverse findings that a single synthesizer can compose; sequential single-agent analysis tends to converge on the first angle it considers. This is the Curiosity lens applied to the audit itself.

The cartographer uses parallel researchers rather than a new dedicated auditor agent because researchers already own the evidence-gathering shape and scale cleanly to N lenses. Lens sets are derived per project — project values + domain constraints + best-fit exemplar — rather than a single hardcoded universal list, because universal-list audits mis-fit projects outside the list's target class.

---

## Lens Selection Rubric

Lens selection is governed by the 4-step derivation methodology in [`lens-framework.md`](lens-framework.md): inventory the project's values, inventory domain constraints, compose the set, user-gate the proposal. The audit-methodology role is downstream of selection — once the set is fixed, this file governs how the audit runs.

### Exemplar lens sets (common starting points)

The cartographer begins with an exemplar that fits the detected project class, then adapts:

| Exemplar | Project class | Lens count |
|---|---|---|
| **SPIRIT** (Automation · Coordinator Awareness · Quality · Evolution · Pragmatism · Curiosity & Imagination) | Multi-agent dev tools, LLM-app frameworks | 6 |
| **DORA** (Deploy Frequency · Lead Time · Change Fail Rate · MTTR) | Continuous-delivery products | 4 |
| **SPACE** (pick 3+ of Satisfaction · Performance · Activity · Communication · Efficiency) | Developer productivity / internal platforms | 3–5 |
| **FAIR** (Findable · Accessible · Interoperable · Reusable) | Research code, data repositories | 4 |
| **CNCF Platform Maturity** (Investment · Adoption · Interfaces · Operations · Measurement) | Infrastructure platforms, IDPs | 5 |
| **Custom / Derived** | Anything else | 4–8 |

Full definitions, when-to-use guidance, and the SPIRIT worked example: [`lens-framework.md`](lens-framework.md).

### Paradigm-tuning rules

Paradigm (deterministic / agentic / hybrid — see [`paradigm-detection.md`](paradigm-detection.md)) shapes **which sub-questions** fire within a chosen lens, and **which exemplar** is most likely a fit:

| Paradigm | Exemplar likely to fit | Sub-question style | Typical emphasis |
|----------|------------------------|---------------------|-------------------|
| **Deterministic** | SPACE · DORA · FAIR · Custom | Deterministic sub-questions (test coverage, API stability, latency budgets) | Structure + Quality + Docs |
| **Agentic** | SPIRIT · Custom | Agentic sub-questions (hallucination rate, coordinator awareness, prompt hygiene) | Coordinator Awareness + Evolution + Curiosity |
| **Hybrid** | SPIRIT, Custom, or exemplar-blend | Apply both sub-question sets; tag findings by paradigm layer | Full lens set; bias toward the dominant paradigm signals |

### Project-specific lens additions

When composing a Custom lens set or augmenting an exemplar, consider:

- A dominant domain concern the exemplar underweights (e.g., **Security**, **Performance**, **Accessibility**, **Cost**)
- The project's maturity stage (e.g., **Deprecation Hygiene** for mature projects, **Bootstrapping** for greenfield)
- External evidence pointing at a weakness category (e.g., **Observability** when logging/tracing is known to be thin)

Every added lens must declare its schema (name, definition, sub-questions, evidence types, failure signals) per the [lens-framework.md lens schema](lens-framework.md#lens-schema). Mirror the structure in [`audit-fragment-template.md`](../assets/audit-fragment-template.md).

### Lens count discipline

- **Floor: 4** — below this, synthesis lacks cross-lens tension and the roadmap skews to first-lens perspective
- **Ceiling: 8** — above this, per-lens findings thin out; researchers can't go deep
- **Typical: 4-6** — matches the exemplar sets and researcher-concurrency budget

Praxion's parallel-agent guidance caps concurrent subagents at 3. For lens sets of 4-6, fan out in **waves of ≤3** — first wave kicked off, cartographer waits for completion, second wave launched. The fragment reconciliation is insensitive to wave ordering.

---

## Researcher Fragment Schema

Each researcher writes a fragment following the schema in [`audit-fragment-template.md`](../assets/audit-fragment-template.md):

- **Lens** name and **paradigm applicability**
- **Scope** — what this lens examines
- **Findings** — numbered, each with Evidence
- **Evidence** — full citation list
- **Cross-lens Tensions** — conflicts/overlaps with other lenses the cartographer should reconcile
- **Memory Candidates for Main Coordinator** — structured entries (subagents can't call `remember()` directly)

Researchers are spawned with prompts that include the template path and the cartographer's task slug. Each researcher's prompt must name its specific lens; the researcher does not choose its lens.

---

## Fragment Reconciliation Protocol

After all fragments land, the cartographer's Phase 4 synthesizes them into draft roadmap sections:

1. **Collect** — read all `.ai-work/<task-slug>/AUDIT_*.md` files written by the wave(s).
2. **Map findings to roadmap sections** — per finding, decide whether it is:
   - a strength (→ section 2 "What's Working")
   - a weakness (→ section 3 "Weaknesses" as W_n with Evidence carried forward) — current deficit
   - an **opportunity** (→ section 4 "Opportunities (Forward Lines)" as O_n) — non-deficit forward line of work driven by evolution trend, user signal, adjacent-project traction, or strategic bet
   - an improvement (→ section 5 "Improvement Roadmap" item, with Motivation citing either a Weakness Wn, an Opportunity On, an Evolution trend, a Strategic bet, a User request, or a Prior item)
   - a deprecation (→ section 6 "Deprecation & Cleanup")
3. **Resolve cross-lens tensions** — when two lenses disagree on the same observation, the cartographer surfaces both views as a "Considered Angles" note under the affected weakness or improvement item. Do not silently pick one side.
4. **Deduplicate** — findings may surface in multiple lenses (e.g., "no CI test workflow" appears in Quality and Automation). Merge into one weakness, cite both lenses as evidence sources.
5. **Verify coverage** — every lens in the derived lens set should be touched by at least one weakness or improvement item. Sparse lenses trigger a "Considered Angles" revisit in the synthesis.
6. **Carry-forward memory candidates** — aggregate structured entries from every fragment's "Memory Candidates" section; the cartographer returns them to the main coordinator for `remember()`.

Conflict surfacing rule: **if a cross-lens tension cannot be resolved from evidence, surface it — do not hide it.** Hidden tensions compound; surfaced tensions get user input.

---

## Evidence Citation Format

Every quantitative claim in any fragment (and in the final roadmap) must cite a reachable source. Accepted forms:

- **File reference**: `` `path/to/file.py:42` `` or a line range `` `path/to/file.py:42-55` ``
- **Command output**: `` `$ pytest --collect-only | head -5` → ``[excerpt]`` `` — include the command so the reader can re-run
- **External source**: `https://example.com/ref (fetched YYYY-MM-DD)` — fetch date is required for drift
- **ADR reference**: `` `dec-NNN` `` — short form; full path optional
- **Metric**: must include measurement methodology ("line coverage" vs "behavioral coverage")

Anti-patterns (flagged by the grounding protocol):

- Round numbers without source ("~50% improvement")
- Vague quantifiers ("many users report")
- "Industry standard" claims without citation
- Imported assumptions from memory without re-verification

Full grounding rules: [`grounding-protocol.md`](grounding-protocol.md).

---

## Parallel Fan-Out Invocation

The cartographer fans out researchers using the `Task` tool. Concrete pattern:

1. Construct N researcher prompts — one per lens — including:
   - Task slug (inherited from cartographer)
   - Lens name and scope
   - Fragment file path (`.ai-work/<task-slug>/AUDIT_<lens>.md`)
   - Pointer to [`audit-fragment-template.md`](../assets/audit-fragment-template.md)
   - Pointer to [`lens-framework.md`](lens-framework.md) for lens schema and (if the lens is SPIRIT-drawn) the [SPIRIT Appendix](lens-framework.md#spirit-appendix-six-dimensions-in-detail) for worked sub-questions
   - Any project-specific instructions (scope carveouts, skip lists)
2. Invoke `Task` tool N times in a single message when N ≤ 3 (single-wave fan-out).
3. When N > 3, fan out in waves of ≤3. Wait for wave completion before launching the next.
4. After all fragments land, begin Phase 4 synthesis.

Wave count and concurrency cap are documented in Praxion's coordination-protocol rule (the `Parallel Execution & Boundary Discipline` section). The cartographer does not exceed that cap.

---

## Tying it Back

The audit feeds the `ROADMAP_TEMPLATE.md` structure (see [`../assets/ROADMAP_TEMPLATE.md`](../assets/ROADMAP_TEMPLATE.md)):

- Fragment **Findings (deficit-framed)** → template **Section 3 (Weaknesses)** with W_n numbering
- Fragment **Findings (opportunity-framed — evolution trends, user signals, adjacent traction)** → template **Section 4 (Opportunities / Forward Lines)** with O_n numbering
- Cross-lens **strengths** → template **Section 2 (What's Working)**
- Fragment **Cross-lens Tensions** → template **Section 5 (Improvement Roadmap)** "Considered Angles" notes
- Fragment **Evidence** → grounding citations preserved verbatim in the final roadmap
- Fragment **Memory Candidates** → carried out-of-band to the main coordinator

The methodology footer (template section 9) records which lenses ran, how many researchers fanned out, and what evidence sources were consulted — making every roadmap auditable. A roadmap that surfaces Weaknesses without any Opportunities is structurally incomplete — the Evolution and Curiosity lenses (or their equivalents in non-SPIRIT lens sets) are expected to produce forward-looking material, and the cartographer must seek it out rather than stopping at deficit repair.
