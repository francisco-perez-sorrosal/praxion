---
title: Integrating Linear into Praxion — Feasibility, Vision, and Approach
type: independent-analysis
audience: architect / maintainer
status: analysis (no implementation)
date: 2026-06-24
author: Francisco Perez-Sorrosal (analysis drafted with Cursor agent)
verification: claims tagged VERIFIED / SINGLE-SOURCE / ASSUMPTION / DESIGN
---

# Integrating Linear into Praxion

> **Scope of this document.** This is an analysis, not an implementation. It answers three
> questions in order — (1) *does it make sense?*, (2) *is it possible?*, (3) *how would we do
> it?* — and then lays out a phased plan. No code, no canonical blocks, no onboarding edits
> are produced here. It is written to be decision-grade: a `systems-architect` should be able
> to render an ADR from it, and an `implementation-planner` should be able to decompose Phase 1
> without further research.

---

## 0. TL;DR

- **Does it make sense? — Yes.** Praxion is a "software factory" whose work-tracking today
  lives in *ephemeral* (`.ai-work/<slug>/`) and *local-permanent* (`.ai-state/`) artifacts plus
  git and in-session `TodoWrite`. It has **no durable, human-facing, multi-actor backlog /
  triage / roadmap surface**. That is precisely the gap Linear fills. The fit is strong and the
  two systems are complementary, not overlapping.
- **Is it possible? — Yes, and on two independent maturity levels.** Linear ships an **official,
  GA, remote MCP server** (`https://mcp.linear.app/mcp`) that any Praxion-supported assistant
  (Claude Code, Cursor, Codex) can consume today, and a **first-class Agent Interaction API**
  (currently *Developer Preview*) that lets an external agent be *delegated* Linear issues and
  report progress back into Linear's native UI.
- **One-line recommendation.** Ship **Tier A (Linear-as-MCP, consumption-side)** first — a
  per-project, opt-in, version-pinned integration installed by `/onboard-project`, dogfooded by
  Praxion itself, with a thin identity bridge between **Linear issue ↔ Praxion task slug ↔
  `.ai-work`/`.ai-state` artifacts**. Treat **Tier B (Praxion-as-Linear-agent)** as a later,
  explicitly opt-in, self-hosted phase gated on the Agent API reaching GA — because it
  introduces a hosted always-on endpoint that is in direct tension with Praxion's local-first,
  git-as-sole-substrate ethos.

---

## 1. Does it make sense?

### 1.1 The gap in Praxion today

Praxion's SDLC is rich on the **execution and knowledge** axes but deliberately thin on the
**work-management** axis:

| Concern | Where it lives in Praxion today | Limitation |
|---|---|---|
| In-flight pipeline state | `.ai-work/<task-slug>/` (WIP.md, PLANs, REPORTs) | Ephemeral, gitignored, single-task, single-machine |
| Decisions | `.ai-state/decisions/` ADRs (`dec-NNN`) | Durable but not a *task* surface |
| Tech debt | `.ai-state/TECH_DEBT_LEDGER.md` (`td-NNN`) | A ledger, not a workflow/triage board |
| Ideas | promethean `.ai-state/idea_ledgers/` | Local markdown, no assignment/status/collaboration |
| Roadmap | roadmap-cartographer `ROADMAP.md` (regenerated on demand) | A document, not a living tracked backlog |
| Per-session todos | `TodoWrite` tool | In-memory, vanishes with the session |
| Cross-session work | git history + `.ai-state/` | No human-facing status / ownership / due-date / triage |

There is **no surface that answers "what is the team working on, who owns it, what's the
status, what's next, and how does this map to the roadmap"** in a way a human (or a second
collaborator, or a stakeholder) can see and steer. `task-chronograph` is *observability*
(OpenTelemetry spans → Phoenix), **not** a task tracker — the name is misleading in this
context. *(VERIFIED against `docs/observability.md` and `task-chronograph-mcp/`.)*

Linear is exactly a durable, multi-actor, human-facing **issue / project / initiative / cycle**
system with triage, assignment, status workflows, and roadmap. It slots into the one axis
Praxion under-serves.

### 1.2 Why it is complementary, not redundant

The two systems have a clean **source-of-truth split**:

- **Linear owns intent & status:** *what* to build, *who* owns it, *what state* it's in, *how*
  it ladders up to projects/initiatives, *when* it's due.
- **Praxion owns process & rationale:** *how* it was researched, decided (ADRs), planned,
  implemented, verified — and the durable trace of that (git, `.ai-state/`).

This split means Linear becomes the **front door and status mirror** of the factory, while
Praxion remains the **factory floor**. A Linear issue becomes the long-lived, human-readable
handle for a unit of work whose internal artifacts are the Praxion pipeline documents.

### 1.3 Strategic fit with Praxion's own principles

