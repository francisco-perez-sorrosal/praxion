---
id: dec-362
title: The hook-chain self-heal rides a SessionStart hook, not the finalize chain, because the finalize chain cannot reach the failure it would repair
status: accepted
category: architectural
date: 2026-09-02
summary: A new hooks/heal_hook_chain.py re-points core.hooksPath at the Praxion wrapper when a package manager re-points it away. The finalize chain - Praxion's established self-delivering repair channel - is structurally unable to carry this repair, because the failure being repaired is precisely that git no longer invokes the hooks the finalize chain lives in. A non-ping-pong invariant makes the heal a fixed point.
tags: [self-healing, git-hooks, hooks-path, session-start, husky, repair-channel, convergence]
made_by: agent
agent_type: systems-architect
branch: worktree-sidecar-placement
pipeline_tier: full
affected_files:
  - hooks/heal_hook_chain.py
  - hooks/hooks.json
  - scripts/install_git_hooks.py
dissent: "Praxion already registers eight SessionStart hooks, and every one of them is a tax on the start of every session in every project including the overwhelming majority that will never use a hook manager; adding a ninth to repair a configuration value that a package manager changes at most a few times a year is a permanent, universal cost paid for a rare, local fault."
---

## Context

Praxion's hook install can now take over `core.hooksPath` to compose with a
repository's existing hook manager. That takeover is not stable: husky's
`prepare` script re-points `core.hooksPath` on every `npm install`, and other
managers behave similarly on their own install steps. Without repair, Praxion's
hooks go silently inert the first time the operator runs a routine package
install — the same silent-inert failure the chaining work exists to fix,
re-introduced through the back door.

`dec-356` established Praxion's answer to fleet-wide silent repair: the finalize
hook chain is "the one channel that executes current plugin code inside every
managed project on every merge/commit/checkout", so repairs ride there and heal
without operator action. The broken-Block-D repair is the worked example.

**That channel cannot carry this repair.** The finalize chain executes because
git invokes `.git/hooks/post-merge`, `post-commit` and `post-checkout`. When
`core.hooksPath` has been re-pointed away from Praxion's wrapper, git invokes
none of them. The condition that would trigger the repair is exactly the
condition that prevents the repair from running. This is not a stylistic
preference between two channels; it is a structural property of the failure.

## Decision

A new `hooks/heal_hook_chain.py` is registered on `SessionStart`. Plugin hooks
run whenever the plugin is enabled, independent of the repository's git
configuration, which is precisely the property the finalize chain lacks here.

1. **Thin by construction.** The hook fast-exits on one `lstat` when
   `<git-common-dir>/praxion-hooks` does not exist — that is, in every project
   that never needed chaining, which is almost all of them. Only when the
   wrapper directory exists does it invoke
   `scripts/install_git_hooks.py --heal`. The repair logic lives in the script
   layer under test, per `dec-355`; the hook is a trigger, not an
   implementation.

2. **The repairer is `install_git_hooks.py`, with two callers.** The SessionStart
   hook is the automatic caller; `upgrade_project_pins.sh` is the operator-driven
   one. One repairer, several callers — the same shape `dec-356` used, with the
   channel changed for the reason above.

3. **Non-ping-pong invariant.** The recorded delegate may never resolve to the
   Praxion wrapper directory itself. The invariant is asserted at the single
   write site; a violation refuses the write and warns. Its purpose is to make a
   wrapper that delegates to itself unrepresentable rather than merely unlikely.

4. **`PraxionWrapper` is a fixed point.** When the observed `core.hooksPath`
   already equals the wrapper, the heal performs no write at all. Every heal
   transition moves the state to `PraxionWrapper`, and nothing moves it out
   except an external tool whose write is not reactive to Praxion's — husky
   writes on `npm install`, never in response to a `git config` read. So each
   external event produces exactly one heal, and the sequence terminates rather
   than cycling.

5. **Defence in depth.** The wrapper carries a `PRAXION_HOOK_CHAIN_DEPTH`
   re-entrancy guard and refuses to exec a delegate at depth one or greater, so
   even a pathological delegate directory containing the wrapper cannot recurse.

