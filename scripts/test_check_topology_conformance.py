"""Tests for check_topology_conformance.py -- TT01/TT02/TT05/TT06 gate-liveness canary.

Each test builds the minimal `.ai-state`/`skills/testing-strategy/references` substrate
a check needs under `tmp_path`. One canary-named test per check id, plus supporting
clean/skip cases.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import check_topology_conformance as topo  # noqa: E402
from check_topology_conformance import CHECK_IDS, classify  # noqa: E402

_DESIGN_3A_HEADER = (
    "### 3a. Structural components\n\n"
    "| Component | Element | Responsibility | Status | Key Files (illustrative) |\n"
    "|-----------|---------|---------------|--------|--------------------------|\n"
)

_LEAF_REGISTRY = """## Selector Strategy Registry (Registry 1)

| Identifier | Argument shape | Registered by | Concrete meaning |
|-----------|----------------|---------------|-----------------|
| `pytest-globs` | List of path/glob strings | Python leaf | No marker registration required. |
| `pytest-markers` | List of snake_case marker name strings | Python leaf | Each marker must be registered. |
| `pytest-keywords` | A single keyword expression string | Python leaf | Optional within the Python leaf; requires no marker registration. |

### Indicative Future Identifiers

| Identifier (future) | Registered by (future) | Indicative concrete meaning |
|--------------------|-----------------------|-----------------------------|
| `go-test-packages` | Go leaf | not registered yet |
"""

_LEAF_RESERVED_TRUNK = """## Reserved Name Set

- Tier keywords: `unit`, `integration`, `contract`, `e2e`

