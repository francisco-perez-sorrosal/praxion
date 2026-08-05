"""Tests for check_architecture_projection.py -- the model <-> section-3a reconciler.

Cites: rules/swe/gate-liveness.md -- a CODE gate ships a canary proving it bites
on a known-bad input, not merely that it passes on the current good state.

The canaries here are drawn from real drift. All four shapes below existed
simultaneously in this repository and went unnoticed for months, because the
two descriptions had no mechanical binding: a model element with no row, a row
naming no element, over-granular modelling, and a row pointing at an element
that does not exist. The gate was written against that live known-bad state and
reproduced all four before any of them was fixed.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import check_architecture_projection as cap
import pytest

MODEL = """
model {
  praxion = system "Praxion" {
    knowledge = component "Knowledge Layer" {
      skills = component "Skills" { description "d" }
      rules  = component "Rules"  { description "d" }
    }
    tooling = component "Tooling" {
      scripts = component "Scripts" { description "d" }
    }
  }
}
"""

HEADER = "| Component | Element | Responsibility | Status | Key Files |\n|---|---|---|---|---|\n"


def _design(rows: str, *, heading: str = "### 3a. Structural components") -> str:
    return f"# Design\n\n## 3. Components\n\n{heading}\n\n{HEADER}{rows}\n### 3b. Capabilities\n\n| x |\n"


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    (tmp_path / "docs/diagrams/architecture/src").mkdir(parents=True)
    (tmp_path / ".ai-state").mkdir()
    (tmp_path / cap._MODEL).write_text(MODEL, encoding="utf-8")
    return tmp_path


def _write_rows(repo: Path, rows: str) -> None:
    (repo / cap._DESIGN).write_text(_design(rows), encoding="utf-8")


def _kinds(report) -> set[str]:
    return {f["kind"] for f in report["findings"]}


ALL_THREE = (
    "| Skills | `knowledge.skills` | r | Built | f |\n"
    "| Rules | `knowledge.rules` | r | Built | f |\n"
    "| Scripts | `tooling.scripts` | r | Built | f |\n"
)


def test_model_and_section_agree(repo: Path) -> None:
    _write_rows(repo, ALL_THREE)
    report = cap.reconcile(repo)
    assert report["findings"] == []
    assert (report["elements"], report["rows"]) == (3, 3)


def test_canary_model_element_with_no_row(repo: Path) -> None:
    """The live shape: a model element documented nowhere carries no doc contract."""
    _write_rows(
        repo,
        "| Skills | `knowledge.skills` | r | Built | f |\n| Rules | `knowledge.rules` | r | Built | f |\n",
    )
    report = cap.reconcile(repo)
    assert _kinds(report) == {"element-without-row"}
    assert report["findings"][0]["subject"] == "tooling.scripts"


def test_canary_row_naming_no_element(repo: Path) -> None:
    """The live shape: a documented component carrying zero structural enforcement."""
    _write_rows(repo, ALL_THREE + "| Dashboard |  | r | Built | f |\n")
    report = cap.reconcile(repo)
    assert _kinds(report) == {"row-without-element"}
    assert report["findings"][0]["subject"] == "Dashboard"


def test_canary_row_naming_an_element_that_does_not_exist(repo: Path) -> None:
    """Catches a rename on the model side that the doc did not follow."""
    _write_rows(repo, ALL_THREE + "| Ghost | `tooling.ghost` | r | Built | f |\n")
    report = cap.reconcile(repo)
    assert _kinds(report) == {"unknown-element"}
    assert "tooling.ghost" in report["findings"][0]["detail"]


def test_canary_row_for_a_layer_container_is_rejected(repo: Path) -> None:
    """Layers group components; giving one a row double-counts its children."""
    _write_rows(repo, ALL_THREE + "| Knowledge Layer | `knowledge` | r | Built | f |\n")
    report = cap.reconcile(repo)
    assert _kinds(report) == {"not-structural"}


def test_a_component_whose_children_are_all_agents_is_structural(repo: Path) -> None:
    """The pipeline holds agent elements and is still one structural component.

    A naive leaf test would drop it, losing the single busiest row in the table.
    """
    (repo / cap._MODEL).write_text(
        MODEL.replace(
            'scripts = component "Scripts" { description "d" }',
            'scripts = component "Scripts" {\n  a = agent "A" { description "d" }\n}',
        ),
        encoding="utf-8",
    )
    _write_rows(repo, ALL_THREE)
    assert cap.reconcile(repo)["findings"] == []


def test_absent_substrate_skips_rather_than_failing(repo: Path) -> None:
    """A project with no model must not be reported as fully drifted."""
    (repo / cap._MODEL).unlink()
    report = cap.reconcile(repo)
    assert report["findings"] == []
    assert "substrate absent" in report["skipped"]


def test_exit_code_is_nonzero_only_when_findings_exist(repo: Path) -> None:
    """It doubles as a commit gate, so the exit code is the contract."""
    script = str(Path(cap.__file__))
    _write_rows(repo, ALL_THREE)
    clean = subprocess.run(
        [sys.executable, script, "--repo-root", str(repo)], capture_output=True, check=False
    )
    _write_rows(repo, ALL_THREE + "| Ghost | `tooling.ghost` | r | Built | f |\n")
    dirty = subprocess.run(
        [sys.executable, script, "--repo-root", str(repo)], capture_output=True, check=False
    )
    assert (clean.returncode, dirty.returncode) == (0, 1)


def test_never_edits_either_side(repo: Path) -> None:
    """Reports drift; resolving it is a human judgment about which side is right."""
    _write_rows(repo, "| Skills | `knowledge.skills` | r | Built | f |\n")
    before = ((repo / cap._MODEL).read_bytes(), (repo / cap._DESIGN).read_bytes())
    cap.reconcile(repo)
    assert ((repo / cap._MODEL).read_bytes(), (repo / cap._DESIGN).read_bytes()) == before
