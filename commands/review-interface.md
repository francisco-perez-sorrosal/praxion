---
description: Run an interface design review on a file, PR, branch, or named surface
argument-hint: "[PR-number|branch|file|surface]"
allowed-tools: [Bash, Read, Grep, Glob, Task]
---

Run an interface design review using the [interface-designer](../agents/interface-designer.md) agent in **standalone mode**. Produces a structured Interface Design Review covering web UI, TUI/CLI, API, and/or agentic tool surfaces, with findings classified by severity (CRITICAL / IMPORTANT / SUGGESTED).

Peer to [/review-pr](review-pr.md) (which reviews code quality); this command reviews interface design quality.

## Process

1. **Resolve the review target** from `$ARGUMENTS`:

   - **PR number** (e.g., `123`): Fetch PR diff with `gh pr diff` and collect changed interface-surface files (routes, components, API handlers, MCP tool definitions, CLI command modules)
   - **Branch name** (e.g., `feat/api-v2`): Diff against the repo's default branch to collect changed interface-surface files
   - **File path** (e.g., `src/api/routes.ts`): Review the named file directly
   - **Named surface** (e.g., `payment-api`, `dashboard-ui`, `mcp-tools`): Locate relevant files via `grep`/`glob` matching the surface name
   - **No argument**: Review the current branch diff against the default branch, same as branch mode

2. **Invoke the interface-designer** via the Task tool in standalone review mode:

   - Pass the resolved file list or diff as context
   - Include the surface type(s) detected (web UI, TUI/CLI, REST API, GraphQL, gRPC, MCP tools)
   - Request a standalone Interface Design Review (not pipeline-mode `INTERFACE_DESIGN.md`)
   - Include `Task slug: review-interface` so the agent writes any scratch files to `.ai-work/review-interface/`

3. **Output the review** directly in the conversation, structured as:

   - **Verdict** — PASS / PASS WITH FINDINGS / FAIL (one or more CRITICAL findings → FAIL)
   - **Surface Coverage** — which surfaces were reviewed and which skills activated
   - **Findings** — table with columns: Severity | Surface | File:Line | Finding | Recommendation
   - **Scope** — files reviewed, timestamp
