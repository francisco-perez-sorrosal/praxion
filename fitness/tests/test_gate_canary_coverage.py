"""Gate-canary coverage meta-test: every CODE gate — and every check inside it — bites.

Cites: CLAUDE.md§Pragmatism and rules/swe/gate-liveness.md — a CODE gate must be proven to bite (fail on a
known-bad input), not merely pass on the current good state. Without a canary, a
green suite tells you only that the repo currently complies; it never tells you the
gate would catch a violation. This meta-test enforces the canary contract across the
full gate set.

Two coverage units, applied additively:

1. **File level** (unchanged). A gate file must contain — or have a sibling test file
   containing — at least one canary-named test function.
2. **Check level**. When a gate file defines module-level `check_*` / `validate_*`
   functions, each such function additionally needs at least one canary-named test that
   **calls** it. Without this, a check added to a file that already carries canaries is
   invisible to the file-level rule — which is the normal way checks get added, and the
   defect this unit closes. It is `gate-liveness.md`'s scope-fidelity clause applied to
   the meta-gate itself: its computed unit (files) was narrower than its documented
   purpose (gates bite).

Call detection resolves both `check_x(...)` and `module.check_x(...)`. The attribute form
is not an optimisation: `scripts/check_gate_liveness.py::check_forbidden_pattern` is
driven as `gl.check_forbidden_pattern(...)`, and a bare-name-only matcher reports it as a
false violation.

Gate set scanned:
  - scripts/check_*.py and scripts/validate_*.py  → sibling test_<name>.py in scripts/
  - hooks/*_gate.py, hooks/*_guard.py, hooks/*_gate.sh → sibling test_<name>.py in hooks/
  - fitness/tests/test_*.py (except self and pure helpers) → contain their own
    negative-case test named to match the canary regex

Canary regex (from gate-canaries.md):
  test_(reject|flag|fail|block|deny|denie|detect|nonzero|violation|invalid|missing|empty|bad)
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

# ---------------------------------------------------------------------------
# Canary regex — must match the recipe in skills/testing-strategy/references/gate-canaries.md
# ---------------------------------------------------------------------------

# Single source for the keyword alternation: the source-scanning form (file level) and the
# function-name form (check level) must never drift apart.
_CANARY_KEYWORDS = (
    "reject|flag|fail|block|deny|denie|detect|nonzero|violation|invalid|missing|empty|bad"
)

# The keyword may appear anywhere in the test name — the recipe uses the `*_rejects_*`
# form, so `test_full_scan_finds_violation` counts as a canary, not only
# `test_rejects_*`. Matched as a substring within a `def test_<name>` function.
CANARY_REGEX = re.compile(rf"\bdef test_[a-z0-9_]*({_CANARY_KEYWORDS})[a-z0-9_]*\b")

# The same contract applied to a bare function name, for AST-level matching.
CANARY_NAME_REGEX = re.compile(rf"^test_[a-z0-9_]*({_CANARY_KEYWORDS})[a-z0-9_]*$")

# A "check" is a module-level function with one of these prefixes.
_CHECK_PREFIXES = ("check_", "validate_")

# ---------------------------------------------------------------------------
# Gates excluded from coverage enforcement by policy
# ---------------------------------------------------------------------------

# Policy exclusions apply to the FILE-level rule only. The check-level pass deliberately
# scans the full gate set with no exclusions: every entry below was excused on the grounds
# that the file already carries a canary somewhere, which is precisely the reasoning the
# check-level unit exists to distrust. Verified at authoring time — none of the three
# stems declares a module-level check_*/validate_* function, so scanning them adds no
# obligation today; the exclusion is dropped so that adding one is not silently free.
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

_NO_SKIPS: frozenset[str] = frozenset()


def _parse(file: Path) -> ast.Module | None:
    """Parse `file` into an AST, returning None when unreadable or not valid Python."""
    try:
        source = file.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    try:
        return ast.parse(source)
    except SyntaxError:
        return None


def _has_canary(file: Path) -> bool:
    """Return True if `file` contains at least one canary-named test function."""
    try:
        source = file.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False
    return bool(CANARY_REGEX.search(source))


def declared_checks(gate: Path) -> list[str]:
    """Return the module-level `check_*` / `validate_*` function names defined in `gate`.

    Module level only: a helper nested inside a test function is an implementation
    detail of that test, not a gate the repo owes a canary to.
    """
    tree = _parse(gate)
    if tree is None:
        return []
    return [
        node.name
        for node in tree.body
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
        and node.name.startswith(_CHECK_PREFIXES)
    ]


def _called_check_names(func: ast.FunctionDef | ast.AsyncFunctionDef) -> set[str]:
    """Return the check-shaped names `func` calls, resolving Name and Attribute forms."""
    called: set[str] = set()
    for node in ast.walk(func):
        if not isinstance(node, ast.Call):
            continue
        target = node.func
        if isinstance(target, ast.Name):
            name = target.id
        elif isinstance(target, ast.Attribute):
            # `import check_gate_liveness as gl; gl.check_forbidden_pattern(...)`
            name = target.attr
        else:
            continue
        if name.startswith(_CHECK_PREFIXES):
            called.add(name)
    return called


def canary_covered_checks(files: list[Path]) -> dict[str, list[str]]:
    """Map each canary-named test to the check functions it calls.

    Keys are `<filename>::<test_name>` so that same-named canaries in two files in the
    same search scope do not collide. Values are sorted check names.
    """
    covered: dict[str, list[str]] = {}
    for file in files:
        tree = _parse(file)
        if tree is None:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                continue
            if not CANARY_NAME_REGEX.match(node.name):
                continue
            covered[f"{file.name}::{node.name}"] = sorted(_called_check_names(node))
    return covered


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


def _coverage_scope(gate: Path, root: Path) -> list[Path]:
    """Existing files a covering canary for `gate`'s checks may live in.

    The gate file itself (the fitness convention: rule and test are one file) plus the
    sibling locations `_canary_candidates` already resolves for script and hook gates.
    """
    seen: dict[Path, None] = {}
    for candidate in [gate, *_canary_candidates(gate, root)]:
        if candidate.exists():
            seen[candidate] = None
    return list(seen)


def _script_gates(root: Path, skip_stems: frozenset[str] = _SKIP_GATE_STEMS) -> list[Path]:
    """All scripts/check_*.py and scripts/validate_*.py, excluding test_ files and skipped gates."""
    scripts = root / "scripts"
    gates: list[Path] = []
    for pattern in ("check_*.py", "validate_*.py"):
        for p in sorted(scripts.glob(pattern)):
            if p.name.startswith("test_"):
                continue
            if p.stem in skip_stems:
                continue
            gates.append(p)
    return gates


def _hook_gates(root: Path, skip_stems: frozenset[str] = _SKIP_GATE_STEMS) -> list[Path]:
    """All hooks/*_gate.py, hooks/*_guard.py, hooks/*_gate.sh, hooks/remind_*.py.

    Excludes test_ files and skipped gates. The remind_*.py advisory-hook family
    (remind_adr.py, remind_calibration.py) fires fail-open stderr reminders rather
    than blocking a commit, but is still a CODE gate under rules/swe/gate-liveness.md
    -- it must be proven to bite on a known-bad input, not merely absent from scan.
    """
    hooks = root / "hooks"
    gates: list[Path] = []
    for pattern in ("*_gate.py", "*_guard.py", "*_gate.sh", "remind_*.py"):
        for p in sorted(hooks.glob(pattern)):
            if p.name.startswith("test_"):
                continue
            if p.stem in skip_stems:
                continue
            gates.append(p)
    return gates


def _fitness_gates(root: Path, skip_files: frozenset[str] = _SKIP_FITNESS_FILES) -> list[Path]:
    """fitness/tests/test_*.py files that are simultaneously rules and tests.

    Excluded: self (test_gate_canary_coverage.py) and any file in the skip set.
    """
    fitness = root / "fitness" / "tests"
    gates: list[Path] = []
    for p in sorted(fitness.glob("test_*.py")):
        if p.name in skip_files:
            continue
        gates.append(p)
    return gates


def checks_without_canary(root: Path) -> list[str]:
    """Return `<relpath>::<check_name>` for every check no canary-named test calls.

    Scans the full gate set with no policy exclusions — see `_SKIP_GATE_STEMS`.
    """
    missing: list[str] = []
    gates = (
        _script_gates(root, _NO_SKIPS)
        + _hook_gates(root, _NO_SKIPS)
        + _fitness_gates(root, _NO_SKIPS)
    )
    for gate in gates:
        checks = declared_checks(gate)
        if not checks:
            continue
        scope = _coverage_scope(gate, root)
        exercised = {name for names in canary_covered_checks(scope).values() for name in names}
        rel = str(gate.relative_to(root))
        for check in checks:
            if check in exercised:
                continue
            missing.append(
                f"{rel}::{check}: no canary-named test calls it "
                f"(add a def test_*(reject|flag|...) that invokes {check} directly)"
            )
    return missing


def gates_without_canary(root: Path) -> list[str]:
    """Return a list of gate identifiers that lack a canary.

    For script/hook gates: "scripts/<gate>" or "hooks/<gate>" — both the gate file
    and its sibling test must exist AND the sibling test must contain a canary-named
    test function.

    For fitness gates: "fitness/tests/<gate>" — the gate itself must contain a
    canary-named function (it is both rule and test).

    Per-check findings from `checks_without_canary` are appended: a file may satisfy the
    file-level rule and still owe a canary for an individual check.

    Returns relative path strings (from root) for actionable error messages.
    """
    missing: list[str] = []

    for gate in _script_gates(root) + _hook_gates(root):
        rel = str(gate.relative_to(root))
        candidates = _canary_candidates(gate, root)
        existing = [c for c in candidates if c.exists()]
        if not existing:
            missing.append(
                f"{rel}: no test found (looked for test_{gate.stem}.py co-located or in tests/)"
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

    return missing + checks_without_canary(root)


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


def test_every_declared_check_has_canary(project_root: Path) -> None:
    """Every module-level check_*/validate_* in the real repo is called by a canary."""
    missing = checks_without_canary(project_root)
    assert not missing, (
        f"{len(missing)} check(s) lack a canary (rules/swe/gate-liveness.md):\n"
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
    assert any(
        "check_no_canary.py" in m for m in missing
    ), f"meta-test must flag a gate with no sibling test; got: {missing}"


def test_flags_sibling_test_without_canary_function(tmp_path: Path) -> None:
    """Canary: a gate whose sibling test has only happy-path tests is flagged."""
    _make_gate_file(tmp_path, "scripts/check_happy_only.py", "# gate\n")
    _make_gate_file(
        tmp_path,
        "scripts/test_check_happy_only.py",
        "def test_accepts_valid_input():\n    assert True\n",
    )
    missing = gates_without_canary(tmp_path)
    assert any(
        "check_happy_only.py" in m for m in missing
    ), f"meta-test must flag a gate whose sibling has only happy-path tests; got: {missing}"


def test_accepts_gate_with_valid_canary(tmp_path: Path) -> None:
    """Happy path: a gate with a properly named canary is clean."""
    _make_gate_file(tmp_path, "scripts/check_good.py", "# gate\n")
    _make_gate_file(
        tmp_path,
        "scripts/test_check_good.py",
        "def test_flags_bad_input():\n    assert True\n",
    )
    missing = gates_without_canary(tmp_path)
    assert not any(
        "check_good.py" in m for m in missing
    ), f"meta-test must not flag a gate with a valid canary; got: {missing}"


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
    assert not any(
        "test_my_rule.py" in m for m in missing
    ), f"fitness gate with canary must not be flagged; got: {missing}"


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
    assert any(
        "test_bare_rule.py" in m for m in missing
    ), f"meta-test must flag a fitness gate with no canary; got: {missing}"


# ---------------------------------------------------------------------------
# Per-check canaries: the unit is the check, not the file
# ---------------------------------------------------------------------------

_TWO_CHECKS_ONE_CANARY = '''"""Two checks, one canary.

