"""The Codex export of either definition lists the refactoring skill as preloaded only while the
definition preloads it; once it does not, the export points the agent at the skill for a step whose
delegation carries the marker, since no spawn-time delivery reaches a Codex agent.

Each scenario runs the Codex exporter over a copy of the plugin and reads the exported wrapper.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

from tests.acceptance.drivers import refactoring_delivery as rd
from tests.acceptance.drivers.kernel_sandbox import codex_instructions, export_codex
from tests.acceptance.drivers.refactoring_delivery import ROLES, Installation

_CONTRACT_BLOCK = re.compile(r"```yaml\n---\n(.*?)\n---\n```", re.DOTALL)
_SKILL_POINTER = re.compile(r"skills/refactoring/SKILL\.md|refactoring skill", re.IGNORECASE)


def _exported(installation: Installation, out: Path, role: str) -> str:
    return codex_instructions(export_codex(installation.root, out)[role])


def _contract_preloads(instructions: str) -> list[str]:
    block = _CONTRACT_BLOCK.search(instructions)
    assert block, "the Codex wrapper carries no frontmatter contract block"
    return list((yaml.safe_load(block.group(1)) or {}).get("skills") or [])


def _outside_contract(instructions: str) -> str:
    return _CONTRACT_BLOCK.sub("", instructions)


@pytest.fixture
def installation(tmp_path: Path) -> Installation:
    return rd.new_installation(tmp_path / "plugin")


@pytest.mark.parametrize("role", ROLES)
def test_the_codex_export_lists_the_skill_as_preloaded_while_the_definition_preloads_it(
    installation: Installation, tmp_path: Path, role: str
) -> None:
    rd.with_preload(installation, role)

    instructions = _exported(installation, tmp_path / "codex", role)

    assert rd.SKILL_NAME in _contract_preloads(instructions)


@pytest.mark.parametrize("role", ROLES)
def test_after_the_move_the_codex_export_lists_no_refactoring_preload(
    installation: Installation, tmp_path: Path, role: str
) -> None:
    rd.apply_the_move(installation)

    instructions = _exported(installation, tmp_path / "codex", role)

    assert rd.SKILL_NAME not in _contract_preloads(instructions)


@pytest.mark.parametrize("role", ROLES)
def test_after_the_move_the_codex_export_points_a_marked_step_at_the_skill(
    installation: Installation, tmp_path: Path, role: str
) -> None:
    rd.apply_the_move(installation)

    prose = _outside_contract(_exported(installation, tmp_path / "codex", role))

    assert rd.mentions_marker(prose), "the Codex wrapper never names the refactoring marker"
    assert _SKILL_POINTER.search(prose), "the Codex wrapper never points at the refactoring skill"
