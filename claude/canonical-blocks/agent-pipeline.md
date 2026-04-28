## Agent Pipeline

Follow the **Understand, Plan, Verify** methodology. For multi-step work (Standard/Full tier), delegate to specialized agents in pipeline order. Each pipeline operates in an ephemeral `.ai-work/<task-slug>/` directory (deleted after use); permanent artifacts go to `.ai-state/` (committed to git).

1. **researcher** → `.ai-work/<slug>/RESEARCH_FINDINGS.md` — codebase exploration, external docs
2. **systems-architect** → `.ai-work/<slug>/SYSTEMS_PLAN.md` + ADR drafts under `.ai-state/decisions/drafts/` (promoted to stable `<NNN>-<slug>.md` at merge-to-main by the post-merge hook) + `.ai-state/ARCHITECTURE.md` (architect-facing) + `docs/architecture.md` (developer-facing)
3. **implementation-planner** → `.ai-work/<slug>/IMPLEMENTATION_PLAN.md` + `WIP.md` — step decomposition
4. **implementer** + **test-engineer** (concurrent, on disjoint file sets) → code + tests — execute steps from the plan
5. **verifier** → `.ai-work/<slug>/VERIFICATION_REPORT.md` — post-implementation review

**Independent audits.** The `sentinel` agent runs outside the pipeline and writes timestamped `.ai-state/sentinel_reports/SENTINEL_REPORT_<timestamp>.md` plus an append-only `.ai-state/sentinel_reports/SENTINEL_LOG.md`. Trigger it for ecosystem health baselines (before first ideation, after major refactors).

**From PoC to production.** The feature pipeline is one milestone of many. The full journey: baseline audit (`/sentinel`) → CI/CD setup (`cicd-engineer` agent) → deployment (`deployment` skill) → first release (`/release`) → ongoing decisions captured as ADRs in `.ai-state/decisions/` → cross-session memory in `.ai-state/memory.json` (when memory MCP is enabled).

Always include expected deliverables when delegating to an agent. The agent coordination protocol rule has full delegation checklists.
