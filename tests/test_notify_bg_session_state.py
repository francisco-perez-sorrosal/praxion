"""Behavioral tests for hooks/notify_bg_session_state.py.

Tests verify the marker-file correlation flow, slug recovery from marker
content, marker deletion after firing, the PRAXION_DISABLE_OBSERVABILITY
opt-out, and exit-0 discipline.

Testing strategy
----------------
Option B: import the hook module and monkeypatch ``subprocess.run`` so osascript
is never invoked.  The hook's ``REWORK_MARKERS_DIR`` is monkeypatched to a
per-test ``tmp_path`` directory so real markers under ``~/.claude/`` are never
touched.  The hook exposes ``main()`` which is called directly per test.
``sys.stdin`` is patched with a ``StringIO`` carrying the fixture JSON.  Each
test asserts on the captured subprocess.run call list (or its absence) and on
post-call marker filesystem state.

No real macOS notifications are fired under any test condition; no real
``~/.claude/rework_sessions/`` files are read or written.
"""

from __future__ import annotations

import io
import json

# ---------------------------------------------------------------------------
# Module import
# ---------------------------------------------------------------------------
# The hook lives in hooks/ and imports _hook_utils from the same directory.
# Add hooks/ to sys.path so both resolve at import time.
import os
import subprocess
import sys
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

_HOOKS_DIR = os.path.join(os.path.dirname(__file__), "..", "hooks")
if _HOOKS_DIR not in sys.path:
    sys.path.insert(0, _HOOKS_DIR)

import notify_bg_session_state as _hook  # noqa: E402  (import after sys.path patch)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _run_hook(
    payload: dict[str, Any],
    markers_dir: Path,
    *,
    env_overrides: dict[str, str] | None = None,
) -> MagicMock:
    """Call hook.main() with the given payload, returning the mock for subprocess.run.

    Args:
        payload: The hook JSON event dict to feed via stdin.
        markers_dir: Path to use as REWORK_MARKERS_DIR for this test.
        env_overrides: Optional env vars to overlay (e.g. PRAXION_DISABLE_OBSERVABILITY=1).

    Returns:
        The MagicMock that replaced subprocess.run — callers assert .call_args_list.
    """
    stdin_data = json.dumps(payload)
    mock_run = MagicMock(return_value=MagicMock(returncode=0))

    with (
        patch.object(sys, "stdin", io.StringIO(stdin_data)),
        patch.object(subprocess, "run", mock_run),
        patch.object(_hook, "REWORK_MARKERS_DIR", markers_dir),
        patch.dict(os.environ, env_overrides or {}, clear=False),
    ):
        _hook.main()

    return mock_run


def _run_hook_raw_stdin(
    raw: str,
    markers_dir: Path,
    *,
    env_overrides: dict[str, str] | None = None,
) -> MagicMock:
    """Call hook.main() with raw stdin text (for malformed-JSON tests)."""
    mock_run = MagicMock(return_value=MagicMock(returncode=0))
    with (
        patch.object(sys, "stdin", io.StringIO(raw)),
        patch.object(subprocess, "run", mock_run),
        patch.object(_hook, "REWORK_MARKERS_DIR", markers_dir),
        patch.dict(os.environ, env_overrides or {}, clear=False),
    ):
        _hook.main()
    return mock_run


def _write_marker(markers_dir: Path, short_id: str, slug: str) -> Path:
    """Create a marker file simulating dispatch-reworks' marker write."""
    markers_dir.mkdir(parents=True, exist_ok=True)
    marker = markers_dir / short_id
    marker.write_text(slug, encoding="utf-8")
    return marker


# ---------------------------------------------------------------------------
# Happy path: marker present → fire + delete
# ---------------------------------------------------------------------------


def test_marker_present_with_full_uuid_fires_notification(tmp_path):
    """When the Stop payload's session_id maps to an existing marker, fire osascript."""
    short_id = "1ab69684"
    slug = "auth-fix"
    _write_marker(tmp_path, short_id, slug)

    payload = {"session_id": "1ab69684-606b-444e-a71f-8cebfeb89290"}
    mock_run = _run_hook(payload, tmp_path)

    assert mock_run.called, "osascript must be invoked when a marker exists"
    args = mock_run.call_args[0][0]
    assert args[0] == "osascript", f"First arg must be 'osascript', got {args[0]!r}"
    assert f"[rework: {slug}] completed" in args[-1], (
        f"Notification message must reference the slug from the marker. Got: {args[-1]!r}"
    )
    assert "Praxion rework" in args[-1], f"Title must contain 'Praxion rework', got: {args[-1]!r}"


def test_marker_present_with_bare_short_id_fires_notification(tmp_path):
    """A bare 8-hex session_id (no dashes) also matches the marker."""
    short_id = "cafebabe"
    slug = "api-cleanup"
    _write_marker(tmp_path, short_id, slug)

    payload = {"session_id": "cafebabe"}
    mock_run = _run_hook(payload, tmp_path)

    assert mock_run.called, "Bare short ID must match marker lookup"
    assert f"[rework: {slug}] completed" in mock_run.call_args[0][0][-1]


