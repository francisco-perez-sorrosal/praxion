"""Tests for check_agent_lifecycle_pairing.py -- P03's agent-lifecycle pairing check.

Cites: rules/swe/gate-liveness.md -- a CODE gate ships a canary proving it
bites on a known-bad input, not merely that it passes on the current good
state.

The main golden bad-case is drawn from the check's own docstring: a burst of
unpaired starts sharing one session, one narrow window and one agent_type
that matches no file in agents/, none of which ran any tool_use, occurring
alongside a scattering of unpaired starts across other sessions that each
did run tool_use. The check must report the burst as one info.incidents
entry, the scattered ones as separate WARN findings, and never sum the two --
proven here by a total-count assertion (every unpaired start lands in
exactly one bucket) rather than by eyeballing individual counts.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import check_agent_lifecycle_pairing as clp

_POST_BASELINE = "2026-09-06T00:00:00+00:00"
_PRE_BASELINE = "2026-09-01T00:00:00+00:00"


def _row(
    event_type: str,
    agent_id: str,
    *,
    agent_type: str = "praxion:implementer",
    session_id: str = "s1",
    timestamp: str = _POST_BASELINE,
    start_correlation: str | None = None,
) -> dict:
    row: dict = {
        "event_type": event_type,
        "agent_id": agent_id,
        "agent_type": agent_type,
        "session_id": session_id,
        "timestamp": timestamp,
    }
    if start_correlation is not None:
        row["start_correlation"] = start_correlation
    return row


def _write_wal(tmp_path: Path, rows: list[dict]) -> Path:
    obs_dir = tmp_path / ".ai-state"
    obs_dir.mkdir(parents=True, exist_ok=True)
    path = obs_dir / "observations.jsonl"
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    return path


def _known_agent(tmp_path: Path, name: str) -> None:
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir(parents=True, exist_ok=True)
    (agents_dir / f"{name}.md").write_text(f"# {name}\n", encoding="utf-8")


# -- Substrate absence ------------------------------------------------------------


def test_missing_observations_file_is_a_skip_not_a_finding(tmp_path: Path) -> None:
    report = clp.classify(tmp_path)
    assert report["skipped"] is not None
    assert report["skipped"]["reason"] == "substrate-absent"
    assert report["findings"] == []


# -- Pairing is on agent_id, never agent_type --------------------------------------


def test_warn_pairs_on_agent_id_not_agent_type(tmp_path: Path) -> None:
    """Two same-typed siblings, only one stops -- the type-pairing trap must not clear the other."""
    rows = [
        _row("agent_start", "a1", agent_type="typeX", session_id="s-old", timestamp=_POST_BASELINE),
        _row("agent_start", "a2", agent_type="typeX", session_id="s-old", timestamp=_POST_BASELINE),
        _row("agent_stop", "a1", agent_type="typeX", session_id="s-old"),
        _row("tool_use", "a1", agent_type="typeX", session_id="s-old"),
        _row("tool_use", "a2", agent_type="typeX", session_id="s-old"),
        # Sentinel newest row in its own session -- excludes nothing tested above.
        _row("agent_start", "sentinel", session_id="s-newest"),
    ]
    _write_wal(tmp_path, rows)

    report = clp.classify(tmp_path)

    assert [f["entity"] for f in report["findings"]] == ["a2"]
    assert "typeX" in report["findings"][0]["message"]


# -- Main golden bad-case: burst vs. scattered, total-count assertion --------------


def test_golden_bad_case_burst_vs_scattered_total_count(tmp_path: Path) -> None:
    _known_agent(tmp_path, "implementer")
    rows = [
        # Burst: 3 unpaired starts, one session, one unknown agent_type, a
        # 10-minute window, none ran tool_use.
        _row(
            "agent_start",
            "burst1",
            agent_type="not-a-real-agent",
            session_id="s-burst",
            timestamp="2026-09-06T10:00:00+00:00",
        ),
        _row(
            "agent_start",
            "burst2",
            agent_type="not-a-real-agent",
            session_id="s-burst",
            timestamp="2026-09-06T10:05:00+00:00",
        ),
        _row(
            "agent_start",
            "burst3",
            agent_type="not-a-real-agent",
            session_id="s-burst",
            timestamp="2026-09-06T10:10:00+00:00",
        ),
        # Scattered: 2 unpaired starts, each its own session, each ran tool_use.
        _row(
            "agent_start",
            "scat1",
            agent_type="praxion:implementer",
            session_id="s-scatter-1",
            timestamp=_POST_BASELINE,
        ),
        _row("tool_use", "scat1", session_id="s-scatter-1"),
        _row(
            "agent_start",
            "scat2",
            agent_type="praxion:implementer",
            session_id="s-scatter-2",
            timestamp=_POST_BASELINE,
        ),
        _row("tool_use", "scat2", session_id="s-scatter-2"),
        # Cleanly-paired control: must never appear in any bucket.
        _row("agent_start", "clean1", session_id="s-clean", timestamp=_POST_BASELINE),
        _row("agent_stop", "clean1", session_id="s-clean"),
        # In-flight: the newest session in the file, excluded from pairing
        # entirely even though it looks like an unpaired, tool-using start.
        _row("agent_start", "inflight1", session_id="s-newest", timestamp=_POST_BASELINE),
        _row("tool_use", "inflight1", session_id="s-newest"),
    ]
    _write_wal(tmp_path, rows)

    report = clp.classify(tmp_path)

    incidents = report["info"]["incidents"]
    assert len(incidents) == 1
    assert incidents[0]["session_id"] == "s-burst"
    assert incidents[0]["count"] == 3
    assert incidents[0]["not_this_fleet"] is True

    # Set equality already proves clean1/inflight1 are absent from findings --
    # the cleanly-paired control and the excluded in-flight start must never
    # surface as WARNs.
    warn_entities = {f["entity"] for f in report["findings"]}
    assert warn_entities == {"scat1", "scat2"}

    total_unpaired = 5  # 3 burst + 2 scattered; clean1 paired, inflight1 excluded
    accounted = (
        sum(i["count"] for i in incidents)
        + len(report["findings"])
        + len(report["info"]["pre_baseline"])
        + len(report["info"]["no_tool_use"])
    )
    assert accounted == total_unpaired


# -- Inverse guard: in-flight session excluded entirely ----------------------------


def test_inverse_guard_newest_session_start_produces_zero_findings(tmp_path: Path) -> None:
    rows = [
        _row("agent_start", "old1", session_id="s-old", timestamp=_POST_BASELINE),
        _row("agent_stop", "old1", session_id="s-old"),
        # The newest record in the file: an unpaired, tool-using start that
        # would WARN if it were examined -- it must not be, since it is in flight.
        _row("agent_start", "newest1", session_id="s-newest", timestamp=_POST_BASELINE),
        _row("tool_use", "newest1", session_id="s-newest"),
    ]
    _write_wal(tmp_path, rows)

    report = clp.classify(tmp_path)

    assert report["findings"] == []
    assert report["examined"]["excluded_in_flight_session"] == "s-newest"


# -- Pre-baseline classification ---------------------------------------------------


def test_pre_baseline_unpaired_start_is_info_not_warn(tmp_path: Path) -> None:
    rows = [
        _row("agent_start", "old1", session_id="s-pre", timestamp=_PRE_BASELINE),
        _row("tool_use", "old1", session_id="s-pre"),
        _row("agent_start", "sentinel", session_id="s-newest", timestamp=_POST_BASELINE),
    ]
    _write_wal(tmp_path, rows)

    report = clp.classify(tmp_path)

    assert report["findings"] == []
    assert [p["agent_id"] for p in report["info"]["pre_baseline"]] == ["old1"]


# -- Unmatched-stop classification: three distinct outputs, never one count --------


def test_unmatched_stops_classification(tmp_path: Path) -> None:
    rows = [
        # u1: no start anywhere, but a tool_use row exists elsewhere for it
        # (any_row_seen=True) and it self-reports "unobserved-start" --
        # agrees with the freshly-derived WAL verdict.
        _row("tool_use", "u1", session_id="s-u1-evidence"),
        _row(
            "agent_stop",
            "u1",
            session_id="s-u",
            start_correlation=clp.CORRELATION_UNOBSERVED_START,
        ),
        # u2: no row anywhere else (any_row_seen=False), self-reports
        # "unobserved-agent" -- agrees.
        _row(
            "agent_stop",
            "u2",
            session_id="s-u",
            start_correlation=clp.CORRELATION_UNOBSERVED_AGENT,
        ),
        # u3: no self-reported field at all -- unattested, never agreement.
        _row("agent_stop", "u3", session_id="s-u"),
        # u4: self-reports "paired" despite this classifier finding no start
        # for it -- the WAL wins, and the disagreement is the finding.
        _row(
            "agent_stop",
            "u4",
            session_id="s-u",
            start_correlation=clp.CORRELATION_PAIRED,
        ),
        # u5: cleanly paired by this classifier's own pairing, but its
        # field nonetheless reads "unobserved-start" -- must be excluded
        # from unmatched-stop processing entirely, regardless of the field.
        _row("agent_start", "u5", session_id="s-u", timestamp=_POST_BASELINE),
        _row(
            "agent_stop",
            "u5",
            session_id="s-u",
            start_correlation=clp.CORRELATION_UNOBSERVED_START,
        ),
        _row("agent_start", "sentinel", session_id="s-newest", timestamp=_POST_BASELINE),
    ]
    _write_wal(tmp_path, rows)

    report = clp.classify(tmp_path)

    unmatched = report["info"]["unmatched_stops"]
    assert unmatched[clp.CORRELATION_UNOBSERVED_START] == ["u1"]
    assert unmatched[clp.CORRELATION_UNOBSERVED_AGENT] == ["u2"]
    assert unmatched["unattested"] == ["u3"]

    # u5 is cleanly paired, so it must appear in none of the above -- already
    # proven by the exact single-element equalities: each bucket contains
    # only its intended member, leaving no room for u5 to have slipped in.
    disagreements = report["info"]["producer_log_disagreement"]
    assert [d["agent_id"] for d in disagreements] == ["u4"]


# -- Withheld: malformed lines never silently dropped -------------------------------


def test_malformed_line_is_withheld_not_silently_dropped(tmp_path: Path) -> None:
    obs_dir = tmp_path / ".ai-state"
    obs_dir.mkdir(parents=True)
    path = obs_dir / "observations.jsonl"
    path.write_text(
        'not json\n{"event_type": "agent_start", "agent_id": "a1", '
        '"session_id": "s1", "timestamp": "' + _POST_BASELINE + '"}\n',
        encoding="utf-8",
    )

    report = clp.classify(tmp_path)

    assert len(report["withheld"]) == 1
    assert "line 1" in report["withheld"][0]


# -- CLI contract ----------------------------------------------------------------


def test_exits_zero_by_default_even_with_findings(tmp_path: Path) -> None:
    rows = [
        _row("agent_start", "a1", timestamp=_POST_BASELINE),
        _row("tool_use", "a1"),
        _row("agent_start", "sentinel", session_id="s-newest", timestamp=_POST_BASELINE),
    ]
    _write_wal(tmp_path, rows)
    rc = subprocess.run(
        [sys.executable, str(Path(clp.__file__)), "--json", "--repo-root", str(tmp_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert rc.returncode == 0
    assert '"warn"' in rc.stdout


def test_check_flag_exits_one_on_findings(tmp_path: Path) -> None:
    rows = [
        _row("agent_start", "a1", timestamp=_POST_BASELINE),
        _row("tool_use", "a1"),
        _row("agent_start", "sentinel", session_id="s-newest", timestamp=_POST_BASELINE),
    ]
    _write_wal(tmp_path, rows)
    rc = subprocess.run(
        [sys.executable, str(Path(clp.__file__)), "--check", "--repo-root", str(tmp_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert rc.returncode == 1


def test_exits_zero_when_substrate_absent(tmp_path: Path) -> None:
    rc = subprocess.run(
        [sys.executable, str(Path(clp.__file__)), "--check", "--repo-root", str(tmp_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert rc.returncode == 0


# -- Guarded import (rules/swe/gate-liveness.md GL05) -----------------------------


def test_missing_capture_session_exits_with_remedy_not_a_bare_traceback(tmp_path: Path) -> None:
    """The ambient-interpreter case: `hooks/capture_session.py` is unreachable.

    Runs a real copy of this script from an isolated tree whose `hooks/`
    directory has no `capture_session.py`, reproducing exactly what the
    ambient `python3` invocation in agents/sentinel.md would hit if the WAL
    emitter were missing. Non-vacuous: a bare `except ImportError: pass` or a
    reverted guard would print a `Traceback (most recent call last):` here
    instead of the remedy message, so this assertion fails the moment the
    guard is removed or degrades to a silent fallback -- it does not just
    confirm the current exit code.
    """
    fake_root = tmp_path / "fake_repo"
    (fake_root / "scripts").mkdir(parents=True)
    (fake_root / "hooks").mkdir(parents=True)  # present but empty -- no capture_session.py
    real_scripts_dir = Path(clp.__file__).resolve().parent
    for name in ("check_agent_lifecycle_pairing.py", "_repo_root.py", "_script_cli.py"):
        (fake_root / "scripts" / name).write_text(
            (real_scripts_dir / name).read_text(encoding="utf-8"), encoding="utf-8"
        )

    rc = subprocess.run(
        [sys.executable, str(fake_root / "scripts" / "check_agent_lifecycle_pairing.py")],
        capture_output=True,
        text=True,
        check=False,
    )

    assert rc.returncode != 0
    assert "Traceback (most recent call last)" not in rc.stderr
    assert "capture_session is not importable" in rc.stderr
    assert sys.executable in rc.stderr
