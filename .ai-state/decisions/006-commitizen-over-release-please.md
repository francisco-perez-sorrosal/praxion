---
id: dec-006
title: "Use Commitizen over Release Please for versioning"
status: accepted
category: architectural
date: "2026-04-01"
summary: "Commitizen selected for native PEP 440 dev releases and local-first CLI workflow over Release Please's PR-based model"
tags: [versioning, automation, commitizen]
made_by: agent
agent_type: systems-architect
pipeline_tier: standard
---

## Context

The project needed automated versioning and changelog generation. Two leading tools were evaluated: Commitizen (local CLI that bumps versions based on conventional commits) and Release Please (GitHub-native PR-based release workflow).

## Decision

Use Commitizen for versioning and changelog generation. It provides native PEP 440 dev release support (`cz bump --prerelease dev`), local-first CLI operation, and direct integration with `pyproject.toml` via `version_files`.

## Considered Options

### Option 1: Release Please

Google's PR-based release automation.

- (+) Zero local tooling required; fully GitHub-native
- (+) Release PRs provide a review checkpoint
- (-) PR-based model does not support PEP 440 dev pre-releases natively
- (-) Requires GitHub infrastructure; cannot release from local machine
- (-) Less control over version bump logic

### Option 2: Commitizen (selected)

Local CLI tool for conventional commit-driven versioning.

- (+) Native PEP 440 pre-release support (`--prerelease dev`)
- (+) Local-first: works without GitHub, CI optional
- (+) Direct `pyproject.toml` integration via `version_files`
- (+) Mature Python ecosystem support
- (-) Requires local installation (`pip install commitizen`)
- (-) No built-in PR review checkpoint for releases

## Consequences

### Positive

- Dev pre-releases work natively for development builds
- Version bumps are local operations with full control
- Changelog generation is automatic from conventional commits

### Negative

- Must configure `version_files` carefully (substring matching gotcha)
- CI release workflow requires explicit setup rather than being built-in
