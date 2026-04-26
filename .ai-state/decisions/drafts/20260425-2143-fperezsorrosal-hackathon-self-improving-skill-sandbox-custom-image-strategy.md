---
id: dec-draft-e88a9e93
title: Daytona sandbox uses a pre-built custom image with anthropic + pydantic + pytest
status: proposed
category: architectural
date: 2026-04-25
summary: Sandbox image bakes anthropic, pydantic, and pytest into Image.debian_slim('3.12').pip_install([...]) to keep demo logs clean; cold-start mitigated by a --warm pre-create step in run_dashboard.sh.
tags: [hackathon, daytona, sandbox, demo-day]
made_by: agent
agent_type: systems-architect
pipeline_tier: standard
affected_files:
  - hackathon/demo.py
  - hackathon/run_dashboard.sh
affected_reqs: []
---

## Context

Daytona's warm pool delivers ~27-90ms first-creation latency for the default image. Adding `pip_install([...])` to the image breaks the warm-pool optimization and incurs a cold boot of several seconds. The demo has two real-time constraints: (1) the live demo log streamed in dashboard Panel 4 — judges watching `Collecting anthropic...` for 10s is bad demo theater; (2) total round-execution time on the demo clock. The use case proposes pre-creating Round 1 to shift cold-start cost off the demo clock either way. The trade-off is whether the runtime install runs inside a vanilla sandbox (warm pool, noisy log) or whether the cold-boot of a custom image is paid for once at warm-up time and amortized.

## Decision

Use a custom image: `Image.debian_slim("3.12").pip_install(["anthropic==0.97.0", "pydantic", "pytest"])`. Pre-create one sandbox of this image as a `--warm` step in `run_dashboard.sh` before Streamlit starts — this populates Daytona's image cache so subsequent Round 1 / Round 2 creates skip the image-build phase. Set `auto_stop_interval=10` minutes to keep the cache warm across the gap between rounds.

## Considered Options

### Option A: Custom image with all deps baked in (selected)

- **Pro:** clean demo log (no `pip install` chatter in Panel 4)
- **Pro:** deterministic Round 2 start time (~3-5s vs 10-15s with runtime install)
- **Con:** breaks Daytona warm pool; cold-boot on first run
- **Con:** image rebuilds when SDK pin changes (acceptable — pin is stable for the demo)

### Option B: Vanilla sandbox + process.exec("pip install ...")

- **Pro:** Daytona warm-pool sub-90ms create
- **Pro:** image is always fresh
- **Con:** ~10s of `pip install` log noise in Panel 4
- **Con:** Round 2 pays the install cost again

## Consequences

- Positive: dashboard Panel 4 log is dominated by review reasoning, not pip output
- Positive: `--warm` step in `run_dashboard.sh` is a one-time cost before judges start watching
- Negative: image cache may evict between Round 1 and Round 2 — `auto_stop_interval=10` mitigates by keeping Round 1's sandbox alive
- Negative: SDK pin upgrades require an image rebuild (not on the demo critical path)
- Risk accepted: if the warm step fails, the dashboard surfaces it via Panel 1 status before judges press "Run Round"
