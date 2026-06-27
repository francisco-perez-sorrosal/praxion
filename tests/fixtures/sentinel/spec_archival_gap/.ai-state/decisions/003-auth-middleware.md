---
id: dec-003
title: Auth middleware placement in request pipeline
status: accepted
category: architectural
date: 2026-06-01
summary: Auth middleware runs before routing, not per-handler.
tags:
  - auth
  - middleware
made_by: agent
agent_type: systems-architect
dissent: Per-handler auth allows fine-grained public-route control without middleware exclusions.
---

## Context

The API framework requires a decision on where token validation occurs:
globally in middleware (before routing) or locally in each route handler.

## Decision

Run auth token validation in middleware before routing. Public routes are
declared in a per-route `auth_exempt` flag rather than bypassing the middleware
layer.

## Considered Options

### Option A — Global middleware (chosen)

Pros: single enforcement point; handlers never run without valid auth context.
Cons: public routes need explicit exemptions.

### Option B — Per-handler injection

Pros: handlers declare their own auth requirements.
Cons: any new handler omitting auth is silently unprotected until noticed.

## Consequences

The exempt-route registry becomes load-bearing; it must be tested alongside
the middleware. The single enforcement point reduces the risk of handlers
accidentally bypassing auth.

## Disconfirmation

**Falsifier**: if the exempt-route registry grows unbounded or is regularly
misapplied, the global approach may provide false security.

**Steelmanned runner-up**: per-handler auth requires explicit opt-in, making
public routes self-documenting.

**Reversal trigger**: if more than 20% of routes need exemptions, the global
approach degrades to noise.
