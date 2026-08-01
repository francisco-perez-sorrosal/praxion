---
id: dec-305
title: Project-local discipline registry overlay with collision-as-error precedence
status: accepted
category: architectural
date: 2026-07-30
summary: A managed project may add consulting disciplines via an optional .ai-state overlay unioned with the shipped registry; a duplicate key is a named [BLOCKED] error, never an override.
tags: [multi-perspective-analysis, discipline-consultant, extensibility, registry, fail-loud, plugin-distribution]
made_by: agent
agent_type: systems-architect
branch: main
pipeline_tier: standard
affected_files:
  - skills/multi-perspective-analysis/references/discipline-registry.md
  - agents/discipline-consultant.md
  - fitness/tests/test_discipline_registry_invariants.py
  - .ai-state/discipline_registry_overlay.md
affected_reqs: [REQ-01, REQ-02, REQ-03, REQ-04, REQ-05, REQ-06, REQ-07, REQ-08]
dissent: >
  A mandatory namespace prefix on overlay keys would make collision unrepresentable
  rather than merely detected, and "assert unrepresentable over detect-after-the-fact"
  is the stronger general principle; collision-as-error is chosen only because the
  prefix taxes every user forever to prevent a rare, loud, rename-fixable event.
re_affirmed_by:
  - dec-311
---

# Project-local discipline registry overlay with collision-as-error precedence

## Context

The consulting-discipline roster ships as a data table inside a Praxion-distributed skill reference
(`skills/multi-perspective-analysis/references/discipline-registry.md`). Adding a discipline is one
row there — cheap for *Praxion*, impossible for a *managed-project user*, who would have to edit a
file inside the installed plugin that the next `plugin update` replaces. The originating requirement
included identities "optionally proposed by the praxion users", so the roster's extensibility story
is complete on one axis (N+1 for Praxion) and absent on another (user authorship). Filed as `td-064`;
the intended shape — a project-local overlay consulted alongside the shipped registry — was recorded
but deliberately not designed at planning stage.

Three constraints frame the design. The extensibility invariant must survive: a new discipline costs
0 always-loaded bytes, 0 agent files, 0 manifest entries, 0 consultant `tools:`/`skills:` changes,
asserted by 22 committed fitness tests. The consultant's resolution contract must stay fail-loud: an
unresolvable `Discipline:` value returns `[BLOCKED]` naming the value, never an improvised substitute.
And the registry is read at **two moments by two different readers** — a convener before spawn, the
consultant after spawn — so any overlay must be readable, and must mean the same thing, at both.

## Decision

A managed project may define disciplines in an optional, project-owned file at
`.ai-state/discipline_registry_overlay.md`, carrying the same seven-column row schema as the shipped
registry. Both readers resolve a `Discipline:` value against the **union** of the two tables.

- **Absence is silent and is the common case.** No overlay means today's behavior exactly — no
  warning, no diagnostic. `/onboard-project` creates nothing and gains no phase.
- **A discipline key present in both sources is a hard error**, not a precedence rule: `[BLOCKED]`
  naming the colliding key and both paths. There is no override and no shadow in this version.
- **Discovery rides the read that already happens.** A `## Project-Local Overlay` section in the
  shipped registry names the path shape and the union/collision semantics, so the pointer arrives in
  the same read that establishes the roster — zero always-loaded bytes, no new rule, no `CLAUDE.md`
  line.
- **Columns are matched by header name.** Missing required column, blank required cell, unmatched
  discipline, or unloadable `binds-to` each terminate in `[BLOCKED]` with a named cause. No branch of
  the amended resolution yields a substitute or a degraded consult.
- **An overlay row's `binds-to` is documented only for skills resolvable in the consultant's runtime
  listing.** Runtime `Skill` resolution is proven for plugin-shipped skills; resolution of a
  *project-local* `.claude/skills/` skill is untested and is not claimed to work until probed.
- **Praxion's own overlay stays empty.** A discipline good enough for Praxion belongs in the shipped
  registry, where every managed project receives it.

Enforcement is three additive fitness assertions, each vacuous when no overlay exists: disjointness of
the two name sets, row-shape validity of overlay rows (reusing the existing shape checker), and an
extension of the always-loaded-surface scan to the union of names. Both files are parsed by the one
existing table parser, so "a valid row" cannot drift between them.

## Considered Options

### Option A — Overlay overrides the shipped row of the same name (rejected)

Standard config-overlay semantics (`.gitconfig`, `tsconfig extends`), and genuinely useful: a project
could sharpen a shipped discipline's `fires-when` for its own domain without forking.

Rejected on two grounds. First, with two readers at two moments, a convener and a consultant that
disagree about which file they read — or in which order — select and resolve two different definitions
of one key, and the produced artifact records only the name. That is silent divergence with no
surface, and it is exactly the shape the fail-loud contract exists to exclude. Second, overlay-wins
turns a *plugin update* into an invisible behavior change: Praxion ships a better predicate for a name
the project happens to have overridden, and the project keeps its stale row forever with no signal.
Extensibility should not purchase permanent invisible staleness.

