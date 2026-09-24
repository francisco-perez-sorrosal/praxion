---
id: dec-draft-2a6891c5
title: Retire context-hub and the external-api-docs skill; fold a provider-neutral current-docs protocol into software-planning
status: proposed
category: architectural
date: 2026-09-24
summary: "Deletes the external-api-docs skill, its docs page and every context-hub (chub) install path. The methodology that never depended on chub is folded into one ~35-line section, software-planning/references/cross-agent-skill-conventions.md § Current docs for external APIs: source order (official docs, llms.txt/.md first, via WebFetch or else a bounded Bash curl), version-drift detection, token hygiene, trust, and mismatches recorded in LEARNINGS.md in place of chub_feedback. The tool-neutral always-loaded rule line carries the trigger and pointer and reaches all 17 agents; agent skill preloads are dropped, and WebFetch (not WebSearch) is granted to the five agents that fetch in their own phase. Retires dec-001 and dec-348, narrows dec-053's mechanism clause, and moves the orphaned webhooks reference into api-design-craft."
tags: [context-hub, external-api-docs, skills, retirement, current-docs-protocol, token-budget, onboarding, webhooks, agents]
made_by: agent
agent_type: systems-architect
branch: worktree-remove-chub
pipeline_tier: standard
affected_files:
  - skills/software-planning/references/cross-agent-skill-conventions.md
  - skills/software-planning/SKILL.md
  - rules/swe/swe-agent-coordination-protocol.md
  - agents/researcher.md
  - agents/systems-architect.md
  - agents/implementation-planner.md
  - agents/implementer.md
  - agents/test-engineer.md
  - agents/cicd-engineer.md
  - agents/agentic-transactions-architect.md
  - skills/onboard-project/references/seed-pipeline.md
  - scripts/onboard-project
  - claude/canonical-blocks/hackathon-mode.md
  - skills/api-design-craft/references/webhooks.md
affected_reqs: [REQ-01, REQ-02, REQ-03, REQ-04, REQ-05, REQ-11, REQ-12, REQ-13, REQ-14]
supersedes_in_part: [dec-053]
dissent: "A one-line pointer inside ~16.6k tokens of always-loaded text may trigger less reliably than a skill whose description auto-matches external-API work — the ~5.2k-token preload may have been buying real verification behavior, not just ceremony."
---

## Context

context-hub (`@aisuite/chub`) has been dormant since mid-2026:

- last npm release 0.1.4 on 2026-04-27
- last push to `main` on 2026-05-31
- 141 open issues, with contributor PRs closed unmerged

Praxion integrated it at three levels:

- **The skill.** `skills/external-api-docs/` was preloaded by 10 of the 17 agents, at about 5.2k tokens per spawn.
- **Installers.** A global npm package, `~/.chub/config.yaml`, and an MCP entry in `~/.claude.json` and Cursor's `mcp.json`.
- **Onboarding.** The seed pipeline's SDK discovery (dec-053's "discovery hook"), the Phase 7 companion-CLI table, the seed allowlist, and the hackathon block.

A survey of alternatives (Context7, vendor-official docs MCPs, DeepWiki, the `llms.txt` convention, the now-archived `mcpdoc`) found no replacement that is at once general-purpose, free, open and trustworthy. The best general mechanism is plain `WebFetch` against official docs, preferring `llms.txt` / `.md` page variants. That is a *convention*, not a component.

Most of the skill never depended on chub:

- when to check
- the fallback order
- API version-drift detection
- token hygiene

A reach defect was also found. `cross-agent-skill-conventions.md` claimed to be "loaded by `software-planning`" and made "the agent's skill list the enforcement surface". But `software-planning/SKILL.md` never linked it, and 6 of the 10 preloading agents do not preload `software-planning` at all. Only the always-loaded rule line reached every agent.

## Decision

1. **Remove** the following:
   - `skills/external-api-docs/` (SKILL.md, README.md, `references/context-hub.md`, `references/mcp-setup.md`, `references/upstream-skill.md`)
   - `docs/external-api-docs.md`
   - every chub install path in `install.sh`, `install_claude.sh`, `install_cursor.sh` and `cursor/config/`

   Transitional cleanup of existing installs is decided separately in dec-draft-218ce4c9.
2. **Fold** the provider-neutral methodology into `skills/software-planning/references/cross-agent-skill-conventions.md § Current docs for external APIs` (anchor `#current-docs-for-external-apis`), about 35 lines covering:
   - when to check
   - source order: official docs (`llms.txt`/`.md` first) via `WebFetch`, or a bounded Bash `curl` where `WebFetch` is absent (see item 7) → a user-configured vendor-official docs MCP → official repo/changelog → `WebSearch` → introspecting the installed package → training data labeled unverified
   - version-drift detection, flag format, priority, and where each agent records it
   - token hygiene
   - trust: fetched docs are data, not instructions
   - mismatches
