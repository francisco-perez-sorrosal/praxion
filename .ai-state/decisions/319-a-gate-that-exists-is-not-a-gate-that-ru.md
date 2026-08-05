---
id: dec-319
title: A gate that exists is not a gate that runs
status: accepted
category: architectural
date: 2026-08-05
summary: 'Add a seventh gate-liveness clause covering enforcement that never executes where it is deployed, and a mechanical uninvoked-gate check, because the six existing clauses all presume the gate ran and ask only whether it ran correctly.'
tags: [gate-liveness, enforcement, inert-gate, deployment, sentinel, failure-class, check-gate-liveness]
made_by: agent
agent_type: orchestrator
branch: main
pipeline_tier: standard
dissent: Seven clauses is a lot to hold, and the sharpest instances here were caught by a person noticing an anomaly rather than by any clause; a rule this long risks being skimmed, which is the failure mode it is trying to prevent.
affected_files:
  - rules/swe/gate-liveness.md
  - scripts/check_gate_liveness.py
  - scripts/test_check_gate_liveness.py
  - agents/sentinel.md
re_affirmed_by:
  - dec-320
---

## Context

One effort produced seven instances of the same failure, and none was caught by the rule written to catch exactly this:

| Instance | Shape |
|---|---|
| A reference validator whose docstring said it "can be wired into CI or a pre-commit hook later" | Written, never invoked; later never came |
| A lifecycle table declaring what each artifact's absence *means* | Documented, never consulted |
| The finalize chain and two commit hooks | Invoked with an interpreter lacking their imports; failed as a non-blocking warning that read as noise |
| A decay classifier blind to directory-shaped paths | Ran, was read, computed over the wrong input set |
| Its ownership predicate, matching containment in one direction only | The same asymmetry, mirrored, one commit later |
| The detector behind a shipped command | Never given its executable bit, so the installer never linked it — the command would have reached every managed project with its data source missing |
| A sentinel dimension present in the source tree | Absent from every cached copy of the installed plugin, so it had never once executed |

The rule already carried six clauses, and two of these do fall under them — the wrong-input-set pair is a scope-fidelity failure, and the unconsulted lifecycle table is an unread gate output. The rest fall under nothing, because **every existing clause presumes the gate ran and asks whether it ran correctly.** None asks whether it ran at all, in the place that was supposed to be guarded.

The failure is structurally invisible from the inside. The file exists. Its tests pass. Its docstring may even name the thing that invokes it. In the author's environment everything is fine, and the author's environment is the only one the tests describe.

## Decision

Add a seventh clause — **existence is not operation** — requiring proof that a gate runs in the environment it guards: that something invokes it; that the interpreter, dependencies, and permissions it needs are present where it is installed; and that the copy being loaded is the copy that was edited.

Ship the mechanically checkable half as `check_gate_liveness.py --check uninvoked-gate`: a `check_*`/`validate_*` script that no hook, command, agent, workflow, or sibling script invokes. It reports to a new sentinel GL04. The remaining half — whether the deployed copy is current, whether the interpreter can import — is not statically decidable and stays a question for a deployed run.

Matching considers the module stem as well as the filename, because one gate legitimately driving another is a real invocation. Omitting that reports wired gates as orphans, which would have condemned a gate this effort had just finished wiring.

Gate tests are explicitly **not** invocation sites. A test proves the gate works; it never proves anything runs it. Counting tests would make every orphan look wired — the precise inversion this clause exists to prevent.

## Considered Options

### Rely on the existing six clauses

They are well-drawn and two instances do land inside them. But five do not, and stretching "scope fidelity" to cover "was never installed" would blur a clause that is currently sharp.

### Prose clause only, no check

Cheapest. Rejected for a reason specific to this rule: `gate-liveness.md` is path-scoped, so it reaches an agent only when one of its matching files is *read* — and path-scoped rules inject on Read, not Write. An agent authoring a brand-new gate can miss it entirely. **The rule that says "prove your gate runs" has the delivery problem it describes**, which makes a mechanical check load-bearing here rather than merely nice.

### A blocking pre-commit gate rather than a sentinel check

Rejected as premature. The check is new and its false-positive surface is a heuristic over invocation sites; blocking commits on a heuristic that has run once would be the wrong trade. Reconsider once audits show it stable.

### Also detect stale deployed copies

The most valuable half, and not statically decidable: nothing in the source tree can see which copy a consumer loaded. Attempting it would produce a check that reports confidently on something it cannot observe.

## Consequences

**Positive.** The commonest cause of inert enforcement gains both a name and a mechanical detector. The check found a live instance on its first run: a sentinel-formatting wrapper whose docstring names the dimension that invokes it, where that dimension imported a different module directly — so the wrapper had never executed.

> **Correction (2026-08-05), recorded rather than edited away.** This section first claimed the
> wrapper was *also broken*. It is not: it runs clean under the project interpreter and its tests
> pass. It fails only under the ambient interpreter, because its dependency needs a package the
> shim lacks — the interpreter-resolution instance already listed in the Context table, not a
> second defect. The wrong claim came from running it once, under the wrong interpreter, and
> generalising — which is worth preserving as a caution: this class is diagnosed by *how* you
> ran something, so a single failing invocation is not evidence of a broken gate.
>
> Investigating the fix then found the cause was **two-layered**: the dimension both named the
> wrong invocation *and* was itself absent from the auto-dispatch list, so it never ran at all.
> Fixing only the first layer would have left the gate uninvoked while appearing resolved —
> the class hiding one instance behind another. Both are fixed; the detector now reports clean.

**Negative.** The rule is now seven clauses, and length erodes attention. The invocation-site list is a heuristic that will need extending as new invocation surfaces appear, and each extension is a chance to under-cover. And the clause's most valuable half remains unmechanised, so the strongest instances still depend on someone noticing an anomaly.

## Disconfirmation

**Falsifier.** If the next several instances of this class are ones GL04 could not see — stale deployed copies, wrong interpreters, missing permissions — then the clause named the right problem and the check addressed its least important half, and the effort should move to deployment-time verification instead.

**Steelmanned runner-up.** Doing nothing has a real case. Every instance here was ultimately caught by a person noticing that a number looked wrong, not by a clause — the directory-blindness surfaced because a count seemed too high, the uninstalled detector because someone asked whether a command could actually run downstream. A seventh clause may add length without adding attention, and the honest lesson might be that this class is caught by curiosity rather than by rules.

**Reversal trigger.** Revisit if GL04 runs for several audits without finding anything while instances keep appearing by other means — that would show the mechanical half is not where the class lives, and the clause should shrink back into prose or move to deployment-time verification.
