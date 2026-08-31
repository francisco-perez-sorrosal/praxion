"""Tests for check_architecture_projection.py -- DESIGN.md against its two authorities.

Cites: rules/swe/gate-liveness.md -- a CODE gate ships a canary proving it bites
on a known-bad input, not merely that it passes on the current good state.

The structural canaries are drawn from real drift. All four shapes existed
simultaneously in this repository and went unnoticed for months, because the
two descriptions had no mechanical binding: a model element with no row, a row
naming no element, over-granular modelling, and a row pointing at an element
that does not exist. The gate was written against that live known-bad state and
reproduced all four before any of them was fixed.

The published-half canaries guard a larger blast radius. A canonical block is
installed into every managed project's own CLAUDE.md, so a block shipping with
no row means N repositories carry content this project does not record. The
withholding canary matters most there: an unreadable registry must withhold,
never report that nothing ships, because the empty reading inverts every
finding at once.
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
    report = cap.check_projection(repo, block_slugs=())
    assert report["findings"] == []
    assert (report["elements"], report["rows"]) == (3, 3)


def test_canary_model_element_with_no_row(repo: Path) -> None:
    """The live shape: a model element documented nowhere carries no doc contract."""
    _write_rows(
        repo,
        "| Skills | `knowledge.skills` | r | Built | f |\n| Rules | `knowledge.rules` | r | Built | f |\n",
    )
    report = cap.check_projection(repo, block_slugs=())
    assert _kinds(report) == {"element-without-row"}
    assert report["findings"][0]["subject"] == "tooling.scripts"


def test_canary_row_naming_no_element(repo: Path) -> None:
    """The live shape: a documented component carrying zero structural enforcement."""
    _write_rows(repo, ALL_THREE + "| Dashboard |  | r | Built | f |\n")
    report = cap.check_projection(repo, block_slugs=())
    assert _kinds(report) == {"row-without-element"}
    assert report["findings"][0]["subject"] == "Dashboard"


def test_canary_row_naming_an_element_that_does_not_exist(repo: Path) -> None:
    """Catches a rename on the model side that the doc did not follow."""
    _write_rows(repo, ALL_THREE + "| Ghost | `tooling.ghost` | r | Built | f |\n")
    report = cap.check_projection(repo, block_slugs=())
    assert _kinds(report) == {"unknown-element"}
    assert "tooling.ghost" in report["findings"][0]["detail"]


def test_canary_row_for_a_layer_container_is_rejected(repo: Path) -> None:
    """Layers group components; giving one a row double-counts its children."""
    _write_rows(repo, ALL_THREE + "| Knowledge Layer | `knowledge` | r | Built | f |\n")
    report = cap.check_projection(repo, block_slugs=())
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
    assert cap.check_projection(repo, block_slugs=())["findings"] == []


# -- The published half -------------------------------------------------------
#
# Section 4 documents the blocks installed into every managed project's own
# CLAUDE.md. Those rows carry the highest blast radius in the repo, and the
# shipped-block registry is their authority.


def _with_section_4(repo: Path, block_rows: str) -> None:
    (repo / cap._DESIGN).write_text(
        _design(ALL_THREE) + "\n## 4. Interfaces\n\n| Interface | Type |\n|---|---|\n" + block_rows,
        encoding="utf-8",
    )


def test_documented_blocks_matching_the_registry_agree(repo: Path) -> None:
    _with_section_4(repo, "| Canonical block: `alpha` | Markdown |\n")
    assert cap.check_projection(repo, block_slugs=("alpha",))["findings"] == []


def test_canary_shipped_block_missing_from_the_interfaces_table(repo: Path) -> None:
    """A block reaching N projects with nothing documenting it."""
    _with_section_4(repo, "| Canonical block: `alpha` | Markdown |\n")
    report = cap.check_projection(repo, block_slugs=("alpha", "beta"))
    assert _kinds(report) == {"block-without-row"}
    assert report["findings"][0]["subject"] == "beta"


def test_canary_interfaces_table_documents_a_block_that_does_not_ship(repo: Path) -> None:
    """The mirror: a retired block still advertised as part of the contract."""
    _with_section_4(
        repo, "| Canonical block: `alpha` | Markdown |\n| Canonical block: `ghost` | M |\n"
    )
    report = cap.check_projection(repo, block_slugs=("alpha",))
    assert _kinds(report) == {"row-without-block"}
    assert report["findings"][0]["subject"] == "ghost"


def test_canary_unreadable_registry_withholds_rather_than_claiming_nothing_ships(
    repo: Path,
) -> None:
    """Withhold, never default -- an import failure must not read as "no contract".

    Reporting an empty registry would flag every documented block as bogus and
    invert the finding, which is the worst way for this check to fail.
    """
    _with_section_4(repo, "| Canonical block: `alpha` | Markdown |\n")
    report = cap.check_projection(repo, block_slugs=None)
    assert report["findings"] == []
    assert any("registry could not be read" in w for w in report["withheld"])


def test_absent_substrate_skips_rather_than_failing(repo: Path) -> None:
    """A project with no model must not be reported as fully drifted."""
    (repo / cap._MODEL).unlink()
    report = cap.check_projection(repo, block_slugs=())
    assert report["findings"] == []
    assert "substrate absent" in report["skipped"]


def test_exit_code_is_nonzero_only_when_findings_exist(repo: Path) -> None:
    """It doubles as a commit gate, so the exit code is the contract.

    Run through the CLI, which resolves the shipped-block registry rather than
    an injected one -- so section 4 is built from that registry here. Copying
    the real registry in keeps the fixture honest as blocks are added or
    retired, and exercises the registry lookup the in-process tests bypass.
    """
    script = str(Path(cap.__file__))
    rows = "".join(
        f"| Canonical block: `{slug}` | Markdown |\n" for slug in _install_registry(repo)
    )
    section_4 = "\n## 4. Interfaces\n\n| Interface | Type |\n|---|---|\n" + rows

    (repo / cap._DESIGN).write_text(_design(ALL_THREE) + section_4, encoding="utf-8")
    clean = subprocess.run(
        [sys.executable, script, "--repo-root", str(repo)], capture_output=True, check=False
    )
    (repo / cap._DESIGN).write_text(
        _design(ALL_THREE + "| Ghost | `tooling.ghost` | r | Built | f |\n") + section_4,
        encoding="utf-8",
    )
    dirty = subprocess.run(
        [sys.executable, script, "--repo-root", str(repo)], capture_output=True, check=False
    )
    assert (clean.returncode, dirty.returncode) == (0, 1), clean.stdout + dirty.stdout


def _install_registry(repo: Path) -> tuple[str, ...]:
    """Copy this repo's real shipped-block registry into *repo*; return its slugs.

    The checker resolves the registry from the tree under inspection, so an
    end-to-end run needs one there. Copying the real file rather than writing a
    synthetic one keeps the fixture honest as blocks are added or retired.
    """
    source = Path(cap.__file__).parent / cap._REGISTRY.name
    target = repo / cap._REGISTRY
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
    slugs = cap.canonical_block_slugs(repo)
    assert slugs, "precondition: the copied registry must parse"
    return slugs


def test_the_registry_is_read_from_the_tree_under_inspection(repo: Path) -> None:
    """`--repo-root` must relocate every authority, not just some of them.

    Reading the registry from the running copy while reading the design doc from
    `--repo-root` reconciles one tree's document against another tree's shipped
    contract -- a wrong answer that presents as a clean run.
    """
    registry = repo / cap._REGISTRY
    registry.parent.mkdir(parents=True, exist_ok=True)
    registry.write_text('BLOCKS = {"only-in-this-tree": 1}\n', encoding="utf-8")

    assert cap.canonical_block_slugs(repo) == ("only-in-this-tree",)


def test_canary_a_registry_with_a_computed_key_withholds_rather_than_part_reading(
    repo: Path,
) -> None:
    """A partial read is a wrong answer, not a smaller one, so it must withhold.

    Returning the literal keys and dropping the computed one would report every
    undropped block as documented and the dropped one as never shipped -- the
    same inversion an unreadable registry would cause, but harder to notice
    because most of the answer is right.
    """
    registry = repo / cap._REGISTRY
    registry.parent.mkdir(parents=True, exist_ok=True)
    registry.write_text('COMPUTED = "b"\nBLOCKS = {"a": 1, COMPUTED: 2}\n', encoding="utf-8")

    assert cap.canonical_block_slugs(repo) is None


def test_tolerates_a_registry_entry_with_a_single_element_consumers_tuple(repo: Path) -> None:
    """Forward cover for the onboarding-unification cut: `_ONBOARDING_PAIR` (2
    consumers) narrows to a 1-tuple once the two command files retire in favor
    of one skill reference file. `canonical_block_slugs()` extracts only
    `BLOCKS` dict *keys* via `ast.walk` -- it never inspects `consumers`
    contents -- so a 1-element tuple is already trivially tolerated. This pins
    that tolerance as a regression guard, not a fix for a real defect.
    """
    registry = repo / cap._REGISTRY
    registry.parent.mkdir(parents=True, exist_ok=True)
    registry.write_text(
        "from pathlib import Path\n"
        "from dataclasses import dataclass\n\n"
        "@dataclass(frozen=True)\n"
        "class BlockSpec:\n"
        "    consumers: tuple\n\n"
        "BLOCKS = {\n"
        '    "onboarding-solo": BlockSpec(consumers=(Path("skills/onboard-project/'
        'references/claude-md-blocks.md"),)),\n'
        "}\n",
        encoding="utf-8",
    )
    assert cap.canonical_block_slugs(repo) == ("onboarding-solo",)

    _with_section_4(repo, "| Canonical block: `onboarding-solo` | Markdown |\n")
    report = cap.check_projection(repo, block_slugs=("onboarding-solo",))
    assert report["findings"] == []


def test_never_edits_either_side(repo: Path) -> None:
    """Reports drift; resolving it is a human judgment about which side is right."""
    _write_rows(repo, "| Skills | `knowledge.skills` | r | Built | f |\n")
    before = ((repo / cap._MODEL).read_bytes(), (repo / cap._DESIGN).read_bytes())
    cap.check_projection(repo, block_slugs=())
    assert ((repo / cap._MODEL).read_bytes(), (repo / cap._DESIGN).read_bytes()) == before
