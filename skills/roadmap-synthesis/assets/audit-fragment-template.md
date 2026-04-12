<!--
Per-lens audit fragment written by a researcher spawned by the cartographer.
File path: .ai-work/<task-slug>/AUDIT_<lens>.md (one per lens).
The cartographer reads all fragments and synthesizes them in its Phase 4.

Keep this fragment focused on ONE lens — cross-lens synthesis is the cartographer's job.
Authoring guidance: skills/roadmap-synthesis/references/audit-methodology.md
-->

# Audit Fragment: [Lens Name]

**Lens**: [Structure | Quality | Evolution | Automation | Coordinator Awareness | Curiosity | <project-specific>]
**Paradigm applicability**: [deterministic | agentic | both]
**Scope**: [one-paragraph description of what this lens examines in this project]
**Researcher**: [agent id or invocation count]
**Generated**: [ISO 8601 timestamp, UTC]

---

## Findings

Numbered observations, each a single statement backed by ≥1 evidence item. Prefer concrete claims over generalities.

1. **[Finding statement]**
   - Evidence: [`file:line` | `$ cmd` → output | URL (fetched YYYY-MM-DD) | `dec-NNN`]
2. **[Finding statement]** — Evidence: [...]
3. **[Finding statement]** — Evidence: [...]

---

## Evidence

Full citation list. Every quantitative claim must cite a reachable source — see `skills/roadmap-synthesis/references/grounding-protocol.md`.

- [`file:line` — what this file/line shows]
- [`$ command` → relevant excerpt of output]
- [URL (fetched YYYY-MM-DD) — what this source establishes]
- [`dec-NNN` — ADR id and decision line]

---

## Cross-lens Tensions

Observations that might conflict with findings from other lenses. The cartographer uses this section to surface "Considered Angles" in the synthesized roadmap.

- [Tension with <other-lens>]: [one-line description of the disagreement and what the cartographer should weigh]
- [Tension with <other-lens>]: [...]

---

## Memory Candidates for Main Coordinator

Subagents cannot call `remember()` directly. Structured entries below let the main coordinator persist them on return.

- **category**: [learnings | project] · **key**: [kebab-case slug] · **type**: [decision | gotcha | pattern | convention | preference | correction | insight] · **importance**: [3-8]
  **summary**: [~100 chars] · **tags**: [2-4 lowercase] · **value**: [what future agents should know]
