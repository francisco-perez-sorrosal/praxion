"""Tests for check_p06_task_brief.py — P06 gate-liveness canary.

Gate-liveness contract (rules/swe/gate-liveness.md): this is a CODE gate
detecting slugs with SYSTEMS_PLAN.md but no TASK_BRIEF.md. It ships canaries
that feed a known-bad fixture and assert the gate fires. A detector that only
passes on good inputs is indistinguishable from no gate.

Two axes of coverage:

1. **Known-bad canary** — builds a known-bad input in tmp_path at runtime
   (.ai-work/test-slug/SYSTEMS_PLAN.md present, no TASK_BRIEF.md) and asserts
   ≥1 row with check="P06", severity="warn". The bad-case is constructed in
   tmp_path — NOT read from a committed fixture — because the P06 input shape is
   a `.ai-work/<slug>/` directory and `.ai-work/` is globally gitignored
   (.gitignore:50); a committed fixture file there would never reach a fresh
   checkout / CI (the canary would pass locally but fail in CI). gitignore
   affects only git, not filesystem reads, so tmp_path construction works
   everywhere. See tests/fixtures/sentinel/p06_missing_task_brief/README.md.

2. **No-false-positive control** — uses tmp_path to build a slug with BOTH
   SYSTEMS_PLAN.md and TASK_BRIEF.md present and asserts zero P06 rows.

Import strategy: deferred per-test-body via importlib.util so pytest collection
succeeds before the module exists (BDD/TDD concurrent-execution RED handshake).
Each test fails individually with FileNotFoundError until the implementation lands.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

_SCRIPT_PATH = Path(__file__).resolve().parent / "check_p06_task_brief.py"


# -- Fixture helpers ----------------------------------------------------------


def _make_missing_brief_slug(repo_root: Path, slug: str = "test-slug") -> Path:
    """Build a known-bad P06 input: SYSTEMS_PLAN.md present, TASK_BRIEF.md absent.

    Constructed at runtime under repo_root/.ai-work/<slug>/ rather than read from
    a committed fixture — `.ai-work/` is gitignored, so a committed file there
    would never reach a fresh checkout / CI. gitignore affects git, not
    filesystem reads, so runtime construction works everywhere.
    """
    slug_dir = repo_root / ".ai-work" / slug
    slug_dir.mkdir(parents=True)
    (slug_dir / "SYSTEMS_PLAN.md").write_text("# Plan", encoding="utf-8")
    # Intentionally NO TASK_BRIEF.md — this is the bad-case.
    return slug_dir


# -- Module loading -----------------------------------------------------------


def _load_module() -> Any:
    """Load check_p06_task_brief.py without requiring it on sys.path."""
    sys.modules.pop("check_p06_task_brief", None)
    spec = importlib.util.spec_from_file_location("check_p06_task_brief", _SCRIPT_PATH)
    assert spec is not None, f"Could not locate {_SCRIPT_PATH} — the detector script must exist"
    assert spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["check_p06_task_brief"] = mod
    spec.loader.exec_module(mod)
    return mod


# -- Gate-liveness canary (known-bad input built in tmp_path) ------------------


def test_canary_p06_fires_on_known_bad_input(tmp_path: Path) -> None:
    """Gate-liveness canary: run_p06 must WARN on a slug missing TASK_BRIEF.md.

    This is the CODE-gate liveness proof (rules/swe/gate-liveness.md). A gate
    that never fires on a known-bad input is indistinguishable from no gate.

    The bad-case is built in tmp_path (.ai-work/test-slug/SYSTEMS_PLAN.md present,
    TASK_BRIEF.md absent) rather than read from a committed fixture, because
    `.ai-work/` is gitignored and a committed fixture there would never reach CI.

    run_p06 must return ≥1 row with check="P06" and severity="warn".
    """
    _make_missing_brief_slug(tmp_path)

    mod = _load_module()
    findings = mod.run_p06(tmp_path)

    assert len(findings) >= 1, (
        f"run_p06 must emit ≥1 P06 finding for the known-bad input, got: {findings!r}"
    )

    p06_rows = [r for r in findings if r.get("check") == "P06" and r.get("severity") == "warn"]
    assert len(p06_rows) >= 1, (
        f"Expected ≥1 row with check='P06' severity='warn', got: {findings!r}"
    )


def test_canary_p06_fires_on_known_bad_input_json_mode(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Gate-liveness canary: --json output must have ≥1 P06 warn row for the bad-case."""
    _make_missing_brief_slug(tmp_path)

    mod = _load_module()
    with pytest.raises(SystemExit):
        mod.main(["--repo-root", str(tmp_path), "--json"])

    payload = json.loads(capsys.readouterr().out)
    assert isinstance(payload, list), f"--json must return a JSON array, got: {payload!r}"
    p06_rows = [r for r in payload if r.get("check") == "P06" and r.get("severity") == "warn"]
    assert len(p06_rows) >= 1, (
        f"--json must include ≥1 P06 warn row for the known-bad input, got: {payload!r}"
    )


# -- No-false-positive control ------------------------------------------------