Cites: CLAUDE.md§Pragmatism.
"""


def check_covered(rows):
    return ["bad"] if rows else []


def check_uncovered(rows):
    return ["bad"] if rows else []


def test_flags_bad_rows():
    assert check_covered(["x"])
'''

_ATTRIBUTE_CALL_GATE = '''"""One check, driven through a module attribute.

Cites: CLAUDE.md§Pragmatism.
"""


def check_via_attribute(rows):
    return ["bad"] if rows else []
'''

_ATTRIBUTE_CALL_CANARY = """import gate_module as gm


def test_flags_bad_rows():
    assert gm.check_via_attribute(["x"])
"""


def test_flags_uncovered_check_in_a_file_that_already_has_canaries(tmp_path: Path) -> None:
    """Canary: a check with no canary calling it is flagged even when the file has canaries.

    This is the exact defect the file-level unit could not see — the normal way a check
    gets added is into a file that already carries canaries for its siblings.
    """
    fitness_dir = tmp_path / "fitness" / "tests"
    fitness_dir.mkdir(parents=True)
    (fitness_dir / "test_two_checks.py").write_text(_TWO_CHECKS_ONE_CANARY, encoding="utf-8")

    missing = checks_without_canary(tmp_path)

    assert any(
        "test_two_checks.py::check_uncovered" in m for m in missing
    ), f"the uncalled check must be flagged; got: {missing}"
    assert not any(
        "check_covered" in m for m in missing
    ), f"the called check must not be flagged; got: {missing}"


def test_module_attribute_call_counts_as_covering_the_check(tmp_path: Path) -> None:
    """A check driven as `module.check_x(...)` is covered, not a false violation.

    A bare-`ast.Name` matcher reports the real `check_gate_liveness::check_forbidden_pattern`
    as uncovered, because its canary drives it as `gl.check_forbidden_pattern(...)`.
    """
    scripts_dir = tmp_path / "scripts"
    scripts_dir.mkdir(parents=True)
    (scripts_dir / "check_gate_module.py").write_text(_ATTRIBUTE_CALL_GATE, encoding="utf-8")
    (scripts_dir / "test_check_gate_module.py").write_text(_ATTRIBUTE_CALL_CANARY, encoding="utf-8")

    missing = checks_without_canary(tmp_path)

    assert not any(
        "check_via_attribute" in m for m in missing
    ), f"an attribute-call canary must count as coverage; got: {missing}"


def test_gate_file_with_no_checks_is_left_to_the_file_level_rule(tmp_path: Path) -> None:
    """A gate defining no check_* function yields no per-check findings at all.

    The per-check unit is purely additive: a `main()`-shaped script gate keeps exactly the
    obligation it had before.
    """
    scripts_dir = tmp_path / "scripts"
    scripts_dir.mkdir(parents=True)
    (scripts_dir / "check_main_shaped.py").write_text(
        "def main():\n    return 0\n", encoding="utf-8"
    )
    (scripts_dir / "test_check_main_shaped.py").write_text(
        "def test_flags_bad_input():\n    assert True\n", encoding="utf-8"
    )

    assert checks_without_canary(tmp_path) == []


def test_declared_checks_ignores_nested_helpers_and_non_check_names(tmp_path: Path) -> None:
    """Only module-level check_*/validate_* names become obligations.

    A helper nested inside a test belongs to that test; enumerating it would manufacture
    an obligation the repo never took on.
    """
    gate = tmp_path / "gate.py"
    gate.write_text(
        "def check_top_level(x):\n"
        "    return []\n"
        "\n"
        "\n"
        "def validate_top_level(x):\n"
        "    return None\n"
        "\n"
        "\n"
        "def helper(x):\n"
        "    return x\n"
        "\n"
        "\n"
        "def test_flags_bad_input():\n"
        "    def check_nested(y):\n"
        "        return []\n"
        "\n"
        "    assert check_nested(1) == []\n",
        encoding="utf-8",
    )

    assert declared_checks(gate) == ["check_top_level", "validate_top_level"]


def test_non_canary_test_calling_a_check_does_not_count_as_coverage(tmp_path: Path) -> None:
    """Only canary-named tests confer coverage — a happy-path caller is not proof of bite."""
    fitness_dir = tmp_path / "fitness" / "tests"
    fitness_dir.mkdir(parents=True)
    (fitness_dir / "test_happy_caller.py").write_text(
        '"""A rule exercised only by a happy-path test.\n\nCites: CLAUDE.md§Pragmatism.\n"""\n'
        "\n\ndef check_something(rows):\n    return []\n"
        "\n\ndef test_accepts_valid_rows():\n    assert check_something([]) == []\n"
        "\n\ndef test_flags_unrelated_thing():\n    assert True\n",
        encoding="utf-8",
    )

    missing = checks_without_canary(tmp_path)

    assert any(
        "test_happy_caller.py::check_something" in m for m in missing
    ), f"a check called only by a happy-path test must be flagged; got: {missing}"
