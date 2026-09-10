"""Tests for check_agent_prompt_size.py -- T03's per-agent line-count check.

Cites: rules/swe/gate-liveness.md -- a CODE gate ships a canary proving it
bites on a known-bad input, not merely that it passes on the current good
state.

The golden bad-case is drawn straight from the check's own docstring: a
synthetic `agents/sentinel.md` whose catalog *shrinks* by a retired dimension
while its prose *grows* by the same line count -- so the file's total line
count is UNCHANGED, and only the derived ceiling moves. A fixed ceiling
would pass this file unread; the derived ceiling must fall to meet it and
flag. The inverse guard proves the complementary claim: growing the catalog
(never shrinking it) must never change the verdict, because headroom is
invariant under catalog growth.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import check_agent_prompt_size as ck


def _write_agent(root: Path, name: str, line_count: int) -> Path:
    """Write `agents/<name>` with exactly `line_count` filler lines."""
    agents = root / "agents"
    agents.mkdir(parents=True, exist_ok=True)
    path = agents / name
    path.write_text("\n".join(f"line {i}" for i in range(line_count)) + "\n", encoding="utf-8")
    return path


def _synthetic_sentinel(catalog_rows: int, prose_lines: int) -> str:
    """Build a sentinel.md body: preamble, a `## Check Catalog` span of exactly
    `catalog_rows` rows (so `_catalog_span` measures `catalog_rows + 1`, the
    heading line itself counting), then a `## Findings` heading followed by
    `prose_lines` of prose.
    """
    lines = ["# Sentinel", "", "## Check Catalog"]
    lines.extend(f"| ID{i} | A | rule | pass |" for i in range(catalog_rows))
    lines.append("## Findings")
    lines.extend(f"prose line {i}" for i in range(prose_lines))
    return "\n".join(lines) + "\n"


def _write_sentinel(root: Path, catalog_rows: int, prose_lines: int) -> Path:
    agents = root / "agents"
    agents.mkdir(parents=True, exist_ok=True)
    path = agents / "sentinel.md"
    path.write_text(_synthetic_sentinel(catalog_rows, prose_lines), encoding="utf-8")
    return path


# -- Golden bad-case and inverse guard (sentinel.md's derived ceiling) --------


def test_shrinking_catalog_growing_prose_flips_the_derived_verdict(tmp_path: Path) -> None:
    """Golden bad-case: catalog shrinks by 50 rows, prose grows by 50 lines --
    total line count is IDENTICAL before and after (564 either way). A fixed
    700-line ceiling would pass both cuts unread; the derived ceiling falls
    with the catalog (601 -> 551) and must flag the second cut.
    """
    _write_sentinel(tmp_path, catalog_rows=300, prose_lines=260)
    assert ck.run_t03(tmp_path) == []  # baseline: under its own derived warn (601)

    _write_sentinel(tmp_path, catalog_rows=250, prose_lines=310)  # -50 catalog, +50 prose
    findings = ck.run_t03(tmp_path)

    assert len(findings) == 1
    assert findings[0]["entity"] == "agents/sentinel.md"
    assert findings[0]["severity"] == "warn"
    assert "derived" in findings[0]["message"]


def test_catalog_growth_alone_leaves_the_verdict_unchanged(tmp_path: Path) -> None:
    """Inverse guard: growing the catalog (never shrinking it) must not change
    the verdict -- each added row lifts the derived ceiling by exactly what it
    consumed, so headroom (37 lines here) is invariant under catalog growth.
    """
    _write_sentinel(tmp_path, catalog_rows=300, prose_lines=260)
    assert ck.run_t03(tmp_path) == []

    _write_sentinel(tmp_path, catalog_rows=380, prose_lines=260)  # +80 catalog rows only
    assert ck.run_t03(tmp_path) == []


# -- Standard agents and the fixed verifier.md exception ----------------------


def test_standard_agent_at_fail_ceiling_is_flagged_by_name(tmp_path: Path) -> None:
    _write_agent(tmp_path, "some-agent.md", 500)

    findings = ck.run_t03(tmp_path)

    assert len(findings) == 1
    assert findings[0]["entity"] == "agents/some-agent.md"
    assert findings[0]["severity"] == "fail"


def test_standard_agent_under_warn_ceiling_is_clean(tmp_path: Path) -> None:
    _write_agent(tmp_path, "some-agent.md", 399)
    assert ck.run_t03(tmp_path) == []


def test_verifier_uses_its_own_fixed_pair_not_the_standard_one(tmp_path: Path) -> None:
    """520 lines exceeds the standard fail ceiling (500) but sits under
    verifier.md's own fixed warn (550) -- proving the exception is actually
    applied, not merely documented.
    """
    _write_agent(tmp_path, "verifier.md", 520)
    assert ck.run_t03(tmp_path) == []


def test_catalog_files_are_excluded(tmp_path: Path) -> None:
    """CLAUDE.md and README.md carry no agent prompt body -- never sized."""
    _write_agent(tmp_path, "CLAUDE.md", 900)
    _write_agent(tmp_path, "README.md", 900)
    assert ck.run_t03(tmp_path) == []


def test_missing_agents_dir_is_a_skip_not_a_finding(tmp_path: Path) -> None:
    assert ck.run_t03(tmp_path) == []


# -- CLI contract: advisory by default -----------------------------------------


def test_exits_zero_by_default_even_with_findings(tmp_path: Path) -> None:
    """Advisory by construction -- it reports, it does not gate, unless asked to."""
    _write_agent(tmp_path, "some-agent.md", 500)
    rc = subprocess.run(
        [sys.executable, str(Path(ck.__file__)), "--json", "--repo-root", str(tmp_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert rc.returncode == 0
    assert '"fail"' in rc.stdout


def test_check_flag_exits_one_on_findings(tmp_path: Path) -> None:
    _write_agent(tmp_path, "some-agent.md", 500)
    rc = subprocess.run(
        [sys.executable, str(Path(ck.__file__)), "--check", "--repo-root", str(tmp_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert rc.returncode == 1


def test_live_repo_exits_zero_despite_a_warn_finding_for_sentinel_md() -> None:
    """Explicit acceptance check the plan names beyond the canary: the live
    repo's agents/sentinel.md already sits in derived WARN today (S=352 ->
    warn 652, file 680 lines) -- the exact risk this step is RISKY for.
    Default invocation (no --check) must still exit 0.
    """
    repo_root = Path(ck.__file__).resolve().parents[1]
    rc = subprocess.run(
        [sys.executable, str(Path(ck.__file__)), "--json", "--repo-root", str(repo_root)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert rc.returncode == 0
    payload = json.loads(rc.stdout)
    assert any(f["entity"] == "agents/sentinel.md" and f["severity"] == "warn" for f in payload)
