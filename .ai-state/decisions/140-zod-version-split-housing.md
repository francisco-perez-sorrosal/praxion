---
id: dec-140
title: Zod v3/v4 cross-skill version split — canonical home in node-prj-mgmt
status: accepted
category: architectural
date: 2026-05-11
summary: The Zod v3 (MCP TS SDK v1) vs Zod v4 (OpenAI Agents SDK JS) coexistence gotcha lives in node-prj-mgmt/SKILL.md Gotchas. mcp-crafting and agentic-sdks contexts cross-reference. Establishes a protocol for future cross-skill version conflicts.
tags: [skills, node-prj-mgmt, zod, cross-skill, version-conflict, gotcha]
made_by: agent
agent_type: systems-architect
branch: worktree-multi-language-support
pipeline_tier: full
affected_files:
  - skills/node-prj-mgmt/SKILL.md
  - skills/mcp-crafting/contexts/typescript.md
  - skills/agentic-sdks/contexts/openai-agents-typescript.md
re_affirms: dec-139
---

## Context

Phase 1b research identified that two Praxion skills' recommended TypeScript SDKs pin incompatible Zod majors:

- `mcp-crafting`'s recommended `@modelcontextprotocol/sdk` v1.x stable uses **Zod v3**
- `agentic-sdks`'s `@openai/agents` JS SDK requires **Zod v4** at runtime (silent schema-validation failures otherwise — already documented in `agentic-sdks` Gotchas)

A project using both SDKs simultaneously needs to manage two Zod majors. The pnpm `overrides` field handles this cleanly; npm uses `overrides`; yarn uses `resolutions`. The canonical knowledge needs ONE home, and future cross-skill version conflicts need a documented surfacing protocol.

The candidate homes are: (a) both `mcp-crafting/contexts/typescript.md` AND `agentic-sdks/contexts/openai-agents-typescript.md` (duplicated), (b) a single home with cross-references, or (c) a new shared reference file.

## Decision

**Canonical home**: `skills/node-prj-mgmt/SKILL.md` Gotchas section. Concrete content the implementer writes (Phase B.1):

```markdown
## Gotchas

- **Zod v3 (MCP TS SDK) and Zod v4 (OpenAI Agents SDK) coexist via package-manager overrides.**
  The MCP TypeScript SDK v1.x stable depends on Zod v3; the OpenAI Agents SDK for JS requires
  Zod v4 at runtime (silent schema failures otherwise). Projects using both must pin both:

      // package.json
      "dependencies": {
        "@modelcontextprotocol/sdk": "^1",
        "@openai/agents": "^X",
        "zod": "^4"  // primary version your project code uses
      },
      "pnpm": {
        "overrides": {
          "zod@<4": "$zod"  // optional: force all consumers to v4 if compatible
        }
      }

  In practice, the MCP SDK v1 accepts Zod v4 via duck-typed parsing for most schemas, so
  pinning Zod v4 + letting the MCP SDK consume it works in most cases. Verify your
  specific MCP schemas before relying on this. When MCP SDK v2 stable ships with Standard
  Schema support, this gotcha resolves naturally (see MCP SDK v2 Promotion ADR).
```

**Cross-references** from the conflicting skills:

- `mcp-crafting/contexts/typescript.md` adds a short callout: "If your project also uses OpenAI Agents SDK JS (Zod v4), see [node-prj-mgmt § Zod v3/v4 coexistence] for the canonical pnpm `overrides` pattern."
- `agentic-sdks/contexts/openai-agents-typescript.md` adds (or verifies it already adds, per Phase 1b §Gap 8): "If your project also uses MCP TypeScript SDK v1 (Zod v3), see [node-prj-mgmt § Zod v3/v4 coexistence] for the coexistence pattern."

**Cross-skill version-conflict surfacing protocol** (established by this ADR):

1. Canonical resolution lives in the language-/runtime-rooted project-management skill (`node-prj-mgmt`, `python-prj-mgmt`, etc.) — that is where dependency graph mechanics belong
2. Each conflicting skill's relevant `contexts/<language>.md` cross-references the prj-mgmt entry
3. An ADR documents the resolution mechanism if non-obvious (pnpm `overrides`, uv `tool.uv.constraint-dependencies`, npm `resolutions`)
4. The conflict pair appears in the originating skill's Gotchas section if the silent-failure surface is large (Zod v4-vs-v3 qualifies — silent runtime schema failures)

## Considered Options

### Option 1 — Document in both `mcp-crafting/contexts/typescript.md` and `agentic-sdks/contexts/openai-agents-typescript.md`

**Pros**: Each skill is self-contained; no cross-skill navigation cost.

**Cons**: Duplicated content drifts (two sources of truth on the same dependency-graph fact); a fix in one place doesn't propagate; agents working in one context may see outdated advice in the other.

### Option 2 — Single home in `node-prj-mgmt` with cross-references (chosen)

**Pros**: One source of truth; the prj-mgmt skill is the correct conceptual home for dependency-graph mechanics; cross-references are lightweight; establishes a clear protocol for future conflicts.

**Cons**: Agents working purely inside MCP or Agents contexts must follow one cross-link.

### Option 3 — Create a new shared reference file (e.g., `references/cross-skill-version-conflicts.md`)

**Pros**: A dedicated home for the category.

**Cons**: New file with one entry is overkill; the prj-mgmt skill already covers the conceptual space; setting up a new file just for one gotcha is structurally wasteful.

## Consequences

### Positive

- Single source of truth for the Zod v3/v4 coexistence pattern
- The `node-prj-mgmt` skill becomes the canonical home for *all* Node/TS dependency-graph mechanics — a natural conceptual placement
- Future cross-skill version conflicts (Pydantic v1/v2 across Python skills, etc.) inherit a clear protocol
- Cross-references from both originating skills ensure discoverability without duplication

### Negative

- Cross-link drift risk: one of the linked skills moves files, the other stale-references it; mitigated by Praxion's existing cross-reference verification in sentinel and skill-genesis
- Agents must follow one extra link when first encountering the conflict; one-time cognitive cost

### Neutral

- Establishes a "language-rooted prj-mgmt skill owns cross-skill dependency conflicts" convention that scales to future polyglot work
