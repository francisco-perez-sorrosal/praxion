---
id: dec-001
title: Auth session management approach
status: accepted
category: architectural
date: 2026-05-01
summary: Chose stateless JWT sessions over server-side session store.
tags:
  - auth
  - session
made_by: agent
agent_type: systems-architect
dissent: Server-side sessions allow instant revocation without blacklist overhead.
---

## Context

The auth feature required a session management approach compatible with
horizontal scaling across multiple stateless API nodes.

## Decision

Use stateless JWT sessions (HS256, 24h expiry) rather than a server-side
Redis session store.

## Considered Options

### Option A — Stateless JWT (chosen)

Pros: horizontally scalable, no Redis dependency.
Cons: revocation requires a short-lived token blacklist or rotation policy.

### Option B — Redis session store

Pros: instant revocation.
Cons: introduces a new infrastructure dependency.

## Consequences

Token expiry is enforced client-side; a token blacklist covers the revocation
gap until expiry.

## Disconfirmation

**Falsifier**: if revocation latency causes a security incident before tokens
expire, the blacklist approach is insufficient.

**Steelmanned runner-up**: Redis sessions solve revocation cleanly; the cost
is a new dependency that the platform may absorb.

**Reversal trigger**: if the product requires sub-minute revocation guarantees.
