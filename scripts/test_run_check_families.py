"""Tests for run_check_families.py -- the Family dispatch aggregator canary.

Builds a fake `agents/sentinel.md` with a two-row Family dispatch table
pointing at two tiny stub scripts under `tmp_path/scripts/` -- one emitting a
keyed JSON envelope with findings, one exiting non-zero with no usable
stdout. Also parses the LIVE `agents/sentinel.md` table (no execution) to
pin the real dispatch surface.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from run_check_families import (  # noqa: E402
    CheckAggregate,
    RunnerError,
    build_aggregate,
    parse_dispatch_table,
    render_table,
)

_GOOD_SCRIPT = '''"""Stub family script emitting a keyed envelope with one finding."""
import json

print(json.dumps({
    "script": "check_stub_good",
    "checks": ["ST01"],
    "skipped": {"ST01": None},
    "examined": {"ST01": {"items": 3}},
    "findings": [
        {
            "check": "ST01",
            "severity": "warn",
            "entity": "stub/thing.py",
            "message": "stub finding for canary coverage",
        }
    ],
    "info": {},
    "withheld": [],
    "bound": {"ST01": "ST01 clean means the stub found nothing."},
}))
'''

_BAD_SCRIPT = '''"""Stub family script that crashes instead of emitting JSON."""
import sys

print("not json, a traceback would land here", file=sys.stderr)
sys.exit(1)
'''

_SENTINEL_MD = """# sentinel

Some preamble text.

**Family dispatch (auto).** For every family script in the table: run it once.

| Substrate (skip when absent) | Invocation | Rows |
|---|---|---|
| always | `python3 scripts/check_stub_good.py --json` | ST01 |
| always | `python3 scripts/check_stub_bad.py --json` | ST02 |

