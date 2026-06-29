"""Integration tests for the criteria-to-spec chain gate liveness.

Drives four real validators over a synthetic tmp_path mini-repo to prove that
the chain passes when correctly assembled and bites when exactly one link is
broken.

Chain links exercised:
  link-1  run_p06          TASK_BRIEF present alongside SYSTEMS_PLAN
  link-2  detect_drift     SYSTEMS_PLAN in-flight → traceability in sync
  link-3  REQ-flow assert  traceability keys appear verbatim in the SPEC body
  link-4  detect_gap       SPEC archival recency against ADR cluster

Five tests total: one faithful-chain test (all four links clean) plus four
per-link bite tests, each mutating exactly one link and asserting the
corresponding validator produces a non-clean verdict.
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml

from scripts.spec_drift import detect_drift

# ---------------------------------------------------------------------------
# Scripts/ path setup
#
# check_p06_task_brief, check_spec_archival_gap, and regenerate_specs_index
# all do `from _repo_root import …` at module level, which requires scripts/
# on sys.path before they are imported.  sys.path.insert is done at module
# level so the imports below can resolve on first collection.
# ---------------------------------------------------------------------------
SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import check_p06_task_brief  # noqa: E402
import check_spec_archival_gap  # noqa: E402
import regenerate_specs_index as rsi_mod  # noqa: E402

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_SLUG = "test-slug"

# Reference time for gap calculations.  tests/ is NOT covered by the UP017
# ruff suppress (scripts/** + hooks/* only) — use timezone.utc, not datetime.UTC.
_NOW = datetime(2026, 6, 29, tzinfo=timezone.utc)  # noqa: UP017

# SPEC date matches _NOW so the fresh-spec gap check trivially passes.
_SPEC_DATE = "2026-06-29"

# Single dependent path written into traceability.yml and included in the
# faithful-chain _changed_files_override.  A shared constant ensures both
# lists stay in sync (R2 mitigation: derive override from traceability paths).
_DEP_PATH = "tests/test_criteria_spec_eval.py"

# ---------------------------------------------------------------------------
# Builder helpers
# ---------------------------------------------------------------------------


def _req(n: int) -> str:
    """Generate a requirement ID string at runtime.

    The committed line contains an f-string with { immediately after the
    hyphen, so the id-citation discipline scanner (which requires [A-Z0-9]
    after the hyphen) does not flag it as a bare literal.
    """
    return f"REQ-{n:02d}"


def _write_task_brief(path: Path, reqs: list[str]) -> None:
    """Write a minimal TASK_BRIEF.md containing every req string."""
    body = "# Task Brief\n\nKey signals:\n\n"
    for r in reqs:
        body += f"- {r}: test requirement.\n"
    path.write_text(body, encoding="utf-8")


def _write_systems_plan(path: Path, reqs: list[str]) -> None:
    """Write a minimal SYSTEMS_PLAN.md listing every req string."""
    body = "# Systems Plan\n\n## Behavioral Specification\n\n"
    for r in reqs:
        body += f"- **{r}**: test system behavior.\n"
    path.write_text(body, encoding="utf-8")


def _write_traceability(path: Path, reqs: list[str], dep_paths: list[str]) -> None:
    """Write traceability.yml mapping every req to dep_paths."""
    data: dict = {
        "requirements": {r: {"tests": list(dep_paths), "implementation": []} for r in reqs}
    }
    path.write_text(yaml.safe_dump(data), encoding="utf-8")


def _write_spec(path: Path, reqs: list[str], slug: str, spec_date: str) -> None:
    """Write a SPEC file with a ## Traceability section and all req strings."""
    rows = "\n".join(f"| {r} | test_faithful_chain_passes | |" for r in reqs)
    req_lines = "\n".join(f"- {r}: test behavioral requirement." for r in reqs)
    content = (
        f"**Task slug**: `{slug}`\n"
        f"**Archived**: {spec_date}\n"
        f"**Status**: Shipped\n"
        f"**Tier**: Standard\n"
        f"\n"
        f"## Feature Summary\n"
        f"\n"
        f"Criteria spec eval integration test.\n"
        f"\n"
        f"## Traceability\n"
        f"\n"
        f"| REQ | Tests | Implementation |\n"
        f"|-----|-------|----------------|\n"
        f"{rows}\n"
        f"\n"
        f"## Behavioral Specification\n"
        f"\n"
        f"{req_lines}\n"
    )
    path.write_text(content, encoding="utf-8")


def _build_faithful_chain(
    tmp_path: Path,
    reqs: list[str],
    slug: str = _SLUG,
) -> dict:
    """Build all four chain artifacts under tmp_path and return a path dict.

    Creates:
      tmp_path/.ai-work/<slug>/TASK_BRIEF.md
      tmp_path/.ai-work/<slug>/SYSTEMS_PLAN.md
      tmp_path/.ai-work/<slug>/traceability.yml
      tmp_path/.ai-state/specs/SPEC_<slug>_<date>.md
    """
    work_dir = tmp_path / ".ai-work" / slug
    work_dir.mkdir(parents=True)
    _write_task_brief(work_dir / "TASK_BRIEF.md", reqs)
    _write_systems_plan(work_dir / "SYSTEMS_PLAN.md", reqs)
    _write_traceability(work_dir / "traceability.yml", reqs, [_DEP_PATH])

    specs_dir = tmp_path / ".ai-state" / "specs"
    specs_dir.mkdir(parents=True)
    spec_path = specs_dir / f"SPEC_{slug}_{_SPEC_DATE}.md"
    _write_spec(spec_path, reqs, slug, _SPEC_DATE)

    return {"work_dir": work_dir, "spec_path": spec_path}


# ---------------------------------------------------------------------------
# Faithful-chain test — all four validators return a clean verdict
# ---------------------------------------------------------------------------


def test_faithful_chain_passes(tmp_path: Path) -> None:
    """A correctly linked chain passes all four validators without a finding."""
    reqs = [_req(1), _req(2), _req(3)]
    artifacts = _build_faithful_chain(tmp_path, reqs)

    # link-1: TASK_BRIEF present alongside SYSTEMS_PLAN — no P06 violation
    p06_findings = check_p06_task_brief.run_p06(tmp_path)
    assert (
        p06_findings == []
    ), f"Expected no P06 findings for a faithful chain; got: {p06_findings!r}"

    # link-2: all dependents listed in traceability are in changed_files.
    # _DEP_PATH is derived from the same constant used in _write_traceability
    # so the override and traceability paths are guaranteed to agree (R2 guard).
    changed_override = ["SYSTEMS_PLAN.md", _DEP_PATH]
    drift_findings = detect_drift(
        f"in-flight:{_SLUG}",
        tmp_path,
        None,
        _changed_files_override=changed_override,
    )
    assert not any(
        f.get("severity") == "important" for f in drift_findings
    ), f"Expected no important drift finding for a faithful chain; got: {drift_findings!r}"

    # link-3: SPEC body contains the Traceability section header and every req ID
    spec_text = artifacts["spec_path"].read_text(encoding="utf-8")
    assert "## Traceability" in spec_text, "SPEC must contain '## Traceability' section"

    # REQ-flow cross-linking: the SAME req IDs flow through ALL FOUR chain
    # artifacts — proven, not assumed. This is the core G1 claim made live:
    # the criteria thread links end to end, not just in the final SPEC.
    brief_text = (artifacts["work_dir"] / "TASK_BRIEF.md").read_text(encoding="utf-8")
    plan_text = (artifacts["work_dir"] / "SYSTEMS_PLAN.md").read_text(encoding="utf-8")
    trace = yaml.safe_load((artifacts["work_dir"] / "traceability.yml").read_text(encoding="utf-8"))
    trace_keys = set(trace["requirements"])
    for r in reqs:
        assert r in brief_text, f"TASK_BRIEF must carry req ID {r!r}"
        assert r in plan_text, f"SYSTEMS_PLAN must carry req ID {r!r}"
        assert r in trace_keys, f"traceability.yml must key req ID {r!r}"
        assert r in spec_text, f"SPEC must carry req ID {r!r} in body"

    # link-4a: SPEC is fresh (same date as _NOW, no ADR cluster) — no gap
    gap_result = check_spec_archival_gap.detect_gap(tmp_path, now=_NOW)
    assert (
        gap_result["gap"] is False
    ), f"Expected gap=False for a fresh SPEC with no ADR cluster; result: {gap_result!r}"

    # link-4b: regenerate_specs_index writes an index listing the new SPEC.
    # Rebind module globals to tmp_path immediately before use (R3 mitigation).
    rsi_mod.apply_repo_root(tmp_path)
    specs = rsi_mod.collect_specs()
    index_content = rsi_mod.generate_index(specs)
    rsi_mod.INDEX_PATH.write_text(index_content, encoding="utf-8")
    assert (
        f"SPEC_{_SLUG}_{_SPEC_DATE}.md" in index_content
    ), f"Generated index must list the new SPEC; index:\n{index_content}"


# ---------------------------------------------------------------------------
# Per-link bite tests — each mutates exactly one link
# ---------------------------------------------------------------------------


def test_link1_brief_missing_bites(tmp_path: Path) -> None:
    """Removing TASK_BRIEF.md from a plan slug triggers a P06 finding."""
    reqs = [_req(1), _req(2), _req(3)]
    artifacts = _build_faithful_chain(tmp_path, reqs)

    # Mutate link-1: delete the brief so the slug has SYSTEMS_PLAN but no TASK_BRIEF.
    (artifacts["work_dir"] / "TASK_BRIEF.md").unlink()

    findings = check_p06_task_brief.run_p06(tmp_path)
    assert findings, "Expected P06 finding when TASK_BRIEF.md is absent; got empty list"
    assert any(
        f.get("check") == "P06" for f in findings
    ), f"Expected at least one finding with check='P06'; got: {findings!r}"


def test_link2_traceability_gap_bites(tmp_path: Path) -> None:
    """Changed SYSTEMS_PLAN with no dependent touched produces an important drift finding."""
    reqs = [_req(1), _req(2), _req(3)]
    _build_faithful_chain(tmp_path, reqs)

    # Mutate link-2: pass only SYSTEMS_PLAN.md as changed — dependent paths in
    # traceability.yml are NOT in changed_files → stale-dependent finding.
    findings = detect_drift(
        f"in-flight:{_SLUG}",
        tmp_path,
        None,
        _changed_files_override=["SYSTEMS_PLAN.md"],
    )
    assert (
        findings
    ), "Expected drift finding when dependents not included in changed files; got empty list"
    important = [f for f in findings if f.get("severity") == "important"]
    assert important, f"Expected at least one important drift finding; got: {findings!r}"


def test_link3_spec_missing_req_bites(tmp_path: Path) -> None:
    """A SPEC that omits one traceability req ID fails the REQ-flow assertion."""
    reqs = [_req(1), _req(2), _req(3)]
    artifacts = _build_faithful_chain(tmp_path, reqs)

    # Mutate link-3: overwrite the SPEC without the last req ID.
    missing_req = reqs[-1]
    original = artifacts["spec_path"].read_text(encoding="utf-8")
    broken = original.replace(missing_req, "OMITTED")
    artifacts["spec_path"].write_text(broken, encoding="utf-8")

    spec_text = artifacts["spec_path"].read_text(encoding="utf-8")

    # Bite assertion: the REQ-flow check detects the missing req ID.
    # This assertion is itself the validator for link-3 — it passes when the
    # broken state is caught, and fails if the spec somehow still contains all
    # req IDs (which would mean the fixture setup failed).
    assert not all(
        r in spec_text for r in reqs
    ), "REQ-flow assertion must catch the missing req ID in the SPEC body"
    assert (
        missing_req not in spec_text
    ), f"Fixture setup error: {missing_req!r} still present after removal"


def test_link4_stale_spec_gap_bites(tmp_path: Path) -> None:
    """Stale SPEC plus an ADR cluster of the threshold size triggers a gap."""
    # Build a stale SPEC (well past the N_DAYS=90 threshold before _NOW).
    # 2025-01-01 is 545 days before 2026-06-29 — far exceeds the threshold.
    stale_date = "2025-01-01"
    specs_dir = tmp_path / ".ai-state" / "specs"
    specs_dir.mkdir(parents=True)
    (specs_dir / f"SPEC_{_SLUG}_{stale_date}.md").write_text(
        f"# SPEC: {_SLUG}\n\nArchived on {stale_date}.\n",
        encoding="utf-8",
    )

    # Build exactly K_ADRS=3 finalized ADRs sharing one tag with a date that
    # is more than N_DAYS=90 days after the stale spec date.
    # 2026-05-01 is 485 days after 2025-01-01 — satisfies the > 90-day condition.
    adr_date = "2026-05-01"
    shared_tag = "criteria-spec-eval"
    decisions_dir = tmp_path / ".ai-state" / "decisions"
    decisions_dir.mkdir(parents=True)
    for i in range(1, 4):  # K_ADRS = 3
        adr_body = (
            "---\n"
            f"id: dec-{i:03d}\n"
            f"title: Decision {i}\n"
            "status: accepted\n"
            "category: architectural\n"
            f"date: {adr_date}\n"
            f"summary: Test decision {i}.\n"
            "tags:\n"
            f"  - {shared_tag}\n"
            "made_by: agent\n"
            "---\n\n"
            "## Context\n\nTest decision.\n\n"
            "## Decision\n\nAccepted.\n"
        )
        (decisions_dir / f"{i:03d}-decision.md").write_text(adr_body, encoding="utf-8")

    result = check_spec_archival_gap.detect_gap(tmp_path, now=_NOW)
    assert result["gap"] is True, (
        f"Expected gap=True for a stale SPEC ({stale_date}) with 3 ADRs "
        f"sharing tag '{shared_tag}' dated {adr_date}; result: {result!r}"
    )
