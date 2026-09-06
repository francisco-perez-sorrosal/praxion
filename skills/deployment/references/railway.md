# Railway Agent Integration

Integration recipe for driving Railway (railway.com) deployments from Claude Code sessions and Praxion pipelines — what to install, how to authenticate per context, and how to manage environments. Platform basics (project structure, `railway.toml` fields, runtime gotchas) stay in [paas-deployment.md](paas-deployment.md#railway). Back to [SKILL.md](../SKILL.md).

## Consume, Do Not Vendor

Railway maintains a first-party, MIT-licensed Claude Code integration. Praxion's contribution is this recipe — the install decision, the auth matrix, the environment-lifecycle mapping, and the CI wiring. Never re-implement Railway knowledge in Praxion artifacts:

1. Railway's `use-railway` Agent Skill is the deep knowledge source (route-first: it picks CLI vs remote MCP vs GraphQL API per task intent).
2. Railway's MCP server and CLI are vendor-maintained; Praxion registers and invokes them, never wraps or forks them.
3. When Railway's docs and this recipe disagree, trust Railway's docs and refresh this file (`/refresh-skill deployment`).

This is the same consume-not-vendor pattern the `neo-cloud-abstraction` skill uses for its provider adapters: the vendor ships the tooling, Praxion ships the recipe.

## Railway Agent Components
<!-- last-verified: 2026-07-02 -->

| Component | What it is | Install / register | Auth |
|---|---|---|---|
| `railway` plugin (`railwayapp/railway-skills`) | Claude Code plugin bundling the `use-railway` skill plus a `.mcp.json` that auto-registers the remote MCP server | `/plugin install railway@claude-plugins-official`, or `/plugin marketplace add railwayapp/railway-skills` | Delegates to CLI session or MCP OAuth |
| Remote MCP server | Hosted HTTP endpoint at `https://mcp.railway.com` | Auto-registered by the plugin, or `railway setup agent --remote` | OAuth in browser; **rejects project tokens** |
| Local MCP server | stdio server embedded in the CLI (`railway mcp`) | `railway setup agent` or `railway mcp install` | Shares the CLI login session |
| Railway CLI | `railway` binary; also embeds the local MCP server | `bash <(curl -fsSL https://railway.com/install.sh)` | `railway login`, or token env vars (below) |
| GraphQL public API | Same API as the dashboard; introspectable | Direct HTTP; the `use-railway` skill wraps it as a last-resort fallback | Account/workspace token |

### Install decision

- **Interactive session** (developer at the keyboard): install the plugin. One step yields the skill and the remote MCP registration together.
- **Headless context** (pipeline agent, CI, scripted automation): use the CLI only. The remote MCP's OAuth requirement cannot be satisfied non-interactively.
- The `@railway/mcp-server` npm package is a deprecated compatibility shim delegating to `railway mcp` — do not register it in new setups, even though `railway.com/agents/claude` still shows that snippet.

### Bootstrap from zero

Nothing here assumes Railway tooling is pre-installed. In a fresh session or project, check what exists and install only what is missing:

1. **CLI present?** `railway --version` — if missing: `bash <(curl -fsSL https://railway.com/install.sh)`.
2. **Authenticated?** `railway whoami` — if not: `railway login` (interactive) or export `RAILWAY_TOKEN` / `RAILWAY_API_TOKEN` (headless; see the auth matrix).
3. **Plugin present?** (interactive sessions only) — check for the `use-railway` skill in the session's skill listing; if absent, ask the user to run `/plugin install railway@claude-plugins-official` (plugin installation is a user-typed command, not agent-executable).
4. **Project linked?** `railway status` — if not: `railway link` (existing project) or `railway init` (new project).

Railway also ships a cross-tool one-shot installer — `curl -fsSL agents.railway.com | sh` — that installs the skills, configures MCP, and verifies auth in a single step. Prefer the granular checks above when you need to know exactly what changed on the machine; offer the one-shot to users who just want everything set up.

### Auth matrix

| Context | Path | Credential |
|---|---|---|
| Interactive platform ops (status, projects, redeploys) | Remote MCP (via plugin) | OAuth in browser |
| Interactive local-context work (`railway up`, DB scripts) | CLI | `railway login` session |
| Pipeline / CI, project-scoped actions | CLI | `RAILWAY_TOKEN` (project + environment scoped) |
| Pipeline / CI, account-wide actions | CLI | `RAILWAY_API_TOKEN` (account scoped) |

Set exactly one token env var per invocation; keep both out of git per [secrets-management.md](secrets-management.md).

## Environments from an Agent
<!-- last-verified: 2026-07-02 -->

Hierarchy: **project → service → environment**. Every project starts with `production`; an environment is an isolated instance of all services in the project, and every service change is scoped to a single environment.

- **Create**: `railway environment new staging`, or duplicate an existing environment (clones services, variables, config) via dashboard/MCP.
- **Target**: `-e/--environment` on any CLI command; `--json` for machine-readable output; `-y` to skip confirmations in scripts.
- **Promote**: no dedicated primitive — use environment **sync** to import services and config between environments. ("Forking" an environment was removed in January 2024; treat material mentioning it as stale.)
- **PR environments**: when enabled, Railway auto-provisions an ephemeral environment per opened PR (replicating the base environment) and tears it down on merge/close. *Focused* PR environments deploy only services affected by the diff (monorepos). The *Bot PR environments* toggle governs whether bot-authored PRs — Claude Code's included — get environments; flip it deliberately for agent-heavy repos.

## Config-as-Code Surfaces
<!-- last-verified: 2026-07-02 -->

Two complementary mechanisms — neither supersedes the other:

- `railway.toml` / `railway.json` — per-service build/deploy settings beside the code; overrides dashboard settings when both exist; always-current schema at `railway.com/railway.schema.json`. Examples in [paas-deployment.md](paas-deployment.md#railway).
- `.railway/railway.ts` — newer TypeScript Infrastructure-as-Code for multi-resource definitions, managed through the CLI.

Prefer `railway.toml`/`railway.json` for single-service settings; reach for the TypeScript IaC only when defining multiple resources programmatically.

## CI/CD Wiring
<!-- last-verified: 2026-07-02 -->

- No first-party GitHub Action exists; marketplace Railway actions are third-party. Railway's blessed pattern is the CLI container image `ghcr.io/railwayapp/cli:latest` plus a `RAILWAY_TOKEN` secret — full workflow example in the `cicd` skill's [deployment-and-operations.md § Railway Deploy](../../cicd/references/deployment-and-operations.md#railway-deploy).
- For repos linked to GitHub, prefer Railway's built-in autodeploy with **Wait for CI** (holds the deploy until GitHub checks pass) over deploying from Actions.
- Post-deploy jobs: Railway emits GitHub `deployment_status` events; trigger downstream workflows on `success`.

## Gotchas

- **Remote MCP is OAuth-only** — it rejects `RAILWAY_TOKEN`/project tokens by design (user identity required for billing and audit). Never plan a headless step against the MCP; route it through the CLI.
- **MCP tool names drift** — verify against a live `tools/list` (e.g. `/mcp` in Claude Code) before hard-coding tool names in automation; doc-derived tool lists are directionally correct only.
- **`RAILWAY_TOKEN` vs `RAILWAY_API_TOKEN`** carry different scopes (project + environment vs account); a permission error in CI usually means the wrong one is set.
- **No GPUs** — Railway is app/service hosting only. ML training dispatch belongs to the `neo-cloud-abstraction` backends, never Railway.
- **Ephemeral filesystem and free-tier sleep** — see the Railway gotchas in [paas-deployment.md](paas-deployment.md#railway).

## Praxion Wiring

- Record Railway as the deployment target — services, environments, where tokens live — in `.ai-state/SYSTEM_DEPLOYMENT.md` (see [deployment-documentation.md](deployment-documentation.md)).
- `cicd-engineer` owns workflow authoring; hand it the CI/CD Wiring facts above plus the `cicd` skill example.
- Before writing code against the GraphQL API, use the `external-api-docs` skill; if context-hub lacks Railway coverage, fall back to `docs.railway.com` via WebFetch.