6. **Fail-open and opt-out**, matching every other Praxion hook: any internal
   error exits 0 silently, and `PRAXION_DISABLE_HOOK_CHAIN_HEAL=1` suppresses it.

7. **It carries no sidecar concept.** The hook belongs to the hook-chaining
   milestone alone, which is what keeps that milestone independently mergeable.
   The sidecar's own SessionStart work lives in a separate hook.

## Considered Options

### A — Ride the finalize chain, per the established precedent

Pros: consistent with `dec-356`; no new hook; no session-start cost; the channel
is already proven to reach the fleet.

Cons: it cannot fire. A re-pointed `core.hooksPath` means git does not invoke
the finalize hooks, so the repair would run only in the case where it is not
needed. Consistency with a precedent whose enabling condition is absent is
consistency with a name, not with a mechanism.

### B — No automatic heal; `/upgrade-project` only

Pros: zero new machinery; the operator explicitly re-runs a command they already
know.

Cons: the failure is silent and the trigger is invisible — an operator has no
signal that `npm install` just disabled their commit gate, and therefore no
reason to run anything. A repair that requires noticing an invisible failure is
not a repair.

### C — SessionStart hook (chosen)

Pros: fires regardless of the repository's git configuration, which is the one
property this failure requires; costs one `lstat` in projects that never chain;
the repair implementation stays in the tested script layer.

Cons: a ninth SessionStart hook, paid for by every session in every project; a
hook that writes git configuration, which is a heavier action than the other
SessionStart hooks perform.

### D — Fold the heal into an existing SessionStart hook

Pros: no new registration; no additional session-start cost.

Cons: the plausible host is `auto_complete_install.py`, whose responsibility is
completing Praxion's own global install — an unrelated concern. Overloading it
buys one saved registration in exchange for a hook whose name stops describing
what it does, and whose two responsibilities cannot be disabled independently.

## Consequences

**Positive.** A package manager can no longer silently disable Praxion's hooks;
the worst case is one session's delay. The repair announces itself in one line,
so drift is observable rather than inferred. The heal and the operator-driven
upgrade share one implementation, so they cannot diverge — the `dec-355` failure
mode. The convergence argument is written down and testable rather than assumed.

**Negative.** A ninth SessionStart hook whose cost, however small, is paid
universally for a fault that is local and infrequent. A hook that mutates git
configuration sets a precedent worth being uncomfortable with, even though the
value is untracked and repository-local. `dec-356`'s "the finalize chain is the
repair channel" now has a documented exception, and a future reader must
understand *why* rather than pattern-matching on the precedent.

**Neutral.** `dec-356` is not narrowed or contradicted: Block-D repair still
rides the finalize chain, because git still invokes those hooks in that
scenario. The two decisions partition by whether the failure disables the
channel.

## Disconfirmation

**Falsifier.** If measurement shows the fast-exit path adds meaningful latency
to session start in ordinary projects — where the answer is always "no wrapper
directory, nothing to do" — the universal cost is not justified by the local
benefit, and the heal should move behind an explicit opt-in for projects known
to use a hook manager. Equally: if a hook manager is found that re-points
`core.hooksPath` reactively rather than on install, the fixed-point argument
fails and the design needs a backoff rather than an invariant.

**Steelmanned runner-up.** Option B is stronger than "silent failure" makes it
sound, because the failure need not stay silent. `install_git_hooks.py --status`
already exists in this design, and a single line in the SessionStart banner
Praxion *already* emits could report "Praxion hooks are not currently active in
this repository" — turning an invisible fault into a visible one for a fraction
of the cost, with the operator running one command to fix it. That keeps
Praxion out of the business of writing git configuration behind the operator's
back, which is the property this decision's own dissent objects to. It loses
only because the reporting path still needs a hook to notice the condition, so
the saving is smaller than it appears — but if the falsifier fires, option B
plus a banner line is the right retreat, not option A.

**Reversal trigger.** Any of: the heal writing more than once per external
event in observed use; a second repair wanting to join this hook, which would
mean the hook has become a general local-wiring repairer and should be named
and scoped as one; or Claude Code documenting a guarantee about hook-manager
interoperability that makes the takeover unnecessary.
