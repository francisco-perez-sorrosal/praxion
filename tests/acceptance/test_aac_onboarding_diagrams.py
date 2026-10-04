"""A freshly onboarded project starts at the same diagram bar and the same drift gate.

Onboarding with the architecture-as-code capability installs a category vocabulary
(at least Person, System in scope, External system, Container, Component and Data
store, under those exact names, each with its drawing and legend entry), an example view, and one
documented command that regenerates the renders locally. The example's renders pass
every review check; a second onboarding run changes no file; the project's CI drift
gate pins the toolchain version Praxion pins, fails a drifted render and passes
matching ones.
"""

from __future__ import annotations

import hashlib
import subprocess

import pytest

from tests.acceptance.drivers.aac_onboarding import (
    model_workspace,
    onboard_with_aac,
    regeneration_command,
    render_dir,
)
from tests.acceptance.drivers.architecture_model import category_of, export_model, offline_env
from tests.acceptance.drivers.diagram_regen import (
    DRIFT_JOB,
    drift_gate_pins,
    drift_gate_steps,
    git,
    pins_in_workflow,
    require_pinned_toolchain,
    run_steps,
)
from tests.acceptance.drivers.diagram_rules import ONBOARDING_WORKFLOW_TEMPLATE
from tests.acceptance.drivers.render_review import (
    ONBOARDED_VOCABULARY,
    all_render_check_violations,
    vocabulary_violations,
)


def _fresh_project(path):
    path.mkdir(parents=True)
    git(path, "init", "-q", "-b", "main")
    (path / "README.md").write_text("fresh project\n", encoding="utf-8")
    git(path, "add", "README.md")
    git(path, "commit", "-q", "--no-verify", "-m", "initial")
    return path


def _regenerate(project):
    result = subprocess.run(
        ["bash", "-c", regeneration_command(project)],
        cwd=project,
        env=offline_env(),
        capture_output=True,
        text=True,
        timeout=600,
    )
    assert result.returncode == 0, (
        f"the documented regeneration command failed:\n{result.stdout}{result.stderr}"
    )


def _tree_digest(project):
    return {
        str(path.relative_to(project)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(project.rglob("*"))
        if path.is_file() and ".git" not in path.relative_to(project).parts
    }


@pytest.fixture
def onboarded(tmp_path):
    project = _fresh_project(tmp_path / "project")
    onboard_with_aac(project)
    return project


@pytest.fixture
def regenerated(onboarded):
    require_pinned_toolchain()
    _regenerate(onboarded)
    return onboarded


def test_onboarding_installs_a_vocabulary_covering_the_c4_floor(onboarded) -> None:
    model = export_model(model_workspace(onboarded))

    categories = [category_of(element) for element in model.elements.values()]

    assert vocabulary_violations(categories, ONBOARDED_VOCABULARY) == []


def test_the_documented_command_regenerates_the_example_view_renders(regenerated) -> None:
    assert sorted(render_dir(regenerated).glob("*.svg")), (
        "the regeneration command produced no render"
    )


def test_the_onboarded_example_renders_pass_every_review_check(regenerated) -> None:
    model = export_model(model_workspace(regenerated))

    assert all_render_check_violations(render_dir(regenerated), model, category_of) == []


def test_a_second_onboarding_run_changes_no_file(onboarded) -> None:
    before = _tree_digest(onboarded)

    onboard_with_aac(onboarded)

    assert _tree_digest(onboarded) == before


def test_the_onboarding_drift_gate_template_pins_the_toolchain_praxion_pins() -> None:
    assert pins_in_workflow(ONBOARDING_WORKFLOW_TEMPLATE, DRIFT_JOB) == drift_gate_pins()


def test_the_onboarded_drift_gate_passes_matching_renders_and_fails_a_drifted_one(
    regenerated,
) -> None:
    git(regenerated, "add", "-A")
    git(regenerated, "commit", "-q", "--no-verify", "-m", "onboarded with renders")
    steps = drift_gate_steps(regenerated)
    matching = run_steps(regenerated, steps)
    drifted = sorted(render_dir(regenerated).glob("*.svg"))[0]
    drifted.write_text(drifted.read_text(encoding="utf-8") + "<!-- drift -->\n", encoding="utf-8")
    git(regenerated, "commit", "-q", "--no-verify", "-am", "drift one render")

    after_drift = run_steps(regenerated, steps)

    assert matching.returncode == 0, (
        f"the gate failed matching renders at {matching.failed_step}:\n{matching.output[-1500:]}"
    )
    assert after_drift.returncode != 0, "the gate passed a drifted render"
