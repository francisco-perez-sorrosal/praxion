"""Tests for list_harvest_sources.py -- the /skill-genesis queue pre-flight.

Cites: rules/swe/gate-liveness.md -- a CODE gate ships a canary proving it
bites on a known-bad input, not merely that it passes on the current good
state.

The defect this script closes: a harvest queue was written to
`.ai-work/_harvest/<slug>/` for eleven days while the only reader globbed
`.ai-work/*/LEARNINGS.md` one level deep, so every queued directory was
invisible to the harvest. The fixture below reproduces the queue's real
shapes -- sources at depth one and two, consult fragments, a loose handoff
file at the queue root, and one source larger than any single batch -- and
the prior-report marker is exercised with a row copied verbatim from the
2026-09-04 report's "Learning Sources Consumed" table.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import list_harvest_sources as lhs

_SCRIPT = Path(__file__).resolve().parent / "list_harvest_sources.py"

# Verbatim row from .ai-state/skill_genesis_reports/SKILL_GENESIS_REPORT_2026-09-04_15-12-10.md
_REAL_REPORT_ROW = (
    "| LEARNINGS.md (current task, incl. Batch 21 + folded F1-F8/cells-A/B fragments) "
    "| `.ai-work/sidecar-placement/LEARNINGS.md` | 11 | Read |\n"
)


def _write(path: Path, size: int) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("x" * size)
    return path


def _queue(root: Path) -> Path:
    """A queue mirroring the real `.ai-work/_harvest/` layout."""
    q = root / ".ai-work" / "_harvest"
    _write(q / "sidecar-placement" / "sidecar-placement" / "LEARNINGS.md", 300)  # depth 2, oversize
    _write(
        q / "sidecar-placement" / "sidecar-placement" / "CONSULT_data-structure-specialist.md", 20
    )
    _write(q / "process-economy-p3-1" / "LEARNINGS.md", 90)  # depth 1
    _write(q / "process-economy-p3-1" / "VERIFICATION_REPORT.md", 60)
    _write(q / "process-economy-p3-2-adopt" / "LEARNINGS.md", 50)
    _write(q / "process-economy-p3-2-adopt" / "spike" / "LEARNINGS.md", 10)  # nested child source
    _write(q / "data-structures-pillar" / "beauty-dimensions" / "LEARNINGS.md", 30)
    _write(q / "data-structures-pillar" / "README.md", 5)  # parent with no harvestable file
    _write(q / "HANDOFF_PHASE2_P2-10.md", 40)  # loose file at the queue root: ignored
    _write(q / "empty-dir" / "WIP.md", 5)  # no harvestable file: not a source
    return q


def _reports(root: Path) -> Path:
    d = root / ".ai-state" / "skill_genesis_reports"
    d.mkdir(parents=True)
    (d / "SKILL_GENESIS_REPORT_2026-09-04_15-12-10.md").write_text(
        "## Learning Sources Consumed\n\n| Source | Path | Items Extracted | Status |\n|---|---|---|---|\n"
        + _REAL_REPORT_ROW
    )
    return d


def _memory(root: Path) -> Path:
    d = root / "memory"
    d.mkdir()
    (d / "project_process_economy_roadmap.md").write_text(
        "---\nname: process-economy-roadmap\n---\n\nP3.1 landed from the process-economy-p3-1 worktree.\n"
    )
    return d


def test_enumerates_sources_at_depth_one_and_two_and_ignores_loose_files(tmp_path: Path) -> None:
    q = _queue(tmp_path)
    sources = lhs.enumerate_sources(q, max_depth=2)
    rels = [s.rel for s in sources]
    assert rels == sorted(rels), "sources are emitted in path order so batches are reproducible"
    assert "sidecar-placement/sidecar-placement" in rels
    assert "process-economy-p3-1" in rels
    assert "process-economy-p3-2-adopt" in rels
    assert "process-economy-p3-2-adopt/spike" in rels
    assert "data-structures-pillar/beauty-dimensions" in rels
    assert "data-structures-pillar" not in rels, "a parent with only a README is not a source"
    assert "empty-dir" not in rels
    assert all("HANDOFF" not in r for r in rels), "loose files at the queue root are not sources"
    by_rel = {s.rel: s for s in sources}
    assert by_rel["process-economy-p3-1"].total_bytes == 150
    assert sorted(f.name for f in by_rel["sidecar-placement/sidecar-placement"].files) == [
        "CONSULT_data-structure-specialist.md",
        "LEARNINGS.md",
    ]


def test_prior_report_and_memory_markers(tmp_path: Path) -> None:
    q = _queue(tmp_path)
    reports = _reports(tmp_path)
    memory = _memory(tmp_path)
    sources = lhs.enumerate_sources(q, max_depth=2)
    marked = lhs.mark_promoted(sources, reports_dir=reports, memory_dir=memory)
    by_rel = {s.rel: s for s in marked}
    assert by_rel["sidecar-placement/sidecar-placement"].prior_report is True, (
        "the 2026-09-04 report cites `.ai-work/sidecar-placement/LEARNINGS.md`; the queue copy of that "
        "pipeline must read as already harvested"
    )
    assert by_rel["process-economy-p3-1"].prior_report is False
    assert by_rel["process-economy-p3-1"].memory is True, "a memory file names the slug"
    assert by_rel["process-economy-p3-2-adopt"].memory is False

    unmarked = lhs.mark_promoted(sources, reports_dir=reports, memory_dir=None)
    assert all(s.memory is None for s in unmarked), (
        "no memory dir -> the marker is withheld, not False"
    )


def test_batches_are_greedy_under_the_cap_and_an_oversize_source_stands_alone(
    tmp_path: Path,
) -> None:
    q = _queue(tmp_path)
    sources = lhs.enumerate_sources(q, max_depth=2)
    batches = lhs.plan_batches(sources, cap_bytes=200)
    for b in batches:
        assert b.oversize or b.total_bytes <= 200
    oversize = [b for b in batches if b.oversize]
    assert len(oversize) == 1
    assert [s.rel for s in oversize[0].sources] == ["sidecar-placement/sidecar-placement"]
    assert oversize[0].total_bytes == 320
    flat = [s.rel for b in batches for s in b.sources]
    assert flat == [s.rel for s in sources], "every source lands in exactly one batch, in order"


def test_cli_json_shape_and_text_mode(tmp_path: Path) -> None:
    q = _queue(tmp_path)
    _reports(tmp_path)
    cmd = [
        sys.executable,
        str(_SCRIPT),
        "--sources",
        str(q),
        "--cap",
        "200",
        "--repo-root",
        str(tmp_path),
    ]
    text = subprocess.run(cmd, capture_output=True, text=True, check=False)
    assert text.returncode == 0, text.stderr
    assert "sidecar-placement/sidecar-placement" in text.stdout
    assert "oversize" in text.stdout
    assert "Batch 1" in text.stdout

    js = subprocess.run([*cmd, "--json"], capture_output=True, text=True, check=False)
    assert js.returncode == 0, js.stderr
    payload = json.loads(js.stdout)
    assert payload["sources_dir"].endswith("_harvest")
    assert payload["cap_bytes"] == 200
    assert len(payload["sources"]) == 5
    src = {s["rel"]: s for s in payload["sources"]}
    assert src["sidecar-placement/sidecar-placement"]["prior_report"] is True
    assert src["sidecar-placement/sidecar-placement"]["memory"] is None
    assert {"rel", "slug", "files", "total_bytes", "prior_report", "memory"} <= set(
        src["process-economy-p3-1"]
    )
    assert all(
        {"index", "total_bytes", "oversize", "sources"} <= set(b) for b in payload["batches"]
    )


def test_cli_exits_two_when_the_queue_is_missing_or_empty(tmp_path: Path) -> None:
    missing = subprocess.run(
        [
            sys.executable,
            str(_SCRIPT),
            "--sources",
            str(tmp_path / "nope"),
            "--repo-root",
            str(tmp_path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert missing.returncode == 2
    assert "no harvest sources" in (missing.stdout + missing.stderr).lower()

    empty = tmp_path / ".ai-work" / "_harvest"
    _write(empty / "only-a-handoff.md", 3)
    r = subprocess.run(
        [sys.executable, str(_SCRIPT), "--sources", str(empty), "--repo-root", str(tmp_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert r.returncode == 2
