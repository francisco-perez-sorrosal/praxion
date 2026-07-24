"""Behavioral tests for the cross-model review hub's verdict parser.

The hub (`.github/workflows/reusable-cross-model-review.yml`) embeds its verdict
parser inline as a heredoc — it MUST stay inline because the reusable workflow is
consumed cross-repo and cannot depend on a script that only exists in the
developing repo (same self-containment reason the policy parser is inline). That
makes the parser un-importable, so these tests extract the embedded Python from
the workflow and exec it against synthetic fixtures.

Why this file exists: a live dogfood proved the Cursor CLI's
`--output-format json` envelope is
`{"type":"result","is_error":<bool>,"result":"<agent answer STRING>", ...}` — the
agent's answer (the stringified `{"verdict":..., "findings":[...]}`) lives in the
`.result` STRING. An earlier parser was over-fit to a different assumed shape.
These tests pin the confirmed shape as the primary path and assert that every
failure mode fail-opens to `unavailable` (never raises, never blocks).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
HUB_WORKFLOW_FILE = PROJECT_ROOT / ".github" / "workflows" / "reusable-cross-model-review.yml"

_HEREDOC_OPEN = "python3 - <<'PY'"


def _extract_parser_source() -> str:
    """Pull the act-step verdict parser (the `python3 - <<'PY' ... PY` block)
    out of the workflow and dedent it to runnable module source."""
    text = HUB_WORKFLOW_FILE.read_text(encoding="utf-8")
    start = text.index(_HEREDOC_OPEN) + len(_HEREDOC_OPEN)
    body_lines = text[start:].splitlines()
    collected: list[str] = []
    for line in body_lines:
        if line.strip() == "PY":
            break
        collected.append(line)
    # Drop a leading blank line if present, then dedent the YAML block indent.
    if collected and collected[0].strip() == "":
        collected = collected[1:]
    return textwrap.dedent("\n".join(collected))


def _run_parser(
    raw_output: str, *, reviewer_family: str, resolved_model: str, tmp_path: Path
) -> str:
    """Exec the extracted parser against a synthetic `tmp/review-raw.json` and
    return the verdict it wrote (or '<none>' if it wrote nothing)."""
    (tmp_path / "tmp").mkdir(exist_ok=True)
    (tmp_path / "tmp" / "review-raw.json").write_text(raw_output, encoding="utf-8")
    github_output = tmp_path / "gh_output.txt"
    github_output.write_text("", encoding="utf-8")
    env = {
        **os.environ,
        "REVIEWER_FAMILY": reviewer_family,
        "RESOLVED_MODEL": resolved_model,
        "GITHUB_OUTPUT": str(github_output),
    }
    result = subprocess.run(
        [sys.executable, "-c", _extract_parser_source()],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
    )
    # The parser must never crash — it funnels every failure to a written verdict.
    assert result.returncode == 0, f"parser crashed: {result.stderr}"
    verdict_file = tmp_path / "tmp" / "verdict.txt"
    return verdict_file.read_text(encoding="utf-8").strip() if verdict_file.exists() else "<none>"


_MODEL = "gpt-5.3-codex-low"


def _envelope(result_value: object, *, is_error: bool = False) -> str:
    """Build the confirmed Cursor `--output-format json` envelope shape."""
    return json.dumps(
        {
            "type": "result",
            "subtype": "success",
            "is_error": is_error,
            "result": result_value,
            "session_id": "sess-abc",
            "usage": {"tokens": 42},
        }
    )


# ---------------------------------------------------------------------------
# Primary path — the confirmed live envelope
# ---------------------------------------------------------------------------


def test_confirmed_envelope_result_string_approve(tmp_path: Path) -> None:
    raw = _envelope('{"verdict": "approve", "findings": ["minimal, correct"]}')
    assert (
        _run_parser(raw, reviewer_family="gpt", resolved_model=_MODEL, tmp_path=tmp_path)
        == "approve"
    )


def test_confirmed_envelope_result_string_request_changes(tmp_path: Path) -> None:
    raw = _envelope('{"verdict": "request-changes", "findings": ["scope creep"]}')
    assert (
        _run_parser(raw, reviewer_family="gpt", resolved_model=_MODEL, tmp_path=tmp_path)
        == "request-changes"
    )


def test_confirmed_envelope_result_string_with_markdown_fences(tmp_path: Path) -> None:
    raw = _envelope('```json\n{"verdict": "approve", "findings": []}\n```')
    assert (
        _run_parser(raw, reviewer_family="gpt", resolved_model=_MODEL, tmp_path=tmp_path)
        == "approve"
    )


# ---------------------------------------------------------------------------
# Fail-open — every failure mode converges on `unavailable`, never raises
# ---------------------------------------------------------------------------


def test_is_error_true_fails_open(tmp_path: Path) -> None:
    raw = _envelope("upstream model error", is_error=True)
    assert (
        _run_parser(raw, reviewer_family="gpt", resolved_model=_MODEL, tmp_path=tmp_path)
        == "unavailable"
    )


def test_no_resolved_model_fails_open(tmp_path: Path) -> None:
    raw = _envelope('{"verdict": "approve", "findings": []}')
    assert (
        _run_parser(raw, reviewer_family="gpt", resolved_model="", tmp_path=tmp_path)
        == "unavailable"
    )


def test_empty_output_fails_open(tmp_path: Path) -> None:
    assert (
        _run_parser("", reviewer_family="gpt", resolved_model=_MODEL, tmp_path=tmp_path)
        == "unavailable"
    )


def test_non_json_garbage_fails_open(tmp_path: Path) -> None:
    assert (
        _run_parser(
            "not json at all", reviewer_family="gpt", resolved_model=_MODEL, tmp_path=tmp_path
        )
        == "unavailable"
    )


def test_unrecognized_verdict_value_fails_open(tmp_path: Path) -> None:
    raw = _envelope('{"verdict": "maybe", "findings": []}')
    assert (
        _run_parser(raw, reviewer_family="gpt", resolved_model=_MODEL, tmp_path=tmp_path)
        == "unavailable"
    )


# ---------------------------------------------------------------------------
# Fallback tolerance — churned/other shapes still resolve
# ---------------------------------------------------------------------------


def test_fallback_bare_verdict_object(tmp_path: Path) -> None:
    """A raw, un-enveloped verdict object (a plausible future/alternate shape)
    still resolves via the fallback path."""
    raw = '{"verdict": "approve", "findings": []}'
    assert (
        _run_parser(raw, reviewer_family="gpt", resolved_model=_MODEL, tmp_path=tmp_path)
        == "approve"
    )


def test_fallback_nested_answer_key(tmp_path: Path) -> None:
    """An envelope carrying the answer under a non-`result` key still resolves."""
    raw = json.dumps(
        {"type": "message", "content": '{"verdict": "request-changes", "findings": ["x"]}'}
    )
    assert (
        _run_parser(raw, reviewer_family="gpt", resolved_model=_MODEL, tmp_path=tmp_path)
        == "request-changes"
    )
