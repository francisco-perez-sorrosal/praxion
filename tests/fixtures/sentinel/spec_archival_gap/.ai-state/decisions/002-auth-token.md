---
id: dec-002
title: Refresh token rotation policy
status: accepted
category: implementation
date: 2026-05-15
summary: Single-use refresh tokens with immediate rotation on redemption.
tags:
  - auth
  - token
made_by: agent
agent_type: implementation-planner
---

## Context

Refresh tokens are long-lived (30d) and must be protected against replay attacks.

## Decision

Implement single-use refresh token rotation: each redemption issues a new
refresh token and revokes the redeemed one via a short-lived blacklist entry.

## Considered Options

### Option A — Single-use rotation (chosen)

Pros: replay attacks are neutralized within one redemption cycle.
Cons: concurrent requests with the same token may fail.

### Option B — Sliding-window reuse

Pros: handles concurrent refreshes gracefully.
Cons: replay window exists for the sliding duration.

## Consequences

Concurrent refresh requests during high-load may require client-side retry
logic; acceptable given the security benefit.