---
"""


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _write_design(tmp_path: Path, rows: list[tuple[str, str]]) -> None:
    body = _DESIGN_3A_HEADER
    for name, status in rows:
        body += f"| {name} | `x.{name.lower()}` | desc | {status} | `x` |\n"
    _write(tmp_path / ".ai-state" / "DESIGN.md", body)


def _write_trunk_leaf(tmp_path: Path) -> None:
    _write(
        tmp_path / "skills" / "testing-strategy" / "references" / "test-topology.md",
        _LEAF_REGISTRY + "\n" + _LEAF_RESERVED_TRUNK,
    )


def _write_python_leaf(tmp_path: Path, reserved_extra: str = "") -> None:
    body = (
        "### Reserved Name Set\n\n"
        "- `parametrize`\n"
        "- `skipif`\n"
        f"{reserved_extra}"
        "- `unit`, `integration`, `contract`, `e2e`\n\n"
        "### Next\n"
    )
    _write(tmp_path / "skills" / "testing-strategy" / "references" / "python-testing.md", body)


def _write_topology(tmp_path: Path, groups_yaml: str) -> None:
    _write(tmp_path / ".ai-state" / "TEST_TOPOLOGY.md", groups_yaml)


def _group_block(
    group_id: str, subsystems: list[str], strategy: str = "pytest-globs", arg: str = "tests/"
) -> str:
    subs = "\n".join(f"  - {s}" for s in subsystems)
    return (
        "```yaml\n"
        f"id: {group_id}\n"
        "title: t\n"
        f"subsystems:\n{subs}\n"
        "tier: unit\n"
        "selectors:\n"
        f"  - strategy: {strategy}\n"
        f'    arg: ["{arg}"]\n'
        "file_dependencies:\n"
        '  - "x/**"\n'
        "parallel_safe: true\n"
        "shared_fixture_scope: none\n"
        "```\n"
    )


def test_check_ids_declares_the_four_topology_checks() -> None:
    assert CHECK_IDS == ("TT01", "TT02", "TT05", "TT06")


def test_no_topology_file_skips_tt01_tt02_tt05(tmp_path: Path) -> None:
    _write_design(tmp_path, [("Skills", "Built")])
    report = classify(tmp_path)
    assert report["skipped"]["TT01"]["reason"] == "substrate-absent"
    assert report["skipped"]["TT02"]["reason"] == "substrate-absent"
    assert report["skipped"]["TT05"]["reason"] == "substrate-absent"


# -- TT01: subsystems resolve to a Built §3a component -----------------------


def test_tt01_flags_subsystem_missing_from_design(tmp_path: Path) -> None:
    """Golden bad-case: a group names a subsystem absent from §3a entirely."""
    _write_design(tmp_path, [("Skills", "Built")])
    _write_trunk_leaf(tmp_path)
    _write_topology(tmp_path, _group_block("g1", ["Nonexistent Component"]))
    report = classify(tmp_path)
    findings = [f for f in report["findings"] if f["check"] == "TT01"]
    assert len(findings) == 1
    assert findings[0]["severity"] == "fail"


def test_tt01_flags_non_built_status(tmp_path: Path) -> None:
    """Golden bad-case: the component exists but its Status is not Built."""
    _write_design(tmp_path, [("Rules", "Designed")])
    _write_trunk_leaf(tmp_path)
    _write_topology(tmp_path, _group_block("g1", ["Rules"]))
    report = classify(tmp_path)
    findings = [f for f in report["findings"] if f["check"] == "TT01"]
    assert len(findings) == 1


def test_tt01_built_subsystem_is_clean(tmp_path: Path) -> None:
    _write_design(tmp_path, [("Skills", "Built")])
    _write_trunk_leaf(tmp_path)
    _write_topology(tmp_path, _group_block("g1", ["Skills"]))
    report = classify(tmp_path)
    assert [f for f in report["findings"] if f["check"] == "TT01"] == []


def test_tt01_mixed_built_status_text_is_clean(tmp_path: Path) -> None:
    """A 'Built (current state) / Designed (...)' status still contains 'Built'."""
    _write_design(tmp_path, [("Rules", "Built (current state) / Designed (manifest)")])
    _write_trunk_leaf(tmp_path)
    _write_topology(tmp_path, _group_block("g1", ["Rules"]))
    report = classify(tmp_path)
    assert [f for f in report["findings"] if f["check"] == "TT01"] == []


# -- TT02: selector strategy registration -------------------------------------


def test_tt02_flags_unregistered_strategy(tmp_path: Path) -> None:
    """Golden bad-case: a strategy not in Registry 1 at all."""
    _write_design(tmp_path, [("Skills", "Built")])
    _write_trunk_leaf(tmp_path)
    _write_topology(tmp_path, _group_block("g1", ["Skills"], strategy="totally-bogus"))
    report = classify(tmp_path)
    findings = [f for f in report["findings"] if f["check"] == "TT02"]
    assert len(findings) == 1
    assert findings[0]["severity"] == "fail"


def test_tt02_flags_optional_strategy_as_warn(tmp_path: Path) -> None:
    _write_design(tmp_path, [("Skills", "Built")])
    _write_trunk_leaf(tmp_path)
    _write_topology(tmp_path, _group_block("g1", ["Skills"], strategy="pytest-keywords"))
    report = classify(tmp_path)
    findings = [f for f in report["findings"] if f["check"] == "TT02"]
    assert len(findings) == 1
    assert findings[0]["severity"] == "warn"


def test_tt02_registered_non_optional_strategy_is_clean(tmp_path: Path) -> None:
    _write_design(tmp_path, [("Skills", "Built")])
    _write_trunk_leaf(tmp_path)
    _write_topology(tmp_path, _group_block("g1", ["Skills"], strategy="pytest-globs"))
    report = classify(tmp_path)
    assert [f for f in report["findings"] if f["check"] == "TT02"] == []


# -- TT05: marker-name consistency and reserved-name compliance --------------


def test_tt05_flags_reserved_name_collision(tmp_path: Path) -> None:
    """Golden bad-case: group id 'integration' snake-cases to a reserved tier keyword."""
    _write_design(tmp_path, [("Skills", "Built")])
    _write_trunk_leaf(tmp_path)
    _write_python_leaf(tmp_path)
    _write_topology(tmp_path, _group_block("integration", ["Skills"], strategy="pytest-markers"))
    report = classify(tmp_path)
    findings = [f for f in report["findings"] if f["check"] == "TT05"]
    assert len(findings) == 1
    assert "reserved-name" in findings[0]["message"]


def test_tt05_flags_unregistered_marker(tmp_path: Path) -> None:
    """Golden bad-case: marker-selector group id absent from pyproject.toml's markers list."""
    _write_design(tmp_path, [("Skills", "Built")])
    _write_trunk_leaf(tmp_path)
    _write_python_leaf(tmp_path)
    _write(
        tmp_path / "pyproject.toml",
        '[tool.pytest.ini_options]\nmarkers = ["some_other_group: desc"]\n',
    )
    _write_topology(tmp_path, _group_block("my-group", ["Skills"], strategy="pytest-markers"))
    report = classify(tmp_path)
    findings = [f for f in report["findings"] if f["check"] == "TT05"]
    assert len(findings) == 1
    assert "not registered" in findings[0]["message"]


