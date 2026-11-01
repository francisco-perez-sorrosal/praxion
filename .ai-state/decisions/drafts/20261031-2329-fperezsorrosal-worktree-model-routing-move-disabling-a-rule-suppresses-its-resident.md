---
id: dec-draft-4afb26ec
title: Disabling a rule in the per-project blacklist also suppresses its resident
status: proposed
category: behavioral
date: 2026-10-31
summary: hooks/inject_rules.py adds to the disable set every hook-deliver rule whose frontmatter names a disabled rule in resident_of, through a local check held equal to scripts/_resident_of.py by a parity test, so existing blacklists naming swe/agent-model-routing (the hackathon preset among them) keep removing all routing text.
tags: [rules, startup-context-diet, moves, model-routing, path-scope]
made_by: agent
agent_type: systems-architect
branch: worktree-model-routing-move
pipeline_tier: standard
affected_files:
  - hooks/inject_rules.py
  - hooks/test_inject_rules.py
---
## Context

The routing rule is the first non-core rule with a resident. The blacklist resolves `disable:` globs by `fnmatch` over ids, so `swe/agent-model-routing` would no longer match the resident's id and every project disabling it (the hackathon preset, onboarding examples) would silently regain the session-start text.

## Decision

After glob resolution and the core filter, the injector adds each hook-deliver rule whose frontmatter `resident_of` names a disabled rule's path; it is filtered from `additionalContext`, named in `suppressed:` and given a `claudeMdExcludes` glob like any disabled rule. The check is local (a regex like the exporters'), held equal to `resident_parent` by a parity test, because the moves instrument runs the injector from copies carrying only `rules/`, `lib/` and `hooks/`.

## Considered Options

### Local check in the injector (chosen)
No manifest schema change; works in narrowed copies.

### The manifest carries `resident_of`
One generator line, but it reverses dec-480's "the generator does not read `resident_of`" and touches every manifest-row reader.

### A `-resident` naming convention
Rejected by dec-480 as implicit knowledge each reader re-derives.

## Consequences

- Positive: a blacklist keeps its reach across the move; `swe/*` unaffected.
- Negative: a fourth reader of the key, held only by a parity test; disabling the resident alone remains possible by its own id.

Activation: no — the honest-uncertainty gate does not fire; dec-480's precedent and concrete option costs decide it.