def test_marker_deleted_after_firing(tmp_path):
    """A successful fire must delete the marker to make it one-shot."""
    short_id = "deadbeef"
    slug = "session-cleanup"
    marker = _write_marker(tmp_path, short_id, slug)
    assert marker.exists(), "precondition: marker file exists"

    payload = {"session_id": "deadbeef-1234-5678-9abc-def012345678"}
    _run_hook(payload, tmp_path)

    assert not marker.exists(), "Marker file must be deleted after a successful notification fire"


def test_marker_message_format_is_exact(tmp_path):
    """Notification message is exactly '[rework: <slug>] completed'."""
    short_id = "fedcba98"
    slug = "auth-refactor"
    _write_marker(tmp_path, short_id, slug)

    payload = {"session_id": "fedcba98-0000-0000-0000-000000000000"}
    mock_run = _run_hook(payload, tmp_path)

    assert mock_run.called
    argv = mock_run.call_args[0][0]
    # argv is ["osascript", "-e", "<AppleScript>"]
    assert argv[0] == "osascript"
    assert argv[1] == "-e"
    applescript = argv[2]
    assert 'display notification "[rework: auth-refactor] completed"' in applescript, (
        f"Notification message format wrong. Got AppleScript: {applescript!r}"
    )
    assert 'with title "Praxion rework"' in applescript, (
        f"Title format wrong. Got AppleScript: {applescript!r}"
    )


def test_marker_slug_with_hyphens_preserved(tmp_path):
    """A multi-word hyphenated slug from the marker is preserved verbatim."""
    short_id = "12345678"
    slug = "multi-word-feature-slug"
    _write_marker(tmp_path, short_id, slug)

    payload = {"session_id": "12345678-aaaa-bbbb-cccc-dddddddddddd"}
    mock_run = _run_hook(payload, tmp_path)

    assert mock_run.called
    assert f"[rework: {slug}] completed" in mock_run.call_args[0][0][-1]


def test_marker_content_strips_trailing_whitespace(tmp_path):
    """Marker content with trailing whitespace produces a clean slug."""
    short_id = "abcdef01"
    markers_dir = tmp_path
    markers_dir.mkdir(parents=True, exist_ok=True)
    (markers_dir / short_id).write_text("padded-slug   \n", encoding="utf-8")

    payload = {"session_id": "abcdef01-2222-3333-4444-555555555555"}
    mock_run = _run_hook(payload, markers_dir)

    assert mock_run.called
    assert "[rework: padded-slug] completed" in mock_run.call_args[0][0][-1]


# ---------------------------------------------------------------------------
# Silent: marker absent → no fire
# ---------------------------------------------------------------------------


def test_marker_absent_does_not_fire(tmp_path):
    """When no marker exists for the session_id, the hook must exit silently."""
    payload = {"session_id": "99999999-0000-0000-0000-000000000000"}
    mock_run = _run_hook(payload, tmp_path)
    assert not mock_run.called, (
        "osascript must NOT be invoked when no marker exists for this session"
    )


def test_missing_session_id_does_not_fire(tmp_path):
    """A payload with no session_id field must exit silently."""
    payload = {"hook_event_name": "Stop"}
    mock_run = _run_hook(payload, tmp_path)
    assert not mock_run.called, "osascript must NOT be invoked when session_id is absent"


def test_empty_session_id_does_not_fire(tmp_path):
    """An empty string session_id must exit silently."""
    payload = {"session_id": ""}
    mock_run = _run_hook(payload, tmp_path)
    assert not mock_run.called, "osascript must NOT be invoked when session_id is empty"


def test_markers_dir_missing_does_not_fire(tmp_path):
    """When REWORK_MARKERS_DIR does not exist, hook exits silently."""
    nonexistent = tmp_path / "does-not-exist"
    payload = {"session_id": "abcdef01-2222-3333-4444-555555555555"}
    mock_run = _run_hook(payload, nonexistent)
    assert not mock_run.called, "osascript must NOT be invoked when markers dir is absent"


def test_marker_for_different_session_does_not_fire(tmp_path):
    """A marker for a different short ID must not cause the hook to fire."""
    _write_marker(tmp_path, "11111111", "other-slug")

    payload = {"session_id": "22222222-aaaa-bbbb-cccc-dddddddddddd"}
    mock_run = _run_hook(payload, tmp_path)

    assert not mock_run.called, "Marker for a different session_id must not trigger this hook fire"
    # The unrelated marker must remain untouched.
    assert (tmp_path / "11111111").exists(), (
        "Hook must not delete markers belonging to other sessions"
    )


# ---------------------------------------------------------------------------
# Opt-out: PRAXION_DISABLE_OBSERVABILITY
# ---------------------------------------------------------------------------


def test_disable_observability_suppresses_notification(tmp_path):
    """PRAXION_DISABLE_OBSERVABILITY=1 must prevent osascript invocation."""
    short_id = "1ab69684"
    _write_marker(tmp_path, short_id, "auth-fix")

    payload = {"session_id": "1ab69684-606b-444e-a71f-8cebfeb89290"}
    mock_run = _run_hook(payload, tmp_path, env_overrides={"PRAXION_DISABLE_OBSERVABILITY": "1"})
    assert not mock_run.called, "osascript must NOT be invoked when PRAXION_DISABLE_OBSERVABILITY=1"


