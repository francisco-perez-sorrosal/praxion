---
id: dec-draft-575af979
title: test-coverage presentation model — pp-deltas, threshold bands, per-file column order
status: proposed
category: behavioral
date: 2026-04-24
summary: The skill's rendering API enforces pp-format deltas, red/yellow/green bands at 60/80, and a fixed per-file column order across terminal and Markdown surfaces.
tags: [skill, coverage, rendering, presentation]
made_by: user
pipeline_tier: standard
affected_files:
  - skills/test-coverage/SKILL.md
  - skills/test-coverage/references/python.md
  - commands/project-coverage.md
---

## Context

Coverage output reaches users through at least three surfaces — the `/project-coverage` terminal view, the `/project-metrics` Markdown report, and the verifier's report fragment. Each surface historically re-invents its own formatting. Small inconsistencies (is a 2-point rise `+2.0pp` or `+2%`? is 79% yellow or green?) accumulate into "is coverage getting better or worse?" ambiguity.

The user has settled three specific conventions that the skill must enforce centrally so every surface renders the same way.

## Decision

The skill's rendering API enforces three invariants. All three are documented in `skills/test-coverage/references/python.md` (the presentation-conventions section) and exercised by unit tests.

### 1. Delta format — percentage points, not percent-of-percent

Deltas are rendered as `+2.1pp`, `-0.4pp`, `+0.0pp`. Never `+2.8%` or `+2.8` bare — both are ambiguous (is it two points, or two percent of the prior value?). The `pp` suffix is load-bearing.

### 2. Threshold bands — 60 / 80

- Red: `< 60%`
- Yellow: `60% ≤ x < 80%`
- Green: `x ≥ 80%`

Bands are configurable per project via a documented override mechanism (e.g., constants exposed by the skill and overridable by the caller or by a project-level config). The default above is what ships.

### 3. Per-file breakdown column order

One fixed column order across every surface: `path | covered/total | % | delta`.

- `path` is repo-relative.
- `covered/total` is the raw line ratio (e.g., `412 / 518`) so a reader can see absolute magnitudes alongside the percentage.
- `%` is the percentage with the appropriate band color/style applied.
- `delta` is the pp-format delta from the prior run, empty when no prior run is available.

## Considered Options

### Option A — Enforce conventions centrally in the skill (chosen)

Every surface calls the skill's render functions; the skill owns all three invariants.

- **Pros.** One place to change the rules; three surfaces stay consistent automatically; testable.
- **Cons.** Callers lose the ability to "just sprinkle a percentage somewhere" without going through the skill; minor friction for edge cases.

### Option B — Document conventions, let each caller implement (rejected)

The skill ships a conventions doc; `/project-coverage`, the MD renderer, and the verifier each implement their own rendering against the doc.

- **Pros.** Maximum flexibility per caller.
- **Cons.** Exactly the drift the feature exists to prevent. Rejected.

### Option C — Let the user configure everything (rejected as over-general)

Bands, delta format, column order all configurable per run.

- **Pros.** Pleases every possible preference.
- **Cons.** YAGNI; the user explicitly picked specific values; configurability is reserved for the bands (the one genuinely project-dependent threshold).

## Consequences

**Positive.**
- Reading a coverage number in any Praxion surface means the same thing.
- Future rendering surfaces (e.g., a web UI) inherit the conventions for free — they just call the skill's render.
- Unit tests on the rendering API double as living documentation of the presentation contract.

**Negative.**
- If a caller ever needs a non-conforming rendering (e.g., a compact single-line summary), they have to extend the skill's render API rather than inline their own formatting. Acceptable — the extension becomes the new shared convention.
- The "pp" suffix is unusual enough that some readers will wonder what it means. Mitigated by one sentence in the skill's README and in `/project-coverage`'s on-help output.
