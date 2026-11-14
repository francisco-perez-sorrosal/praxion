"""Tests for `refactoring_move.py` -- the reversible move of the refactoring skill.

Every scenario moves temporary copies of the live definitions; none writes to the checkout.
The copies are first brought to the preloaded state by the tool itself, so the scenarios hold
whether the checkout is still preloaded or the move has since been applied to it.
"""

from __future__ import annotations

import importlib.util
import re
import shutil
import sys
from pathlib import Path

import pytest
import yaml

# The checkout root is found by a marker, not by counting parents: the mutation sensor runs this
# file from a `mutants/` copy one directory deeper.
LIVE_ROOT = next(
    p for p in Path(__file__).resolve().parents if (p / "agents" / "implementer.md").is_file()
)
sys.path.append(str(LIVE_ROOT / "hooks"))
sys.path.append(str(LIVE_ROOT / "scripts"))

import _skill_delivery as delivery  # noqa: E402
import refactoring_move as move  # noqa: E402

ROLES = ("implementer", "test-engineer")
SKILL = "refactoring"
EXPORTER = LIVE_ROOT / "codex" / "config" / "export-codex-agents.py"


def _definition(root: Path, role: str) -> Path:
    return root / "agents" / f"{role}.md"


def _snapshot(root: Path) -> dict[str, bytes]:
    return {role: _definition(root, role).read_bytes() for role in ROLES}


