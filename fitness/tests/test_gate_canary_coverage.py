"""Gate-canary coverage meta-test: every CODE gate ships a sibling negative-case test.

Cites: CLAUDE.md§Pragmatism and rules/swe/gate-liveness.md — a CODE gate must be proven to bite (fail on a
known-bad input), not merely pass on the current good state. Without a canary, a
green suite tells you only that the repo currently complies; it never tells you the
gate would catch a violation. This meta-test enforces the canary contract across the
full gate set.

Gate set scanned:
  - scripts/check_*.py and scripts/validate_*.py  → sibling test_<name>.py in scripts/
  - hooks/*_gate.py, hooks/*_guard.py, hooks/*_gate.sh → sibling test_<name>.py in hooks/
  - fitness/tests/test_*.py (except self and pure helpers) → contain their own
    negative-case test named to match the canary regex

Canary regex (from gate-canaries.md):
  test_(reject|flag|fail|block|deny|denie|detect|nonzero|violation|invalid|missing|empty|bad)
"""

from __future__ import annotations

import re
from pathlib import Path

# ---------------------------------------------------------------------------
# Canary regex — must match the recipe in skills/testing-strategy/references/gate-canaries.md
# ---------------------------------------------------------------------------

# The keyword may appear anywhere in the test name — the recipe uses the `*_rejects_*`
# form, so `test_full_scan_finds_violation` counts as a canary, not only
# `test_rejects_*`. Matched as a substring within a `def test_<name>` function.
CANARY_REGEX = re.compile(
    r"\bdef test_[a-z0-9_]*"
    r"(reject|flag|fail|block|deny|denie|detect|nonzero|violation|invalid|missing|empty|bad)"
    r"[a-z0-9_]*\b"
)

# ---------------------------------------------------------------------------
# Gates excluded from coverage enforcement by policy
# ---------------------------------------------------------------------------

# Gates the task explicitly says "already have a canary — do not touch":
_SKIP_GATE_STEMS = frozenset(
    {
        "check_aac_golden_rule",  # test_check_aac_golden_rule.py has test_*_fails
        "check_squash_safety",  # test_check_squash_safety.py has test_erasure_flagged_*
        "worktree_guard",  # test_worktree_guard.py has test_blocks_*
    }
)

# Fitness tests that are pure helpers (no gate logic of their own) and self:
_SKIP_FITNESS_FILES = frozenset(
    {
        "test_gate_canary_coverage.py",  # self
    }
)


def _has_canary(file: Path) -> bool:
    """Return True if `file` contains at least one canary-named test function."""
    try:
        source = file.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False
    return bool(CANARY_REGEX.search(source))


def _canary_candidates(gate: Path, root: Path) -> list[Path]:
    """Return the locations a gate's canary may live: co-located, or central tests/.

    Praxion uses both conventions — most check-scripts co-locate (`scripts/test_*.py`)
    but some live in the central `tests/` dir. A canary in either satisfies coverage.
    For foo.sh the sibling is test_foo.py (.sh → .py).
    """
    stem = gate.stem
    return [
        gate.parent / f"test_{stem}.py",  # co-located sibling
        root / "tests" / f"test_{stem}.py",  # central tests/ dir
    ]


def _script_gates(root: Path) -> list[Path]:
    """All scripts/check_*.py and scripts/validate_*.py, excluding test_ files and skipped gates."""
    scripts = root / "scripts"
    gates: list[Path] = []
    for pattern in ("check_*.py", "validate_*.py"):
        for p in sorted(scripts.glob(pattern)):
            if p.name.startswith("test_"):
                continue
            if p.stem in _SKIP_GATE_STEMS:
                continue
            gates.append(p)
    return gates


def _hook_gates(root: Path) -> list[Path]:
    """All hooks/*_gate.py, hooks/*_guard.py, hooks/*_gate.sh, excluding test_ files and skipped gates."""
    hooks = root / "hooks"
    gates: list[Path] = []
    for pattern in ("*_gate.py", "*_guard.py", "*_gate.sh"):
        for p in sorted(hooks.glob(pattern)):
            if p.name.startswith("test_"):
                continue
            if p.stem in _SKIP_GATE_STEMS:
                continue
            gates.append(p)
    return gates


def _fitness_gates(root: Path) -> list[Path]:
    """fitness/tests/test_*.py files that are simultaneously rules and tests.

    Excluded: self (test_gate_canary_coverage.py) and any file in the skip set.
    """
    fitness = root / "fitness" / "tests"
    gates: list[Path] = []
    for p in sorted(fitness.glob("test_*.py")):
        if p.name in _SKIP_FITNESS_FILES:
            continue
        gates.append(p)
    return gates


