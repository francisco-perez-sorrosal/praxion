---
id: dec-draft-7461de95
title: Nebius integrated as the first v2 direct dispatch adapter plus a managed/self-hosted inference target
status: proposed
category: architectural
date: 2026-06-06
summary: Add Nebius AI Cloud to Praxion's neocloud surface as a dedicated `nebius-direct` dispatch backend (mirroring `runpod-direct`, the first of dec-118's anticipated v2 direct adapters) and as an actionable inference target in the deployment skill — managed Token Factory API plus self-hosted vLLM on MK8s / GPU VM. SkyPilot `cloud: nebius` is retained as the documented low-friction fallback.
tags: [ml-training, neo-cloud, nebius, deployment, direct-adapter, inference, token-factory]
made_by: agent
agent_type: systems-architect
branch: worktree-nebius-neocloud
pipeline_tier: full
affected_files:
  - skills/neo-cloud-abstraction/references/nebius-direct-adapter.md
  - skills/neo-cloud-abstraction/SKILL.md
  - skills/neo-cloud-abstraction/references/skypilot-backend.md
  - skills/neo-cloud-abstraction/README.md
  - commands/run-experiment.md
  - skills/deployment/references/ai-native-platforms.md
  - skills/deployment/references/nebius-token-factory.md
  - .ai-state/SYSTEM_DEPLOYMENT.md
affected_reqs: []
---

# ADR — Nebius as a direct dispatch adapter and an inference target

## Context

A user needs Praxion to manage Nebius AI Cloud end-to-end for an imminent hackathon: dispatch GPU
training/compute jobs to Nebius **and** deploy services/inference there. Praxion already has both homes
— the `neo-cloud-abstraction` skill (training-job dispatch) and the `deployment` skill's
`ai-native-platforms.md` (serving patterns) — but Nebius was only *named* in each, not actionable: the
SkyPilot backend listed Nebius as a passthrough provider with no setup recipe, and `ai-native-platforms.md`
carried Nebius prose with no deploy recipe (unlike Modal/CoreWeave/RunPod, which ship working code).

`dec-118` (tiered backend strategy) already anticipated this exact extension — "v2 direct adapters
(Lambda/Crusoe/CoreWeave) follow the same opt-in pattern: a skill reference + integration recipe; the
vendor ships the tooling." This decision builds the **first** such v2 adapter (Nebius), and extends the
deployment skill in parallel for the serving half of the request.

Research (2026-06-06, live-doc verified) established: Nebius is a first-class SkyPilot cloud (spot, B200,
InfiniBand landed by SkyPilot 0.10.1); the `nebius` CLI exposes the full compute-instance lifecycle
(`create/get/list/start/stop/delete` + `gpu-cluster` for InfiniBand); and Nebius Token Factory provides a
hosted, OpenAI-compatible inference API (`https://api.tokenfactory.nebius.com/v1/`, `NEBIUS_API_KEY`,
$/token), with a fine-tune → auto-host loop on 30+ open models.

## Decision

1. **Dispatch:** add `backend: nebius-direct` to the neo-cloud abstraction — a dedicated direct adapter
   that maps the invariant 8-operation lifecycle onto the `nebius` CLI (provision-VM + SSH, RunPod-style),
   with a GPU-type → platform/preset map, `gpu-cluster` InfiniBand for `H100:8`/`H200:8`, and S3-compatible
   Object Storage / `scp` artifact fetch. The adapter shells out to the **CLI, not the raw pysdk** (the
   CLI's compute verbs are documented and stable; the pysdk compute-create surface is thin in published
   examples). The `training_job_descriptor` gains `H200`/`B200` to the `gpu_type` enum (additive,
   non-breaking per dec-118).
2. **Serving:** make the existing Nebius entry in `ai-native-platforms.md` actionable with three recipes,
   framed as *managed model API* vs *bring-your-own-GPU serving*: **Token Factory** (managed serverless
   inference, OpenAI-compatible) as the headline; **MK8s + vLLM** (self-hosted K8s); **GPU VM + vLLM**
   (simplest self-hosted, reusing the `nebius-direct` provisioning path).
3. **Fallback retained:** SkyPilot `cloud: nebius` stays documented in `skypilot-backend.md` as the
   lower-friction first step before committing to `nebius-direct`.

Praxion ships recipes, not infrastructure — no Praxion-authored MCP server or SDK wrapper for Nebius.

## Considered Options

### Option 1 — Nebius via SkyPilot provider-pin only (no direct adapter)

Add an optional `cloud:` pin to the SkyPilot backend; Nebius becomes `backend: skypilot` + `cloud: nebius`.

- **Pros:** near-zero new code; spot/B200/InfiniBand free via SkyPilot; SkyPilot tracks Nebius API drift
  upstream; the prior `RESEARCH_FINDINGS.md` recommended this for a hackathon timeline.
- **Cons:** no native control over the exact VM/cluster lifecycle; another dependency in the path; does not
  match the `runpod-direct` precedent for a committed provider.

### Option 2 — Dedicated `nebius-direct` adapter (chosen for dispatch)

A first-class direct backend mirroring `runpod-direct`.

- **Pros:** native VM/cluster control; matches dec-118's anticipated v2 pattern; no SkyPilot indirection;
  direct InfiniBand `gpu-cluster` orchestration.
- **Cons:** Praxion owns the Nebius CLI-drift surface; more recipe surface to maintain; a hand-rolled
  provision/poll/teardown lifecycle is more brittle than SkyPilot's managed one.

### Objection on record (behavioral contract — Register Objection)

The prior research recommended Option 1 for the hackathon (lower risk; raw SDK compute examples were
`[UNVERIFIED]`). The user chose Option 2 for control and commitment to Nebius — a legitimate call that
matches the existing `runpod-direct` precedent. Two mitigations are baked in: the adapter uses the
**verified CLI** rather than the unverified raw SDK, and **Option 1 is retained as the documented
fallback** (`cloud: nebius`) so the low-friction path is never lost.

## Consequences

**Positive:**
- Nebius is managed end-to-end: `/run-experiment` dispatches to it; the deployment skill serves on it.
- Token Factory closes the loop — train on Nebius GPUs (`nebius-direct`), then serve fine-tunes on the
  managed OpenAI-compatible endpoint.
- Establishes the concrete template for the remaining dec-118 v2 adapters (Lambda/Crusoe/CoreWeave).

**Negative:**
- Praxion now owns Nebius CLI/API-drift in the adapter recipe (mitigated by staleness markers +
  `last-verified` dates; sentinel tracks the drift-prone sections).
- Static pricing table in the adapter (`pricing_query()`) needs periodic refresh against nebius.com/prices.

**Neutral:**
- The `gpu_type` enum and lifecycle protocol remain backward-compatible; the additive `H200`/`B200`
  values do not affect existing backends.
