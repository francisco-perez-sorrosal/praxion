"""Canary tests for ``scripts/parse_pre_refactor_yaml.py``.

The orchestrator's mechanical evaluation of ``PRE_REFACTOR_PLAN.md`` is a CODE
gate per the gate-liveness taxonomy. These tests prove the parser:

  1. Returns a structured dict for a well-formed input (happy path).
  2. Raises ``PreRefactorYamlError(error_id="malformed-yaml")`` on a
     standalone malformed YAML body (canary — the body is run through the
     same low-level helper the section-aware parser uses).
  3. Raises ``PreRefactorYamlError(error_id="missing-section")`` on a
     `PRE_REFACTOR_PLAN.md` that omits a required section (cross-verifies
     against the sentinel ``PR01`` golden bad-case fixture).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Allow the test to import the sibling module without installing the package.
sys.path.insert(0, str(Path(__file__).parent))

import parse_pre_refactor_yaml as parser  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURES = REPO_ROOT / "tests" / "fixtures"

WELLFORMED_PLAN = FIXTURES / "pre_refactor_plan_wellformed.md"
MALFORMED_YAML_BODY = FIXTURES / "pre_refactor_yaml_malformed_braces.yaml"
MISSING_LOOPBACK_PLAN = (
    FIXTURES / "sentinel" / "pre_refactor_plan_malformed_missing_loopback.md"
)


def test_parses_wellformed_plan_into_bypass_and_loopback_lists():
    result = parser.parse(WELLFORMED_PLAN)

    assert set(result.keys()) == {"bypass", "loopback"}
    assert isinstance(result["bypass"], list) and result["bypass"], (
        "bypass list must be non-empty"
    )
    assert isinstance(result["loopback"], list) and result["loopback"], (
        "loopback list must be non-empty"
    )
    bypass_ids = {entry["id"] for entry in result["bypass"]}
    loopback_ids = {entry["id"] for entry in result["loopback"]}
    assert "behavior-preservation-tests-green" in bypass_ids
    assert "blast-radius-exceeded" in loopback_ids


def test_malformed_yaml_body_raises_structured_error():
    body = MALFORMED_YAML_BODY.read_text(encoding="utf-8")

    with pytest.raises(parser.PreRefactorYamlError) as excinfo:
        parser._parse_yaml_block(body, where="canary")

    assert excinfo.value.error_id == "malformed-yaml"


def test_missing_section_raises_structured_error():
    with pytest.raises(parser.PreRefactorYamlError) as excinfo:
        parser.parse(MISSING_LOOPBACK_PLAN)

    assert excinfo.value.error_id == "missing-section"
    assert "Loop-Back Conditions" in excinfo.value.detail
