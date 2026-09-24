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


def main() -> int:
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
    args = parser.parse_args()

    # Scripted answers to send, in order — either the explicit --answer
    # list, or --answers blank lines (the original accept-every-default
    # form) when no --answer was given.
    answers = args.answer if args.answer is not None else [""] * args.answers

    cmd = args.cmd
    if cmd and cmd[0] == "--":
        cmd = cmd[1:]
    if not cmd:
        print("pty_scripted_run: no command given", file=sys.stderr)
        return 2

    pid, master_fd = pty.fork()
    if pid == 0:
        # Child: replace ourselves with the target command on the pty slave.
        os.execvp(cmd[0], cmd)
        os._exit(127)  # pragma: no cover — only reached if execvp fails

    deadline = time.time() + args.timeout
    sent = 0
    next_send = time.time() + args.answer_delay
    output = bytearray()

    while True:
        now = time.time()
        if now > deadline:
            try:
                os.kill(pid, signal.SIGKILL)
                os.waitpid(pid, 0)
            except OSError:
                pass
            sys.stdout.buffer.write(bytes(output))
            sys.stdout.flush()
            print("\n[pty_scripted_run] TIMEOUT waiting for child", file=sys.stderr)
            return 124

        if sent < len(answers) and now >= next_send:
            try:
                os.write(master_fd, (answers[sent] + "\n").encode())
            except OSError:
                pass
            sent += 1
            next_send = now + args.answer_delay

        try:
            done_pid, status = os.waitpid(pid, os.WNOHANG)
        except ChildProcessError:
            done_pid, status = pid, 0
        if done_pid == pid:
            # Drain whatever is left in the pty buffer before reporting.
            while True:
                rlist, _, _ = select.select([master_fd], [], [], 0.05)
                if master_fd not in rlist:
                    break
                try:
                    chunk = os.read(master_fd, 4096)
                except OSError:
                    break
                if not chunk:
                    break
                output.extend(chunk)
            sys.stdout.buffer.write(bytes(output))
            sys.stdout.flush()
            if os.WIFEXITED(status):
                return os.WEXITSTATUS(status)
            return 1

        rlist, _, _ = select.select([master_fd], [], [], 0.1)
        if master_fd in rlist:
            try:
                chunk = os.read(master_fd, 4096)
            except OSError:
                chunk = b""
            if chunk:
                output.extend(chunk)


if __name__ == "__main__":
    sys.exit(main())