- **Context engineering.** A delegated Linear issue (with its `promptContext`, comments, and
  team/workspace *guidance*) is a *higher-quality, structured intake* than a free-text prompt —
  it directly feeds the **Intake Clarity Gate** and `TASK_BRIEF.md`. *(DESIGN.)*
- **Human-in-the-loop.** Linear's agent model sets a delegated agent as **`delegate`, not
  `assignee`** — "humans maintain ownership while agents act on their behalf." *(VERIFIED — Linear
  agents docs.)* This is a near-perfect match for Praxion's Conversation Checkpoints and the
  Behavioral Contract's *Surface Assumptions / Register Objection* stance.
- **Assistant-agnostic.** Linear's MCP server is consumed identically by Claude Code, Cursor,
  and Codex *(VERIFIED — Linear MCP docs list all three)* — matching Praxion's
  "assistant-agnostic shared assets" rule.
- **Standards convergence as opportunity** (a stated Praxion principle): MCP is the convergence
  point; adopting Linear's official MCP server is exactly the kind of "ride the standard"
  move Praxion's guiding principles call for.

**Verdict: it makes sense.** The integration is additive, fills a real gap, and is philosophically
aligned. The one genuine tension (a hosted agent endpoint vs. local-first) is isolable to Tier B
and is *opt-in* — see §3.

---

## 2. Is it possible?

Yes. Linear exposes **four** integration surfaces, of increasing power and increasing
operational cost. All claims below are tagged.

### 2.1 Linear's integration surfaces

| # | Surface | What it gives you | Transport / auth | Maturity |
|---|---|---|---|---|
| S1 | **Official remote MCP server** (`https://mcp.linear.app/mcp`) | Find / create / update issues, projects, comments, initiatives, milestones, updates as MCP tools | Streamable HTTP; OAuth 2.1 w/ dynamic client registration, **or** `Authorization: Bearer <API key / OAuth token>` | **GA** *(VERIFIED — linear.app/docs/mcp)* |
| S2 | **GraphQL API** (`https://api.linear.app/graphql`) | Full programmatic access to the entire data model | API key or OAuth | **GA** *(VERIFIED)* |
| S3 | **Webhooks + `@linear/sdk`** (`LinearWebhookClient`) | React to issue/comment/etc. changes; signature-verified | HTTPS endpoint you host; HMAC signature on raw body | **GA** *(VERIFIED — sdk-webhooks docs)* |
| S4 | **Agent Interaction API** (Agent Sessions + Agent Activities) | Be a *first-class workspace agent*: `@mentionable`, assignable (as **delegate**), receive `AgentSessionEvent` webhooks (`created`/`prompted`), emit `thought`/`elicitation`/`action`/`response`/`error` activities that render natively in Linear | OAuth app with `actor=app` + `app:assignable` + `app:mentionable` scopes; webhook endpoint | **Developer Preview** — "may change before GA" *(VERIFIED — linear.app/developers/agents)* |

Key verified facts that shape the design:

- The MCP server (S1) accepts a **Bearer API key directly** — so a headless/CI agent can use it
  without the interactive OAuth dance. *(VERIFIED.)*
- Agents (S4) **do not count as billable users**, and developing them is free. *(VERIFIED.)*
- S4 imposes **responsiveness SLAs**: acknowledge a `created` session within ~5s and emit a
  first activity within ~10s, or be marked unresponsive. *(VERIFIED — agent-interaction docs.)*
- `actor=app` **cannot** also request `admin` scope. *(VERIFIED.)*
- S4 carries **`guidance`** (workspace/team/parent instructions, e.g. preferred repos) inside the
  webhook — a structured place for "how this team wants its agent to behave." *(VERIFIED.)*

### 2.2 What each surface buys Praxion

- **S1 (MCP)** → the *cheapest, GA, assistant-agnostic* path. Praxion agents read & write Linear
  as a tool. **This is the backbone of Tier A.**
- **S2 (GraphQL)** → fallback for operations the MCP tool surface doesn't yet expose (e.g.
  bulk queries, custom fields, cycle mechanics). Used surgically, not as the primary path.
- **S3 (webhooks)** → enables *Linear → Praxion* push (status changes, new triage issues) for a
  sync daemon, **but requires a hosted endpoint.**
- **S4 (Agent API)** → the full "delegate an issue to Praxion and watch it work" vision.
  **Most powerful, least mature, most operationally heavy.**

**Verdict: it is possible** — comfortably for Tier A (today, GA), and ambitiously for Tier B
(soon, pending GA + self-hosting).

---

## 3. The load-bearing tension (and how to resolve it)

Praxion has an architectural constraint worth stating plainly: **git is the sole synchronization
substrate**, the system is **local-first**, and the explicit design stance (echoed in the
in-flight `cursor-ci-autofix-research-brief.md`) is **per-project ownership, not a centralized
service that reaches into projects.**

Linear is a hosted SaaS. Two of its surfaces (S3 webhooks, S4 agent) require an **always-on,
publicly reachable endpoint** to receive pushes. That endpoint is, by nature, a *service* — the
very shape Praxion avoids.

