# LikeC4 MCP Tool Recipes

Worked-examples companion to [`../SKILL.md`](../SKILL.md)'s decision rubric. For each of
the 20 `likec4` MCP tools: use case, input shape, and a representative invocation with
response excerpt. Inputs and outputs are illustrative — the live tool surface is the
source of truth.

## MCP Tool Quick Reference
<!-- last-verified: 2026-10-04 -->

**20 tools.** Every tool below carries `readOnlyHint` and `idempotentHint` **except
`apply-semantic-layout`**, which writes a snapshot — see [Layout](#layout-not-read-only).

| Tool | Purpose |
|------|---------|
| `list-projects` | List all LikeC4 projects in the workspace |
| `read-project-summary` | Full project spec: all elements, deployment nodes, and views in one call |
| `search-element` | Search elements and deployment nodes by id, title, kind, shape, tags, or metadata |
| `read-element` | Full details for one element: relationships, views it appears in, deployment instances |
| `read-deployment` | Details for a deployment node or deployed instance |
| `read-view` | Full view details including nodes, edges, and source location |
| `render-view` | Render an existing view as an interactive diagram (pan/zoom/fit) inline, for hosts that support MCP Apps |
| `preview-view` | Render a view defined by DSL text against the project's real elements, without saving; the view id must be new |
| `find-relationships` | Direct and indirect relationships between two named elements |
| `query-graph` | Element hierarchy queries (ancestors, descendants, siblings) and relationship queries |
| `query-incomers-graph` | Complete upstream dependency graph (recursive incomers) |
| `query-outgoers-graph` | Complete downstream dependent graph (recursive outgoers) |
| `query-by-metadata` | Search elements by metadata key-value with exact/contains/exists matching |
| `query-by-tags` | Advanced tag filtering with boolean logic (allOf, anyOf, noneOf) |
| `find-relationship-paths` | All paths (chains of relationships) between two elements via BFS |
| `query-by-tag-pattern` | Tag **pattern** matching — prefix / contains / suffix; for structured taxonomies (`schedule_*`, `*_asil_*`) |
| `batch-read-elements` | Read details for multiple elements in one call (**max 50 ids**) |
| `element-diff` | Compare two elements side by side: properties, tags, metadata, relationships |
| `subgraph-summary` | Compact summary of all descendants of a parent: depth, tags, metadata, relationship counts (`maxDepth` default 10, max 20; capped at 200 descendants) |
| `apply-semantic-layout` | Apply semantic layout to a **view** (LLM-driven via MCP sampling). **Not read-only** — saves a snapshot |

Re-verify when the LikeC4 MCP tool surface changes: inspect the server's tool list in the session, or the
`instructions` string it sends at start.

**Sample domain**: Acme Banking — `auth.service` → `accounts.service`;
`payments.service` → `accounts.service`, `payments.service` → `notifications.service`.
All four are `Component` kind, connected via gRPC.

---

## Discovery

### `list-projects`

**Use case**: Call this first when the workspace is unfamiliar. Returns all LikeC4
project names so subsequent tools can be scoped with `project`. Faster than reading
the directory tree.

**Input shape**: `{}`

**Worked example** — Invocation: `{}`

Response: `["default", "acme-banking"]`

---

### `read-project-summary`

**Use case**: Use when the task needs a full model snapshot — all elements, deployment
nodes, and views. Expensive for narrow lookups; prefer `search-element` or
`query-by-tags` for targeted queries.

**Input shape**: `{ "project": "optional" }`

**Worked example** — Invocation: `{ "project": "acme-banking" }`

Response excerpt:
```json
{
  "elements": [
    { "id": "auth.service",     "title": "Auth Service",     "kind": "Component" },
    { "id": "payments.service", "title": "Payments Service", "kind": "Component" }
  ],
  "views": [{ "id": "landscape", "title": "System Landscape" }]
}
```

---

### `search-element`

**Use case**: Use when the element id is unknown. Keyword-matched against id, title,
kind, shape, tags, and metadata — avoids reading every `.c4` file.

**Input shape**: `{ "search": "string" }`

**Worked example** — Invocation: `{ "search": "auth" }`

Response excerpt:
```json
[{ "id": "auth.service", "title": "Auth Service", "kind": "Component",
   "tags": ["security", "grpc"], "metadata": { "owner": "platform-team" } }]
```

---

## Read

### `read-element`

**Use case**: Use after `search-element` (or when the id is known) to get full element
details: relationships, views it appears in, deployed instances, source location.
Prefer over raw `.c4` reads when the goal is exploring relationships.

**Input shape**: `{ "id": "string", "project": "optional" }`

**Worked example** — Invocation: `{ "id": "payments.service", "project": "acme-banking" }`

Response excerpt:
```json
{
  "id": "payments.service",
  "relationships": [
    { "to": "accounts.service",      "title": "queries balance", "technology": "gRPC" },
    { "to": "notifications.service", "title": "sends receipt",   "technology": "gRPC" }
  ],
  "includedInViews": ["landscape"],
  "sourceLocation": { "file": "model/banking.c4", "line": 24 }
}
```

---

### `read-deployment`

**Use case**: Use for deployment topology queries — which node hosts which component
instance. Switch to `read-element` for logical-relationship queries.

**Input shape**: `{ "id": "string — deployment node or instance id", "project": "optional" }`

**Worked example** — Invocation: `{ "id": "prod.payments-pod", "project": "acme-banking" }`

Response excerpt:
```json
{
  "id": "prod.payments-pod", "kind": "DeploymentNode",
  "deployedInstances": [{ "element": "payments.service", "tags": ["prod"] }],
  "sourceLocation": { "file": "deploy/prod.c4", "line": 8 }
}
```

---

### `read-view`

**Use case**: Use to inspect which elements and edges appear in a specific diagram —
useful before writing docs that reference a view.

**Input shape**: `{ "viewId": "string", "project": "optional" }`

**Worked example** — Invocation: `{ "viewId": "landscape", "project": "acme-banking" }`

Response excerpt:
```json
{
  "id": "landscape",
  "nodes": [{ "id": "auth.service" }, { "id": "accounts.service" }],
  "edges": [{ "source": "auth.service", "target": "accounts.service",
              "label": "authenticates for" }],
  "sourceLocation": { "file": "views/landscape.c4", "line": 1 }
}
```

---

## Relationships

### `find-relationships`

**Use case**: Use for a yes/no reachability check with a compact summary of direct and
indirect relationships between two elements. Faster than `find-relationship-paths` when
full path enumeration is not needed.

**Input shape**: `{ "element1": "string", "element2": "string", "project": "optional" }`

**Worked example** — Invocation:
`{ "element1": "auth.service", "element2": "accounts.service" }`

Response excerpt:
```json
{
  "direct": [{ "from": "auth.service", "to": "accounts.service",
               "title": "authenticates for", "technology": "gRPC" }],
  "indirect": []
}
```

---

### `find-relationship-paths`

**Use case**: Use when every chain of relationships between two elements is needed.
The traversal is already bounded — `maxDepth` defaults to **3** and the server **caps it at
5**, and results are limited to 100 paths. Lower it for tighter scoping; you cannot raise it
past 5. Rejects a call where source equals target.

**Input shape**:
```json
{ "sourceId": "string", "targetId": "string",
  "maxDepth": "optional integer (default 3, min 1, max 5)",
  "includeIndirect": "optional boolean (default false)", "project": "optional" }
```

`includeIndirect: true` also follows implied relationships through nested elements.

**Worked example** — Invocation:
`{ "sourceId": "auth.service", "targetId": "notifications.service", "maxDepth": 4 }`

Response excerpt:
```json
{ "paths": [[
  { "from": "auth.service",     "to": "accounts.service",      "label": "authenticates for" },
  { "from": "accounts.service", "to": "payments.service",      "label": "triggers payment" },
  { "from": "payments.service", "to": "notifications.service", "label": "sends receipt" }
]]}
```

---

### `query-graph`

**Use case**: Use for single-element hierarchy and adjacency queries: parent, children,
siblings, ancestors, descendants, immediate incomers/outgoers. More targeted than the
recursive graph tools when only one structural dimension is needed.

**Input shape**:
```json
{ "elementId": "string",
  "queryType": "ancestors|descendants|siblings|children|parent|incomers|outgoers",
  "includeIndirect": "optional boolean", "project": "optional" }
```

**Worked example** — Invocation:
`{ "elementId": "payments.service", "queryType": "outgoers" }`

Response excerpt:
```json
{ "elements": [
  { "id": "accounts.service",      "relationship": "queries balance" },
  { "id": "notifications.service", "relationship": "sends receipt" }
]}
```

---

### `query-incomers-graph`

**Use case**: Use when the full upstream dependency graph of an element is needed —
recursive incomer traversal in one call, far more efficient than looping over
`query-graph`. Set `maxDepth` on large models.

**Input shape**:
```json
{ "elementId": "string", "includeIndirect": "optional boolean",
  "maxDepth": "optional integer", "maxNodes": "optional integer", "project": "optional" }
```

**Worked example** — Invocation:
`{ "elementId": "accounts.service", "maxDepth": 3, "project": "acme-banking" }`

Response excerpt:
```json
{ "root": "accounts.service",
  "incomers": [
    { "id": "auth.service",     "title": "Auth Service",     "depth": 1 },
    { "id": "payments.service", "title": "Payments Service", "depth": 1 }
  ]}
```

---

### `query-outgoers-graph`

**Use case**: Mirror of `query-incomers-graph` — recursive downstream traversal. Use
for impact analysis: "if X changes, which downstream components are affected?"

**Input shape**:
```json
{ "elementId": "string", "includeIndirect": "optional boolean",
  "maxDepth": "optional integer", "maxNodes": "optional integer", "project": "optional" }
```

**Worked example** — Invocation:
`{ "elementId": "payments.service", "maxDepth": 3, "project": "acme-banking" }`

Response excerpt:
```json
{ "root": "payments.service",
  "outgoers": [
    { "id": "accounts.service",      "title": "Accounts Service",      "depth": 1 },
    { "id": "notifications.service", "title": "Notifications Service", "depth": 1 }
  ]}
```

---

## Filtering

### `query-by-metadata`

**Use case**: Use when elements carry structured metadata (e.g., `owner`, `sla`) and
the task is to find all matching elements. Server-side indexed filter; three match
modes: `exact` (default), `contains`, `exists`.

**Input shape**:
```json
{ "key": "string", "value": "optional string — omit for exists-mode",
  "matchMode": "exact|contains|exists (default exact)", "project": "optional" }
```

**Worked example** — Invocation:
`{ "key": "owner", "value": "platform-team", "project": "acme-banking" }`

Response excerpt:
```json
[
  { "id": "auth.service",     "metadata": { "owner": "platform-team", "sla": "99.99%" } },
  { "id": "accounts.service", "metadata": { "owner": "platform-team", "sla": "99.9%"  } }
]
```

---

### `query-by-tags`

**Use case**: Use when the filter requires boolean tag logic. More expressive than
`search-element`'s keyword match: `allOf` (must have all), `anyOf` (must have at least
one), `noneOf` (must have none). All three parameters are optional and composable.

