---
paths:
  - "fitness/**"
  - "scripts/check_*.py"
  - "scripts/validate_*.py"
  - "hooks/*.py"
  - "agents/sentinel.md"
  - "agents/verifier.md"
  - "agents/implementation-planner.md"
---

## Gate Liveness

A *gate* is any mechanism whose purpose is to detect or prevent a defect class — a `check_*`/`validate_*` script, a fitness test or import-linter contract, a hook guard/gate, a sentinel check, a verifier phase, a planner or agent checkpoint, or any "verify/ensure/check X" instruction.

A gate is a **claim** that it catches its defect class. Like every claim in this codebase, it must be paired with a verification path (the "pair every claim with a verification path" practice). **A gate must be proven to bite** — proven to *fail* on a known-bad input, not merely to pass on the current good state. A gate nobody has seen fail is indistinguishable from no gate at all.

### The seven clauses

- **Substance over structure** — fail on missing or empty *content*, not just an absent *container*. Checking that a section exists is not checking that it says anything.
- **A named producer for every consumer** — if a gate reads or harvests `X`, some instruction must produce `X`. A consumer with no producer reads emptiness forever.
- **No self-contradiction** — never grep for, expect, or assert a pattern another rule forbids. The pattern can never appear, so the gate can never fire.
- **Pair with a verification path** — every gate ships proof it bites (which proof depends on the gate kind below).
- **Scope fidelity** — a gate's actual computed input set (the literal glob, allowlist, regex, or aggregation unit it evaluates) must be checked against the scope it is documented or claimed to cover, independently of whether it fires correctly on the inputs it does examine. A gate that correctly flags every violation inside a narrower-than-documented scope still returns a false "all clear" for everything outside it.
- **A named consumer for every gate output** — the mirror of "a named producer for every consumer" above: if a gate *computes* or *reports* a value (a count, a rate, a staleness signal), some document, check, or decision point must be named as its required reader before anyone states a conclusion that value would confirm or contradict. This is not a mandate to make advisory gates blocking — a gate can be correctly and deliberately advisory (it may be too early, too costly, or too disruptive to hard-fail on) and still need a named consumer. What fails is the combination: sound advisory design **plus** no reader named anywhere, which lets a human-authored claim drift from or contradict the gate's own output indefinitely with nothing to surface the mismatch. (A per-discipline count computed correctly by a test, with no document reading it before a combined figure is published; a release-staleness check that correctly declines to hard-fail on every commit, with no document consulting it before claiming an artifact has shipped — both are the same gap wearing different clothes.)

- **Existence is not operation** — every clause above assumes the gate ran, and asks whether it ran *correctly*. Also prove it runs *at all, in the environment it guards*: that something actually invokes it; that the interpreter, dependencies, and permissions it needs are present where it is installed; and that the copy being loaded is the copy you edited. A gate nothing calls, one whose failure prints as a non-blocking warning, one that never got its executable bit and so was never installed, and one shipped to a consumer running a cached older copy are all indistinguishable from no gate at all. None of these is visible from the gate's own tests, which pass in the author's environment — that is exactly why the failure survives.

### Two gate kinds, two proofs

| Gate kind | Examples | Proof it bites |
|---|---|---|
| **CODE** (deterministic) | `check_*`/`validate_*` scripts, fitness tests + import-linter contracts, hook `*_gate`/`*_guard` scripts | a **canary** — a sibling negative-case test that feeds a known-bad input and asserts the gate flags it (non-zero exit / failure / finding). Where the fitness tier is present, a canary-coverage meta-test enforces this. The authoring recipe lives in the `testing-strategy` skill's gate-canaries reference. |
| **PROMPT** (LLM-interpreted) | sentinel checks, verifier phases, planner/agent checkpoints, "verify X" instructions | a documented **golden bad-case** — the input the check must flag — in the gate's own definition, plus coverage by a sentinel Gate Liveness detector where one applies. |

A deterministic canary cannot prove a judgment gate; a golden bad-case cannot replace a real test for deterministic code. Use the proof that matches the gate.

### Anti-patterns

| Pattern | Why it fails | What to do instead |
|---|---|---|
| Check asserts a section/field *exists* | passes on an empty section — a hollow artifact looks complete | assert the section has ≥1 substantive entry (a row, a value, a non-placeholder line) |
| Instruction greps for a pattern another rule forbids | the pattern can never appear → 0 hits → a false "all clear" | read from the source-of-truth artifact instead (e.g., a traceability file, not test-name greps) |
| Instruction reads `X` that no instruction writes | the consumer reads emptiness; the feature is silently inert | wire a producer first, or cite the existing one; if neither exists, delete the consumer |
| New CODE gate with only a happy-path test | proves the code runs, not that the gate catches violations | add a canary: a test that drives a bad input and asserts the flag |
| "Indicative/future" capability referenced as if live | consumers depend on a contract that was never registered | register it before pointing at it, or gate the reference behind a liveness check |
| A convention lives at two+ textual sites (a canonical table row + a dispatch/prose paragraph; a canonical count duplicated elsewhere) | updating one site silently drifts from the other — a check reading only the canonical site can't catch the paired site falling out of sync | pick a single source of truth with the second site deriving from it, or add an explicit cross-reference note naming the paired site at both locations (e.g., the discipline-consultant's rules span `agents/discipline-consultant.md`, `agents/CLAUDE.md`, and `skills/software-planning/references/coordination-details.md` — update all three in the same commit) |
| A gate computes or reports a value, correctly and often deliberately advisory, that no document, check, or decision point is named to read | the computation is inert in practice — a human-authored claim can silently drift from or contradict it, and nothing surfaces the mismatch | name the consumer explicitly: a document section the value must match before asserting a conclusion, a check that diffs computed vs. published, or a golden bad-case in the gate's own definition documenting the correct reading — do not "fix" this by making the gate blocking if its advisory design was itself correct |

### Self-test before shipping a gate

Did I prove it *fails* on a bad input — not just pass on the current good state? If I cannot point to that proof (a canary test, or a golden bad-case the check flags), the gate is unverified and must not be trusted.

Did I diff the gate's *documented* scope against its *actual* computed scope — not just confirm it fires within the scope it already computes?

Did I name the consumer and the decision point this gate's output must reach — not just confirm the gate computes or reports correctly and leave its output for a human to independently re-derive, contradict, or ignore?

Did I watch it run in the environment it guards — not just in mine? Name what invokes it, and confirm the installed copy is the one I edited. `check_gate_liveness.py --check uninvoked-gate` answers the first half mechanically; the second half is a question only a deployed run can answer.
