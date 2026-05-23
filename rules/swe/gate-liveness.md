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

### The four clauses

- **Substance over structure** — fail on missing or empty *content*, not just an absent *container*. Checking that a section exists is not checking that it says anything.
- **A named producer for every consumer** — if a gate reads or harvests `X`, some instruction must produce `X`. A consumer with no producer reads emptiness forever.
- **No self-contradiction** — never grep for, expect, or assert a pattern another rule forbids. The pattern can never appear, so the gate can never fire.
- **Pair with a verification path** — every gate ships proof it bites (which proof depends on the gate kind below).

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

### Self-test before shipping a gate

Did I prove it *fails* on a bad input — not just pass on the current good state? If I cannot point to that proof (a canary test, or a golden bad-case the check flags), the gate is unverified and must not be trusted.