**Resolution — split by direction of data flow:**

- **Pull / command-driven (Praxion → Linear, and Praxion-pulls-Linear):** no hosted endpoint
  needed. The agent calls the MCP server on demand (during a pipeline, or via a slash command,
  or in a CI job). This is **Tier A** and it preserves local-first perfectly — Linear is "just
  another MCP tool," configured per-project, secrets owned per-project.
- **Push (Linear → Praxion, real-time):** requires hosting. Quarantine this into **Tier B**, make
  it **opt-in**, **self-hosted by the operator** (mirroring the autofix brief's per-project,
  operator-owned-secrets discipline), and gate it on the Agent API reaching GA.

This keeps the default integration faithful to Praxion's ethos while leaving a clean runway to
the full vision for teams that want it.

---

## 4. Vision

> **Linear is the front door and the status mirror of the Praxion software factory; the Praxion
> pipeline is the factory floor. A unit of work is born or triaged in Linear, executed by the
> Praxion pipeline, and its status, rationale, and artifacts flow back to Linear as a living,
> human-readable record — without either system becoming the other.**

Concretely, at full maturity:

1. A human (or promethean, or roadmap-cartographer) files or triages an issue in Linear.
2. The issue is **delegated** to Praxion (Tier B) or **pulled** by a developer running a command
   (Tier A). Its `promptContext` + `guidance` seed the **Intake Clarity Gate** and `TASK_BRIEF.md`.
3. The Praxion pipeline runs (researcher → architect → planner → implementer ∥ test-engineer →
   verifier). At each **phase transition**, a concise status update is mirrored to the Linear
   issue (a comment in Tier A; a native `AgentActivity` in Tier B).
4. ADRs (`dec-NNN`), tech-debt rows (`td-NNN`), and the eventual PR are **linked** on the Linear
   issue. Rework clusters (`REWORK_MANIFEST.md`) become Linear **sub-issues**.
5. The issue closes when the verifier passes and the PR merges; the durable rationale stays in
   `.ai-state/`, the human-facing trail stays in Linear, and the two are cross-linked by a
   stable identity bridge.

The factory gains a **shared, durable, multi-actor work surface** without sacrificing its
local-first, git-anchored core.

---

## 5. Approach — architecture

### 5.1 Two tiers, shipped in order

```
                          ┌─────────────────────────────────────────────┐
   TIER A (ship first)    │  Praxion pipeline / slash command / CI       │
   pull + command-driven  │        │  calls on demand                     │
   GA, local-first        │        ▼                                      │
                          │  Linear official MCP server (S1)  ◀──Bearer──┤  per-project secret
                          │   find/create/update issue|project|comment   │
                          └─────────────────────────────────────────────┘
                                           ▲   ▲
            identity bridge: Linear issue ─┘   └─ ADR / td / PR back-links

                          ┌─────────────────────────────────────────────┐
   TIER B (later, opt-in) │  Self-hosted Praxion-Linear dispatcher        │
   push + agent, self-host│   (OAuth app, actor=app; webhook endpoint)    │
   pending Agent API GA   │        ▲ AgentSessionEvent (created/prompted)  │
                          │        │                                      │
                          │   Linear workspace ──delegate issue──▶ agent  │
                          │        ▲ AgentActivity (thought/action/resp)  │
                          └─────────────────────────────────────────────┘
```

### 5.2 The identity bridge (the keystone)

The single most important design element: a **stable correlation key** linking the three
identity spaces.

```
Linear issue identifier (e.g. ENG-123)
        │  1:1
        ▼
Praxion task slug (kebab-case, e.g. linear-eng-123-rate-limit)   ← drives .ai-work/<slug>/
        │  1:N
        ▼
Pipeline artifacts (.ai-work/<slug>/*) + ADRs (dec-NNN) + td-NNN + branch/PR
```

- The Linear issue **identifier** becomes the durable handle; the **task slug** is derived from
  it (so `.ai-work/<slug>/` and the worktree branch are traceable back to the issue and vice
  versa). *(DESIGN — extends the existing "task slug propagation" contract in
  `swe-agent-coordination-protocol.md`.)*
- Store the mapping in a small, committed, per-project file — e.g.
  `.ai-state/linear/issue_map.jsonl` (append-only, merge-driver-friendly like
  `observations.jsonl`) — so the link survives across sessions and machines and rides git, the
  sole substrate. *(DESIGN.)*
- Chronograph spans gain an optional `linear.issue.id` / `linear.session.id` attribute, so
  observability traces are filterable by Linear issue (mirrors the existing
  `praxion.git.branch` attribute pattern). *(DESIGN.)*

### 5.3 Where Linear touches the pipeline (stage-by-stage)