def test_tt05_registered_marker_is_clean(tmp_path: Path) -> None:
    _write_design(tmp_path, [("Skills", "Built")])
    _write_trunk_leaf(tmp_path)
    _write_python_leaf(tmp_path)
    _write(
        tmp_path / "pyproject.toml",
        '[tool.pytest.ini_options]\nmarkers = ["my_group: desc"]\n',
    )
    _write_topology(tmp_path, _group_block("my-group", ["Skills"], strategy="pytest-markers"))
    report = classify(tmp_path)
    assert [f for f in report["findings"] if f["check"] == "TT05"] == []


def test_tt05_no_marker_selector_groups_is_a_noop(tmp_path: Path) -> None:
    _write_design(tmp_path, [("Skills", "Built")])
    _write_trunk_leaf(tmp_path)
    _write_topology(tmp_path, _group_block("g1", ["Skills"], strategy="pytest-globs"))
    report = classify(tmp_path)
    assert [f for f in report["findings"] if f["check"] == "TT05"] == []


# -- TT06: topology-less growth-trigger advisory ------------------------------


def _write_many_tests(tmp_path: Path, count: int) -> None:
    body = "\n".join(f"def test_n{i}():\n    pass\n" for i in range(count))
    _write(tmp_path / "tests" / "test_bulk.py", body)


def test_tt06_skips_when_topology_present(tmp_path: Path) -> None:
    _write_topology(tmp_path, _group_block("g1", ["Skills"]))
    report = classify(tmp_path)
    assert [f for f in report["findings"] if f["check"] == "TT06"] == []
    assert report["examined"]["TT06"]["reason"] == "topology-present"


def test_tt06_missing_design_doc_withholds_component_term(tmp_path: Path) -> None:
    """No TEST_TOPOLOGY.md and no DESIGN.md -- the component-count term withholds."""
    report = classify(tmp_path)
    assert (
        "Built structural components (DESIGN.md absent)"
        in report["examined"]["TT06"]["withheld_terms"]
    )
    assert report["examined"]["TT06"]["component_count"] is None


def test_tt06_below_threshold_signals_do_not_flag(tmp_path: Path) -> None:
    _write_design(tmp_path, [("Skills", "Built")])
    report = classify(tmp_path)
    assert [f for f in report["findings"] if f["check"] == "TT06"] == []


def test_tt06_flags_all_thresholds_crossed(monkeypatch, tmp_path: Path) -> None:
    """Golden bad-case: all three growth signals confirmed crossed -> INFO advisory.

    Monkeypatches `_recorded_full_suite_runtime` (the seam named in the module
    docstring) rather than inventing a `.ai-state/` file format, since no such
    format exists yet -- see that function's own docstring.
    """
    monkeypatch.setattr(topo, "_recorded_full_suite_runtime", lambda repo_root: 95.0)
    _write_design(tmp_path, [(f"Component{i}", "Built") for i in range(5)])
    _write_many_tests(tmp_path, 210)
    report = classify(tmp_path)
    findings = [f for f in report["findings"] if f["check"] == "TT06"]
    assert len(findings) == 1
    assert findings[0]["severity"] == "info"
    for term in ("wall-clock", "Built structural components", "test count"):
        assert term in findings[0]["message"]


def test_tt06_two_of_three_crossed_without_runtime_does_not_flag(tmp_path: Path) -> None:
    """Component count and test count cross, but runtime is always withheld today --
    the advisory must not fire on partial evidence."""
    _write_design(tmp_path, [(f"Component{i}", "Built") for i in range(5)])
    _write_many_tests(tmp_path, 210)
    report = classify(tmp_path)
    assert [f for f in report["findings"] if f["check"] == "TT06"] == []
    assert "full-suite wall-clock runtime" in report["examined"]["TT06"]["withheld_terms"]
