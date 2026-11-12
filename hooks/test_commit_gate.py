"""Canary tests for hooks/commit_gate.sh — PreToolUse shell fast-path for git commits.

Cites: rules/swe/gate-liveness.md — every CODE gate ships a sibling canary proving
it fails on a known-bad input. The gate's job is to intercept `git commit` commands
and forward them to a Python hook; non-commit commands must be silently ignored.
These tests prove the gate:
  - blocks the fast-path for git commit commands (they reach Python)
  - allows the fast-path for non-commit commands (silent exit 0)
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

HOOKS_DIR = Path(__file__).resolve().parent
GATE_SCRIPT = HOOKS_DIR / "commit_gate.sh"

DELEGATION_MARKER = "COMMIT_GATE_DELEGATED"


def _write_delegation_spy(tmp_path: Path) -> Path:
    """Write a Python stub that prints a marker when invoked by the gate."""
    spy = tmp_path / "spy_hook.py"
    spy.write_text(
        f"import sys\nsys.stdin.read()\nprint({DELEGATION_MARKER!r})\n",
        encoding="utf-8",
    )
    return spy


def _write_exiting_spy(tmp_path: Path, code: int) -> Path:
    """Write a Python stub that exits with `code` after draining stdin."""
    spy = tmp_path / f"exit_{code}_hook.py"
    spy.write_text(f"import sys\nsys.stdin.read()\nsys.exit({code})\n", encoding="utf-8")
    return spy


def _run_gate(
    payload: dict,
    *,
    hook: Path | None = None,
    env: dict[str, str] | None = None,
    blocking: bool = False,
    shell: str | None = None,
    stderr: int | None = subprocess.PIPE,
    close_stderr: bool = False,
) -> subprocess.CompletedProcess[str]:
    """Invoke commit_gate.sh with a JSON payload on stdin.

    `shell` runs the script under that interpreter instead of its shebang; `stderr`
    is what the gate's fd 2 is connected to, and `close_stderr` leaves fd 2 closed
    (both let a test prove a failed stderr write cannot change the verdict).
    """
    real_hook = str(hook) if hook else str(HOOKS_DIR / "check_id_citation_discipline.py")
    merged_env = dict(os.environ)
    merged_env.update(env or {})
    argv = [shell] if shell else []
    argv += [str(GATE_SCRIPT)] + (["--blocking"] if blocking else []) + [real_hook]
    if close_stderr:
        argv = ["sh", "-c", 'exec "$@" 2>&-', "sh", *argv]
    return subprocess.run(
        argv,
        input=json.dumps(payload),
        stdout=subprocess.PIPE,
        stderr=stderr,
        text=True,
        env=merged_env,
        check=False,
    )


SHELLS = [
    pytest.param(name, marks=pytest.mark.skipif(shutil.which(name) is None, reason=f"no {name}"))
    for name in ("sh", "dash", "bash")
]


@pytest.fixture(params=SHELLS)
def shell(request: pytest.FixtureRequest) -> str:
    """Each POSIX shell the gate must behave identically under."""
    return request.param


def _make_bash_payload(command: str) -> dict:
    return {"tool_name": "Bash", "tool_input": {"command": command}}


# ---------------------------------------------------------------------------
# Script integrity
# ---------------------------------------------------------------------------


def test_gate_script_is_executable() -> None:
    """The shell gate must be executable or the hook silently no-ops."""
    assert GATE_SCRIPT.exists(), f"missing {GATE_SCRIPT}"
    assert os.access(GATE_SCRIPT, os.X_OK), f"{GATE_SCRIPT} is not executable (chmod +x required)"


# ---------------------------------------------------------------------------
# Canary: git commit commands reach Python (fast-path does NOT fire)
# ---------------------------------------------------------------------------


def test_blocks_fast_path_for_git_commit_command(tmp_path: Path) -> None:
    """Canary: a `git commit` command is forwarded to Python, not silently dropped.

    The gate exists to run the Python hook on every commit attempt. If the
    fast-path fires for a `git commit` command, violations would be silently
    missed. This test proves the gate bites by asserting the spy hook is reached.
    """
    spy_hook = _write_delegation_spy(tmp_path)
    result = _run_gate(_make_bash_payload("git commit -m 'add feature'"), hook=spy_hook)
    assert result.returncode == 0
    assert DELEGATION_MARKER in result.stdout, (
        "commit_gate.sh must delegate a `git commit` command to Python "
        f"(fast-path must NOT silence it); stdout={result.stdout!r}, "
        f"stderr={result.stderr!r}"
    )


def test_blocks_fast_path_for_git_commit_no_edit(tmp_path: Path) -> None:
    """Canary: `git commit --no-edit` is also forwarded to Python."""
    spy_hook = _write_delegation_spy(tmp_path)
    result = _run_gate(_make_bash_payload("git commit --no-edit"), hook=spy_hook)
    assert result.returncode == 0
    assert DELEGATION_MARKER in result.stdout, (
        "commit_gate.sh must delegate `git commit --no-edit` to Python"
    )


# ---------------------------------------------------------------------------
# Happy paths: non-commit commands are silently ignored
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "command",
    [
        "git status",
        "git push origin main",
        "ls -la",
        "python script.py",
    ],
    ids=["git-status", "git-push", "ls", "python"],
)
def test_non_commit_command_exits_fast(command: str, tmp_path: Path) -> None:
    """Non-commit commands exit 0 with empty stdout — Python never runs."""
    spy_hook = _write_delegation_spy(tmp_path)
    result = _run_gate(_make_bash_payload(command), hook=spy_hook)
    assert result.returncode == 0, f"expected exit 0, got {result.returncode}"
    assert DELEGATION_MARKER not in result.stdout, (
        f"non-commit command {command!r} must not reach Python; stdout={result.stdout!r}"
    )


# ---------------------------------------------------------------------------
# PreToolUse exit-code translation (--blocking)
# ---------------------------------------------------------------------------


def test_blocking_translates_findings_exit_into_pretooluse_block(tmp_path: Path) -> None:
    """A gate reporting findings (1) must reach Claude Code as a block (2).

    PreToolUse treats *only* exit 2 as "block this tool call"; every other
    non-zero is a non-blocking error the model never sees. Praxion's check_*
    scripts use the POSIX-natural 1-on-findings, so without this translation a
    gate detects a violation perfectly and has its verdict discarded --
    check_id_citation_discipline.py did exactly that while the rule it enforces
    called it "the primary enforcement layer".
    """
    result = _run_gate(
        _make_bash_payload("git commit -m 'x'"),
        hook=_write_exiting_spy(tmp_path, 1),
        blocking=True,
    )
    assert result.returncode == 2


def test_without_blocking_a_findings_exit_passes_through(tmp_path: Path) -> None:
    """Reminders must not block, so the translation is opt-in per invocation.

    remind_adr.py and remind_calibration.py are wrapped by the same gate and
    exit 0 normally -- but a Python traceback also exits 1, the same code a gate
    uses for findings. A blanket translation would turn any crashing reminder
    into a commit blocker.
    """
    result = _run_gate(
        _make_bash_payload("git commit -m 'x'"),
        hook=_write_exiting_spy(tmp_path, 1),
    )
    assert result.returncode == 1


def test_blocking_leaves_clean_and_error_codes_unchanged(tmp_path: Path) -> None:
    """Only the findings code is translated; 0 and 2 pass through untouched."""
    clean = _run_gate(
        _make_bash_payload("git commit -m 'x'"),
        hook=_write_exiting_spy(tmp_path, 0),
        blocking=True,
    )
    script_error = _run_gate(
        _make_bash_payload("git commit -m 'x'"),
        hook=_write_exiting_spy(tmp_path, 2),
        blocking=True,
    )
    assert clean.returncode == 0
    assert script_error.returncode == 2


def test_id_citation_gate_is_wired_as_blocking() -> None:
    """The mechanism is useless unwired -- pin the declaration, not just the code.

    This is the half a unit test cannot reach: commit_gate.sh can translate
    correctly forever while hooks.json invokes it without the flag.
    """
    raw = json.loads((HOOKS_DIR / "hooks.json").read_text(encoding="utf-8"))
    # Events nest under a top-level "hooks" key; reading the top level directly
    # yields an empty list and a vacuously passing test.
    hooks_json = raw["hooks"]
    commands = [
        h["command"]
        for group in hooks_json.get("PreToolUse", [])
        for h in group.get("hooks", [])
        if "command" in h
    ]
    id_citation = [c for c in commands if "check_id_citation_discipline.py" in c]
    assert id_citation, "the id-citation gate is not wired into PreToolUse at all"
    for command in id_citation:
        assert "--blocking" in command, f"gate invoked without --blocking: {command}"


# td-188: the wrapper must hand the Python hook byte-identical JSON. Under
# /bin/sh (bash in POSIX mode) `echo "$input"` interprets backslash escapes,
# so a command carrying a grep pattern like `\\|` reached json.loads as an
# invalid escape and every gate silently returned before recording anything.
_ROUNDTRIP_HOOK = """
import json, sys
from pathlib import Path
payload = json.loads(sys.stdin.read())
Path(sys.argv[1] if len(sys.argv) > 1 else "roundtrip.json").write_text(json.dumps(payload))
"""


def test_forwards_backslash_bearing_payload_intact(tmp_path: Path) -> None:
    """A command containing `\\|` and `\\n` must parse on the Python side unchanged."""
    hook = tmp_path / "roundtrip_hook.py"
    out = tmp_path / "roundtrip.json"
    hook.write_text(_ROUNDTRIP_HOOK.replace('"roundtrip.json"', repr(str(out))))
    command = 'git commit -q -m "x" 2>&1 | grep -v -i \'skipped\\|passed\\s*$\' && printf "a\\nb"'
    payload = {"tool_name": "Bash", "tool_input": {"command": command}, "cwd": str(tmp_path)}

    result = _run_gate(payload, hook=hook)

    assert result.returncode == 0, result.stderr
    assert out.exists(), "the Python hook never received parseable JSON"
    assert json.loads(out.read_text())["tool_input"]["command"] == command


# ---------------------------------------------------------------------------
# A refusal shows the session its findings and the way out
#
# On exit 2 the harness shows the model only stderr, and a checker prints its
# findings on stdout (so a hand, pre-commit or CI run is unchanged). The gate
# re-routes them and adds the hint; exit statuses stay as they were.
# ---------------------------------------------------------------------------

FINDING = "src/widget.py:2: a finding the session must read"
HINT_PHRASES = (
    "no command of that call ran",
    "before the call began",
    "stage in one call and commit in a separate call",
)
# Mirrors the gate's cap on the findings a refusal replays; pins the bound.
FINDINGS_LINE_CAP = 40


def _write_reporting_spy(tmp_path: Path, code: int, *, stream: str) -> Path:
    """A stub check that prints FINDING on `stream` and exits with `code`."""
    spy = tmp_path / f"report_{stream}_{code}.py"
    spy.write_text(
        f"import sys\nsys.stdin.read()\nprint({FINDING!r}, file=sys.{stream})\nsys.exit({code})\n",
        encoding="utf-8",
    )
    return spy


def _write_raw_stdout_spy(tmp_path: Path, code: int, text: str) -> Path:
    """A stub check that writes `text` to stdout exactly (no added newline)."""
    spy = tmp_path / "raw_stdout_hook.py"
    spy.write_text(
        f"import sys\nsys.stdin.read()\nsys.stdout.write({text!r})\nsys.exit({code})\n",
        encoding="utf-8",
    )
    return spy


def _write_many_findings_spy(tmp_path: Path, count: int) -> Path:
    """A stub check that prints `count` numbered finding lines on stdout and exits 1."""
    spy = tmp_path / "many_findings_hook.py"
    spy.write_text(
        "import sys\nsys.stdin.read()\n"
        f"for n in range(1, {count} + 1):\n    print(f'finding line {{n}}')\n"
        "sys.exit(1)\n",
        encoding="utf-8",
    )
    return spy


def _stderr_lines(result: subprocess.CompletedProcess[str]) -> list[str]:
    return result.stderr.splitlines()


def test_a_blocked_refusal_carries_stdout_findings_and_the_hint_on_stderr(tmp_path: Path) -> None:
    """Canary: the finding printed on stdout reaches the session through stderr."""
    result = _run_gate(
        _make_bash_payload("git commit -m 'x'"),
        hook=_write_reporting_spy(tmp_path, 1, stream="stdout"),
        blocking=True,
    )
    assert result.returncode == 2
    assert FINDING in result.stderr


@pytest.mark.parametrize("phrase", HINT_PHRASES)
def test_a_blocked_refusal_says_the_hint_phrase(tmp_path: Path, phrase: str) -> None:
    result = _run_gate(
        _make_bash_payload("git commit -m 'x'"),
        hook=_write_reporting_spy(tmp_path, 1, stream="stdout"),
        blocking=True,
    )
    assert phrase in result.stderr


def test_a_native_exit_two_keeps_its_stderr_and_gains_the_hint(tmp_path: Path) -> None:
    result = _run_gate(
        _make_bash_payload("git commit -m 'x'"),
        hook=_write_reporting_spy(tmp_path, 2, stream="stderr"),
        blocking=True,
    )
    assert result.returncode == 2
    assert FINDING in result.stderr


@pytest.mark.parametrize("phrase", HINT_PHRASES)
def test_a_native_exit_two_says_the_hint_phrase(tmp_path: Path, phrase: str) -> None:
    result = _run_gate(
        _make_bash_payload("git commit -m 'x'"),
        hook=_write_reporting_spy(tmp_path, 2, stream="stderr"),
        blocking=True,
    )
    assert phrase in result.stderr


def test_a_refusal_without_findings_still_carries_the_hint(tmp_path: Path) -> None:
    result = _run_gate(
        _make_bash_payload("git commit -m 'x'"),
        hook=_write_exiting_spy(tmp_path, 1),
        blocking=True,
    )
    assert result.returncode == 2
    assert HINT_PHRASES[0] in result.stderr


def test_a_pass_prints_its_stdout_unchanged_and_no_hint(tmp_path: Path) -> None:
    """Canary: only a refusal gains the hint; a pass writes no stderr of its own."""
    result = _run_gate(
        _make_bash_payload("git commit -m 'x'"),
        hook=_write_reporting_spy(tmp_path, 0, stream="stdout"),
        blocking=True,
    )
    assert result.returncode == 0
    assert result.stdout == FINDING + "\n"
    assert result.stderr == ""


# Output shapes a command substitution would normalise: trailing blank lines,
# blank-only output, a missing final newline, no output at all.
STDOUT_SHAPES = [
    pytest.param("a\n\n\n", id="trailing-blank-lines"),
    pytest.param("\n", id="blank-only"),
    pytest.param("\n\n", id="blank-lines-only"),
    pytest.param("abc", id="no-final-newline"),
    pytest.param("a\nb\n", id="ordinary"),
    pytest.param("", id="empty"),
]


@pytest.mark.parametrize("text", STDOUT_SHAPES)
def test_a_pass_replays_the_checkers_stdout_byte_for_byte(
    tmp_path: Path, shell: str, text: str
) -> None:
    result = _run_gate(
        _make_bash_payload("git commit -m 'x'"),
        hook=_write_raw_stdout_spy(tmp_path, 0, text),
        blocking=True,
        shell=shell,
    )
    assert result.returncode == 0
    assert result.stdout == text
    assert result.stderr == ""


@pytest.mark.parametrize("text", STDOUT_SHAPES)
def test_a_non_blocking_findings_exit_replays_stdout_byte_for_byte(
    tmp_path: Path, shell: str, text: str
) -> None:
    result = _run_gate(
        _make_bash_payload("git commit -m 'x'"),
        hook=_write_raw_stdout_spy(tmp_path, 1, text),
        shell=shell,
    )
    assert result.returncode == 1
    assert result.stdout == text
    assert result.stderr == ""


def test_a_non_blocking_findings_exit_keeps_its_stdout_and_gains_no_hint(tmp_path: Path) -> None:
    result = _run_gate(
        _make_bash_payload("git commit -m 'x'"),
        hook=_write_reporting_spy(tmp_path, 1, stream="stdout"),
    )
    assert result.returncode == 1
    assert result.stdout == FINDING + "\n"
    assert result.stderr == ""


def test_a_refusal_leads_with_the_way_out_before_its_findings(tmp_path: Path, shell: str) -> None:
    result = _run_gate(
        _make_bash_payload("git commit -m 'x'"),
        hook=_write_reporting_spy(tmp_path, 1, stream="stdout"),
        blocking=True,
        shell=shell,
    )
    assert result.returncode == 2
    assert result.stderr.index(HINT_PHRASES[0]) < result.stderr.index(FINDING)


def test_a_refusal_with_few_findings_replays_every_one(tmp_path: Path, shell: str) -> None:
    result = _run_gate(
        _make_bash_payload("git commit -m 'x'"),
        hook=_write_many_findings_spy(tmp_path, FINDINGS_LINE_CAP),
        blocking=True,
        shell=shell,
    )
    assert result.returncode == 2
    assert f"finding line {FINDINGS_LINE_CAP}" in result.stderr
    assert "not shown" not in result.stderr


def test_a_refusal_bounds_the_findings_it_replays(tmp_path: Path, shell: str) -> None:
    total = FINDINGS_LINE_CAP * 25
    result = _run_gate(
        _make_bash_payload("git commit -m 'x'"),
        hook=_write_many_findings_spy(tmp_path, total),
        blocking=True,
        shell=shell,
    )
    assert result.returncode == 2
    assert "finding line 1\n" in result.stderr
    assert f"finding line {FINDINGS_LINE_CAP}\n" in result.stderr
    assert f"finding line {FINDINGS_LINE_CAP + 1}\n" not in result.stderr
    assert len(_stderr_lines(result)) < FINDINGS_LINE_CAP + 10


def test_a_bounded_refusal_says_how_many_lines_were_left_out_and_how_to_see_them(
    tmp_path: Path, shell: str
) -> None:
    total = FINDINGS_LINE_CAP * 25
    hook = _write_many_findings_spy(tmp_path, total)
    result = _run_gate(
        _make_bash_payload("git commit -m 'x'"),
        hook=hook,
        blocking=True,
        shell=shell,
    )
    assert f"{total - FINDINGS_LINE_CAP} more line" in result.stderr
    assert "by hand, scoped to the staged files where it takes --files" in result.stderr
    assert f"python3 {hook}" in result.stderr


@pytest.mark.parametrize("phrase", HINT_PHRASES)
def test_a_bounded_refusal_still_says_the_hint_phrase(tmp_path: Path, phrase: str) -> None:
    result = _run_gate(
        _make_bash_payload("git commit -m 'x'"),
        hook=_write_many_findings_spy(tmp_path, FINDINGS_LINE_CAP * 25),
        blocking=True,
    )
    assert phrase in result.stderr


# A refusal's verdict must not depend on its stderr writes succeeding: under
# `set -e` a failed write would otherwise turn exit 2 (block) into exit 1 (a
# non-blocking error the model never sees).
UNWRITABLE_STDERR = [
    pytest.param({"close_stderr": True}, id="stderr-closed"),
    pytest.param("broken-pipe", id="stderr-broken-pipe"),
]


def _run_blocking_with_unwritable_stderr(
    hook: Path, shell: str, mode: object
) -> subprocess.CompletedProcess[str]:
    payload = _make_bash_payload("git commit -m 'x'")
    if mode == "broken-pipe":
        read_end, write_end = os.pipe()
        os.close(read_end)
        try:
            return _run_gate(payload, hook=hook, blocking=True, shell=shell, stderr=write_end)
        finally:
            os.close(write_end)
    return _run_gate(payload, hook=hook, blocking=True, shell=shell, **mode)


@pytest.mark.parametrize("mode", UNWRITABLE_STDERR)
def test_a_findings_exit_still_blocks_when_stderr_cannot_be_written(
    tmp_path: Path, shell: str, mode: object
) -> None:
    hook = _write_reporting_spy(tmp_path, 1, stream="stdout")
    assert _run_blocking_with_unwritable_stderr(hook, shell, mode).returncode == 2


@pytest.mark.parametrize("mode", UNWRITABLE_STDERR)
def test_a_native_exit_two_still_blocks_when_stderr_cannot_be_written(
    tmp_path: Path, shell: str, mode: object
) -> None:
    hook = _write_exiting_spy(tmp_path, 2)
    assert _run_blocking_with_unwritable_stderr(hook, shell, mode).returncode == 2


@pytest.mark.parametrize("mode", UNWRITABLE_STDERR)
def test_a_bounded_refusal_still_blocks_when_stderr_cannot_be_written(
    tmp_path: Path, shell: str, mode: object
) -> None:
    hook = _write_many_findings_spy(tmp_path, FINDINGS_LINE_CAP * 25)
    assert _run_blocking_with_unwritable_stderr(hook, shell, mode).returncode == 2
