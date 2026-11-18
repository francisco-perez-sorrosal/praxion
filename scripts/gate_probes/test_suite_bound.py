"""Tests for `suite_bound.py` -- the one reader of the selection audit's declared bound.

The failure mode this closes: an audit that borrows another gate's bound, or runs unbounded
because a typo in the declaration was read as "nothing declared". Each broken declaration must
come back `Undeclared` and name the cause; expected values come from the module's contract.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Flat import (siblings by bare name), the layout the mutation sensor reads.
sys.path.insert(0, str(Path(__file__).resolve().parent))

import suite_bound  # noqa: E402
from suite_bound import Declared, Undeclared, read_audit_bound  # noqa: E402

KEY = "selection-audit-timeout-seconds"


def _project(tmp_path: Path, text: str) -> Path:
    (tmp_path / "pyproject.toml").write_text(text, encoding="utf-8")
    return tmp_path


def _declaring(value: str) -> str:
    return f"[tool.praxion.gate-liveness]\n{KEY} = {value}\n"


def test_a_positive_whole_number_is_declared(tmp_path):
    assert read_audit_bound(_project(tmp_path, _declaring("5400"))) == Declared(5400)


def test_one_second_is_the_smallest_declared_bound(tmp_path):
    assert read_audit_bound(_project(tmp_path, _declaring("1"))) == Declared(1)


def test_the_step_loops_bound_is_never_a_fallback(tmp_path):
    root = _project(tmp_path, "[tool.praxion.step-loop]\ngate-timeout-seconds = 1500\n")

    bound = read_audit_bound(root)

    assert isinstance(bound, Undeclared)
    assert "[tool.praxion.gate-liveness]" in bound.reason


def test_a_table_name_holding_a_value_instead_of_a_table_is_undeclared(tmp_path):
    root = _project(tmp_path, '[tool]\npraxion = "not a table"\n')

    bound = read_audit_bound(root)

    assert isinstance(bound, Undeclared)
    assert "[tool.praxion.gate-liveness]" in bound.reason


def test_a_table_without_the_key_is_undeclared_and_names_it(tmp_path):
    root = _project(tmp_path, "[tool.praxion.gate-liveness]\nother = 1\n")

    bound = read_audit_bound(root)

    assert isinstance(bound, Undeclared)
    assert KEY in bound.reason
    assert "missing" in bound.reason


@pytest.mark.parametrize("value", ['"5400"', "5400.0", "true", "[5400]"])
def test_a_value_that_is_not_a_whole_number_is_undeclared(tmp_path, value):
    bound = read_audit_bound(_project(tmp_path, _declaring(value)))

    assert isinstance(bound, Undeclared)
    assert "whole number" in bound.reason


@pytest.mark.parametrize("value", ["0", "-60"])
def test_a_value_of_zero_or_less_is_undeclared(tmp_path, value):
    bound = read_audit_bound(_project(tmp_path, _declaring(value)))

    assert isinstance(bound, Undeclared)
    assert "above zero" in bound.reason


def test_a_file_that_is_not_toml_is_undeclared(tmp_path):
    bound = read_audit_bound(_project(tmp_path, "[tool.praxion\nnot toml"))

    assert isinstance(bound, Undeclared)
    assert "not TOML" in bound.reason


def test_a_file_that_is_not_text_is_undeclared(tmp_path):
    (tmp_path / "pyproject.toml").write_bytes(b"\xff\xfe\x00")

    bound = read_audit_bound(tmp_path)

    assert isinstance(bound, Undeclared)
    assert "not TOML" in bound.reason


def test_a_missing_file_is_undeclared(tmp_path):
    bound = read_audit_bound(tmp_path)

    assert isinstance(bound, Undeclared)
    assert "unreadable" in bound.reason


def test_an_interpreter_without_tomllib_is_undeclared(tmp_path, monkeypatch):
    monkeypatch.setattr(suite_bound, "tomllib", None)

    bound = read_audit_bound(_project(tmp_path, _declaring("5400")))

    assert isinstance(bound, Undeclared)
    assert "no tomllib" in bound.reason