| Praxion stage / artifact | Linear interaction | Tier |
|---|---|---|
| **Intake Clarity Gate / `TASK_BRIEF.md`** | Read issue + `promptContext` + `guidance` → seed intent/signals | A (read), B (delegated) |
| **promethean `idea_ledgers/`** | Push accepted ideas as Linear issues (triage state) | A |
| **roadmap-cartographer `ROADMAP.md`** | Map roadmap items → Linear **projects/initiatives**; milestones → cycles | A |
| **systems-architect ADRs (`dec-NNN`)** | Back-link ADR to the issue (comment/link); never copy rationale (respects `dec-021`) | A |
| **Phase transitions** (research→arch→plan→impl→verify) | Status mirror: comment (A) or `AgentActivity` `thought`/`action` (B) | A / B |
| **verifier `REWORK_MANIFEST.md`** | Each rework cluster → Linear **sub-issue**; `td-NNN` linkage | A |
| **TECH_DEBT_LEDGER (`td-NNN`)** | Optionally surface `defer-with-rationale` rows as Linear backlog issues | A |
| **PR / merge** | Link PR to issue; close/advance issue on verifier-pass + merge | A / B |
| **Conversation Checkpoints** | `elicitation` activity (B) when the agent needs a human decision | B |

This is a **mapping, not a merge**: each field has exactly one owner (see §6) to prevent
bidirectional drift.

### 5.4 Tier B dispatcher shape (when built)

Following the autofix brief's per-project-ownership discipline and Linear's sample (TS SDK +
Cloudflare Workers): a **small, operator-owned, self-hosted** OAuth app that:

1. Receives `AgentSessionEvent` webhooks (signature-verified via `LinearWebhookClient`).
2. Acks within 5s (`thought` activity), then dispatches a Praxion pipeline run **headlessly**
   (e.g. `claude --bg` / `cursor-agent` / `codex` — the same headless-dispatch muscle the
   autofix brief is already designing) against the mapped repo + task slug.
3. Streams phase transitions back as `AgentActivity`s; surfaces Conversation Checkpoints as
   `elicitation`s; posts the final PR link as a `response`.

Crucially, **the fix/build logic stays in the Praxion pipeline** — the dispatcher is a thin
adapter, exactly as the autofix brief insists the agent logic live in the per-repo workflow, not
the central service. This keeps Tier B from becoming a second, divergent execution stack.

---

## 6. Sync model & source-of-truth ownership

To avoid the classic two-system drift, every synced field has **one** authoritative owner and a
**direction**:

| Field | Owner (source of truth) | Sync direction | Notes |
|---|---|---|---|
| Issue title / description / intent | **Linear** | Linear → Praxion | Read at intake; Praxion never overwrites |
| Workflow status (Todo/In-Progress/Done) | **Linear** display, **Praxion** drives transitions | Praxion → Linear | Pipeline phase → status mapping |
| Assignment / ownership | **Linear** (human is assignee; Praxion is `delegate`) | Linear → Praxion | Matches Linear's delegate model |
| Pipeline progress / phase notes | **Praxion** | Praxion → Linear (comment/activity) | Append-only; never the system of record for *decisions* |
| ADR rationale | **Praxion** (`.ai-state/decisions/`) | link only (no copy) | Honors `dec-021` "never duplicate ADR rationale" |
| Tech debt | **Praxion** (`TECH_DEBT_LEDGER.md`) | optional Praxion → Linear backlog | `td-NNN` remains canonical |
| Roadmap structure | **Linear** (projects/initiatives) ⇄ `ROADMAP.md` | bidirectional-by-convention, reconciled by cartographer | Cartographer regenerates; Linear holds the living state |

**Conflict policy (DESIGN):** last-writer-per-field within its owned direction; never a
field-level two-way merge. The `issue_map.jsonl` records last-synced revisions so a sync command
can detect and *report* (not silently resolve) divergence — matching Praxion's "surface, don't
silently fix" stance.

---

## 7. Per-project installable design

Mirrors Praxion's existing dual-source canonical-block + `/onboard-project` pattern so the
feature is **opt-in, idempotent, version-pinned, and dogfooded by Praxion first**.

### 7.1 New onboarding phase

Add **Phase 8f — Linear integration** to `commands/onboard-project.md` (and mirror in
`new-project.md`), slotting beside the other opt-in 8x phases (8b AaC, 8c ML, 8d Obsidian, 8e
code-quality). *(VERIFIED these phases exist; 8f is the natural next sibling.)* It would, when
opted in:

1. Write the **per-project MCP config** wiring `https://mcp.linear.app/mcp` into the
   project's assistant config (the same place `task-chronograph`/`likec4` are wired — `plugin.json`
   `mcpServers` for the plugin; `.cursor`/`.codex` equivalents for those assistants).
2. Write a **per-project policy file** `.ai-state/linear/config.yaml` (committed): which team(s),
   default project/initiative, which pipeline phases mirror to Linear, status mapping, sync mode
   (read-only / write-back / full), and Tier (A only by default).