def test_no_false_positive_slug_with_both_files(tmp_path: Path) -> None:
    """No-false-positive control: slug with BOTH SYSTEMS_PLAN.md and TASK_BRIEF.md → zero P06 rows.

    A slug that has TASK_BRIEF.md is compliant — the gate must not fire.
    """
    slug = tmp_path / ".ai-work" / "compliant-slug"
    slug.mkdir(parents=True)
    (slug / "SYSTEMS_PLAN.md").write_text("# Plan", encoding="utf-8")
    (slug / "TASK_BRIEF.md").write_text("# Task Brief", encoding="utf-8")

    mod = _load_module()
    findings = mod.run_p06(tmp_path)

    assert findings == [], (
        f"run_p06 must return [] when TASK_BRIEF.md is present, got: {findings!r}"
    )


def test_no_false_positive_ai_work_absent(tmp_path: Path) -> None:
    """No-false-positive control: absent .ai-work/ → skip with empty findings.

    Conditional-activation: a project without .ai-work/ has no pipeline slugs
    to check; the detector must exit 0 with no findings.
    """
    # Do NOT create .ai-work/ — substrate is absent.
    mod = _load_module()
    findings = mod.run_p06(tmp_path)

    assert findings == [], f"run_p06 must return [] when .ai-work/ is absent, got: {findings!r}"


def test_no_false_positive_slug_without_systems_plan(tmp_path: Path) -> None:
    """No-false-positive control: slug without SYSTEMS_PLAN.md must not trigger P06.

    Lightweight slugs lack SYSTEMS_PLAN.md (the architect doesn't run there).
    The check must be conditioned on SYSTEMS_PLAN.md presence — not just on
    TASK_BRIEF.md absence.
    """
    slug = tmp_path / ".ai-work" / "lightweight-slug"
    slug.mkdir(parents=True)
    # No SYSTEMS_PLAN.md and no TASK_BRIEF.md — Lightweight slug, must not fire.

    mod = _load_module()
    findings = mod.run_p06(tmp_path)

    assert findings == [], (
        f"run_p06 must not flag a slug that lacks SYSTEMS_PLAN.md, got: {findings!r}"
    )


# -- Multiple slugs -----------------------------------------------------------


def test_multiple_slugs_only_violating_slug_flagged(tmp_path: Path) -> None:
    """Multiple slugs: only the violating slug emits a P06 finding."""
    ai_work = tmp_path / ".ai-work"

    good = ai_work / "good-slug"
    good.mkdir(parents=True)
    (good / "SYSTEMS_PLAN.md").write_text("# Plan", encoding="utf-8")
    (good / "TASK_BRIEF.md").write_text("# Brief", encoding="utf-8")

    bad = ai_work / "bad-slug"
    bad.mkdir(parents=True)
    (bad / "SYSTEMS_PLAN.md").write_text("# Plan", encoding="utf-8")
    # No TASK_BRIEF.md in bad-slug.

    mod = _load_module()
    findings = mod.run_p06(tmp_path)

    assert len(findings) == 1, f"Expected exactly 1 finding for bad-slug, got: {findings!r}"
    assert findings[0]["check"] == "P06"
    assert findings[0]["severity"] == "warn"
    assert "bad-slug" in findings[0]["message"]


# -- CLI gates ----------------------------------------------------------------


def test_check_flag_exits_one_on_violation(tmp_path: Path) -> None:
    """--check exits 1 when ≥1 P06 finding is present."""
    slug = tmp_path / ".ai-work" / "missing-brief"
    slug.mkdir(parents=True)
    (slug / "SYSTEMS_PLAN.md").write_text("# Plan", encoding="utf-8")

    mod = _load_module()
    with pytest.raises(SystemExit) as exc:
        mod.main(["--repo-root", str(tmp_path), "--check"])

    assert exc.value.code == 1, f"--check must exit 1 on P06 violation, got {exc.value.code}"


def test_check_flag_exits_zero_on_clean(tmp_path: Path) -> None:
    """--check exits 0 when no P06 findings."""
    slug = tmp_path / ".ai-work" / "compliant"
    slug.mkdir(parents=True)
    (slug / "SYSTEMS_PLAN.md").write_text("# Plan", encoding="utf-8")
    (slug / "TASK_BRIEF.md").write_text("# Brief", encoding="utf-8")

    mod = _load_module()
    with pytest.raises(SystemExit) as exc:
        mod.main(["--repo-root", str(tmp_path), "--check"])

    assert exc.value.code == 0, f"--check must exit 0 on clean state, got {exc.value.code}"


def test_plugin_cache_refusal(tmp_path: Path) -> None:
    """Plugin-cache path must exit 2 without reading any slug dirs."""
    slug = tmp_path / ".ai-work" / "some-slug"
    slug.mkdir(parents=True)
    (slug / "SYSTEMS_PLAN.md").write_text("# Plan", encoding="utf-8")

    mod = _load_module()
    with patch.object(mod, "is_plugin_cache_path", return_value=True):
        with pytest.raises(SystemExit) as exc:
            mod.main(["--repo-root", str(tmp_path)])

    assert exc.value.code == 2, (
        "Plugin-cache path must exit 2 (refusal) to protect shared plugin state"
    )
