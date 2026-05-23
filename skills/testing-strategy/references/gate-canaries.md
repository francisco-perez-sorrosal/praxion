# Gate Canaries

How to author the canary that proves a CODE gate bites. Back-link: [`../SKILL.md`](../SKILL.md). Companion rule: `rules/swe/gate-liveness.md` (the declarative standard).

A **gate** is any mechanism whose job is to catch a defect class (a `check_*`/`validate_*` script, a fitness test, an import-linter contract, a hook `*_gate`/`*_guard`). A **canary** is the test that proves the gate *fails on a known-bad input* — not just that it passes on the current good state. Without a canary, a green suite only tells you the repo currently complies; it never tells you the gate would catch a violation. The canary is the gate's RED proof, the same way a failing test precedes the implementation in TDD.

## The contract

Every CODE gate ships a sibling test containing **at least one negative-case test**: it constructs or points at a known-bad input and asserts the gate flags it (non-zero exit, raised error, or a non-empty findings list).

- **Location** — co-located sibling, mirroring source structure: `scripts/check_foo.py` → `scripts/test_check_foo.py`; fitness rules already live in `fitness/tests/`; `hooks/foo_gate.py` → `hooks/test_foo_gate.py`.
- **Naming** — the negative-case test's name must signal the bad-case outcome so the coverage meta-test can find it. Use one of: `*_rejects_*`, `*_flags_*`, `*_fails_*`, `*_blocks_*`, `*_denies_*`, `*_detects_*`, `*_nonzero_*`, `*_violation_*`, `*_invalid_*`, `*_missing_*`, `*_empty_*`, `*_bad_*`.
- **A happy-path test is not a canary.** "Passes on the real repo" or "accepts valid input" proves the gate runs, not that it bites. The canary is in addition to any happy-path test.

## Worked example

```python
# scripts/check_no_todo_without_owner.py  (the gate)
def check(text: str) -> list[str]:
    return [ln for ln in text.splitlines() if "TODO" in ln and "@" not in ln]
```

```python
# scripts/test_check_no_todo_without_owner.py  (canary + happy path)
from check_no_todo_without_owner import check

def test_accepts_owned_todo() -> None:          # happy path — NOT the canary
    assert check("# TODO(@alice): wire it up") == []

def test_flags_ownerless_todo() -> None:        # the canary — proves it bites
    findings = check("# TODO: someday")
    assert findings, "gate must flag a TODO with no owner"
```

The canary feeds the exact defect the gate exists to catch and asserts a non-empty result. If someone later guts `check()` to `return []`, `test_flags_ownerless_todo` goes red — that is the gate proving it still bites.

## How coverage is enforced

A fitness meta-test globs the gate set (`scripts/check_*.py`, `scripts/validate_*.py`, `fitness/tests/test_*.py`, `hooks/*_gate.py`, `hooks/*_guard.py`) and asserts each gate has a sibling test with at least one negative-case-named test. A new gate without a canary fails the suite — the meta-test is itself a gate, so it ships with its own canary (a fixture gate lacking a negative-case test, which the meta-test must flag).

## PROMPT gates do not get canaries

LLM-interpreted gates (sentinel checks, verifier phases, planner/agent checkpoints) cannot be pinned by a deterministic test. They prove bite differently: a documented **golden bad-case** in the gate's own definition (the input it must flag) plus coverage by a sentinel Gate Liveness detector. Do not try to force a code canary onto a judgment gate — a test that can never meaningfully fail is itself a gate that does not bite.
