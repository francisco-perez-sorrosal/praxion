# Decisions Index

Auto-generated from ADR frontmatter. Do not edit manually.
Regenerate: `python scripts/regenerate_adr_index.py`

| ID | Title | Status | Category | Date | Tags | Summary |
|----|-------|--------|----------|------|------|---------|
| dec-001 | Skill wrapper as primary context-hub integration | accepted | architectural | 2026-03-31 | context-hub, skills, integration | Use a skill wrapper for context-hub integration instead of bundling an MCP server in plugin.json |
| dec-002 | Chronograph as OTel relay for hook telemetry | accepted | architectural | 2026-03-31 | observability, otel, chronograph, phoenix | Hooks POST events to chronograph which creates OTel spans and exports to Phoenix via OTLP HTTP |
| dec-003 | Dedicated Phoenix venv separate from chronograph | accepted | architectural | 2026-03-31 | observability, phoenix, dependencies, isolation | Phoenix gets its own venv at ~/.phoenix/venv/ to isolate heavy dependencies from chronograph |
| dec-004 | CHAIN span kind for session root, AGENT for pipeline agents | accepted | architectural | 2026-03-31 | observability, otel, openinference, phoenix | Use OpenInference CHAIN for orchestration/session root and AGENT for reasoning blocks in Phoenix traces |
| dec-005 | Dual storage: EventStore for real-time MCP + OTel/Phoenix for persistence | accepted | architectural | 2026-03-31 | observability, storage, chronograph, phoenix | Maintain both in-memory EventStore for MCP queries and OTel/Phoenix for persistent traces in parallel |
| dec-006 | Use Commitizen over Release Please for versioning | accepted | architectural | 2026-04-01 | versioning, automation, commitizen | Commitizen selected for native PEP 440 dev releases and local-first CLI workflow over Release Please's PR-based model |
| dec-007 | Skill-centric security watchdog instead of dedicated agent | accepted | architectural | 2026-04-01 | security, skills, architecture | Shared context-security-review skill consumed by CI workflow and verifier agent instead of a dedicated security-reviewer agent |
| dec-008 | Diff mode by default with full-scan on command for security review | accepted | architectural | 2026-04-01 | security, review-modes, ci | Security review defaults to diff mode (changed files only) with full-scan mode available via explicit command invocation |