def gates_without_canary(root: Path) -> list[str]:
    """Return a list of gate identifiers that lack a canary.

    For script/hook gates: "scripts/<gate>" or "hooks/<gate>" — both the gate file
    and its sibling test must exist AND the sibling test must contain a canary-named
    test function.

    For fitness gates: "fitness/tests/<gate>" — the gate itself must contain a
    canary-named function (it is both rule and test).

    Returns relative path strings (from root) for actionable error messages.
    """
    missing: list[str] = []

    for gate in _script_gates(root) + _hook_gates(root):
        rel = str(gate.relative_to(root))
        candidates = _canary_candidates(gate, root)
        existing = [c for c in candidates if c.exists()]
        if not existing:
            missing.append(
                f"{rel}: no test found (looked for test_{gate.stem}.py "
                f"co-located or in tests/)"
            )
            continue
        if not any(_has_canary(c) for c in existing):
            missing.append(
                f"{rel}: test_{gate.stem}.py has no canary-named test "
                f"(needs def test_*(reject|flag|fail|block|...)* per gate-canaries.md)"
            )

    for gate in _fitness_gates(root):
        rel = str(gate.relative_to(root))
        if not _has_canary(gate):
            missing.append(
                f"{rel}: fitness gate has no canary-named test function "
                f"(add a def test_(reject|flag|...) proving the rule bites)"
            )

    return missing


# ---------------------------------------------------------------------------
# Meta-test: assert the real repo is clean
# ---------------------------------------------------------------------------


def test_every_gate_has_canary(project_root: Path) -> None:
    """Every CODE gate in the real repo ships a sibling canary-named test."""
    missing = gates_without_canary(project_root)
    assert not missing, (
        f"{len(missing)} gate(s) lack a canary (rules/swe/gate-liveness.md):\n"
        + "\n".join(f"  - {m}" for m in missing)
    )


# ---------------------------------------------------------------------------
# Own canary: prove this meta-test bites on a known-bad fixture
# ---------------------------------------------------------------------------


def _make_gate_file(root: Path, rel: str, body: str = "# gate\n") -> None:
    """Write a gate fixture file under root."""
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body, encoding="utf-8")


def test_flags_gate_without_canary(tmp_path: Path) -> None:
    """Canary: a gate with NO sibling test is reported by gates_without_canary."""
    _make_gate_file(tmp_path, "scripts/check_no_canary.py", "# gate without test\n")
    # Deliberately do NOT create a sibling test
    missing = gates_without_canary(tmp_path)
    assert any("check_no_canary.py" in m for m in missing), (
        f"meta-test must flag a gate with no sibling test; got: {missing}"
    )


def test_flags_sibling_test_without_canary_function(tmp_path: Path) -> None:
    """Canary: a gate whose sibling test has only happy-path tests is flagged."""
    _make_gate_file(tmp_path, "scripts/check_happy_only.py", "# gate\n")
    _make_gate_file(
        tmp_path,
        "scripts/test_check_happy_only.py",
        "def test_accepts_valid_input():\n    assert True\n",
    )
    missing = gates_without_canary(tmp_path)
    assert any("check_happy_only.py" in m for m in missing), (
        f"meta-test must flag a gate whose sibling has only happy-path tests; got: {missing}"
    )


def test_accepts_gate_with_valid_canary(tmp_path: Path) -> None:
    """Happy path: a gate with a properly named canary is clean."""
    _make_gate_file(tmp_path, "scripts/check_good.py", "# gate\n")
    _make_gate_file(
        tmp_path,
        "scripts/test_check_good.py",
        "def test_flags_bad_input():\n    assert True\n",
    )
    missing = gates_without_canary(tmp_path)
    assert not any("check_good.py" in m for m in missing), (
        f"meta-test must not flag a gate with a valid canary; got: {missing}"
    )


def test_accepts_fitness_gate_with_canary(tmp_path: Path) -> None:
    """Happy path: a fitness gate file with a canary-named test is clean."""
    fitness_dir = tmp_path / "fitness" / "tests"
    fitness_dir.mkdir(parents=True)
    (fitness_dir / "test_my_rule.py").write_text(
        '"""My rule.\n\nCites: CLAUDE.md§Pragmatism.\n"""\n'
        "def test_flags_violation():\n    assert True\n",
        encoding="utf-8",
    )
    missing = gates_without_canary(tmp_path)
    assert not any("test_my_rule.py" in m for m in missing), (
        f"fitness gate with canary must not be flagged; got: {missing}"
    )


def test_flags_fitness_gate_without_canary(tmp_path: Path) -> None:
    """Canary: a fitness gate file with no canary-named function is flagged."""
    fitness_dir = tmp_path / "fitness" / "tests"
    fitness_dir.mkdir(parents=True)
    (fitness_dir / "test_bare_rule.py").write_text(
        '"""My rule.\n\nCites: CLAUDE.md§Pragmatism.\n"""\n'
        "def test_rule_passes_on_valid_input():\n    assert True\n",
        encoding="utf-8",
    )
    missing = gates_without_canary(tmp_path)
    assert any("test_bare_rule.py" in m for m in missing), (
        f"meta-test must flag a fitness gate with no canary; got: {missing}"
    )
