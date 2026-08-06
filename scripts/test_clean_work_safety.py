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
import os
import sys
import time
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

# The scanner recognises a requirement-bearing plan by matching the literal id
# prefix in the file's text, so this fixture must carry a real id for the
# spec-archive warning to fire at all. Paraphrasing it would silently disarm
# every test below that depends on that branch.
REQ_BEARING_PLAN = "## Acceptance\n- REQ-01: login works\n"  # id-citation-discipline:ignore


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
    _make_task(ai_work, "done", {"WIP.md": "# WIP\n- [x] Draft schema\n- [x] Wire consumer\n"})
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
    _make_task(ai_work, "in-flight", {"WIP.md": "# WIP\n- [x] Draft schema\n- [ ] Wire consumer\n"})
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
    _make_task(ai_work, "feat", {"traceability.yml": "some-req: [test_x]\n"})
    assert "unarchived-traceability" in _codes(_classify(ai_work, "feat"))


def test_systems_plan_req_warns_when_no_traceability(tmp_path: Path) -> None:
    ai_work = tmp_path / ".ai-work"
    _make_task(ai_work, "feat", {"SYSTEMS_PLAN.md": REQ_BEARING_PLAN})
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
        {"traceability.yml": "some-req: []\n", "SYSTEMS_PLAN.md": REQ_BEARING_PLAN},
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
    assert payload["summary"] == {"total": 2, "block": 1, "warn": 0, "safe": 1, "stale_safe": 0}
    by_slug = {d["slug"]: d for d in payload["task_dirs"]}
    assert by_slug["blocked"]["classification"] == "BLOCK"
    assert by_slug["blocked"]["reasons"][0]["code"] == "open-rework"
    assert by_slug["safe"]["classification"] == "SAFE"


# -- Staleness signal (P21) ---------------------------------------------------


def _age_file(path: Path, days_ago: float) -> None:
    past = time.time() - days_ago * 86400
    os.utime(path, (past, past))


def test_age_days_reflects_newest_file_mtime(tmp_path: Path) -> None:
    ai_work = tmp_path / ".ai-work"
    task = _make_task(ai_work, "old", {"RESEARCH_FINDINGS.md": "x\n"})
    _age_file(task / "RESEARCH_FINDINGS.md", days_ago=30)
    assert _classify(ai_work, "old").age_days >= 29


def test_empty_dir_age_is_none(tmp_path: Path) -> None:
    ai_work = tmp_path / ".ai-work"
    _make_task(ai_work, "empty", {})
    assert _classify(ai_work, "empty").age_days is None


def test_recent_safe_dir_is_not_stale(tmp_path: Path) -> None:
    ai_work = tmp_path / ".ai-work"
    _make_task(ai_work, "fresh", {"RESEARCH_FINDINGS.md": "x\n"})  # mtime ~ now
    verdict = _classify(ai_work, "fresh")
    assert verdict.classification == "SAFE"
    assert not cws._is_stale_safe(verdict)


def test_old_safe_dir_is_flagged_stale(tmp_path: Path) -> None:
    ai_work = tmp_path / ".ai-work"
    task = _make_task(ai_work, "abandoned", {"RESEARCH_FINDINGS.md": "x\n"})
    _age_file(task / "RESEARCH_FINDINGS.md", days_ago=60)
    verdict = _classify(ai_work, "abandoned")
    assert verdict.classification == "SAFE"
    assert cws._is_stale_safe(verdict)


def test_old_blocking_dir_is_not_a_stale_cleanup_candidate(tmp_path: Path) -> None:
    """An old dir that still BLOCKs (open rework) must never be a stale candidate."""
    ai_work = tmp_path / ".ai-work"
    task = _make_task(ai_work, "old-rework", {"REWORK_MANIFEST.md": "x\n"})
    _age_file(task / "REWORK_MANIFEST.md", days_ago=90)
    verdict = _classify(ai_work, "old-rework")
    assert verdict.classification == "BLOCK"
    assert not cws._is_stale_safe(verdict)


