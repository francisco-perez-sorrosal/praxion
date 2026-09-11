"""Tests for promote_learnings.py -- gate_fire coverage and CLEANUP_PATTERNS precision.

`promote_learnings.py` had no prior dedicated test file (only
`test_cleanup_gate.py`, which exercises the `cleanup_gate.sh` shell wrapper's
own delegation/fast-path contract via a spy hook, not this hook's own
pass/warn decision or its `record_gate_fire` call site).

Contract under test (hooks/promote_learnings.py): the hook fires on Bash
commands matching CLEANUP_PATTERNS, warns (stdout hookSpecificOutput) when
`.ai-work/**/LEARNINGS.md` under `payload["cwd"]` has unpromoted entries, and
always exits 0 (fail-open). It also makes one `record_gate_fire` call per
invocation, wrapped in its own `except Exception: pass` (belt-and-suspenders
on top of `_hook_utils.record_gate_fire`'s own fail-open contract).
"""

from __future__ import annotations

import io
import json
import sys
from pathlib import Path

import pytest

HOOKS_DIR = Path(__file__).resolve().parent
HOOK_PATH = HOOKS_DIR / "promote_learnings.py"


def _cleanup_payload(cwd: str) -> dict:
    return {
        "tool_name": "Bash",
        "tool_input": {"command": "rm -rf .ai-work/some-slug"},
        "cwd": cwd,
    }


def _write_learnings(cwd: Path) -> None:
    learnings_dir = cwd / ".ai-work" / "test-slug"
    learnings_dir.mkdir(parents=True)
    (learnings_dir / "LEARNINGS.md").write_text(
        "# LEARNINGS\n- **[implementer] sample**: test entry\n", encoding="utf-8"
    )


def _read_gate_fire_rows(cwd: Path) -> list[dict]:
    obs_path = cwd / ".ai-state" / "observations.jsonl"
    if not obs_path.exists():
        return []
    return [json.loads(line) for line in obs_path.read_text(encoding="utf-8").splitlines()]


def _load_module():
    """Load promote_learnings.py fresh, for in-process test control."""
    import importlib.util

    if str(HOOKS_DIR) not in sys.path:
        sys.path.insert(0, str(HOOKS_DIR))
    spec = importlib.util.spec_from_file_location("promote_learnings", HOOK_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _raise(*_args, **_kwargs):
    raise RuntimeError("boom")


def test_gate_fire_row_on_pass(tmp_path: Path, monkeypatch) -> None:
    """No unpromoted LEARNINGS.md under cwd's .ai-work -> outcome=pass.

    `.ai-state/` lives under tmp_path (via chdir) -- never the live WAL.
    """
    module = _load_module()
    (tmp_path / ".ai-state").mkdir()
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(_cleanup_payload(str(tmp_path)))))

    module.main()

    rows = _read_gate_fire_rows(tmp_path)
    assert len(rows) == 1
    assert rows[0]["event_type"] == "gate_fire"
    assert rows[0]["tool_name"] == "promote_learnings"
    assert rows[0]["outcome"] == "pass"


def test_gate_fire_row_on_warn(tmp_path: Path, monkeypatch) -> None:
    """Unpromoted LEARNINGS.md entries under cwd's .ai-work -> outcome=warn."""
    module = _load_module()
    (tmp_path / ".ai-state").mkdir()
    _write_learnings(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(_cleanup_payload(str(tmp_path)))))

    module.main()

    rows = _read_gate_fire_rows(tmp_path)
    assert len(rows) == 1
    assert rows[0]["outcome"] == "warn"


def test_helper_exception_does_not_change_exit_code_on_pass(tmp_path: Path, monkeypatch) -> None:
    module = _load_module()
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(module, "record_gate_fire", _raise)
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(_cleanup_payload(str(tmp_path)))))

    module.main()  # must not raise


def test_helper_exception_does_not_change_exit_code_on_warn(tmp_path: Path, monkeypatch) -> None:
    module = _load_module()
    _write_learnings(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(module, "record_gate_fire", _raise)
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(_cleanup_payload(str(tmp_path)))))

    module.main()  # must not raise; the hook stays fail-open (exits 0)


def test_non_cleanup_command_never_fires_gate(tmp_path: Path, monkeypatch) -> None:
    """A non-cleanup Bash command must not emit a gate_fire row at all."""
    module = _load_module()
    (tmp_path / ".ai-state").mkdir()
    monkeypatch.chdir(tmp_path)
    payload = {"tool_name": "Bash", "tool_input": {"command": "ls -la"}, "cwd": str(tmp_path)}
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(payload)))

    module.main()

    assert _read_gate_fire_rows(tmp_path) == []


