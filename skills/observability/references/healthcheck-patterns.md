# Healthcheck Patterns — per service type

Health-surface guidance for the [Observability](../SKILL.md) skill's § Service Observability Baseline. A health check is **service-conditional**: wire it the moment a project becomes a runtime service. This reference gives the per-type pattern — progressive disclosure for the service type at hand (web service, MCP server, agent).

## The one rule that matters most: never an unconditional 200

The dominant failure mode across every service type is the **always-200 anti-pattern** — a health endpoint that returns success regardless of real state. A check that always passes is *worse than none*: it suppresses alerts while masking the failure. Two corollaries:

- **Signal failure with the status code, not the body.** Monitors check the HTTP status, not the JSON. Return **`503`** when unhealthy — not `200` with `{ "ok": false }`.
- **Make the check actually run.** Framework static-rendering or caching can freeze a health route at a build-time 200. For Next.js App Router, set `export const dynamic = "force-dynamic"` and a `Cache-Control: no-store` header; for any framework, ensure the route is dynamic and uncached.

## Liveness vs readiness — the Kubernetes model

Two questions, two probes ([Kubernetes probes](https://kubernetes.io/docs/concepts/workloads/pods/probes/), **VERIFIED**):

| Probe | Question | Failure action | Checks |
|---|---|---|---|
| **Liveness** (`/healthz`) | Is the process alive/responsive? | Restart it | The process loop only — *no* dependency checks |
| **Readiness** (`/readyz`) | Is it ready to serve traffic? | Remove from rotation (no restart) | Critical dependencies reachable (DB, data root, downstream) |

**Critical anti-pattern:** putting dependency checks in the *liveness* probe. When the dependency blips, every instance fails liveness and restarts *simultaneously* — the probe becomes the outage. Dependency checks belong in *readiness*.

**Sub-Kubernetes (Docker standalone, a local service):** one `/healthz` serving both roles is correct; lean it readiness-style (verify the one critical dependency) but keep it cheap.

## Web service (HTTP)

- **Minimal correct:** `GET /healthz` returns `200` when the critical dependency is reachable, `503` otherwise. Add `/readyz` separately if you run under an orchestrator that distinguishes the two.
- **Next.js App Router:** `app/api/health/route.ts` — `export const dynamic = "force-dynamic"`, `Cache-Control: no-store`, verify the one critical dependency (e.g. the data root), return 200/503. (Praxion's dashboard is the worked example: `dashboard_app/src/app/api/health/route.ts`.)
- **Containerized:** add a `Dockerfile` `HEALTHCHECK`, e.g. `HEALTHCHECK --interval=30s --timeout=3s CMD curl -fsS http://localhost:8080/healthz || exit 1`.

## MCP server

MCP has no generic HTTP health surface; the signal depends on the transport ([MCP spec — ping, 2025-11-25](https://modelcontextprotocol.io/specification/2025-11-25/basic/utilities/ping), **VERIFIED**):

- **stdio transport** (no HTTP port): the protocol-native liveness signal is the **`ping`** JSON-RPC request. Process alive + a timely ping response = live. There is no HTTP endpoint to expose.
- **Streamable-HTTP transport:** expose a plain `GET /health` (200 alive / 503 degraded) for infrastructure liveness, **and** treat a successful **`list_tools`** call as the *readiness* signal — it exercises real initialization, not just socket reachability.
- **Caveat:** a server that answers `ping` may still fail `call_tool`. `list_tools` is the stronger readiness check; `ping`/process-alive is liveness only.

## Long-running agent

Agent health is **three signals, not one** — and convention maturity is **LOW** outside orchestrators like Temporal (treat as guidance, not a settled standard):

1. **Liveness** — a heartbeat to a coordinator every N seconds ([Temporal heartbeats](https://docs.temporal.io/encyclopedia/detecting-activity-failures), **VERIFIED**).
2. **Progress** — a `last_progress_at` timestamp in a durable store; alert if it does not advance within 2–3× the expected step time.
3. **Status surface** — `GET /status` returning `{ step, last_heartbeat_at, last_error }`.

**Caveat (the agent-specific always-200 trap):** **liveness ≠ progress.** An agent can emit heartbeats while completely stuck waiting on an LLM call. Health for an agent therefore requires the *progress* signal in addition to liveness — a heartbeat alone is the always-200 anti-pattern wearing a different hat.

## What Praxion's readiness detector recognizes

`c.observability.healthcheck` passes on any of: a `Dockerfile` `HEALTHCHECK` (root or a subdirectory service), a `healthz`/`/health` signal in a `package.json` (root or subdir), or a `route.*` handler inside a `health`/`healthz`/`healthcheck` directory (the app-router pattern). So a web service's health route or a container `HEALTHCHECK` satisfies it; an MCP stdio server (ping-only, no HTTP) legitimately may not — for a non-service repo, down-weight the observability pillar in `.ai-state/readiness_config.json` rather than fabricating a health surface the project does not need.

## Sources

- [Kubernetes — Liveness, Readiness and Startup Probes](https://kubernetes.io/docs/concepts/workloads/pods/probes/) — the probe model + the dependency-in-liveness anti-pattern. **[VERIFIED]**
- [MCP specification — Ping (2025-11-25)](https://modelcontextprotocol.io/specification/2025-11-25/basic/utilities/ping) — protocol-native liveness. **[VERIFIED]**
- [Temporal — Detecting activity failures (heartbeats)](https://docs.temporal.io/encyclopedia/detecting-activity-failures) — agent liveness via heartbeat. **[VERIFIED]**
- [Cloudflare — Long-running agents](https://developers.cloudflare.com/agents/concepts/long-running-agents/) — agent progress/status patterns. **[SINGLE-SOURCE — convention maturity LOW]**