**Input shape**:
```json
{ "allOf": "optional string[]", "anyOf": "optional string[]",
  "noneOf": "optional string[]", "project": "optional" }
```

**Worked example** — Invocation:
`{ "anyOf": ["security", "grpc"], "noneOf": ["deprecated"], "project": "acme-banking" }`

Response excerpt:
```json
[
  { "id": "auth.service",     "tags": ["security", "grpc"] },
  { "id": "payments.service", "tags": ["grpc", "pci"]      }
]
```

### `query-by-tag-pattern`

**Use case**: Match tags by **shape** rather than by exact value — the complement to
`query-by-tags`. Use it for structured tag taxonomies where the convention encodes meaning in
the name (`schedule_daily`, `schedule_hourly`; `asil_b`, `asil_d`). `query-by-tags` needs the
exact tags up front; this one does not.

**Input shape**:
```json
{ "pattern": "string", "matchMode": "optional prefix|contains|suffix", "project": "optional" }
```

**Worked example** — Invocation:
`{ "pattern": "schedule_", "matchMode": "prefix" }`

Response excerpt:
```json
[
  { "id": "batch.nightly", "tags": ["schedule_daily"]  },
  { "id": "batch.rollup",  "tags": ["schedule_hourly"] }
]
```

## Bulk and Comparison