### Option B — Shipped registry shadows the overlay (rejected)

Praxion always wins. Rejected outright: it makes the user's own authored file the thing that silently
does nothing — the worst possible feedback for a feature whose entire purpose is user authorship.

### Option C — Collision made unrepresentable by a mandatory key prefix (rejected; strongest rival)

Require overlay keys to carry a namespace (`local-<name>`), so a collision cannot occur. This is the
better principle in the abstract — making a defect unrepresentable beats detecting it after the fact.

Rejected on cost distribution. The prefix taxes every overlay user, in every spawn directive, forever,
to prevent an event that is rare (the shared namespace is a handful of names), loudly detected at both
read moments, and repaired by a rename. It also bakes deployment provenance into a key that should
carry methodological meaning, and it forecloses a future *declared* override (`overrides: <name>`) if
one is ever earned by evidence.

### Option D — Overlay inside the project's `CLAUDE.md` (rejected decisively)

A `## Local Disciplines` section in the project's always-loaded instructions. This converts a
per-discipline *knowledge* cost into a per-discipline *structural* cost — the precise failure the
extensibility criterion was corrected to forbid — and would fail the committed
always-loaded-surface invariant the moment Praxion dogfooded it.

### Option E — Project-local skill carrying a second registry file (rejected)

`<project>/.claude/skills/<name>/references/discipline-registry.md`. Needs registration, and makes the
roster's home depend on the unproven question of whether project-scope skills appear in a subagent's
skill listing. A design should not rest its storage location on its least-verified assumption.

### Option F — `/onboard-project` scaffolds an empty overlay (rejected)

A header-only overlay is a populated-looking absence — the failure mode the row-schema rule already
names — and it would need a special case in every parser to avoid reading as a malformed table. It
also adds per-project install footprint with zero day-one value. Absence is the common case and should
cost nothing.

## Consequences

**Positive.**

- The user-authorship axis of the extensibility requirement is opened without touching any invariant:
  0 always-loaded bytes, 0 agent files, 0 manifest entries, 0 consultant frontmatter changes, and 0
  Praxion-shipped files edited per project discipline.
- The overlay is structurally immune to plugin update — the plugin body installs to the plugin cache
  and the installer writes no content into a project's `.ai-state/` (verified, not assumed). Sync
  tooling therefore needs to know nothing new.
- Fail-loud is extended rather than weakened: every added branch terminates in a named `[BLOCKED]`.
- Discovery costs nothing because it reuses an edge that already closes — both readers must open the
  shipped registry at exactly the moment they need the roster.
- Rollback is deleting one project file.

**Negative / accepted.**

- No way to tune a shipped discipline for a project's domain. A project that wants that must choose a
  different key name; the collision fails loudly rather than accommodating it.
- A future *required* registry column is a breaking change for every overlay in existence. Mitigated
  by header-name matching (an additive optional column is free) plus a standing obligation to prefer
  optional columns or ship a migration note. This obligation is real and will be forgotten if it is
  not carried in the registry's own overlay section.
- The most valuable version of the feature — a project discipline binding the project's *own*
  knowledge — is unproven, and ships documented as unsupported rather than claimed. Until a spike
  settles it, an overlay discipline contributes standing to object rather than new knowledge.
- User-authored rows have no quality gate. The disposition ledger's accept/defer/dismiss counts are
  the only feedback, and they are retrospective.

## Disconfirmation

**Falsifier.** If, in practice, projects overwhelmingly want to *modify* a shipped discipline rather
than add a distinct one, collision-as-error is the wrong rule: users would hit `[BLOCKED]` as a matter
of course and would work around it by choosing near-duplicate names, producing a roster with
`statistician` and `statistician-local` differing in ways no reader can see. Two or more independent
projects reporting that shape falsifies the decision. Conversely, if a single silent-divergence
incident ever occurs under this design, the decision's core argument is unsound.

**Steelmanned runner-up.** The mandatory-prefix design (Option C) is the strongest rival, and it is
stronger than the rejection above may make it sound. It eliminates an entire error class rather than
detecting it, needs no collision check at either read moment, removes the possibility that one reader
checks for collisions and the other forgets, and its cost is a few characters in a directive a human
writes rarely and an agent copies mechanically. If the overlay ever gains multiple sources (a team
overlay plus a personal one, say), namespaces stop being ceremony and start being necessary — at that
point Option C is not merely defensible, it is correct, and this ADR should be superseded rather than
patched.

**Reversal trigger.** Revisit when any of: (a) a second overlay source is proposed, making a
two-source disjointness check into an N-source one; (b) two or more projects request modification of a
shipped discipline's row, which is the concrete evidence that would earn an explicit `overrides:`
declaration; (c) the shipped registry needs a new *required* column, forcing the schema-compatibility
question into the open; or (d) the project-local-skill binding spike returns negative, since that
materially changes what an overlay discipline can be and may argue for a different mechanism entirely.
