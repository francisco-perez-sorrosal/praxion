---
id: dec-357
title: Praxion CLI exit codes are a three-layer contract; 2 stays usage and refusal moves to 3
status: accepted
category: behavioral
date: 2026-09-02
summary: Every Praxion CLI shares 0=ok and 2=usage; 1 means "actionable state, not clean" per the upgrade_project_pins.sh precedent; codes >=3 are per-script and documented in --help. praxion-sidecar puts refusal at 3 and environment failure at 4, declining the initially proposed 2=refused which collided with onboard-project's EXIT_USAGE=2.
tags: [cli, exit-codes, interface-design, sidecar-placement, tui, error-contract]
made_by: agent
agent_type: interface-designer
branch: worktree-sidecar-placement
pipeline_tier: full
affected_files:
  - scripts/praxion-sidecar
  - scripts/onboard-project
  - scripts/upgrade_project_pins.sh
dissent: "Three shipped scripts already disagree about codes above 2 (onboard-project reserves 3-8 for its own preconditions, upgrade_project_pins.sh uses only 0/1), so codifying a 'shared' contract that in practice only fixes 0/1/2 may be ceremony over a convention that could simply be documented per script."
---

## Context

`scripts/praxion-sidecar` is a new user- and hook-facing CLI. Its spawn brief
proposed the exit-code shape `0` healthy / `1` drift / `2` refused / `>=3` error.
That shape collides with two contracts already on disk:

- `scripts/onboard-project` declares `readonly EXIT_USAGE=2` and places
  *refused (guard)* at `7`. Two sibling scripts in one `scripts/` directory
  would then give `2` two incompatible meanings.
- The shell/POSIX convention — and the `tui-design` skill's exit-code table —
  reserve `2` for **misuse: wrong arguments, wrong usage**. Every wrapper,
  Makefile and CI step that special-cases `2` reads it that way.

Meanwhile `upgrade_project_pins.sh` has established a genuinely useful Praxion
convention that is not POSIX: `--check` exits `1` when drift is found, meaning
"the command worked; the answer is *not clean*". `onboard-project --check` does
the same thing at `8` (`EXIT_CHECK_PENDING`), which is the outlier.

Hooks are the forcing function. `post-checkout`, the finalize chain and the
SessionStart hook all need to distinguish "this project is set up but blocked"
(warn loudly) from "this project is not on a sidecar" (skip silently). Without
distinct codes, every caller parses stderr prose — which is not an interface.

## Decision

Praxion CLI exit codes are a **three-layer contract**:

| Layer | Codes | Binding on |
|---|---|---|
| Ecosystem-wide, never redefined | `0` = success / healthy / nothing to do; `2` = usage error | every Praxion CLI |
| Praxion convention | `1` = actionable state — the command worked, the answer is "not clean" | any CLI with a check/drift surface |
| Per-script, enumerated in `--help` | `>=3` | each script individually |

`praxion-sidecar`'s per-script codes: `3` = refused on safety grounds (understood
and deliberately declined), `4` = environment (not a git repo, no manifest,
sidecar unreadable, git subprocess failure).

The proposed `2 = refused` is **declined**. `onboard-project`'s existing `7` and
`8` are left untouched — no churn on shipped codes.

The test for whether a new code earns its place: does a caller take a
**distinct action** on it? Five codes pass that test here; a sixth (splitting
environment from unexpected-runtime) did not.

## Considered Options

### A — The brief's shape: 0 / 1 drift / 2 refused / >=3 error

Pros: fewest codes; refusal is prominent.
Cons: `2` means "refused" here and "usage" one file away in the same directory;
breaks the universal shell convention that CI tooling relies on; a user who
typos a flag gets a message about safety refusal.

### B — Three-layer contract with refusal at 3 (chosen)

Pros: honours both the POSIX convention and `onboard-project`'s existing
declaration; keeps the useful `1 = not clean` Praxion convention; gives hooks
the refused-vs-absent distinction they need; each script still owns its own
`>=3` space so no script is forced into a numbering that does not fit it.
Cons: five codes rather than four; `>=3` is not portable *across* Praxion CLIs,
so a generic wrapper cannot interpret them without reading `--help`.

### C — Adopt onboard-project's full numbering (3=no-claude … 7=refused)

Pros: maximal consistency with the largest sibling script.
Cons: codes `3`–`6` encode preconditions specific to onboarding (Claude CLI
present, plugin installed, target directory empty) that are meaningless for a
sidecar CLI. It would ship four permanently-unreachable codes to buy the
appearance of consistency.

## Consequences

**Positive.** Hooks branch on integers rather than stderr text. A usage typo and
a safety refusal are never confused. The `1 = not clean` convention is now
written down rather than inferred from one script. New Praxion CLIs have a rule
to follow for `0`/`1`/`2` and freedom below it.

**Negative.** `>=3` is per-script, so a generic runner cannot interpret an
arbitrary Praxion CLI's failure beyond "not 0, not 1, not 2". `onboard-project`
stays inconsistent with the `1 = not clean` convention (it uses `8`), a
deliberate non-fix that leaves one visible wart. Five codes must each be
covered by a test, or they decay into aspiration.

## Disconfirmation

**Falsifier.** If, six months on, callers are found treating `3` and `4`
identically at every call site — hooks, CI, and the orchestrator all collapsing
them to "non-zero, warn" — then the distinction bought nothing and the two
should merge into a single `3 = error`.

**Steelmanned runner-up.** Option A is right if one believes a *toolbox-local*
convention beats a global one: a user who lives inside Praxion learns "2 means
Praxion refused" once and is thereafter faster, and Praxion's CLIs are rarely
invoked from generic shell wrappers where the POSIX meaning of `2` matters. The
counter is that `onboard-project` already shipped `EXIT_USAGE=2`, so option A
is not "a consistent toolbox convention" — it is a *second* convention inside
one toolbox, which is strictly worse than either alternative alone.

**Reversal trigger.** A future Praxion CLI whose natural failure taxonomy needs
more than two codes above `2`, or the introduction of a generic runner that
must interpret any Praxion CLI's exit code without reading its help — either
would justify promoting `3` and `4` into the ecosystem-wide layer.
