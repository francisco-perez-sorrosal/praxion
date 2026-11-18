"""Every document that says where the liveness checks run names their own workflow.

The scripts catalog, the developer architecture guide, the design target and the root project
file (its marker list and the step loop's bound comment) name the liveness workflow. None of them
still places the checks in the scheduled test-health workflow, or the audit's traced run inside a
20-minute step limit.
"""

from __future__ import annotations

import re
import tomllib

import pytest

from tests.acceptance.drivers.liveness_workflow import (
    GATE_COMMAND,
    REPO_ROOT,
    SCHEDULED_NAME,
    liveness_workflow,
)

DOCUMENTS = ("scripts/CLAUDE.md", "docs/architecture.md", ".ai-state/DESIGN.md", "pyproject.toml")
TWENTY_MINUTES = re.compile(r"\b20[- ]minute", re.IGNORECASE)
LIVENESS_WORDS = re.compile(r"liveness|traced|selection audit|check_gates_bite", re.IGNORECASE)


def _read(relpath: str) -> str:
    return (REPO_ROOT / relpath).read_text(encoding="utf-8")


def _names(text: str) -> bool:
    workflow = liveness_workflow()
    return workflow.basename in text or (bool(workflow.name) and workflow.name in text)


def _step_loop_comment() -> str:
    lines = _read("pyproject.toml").splitlines()
    table = lines.index("[tool.praxion.step-loop]")
    above = []
    for line in reversed(lines[:table]):
        if not line.startswith("#"):
            break
        above.insert(0, line)
    return "\n".join(above)


@pytest.mark.parametrize("relpath", DOCUMENTS)
def test_the_document_names_the_liveness_workflow(relpath):
    assert _names(_read(relpath)), f"{relpath} does not name the liveness workflow"


def test_the_liveness_marker_description_names_the_liveness_workflow():
    project = tomllib.loads(_read("pyproject.toml"))
    markers = project["tool"]["pytest"]["ini_options"]["markers"]

    (description,) = [m for m in markers if m.startswith("liveness:")]

    assert _names(description), f"the liveness marker does not name its workflow: {description}"


def test_the_step_loop_bound_comment_places_no_traced_run_in_a_twenty_minute_step():
    comment = _step_loop_comment()

    assert not TWENTY_MINUTES.search(comment), f"the bound comment still says: {comment}"


@pytest.mark.parametrize("relpath", DOCUMENTS)
def test_no_document_places_the_liveness_checks_in_a_twenty_minute_step(relpath):
    stale = [
        line
        for line in _read(relpath).splitlines()
        if TWENTY_MINUTES.search(line) and LIVENESS_WORDS.search(line)
    ]

    assert stale == [], f"{relpath} still says: {stale}"


@pytest.mark.parametrize("relpath", DOCUMENTS)
def test_no_document_places_the_liveness_checks_in_the_scheduled_health_workflow(relpath):
    stale = [
        line
        for line in _read(relpath).splitlines()
        if SCHEDULED_NAME in line
        and (GATE_COMMAND in line or "liveness" in line.lower())
        and not _names(line)
    ]

    assert stale == [], f"{relpath} still places the liveness checks in {SCHEDULED_NAME}: {stale}"