# -- Full-verdict characterization pins (safety floor) ------------------------
# Each pin asserts classification + exact reason code + severity for one safety-
# critical file type.  These are the regression barriers the registry refactor
# must not perturb.


def test_unchecked_wip_pins_block_severity(tmp_path: Path) -> None:
    ai_work = tmp_path / ".ai-work"
    _make_task(ai_work, "wip", {"WIP.md": "# WIP\n- [x] alpha\n- [ ] beta\n"})
    verdict = _classify(ai_work, "wip")
    assert verdict.classification == "BLOCK"
    reason = next(r for r in verdict.reasons if r.code == "active-pipeline")
    assert reason.blocker == "WIP.md"
    assert reason.severity == "block"


def test_rework_manifest_pins_block_severity(tmp_path: Path) -> None:
    ai_work = tmp_path / ".ai-work"
    _make_task(ai_work, "rework", {"REWORK_MANIFEST.md": "| td | worktree |\n"})
    verdict = _classify(ai_work, "rework")
    assert verdict.classification == "BLOCK"
    reason = next(r for r in verdict.reasons if r.code == "open-rework")
    assert reason.blocker == "REWORK_MANIFEST.md"
    assert reason.severity == "block"


def test_learnings_pins_warn_severity(tmp_path: Path) -> None:
    ai_work = tmp_path / ".ai-work"
    _make_task(ai_work, "feat", {"LEARNINGS.md": "# Learnings\n- gotcha\n"})
    verdict = _classify(ai_work, "feat")
    assert verdict.classification == "WARN"
    reason = next(r for r in verdict.reasons if r.code == "unmerged-learnings")
    assert reason.blocker == "LEARNINGS.md"
    assert reason.severity == "warn"


def test_verification_report_pins_warn_severity(tmp_path: Path) -> None:
    ai_work = tmp_path / ".ai-work"
    _make_task(ai_work, "feat", {"VERIFICATION_REPORT.md": "# Report\nPASS\n"})
    verdict = _classify(ai_work, "feat")
    assert verdict.classification == "WARN"
    reason = next(r for r in verdict.reasons if r.code == "unmerged-verification")
    assert reason.blocker == "VERIFICATION_REPORT.md"
    assert reason.severity == "warn"


def test_traceability_pins_warn_severity(tmp_path: Path) -> None:
    ai_work = tmp_path / ".ai-work"
    _make_task(ai_work, "feat", {"traceability.yml": "requirements: {}\n"})
    verdict = _classify(ai_work, "feat")
    assert verdict.classification == "WARN"
    reason = next(r for r in verdict.reasons if r.code == "unarchived-traceability")
    assert reason.blocker == "traceability.yml"
    assert reason.severity == "warn"


def test_recovery_log_pins_warn_classification_and_severity(tmp_path: Path) -> None:
    ai_work = tmp_path / ".ai-work"
    _make_task(ai_work, "feat", {"RECOVERY_LOG.md": "auto-marked step 3\n"})
    verdict = _classify(ai_work, "feat")
    assert verdict.classification == "WARN"
    reason = next(r for r in verdict.reasons if r.code == "recovery-audit")
    assert reason.blocker == "RECOVERY_LOG.md"
    assert reason.severity == "warn"


def test_unconsumed_pre_refactor_pins_warn_severity(tmp_path: Path) -> None:
    ai_work = tmp_path / ".ai-work"
    _make_task(ai_work, "feat", {"PRE_REFACTOR_PLAN.md": "## Goal\nrefactor\n"})
    verdict = _classify(ai_work, "feat")
    assert verdict.classification == "WARN"
    reason = next(r for r in verdict.reasons if r.code == "unconsumed-refactor")
    assert reason.blocker == "PRE_REFACTOR_PLAN.md"
    assert reason.severity == "warn"


def test_consumed_pre_refactor_is_safe_with_no_reasons(tmp_path: Path) -> None:
    ai_work = tmp_path / ".ai-work"
    _make_task(ai_work, "feat", {"PRE_REFACTOR_PLAN.md": "## Goal\nrefactor\n\n[CONSUMED]\n"})
    verdict = _classify(ai_work, "feat")
    assert verdict.classification == "SAFE"
    assert verdict.reasons == []


