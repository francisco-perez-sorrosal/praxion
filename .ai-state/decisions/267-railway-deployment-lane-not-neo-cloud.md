---
id: dec-267
title: Railway integrates via the deployment-skill lane, consuming Railway's first-party tooling
status: accepted
category: architectural
date: 2026-07-02
summary: Railway support lands as a deployment-skill integration recipe consuming Railway's MIT-licensed plugin/MCP/CLI unmodified — not as a neo-cloud backend, not as a standalone Praxion skill, and with nothing vendored.
tags: [railway, deployment, paas, mcp, plugin, cicd, consume-not-vendor]
made_by: agent
agent_type: orchestrator
branch: main
pipeline_tier: lightweight
affected_files:
  - skills/deployment/references/railway.md
  - skills/deployment/SKILL.md
  - skills/deployment/README.md
  - skills/deployment/references/paas-deployment.md
  - skills/cicd/SKILL.md
  - skills/cicd/references/patterns-and-examples.md
dissent: "A dedicated railway skill with its own activation triggers would be more discoverable than a reference inside the deployment skill; discovery now depends on the deployment skill's description matching Railway-environment tasks."
---

## Context

The user asked to extend Praxion's provider abstractions to manage Railway environments, explicitly constraining the integration to (a) reuse Railway's own shipped tooling without rewriting anything and (b) live outside `neo-cloud-abstraction` if a deployment-side home fits better (user directive at intake). External research (`.ai-work/railway-integration/RESEARCH_FINDINGS.md`) established: Railway ships a first-party, MIT-licensed Claude Code plugin (`railwayapp/railway-skills`, marketplace entry `railway@claude-plugins-official`) bundling a route-first `use-railway` Agent Skill plus auto-registration of a hosted remote MCP server (`https://mcp.railway.com`, HTTP + OAuth); the standalone MCP npm package is a deprecated shim, the MCP server having been folded into the Railway CLI; headless auth exists only through CLI token env vars (`RAILWAY_TOKEN` / `RAILWAY_API_TOKEN`); Railway offers no GPU/training compute; and no first-party GitHub Action exists (the blessed CI pattern is the `ghcr.io/railwayapp/cli:latest` container).

## Decision

Integrate Railway in the deployment lane as a consume-not-vendor recipe:

1. New `skills/deployment/references/railway.md` — component inventory, install decision (plugin for interactive; CLI-only for headless), per-context auth matrix, environment/PR-environment lifecycle, config-as-code surfaces, CI wiring, gotchas.
2. New `Railway Deploy` workflow example in `skills/cicd/references/patterns-and-examples.md` (CLI-container + `RAILWAY_TOKEN` pattern).
3. Praxion vendors nothing: Railway's plugin, skill, MCP server, and CLI are installed/invoked as-shipped; the recipe only encodes the decisions Railway's own docs leave to the consumer (which surface per context, which token per scope) plus Praxion-specific wiring (`SYSTEM_DEPLOYMENT.md`, `cicd-engineer` handoff).
4. Drift-prone sections are cataloged in both skills' `staleness_sensitive_sections`.

## Considered Options

### Neo-cloud backend (rejected — user directive + domain mismatch)

`neo-cloud-abstraction` is a training-job dispatch contract (8 lifecycle operations over GPU backends). Railway has no GPU/training compute; forcing an app-hosting PaaS behind a training-dispatch schema would leak the abstraction. Only the pattern (vendor ships tooling, Praxion ships recipe) transfers.

### Standalone `railway` Praxion skill (rejected)

Pro: own activation triggers, higher discoverability. Con: duplicates the knowledge surface Railway's own `use-railway` skill already owns, adds a catalog entry + always-loaded description cost, and blurs the boundary between Praxion's recipe and Railway's content — the exact wheel-reinvention the intake constraint forbids.

### Deployment-skill reference (chosen)

Keeps one deployment knowledge surface, mirrors the established provider-adapter recipe shape, costs zero always-loaded tokens beyond an amended description, and leaves Railway's plugin as the deep knowledge source.

### Extend paas-deployment.md only (rejected)

Cheapest, but buries an agent-integration recipe inside a four-platform comparison file and bloats a shared reference; the agent surface (plugin/MCP/auth routing) is a different concern from platform basics.

## Consequences

Positive: zero vendored content to maintain; Railway updates flow through their plugin/CLI without Praxion changes; headless-vs-interactive auth routing is now an explicit, teachable matrix; cicd-engineer gains a citable Railway workflow pattern; staleness machinery covers the drift-prone facts (install commands, token names, MCP consolidation state).

Negative: discovery of the recipe depends on the deployment skill triggering (see `dissent:`); managed projects get no proactive onboarding nudge yet — `/onboard-project` Railway detection (railway.toml/json, `.railway/`) was deliberately deferred as a follow-up pending user scope confirmation; MCP tool names in Railway's docs were not schema-verified, so the recipe instructs live `tools/list` verification instead of hard-coding names.

## Disconfirmation

- **Falsifier**: evidence that agents repeatedly fail to find the Railway recipe when handling Railway tasks (sessions reaching for web search or hallucinating Railway CLI/MCP facts despite the deployment skill being installed) would show the reference placement is too buried and the standalone-skill option was right.
- **Steelmanned runner-up**: a standalone `railway` skill is the strongest alternative — vendor-named skills are how users think ("the DigitalOcean skill", "the Railway skill"), activation triggers could name Railway environment vocabulary directly, and the marginal always-loaded cost is one description line; if Railway coverage grows past one reference file (templates, IaC deep-dive, observability), promotion to a skill becomes the natural shape.
- **Reversal trigger**: Railway coverage needing a second or third reference file, or a managed project's session demonstrably missing the recipe on a Railway task, should prompt promoting the content to a dedicated skill (and demoting `railway.md` to a pointer).
