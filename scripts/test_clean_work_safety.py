"""Tests for clean_work_safety.py -- deletion-safety classifier for .ai-work/.

Gate-liveness contract (rules/swe/gate-liveness.md): this is a CODE gate
guarding irreversible `rm -rf` of pipeline state, so it ships canaries — tests
that feed a known-bad task directory (an open REWORK_MANIFEST.md; a WIP.md with
an unchecked step) and assert the gate flags it (classification BLOCK, exit 1).
A scanner that only ever passes on clean input is indistinguishable from no gate.

Import strategy mirrors scripts/test_check_squash_safety.py: load via
importlib.util so the script need not be on sys.path. All filesystem state is
built under pytest's tmp_path; no git calls are made (--ai-work-root bypasses
repo-root resolution).
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import pytest

_SCRIPT_PATH = Path(__file__).resolve().parent / "clean_work_safety.py"


def _load_module() -> Any:
    spec = importlib.util.spec_from_file_location("clean_work_safety", _SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


cws = _load_module()


# -- Helpers ------------------------------------------------------------------


def _make_task(ai_work: Path, slug: str, files: dict[str, str]) -> Path:
    """Create .ai-work/<slug>/ populated with the given filename->content map."""
    task_dir = ai_work / slug
    task_dir.mkdir(parents=True)
    for name, content in files.items():
        (task_dir / name).write_text(content, encoding="utf-8")
    return task_dir


def _classify(ai_work: Path, slug: str) -> Any:
    return cws.classify(ai_work / slug)


def _codes(verdict: Any) -> set[str]:
    return {r.code for r in verdict.reasons}


# -- SAFE ---------------------------------------------------------------------


def test_research_only_dir_is_safe(tmp_path: Path) -> None:
    ai_work = tmp_path / ".ai-work"
    _make_task(ai_work, "research-only", {"RESEARCH_FINDINGS.md": "# Findings\n"})
    verdict = _classify(ai_work, "research-only")
    assert verdict.classification == "SAFE"
    assert verdict.reasons == []


def test_empty_task_dir_is_safe(tmp_path: Path) -> None:
    ai_work = tmp_path / ".ai-work"
    _make_task(ai_work, "empty", {})
    assert _classify(ai_work, "empty").classification == "SAFE"


def test_completed_wip_all_checked_is_not_blocked(tmp_path: Path) -> None:
    ai_work = tmp_path / ".ai-work"
    _make_task(ai_work, "done", {"WIP.md": "# WIP\n- [x] Step 1\n- [x] Step 2\n"})
    verdict = _classify(ai_work, "done")
    assert verdict.classification == "SAFE"


# -- BLOCK canaries (the gate must bite) --------------------------------------


def test_open_rework_manifest_blocks(tmp_path: Path) -> None:
    ai_work = tmp_path / ".ai-work"
    _make_task(ai_work, "pay-rework", {"REWORK_MANIFEST.md": "| td | worktree |\n"})
    verdict = _classify(ai_work, "pay-rework")
    assert verdict.classification == "BLOCK"
    assert "open-rework" in _codes(verdict)


def test_active_wip_unchecked_step_blocks(tmp_path: Path) -> None:
    ai_work = tmp_path / ".ai-work"
    _make_task(ai_work, "in-flight", {"WIP.md": "# WIP\n- [x] Step 1\n- [ ] Step 2\n"})
    verdict = _classify(ai_work, "in-flight")
    assert verdict.classification == "BLOCK"
    assert "active-pipeline" in _codes(verdict)


def test_block_exit_code_is_nonzero(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    ai_work = tmp_path / ".ai-work"
    _make_task(ai_work, "blocked", {"REWORK_MANIFEST.md": "x\n"})
    with pytest.raises(SystemExit) as exc:
        cws.main(["--ai-work-root", str(ai_work), "--json"])
    assert exc.value.code == 1


def test_safe_only_exit_code_is_zero(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    ai_work = tmp_path / ".ai-work"
    _make_task(ai_work, "safe", {"RESEARCH_FINDINGS.md": "x\n"})
    with pytest.raises(SystemExit) as exc:
        cws.main(["--ai-work-root", str(ai_work)])
    assert exc.value.code == 0


# -- WARN cases ---------------------------------------------------------------


def test_learnings_warns(tmp_path: Path) -> None:
    ai_work = tmp_path / ".ai-work"
    _make_task(ai_work, "feat", {"LEARNINGS.md": "# Learnings\n- gotcha\n"})
    verdict = _classify(ai_work, "feat")
    assert verdict.classification == "WARN"
    assert "unmerged-learnings" in _codes(verdict)


def test_verification_report_warns_without_marker(tmp_path: Path) -> None:
    ai_work = tmp_path / ".ai-work"
    _make_task(ai_work, "feat", {"VERIFICATION_REPORT.md": "# Report\nPASS\n"})
    assert "unmerged-verification" in _codes(_classify(ai_work, "feat"))


def test_verification_warning_suppressed_by_learnings_marker(tmp_path: Path) -> None:
    ai_work = tmp_path / ".ai-work"
    _make_task(
        ai_work,
        "feat",
        {
            "VERIFICATION_REPORT.md": "# Report\nPASS\n",
            "LEARNINGS.md": "# Learnings\n### Verification Patterns Merged\n- pattern\n",
        },
    )
    verdict = _classify(ai_work, "feat")
    codes = _codes(verdict)
    assert "unmerged-verification" not in codes
    # LEARNINGS.md itself still warrants a merge-to-permanent warning.
    assert "unmerged-learnings" in codes
    assert verdict.classification == "WARN"


def test_traceability_warns(tmp_path: Path) -> None:
    ai_work = tmp_path / ".ai-work"
    _make_task(ai_work, "feat", {"traceability.yml": "REQ-01: [test_x]\n"})
    assert "unarchived-traceability" in _codes(_classify(ai_work, "feat"))


def test_systems_plan_req_warns_when_no_traceability(tmp_path: Path) -> None:
    ai_work = tmp_path / ".ai-work"
    _make_task(ai_work, "feat", {"SYSTEMS_PLAN.md": "## Acceptance\n- REQ-01: login works\n"})
    assert "unarchived-spec" in _codes(_classify(ai_work, "feat"))


def test_systems_plan_without_req_does_not_warn_spec(tmp_path: Path) -> None:
    ai_work = tmp_path / ".ai-work"
    _make_task(ai_work, "feat", {"SYSTEMS_PLAN.md": "## Design\nNo requirement ids here.\n"})
    assert "unarchived-spec" not in _codes(_classify(ai_work, "feat"))


def test_traceability_supersedes_spec_reason(tmp_path: Path) -> None:
    """traceability.yml + REQ-bearing plan yields one spec reason, not two."""
    ai_work = tmp_path / ".ai-work"
    _make_task(
        ai_work,
        "feat",
        {"traceability.yml": "REQ-01: []\n", "SYSTEMS_PLAN.md": "- REQ-01\n"},
    )
    codes = _codes(_classify(ai_work, "feat"))
    assert "unarchived-traceability" in codes
    assert "unarchived-spec" not in codes


def test_recovery_log_warns(tmp_path: Path) -> None:
    ai_work = tmp_path / ".ai-work"
    _make_task(ai_work, "feat", {"RECOVERY_LOG.md": "auto-marked step 3\n"})
    assert "recovery-audit" in _codes(_classify(ai_work, "feat"))


def test_unconsumed_pre_refactor_warns(tmp_path: Path) -> None:
    ai_work = tmp_path / ".ai-work"
    _make_task(ai_work, "feat", {"PRE_REFACTOR_PLAN.md": "## Goal\nrefactor\n"})
    assert "unconsumed-refactor" in _codes(_classify(ai_work, "feat"))


def test_consumed_pre_refactor_does_not_warn(tmp_path: Path) -> None:
    ai_work = tmp_path / ".ai-work"
    _make_task(ai_work, "feat", {"PRE_REFACTOR_PLAN.md": "## Goal\nrefactor\n\n[CONSUMED]\n"})
    assert "unconsumed-refactor" not in _codes(_classify(ai_work, "feat"))


# -- Severity precedence + aggregation ----------------------------------------


def test_block_wins_over_warn(tmp_path: Path) -> None:
    ai_work = tmp_path / ".ai-work"
    _make_task(
        ai_work,
        "mixed",
        {"REWORK_MANIFEST.md": "x\n", "LEARNINGS.md": "y\n"},
    )
    verdict = _classify(ai_work, "mixed")
    assert verdict.classification == "BLOCK"
    # Both reasons are still reported, not just the blocking one.
    assert {"open-rework", "unmerged-learnings"} <= _codes(verdict)


def test_scan_filters_by_slug(tmp_path: Path) -> None:
    ai_work = tmp_path / ".ai-work"
    _make_task(ai_work, "a", {"LEARNINGS.md": "x\n"})
    _make_task(ai_work, "b", {"RESEARCH_FINDINGS.md": "x\n"})
    verdicts = cws.scan_task_dirs(ai_work, ["b"])
    assert [v.slug for v in verdicts] == ["b"]


def test_scan_skips_root_pipeline_state_file(tmp_path: Path) -> None:
    ai_work = tmp_path / ".ai-work"
    ai_work.mkdir(parents=True)
    (ai_work / "PIPELINE_STATE.md").write_text("snapshot\n", encoding="utf-8")
    _make_task(ai_work, "a", {})
    verdicts = cws.scan_task_dirs(ai_work, [])
    assert [v.slug for v in verdicts] == ["a"]


def test_missing_ai_work_reports_nothing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    missing = tmp_path / ".ai-work"
    with pytest.raises(SystemExit) as exc:
        cws.main(["--ai-work-root", str(missing)])
    assert exc.value.code == 0
    assert "Nothing to clean" in capsys.readouterr().out


# -- JSON output --------------------------------------------------------------


def test_json_output_shape(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    ai_work = tmp_path / ".ai-work"
    _make_task(ai_work, "blocked", {"REWORK_MANIFEST.md": "x\n"})
    _make_task(ai_work, "safe", {"RESEARCH_FINDINGS.md": "x\n"})
    with pytest.raises(SystemExit):
        cws.main(["--ai-work-root", str(ai_work), "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert payload["summary"] == {"total": 2, "block": 1, "warn": 0, "safe": 1}
    by_slug = {d["slug"]: d for d in payload["task_dirs"]}
    assert by_slug["blocked"]["classification"] == "BLOCK"
    assert by_slug["blocked"]["reasons"][0]["code"] == "open-rework"
    assert by_slug["safe"]["classification"] == "SAFE"