@pytest.fixture(params=["true", "yes", "TRUE", "YES"])
def truthy_value(request):
    return request.param


def test_disable_observability_truthy_variants_suppress_notification(
    tmp_path,
    truthy_value: str,
):
    """PRAXION_DISABLE_OBSERVABILITY set to 'true' or 'yes' also suppresses."""
    short_id = "1ab69684"
    _write_marker(tmp_path, short_id, "auth-fix")

    payload = {"session_id": "1ab69684-606b-444e-a71f-8cebfeb89290"}
    mock_run = _run_hook(
        payload,
        tmp_path,
        env_overrides={"PRAXION_DISABLE_OBSERVABILITY": truthy_value},
    )
    assert not mock_run.called, (
        f"osascript must NOT be invoked when PRAXION_DISABLE_OBSERVABILITY={truthy_value!r}"
    )


def test_disable_observability_preserves_marker(tmp_path):
    """When observability is disabled, the marker must not be deleted."""
    short_id = "1ab69684"
    marker = _write_marker(tmp_path, short_id, "auth-fix")

    payload = {"session_id": "1ab69684-606b-444e-a71f-8cebfeb89290"}
    _run_hook(payload, tmp_path, env_overrides={"PRAXION_DISABLE_OBSERVABILITY": "1"})

    assert marker.exists(), (
        "Marker must survive when the hook exits early via DISABLE_OBSERVABILITY"
    )


# ---------------------------------------------------------------------------
# Exit-0 discipline
# ---------------------------------------------------------------------------


def test_malformed_json_on_stdin_is_silent(tmp_path):
    """Malformed JSON on stdin must not raise — hook exits silently (exit 0).

    Informational hooks must never block lifecycle; all errors are swallowed.
    """
    mock_run = _run_hook_raw_stdin("{not: valid json}", tmp_path)
    assert not mock_run.called, (
        "Malformed JSON must produce silent exit — no osascript, no exception"
    )


def test_osascript_failure_absorbed_by_main_guard(tmp_path):
    """When osascript fails, the hook's __main__ guard absorbs it (exit 0 in production).

    Informational hooks must never block lifecycle.  When invoked as a
    subprocess (production path), ``if __name__ == "__main__": try: main()
    except Exception: pass`` ensures exit 0 even if subprocess.run raises.
    """
    import subprocess as _subp  # noqa: PLC0415

    # Pre-populate a marker so the hook reaches the osascript branch.
    short_id = "1ab69684"
    markers_dir = tmp_path / "rework_sessions"
    markers_dir.mkdir(parents=True, exist_ok=True)
    (markers_dir / short_id).write_text("auth-fix", encoding="utf-8")

    # Replace osascript on PATH with a stub that exits non-zero.
    stub_dir = None
    try:
        import tempfile

        stub_dir = tempfile.mkdtemp()
        stub_path = os.path.join(stub_dir, "osascript")
        with open(stub_path, "w", encoding="utf-8") as f:
            f.write("#!/bin/sh\nexit 1\n")
        os.chmod(stub_path, 0o755)

        env = os.environ.copy()
        env["PATH"] = f"{stub_dir}:{env.get('PATH', '')}"
        # Force the hook to use the test markers_dir by pointing HOME at tmp_path.
        env["HOME"] = str(tmp_path)

        payload = json.dumps({"session_id": "1ab69684-606b-444e-a71f-8cebfeb89290"})
        # Inject the test markers dir at the path the hook computes from HOME.
        expected_dir = tmp_path / ".claude" / "rework_sessions"
        expected_dir.mkdir(parents=True, exist_ok=True)
        (expected_dir / short_id).write_text("auth-fix", encoding="utf-8")

        result = _subp.run(
            [sys.executable, os.path.join(_HOOKS_DIR, "notify_bg_session_state.py")],
            input=payload,
            capture_output=True,
            text=True,
            env=env,
        )
        assert result.returncode == 0, (
            f"Hook must exit 0 even when osascript fails. "
            f"Got returncode={result.returncode}, stderr={result.stderr!r}"
        )
    finally:
        if stub_dir is not None:
            import shutil

            shutil.rmtree(stub_dir, ignore_errors=True)


# ---------------------------------------------------------------------------
# Short-ID derivation edge cases
# ---------------------------------------------------------------------------


def test_session_id_longer_than_short_id_uses_prefix(tmp_path):
    """A session_id with a >8-char prefix before the first dash uses 8-char prefix."""
    # If Claude Code ever ships session IDs without dashes that are longer
    # than 8 chars, the hook must still look up the 8-char prefix.
    short_id = "abcdef12"
    _write_marker(tmp_path, short_id, "long-prefix-test")

    payload = {"session_id": "abcdef1234567890"}  # no dash, 16 chars
    mock_run = _run_hook(payload, tmp_path)

    assert mock_run.called, "8-char prefix must be derived from a longer dash-free session_id"
    assert "[rework: long-prefix-test] completed" in mock_run.call_args[0][0][-1]
