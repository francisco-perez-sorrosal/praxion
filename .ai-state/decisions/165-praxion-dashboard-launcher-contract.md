---
id: dec-165
title: praxion-dashboard launcher contract — stable user-facing interface across runtime changes
status: accepted
category: architectural
date: 2026-05-13
summary: Promote the dashboard launcher invariants (entrypoint, project-selection env var, port-override env var, deterministic per-path ports in 8501-9500, 127.0.0.1 bind, user-scoped runtime home) from a path-scoped rule entry into a first-class ADR so the contract survives runtime migrations and rule consolidation
tags: [dashboard, interface-contract, launcher, stability, user-facing]
made_by: user
pipeline_tier: direct
affected_files:
  - scripts/praxion-dashboard
  - dashboard_app/
  - rules/swe/dashboard-conventions.md
  - rules/writing/html-output-conventions.md
---

## Context

`scripts/praxion-dashboard` is the user-facing entrypoint for Praxion's per-project pipeline dashboard. Users invoke it through `/dashboard` and through direct shell calls. The runtime behind the launcher has already migrated once (Streamlit → Next.js, removed in commit `313a50e`) and may migrate again; users should not need to re-learn the interface when the implementation changes.

The launcher's invariants were previously documented as section 2 of `rules/swe/dashboard-conventions.md` ("Launcher Contract Stays Stable") — a path-scoped rule. That location had two problems: (a) the invariants are a stability contract, not a code-authoring convention, so a rule is the wrong shape for them; (b) the rule's other sections duplicated content already in `rules/writing/html-output-conventions.md`, motivating consolidation. Removing the rule without preserving the launcher contract somewhere first-class would leave the contract implicit in `dashboard_app/README.md` prose, where it could drift silently across runtime changes.

## Decision

Edits to `scripts/praxion-dashboard` must preserve the following invariants unless a subsequent ADR explicitly changes them:

1. **Entrypoint stability** — `/dashboard` remains the user-facing slash-command entrypoint; it delegates to `scripts/praxion-dashboard`.
2. **`PRAXION_PROJECT_ROOT`** remains the target-project selection contract. The launcher never falls back to `cwd` for project root resolution.
3. **`PRAXION_DASHBOARD_PORT`** remains the port-override hook for users who need to pin a specific port.
4. **Deterministic per-path ports** — when `PRAXION_DASHBOARD_PORT` is unset, the port is derived from the absolute project path (sha256-based) and lands in the **8501–9500** range, stable across restarts.
5. **Loopback bind** — the server binds to `127.0.0.1`. No interface-binding flag exposes the dashboard externally.
6. **User-scoped runtime home** — runtime dependencies (node_modules, built output) live under `~/.praxion-dashboard/`, never inside the target project tree.

A change to any of these is a breaking change to the launcher's user-facing contract and requires its own ADR superseding the relevant clause of this one.

## Considered Options

### Option 1 — Keep the invariants in a path-scoped rule (status quo before this ADR)

**Pros:** Auto-loads when editing `scripts/praxion-dashboard`; co-located with code-authoring conventions.
**Cons:** Rules ship into managed projects via `install_claude.sh`; a launcher-specific contract has no business loading in arbitrary downstream projects. Stability contracts are also a poor fit for the "declarative coding convention" shape of a rule — they describe an *interface*, not a coding convention.

### Option 2 — Document only in `dashboard_app/README.md`

**Pros:** No new artifact; readers landing on the dashboard package find the contract inline.
**Cons:** README prose drifts. The Streamlit → Next.js migration already happened once; preserving the contract through future migrations needs a more durable surface than a per-runtime README.

### Option 3 — Promote to a first-class ADR (chosen)

**Pros:** ADRs are Praxion's durable decision record. The contract survives runtime migrations, rule consolidation, and README rewrites. `DECISIONS_INDEX.md` makes it discoverable. The shipped-artifact-isolation rule keeps the ADR out of downstream projects, where it does not belong.
**Cons:** One more ADR to maintain. Outweighed by the durability gain.

## Consequences

**Positive:**

- The launcher contract becomes a first-class decision record, not a section in a rule file scheduled for deletion.
- Future runtime migrations (Next.js → some-other-framework) inherit the same invariants without re-deriving them from README archaeology.
- `rules/swe/dashboard-conventions.md` can be removed cleanly — its non-duplicate content is preserved here; its duplicate content is already in `rules/writing/html-output-conventions.md`.

**Negative:**

- An ADR is not auto-loaded when editing `scripts/praxion-dashboard`. Mitigated by:
  - `dashboard_app/README.md` linking to this ADR in its launcher section.
  - The script header itself can include a one-line pointer.

**Operational:**

- **Rollback:** if the dashboard rule is restored, this ADR can stay — the rule and ADR could coexist with the rule citing this ADR for rationale.
- **Supersession:** any future change to one of the six clauses must land as a new ADR setting `supersedes: dec-165` (per `rules/swe/adr-conventions.md`).
