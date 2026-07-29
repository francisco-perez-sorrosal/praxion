"""Canary tests for scripts/check_html_authorship.py.

Cites: rules/swe/gate-liveness.md -- every CODE gate ships a sibling canary proving
it fails on a known-bad input. These tests feed the detector an orphaned HTML file
and a share_out-less sibling and assert both are flagged, alongside happy-path and
allowlist cases.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path
from typing import Any

_SCRIPT_PATH = Path(__file__).resolve().parent / "check_html_authorship.py"


def _load_module() -> Any:
    spec = importlib.util.spec_from_file_location("check_html_authorship", _SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["check_html_authorship"] = mod
    spec.loader.exec_module(mod)
    return mod


_mod = _load_module()
main = _mod.main


def _write(root: Path, rel: str, body: str) -> Path:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body, encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# Canary: violations are flagged
# ---------------------------------------------------------------------------


def test_orphaned_html_with_no_md_sibling_is_flagged(tmp_path: Path) -> None:
    """An .html file with no MD source at all is a violation."""
    _write(tmp_path, "reports/orphan.html", "<html><body>orphan</body></html>\n")

    rc = main(
        [
            "--repo-root",
            str(tmp_path),
            "--files",
            str(tmp_path / "reports" / "orphan.html"),
        ]
    )

    assert rc == 1, "orphaned HTML with no MD sibling must exit 1"


def test_sibling_md_without_share_out_is_flagged(tmp_path: Path) -> None:
    """An .html file whose sibling .md exists but lacks share_out: true is a violation."""
    _write(tmp_path, "reports/report.html", "<html><body>report</body></html>\n")
    _write(
        tmp_path,
        "reports/report.md",
        "---\ntitle: Report\n---\n\n# Report\n",
    )

    rc = main(
        [
            "--repo-root",
            str(tmp_path),
            "--files",
            str(tmp_path / "reports" / "report.html"),
        ]
    )

    assert rc == 1, "sibling MD without share_out: true must exit 1"


def test_sibling_md_with_share_out_false_is_flagged(tmp_path: Path) -> None:
    """An .html file whose sibling .md explicitly sets share_out: false is a violation."""
    _write(tmp_path, "reports/report.html", "<html><body>report</body></html>\n")
    _write(
        tmp_path,
        "reports/report.md",
        "---\ntitle: Report\nshare_out: false\n---\n\n# Report\n",
    )

    rc = main(
        [
            "--repo-root",
            str(tmp_path),
            "--files",
            str(tmp_path / "reports" / "report.html"),
        ]
    )

    assert rc == 1, "sibling MD with share_out: false must exit 1"


# ---------------------------------------------------------------------------
# Happy path + allowlist
# ---------------------------------------------------------------------------


def test_sibling_md_with_share_out_true_passes(tmp_path: Path) -> None:
    """An .html file with a share_out: true MD sibling is clean."""
    _write(tmp_path, "reports/report.html", "<html><body>report</body></html>\n")
    _write(
        tmp_path,
        "reports/report.md",
        "---\ntitle: Report\nshare_out: true\n---\n\n# Report\n",
    )

    rc = main(
        [
            "--repo-root",
            str(tmp_path),
            "--files",
            str(tmp_path / "reports" / "report.html"),
        ]
    )

    assert rc == 0, "sibling MD with share_out: true must exit 0"


def test_allowlisted_path_with_no_sibling_passes(tmp_path: Path) -> None:
    """An .html file under an EXEMPT_PATH_PREFIXES entry passes with no MD sibling."""
    _write(
        tmp_path,
        "scripts/praxion_parallel_ui_assets/index.html",
        "<html><body>tool ui</body></html>\n",
    )

    rc = main(
        [
            "--repo-root",
            str(tmp_path),
            "--files",
            str(tmp_path / "scripts" / "praxion_parallel_ui_assets" / "index.html"),
        ]
    )

    assert rc == 0, "allowlisted path with no MD sibling must exit 0"


def test_main_exits_zero_when_no_html_files_given(tmp_path: Path) -> None:
    """end-to-end: main() returns 0 when the file list has no matching .html files."""
    rc = main(["--repo-root", str(tmp_path), "--files"])

    assert rc == 0, f"main() must return 0 with no files; got {rc}"


# ---------------------------------------------------------------------------
# Default (no --files) mode: scoped to git-tracked files, not an unscoped rglob
# ---------------------------------------------------------------------------


def test_default_mode_scans_only_tracked_html_ignoring_untracked(tmp_path: Path) -> None:
    """With no --files flag, only git-tracked .html files are scanned -- an
    untracked orphan (e.g. gitignored build output) must not be flagged."""
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "test"], cwd=tmp_path, check=True)

    tracked_html = _write(tmp_path, "docs/report.html", "<html><body>report</body></html>\n")
    _write(tmp_path, "docs/report.md", "---\nshare_out: true\n---\n\n# Report\n")
    subprocess.run(["git", "add", "docs/report.html", "docs/report.md"], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "add report"], cwd=tmp_path, check=True)

    _write(tmp_path, "node_modules/pkg/orphan.html", "<html><body>vendored</body></html>\n")

    rc = main(["--repo-root", str(tmp_path)])

    assert rc == 0, "untracked orphan under an unscoped path must not fail the gate"
    assert tracked_html.is_file()
