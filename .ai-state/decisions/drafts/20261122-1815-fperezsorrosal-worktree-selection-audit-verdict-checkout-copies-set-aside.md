---
id: dec-draft-c74dd28f
title: The selection audit sets aside reads made by copying the checkout as a whole, counts them in its notes, and still judges every other read
status: proposed
category: behavioral
date: 2026-11-22
summary: "The tracer adds a fourth channel, copy, for the source-side open of a shutil copy of the checkout as a whole. That is a copytree whose outermost source is the repository root, or copy2 calls that keep repository-relative paths after the running test listed the checkout with git ls-files at the root. Copy pairs are not audited, and the verdict's notes count them (reads and tests) and say that later reads from the copies are unaudited. A copy of a directory or a named file is still an ordinary read. A copying test's other reads stay direct or child and are judged as before. Gaps are closed by reader-sized additive declared entries"
tags: [selection-audit, tracer, test-selection, gate-liveness, copy-reads, determinism]
made_by: agent
agent_type: systems-architect
branch: worktree-selection-audit-verdict
pipeline_tier: standard
affected_files:
  - scripts/gate_probes/tracer/sitecustomize.py
  - scripts/gate_probes/selection.py
  - scripts/check_gates_bite.py
  - tests/declared-deps.toml
  - .github/workflows/gate-liveness.yml
  - skills/testing-strategy/references/test-selection.md
affected_reqs: [REQ-01, REQ-02, REQ-03, REQ-04, REQ-05, REQ-06, REQ-07]
supersedes_in_part: [dec-420]
---

## Context

The weekly selection audit (`dec-420`, hosted by `dec-520`) failed at the base 260a6d02 on 44,582 unselected reads locally and 39,753 on Linux. About 40,000 come from about 30 tests credited with building a sandbox copy of the checkout. Each such copy opens every copied file, and `dec-420` recorded those opens as `direct` reads. So the verdict said nothing a reader could act on, and its size depended on the xdist worker count, because a template built once per process is credited to whichever test of a worker asks first (12 workers locally, 4 on the runner). The user's working assumption: a copy read is evidence that the test needs a checkout, not that it depends on each copied file. Requirements: a copy of a particular directory or file stays a read; a copying test's other reads still count; the audit still fails on a lost dependency; and the rule's blind spot is counted on every run.

**Activation:** yes, honest uncertainty on where the whole-checkout copy ends. Four options were weighed against the measured copy sites. No Tier-B challenge: the stakes are not security, one-way-door or user-visible-breaking (the audit is Praxion-only and the rule is reversible by deleting one channel).

## Decision

- **The line is the copy's source root.** A read is on the new `copy` channel when it is the source-side open of a `shutil.copyfile` call (`copy`, `copy2` and `copytree`'s default copy function route through it) and the copy is either:
  - (a) inside a `shutil.copytree` whose outermost `src` is the repository root; or
  - (b) outside any `copytree`, to a destination ending in the file's full repository-relative path, after the running test, in that process, started a `git ls-files` at the repository root.

  Every other copy, of a subdirectory or of a named file, stays `direct` or `child`.
- **The verdict still audits `direct ∪ child` only.** `copy − (direct ∪ child)` over tracked files is set aside and counted in a note on every run: the reads (test, file pairs) and the tests that made them, and that later reads from the copies are not audited, with a count of none when no test copied. The rule classifies open events, never tests or pairs, so a copying test's other reads of the same files are judged.
- **Closures are sized to the reader.** A remaining gap is closed by an additive `[[dep]]` entry that selects every test reaching the shared reader, not the one test a run credited, so a local pass predicts the runner's. The local pass is taken at the default worker count and at `PYTEST_XDIST_AUTO_NUM_WORKERS=4`.

## Considered Options

### Option 1: source root plus enumeration (chosen)

- **Pro**: structural and threshold-free. It holds at every copy site in the repository (the kernel-sandbox, diagram-regen, plugin-update, refactoring-delivery, registry-drift, move-eval, adherence-eval and decision-gate templates, and the canary projects), and it leaves the named-tree testkit and the directory copies as reads.
- **Con**: a test that lists the checkout and then copies one named file under its own path has that read set aside (counted in the note). A hand-rolled copy loop is not recognized, which errs toward auditing.

### Option 2: a size or coverage threshold per destination

- **Pro**: needs no listing detection.
- **Con**: refuted by the measured sites. The kernel sandbox copies 285 of 3,915 tracked files (7.3 percent), the kernel-checker testkit copies 5 named files that keep their paths, and the canary copies 8 of 9. A threshold between them drifts as the tree grows, and a top-level-span rule cannot tell the canary (4 entries) from the testkit (4 entries).

### Option 3: each copying test declares itself

- **Pro**: explicit.
- **Con**: it excuses by test rather than by read, which a copying test's other reads rule out. A project the audit has never seen carries no declaration.

### Option 4: widen every change to every copier (a `**` declared entry)

- **Pro**: the safe direction. A sandboxed test plausibly depends on the whole checkout.
- **Con**: every test that *can* be credited with a template build must be listed (far more than the roughly 38 test files the selection-size bound allows, 5 points of the 764-file corpus), so every change's selection grows past the bound. It also contradicts the user's reading of what a copy shows.

## Consequences

**Positive**:

- The verdict names only reads a reader can act on, and it is independent of the worker count for copy reads.
- The rule's blind spot has a size on every run, like the import-time limit.
- The audit can pass, so its red is news again, and the two audit-gated whole-suite scenarios can pass with it.

**Negative**:

- Reads made later from a copy (outside the root) are unaudited. That was already true of `dec-420`'s tracer. It is now stated, counted and attributed.
- The tracer handles two more audit events. Their cost is per copy and per process start, not per open.
- The trace wire format gains a channel. An old probe reading a new trace fails loudly, and the two ship together.
- Reader-sized closures widen selection, because a declared entry holds at every hop: the median narrow root selection grew from 21.6 to 25.6 percent of test files (+4.0 points), most of it the hook-replay tests joining every change that reaches a module the hooks import. The selection-size limit was amended from +3 to +5 points on the user's word; how far a hook dependency should reach is left to its own design.

## Disconfirmation

- **Falsifier**: a selection miss found after merge (by `audit_tests.py`'s failure-based audit or a red full run) in which a test failed on a change to file F, the resolver did not select it, and the tracer recorded that test's reads of F only on the `copy` channel.
- **Steelmanned runner-up**: option 4. A sandboxed kernel test runs the generator over its copy, so a rule edit can change its outcome, and the copy rule leaves that edge to a declared entry someone must remember to write. Over-selection is the resolver's own safe direction.
- **Reversal trigger**: the falsifier firing once, or the copy note's count shrinking to fewer reads than the declared entries the copiers needed. Either moves copier tests to reader-sized declared entries and narrows rule (b).

## Prior Decision

`dec-420` defined `direct` as every in-process read that is not an import, explicit path loads included, so a checkout copy's opens were `direct` and judged. This decision narrows that clause only: an open that is the source side of a copy of the checkout as a whole is `copy`, which is not judged and is counted. `dec-420`'s `import` and `child` channels, its per-path resolver evaluation and its fail-closed answers are unchanged. It stays `accepted`.