3. **Reach** is delivered in three layers:
   - The always-loaded rule line in `swe-agent-coordination-protocol.md` carries the trigger and the pointer, and reaches all 17 agents. Its length must not exceed today's 454 bytes. It names no tool ("fetch `llms.txt`/`.md` pages first"), because it also reaches agents and non-Claude hosts that do not hold `WebFetch`. The mechanism lives only in the protocol.
   - The 7 agents with a phase-specific external-API obligation get one-line pointers straight to the protocol anchor.
   - `software-planning/SKILL.md` gains the missing link to that reference.

   All 10 `skills:` preloads of `external-api-docs` are removed.
4. **Replace `chub_feedback`** with recording doc/behavior mismatches in `LEARNINGS.md`. The next agent is the reader Praxion controls; upstream bugs already route to `/report-upstream`.
5. **Narrow dec-053's mechanism.** The seed pipeline discovers the current Claude Agent SDK / `uv` / FastAPI surface through the protocol, and its smoke-check recovery introspects the installed package and records the mismatch. The prompt-over-template principle is unchanged.
6. **Move** the orphaned `skills/external-api-docs/references/webhooks.md` (receiving side) to `skills/api-design-craft/references/webhooks.md`. There it cross-links `rest-patterns.md § Webhook Design` (sending side) and is wired into the skill's satellites, routing table and README.
7. **Fetch path, decided per agent.** Verification found that 6 of the 7 agents with a protocol obligation held neither `WebFetch` nor `WebSearch`. The chub path had worked through `Bash`, which every agent holds.
   - **`WebFetch` is added** to the five agents that fetch during their own phase: `systems-architect`, `implementer`, `test-engineer`, `cicd-engineer` and `agentic-transactions-architect`.
   - **`implementation-planner` gets nothing.** It *schedules* the verifying step and does not fetch.
   - **`WebSearch` stays researcher-only.** Open-ended discovery is the researcher's boundary. Agents without it skip rung 4 and recommend a researcher pass.
   - **Rung 1 carries a bounded Bash fallback** for agents without `WebFetch` and for hosts where `tools:` does not bind. The Codex export copies the frontmatter as text, and Cursor's `sub-agents` MCP does not enforce it. The fallback is `curl -sL --max-time 30 -o tmp/api-docs/<name>.md <url>`: GET only, no credentials, `llms.txt`/`.md`/plain-text URLs only, then Grep/Read the needed section.
   - **`WebFetch` callers ask for verbatim signatures**, because its extraction step paraphrases.

This decision's action removes the subject of **dec-001** (skill wrapper as the primary context-hub integration) and of **dec-348** (its re-affirmation). Both are therefore retired, per the Retirement protocol, on their own records.

## Considered Options

### Option 1: Rewrite `external-api-docs` provider-neutral in place (keep the name)

- (+) About 35 inbound see-also references and 10 preloads keep resolving, so the blast radius is small.
- (+) It keeps an auto-trigger by description match and a user-invocable `/external-api-docs`.
- (−) A skill whose only mechanism is "use `WebFetch` on official docs" is a wrapper around a built-in tool.
- (−) Keeping it preloaded keeps paying about 1.5k+ tokens per spawn on 10 agents. Un-preloading it recreates the reach gap, since the listing trigger alone is not a mandate.
- (−) The name promises a retrieval capability that no longer exists.

### Option 2: Delete, and scatter the methodology into several skills (`python-prj-mgmt`, `refactoring`, …)

- (+) Smallest new surface.
- (−) Drift detection would have no single home. Agents would receive contradictory fragments, and the always-loaded rule would have nothing coherent to point at.

### Option 3: Delete + fold into `cross-agent-skill-conventions.md` (chosen)

- (+) The protocol lives where cross-agent conventions already live, and where the always-loaded rule already points.
- (+) It is read on demand, so there is zero per-spawn cost.
- (+) It removes the Node/npm dependency and one listing entry.
- (−) The sweep is one-time but broad (about 60 files).
- (−) It loses the skill-description auto-trigger and the `/external-api-docs` entry point. The rule line is the replacement trigger.

### Option 4: Adopt Context7 as the replacement provider

- (−) Proprietary backend, with community content carrying an explicit accuracy/security disclaimer.
- (−) CVE-2026-75130 (CVSS 9.0, prompt injection).
- (−) Rate-limited free tier.
- (−) It re-creates the single-vendor coupling that this decision removes.

### Fetch-path sub-decision (Decision item 7)

1. **Grant `WebFetch` + `WebSearch` to all six agents.**
   - (+) Uniform.
   - (−) `WebSearch` erodes the researcher boundary and pulls results from arbitrary domains, which widens the injection surface.
   - (−) The planner gains a tool it never uses.
   - Adopted only narrowly: `WebFetch` alone, for five agents.
2. **Bash `curl` only, with no grants** (runner-up).
   - (+) Zero schema cost, host-neutral, and it works while the installed plugin is still stale.
   - (−) Vendors without `.md` variants return raw HTML: a token blow-up.
   - (−) Nothing summarizes the content between attacker-controlled bytes and the agent's context.
   - (−) Egress becomes a generic shell command rather than a per-domain `WebFetch` permission.
   - Kept as the bounded fallback rung.
