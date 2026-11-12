#!/usr/bin/env python3
"""Run a command under a real pty, feeding it scripted prompt answers.

tests/test_legacy_chub_cleanup.sh needs scenarios where the installer's
TTY-gated `ask()` prompts actually fire (interactive runs, both
Enter-key defaults and explicit non-default choices). Piping input
(`printf '\\n\\n' | cmd`) makes stdin a *pipe*, not a tty, which the
installer's `[ -t 0 ]` guard treats as non-interactive — the wrong code
path. A real pty is the only way to drive the interactive branch
hermetically.

Usage:
  pty_scripted_run.py --timeout SECONDS --answers N [--answer-delay SECONDS] -- CMD ARG...
  pty_scripted_run.py --timeout SECONDS --answer VAL [--answer VAL ...] [--answer-delay SECONDS] -- CMD ARG...

Two ways to script the answers sent to successive prompts:
  - `--answers N`: sends N blank lines ("\\n" — accepts the installer's
    numbered default at every prompt). The original, accept-every-default
    form.
  - `--answer VAL` (repeatable): sends VAL followed by "\\n" at each
    prompt, in the order given — e.g. `--answer "" --answer 2` accepts the
    first prompt's default and explicitly picks "2" at the second. Lets a
    scenario exercise a decline/non-default branch at one prompt while
    defaulting every other. When any `--answer` is given, it takes over
    entirely and `--answers` is ignored.

Behavior:
  - Forks CMD under a pty; the child's stdin/stdout/stderr are the pty slave,
    so `[ -t 0 ]` is true inside it.
  - Every --answer-delay seconds, writes the next scripted answer (blank, or
    the next `--answer` value) followed by a newline to the pty master, up
    to the scripted count.
  - The master is kept open until the child exits or --timeout is hit — pty
    semantics deliver SIGHUP to the child the instant the master closes
    (pty.fork() makes the child a session leader), so closing it early to
    simulate "ran out of scripted answers" kills the child mid-output
    instead of giving it a clean EOF on its next `read`. If the child asks
    more questions than were scripted, the run times out instead — a
    diagnosable failure, not a false pass.
  - Combined stdout+stderr of the child is relayed to this process's stdout.
  - Exits with the child's exit code, or 124 if --timeout is exceeded (the
    child is SIGKILLed first, matching the `timeout(1)` convention).
"""

from __future__ import annotations

import argparse
import os
import pty
import select
import signal
import sys
import time

READ_CHUNK_BYTES = 4096
POLL_SECONDS = 0.1
DRAIN_POLL_SECONDS = 0.05
TIMEOUT_EXIT = 124
NO_COMMAND_EXIT = 2
EXEC_FAILED_EXIT = 127


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--timeout", type=float, default=20.0)
    parser.add_argument("--answers", type=int, default=8)
    parser.add_argument(
        "--answer",
        action="append",
        default=None,
        help="Scripted answer for the next prompt (repeatable, in order). "
        "Overrides --answers when given at least once.",
    )
    parser.add_argument("--answer-delay", type=float, default=0.2)
    parser.add_argument("cmd", nargs=argparse.REMAINDER)
    return parser.parse_args(argv)


def scripted_answers(args: argparse.Namespace) -> list[str]:
    """The explicit --answer list, else --answers blank lines (accept every default)."""
    return args.answer if args.answer is not None else [""] * args.answers


def command_from(args: argparse.Namespace) -> list[str]:
    return args.cmd[1:] if args.cmd and args.cmd[0] == "--" else args.cmd


def spawn(cmd: list[str]) -> tuple[int, int]:
    """Fork `cmd` onto a pty slave; returns (child pid, pty master fd)."""
    pid, master_fd = pty.fork()
    if pid == 0:
        os.execvp(cmd[0], cmd)
        os._exit(EXEC_FAILED_EXIT)  # pragma: no cover — only reached if execvp fails
    return pid, master_fd


def emit(output: bytearray) -> None:
    sys.stdout.buffer.write(bytes(output))
    sys.stdout.flush()


def send_answer(master_fd: int, answer: str) -> None:
    try:
        os.write(master_fd, (answer + "\n").encode())
    except OSError:
        pass


def poll_exit(pid: int) -> int | None:
    """The child's wait status once it has exited, else None."""
    try:
        done_pid, status = os.waitpid(pid, os.WNOHANG)
    except ChildProcessError:
        return 0
    return status if done_pid == pid else None


def exit_code_of(status: int) -> int:
    return os.WEXITSTATUS(status) if os.WIFEXITED(status) else 1


def is_readable(master_fd: int, wait: float) -> bool:
    rlist, _, _ = select.select([master_fd], [], [], wait)
    return master_fd in rlist


def read_chunk(master_fd: int) -> bytes:
    try:
        return os.read(master_fd, READ_CHUNK_BYTES)
    except OSError:
        return b""


def drain(master_fd: int, output: bytearray) -> None:
    """Collect whatever is left in the pty buffer after the child exited."""
    while is_readable(master_fd, DRAIN_POLL_SECONDS):
        chunk = read_chunk(master_fd)
        if not chunk:
            break
        output.extend(chunk)


def kill_and_report_timeout(pid: int, output: bytearray) -> int:
    try:
        os.kill(pid, signal.SIGKILL)
        os.waitpid(pid, 0)
    except OSError:
        pass
    emit(output)
    print("\n[pty_scripted_run] TIMEOUT waiting for child", file=sys.stderr)
    return TIMEOUT_EXIT


def run(cmd: list[str], answers: list[str], timeout: float, answer_delay: float) -> int:
    pid, master_fd = spawn(cmd)
    deadline = time.time() + timeout
    sent = 0
    next_send = time.time() + answer_delay
    output = bytearray()

    while True:
        now = time.time()
        if now > deadline:
            return kill_and_report_timeout(pid, output)

        if sent < len(answers) and now >= next_send:
            send_answer(master_fd, answers[sent])
            sent += 1
            next_send = now + answer_delay

        status = poll_exit(pid)
        if status is not None:
            drain(master_fd, output)
            emit(output)
            return exit_code_of(status)

        if is_readable(master_fd, POLL_SECONDS):
            output.extend(read_chunk(master_fd))


def main() -> int:
    args = parse_args()
    cmd = command_from(args)
    if not cmd:
        print("pty_scripted_run: no command given", file=sys.stderr)
        return NO_COMMAND_EXIT
    return run(cmd, scripted_answers(args), args.timeout, args.answer_delay)


if __name__ == "__main__":
    sys.exit(main())
