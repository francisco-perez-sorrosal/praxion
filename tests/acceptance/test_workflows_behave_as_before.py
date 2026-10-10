"""Each moved workflow performs the procedure it performed before, plus the three restorations.

Equivalence is read against the frozen manifest: the procedure outline, the repository scripts
named, the documents linked, and the shared commit-process text. The restorations are read
through the harness's argument substitution: what text the model receives for a given input.
"""

from __future__ import annotations

import os
import re
import stat
import subprocess
from pathlib import Path

import pytest

from tests.acceptance.drivers.command_migration import (
    REPO_ROOT,
    canonical_fence,
    expected_link_target,
    fenced_blocks,
    fold_kind,
    heading_outline,
    link_targets,
    names,
    render,
    scripts_referenced,
    skill_text,
    workflow,
)

ALL = names()
WITH_LINKS = [n for n in ALL if workflow(n)["relative_links"]]
COMMIT_PROCESS = [n for n in ALL if workflow(n)["carries_commit_process"]]


@pytest.mark.parametrize("name", ALL)
def test_the_procedure_outline_is_the_frozen_one(name):
    frozen = [fold_kind(h) for h in workflow(name)["heading_outline"]]

    assert heading_outline(skill_text(name)) == frozen


@pytest.mark.parametrize("name", ALL)
def test_the_skill_names_the_same_repository_scripts(name):
    assert scripts_referenced(skill_text(name)) == set(workflow(name)["scripts_invoked"])


@pytest.mark.parametrize("name", WITH_LINKS)
def test_every_relative_link_reaches_the_document_it_reached_before(name):
    before = sorted(
        expected_link_target(link["resolves_to"]) for link in workflow(name)["relative_links"]
    )
    after = sorted(link_targets(skill_text(name), name))

    assert after == before
    assert all((REPO_ROOT / target).exists() for target in after), after


def test_the_workflows_carrying_the_commit_process_are_co_and_cop():
    assert sorted(COMMIT_PROCESS) == ["co", "cop"]


@pytest.mark.parametrize("name", ["co", "cop"])
def test_the_commit_process_fence_is_byte_identical_to_the_canonical_block(name):
    canonical = (REPO_ROOT / "claude" / "canonical-blocks" / "commit-process.md").read_text(
        encoding="utf-8"
    )

    assert canonical_fence(skill_text(name)) == canonical


def test_the_canonical_block_sync_check_passes():
    result = subprocess.run(
        ["python3", "scripts/sync_canonical_blocks.py", "--check"],
        cwd=REPO_ROOT, capture_output=True, text=True, timeout=120,
    )  # fmt: skip

    assert result.returncode == 0, result.stdout[-1500:] + result.stderr[-1500:]


# --- positional arguments counted from the first token ---------------------------------------

SCAFFOLD_ARGS = 'zz-probe "quux described" uv /zz/target'


def test_the_scaffolding_workflow_reads_every_typed_argument():
    rendered = render(skill_text("create-simple-python-prj"), SCAFFOLD_ARGS)

    for token in ("zz-probe", "quux described", "/zz/target"):
        assert token in rendered, f"{token!r} never reaches the model"


def test_the_scaffolding_workflow_names_the_project_after_the_first_token():
    rendered = render(skill_text("create-simple-python-prj"), SCAFFOLD_ARGS)
    naming_lines = [ln for ln in rendered.splitlines() if re.search(r"\bname", ln, re.IGNORECASE)]

    assert any("zz-probe" in ln for ln in naming_lines), naming_lines
    assert not any(
        re.search(r"project name|named", ln, re.IGNORECASE) and "quux described" in ln
        for ln in naming_lines
    ), naming_lines


def test_the_scaffolding_workflow_states_the_documented_defaults_when_only_a_name_is_typed():
    rendered = render(skill_text("create-simple-python-prj"), "zz-probe")

    assert "zz-probe" in rendered
    assert "A simple Python project scaffolding" in rendered
    assert "pixi" in rendered
    assert "$HOME/dev" in rendered


def test_the_api_documentation_workflow_reads_the_target_path_from_the_first_token():
    rendered = render(skill_text("document-api"), "zz/api/surface --lang python")

    assert "zz/api/surface" in rendered


def test_the_api_documentation_workflow_defaults_to_the_current_directory():
    rendered = render(skill_text("document-api"), "")

    assert re.search(r"current (working )?directory", rendered, re.IGNORECASE)


# --- the dashboard honours a supplied project root --------------------------------------------


def _run_dashboard_procedure(tmp_path: Path, arguments: str) -> list[str]:
    """Run the skill's shell blocks, as rendered for `arguments`, against a recording stub."""
    plugin_root = tmp_path / "plugin"
    record = tmp_path / "calls.txt"
    stub = f'#!/bin/sh\nprintf "%s\\n" "$*" >> "{record}"\n'
    for directory in (tmp_path / "work" / "scripts", plugin_root / "scripts", tmp_path / "bin"):
        directory.mkdir(parents=True, exist_ok=True)
        launcher = directory / "praxion-dashboard"
        launcher.write_text(stub, encoding="utf-8")
        launcher.chmod(launcher.stat().st_mode | stat.S_IEXEC)
    script = "\n".join(fenced_blocks(render(skill_text("dashboard"), arguments)))
    env = {
        "PATH": f"{tmp_path / 'bin'}:/usr/bin:/bin",
        "HOME": str(tmp_path),
        "CLAUDE_PLUGIN_ROOT": str(plugin_root),
        "CLAUDE_SKILL_DIR": str(plugin_root / "skills" / "dashboard"),
    }
    subprocess.run(
        ["bash", "-c", script], cwd=tmp_path / "work", env=env, capture_output=True, timeout=30
    )
    return record.read_text(encoding="utf-8").splitlines() if record.exists() else []


def test_the_dashboard_starts_for_the_project_root_the_user_supplies(tmp_path):
    calls = _run_dashboard_procedure(tmp_path, "/zz/some/project")

    assert any(re.match(r"start\s+/zz/some/project$", c) for c in calls), calls


def test_the_dashboard_starts_for_the_current_directory_when_no_root_is_supplied(tmp_path):
    calls = _run_dashboard_procedure(tmp_path, "")
    here = os.path.realpath(tmp_path / "work")

    assert any(c.startswith("start ") and os.path.realpath(c[6:].strip()) == here for c in calls), (
        calls
    )


# --- literal dollar amounts -------------------------------------------------------------------


@pytest.mark.parametrize("amount", ["50", "15"])
def test_the_eval_cost_guidance_shows_its_dollar_amounts_literally(amount):
    rendered = render(skill_text("eval-praxion"), "--mechanical-only --task-slug zz")

    assert re.search(rf"\\?\${amount}(?!\d)", rendered), f"${amount} is substituted away"