### `batch-read-elements`

**Use case**: Fetch full details for a **known set** of element ids in one round-trip. This is
the cheap middle ground between `read-element` (one call per element) and
`read-project-summary` (the entire model). Prefer it whenever you already have the ids.

**Input shape**:
```json
{ "ids": "string[] (max 50)", "project": "optional" }
```

**Worked example** — Invocation:
`{ "ids": ["auth.service", "payments.service", "shop.frontend"] }`

Returns the same per-element shape as `read-element`, one entry per requested id. Requesting
more than 50 ids is an error, not a silent truncation — chunk the list yourself.

### `element-diff`

**Use case**: Compare two elements side by side — properties, tags, metadata, and
relationships. Useful when two components are meant to be symmetric (two adapters, two
regions) and you need to find where they diverged.

**Input shape**:
```json
{ "element1Id": "string", "element2Id": "string", "project": "optional" }
```

**Worked example** — Invocation:
`{ "element1Id": "eu.payments", "element2Id": "us.payments" }`

Response reports matching and differing fields, so an asymmetry (a tag on one side only, an
extra outgoing relationship) surfaces without reading both elements in full.

### `subgraph-summary`

**Use case**: Survey **everything beneath a parent element** in one call. Returns each
descendant with its depth, tags, metadata, and relationship counts — the tool's own
description notes it is "much more efficient than calling `read-element` for each descendant
individually."

