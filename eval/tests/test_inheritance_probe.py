"""Unit tests for the inheritance-probe differential checker.

Exercises `parse_report()` and `check_differential()` — the pure layers —
against fixture JSON shaped like what a live `claude -p` session would
report. Never spawns a real session: `main()`'s two `_run()` subprocess
calls are out of scope for this file by design (two full headless sessions
per invocation, API-metered — see `eval/scripts/inheritance_probe.py`'s own
module docstring). `--dry-run` is the one `main()` path this file *does*
exercise, since it never touches `subprocess`.

`eval/scripts/` is not part of the `praxion_evals` package (no `__init__.py`,
not listed in `pyproject.toml`'s wheel target), so the module under test is
loaded by file path rather than a normal package import.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType

import pytest

_FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures" / "inheritance_probe"
_SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "inheritance_probe.py"
_MODULE_NAME = "inheritance_probe"


def _load_fixture_text(name: str) -> str:
    return (_FIXTURES_DIR / name).read_text(encoding="utf-8")


def _load_module() -> ModuleType:
    """Load the script by file path (it is not part of the packaged wheel).

    Registered in `sys.modules` *before* `exec_module()` -- required for its
    `from __future__ import annotations` + `@dataclass` combination, which
    resolves string annotations via `sys.modules[cls.__module__]` at class
    definition time.
    """
    spec = importlib.util.spec_from_file_location(_MODULE_NAME, _SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[_MODULE_NAME] = module
    spec.loader.exec_module(module)
    return module


def test_differential_passes_when_only_top_level_reports_heading():
    """Top-level sees the routing heading, subagent does not -- PASS."""
    probe = _load_module()

    top_level = probe.parse_report("top-level", _load_fixture_text("pass_top_level.json"))
    subagent = probe.parse_report("subagent", _load_fixture_text("pass_subagent.json"))
    verdict = probe.check_differential(top_level, subagent)

    assert verdict.verdict == "PASS"


def test_differential_fails_when_both_report_heading_present():
    """Both runs agree the heading is present -- the vacuous-guard bug this
    rework fixes -- FAIL, naming the subagent run as the culprit."""
    probe = _load_module()

    top_level = probe.parse_report("top-level", _load_fixture_text("fail_top_level.json"))
    subagent = probe.parse_report("subagent", _load_fixture_text("fail_subagent.json"))
    verdict = probe.check_differential(top_level, subagent)

    assert verdict.verdict == "FAIL"
    assert any("subagent run reported" in f for f in verdict.findings)


def test_differential_fails_when_a_run_is_missing_expected_paths():
    """Dropping one of the 7 always-loaded paths from either run -- FAIL."""
    probe = _load_module()

    top_level = probe.parse_report("top-level", _load_fixture_text("pass_top_level.json"))
    subagent_data = json.loads(_load_fixture_text("pass_subagent.json"))
    subagent_data["claude_md_paths"] = [
        p for p in subagent_data["claude_md_paths"] if "adr-conventions.md" not in p
    ]
    subagent = probe.parse_report("subagent", json.dumps(subagent_data))

    verdict = probe.check_differential(top_level, subagent)

    assert verdict.verdict == "FAIL"
    assert any("adr-conventions.md" in f for f in verdict.findings)


def test_malformed_output_raises_on_parse():
    """A session that doesn't reply with the requested JSON shape -- the
    parse fails loudly rather than being silently coerced into a verdict."""
    probe = _load_module()

    with pytest.raises(json.JSONDecodeError):
        probe.parse_report("top-level", _load_fixture_text("malformed.txt"))


def test_dry_run_exits_zero_and_prints_two_invocations(capsys):
    """`--dry-run` never touches `subprocess`; prints both argv lists."""
    probe = _load_module()

    exit_code = probe.main(["--dry-run"])
    captured = capsys.readouterr()

    assert exit_code == 0
    assert "top-level" in captured.out
    assert "subagent" in captured.out
    assert "claude" in captured.out
