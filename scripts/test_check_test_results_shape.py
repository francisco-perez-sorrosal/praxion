"""Canary tests for scripts/check_test_results_shape.py.

Cites: rules/swe/gate-liveness.md -- every CODE gate ships a sibling canary
proving it fails on a known-bad input. These tests feed the detector an
oversized green section and a section with no Result: line and assert both
are flagged, alongside happy-path, red-section, and --ceiling-override cases.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

_SCRIPT_PATH = Path(__file__).resolve().parent / "check_test_results_shape.py"


def _load_module() -> Any:
    spec = importlib.util.spec_from_file_location("check_test_results_shape", _SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["check_test_results_shape"] = mod
    spec.loader.exec_module(mod)
    return mod


_mod = _load_module()
main = _mod.main
find_findings = _mod.find_findings
DEFAULT_CEILING_BYTES = _mod.DEFAULT_CEILING_BYTES


def _write(root: Path, rel: str, body: str) -> Path:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body, encoding="utf-8")
    return p


def _fixed_shape_green(padding: str = "") -> str:
    return (
        "## Step 1 — a step\n"  # id-citation-discipline:ignore
        "\n"
        "Command: `uv run pytest tests/ -q --tb=short -rf`\n"
        "Result: pass=42 fail=0 skip=0\n"
        "Duration: 3.1s\n"
        f"{padding}"
    )


# ---------------------------------------------------------------------------
# Canary: violations are flagged
# ---------------------------------------------------------------------------


def test_green_section_over_ceiling_is_flagged(tmp_path: Path) -> None:
    """A planted green section of ceiling+1 bytes is flagged as green-over-ceiling."""
    padding = "x" * (DEFAULT_CEILING_BYTES + 1)
    body = _fixed_shape_green(padding=padding)
    path = _write(tmp_path, "TEST_RESULTS.md", body)

    rc = main([str(path)])

    assert rc == 1, "a green section over the ceiling must exit 1"
    findings = find_findings(path, DEFAULT_CEILING_BYTES)
    assert len(findings) == 1
    assert findings[0].kind == "green-over-ceiling"


def test_section_with_no_result_line_is_flagged(tmp_path: Path) -> None:
    """A section with no Result: line at all is flagged as missing-result-line."""
    body = "## Step 1 — a step\n\nCommand: `uv run pytest tests/ -q --tb=short -rf`\n"  # id-citation-discipline:ignore
    path = _write(tmp_path, "TEST_RESULTS.md", body)

    rc = main([str(path)])

    assert rc == 1, "a section with no Result: line must exit 1"
    findings = find_findings(path, DEFAULT_CEILING_BYTES)
    assert len(findings) == 1
    assert findings[0].kind == "missing-result-line"


# ---------------------------------------------------------------------------
# Happy path: green at fixed shape, red of any size, --ceiling override
# ---------------------------------------------------------------------------


def test_green_section_at_fixed_shape_passes(tmp_path: Path) -> None:
    """A green section following the fixed shape (well under the ceiling) is clean."""
    path = _write(tmp_path, "TEST_RESULTS.md", _fixed_shape_green())

    rc = main([str(path)])

    assert rc == 0, "a fixed-shape green section must exit 0"


def test_large_red_section_is_not_flagged(tmp_path: Path) -> None:
    """A 5 KB red section (fail > 0) is never flagged for size."""
    failure_block = "### Failures\n" + ("some failure detail line\n" * 200)  # ~5 KB
    body = (
        "## Step 1 — a step\n"  # id-citation-discipline:ignore
        "\n"
        "Command: `uv run pytest tests/ -q --tb=short -rf`\n"
        "Result: pass=10 fail=2 skip=0\n"
        "Duration: 4.0s\n"
        f"{failure_block}"
    )
    path = _write(tmp_path, "TEST_RESULTS.md", body)
    assert len(body.encode("utf-8")) > 5000

    rc = main([str(path)])

    assert rc == 0, "a red section must never be flagged regardless of size"


def test_ceiling_override_is_honoured(tmp_path: Path) -> None:
    """A --ceiling override changes the threshold used for green-over-ceiling."""
    padding = "x" * 200
    body = _fixed_shape_green(padding=padding)
    path = _write(tmp_path, "TEST_RESULTS.md", body)

    # Default ceiling (1024) is not exceeded by this small section.
    assert main([str(path)]) == 0

    # A tiny override ceiling makes the same section exceed it.
    rc = main([str(path), "--ceiling", "10"])
    assert rc == 1, "a lowered --ceiling must flag a section it would otherwise pass"


def test_main_exits_zero_with_no_findings(tmp_path: Path) -> None:
    """end-to-end: main() returns 0 when every section is clean."""
    path = _write(tmp_path, "TEST_RESULTS.md", _fixed_shape_green())

    rc = main([str(path)])

    assert rc == 0, f"main() must return 0 with no findings; got {rc}"


# ---------------------------------------------------------------------------
# --json shape
# ---------------------------------------------------------------------------


def test_json_output_shape(tmp_path: Path, capsys: Any) -> None:
    """--json emits a `findings` list with kind/section/file/detail per entry."""
    padding = "x" * (DEFAULT_CEILING_BYTES + 1)
    path = _write(tmp_path, "TEST_RESULTS.md", _fixed_shape_green(padding=padding))

    rc = main([str(path), "--json"])
    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert rc == 1
    assert "findings" in payload
    assert len(payload["findings"]) == 1
    finding = payload["findings"][0]
    assert finding["kind"] == "green-over-ceiling"
    assert finding["section"] == "Step 1 — a step"  # id-citation-discipline:ignore
    assert "bytes" in finding
    assert "ceiling" in finding


# ---------------------------------------------------------------------------
# Script error (exit 2)
# ---------------------------------------------------------------------------


def test_missing_file_exits_two(tmp_path: Path) -> None:
    """A FILE argument that does not exist on disk is a script error, exit 2."""
    rc = main([str(tmp_path / "does_not_exist.md")])

    assert rc == 2, "an unreadable file must exit 2, not be silently skipped"
