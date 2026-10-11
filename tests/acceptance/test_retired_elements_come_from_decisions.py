"""An element may leave the architecture model only when an accepted decision says so."""

from __future__ import annotations

from pathlib import Path

from tests.acceptance.drivers.model_coverage import retired_elements


def _decision(directory: Path, name: str, status: str, retires: str) -> None:
    (directory / name).write_text(
        f"---\nid: dec-001\nstatus: {status}\n{retires}---\n\n# Body\n", encoding="utf-8"
    )


def test_an_accepted_decision_retires_the_elements_it_names(tmp_path: Path) -> None:
    _decision(tmp_path, "001-a.md", "accepted", "retires_elements:\n  - praxion.knowledge.old\n")

    assert retired_elements(tmp_path) == {"praxion.knowledge.old"}


def test_a_decision_that_is_not_accepted_retires_nothing(tmp_path: Path) -> None:
    _decision(tmp_path, "001-a.md", "proposed", "retires_elements:\n  - praxion.knowledge.old\n")
    _decision(tmp_path, "002-b.md", "superseded", "retires_elements:\n  - praxion.knowledge.x\n")

    assert retired_elements(tmp_path) == frozenset()


def test_a_decision_without_the_field_retires_nothing(tmp_path: Path) -> None:
    _decision(tmp_path, "001-a.md", "accepted", "")

    assert retired_elements(tmp_path) == frozenset()


def test_the_commands_element_is_retired_by_a_recorded_decision() -> None:
    assert "praxion.knowledge.commands" in retired_elements()