3. Create the empty `.ai-state/linear/issue_map.jsonl` with a merge-driver entry (reuse the
   `observations.jsonl` semantic merge-driver pattern from Phase 3).
4. **Print** (never auto-inject) the secret-setup instructions — how to create a Linear API key /
   OAuth app and set `LINEAR_API_KEY` per the operator's secret store (mirrors the autofix brief's
   "instruct, never inject" secrets discipline; honors the personal `create_dotenv.sh` convention).
5. Add a `## Linear Integration` CLAUDE.md block (canonical-block sourced, sync-checked by
   `scripts/sync_canonical_blocks.py`) describing the issue↔slug bridge and the sync conventions.

### 7.2 New ecosystem components

| Component | Kind | Purpose |
|---|---|---|
| `linear-integration` | **Skill** (progressive disclosure) | How to map issues↔slugs, the MCP tool surface, sync conventions, status mapping; references for GraphQL fallback and the Tier-B dispatcher |
| `/linear` (e.g. `/linear-pull`, `/linear-sync`, `/linear-status`) | **Command(s)** | Pull an issue into a pipeline; push status; reconcile the map |
| `linear-sync-conventions` | **Rule** (path-scoped to `.ai-state/linear/**`) | Source-of-truth field ownership, conflict policy, what never to copy (ADR rationale) |
| `claude/canonical-blocks/linear-integration.md` | **Canonical block** | The shipped CLAUDE.md block (dual-source, sync-checked) |
| Tier-B dispatcher | **Self-hosted adapter** (separate, opt-in) | OAuth app + webhook → headless Praxion dispatch; **not** shipped into managed repos by default |

This is a **standard Praxion feature shape** — skill + command + rule + canonical block +
onboarding phase + optional MCP wiring — so it composes with everything already there and needs
no new architectural primitives for Tier A.

### 7.3 Dashboard surface (optional, later)

The read-only Next.js dashboard could gain a "Linear" surface rendering the `issue_map.jsonl` +
live MCP reads (issue status alongside the pipeline state for the same slug). Read-only, no new
persistence — consistent with the dashboard's existing design. *(DESIGN.)*

---

## 8. Security model

Treat per the autofix brief's adversarial discipline:

- **Least privilege.** Tier A with a **read-only restricted API key** for projects that only
  pull; a write-scoped key only where write-back is enabled. *(Linear supports restricted/
  read-only keys — VERIFIED.)*
- **Per-project secrets, operator-provisioned.** Never auto-inject; `/onboard-project` prints
  setup steps. Each repo owns its own credential (no central token), matching per-project
  ownership.
- **Tier B = OAuth app, `actor=app`, no `admin` scope** *(VERIFIED constraint)*; webhook
  signature verification mandatory (`LinearWebhookClient`); the delegate-not-assignee model keeps
  a human owner on every issue.
