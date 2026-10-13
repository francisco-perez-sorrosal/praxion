### Delegation Checklists

<!-- Anchor preserved for cross-rule links; canonical content lives in coordination-details.md -->

When delegating to an agent, the main agent **must** include the per-agent deliverables in the prompt. The subagent's system prompt contains full instructions, but the main agent's prompt determines priority and scope.

When the orchestrator authors a pipeline artifact itself rather than spawning its owning agent — legitimate at any tier — the document contract still binds: **the schema binds the path, not the author**. Write that agent's canonical section skeleton, or pick a filename it does not own.

Full per-agent checklists (systems-architect, implementation-planner, implementer, verifier) are authoritative at [`coordination-details.md § Delegation Checklists`](../../skills/software-planning/references/coordination-details.md#delegation-checklists). `REWORK_MANIFEST.md` triggers the main agent to spawn rework worktrees before cleanup.

**Multiplicity check:** Before spawning any Bg Safe agent, check whether the work decomposes into N independent targets with disjoint file sets; if so, spawn N instances (up to 2-3 concurrent) instead of one sequential agent. Each gets the same task slug — they share a task-scoped directory and use fragment files to avoid collisions (see [agent-intermediate-documents](agent-intermediate-documents.md)). **Lens-independence mandate:** parallel lens/fan-out agents MUST NOT reference sibling lenses during collection; reconciliation happens only at the synthesis/aggregator layer. Violating this collapses independent perspectives into correlated ones, defeating the breadth rationale. Deep-dive: [`agent-pipeline-details.md` § Multi-Perspective Analysis](../../skills/software-planning/references/agent-pipeline-details.md).

**Task slug propagation:** defined once in [agent-intermediate-documents.md § Task Slug Convention](agent-intermediate-documents.md#task-slug-convention).