def _edit(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    assert old in text, f"{path.name} does not hold the text to edit"
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


def _run(root: Path, to: str, *flags: str) -> int:
    return move.main(["--to", to, "--root", str(root), *flags])


def _preloaded_skills(root: Path, role: str) -> list[str]:
    text = _definition(root, role).read_text(encoding="utf-8")
    frontmatter = text.split("\n---\n", 1)[0].removeprefix("---\n")
    return list(yaml.safe_load(frontmatter)["skills"])


def _wrapper_passages(root: Path, role: str) -> list[str]:
    spec = importlib.util.spec_from_file_location("export_codex_agents", EXPORTER)
    assert spec is not None
    assert spec.loader is not None
    exporter = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(exporter)
    path = _definition(root, role)
    return exporter.extract_wrapper_passages(path.read_text(encoding="utf-8"), path)


@pytest.fixture
def preloaded(tmp_path: Path) -> Path:
    for role in ROLES:
        _definition(tmp_path, role).parent.mkdir(exist_ok=True)
        shutil.copyfile(_definition(LIVE_ROOT, role), _definition(tmp_path, role))
    assert _run(tmp_path, "preloaded") == 0
    return tmp_path


# -- The live definitions ----------------------------------------------------------------------


def test_the_live_definitions_hold_one_state_wholly() -> None:
    preloaded_holds = _run(LIVE_ROOT, "preloaded", "--check") == 0
    delivered_holds = _run(LIVE_ROOT, "delivered", "--check") == 0

    assert preloaded_holds != delivered_holds, "the live definitions hold neither state wholly"


# -- What each state means for the preload reader ---------------------------------------------


@pytest.mark.parametrize("role", ROLES)
def test_the_preloaded_state_reads_as_preloaded(preloaded: Path, role: str) -> None:
    assert delivery.preload_state(preloaded, role) == delivery.Preloaded()


@pytest.mark.parametrize("role", ROLES)
def test_the_delivered_state_reads_as_not_preloaded(preloaded: Path, role: str) -> None:
    assert _run(preloaded, "delivered") == 0

    assert delivery.preload_state(preloaded, role) == delivery.NotPreloaded()


@pytest.mark.parametrize("role", ROLES)
def test_the_delivered_state_drops_only_the_refactoring_preload(preloaded: Path, role: str) -> None:
    before = _preloaded_skills(preloaded, role)

    _run(preloaded, "delivered")

    assert SKILL in before
    assert _preloaded_skills(preloaded, role) == [s for s in before if s != SKILL]


# -- Reversal and idempotence ------------------------------------------------------------------


def test_moving_to_delivered_and_back_restores_the_bytes(preloaded: Path) -> None:
    original = _snapshot(preloaded)

    assert _run(preloaded, "delivered") == 0
    assert _snapshot(preloaded) != original
    assert _run(preloaded, "preloaded") == 0

    assert _snapshot(preloaded) == original


@pytest.mark.parametrize("state", move.STATES)
def test_applying_a_state_already_held_changes_nothing(preloaded: Path, state: str) -> None:
    _run(preloaded, state)
    held = _snapshot(preloaded)

    assert _run(preloaded, state) == 0

    assert _snapshot(preloaded) == held


def test_applying_reports_each_definition_it_moved_and_a_held_state_as_held(
    preloaded: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _run(preloaded, "delivered")
    moved_report = capsys.readouterr().out.splitlines()

    _run(preloaded, "delivered")
    held_report = capsys.readouterr().out.splitlines()

    assert moved_report == [
        "refactoring-move: moved agents/implementer.md to delivered",
        "refactoring-move: moved agents/test-engineer.md to delivered",
    ]
    assert held_report == ["refactoring-move: already delivered"]


# -- --check -----------------------------------------------------------------------------------


def test_check_exits_1_when_the_state_differs_and_writes_nothing(
    preloaded: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    original = _snapshot(preloaded)

    assert _run(preloaded, "delivered", "--check") == 1

    assert _snapshot(preloaded) == original
    assert capsys.readouterr().out.splitlines() == [
        "refactoring-move: agents/implementer.md does not hold the delivered state",
        "refactoring-move: agents/test-engineer.md does not hold the delivered state",
    ]


def test_check_exits_0_when_the_state_holds(preloaded: Path) -> None:
    assert _run(preloaded, "preloaded", "--check") == 0
    _run(preloaded, "delivered")

    assert _run(preloaded, "delivered", "--check") == 0


# -- Drift -------------------------------------------------------------------------------------

SITE_AND_TARGET = [
    pytest.param(site, to, id=f"{site.definition.split('/')[1]}-{site.name}-to-{to}")
    for site in move.SITES
    for to in move.STATES
]


@pytest.mark.parametrize(("site", "to"), SITE_AND_TARGET)
def test_a_drifted_site_is_refused_by_name_and_nothing_is_written(
    preloaded: Path, capsys: pytest.CaptureFixture[str], site: move.Site, to: str
) -> None:
    # Start from the state opposite to the target, so the move has work to do at every site.
    start = "delivered" if to == "preloaded" else "preloaded"
    _run(preloaded, start)
    _edit(preloaded / site.definition, site.text(start), "edited elsewhere")
    before = _snapshot(preloaded)

    assert _run(preloaded, to) == 1

    assert _snapshot(preloaded) == before
    assert capsys.readouterr().err.splitlines() == [
        f"refactoring-move: DRIFT -- {site.definition} ({site.name}): neither the preloaded nor "
        "the delivered text is found exactly once"
    ]


def test_a_text_found_twice_is_drift_not_a_guess(
    preloaded: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    site = move.SITES[0]
    _edit(preloaded / site.definition, site.preloaded, f"{site.preloaded}\n{site.preloaded}")

    assert _run(preloaded, "delivered") == 1

    assert site.name in capsys.readouterr().err


def test_every_drifted_site_is_named_in_one_run(
    preloaded: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _edit(_definition(preloaded, "implementer"), "skills: [software", "skills: [x, software")
    _edit(_definition(preloaded, "test-engineer"), "skills: [software", "skills: [x, software")

    assert _run(preloaded, "delivered") == 1

    err = capsys.readouterr().err
    assert "agents/implementer.md (skills list)" in err
    assert "agents/test-engineer.md (skills list)" in err


# -- Usage errors ------------------------------------------------------------------------------


@pytest.mark.parametrize("argv", [[], ["--to", "elsewhere"], ["--to"], ["--unknown"]])
def test_a_malformed_command_line_exits_2(argv: list[str]) -> None:
    with pytest.raises(SystemExit) as exit_info:
        move.main(argv)

    assert exit_info.value.code == 2


def test_a_root_without_the_definitions_is_a_usage_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert _run(tmp_path, "delivered") == 2

    assert capsys.readouterr().err.startswith("refactoring-move: ERROR -- ")


# -- What the move writes ----------------------------------------------------------------------

_EPHEMERAL = re.compile(
    r"\bdec-\d+|\bdec-draft|\bREQ-\d+|\bAC-\d+|\bStep \d+|\.ai-work|"
    r"\b(?:WIP|LEARNINGS|IMPLEMENTATION_PLAN|SYSTEMS_PLAN|CONTEXT_REVIEW|TASK_BRIEF)\.md"
)


@pytest.mark.parametrize("site", move.SITES, ids=lambda s: f"{s.definition}-{s.name}")
def test_the_delivered_texts_cite_no_decision_number_or_pipeline_file(site: move.Site) -> None:
    assert _EPHEMERAL.search(site.delivered) is None


def test_the_phase_tag_sentence_is_state_neutral_wording() -> None:
    (site,) = [s for s in move.SITES if s.name == "phase-tag sentence"]

    assert "always-loaded" in site.preloaded
    assert "always-loaded" not in site.delivered
    assert "preloaded by your frontmatter or delivered with the delegation" in site.delivered


# -- The Codex passage -------------------------------------------------------------------------


@pytest.mark.parametrize("role", ROLES)
def test_the_delivered_state_marks_one_codex_passage_naming_the_marker_and_the_skill(
    preloaded: Path, role: str
) -> None:
    named = [p for p in _wrapper_passages(preloaded, role) if "skills/refactoring/SKILL.md" in p]
    assert named == []

    _run(preloaded, "delivered")

    (passage,) = [p for p in _wrapper_passages(preloaded, role) if "[Phase: Refactoring]" in p]
    assert "skills/refactoring/SKILL.md" in passage
    assert "not already in your context" in passage


@pytest.mark.parametrize("site", [s for s in move.SITES if s.name == "Codex passage"], ids=str)
def test_the_codex_passage_stands_in_its_own_paragraph_after_its_anchor(
    preloaded: Path, site: move.Site
) -> None:
    _run(preloaded, "delivered")

    text = (preloaded / site.definition).read_text(encoding="utf-8")

    assert f"{site.preloaded}\n\n<!-- codex-wrapper:begin -->\nA step whose" in text
    assert "the step.\n<!-- codex-wrapper:end -->\n" in text
