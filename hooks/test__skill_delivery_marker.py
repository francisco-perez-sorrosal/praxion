"""Tests for the marker the delivery module matches, ``hooks/_skill_delivery.py``.

The delivery module holds no grammar of its own: its ``MARKER_PATTERN`` is the plan reader's
``REFACTORING_TAG_PATTERN``. These tests pin that identity, the accepted case and spacing forms
of the marker, and the fail-open import in a plugin whose ``scripts/`` directory is absent.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

HOOKS_DIR = Path(__file__).resolve().parent
SCRIPTS_DIR = HOOKS_DIR.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import _plan_steps as plan_steps  # noqa: E402
import _skill_delivery as delivery  # noqa: E402

SUBPROCESS_TIMEOUT_SECONDS = 60
# The delivery module imports the frontmatter pattern from `_rule_delivery`, which imports
# `_project_scope`: a plugin copy without them fails on those, not on the missing plan reader.
SKILL_DELIVERY_MODULE = "_skill_delivery.py"
SKILL_DELIVERY_SIBLINGS = ("_rule_delivery.py", "_project_scope.py")


def test_marker_pattern_is_the_plan_readers_one_pattern_object():
    assert delivery.MARKER_PATTERN is plan_steps.REFACTORING_TAG_PATTERN
    assert plan_steps.REFACTORING_TAG_PATTERN is plan_steps._REFACTORING_TAG_RE


@pytest.mark.parametrize(
    "marker",
    [
        "[Phase: Refactoring]",
        "[phase: refactoring]",
        "[PHASE:REFACTORING]",
        "[ Phase :  Refactoring ]",
        "[\tphase\t:\trefactoring\t]",
    ],
)
def test_marker_matches_its_case_and_spacing_forms(marker):
    assert delivery.MARKER_PATTERN.search(marker) is not None


@pytest.mark.parametrize(
    "text",
    [
        "[Phase: Refactor]",
        "Phase: Refactoring",
        "[Phase: Refactoring extra]",
        "[Architecture]",
    ],
)
def test_marker_does_not_match_other_text(text):
    assert delivery.MARKER_PATTERN.search(text) is None


def test_delivery_imports_fail_open_when_the_plugin_has_no_plan_reader(tmp_path):
    plugin_hooks = tmp_path / "hooks"
    plugin_hooks.mkdir()
    for module in (SKILL_DELIVERY_MODULE, *SKILL_DELIVERY_SIBLINGS):
        shutil.copy(HOOKS_DIR / module, plugin_hooks / module)
    probe = (
        "import json, sys; sys.path.insert(0, sys.argv[1]); import _skill_delivery as d; "
        "print(json.dumps([d.MARKER_PATTERN is None, d.MARKER_IMPORT_ERROR]))"
    )

    result = subprocess.run(
        [sys.executable, "-I", "-c", probe, str(plugin_hooks)],
        capture_output=True,
        text=True,
        check=True,
        cwd=tmp_path,
        timeout=SUBPROCESS_TIMEOUT_SECONDS,
    )

    pattern_is_none, import_error = json.loads(result.stdout)
    assert pattern_is_none is True
    assert "_plan_steps" in import_error