This pass is deterministic and fast.
"""


def _build_fixture_repo(tmp_path: Path) -> Path:
    (tmp_path / "agents").mkdir()
    (tmp_path / "agents" / "sentinel.md").write_text(_SENTINEL_MD, encoding="utf-8")
    scripts_dir = tmp_path / "scripts"
    scripts_dir.mkdir()
    (scripts_dir / "check_stub_good.py").write_text(_GOOD_SCRIPT, encoding="utf-8")
    (scripts_dir / "check_stub_bad.py").write_text(_BAD_SCRIPT, encoding="utf-8")
    return tmp_path


# -- table parsing ----------------------------------------------------------


def test_parse_dispatch_table_reads_both_rows(tmp_path: Path) -> None:
    repo = _build_fixture_repo(tmp_path)
    rows = parse_dispatch_table(repo / "agents" / "sentinel.md")
    assert [r.family for r in rows] == ["check_stub_good", "check_stub_bad"]
    assert rows[0].check_ids == ("ST01",)
    assert rows[1].check_ids == ("ST02",)


def test_parse_dispatch_table_rejects_a_missing_header(tmp_path: Path) -> None:
    """Canary: a sentinel.md with no Family dispatch table raises rather than
    silently returning an empty dispatch list."""
    sentinel_md = tmp_path / "sentinel.md"
    sentinel_md.write_text("# sentinel\n\nno table here.\n", encoding="utf-8")
    with pytest.raises(ValueError, match="Family dispatch header not found"):
        parse_dispatch_table(sentinel_md)


def test_parse_dispatch_table_on_the_live_sentinel_finds_at_least_ten_families() -> None:
    """The real Family dispatch table currently lists ~11 rows -- pin a floor of 10
    so a future edit that accidentally drops rows is detected."""
    rows = parse_dispatch_table(REPO_ROOT / "agents" / "sentinel.md")
    assert len(rows) >= 10, (
        f"expected >= 10 families, found {len(rows)}: {[r.family for r in rows]}"
    )


# -- aggregation + runner-error handling -------------------------------------


def test_build_aggregate_flags_a_missing_script_as_runner_error(tmp_path: Path) -> None:
    """Canary: a dispatch row naming a script that does not exist on disk becomes
    a runner-error entry, not a crash."""
    repo = _build_fixture_repo(tmp_path)
    (repo / "scripts" / "check_stub_bad.py").unlink()
    rows = parse_dispatch_table(repo / "agents" / "sentinel.md")

    aggregate = build_aggregate(rows, repo, timeout=10.0, max_entities=5)

    assert len(aggregate["runner_errors"]) == 1
    error = aggregate["runner_errors"][0]
    assert error.family == "check_stub_bad"
    assert "not found" in error.reason


def test_build_aggregate_detects_unparseable_stdout_from_a_bad_script(tmp_path: Path) -> None:
    """Canary: a script that exits non-zero with non-JSON stdout is a runner error,
    and the aggregate for the other (good) family is still produced."""
    repo = _build_fixture_repo(tmp_path)
    rows = parse_dispatch_table(repo / "agents" / "sentinel.md")

    aggregate = build_aggregate(rows, repo, timeout=10.0, max_entities=5)

    assert len(aggregate["runner_errors"]) == 1
    assert aggregate["runner_errors"][0].family == "check_stub_bad"

    assert "ST01" in aggregate["checks"]
    st01 = aggregate["checks"]["ST01"]
    assert st01.warn == 1
    assert st01.fail == 0
    assert st01.entities == [("stub/thing.py", "stub finding for canary coverage")]

    assert aggregate["totals"]["families"] == 2
    assert aggregate["totals"]["warn"] == 1


def test_build_aggregate_counts_still_include_the_invalid_family_row(tmp_path: Path) -> None:
    """Canary: families total counts every dispatch row, including the failed one --
    it must not silently shrink the denominator."""
    repo = _build_fixture_repo(tmp_path)
    rows = parse_dispatch_table(repo / "agents" / "sentinel.md")
    aggregate = build_aggregate(rows, repo, timeout=10.0, max_entities=5)
    statuses = {f["name"]: f["status"] for f in aggregate["families"]}
    assert statuses == {"check_stub_good": "ok", "check_stub_bad": "runner-error"}


# -- table rendering ----------------------------------------------------------


def test_render_table_shape_has_the_documented_header_and_footer(tmp_path: Path) -> None:
    repo = _build_fixture_repo(tmp_path)
    rows = parse_dispatch_table(repo / "agents" / "sentinel.md")
    aggregate = build_aggregate(rows, repo, timeout=10.0, max_entities=5)

    table = render_table(aggregate, max_entities=5)

    assert (
        "| Check | Family | FAIL | WARN | INFO | Skipped | Examined | Withheld | Sample entity | Bound |"
        in table
    )
    assert "| ST01 | check_stub_good | 0 | 1 | 0 |" in table
    assert "### Runner errors" in table
    assert "check_stub_bad" in table
    assert "calls saved: 2 → 1" in table
    assert "fail: 0" in table
    assert "warn: 1" in table


# -- CLI exit code -------------------------------------------------------------


def test_cli_exits_zero_even_when_a_family_is_invalid(tmp_path: Path) -> None:
    """Canary: the runner's own exit code stays 0 -- an advisory aggregator over
    scripts with their own gating semantics, never a gate itself -- even though
    one family in this fixture crashes."""
    repo = _build_fixture_repo(tmp_path)
    runner = REPO_ROOT / "scripts" / "run_check_families.py"

    result = subprocess.run(
        [sys.executable, str(runner), "--repo-root", str(repo), "--json"],
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert result.returncode == 0, result.stderr
    assert "runner-error" in result.stdout


def test_render_table_carries_bound_and_keeps_a_failed_familys_checks(tmp_path: Path) -> None:
    """Light-review wrap F1/W3: the digest must reproduce each check's `bound` (the preamble
    tells the sentinel to copy it verbatim) and must list a runner-error family's check ids
    as skipped rather than dropping them (absence reads as clean)."""
    aggregate = {
        "checks": {
            "Z01": CheckAggregate(family="good", bound="Z01 clean means nothing is missing."),
            "Z02": CheckAggregate(
                family="bad", skipped={"reason": "runner-error", "detail": "exit 2"}
            ),
        },
        "runner_errors": [
            RunnerError(family="bad", invocation="python3 scripts/bad.py --json", reason="exit 2")
        ],
        "totals": {"families": 2, "checks": 2, "fail": 0, "warn": 0, "info": 0},
    }
    table = render_table(aggregate, max_entities=5)
    assert "Z01 clean means nothing is missing." in table
    assert "| Z02 | bad |" in table
    assert "runner-error" in table
