---
id: dec-draft-3abce869
title: Skip Cognee cognify(); use SearchType.CHUNKS only
status: proposed
category: architectural
date: 2026-04-25
summary: Hackathon demo skips Cognee's graph-build step and retrieves SkillRunEntry records via vector chunk similarity, eliminating the OpenAI dependency and reducing latency.
tags: [hackathon, cognee, llm-provider, single-provider]
made_by: agent
agent_type: systems-architect
pipeline_tier: standard
affected_files:
  - hackathon/demo.py
  - hackathon/rewrite_skill.py
  - hackathon/dashboard.py
affected_reqs: []
---

## Context

Cognee 1.0.3's `cognify()` step performs entity extraction and relationship detection by calling an LLM — by default OpenAI. The demo's primary LLM provider is Anthropic, and adding `OPENAI_API_KEY` would (a) require a second credential in `.env`, (b) introduce a second SDK to the dependency surface, and (c) add seconds to the demo's critical path for what is, in practice, a single retrieval over a single ~250-token JSON document. The use case lists three options: skip `cognify()`, configure Cognee to use Anthropic, or accept a second key. The retrieval pattern in `rewrite_skill.py` is a single `search("error_type:missed_bug", datasets=["skill-runs"])` — pure vector similarity over chunked text is sufficient.

## Decision

Use `cognee.add(...)` to write `SkillRunEntry` JSON strings and `cognee.search(query_text, query_type=SearchType.CHUNKS, datasets=["skill-runs"])` to retrieve them. Do not call `cognee.cognify()` at all. The demo runs end-to-end with only `ANTHROPIC_API_KEY`, `DAYTONA_API_KEY`, and Cognee credentials — `OPENAI_API_KEY` is neither required nor referenced.

## Considered Options

### Option A: Skip cognify(), use SearchType.CHUNKS only (selected)

- **Pro:** single-provider story, lowest latency, fewer credentials
- **Pro:** retrieval is sufficient for the demo's one-record-per-round access pattern
- **Con:** loses entity-extraction and relationship-traversal features (unused in the demo)

### Option B: Configure Cognee to use Anthropic for cognify()

- **Pro:** single API key, full Cognee feature surface
- **Con:** unverified path per researcher (Cognee's Anthropic provider config is not in curated docs)
- **Con:** Adds an LLM round-trip to the storage path that the demo never exercises

### Option C: Accept a second OPENAI_API_KEY

- **Pro:** Cognee runs as designed, fully featured
- **Con:** two credentials, two providers, more demo-day failure surface
- **Con:** Adds dependency on OpenAI for what is purely a Cognee internal step

## Consequences

- Positive: Demo `.env` requires only the three documented keys; setup is one line in `hackathon/.env.example`
- Positive: Round-trip latency for `add()` + `search()` is dominated by file I/O, not LLM calls — judges see snappy panel transitions
- Negative: If a future round wants graph-traversal queries (e.g., "all runs that failed with the same defect class across skills"), the demo will need `cognify()` then. Out of scope for the hackathon.
- Negative: `SearchType.CHUNKS` returns chunk-level matches; retrieval logic must filter explicitly for `error_type:missed_bug` to disambiguate between rounds (mitigation in `rewrite_skill.py`).
