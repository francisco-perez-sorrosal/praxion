---
id: dec-341
title: Persist the onboarding mode in the onboard stamp and make hackathon promotion mechanical
status: accepted
category: architectural
date: 2026-08-30
summary: Add a "mode" field (values "full" | "hackathon") to .ai-state/.praxion-onboard.json as the single persisted onboarding-mode signal, and add Sub-step 5b.t so promotion from hackathon to fully-managed removes all six hackathon artifacts instead of a partly-documented three-item manual checklist.
tags: [onboarding, hackathon, state, promotion, contracts]
made_by: agent
agent_type: systems-architect
branch: worktree-onboarding-unification
pipeline_tier: full
affected_files:
  - skills/onboard-project/SKILL.md
  - skills/onboard-project/references/phases-core.md
  - skills/onboard-project/references/detection.md
  - scripts/onboard-project
  - scripts/upgrade_project_pins.sh
  - docs/onboarding.md
affected_reqs: [REQ-05, REQ-06]
dissent: >
  The runtime switch every agent already reads is .claude/settings.json env.PRAXION_HACKATHON_MODE.
  Deriving the mode from that key needs no schema change and no second source of truth; adding a
  "mode" field to the onboard stamp creates two places that answer "is this a hackathon project?"
  and therefore a new way for them to disagree.
---

# Persist the onboarding mode in the onboard stamp and make hackathon promotion mechanical

## Context

Hackathon mode is activated by a boolean that crosses five process and format boundaries before reaching its destination: a bash flag or env var on `new_project.sh`, a `# Hackathon mode: true` trailer line in the seed prompt, `/new-project`'s conditional logic, a changed exit-handoff recommendation string, a `--hackathon` flag the user must retype on `/onboard-project`, and finally Phase 5b's auto-default. Nothing re-derives "this project was seeded with `--hackathon`" from persisted state, so a user who retypes the handoff without the flag silently drops the signal.

The exit path is worse. Phase 5b installs six artifacts (settings env key, `## Hackathon Mode` CLAUDE.md block, `praxion-rules.yaml` preset, `scripts/praxion-hackathon`, `.claude/hackathon-directive.md`, `.claude/hackathon-settings.json`). The documented graduation procedure — stated in two places, the CLAUDE.md block's own "To exit" section and `docs/greenfield-onboarding.md` — names only three of the six for removal. No script verifies any of it; no `check_hackathon_exit` gate exists.

The task mandate requires the hackathon signal to be persisted once rather than relayed, and requires a real, mechanical promotion path to fully-managed.

## Decision

**Persist once.** `.ai-state/.praxion-onboard.json` gains an additive `"mode"` field with values `"full" | "hackathon"`, written by Phase 9. The field records the **management level**, not the entry path: a `new`-mode onboarding stamps `"full"`, exactly as an `existing`-mode one does — the two converge on the same end state, so the provenance record must not distinguish them. A stamp lacking the field reads as `"full"` (back-compat). Phase 0 of every later invocation reads the stamp to resolve the mode with no user input and no relayed flag. The prompt trailer keeps exactly one hop — the unavoidable process boundary between the bash launcher and the Claude session — and terminates there.

`.claude/settings.json`'s `env.PRAXION_HACKATHON_MODE` remains the **runtime** switch every agent and rule checks each session; the stamp is the **provenance** record of what onboarding installed. When the stamp is absent (pre-existing hackathon projects), the env key is the fallback signal.

**Promote mechanically.** Add `Sub-step 5b.t` — the inverse of Phase 5b. It fires only when the stamp reads `"hackathon"` and the requested mode is `promote` (reachable as `--mode promote` or the one-word alias `--full`). It enumerates all six artifacts before touching any, compares each against its installed template, removes those that match, warns and skips those that diverge, then lets the full phase set run idempotently and rewrites the stamp to `"full"`. Never a recursive directory removal.

## Considered Options

### Option A — `"mode"` in the onboard stamp, with the env key as fallback, plus Sub-step 5b.t (chosen)

- Pro: one persisted provenance signal; promotion becomes `--full`; the removal set finally matches the write set; the runtime switch and the provenance record stay distinguishable.
- Con: an additive schema field, and 5b.t is genuinely new behavior that deletes files.

### Option B — Derive the mode entirely from `.claude/settings.json` `env.PRAXION_HACKATHON_MODE`

- Pro: no schema change; reuses the key every agent already reads; exactly one source of truth by construction.
- Con: conflates a runtime toggle with an installation record. A user who flips the env key by hand has silently "promoted" a project whose six artifacts are all still installed — precisely the inconsistent half-state this decision exists to close. It is also a bare boolean: it cannot record that a project was onboarded at all, only that hackathon mode is currently on.

### Option C — Status quo: relay the boolean, keep the manual three-step graduation

- Pro: zero change; no new field, no deletion behavior.
- Con: the documented exit procedure is incomplete by three artifacts and gated by nothing, and the mandate explicitly rejects the five-hop relay.

## Consequences

**Positive**

- Mode survives across sessions, re-runs, and direct skill invocation.
- Promotion is one flag rather than an incomplete checklist, and the six-artifact write set finally has a six-artifact removal set.
- Idempotency — already the load-bearing property of every phase — is what makes promotion a re-run rather than a migration.

**Negative**

- Two places can answer "is this a hackathon project?" (stamp and env key). Mitigated by assigning them different questions — provenance vs runtime — and by defining the fallback precedence explicitly, but the disagreement is now *possible*.
- `scripts/upgrade_project_pins.sh` rewrites the stamp's version field and must be verified not to clobber `"mode"`.
- 5b.t deletes files, which no onboarding phase does today.

## Disconfirmation

**Falsifier.** If a project promoted with `--full` still carries any of the six hackathon artifacts, or if its stamp says `"full"` while `env.PRAXION_HACKATHON_MODE` is still `"1"`, the mechanical promotion claim is false. Equally: if a `upgrade_project_pins.sh` run drops the `"mode"` field, the "persisted once" claim is false.

**Steelmanned runner-up.** Option B is the simpler and arguably more honest design. The env key is already the *sole* switch every agent, rule, and the always-loaded tier selector consults — the research is explicit that everything else is supporting infrastructure, not the switch. Introducing a second field means a future reader must learn which one wins and when, and the "provenance vs runtime" distinction is a rationalization for a divergence we are choosing to create. If the real problem is that graduation removes only three of six artifacts, that is fixed by writing the teardown sub-step alone — 5b.t needs no new field to know what to remove, because the six artifacts are a fixed set it can simply probe for. Option B plus 5b.t solves the mandate with strictly less state.

**Reversal trigger.** Revisit if the stamp and the env key are ever observed to disagree in a real managed project, or if 5b.t's probe-for-the-six-artifacts logic turns out to be sufficient on its own — either would show the `"mode"` field is carrying no weight the env key and a direct probe do not already carry.
