---
id: dec-008
title: "Diff mode by default with full-scan on command for security review"
status: accepted
category: architectural
date: "2026-04-01"
summary: "Security review defaults to diff mode (changed files only) with full-scan mode available via explicit command invocation"
tags: [security, review-modes, ci]
made_by: agent
agent_type: systems-architect
pipeline_tier: standard
affected_files: ["skills/context-security-review/SKILL.md", ".github/workflows/security-review.yml", "commands/full-security-scan.md"]
---

## Context

The security review skill needs to operate in two contexts: automated CI/verifier review (scoped to PR changes) and on-demand full-project audits. The default mode determines the tradeoff between thoroughness and noise.

## Decision

Diff mode is the default for CI and verifier consumers (review only changed files against security-critical paths). Full-scan mode is available only via the explicit `/full-security-scan` command, which reviews all files matching security-critical path patterns.

## Considered Options

### Option 1: Full-scan by default

Review all security-critical files on every PR.

- (+) Comprehensive coverage on every review
- (-) High noise: flags existing issues unrelated to the PR
- (-) Slow: scanning all 13 security-critical path patterns on every PR
- (-) Alert fatigue: developers learn to ignore persistent warnings

### Option 2: Diff mode by default (selected)

Review only changed files, with full-scan available on demand.

- (+) Low noise: only flags issues introduced or modified in the current change
- (+) Fast: scoped to the PR diff
- (+) Full-scan available when a comprehensive audit is wanted
- (-) Does not catch pre-existing security issues unless they are in changed files

### Option 3: No default, always explicit

Require the user to specify mode every time.

- (-) Friction: most reviews should just run with sensible defaults
- (-) CI workflow needs a default to function without user input

## Consequences

### Positive

- CI reviews are fast and low-noise
- Developers are not overwhelmed with pre-existing findings
- Full-scan is available for periodic security posture assessment

### Negative

- Pre-existing security issues in unchanged files are not surfaced by CI
- Full-scan must be invoked explicitly -- no automatic periodic scanning