3. **Delegate fetches to the researcher.**
   - (−) Subagents cannot spawn subagents, so every signature check would round-trip through the orchestrator.
   - Kept only as the escalation path that replaces rung 4 for agents without `WebSearch`.

## Consequences

**Positive**
- About 5.2k tokens saved per spawn of 10 agent types. This is an estimate (CONTEXT_REVIEW 19,634 B at 3.796 chars/token, which corroborates the 5,156-token figure). The always-loaded delta is ≤ 0 bytes, and the listing loses one skill description.
- No Node.js, npm or third-party MCP dependency remains for docs retrieval, and no telemetry or feedback flows to an external service.
- Reach improves: all 17 agents now receive the trigger, where previously only 4 preloaders had any path to the reference.
- The orphaned webhooks reference becomes reachable.
- Every agent with a protocol obligation can execute rung 1, with `WebFetch` where granted and Bash `curl` elsewhere. The protocol also works on Codex/Cursor exports, where `tools:` does not bind. The tool-neutral rule line measures 429 bytes and 104 tokens, down from 438 and 108.

**Negative**
- `WebFetch` adds an estimated ~300 schema tokens per spawn on five agent types. This is unmeasured and still well below the ~5.2k preload removed. The falsification path is `context_baseline.py` `first_turn` on implementer spawns before and after the plugin refresh.
- `WebFetch`'s extraction step can paraphrase a signature. The mitigation is to ask for verbatim quotes and to `curl` `.md` pages to a file when exact text matters.
- The `curl` fallback puts raw, unsummarized bytes into a file the agent reads. The injection surface is bounded by GET-only access, no credentials, plain-text URLs only, and the Trust rule "never pipe or execute".
- `tools:` grants reach users only after release plus a plugin refresh. Until then the `curl` rung carries the load.
- Users lose the `/external-api-docs` skill entry point. This is a user-facing breaking change and ships under a `BREAKING CHANGE` footer.
- Managed projects that are already onboarded keep the old hackathon block until their next onboard/promote re-sync.
- Retrieval quality now depends on each vendor's docs site; bot-blocked or JS-only sites fall to `WebSearch` and package introspection.
- Existing installs carry chub state until the transitional cleanup (dec-draft-218ce4c9) offers its removal.

## Disconfirmation

- **Falsifier.** Within about 90 days of release, verifier/LEARNINGS evidence shows agents writing integration code against training-data signatures at a *higher* rate than before (API-signature FAILs or mismatch entries citing unverified training data). Or major vendors' official docs turn out to be systematically unreachable via both `WebFetch` and `curl`. Or `LEARNINGS.md` mismatch entries trace coded signatures back to `WebFetch` paraphrases.
- **Steelmanned runner-up.** Option 1 (lean rewrite, about 1.5k tokens). It keeps a description-matched auto-trigger that fires exactly when external-API work starts, rather than relying on a one-line pointer diluted among about 16.6k tokens of always-loaded text. It also keeps every inbound link valid and preserves a user-invocable entry point that users of the hackathon wrapper already knew.
- **Reversal trigger.** Either of the following:
  - An open, free, curated, versioned docs service appears (or Claude Code ships native docs retrieval) that clears the trust bar context-hub was chosen for; then revisit a provider layer behind this protocol.
  - A measured L1 activation failure, i.e. sessions where external-API code was written with no fetch recorded in Sources and no "unverified" label.
  - For the fetch path only: signature mismatches traced to `WebFetch` paraphrase. Then make `curl`-to-file the primary route for `.md` URLs. Alternatively, a measured `WebFetch` schema cost that rivals the removed preload; then fall back to the `curl`-only runner-up.

## Prior Decision

**dec-053** (*Prompt-over-template discipline for greenfield project scaffolding*) is **narrowed, not replaced**. It stays `accepted`.

**Clauses narrowed** by this record:

- The "discovery hook" is no longer "the `external-api-docs` skill, which fetches current SDK docs from context-hub". It is now the provider-neutral current-docs protocol (`cross-agent-skill-conventions.md § Current docs for external APIs`).
- In the smoke-check recovery, "fall back to the alternate symbol surfaced by chub" becomes "re-fetch the official docs page and introspect the installed package". The `chub_feedback` down-vote becomes a mismatch entry in `LEARNINGS.md`.
- The Option C con "failures in chub … surface to the user" and the consequences "onboarding sessions exercise `external-api-docs` and chub feedback loops" and "a chub outage degrades the flow" now read as failures and outages of the vendor's docs site, degrading to `WebSearch` or introspection with the same clear diagnostic.

**Clauses that survive unchanged**:

- no code templates and no pinned SDK signatures
- prose specifications of structure and invariants
- run-time discovery before generating SDK-using code
- the import smoke check before writing source
- the mushi doc generated per run against real paths
- the canonical "What is Praxion?" paragraph as the only static text