**Input shape**:
```json
{ "elementId": "string", "maxDepth": "optional (default 10, max 20)",
  "metadataKeys": "optional string[]", "project": "optional" }
```

**Worked example** — Invocation:
`{ "elementId": "shop", "maxDepth": 2, "metadataKeys": ["code_module"] }`

Response excerpt:
```json
{
  "root": { "id": "shop", "kind": "system", "title": "Shop", "childCount": 3 },
  "descendants": [
    { "id": "shop.frontend", "depth": 1, "tags": ["web"],
      "metadata": { "code_module": "web/" },
      "childCount": 0, "incomingCount": 1, "outgoingCount": 2 }
  ],
  "totalDescendants": 7,
  "truncated": false,
  "truncatedByDepth": true
}
```

Descendants come back breadth-first (`depth: 1` = direct child). Watch both truncation flags:
`truncated` means the 200-descendant cap was hit, `truncatedByDepth` means deeper elements
exist beyond `maxDepth`. Use `metadataKeys` to keep the response small.

## Render and preview

### `render-view`

**Use case**: Show an existing view as an interactive diagram inline in the chat (pan, zoom, fit) when
the user wants to *see* it. Use `read-view` instead when only the structure (nodes and edges) matters.
It draws with LikeC4's own layout, not the committed D2 render.

**Input shape**:
```json
{ "viewId": "string", "project": "optional", "fullModel": false,
  "render": { "size": "compact | standard | large", "fitView": true, "initialZoom": 1 } }
```

**Worked example** — Invocation: `{ "viewId": "landscape", "project": "acme-banking" }`

The result is the laid-out view (nodes, edges, bounds) and its model data, consumed by an interactive UI in
hosts that support MCP Apps; other hosts get the data only.

---

### `preview-view`

**Use case**: Iterate on a **new** element view before writing it to a `.c4` file. The DSL text is
rendered in the context of the project's real elements and nothing is saved.

**Input shape**:
```json
{ "dsl": "view <id> ... { ... }", "project": "optional", "fullModel": false }
```

**Worked example** — Invocation:
`{ "dsl": "view auth-flow { include auth.service, accounts.service }", "project": "acme-banking" }`

Constraints: the DSL is one `view <id> ...` definition referencing elements that already exist; the id must
not match an existing view (use `render-view` for that); `dynamic view` and `deployment view` text is
rejected; the preview does not apply the project's custom theme, so judge structure here and styling from
the regenerated render.

---

## Layout (not read-only)

### `apply-semantic-layout`

**Use case**: Apply an LLM-driven semantic layout to a **view**. This is the one tool in the
catalog that is **not read-only** — it drives an MCP `sampling/createMessage` request and
saves a snapshot, returning `reasoning` and `snapshotUri`. It operates on a view, not on
`.c4` source text, so it is not a way to edit the model DSL.

**Input shape**:
```json
{ "viewId": "string", "projectId": "optional" }
```

**Worked example** — Invocation:
`{ "viewId": "shop-context" }`

Treat it like any other write: confirm the view id first, and do not call it speculatively in
a read-only exploration pass.
