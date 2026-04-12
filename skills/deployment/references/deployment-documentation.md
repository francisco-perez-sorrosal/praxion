# Deployment Documentation

Living document methodology for `SYSTEM_DEPLOYMENT.md`. Back to [SKILL.md](../SKILL.md).

## Purpose

The deployment skill provides generic deployment *knowledge* (primitives, patterns, decision framework). Each project captures its specific deployment *state* in `.ai-state/SYSTEM_DEPLOYMENT.md` -- a living document maintained by the agent pipeline.

**Deployment skill** = how to deploy in general
**SYSTEM_DEPLOYMENT.md** = how THIS system is deployed

## Document Lifecycle

### Creation

The **systems-architect** creates the document from the template (`assets/SYSTEM_DEPLOYMENT_TEMPLATE.md`) during Phase 4 when the architecture includes deployable components. It fills in:
- Section 1 (Overview): quick-facts table
- Section 2 (System Context): boundary diagram and external dependencies
- Section 3 (Service Topology): skeleton with known services
- Section 6 (Failure Analysis): initial FMA table with known risks
- Section 9 (Decisions): cross-references to deployment-related ADRs

Other sections are left with template guidance for downstream agents.

### Updates

The **implementer** is the most frequent updater. After completing any step that creates or modifies deployment files (`compose.yaml`, `Dockerfile`, `Caddyfile`, `systemd` units, `.env.example`), it updates the corresponding section:

| File Changed | Sections Updated |
|-------------|------------------|
| `compose.yaml` | 3 (Service Topology), 8 (Scaling) |
| `Dockerfile` | 3 (image/build info) |
| `Caddyfile` | 3 (reverse proxy entry) |
| `.env.example` | 4 (Configuration) |
| `systemd` units | 5 (Deployment Process) |

The **cicd-engineer** updates Section 5 (Deployment Process) when creating deployment workflows.

### Validation

The **verifier** cross-checks the document against actual configs during Phase 7:
- Port consistency (doc vs compose.yaml)
- Environment variables (doc vs actual usage)
- Service names (doc vs compose service keys)
- File paths (referenced files exist on disk)
- Health checks (doc vs compose healthcheck entries)

A stale deployment doc is a WARN, not a FAIL -- it's advisory, not a gate.

### Auditing

The **sentinel** audits with four checks:
- **F05**: File paths in the doc resolve to existing files
- **F06**: Service list matches compose.yaml
- **X09**: ADR cross-references are valid
- **C09**: Deployment doc exists when deployment configs exist

## Section Ownership Model

Each agent owns specific sections to prevent conflicts:

| Section | Owner(s) | Update Trigger |
|---------|----------|----------------|
| 1. Overview | systems-architect | Architecture changes |
| 2. System Context | systems-architect | New external dependencies |
| 3. Service Topology | systems-architect (skeleton), implementer (as-built) | compose.yaml, Dockerfile changes |
| 4. Configuration | implementer | .env.example changes |
| 5. Deployment Process | cicd-engineer, implementer | Workflow or deploy script changes |
| 6. Failure Analysis | systems-architect (initial), implementer (additions) | New services or risks discovered |
| 7. Monitoring | systems-architect (strategy), implementer (health checks) | compose.yaml healthcheck changes |
| 8. Scaling | systems-architect (strategy), implementer (limits) | Resource limit changes |
| 9. Decisions | systems-architect | ADR creation |
| 10. Runbook | implementer, doc-engineer | New operations established |

Natural pipeline sequencing prevents concurrent edits: architect writes first (Phase 3), implementer updates later (Execution), verifier validates last.

## Staleness Mitigation

Four layers of defense:

1. **Main agent awareness** -- when modifying deployment files in Direct/Lightweight tier (no pipeline), the main agent checks for `.ai-state/SYSTEM_DEPLOYMENT.md` and updates affected sections. The deployment skill's gotchas section reminds of this
2. **Implementer post-step** -- in Standard/Full pipelines, updates doc when deployment files change (proactive, step 7.5)
3. **Verifier Phase 7** -- cross-checks doc vs actual configs after implementation (reactive, per-pipeline)
4. **Sentinel audit** -- checks freshness and consistency independently (reactive, periodic). Finding routing:

| Check | Finding | Recommended Owner | Fix Action |
|-------|---------|-------------------|------------|
| C09 | Deployment configs exist, no deployment doc | systems-architect | Create SYSTEM_DEPLOYMENT.md from template |
| F05 | File paths in deployment doc don't resolve | implementer or main agent | Update stale file references |
| F06 | Service list doesn't match compose.yaml | implementer or main agent | Sync Section 3 with actual compose.yaml |
| X09 | ADR reference in Section 9 invalid | systems-architect | Fix or remove broken ADR reference |

The sentinel detects but never fixes (read-only). Its report's "Recommended Action" and "Owner" columns route findings to the appropriate agent or the main agent for next-session pickup.

## Relationship to ADRs

ADRs document *why* a deployment decision was made. The deployment doc documents *what* the current deployment is. They complement each other:

- The deployment doc references ADR IDs in Section 9 for rationale
- Deployment-related ADRs include `SYSTEM_DEPLOYMENT.md` in `affected_files`
- Never duplicate ADR rationale in the deployment doc -- just link

## Diagram Conventions

Follow the project's Mermaid diagram conventions (see `rules/writing/diagram-conventions.md`):

- **10-12 nodes maximum** per diagram
- **L0/L1/L2 decomposition**: L0 for system context, L1 for service topology, L2 for component internals (only when needed)
- **Standard shapes**: rectangles for services, `[(Database)]` for storage, `([Queue])` for messaging, `{{Decision}}` for decision points
- **Solid arrows** (`-->`) for direct dependencies, **dotted** (`-.->`) for async/event-based
- **Subgraphs** for deployment boundaries, not technical layers
- **Labels over IDs**: `App[Web App]` not bare `App`

## Bootstrap for Existing Projects

For projects that already have deployment configs but no deployment doc:

1. The sentinel's C09 check flags the gap
2. The systems-architect creates the doc when next invoked for a deployment-touching task
3. Read existing `compose.yaml`, `Dockerfile`, `Caddyfile`, `.env.example` to populate sections 3, 4, 7, 8
4. Interview the codebase (grep for port bindings, env vars, health endpoints) to populate remaining sections
