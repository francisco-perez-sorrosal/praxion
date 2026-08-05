---
id: dec-320
title: Mechanise the interpreter half of "existence is not operation"
status: accepted
category: behavioral
date: 2026-08-05
summary: 'Add an `ambient-import` check (sentinel GL05) flagging any script an agent or command runs with a bare `python3` that needs a package the ambient interpreter may not hold — discharging dec-319''s own falsifier, which named wrong interpreters as the class its mechanical half could not see.'
tags: [gate-liveness, enforcement, inert-gate, interpreter, sentinel, failure-class, check-gate-liveness, falsifier]
made_by: agent
agent_type: orchestrator
branch: main
pipeline_tier: standard
re_affirms: dec-319
affected_files:
  - scripts/check_gate_liveness.py
  - scripts/test_check_gate_liveness.py
  - scripts/spec_drift.py
  - agents/sentinel.md
---

## Context

`dec-319` named the failure class *a gate that exists is not a gate that runs*, shipped the
mechanically decidable half as GL04 (`uninvoked-gate`), and recorded a falsifier for its own scope:

> If the next several instances of this class are ones GL04 could not see — stale deployed copies,
> **wrong interpreters**, missing permissions — then the clause named the right problem and the
> check addressed its least important half.

The next instance was a wrong interpreter, and it was introduced by the commit that closed
`dec-319`. That commit rewired the sentinel's spec-drift check from an inline import to
`python3 scripts/check_spec_drift.py --json`. Under a version manager's shim `python3` is routinely
a build holding none of the project's declared dependencies, and the wrapper's sibling module
imported PyYAML at module scope — so the invocation died on `ModuleNotFoundError` before running.

Three properties made it survive. Its own tests passed, because they run under the project
interpreter. GL04 reported clean, because after the rewiring something *did* call it. And the
tech-debt note recording the fix diagnosed the hazard correctly one sentence before re-creating it.
A sweep of all thirteen scripts the sentinel prescribes found this was the only one affected: the
other twelve are stdlib-only, so the invariant held by accident rather than by enforcement.

## Decision

Add a third check to `check_gate_liveness.py`, `ambient-import`, routed to a new sentinel **GL05**.
It flags any script an agent or command instructs a model to run with a bare `python3` that needs a
package the ambient interpreter is not guaranteed to hold. GL04 and GL05 are the two halves of one
clause: GL04 asks whether anything calls the gate, GL05 asks whether the interpreter it is called
with can load it. A gate can pass GL04 and fail GL05, and that is the more dangerous order — the
call site exists, so the wiring looks complete.

Three properties are load-bearing:

- **Transitive.** The motivating instance imported only stdlib plus one sibling, and the dependency
  lived in the sibling. A direct-imports-only scan reports it clean, which is the scope-fidelity
  failure the rule warns about one clause earlier.
- **Guarded imports are exempt.** A `try`/`except ImportError` that prints a remedy naming the
  interpreter is this repo's documented answer, not a defect. Only the `try` body is guarded, never
  the handler's — an import written in an `except` clause is a fallback, and a fallback fails
  exactly like the import it replaces.
- **Scope is agent and command prose only.** Hooks and shell scripts resolve `$PRAXION_PYTHON` →
  `<repo>/.venv/bin/python` → ambient; CI installs the project environment; and
  `.pre-commit-config.yaml` names its interpreter in `language:`. Documented scope and computed
  scope are the same two globs.

The check was written against the live known-bad state and flagged exactly one script before any
fix was applied. The wrapper was then made loadable by importing PyYAML on demand — only the
in-flight scope reaches it, and the sentinel walks the archived one, so a module-scope import made
the whole gate unloadable to pay for a dependency that run never uses.

## Considered Options

### Fix only the script (drop or defer the dependency)

Restores the stdlib-only invariant across all thirteen scripts and costs nothing further. Rejected
as the *whole* answer: the invariant would remain accidental, and the next gate wired to a bare
`python3` reintroduces the class silently. It is however a necessary part of the answer, and was
also done.

### Resolve an interpreter at the sentinel's call sites

Would let gates carry dependencies freely. Rejected: it special-cases one of thirteen otherwise
uniform invocations, and pushes interpreter-resolution logic into agent prose, where it cannot be
tested. The finalize chain resolves an interpreter because it is a shell script that can; an agent
typing a command has no equivalent seam.

### Widen the scope to hooks, CI and pre-commit

Rejected on evidence: each of those already declares its interpreter, so a finding there would be a
false positive. Widening would also force this detector to parse `.pre-commit-config.yaml` to tell
`language: system` from `language: python`, which would require a YAML dependency — making the check
the first finding of its own rule.

### Prose clause only, no check

Rejected for the reason `dec-319` already gave about this rule: `gate-liveness.md` is path-scoped,
so it reaches an agent only when a matching file is read. The rule that says "prove your gate runs"
has the delivery problem it describes.

## Consequences

**Positive.** The commonest half of this class that GL04 could not see is now mechanical, and it
proved itself on a real instance rather than only on fixtures. The invariant that every
ambient-invoked gate is loadable by an ambient interpreter is now enforced instead of accidental.

**Negative.** A third check on one detector makes its scope note load-bearing — a future author
adding a fourth has three scope statements to keep honest. The stdlib-module list is a moving target
across Python versions, so a package vendored into the standard library later would produce a stale
finding. And the class's most valuable half — whether the deployed copy is the edited one — remains
unmechanised, so the strongest instances still depend on someone noticing an anomaly.

## Disconfirmation

**Falsifier.** If GL05 runs for several audits producing only false positives — flagging gates whose
invocation does in fact resolve a capable interpreter — then the scope note is wrong about which
surfaces are ambient, and the check should narrow or move to the invocation layer.

**Steelmanned runner-up.** Fixing only the script has a real case: twelve of thirteen gates were
already compliant, so the invariant may hold by the natural pull of stdlib-only tooling rather than
needing enforcement. If no further instance appears, this check will have cost more than the class
it guards.

**Reversal trigger.** Revisit if a gate legitimately needs a third-party package and the
guarded-import exemption becomes the normal case rather than the exception — at that point the
check is measuring style, not liveness, and the interpreter question belongs at the call site.

## Prior Decision

This re-affirms `dec-319` rather than superseding it. The clause, the class, and GL04 are all
unchanged and were correct; what changed is that the falsifier `dec-319` wrote for itself fired, and
it prescribed exactly this response. Re-opening the clause would require new evidence that the class
is misnamed, which nothing here provides — the instance fits the clause precisely, which is why the
clause found it. A future supersession would need evidence that interpreter availability is better
handled at the invocation layer than at the gate, for example if several gates legitimately need
third-party packages and guarding each one becomes the noisier answer.