def test_req_bearing_systems_plan_pins_warn_severity(tmp_path: Path) -> None:
    req_id = f"REQ-{1:02d}"
    ai_work = tmp_path / ".ai-work"
    _make_task(ai_work, "feat", {"SYSTEMS_PLAN.md": f"## Acceptance\n- {req_id}: login works\n"})
    verdict = _classify(ai_work, "feat")
    assert verdict.classification == "WARN"
    reason = next(r for r in verdict.reasons if r.code == "unarchived-spec")
    assert reason.blocker == "SYSTEMS_PLAN.md"
    assert reason.severity == "warn"


# -- Multi-file snapshot pins --------------------------------------------------


def test_completed_pipeline_dir_warns_with_traceability_not_spec(tmp_path: Path) -> None:
    # LEARNINGS + VERIFICATION_REPORT + traceability.yml + REQ-bearing SYSTEMS_PLAN:
    # traceability.yml wins the elif branch → unarchived-traceability, NOT unarchived-spec.
    req_id = f"REQ-{1:02d}"
    ai_work = tmp_path / ".ai-work"
    _make_task(
        ai_work,
        "done",
        {
            "LEARNINGS.md": "# Learnings\n- gotcha\n",
            "VERIFICATION_REPORT.md": "# Report\nPASS\n",
            "traceability.yml": "requirements: {}\n",
            "SYSTEMS_PLAN.md": f"## Acceptance\n- {req_id}: login works\n",
        },
    )
    verdict = _classify(ai_work, "done")
    assert verdict.classification == "WARN"
    codes = _codes(verdict)
    assert codes == {"unmerged-learnings", "unmerged-verification", "unarchived-traceability"}
    assert "unarchived-spec" not in codes


def test_block_precedence_snapshot_with_all_warn_files(tmp_path: Path) -> None:
    # Unchecked WIP + open REWORK + all warn-level files → BLOCK classification;
    # both block codes and every warn code are reported (not just the blocking ones).
    ai_work = tmp_path / ".ai-work"
    _make_task(
        ai_work,
        "kitchen-sink",
        {
            "WIP.md": "# WIP\n- [ ] pending\n",
            "REWORK_MANIFEST.md": "| td | worktree |\n",
            "LEARNINGS.md": "# Learnings\n",
            "VERIFICATION_REPORT.md": "# Report\nPASS\n",
            "traceability.yml": "requirements: {}\n",
            "RECOVERY_LOG.md": "auto-marked step 1\n",
            "PRE_REFACTOR_PLAN.md": "## Goal\nrefactor\n",
        },
    )
    verdict = _classify(ai_work, "kitchen-sink")
    assert verdict.classification == "BLOCK"
    codes = _codes(verdict)
    assert {"active-pipeline", "open-rework"} <= codes  # block-severity reasons
    assert {  # warn-severity reasons also reported alongside the blockers
        "unmerged-learnings",
        "unmerged-verification",
        "unarchived-traceability",
        "recovery-audit",
        "unconsumed-refactor",
    } <= codes


# -- Conservative-floor pin ---------------------------------------------------


def test_severity_for_unknown_artifact_is_warn() -> None:
    # Unregistered artifact name must resolve to warn (never safe) — the
    # monotonic floor that prevents a future unknown policy from widening deletion.
    assert cws._severity_for("__totally_unknown_artifact__.md") == "warn"


# -- Genuine-consumption test (severity sourced from registry, not hardcoded) -
# Proves the registry read is load-bearing: if severity were a hardcoded literal
# inside detect_reasons, patching cleanup_policy_for would have no observable
# effect and the assertion below would fail.