# ---------------------------------------------------------------------------
# CLEANUP_PATTERNS precision -- three fixes, three defect classes
#
# 1. original (unanchored): "rm" matched mid-word (inside "confirm"); the
#    wildcarded "." in `clean.work` matched any character.
# 2. first fix (anchored, quote/path-blind): closed (1), but `rm -rf
#    /abs/path/.ai-work/slug` and quoted operands went unmatched.
# 3. second fix (`_outside_quotes`, quote-balance heuristic): closed (2),
#    but counted quote characters across the WHOLE command prefix -- so ANY
#    unpaired quote earlier in the command (an apostrophe in "it's", an
#    unrelated -m "message") silently suppressed the gate on a real,
#    unquoted `rm -rf .ai-work/...` later in the same command. Verified:
#    `echo "it's done"; rm -rf .ai-work/slug` fired True before this
#    revision's parent commit, False at it.
#
# `_outside_quotes` is deleted rather than patched a third time: quote-aware
# matching is shell parsing, which a regex over raw command text cannot do
# precisely without a real parser (the same failure class dec-379 retired
# elsewhere in this codebase). The hook is advisory (exits 0
# unconditionally, warns about unpromoted LEARNINGS.md entries) -- a miss
# costs a reminder, not data, so scope is kept narrow and DOCUMENTED rather
# than chased. This table is that documentation: every accepted
# false-negative (and the one accepted false-positive the simplification
# introduces) gets a row with a reason, per dec-378 non-vacuity.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("command", "should_fire"),
    [
        # --- True positives: genuine .ai-work deletions ---
        ("rm -rf .ai-work/x", True),
        ("rm -rf .ai-work/some-slug", True),
        ("rm -rf /abs/path/.ai-work/slug", True),
        ('rm -rf ".ai-work/slug"', True),
        # --- Accepted true negatives: "rm"/".ai-work" as substrings only,
        # not shell words -- word-boundary anchoring alone (no quote logic
        # involved) keeps these False. ---
        ("grep -rn 'confirm ' .ai-work/", False),
        ("echo 'please confirm .ai-work exists'", False),
        ("cat docs/clean-workflow.md", False),
        ("python3 scripts/clean_workspace.py --check", False),
        # --- Defect-3 regressions, now closed: quote-awareness is gone, so
        # an unrelated unpaired quote earlier in the command no longer
        # suppresses a real, unquoted deletion later in the command. ---
        ('echo "it\'s done"; rm -rf .ai-work/slug', True),  # apostrophe-in-message variant
        ('vcs commit -m "don\'t fire" && rm -rf .ai-work/x', True),  # unbalanced-quote variant
        # --- Accepted false negatives: deliberately out of scope. Widening
        # CLEANUP_PATTERNS to cover these needs shell-aware parsing this
        # regex design does not attempt (see module docstring). ---
        ("rmdir .ai-work/slug", False),  # rmdir not matched; mirrors cleanup_gate.sh's v1 scope
        ("trash .ai-work/slug", False),  # trash not matched; same reason
        ("find .ai-work -delete", False),  # find clause dropped with quote logic (row rw-9a9c268a)
        ("find .ai-work/some-slug -type f -delete", False),  # same
        # --- Accepted false positive: the trade-off's cost side. Without
        # quote-awareness, an rm-shaped mention fully inside another
        # command's quoted argument now over-fires (extra reminder, no
        # deletion actually happens) instead of being correctly ignored. ---
        ("echo 'reminder: run rm -rf .ai-work/x later'", True),
    ],
    ids=[
        "tp-rm-rf-x",
        "tp-rm-rf-slug",
        "tp-rm-rf-absolute-path-prefix",
        "tp-rm-rf-quoted-operand",
        "fp-confirm-in-grep",
        "fp-confirm-in-echo",
        "fp-clean-workflow-doc",
        "fp-clean-workspace-script",
        "regression-closed-apostrophe-in-message",
        "regression-closed-unbalanced-quote-flag",
        "fn-accepted-rmdir",
        "fn-accepted-trash",
        "fn-accepted-find-delete",
        "fn-accepted-find-delete-with-flags",
        "fp-accepted-rm-mentioned-in-echo",
    ],
)
def test_is_cleanup_command_precision(command: str, should_fire: bool) -> None:
    """`_is_cleanup_command` fires on genuine .ai-work deletions.

    This IS the documentation of the hook's real precision (see the table's
    header comment) -- a future change to CLEANUP_PATTERNS that alters what
    is caught must break a row here, not silently narrow or widen scope.
    """
    module = _load_module()

    assert module._is_cleanup_command(command) is should_fire