- **Prompt-injection surface.** A Linear issue body/comment is *untrusted input* that flows into
  an agent prompt (especially Tier B's `promptContext`). Map to the `agent-failure-taxonomy`
  (XPIA / tool-abuse / excessive-agency) and apply `agent-runtime-guardrails`: the agent must not
  treat issue text as instructions to exfiltrate secrets or push unreviewed code; HITL gates
  (Conversation Checkpoints) bound autonomy. *(DESIGN, mapped to existing Praxion skills.)*
- **Blast radius.** Tier A's worst case is a bad write to Linear (recoverable). Tier B adds a
  network-reachable endpoint — hence the self-host + GA gate.

---

## 9. Risks, caveats, open questions

| # | Risk / caveat | Severity | Mitigation |
|---|---|---|---|
| R1 | **Agent API is Developer Preview** — "may change before GA" *(VERIFIED)* | High (Tier B only) | Gate Tier B on GA; ship Tier A (GA MCP) first |
| R2 | **Hosted endpoint conflicts with local-first / git-substrate ethos** | High | Quarantine to Tier B; opt-in, self-hosted; default is pull-only Tier A |
| R3 | **Two-source-of-truth drift** | Medium | Strict per-field ownership (§6); divergence is *reported*, never silently merged |
| R4 | **Secret sprawl across N managed repos** | Medium | Per-project, operator-provisioned, least-privilege keys; instruct-don't-inject |
| R5 | **MCP tool surface may not cover every op** (custom fields, cycles, bulk) | Low | GraphQL (S2) surgical fallback, documented in the skill's references |
| R6 | **Responsiveness SLAs (5s/10s)** for Tier B | Medium (Tier B) | Dispatcher acks immediately (`thought`) then runs the pipeline async |
| R7 | **Single-developer reality vs. team tool** — is the durable backlog worth it for solo Praxion? | Low | Dogfood Tier A on Praxion itself first; value is the *durable + roadmap-linked* backlog even solo; abandon if it adds ceremony without payoff |

**Open questions (resolvable only by a prototype / Linear's roadmap):**

- Q1. Exact MCP tool catalog & rate limits at `mcp.linear.app/mcp` (enumerate during a spike).
- Q2. Does the MCP server expose initiatives/cycles richly enough for the roadmap mapping, or is
  GraphQL needed there?
- Q3. Tier-B headless dispatch latency vs. the 10s first-activity SLA under real pipeline cold-start.
- Q4. Whether `guidance` (workspace/team instructions) can carry enough to replace a chunk of the
  Intake Clarity Gate or merely augment it.

---

## 10. Phased roadmap

Each phase is independently shippable; flags mark spike vs. known.

- **Phase 0 — Spike (timeboxed):** wire `mcp.linear.app/mcp` into a Praxion dev session with a
  read-only key; enumerate the actual MCP tool surface and rate limits (resolves Q1/Q2). Decision
  recorded in `LEARNINGS.md`. *(Spike.)*
- **Phase 1 — Tier A read-path (known):** `linear-integration` skill + `/linear-pull` command +
  the identity bridge (`issue_map.jsonl`) + intake seeding from a Linear issue. Dogfood on
  Praxion's own work. No write-back yet.
- **Phase 2 — Tier A write-back (known):** phase-transition status mirroring (comments), ADR/PR
  back-links, `linear-sync-conventions` rule, `/linear-sync` + `/linear-status`. Source-of-truth
  ownership enforced.
- **Phase 3 — Onboarding install (known):** Phase 8f in `/onboard-project` + `/new-project`,
  canonical block, secrets-instructions, per-project policy file. Now installable into any
  managed project.
- **Phase 4 — Ecosystem mapping (known):** promethean ideas → issues; roadmap-cartographer ↔
  projects/initiatives; rework clusters → sub-issues; optional dashboard surface.
- **Phase 5 — Tier B (gated on Agent API GA; partly spike):** self-hosted OAuth-app dispatcher,
  delegation → headless pipeline, `AgentActivity` streaming, `elicitation` for Conversation
  Checkpoints. Opt-in, operator-owned.

---

## 11. ADR seeds

Two load-bearing decisions a `systems-architect` should formalize:

1. **`dec-XXX` — Linear integration via official MCP, consumption-first (Tier A) before
   agent-first (Tier B).**
   - *Decision:* Adopt Linear's GA remote MCP server as the primary integration; treat the
     Developer-Preview Agent API as a later, opt-in, self-hosted tier.
   - *Disconfirmation:* **Falsifier** — if the MCP tool surface proves too thin for the core
     issue↔slug↔status loop (Phase 0 spike fails). **Steelmanned runner-up** — go straight to the
     Agent API for the full native experience (rejected now: Developer Preview + hosted-endpoint
     tension). **Reversal trigger** — Agent API reaches GA *and* a managed project needs real-time
     delegation; revisit Tier B priority.

2. **`dec-YYY` — Source-of-truth split between Linear (intent/status) and Praxion (process/
   rationale), with per-field ownership and no bidirectional field merge.**
   - *Decision:* §6's ownership table; ADR rationale is *linked never copied* (honors `dec-021`).
   - *Disconfirmation:* **Falsifier** — observed drift that the report-don't-merge policy can't
     keep tolerable. **Steelmanned runner-up** — make Linear the single source of truth for work
     items and demote `.ai-work`/`.ai-state` (rejected: breaks local-first + git-substrate).
     **Reversal trigger** — a future where teams work primarily in Linear and rarely touch the repo
     directly.

---

## 12. Verification & sources

Claims are tagged inline: **VERIFIED** (Linear primary docs, accessed 2026-06-24),
**SINGLE-SOURCE**, **ASSUMPTION**, **DESIGN** (proposed here, not yet built).

Primary sources (all Linear official, accessed 2026-06-24):
- MCP server — https://linear.app/docs/mcp
- Agents getting started — https://linear.app/developers/agents
- Agent interaction — https://linear.app/developers/agent-interaction
- SDK webhooks — https://linear.app/developers/sdk-webhooks

Praxion internal grounding (verified against the repo at analysis time):
- Pipeline & tiers — `rules/swe/swe-agent-coordination-protocol.md`
- Architecture & components — `docs/architecture.md`
- Observability (chronograph ≠ task tracker) — `docs/observability.md`
- MCP wiring pattern — `.claude-plugin/plugin.json`
- Onboarding phases & canonical-block dual-source — `commands/onboard-project.md`,
  `claude/canonical-blocks/`
- Per-project-ownership / instruct-don't-inject-secrets discipline —
  `tmp/cursor-ci-autofix-research-brief.md` (the in-flight sibling effort this design deliberately
  mirrors)

> **Definition of done for this analysis:** a `systems-architect` can render `dec-XXX` and
> `dec-YYY` from §11, and an `implementation-planner` can decompose Phases 0–3 (§10) into steps,
> with no remaining "we'd need to research X" gaps except the four prototype-only open questions
> in §9.

---

## 13. Per-artifact storage-backend abstraction (which `.ai-state` artifacts go to Linear, and how)

This section answers a sharper follow-up question: *which persistent, metadata-carrying
`.ai-state` artifacts should be storable in Linear instead of / in addition to the file system,
chosen per-project by configuration, with deterministic push/pull?* The motivating example —
the tech-debt ledger and **its real resolved counterpart `TECH_DEBT_RESOLVED.md`** — turns out
to be the **ideal first candidate.**

### 13.1 Which artifacts are "Linear-shaped" (ranked by fit)

The discriminator is shape: **a Linear issue is an *item* with a stable id, a *status lifecycle*,
and *metadata*.** Artifacts with that shape map cleanly; snapshots and telemetry do not.

| `.ai-state` artifact | Shape | Natural Linear object | Fit |
|---|---|---|---|
| **`TECH_DEBT_LEDGER.md` + `TECH_DEBT_RESOLVED.md`** (`td-NNN`) | Item + status (`open`/`in-flight`/`resolved`/`wontfix`) + 14-field metadata + stable `dedup_key`; two-file pair = active/closed boards | **Issue** (active ledger → open/in-progress; resolved file → done/canceled) | **Ideal — ship first** |
| **`idea_ledgers/IDEA_LEDGER_*.md`** (promethean) | Speculative work items | **Issue** in a Triage/Backlog state | **Strong — second** |
| `decisions/` ADRs (`dec-NNN`) | Decisions with status (`proposed`/`accepted`/`superseded`) + rationale | **Document** or **Project**, *not* an issue | Weak as an issue; link, don't mirror (honors `dec-021`) |
| `REWORK_MANIFEST.md` (`rw-…`, ephemeral in `.ai-work/`) | Defect clusters | **Sub-issue** of the parent issue | Transient only — born and dies inside a pipeline |
| `calibration_log.md`, `observations.jsonl`, `sentinel_reports/`, `metrics_reports/`, `skill_genesis_reports/` | Append-only logs / timestamped snapshots | (Update / report at most) | **No** — keep in `.ai-state`; not item-shaped |

### 13.2 Why the tech-debt ledger pair is the ideal first candidate

1. **It is already an issue in all but name** — stable `td-NNN`, a four-value status lifecycle, an
   owner-role, severity, location, source, first/last-seen dates. *(VERIFIED — schema in
   `skills/software-planning/references/tech-debt-ledger.md`.)*
2. **The two-file pair already maps to two boards** — `TECH_DEBT_LEDGER.md` holds
   `status ∈ {open, in-flight}` (active board); `TECH_DEBT_RESOLVED.md` holds
   `{resolved, wontfix}` (done/canceled). Linear's workflow states model this natively.
3. **`dedup_key` is a ready-made stable external correlation key** —
   `sha1(class|location|direction|goal-ref-type|goal-ref-value)[:12]`. It already survives
   line-range/path-order churn and the LEDGER↔RESOLVED migration. *(VERIFIED.)*
4. **A deterministic finalize step already exists** — `scripts/finalize_tech_debt_ledger.py` runs
   inside the git finalize-hook chain on any on-main commit (dedup, status-precedence collapse,
   migrate-resolved). A Linear sync step **chains right after it**, reusing a proven pattern
   (idempotent, advisory `fcntl` lock, dry-run). *(VERIFIED — `scripts/git-finalize-hook.sh`,
   `finalize_chain.sh`.)*

### 13.3 Field mapping (`td` row → Linear issue)

| `td` field | Linear field | Notes |
|---|---|---|
| `dedup_key` | (external id / sidecar map key) | The join key; **not** shown as content |
| `id` (`td-NNN`) | issue title prefix / label | Keeps the Praxion handle visible |
| `notes` (summary) | title + description | First sentence → title; full notes → description |
| `status` | workflow state | `open→Backlog`, `in-flight→In Progress`, `resolved→Done`, `wontfix→Canceled` (configurable) |
| `severity` | priority | `critical→Urgent`, `important→High`, `suggested→Low` |
| `class`, `source`, `direction` | labels | e.g. `class:complexity`, `src:sentinel` |
| `owner-role` | label (or team) | Praxion role, not a Linear human |
| `location` | description / link | File paths (+ optional repo links) |
| `goal-ref-type`/`-value` | description / link | `dec-NNN` → link to the ADR |
| `first-seen` / `last-seen` | createdAt (display) / description | Linear owns its own timestamps |
| `resolved-by` | link (PR/commit/ADR) on close | |

### 13.4 The per-project configuration

A committed `.ai-state/linear/config.yaml` selects the backend **per artifact class** (so the
same machinery generalizes from the td-ledger to idea-ledgers later without re-architecting):

```yaml
artifacts:
  tech_debt_ledger:
    backend: both          # file | linear | both
    canonical: file        # in "both" mode, which side wins a conflict (default: file)
    linear:
      team: ENG
      project: "Tech Debt"
      status_map:  { open: Backlog, in-flight: "In Progress", resolved: Done, wontfix: Canceled }
      severity_map:{ critical: Urgent, important: High, suggested: Low }
  idea_ledger:
    backend: file          # not yet mirrored
```

- **`backend: file`** — today's behavior, unchanged. Sync is a no-op.
- **`backend: linear`** — Linear is the store; the `.ai-state` file becomes a generated cache.
  *(Discouraged for Praxion's local-first ethos — breaks offline + git-substrate; offered for
  completeness / team-heavy projects.)*
- **`backend: both`** — recommended: **the `.ai-state` file stays canonical** (git remains the
  sole substrate, offline-safe, mergeable), **Linear is a projection/mirror.**

### 13.5 Source-of-truth in `both` mode (keeps local-first intact)

- **File is canonical, Linear is a mirror.** Push reconciles file → Linear; pull imports
  Linear-side changes back into the file. Never a field-level two-way merge.
- **Correlation via a sidecar, not a new column.** Store the `dedup_key → linear_issue_id` map in
  `.ai-state/linear/issue_map.jsonl` (append-only, semantic-merge-driver, like `observations.jsonl`).
  This keeps the ledger schema **backend-agnostic** (no Linear leakage into the canonical 14-field
  table), survives the LEDGER↔RESOLVED migration (keyed on `dedup_key`, not file location), and is
  re-keyed when a producer recomputes `dedup_key` on reclassification. *(DESIGN.)*
- **Push direction (file → Linear):** create issue for a new `dedup_key`; update title/labels;
  transition state on `status` change; move to Done/Canceled when the row migrates to
  `TECH_DEBT_RESOLVED.md`; re-open on recurrence (matches the ledger's own re-open semantics).
- **Pull direction (Linear → file):** a human flips a mirrored issue's state → reflect the
  `status` change in the file on next sync; a human files a *new* debt issue in Linear → import it
  as a new `td-NNN` via the existing **orchestrator** writer path (preserving the four-writer rule
  — Linear is an intake surface, not a fifth writer). *(DESIGN.)*
- **Conflict policy:** divergence (both sides changed the same field since last sync) is
  **reported, never silently merged** — consistent with Praxion's surface-don't-fix stance. The
  `issue_map.jsonl` records last-synced revisions to detect it.

### 13.6 The mechanism — refining the "hooks" instinct

The instinct (*"hooks, so push/pull is deterministic"*) is right about **determinism** but needs
one correction about **which** hooks and **where the network call lives**:

- **The deterministic, git-anchored substrate is the existing finalize hook chain** — but a git
  hook **must never block a commit on a network call**. So the git hook's role is **detect +
  enqueue only**: after `finalize_tech_debt_ledger.py` runs, a sibling step writes pending changes
  to a local **outbox** (`.ai-state/linear/outbox.jsonl`) and exits 0 unconditionally. Fully
  offline, never fails a commit. *(DESIGN, mirrors the chain's existing exit-0 discipline.)*
- **The authoritative network push/pull lives where secrets + network already live: CI** — a
  post-merge-on-`main` GitHub Actions job (and/or an on-demand `/linear-sync` command) drains the
  outbox and reconciles. This is the *same* "secrets live in the CI context, not the local/PR
  context" lesson the autofix brief draws — and it keeps local commits fast and offline.
- **Claude Code agent-lifecycle hooks** (`Stop`, `PostToolUse`) are best-effort and
  assistant-specific → **not** the deterministic substrate. They are fine as an optional *nudge*
  ("you resolved a td row — run `/linear-sync`"), nothing more.

```
 on-main commit ──► git finalize-hook chain
                      ├─ finalize_tech_debt_ledger.py   (existing: dedup, migrate-resolved)
                      └─ enqueue_linear_sync.py          (NEW: write deltas → outbox.jsonl, exit 0, OFFLINE)
                                                              │
 CI post-merge / `/linear-sync` ──► sync_tech_debt_linear.py  ◄┘  (NEW: --push/--pull/--reconcile,
   (has LINEAR_API_KEY + network)        │                          idempotent, advisory lock, dry-run,
                                          ▼                          modeled on finalize_tech_debt_ledger.py)
                              Linear MCP (S1) / GraphQL (S2)
```

### 13.7 Generalization

Define a tiny `LedgerBackend` protocol — `pull()`, `push(rows)`, `reconcile()` — with three
implementations: `FileBackend` (no-op sync, today's behavior), `LinearBackend`, and
`DualBackend` (file canonical + Linear mirror). `config.yaml` selects per artifact class. The
td-ledger is the reference implementation; idea-ledgers (and any future item-shaped ledger) adopt
the same protocol without new architecture. *(DESIGN.)*

This slots cleanly under §10's roadmap: it is the concrete first payload of **Phase 2 (Tier A
write-back)**, with the read/import half belonging to **Phase 4 (ecosystem mapping)**.