def test_wip_severity_changes_when_policy_overridden(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Arrange: task dir with an unchecked WIP step — triggers "active-pipeline"
    # reason via "block-if-active" policy → BLOCK classification.
    ai_work = tmp_path / ".ai-work"
    _make_task(ai_work, "in-flight", {"WIP.md": "# WIP\n- [ ] pending\n"})

    # Sanity check: before patching, WIP.md → block-if-active → "block" severity → BLOCK.
    verdict_before = _classify(ai_work, "in-flight")
    assert verdict_before.classification == "BLOCK"

    # Act: override cleanup_policy_for in the cws module namespace so WIP.md returns
    # "consume-marker" (→ "warn" severity in _POLICY_SEVERITY) instead of "block-if-active".
    # _severity_for resolves cleanup_policy_for from cws globals, so patching cws's
    # binding is sufficient — no need to touch the artifact_registry module directly.
    original_policy_fn = cws.cleanup_policy_for
    monkeypatch.setattr(
        cws,
        "cleanup_policy_for",
        lambda name: "consume-marker" if name == "WIP.md" else original_policy_fn(name),
    )

    # Assert: with WIP.md → consume-marker → "warn" severity, the verdict drops to WARN.
    verdict_after = _classify(ai_work, "in-flight")
    assert verdict_after.classification == "WARN"
    wip_reason = next(r for r in verdict_after.reasons if r.blocker == "WIP.md")
    assert wip_reason.severity == "warn"
    assert wip_reason.code == "active-pipeline"


# -- Registry-drift gate (coupling self-guarding) ------------------------------
# The set of files detect_reasons emits reasons for must equal the registry's
# non-delete artifact set. A new non-delete registry artifact without a matching
# predicate in detect_reasons will be caught at test time (not silently at runtime).
#
# Two directory shapes are needed because SYSTEMS_PLAN.md uses an elif branch:
# when traceability.yml is present, the spec reason is suppressed (traceability wins).
# Shape 1 covers the 7 non-SYSTEMS_PLAN artifacts; Shape 2 covers SYSTEMS_PLAN via
# the spec branch (no traceability.yml present).


def test_detected_blockers_equal_registry_non_delete_artifacts(tmp_path: Path) -> None:
    import artifact_registry

    # Shape 1 (traceability branch): 7 files, each triggering one reason.
    ai_work = tmp_path / ".ai-work"
    _make_task(
        ai_work,
        "shape-traceability",
        {
            "WIP.md": "# WIP\n- [ ] pending\n",
            "REWORK_MANIFEST.md": "| td | worktree |\n",
            "LEARNINGS.md": "# Learnings\n",
            "VERIFICATION_REPORT.md": "# Report\nPASS\n",
            "traceability.yml": "requirements: {}\n",
            "RECOVERY_LOG.md": "auto-marked step 1\n",
            "PRE_REFACTOR_PLAN.md": "## Goal\nrefactor\n",
        },
    )

    # Shape 2 (spec branch): SYSTEMS_PLAN with a REQ-id, no traceability.yml —
    # takes the elif branch that emits "unarchived-spec".
    req_id = f"REQ-{1:02d}"
    _make_task(
        ai_work,
        "shape-spec",
        {"SYSTEMS_PLAN.md": f"## Acceptance\n- {req_id}: criterion\n"},
    )

    reasons_shape1 = cws.detect_reasons(ai_work / "shape-traceability")
    reasons_shape2 = cws.detect_reasons(ai_work / "shape-spec")

    blockers = {r.blocker for r in reasons_shape1} | {r.blocker for r in reasons_shape2}
    expected = {a.name for a in artifact_registry.ARTIFACTS if a.cleanup_policy != "delete"}

    assert blockers == expected, (
        f"Blocker set {blockers!r} does not match registry non-delete set {expected!r}. "
        "A registry edit likely added/removed a non-delete artifact without a "
        "matching predicate in detect_reasons."
    )

    # Gate-liveness canary: prove this check is not vacuous by showing it would fail
    # if the registry gained a new non-delete artifact ("FAKE_ARTIFACT.md") that has
    # no predicate in detect_reasons — detect_reasons never emits a reason for it,
    # so its name cannot appear in the blocker set.
    extended_expected = expected | {"FAKE_ARTIFACT.md"}
    assert blockers != extended_expected, (
        "Canary failed: blockers should NOT equal the extended set because "
        "detect_reasons has no predicate for FAKE_ARTIFACT.md."
    )
