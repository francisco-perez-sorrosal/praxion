"""Unit tests for the inheritance-probe checker (process-economy P0.7).

Exercises `check_inheritance()` — the pure layer — against fixture JSON path
lists shaped like what a live `claude -p` session would report. Never spawns
the real session: `build_invocation()`/`main()` are out of scope for this
file by design (one full headless session per invocation, API-metered — see
`eval/scripts/inheritance_probe.py`'s own module docstring).

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

_FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures" / "inheritance_probe"
_SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "inheritance_probe.py"
_MODULE_NAME = "inheritance_probe"


def _load_fixture(name: str) -> list[str]:
    return json.loads((_FIXTURES_DIR / name).read_text(encoding="utf-8"))


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


def test_all_expected_paths_present_passes():
    """Every expected identifier present, no forbidden rule -- PASS."""
    check_inheritance = _load_module().check_inheritance

    verdict = check_inheritance(_load_fixture("all_present.json"))

    assert verdict.verdict == "PASS"
    assert verdict.missing == ()
    assert verdict.unexpected == ()


def test_missing_expected_path_fails():
    """Dropping one expected always-loaded rule (adr-conventions.md) -- FAIL."""
    check_inheritance = _load_module().check_inheritance

    verdict = check_inheritance(_load_fixture("missing_expected.json"))

    assert verdict.verdict == "FAIL"
    assert any("adr-conventions.md" in m for m in verdict.missing)
    assert verdict.unexpected == ()


def test_hook_delivered_rule_present_fails():
    """A hook-delivered rule (agent-model-routing.md) leaking into a subagent
    probe's claudeMd block -- FAIL, even with every expected path present."""
    check_inheritance = _load_module().check_inheritance

    verdict = check_inheritance(_load_fixture("hook_delivered_present.json"))

    assert verdict.verdict == "FAIL"
    assert verdict.missing == ()
    assert any("agent-model-routing.md" in u for u in verdict.unexpected)


def test_extra_unrelated_paths_still_passes():
    """Extra paths outside the expected/forbidden sets (e.g. a skill file) are
    inert -- PASS, since only the named identifiers are checked."""
    check_inheritance = _load_module().check_inheritance

    verdict = check_inheritance(_load_fixture("extra_unrelated.json"))

    assert verdict.verdict == "PASS"
    assert verdict.missing == ()
    assert verdict.unexpected == ()
