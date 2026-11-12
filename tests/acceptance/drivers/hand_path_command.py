"""Driver for the command the hand path hands over, run in the person's own terminal.

`install.sh code --complete-install` runs from a plugin root (a version directory of the scratch
machine's cache, or a clone checkout) with its standard input, output and error on a
pseudo-terminal that is also its controlling terminal, as in the person's own terminal. A
`Person` answers each prompt the way a scenario says. A prompt is output that stops without a
newline and then waits; it is recognized by what it asks about:

- a numbered choice (`[1] ... [2] Skip ...` then `Choice [n]:`) or a yes/no question
  (`[Y/n]`, `[y/N]`, `(y/n)`): the first one that names `CLAUDE.md`, the instructions or a
  personal value is the instructions offer; any later one that does is a question about the
  personal values; one naming the rules or the scripts offers those; any other is skipped;
- a free-text line whose label (the words before its bracketed default) names the username, the
  email or `GitHub` asks for that personal value, whatever the default it shows holds; an empty
  answer accepts that default;
- a question about the values after the last value line is the confirmation: it shows the values
  the command will write; "y" confirms and "n" declines, whatever words its lines hold. Declining
  the values means that "n"; any question about them before the value lines is accepted.

Accepting a choice picks its first option not labelled "Skip"; declining picks the "Skip" one.
An input that ends is a Ctrl-D on an empty line, and every later prompt gets one too. The closing
report is what the command prints after its last prompt.

The scratch machine, its cache and the update from N to N+1 are `plugin_update`'s.
"""

from __future__ import annotations

import fcntl
import hashlib
import os
import re
import select
import signal
import subprocess
import termios
import time
from dataclasses import dataclass, field
from pathlib import Path

from tests.acceptance.drivers import plugin_update as pu

DONE = "Praxion complete install done"
COMMAND = ("code", "--complete-install")
VALUE_NAMES = ("USERNAME", "EMAIL", "GITHUB_URL")
STALL_SECONDS = 0.6  # silence after output that ends without a newline: the command waits
MAX_PROMPTS = 80
END_OF_INPUT = b"\x04"

# Personal values a person types; made up, and different from anything the machine derives.
TYPED = {
    "USERNAME": "Tamsin Madeup",
    "EMAIL": "tamsin.madeup@example.invalid",
    "GITHUB_URL": "https://example.invalid/tamsin-madeup",
}

_ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")
_CHOICE = re.compile(r"Choice\s*(\[[^\]]*\])?\s*:?\s*$")
_YES_NO = re.compile(r"\[(y/n|yes/no)\]|\((y/n|yes/no)\)", re.IGNORECASE)
_OPTION = re.compile(r"^\s*\[(\d+)\]\s*(.*)$", re.MULTILINE)
_VALUE_WORDS = ("email", "github", "username", "personal value", "identity")
_LABEL = re.compile(r"^\s*([^\[:]*)")  # the words before the bracketed default


# -- The person -----------------------------------------------------------------------------------


@dataclass(frozen=True)
class Person:
    """How the person answers. `instructions` and `at_values`: "accept", "decline" or "end"."""

    instructions: str = "accept"
    values: dict[str, str] | None = None  # typed at the value prompts; None accepts each default
    at_values: str = "accept"


@dataclass(frozen=True)
class Prompt:
    topic: str  # instructions | values | value:<NAME> | rules | scripts | other
    text: str
    answer: str


@dataclass
class _Conversation:
    person: Person
    prompts: list[Prompt] = field(default_factory=list)
    offered: bool = False
    ended: bool = False
    values_answered: bool = False

    def answer(self, segment: str) -> bytes:
        lines = [line for line in segment.splitlines() if line.strip()]
        last = lines[-1]
        if _CHOICE.search(last):
            kind, text = "choice", _options_block(lines)
        elif _YES_NO.search(last):
            kind, text = "yes-no", "\n".join(lines[-6:])
        else:
            kind, text = "text", last
        topic = self._topic(kind, text)
        reply = END_OF_INPUT if self.ended else self._reply(kind, topic, text)
        if reply == END_OF_INPUT:
            self.ended = True
        self.prompts.append(Prompt(topic, text, reply.decode(errors="replace")))
        return reply

    def _topic(self, kind: str, text: str) -> str:
        low = text.lower()
        if kind == "text":
            name = _value_name(text)
            return f"value:{name}" if name else "other"
        if "claude.md" in low or "instructions" in low or any(w in low for w in _VALUE_WORDS):
            if not self.offered:
                self.offered = True
                return "instructions"
            return "values"
        if "rule" in low:
            return "rules"
        return "scripts" if "script" in low else "other"

    def _reply(self, kind: str, topic: str, text: str) -> bytes:
        p = self.person
        intent = {"instructions": p.instructions, "rules": "accept", "scripts": "accept",
                  "other": "decline"}.get(topic, p.at_values)  # fmt: skip
        if topic == "values" and intent == "decline" and not self.values_answered:
            intent = "accept"  # a decline is the answer at the confirmation after the values
        if intent == "end":
            return END_OF_INPUT
        if kind == "text":
            self.values_answered = self.values_answered or topic.startswith("value:")
            name = topic.partition(":")[2]
            return f"{(p.values or {}).get(name, '')}\n".encode()
        own_values = topic == "values" and p.values is not None and intent == "accept"
        if kind == "yes-no":
            return b"y\n" if intent == "accept" else b"n\n"
        return f"{_option(text, intent, prefer_own=own_values)}\n".encode()


def _value_name(prompt: str) -> str | None:
    """The personal value a free-text prompt asks for, read from its label alone: a derived default
    that holds `github` or `email` must not turn the Username line into another question."""
    label = _LABEL.match(prompt).group(1).lower()
    for word, name in (("email", "EMAIL"), ("github", "GITHUB_URL"), ("user", "USERNAME"),
                       ("name", "USERNAME")):  # fmt: skip
        if word in label:
            return name
    return None


def _options_block(lines: list[str]) -> str:
    starts = [i for i, line in enumerate(lines) if re.match(r"^\s*\[1\]", line)]
    return "\n".join(lines[starts[-1] :] if starts else lines[-8:])


def _option(block: str, intent: str, *, prefer_own: bool) -> str:
    options = _OPTION.findall(block)
    skips = [n for n, label in options if label.lower().startswith("skip")]
    others = [n for n, label in options if not label.lower().startswith("skip")]
    if intent != "accept":
        return skips[0] if skips else (options[-1][0] if options else "")
    if prefer_own:
        own = [n for n, label in options if re.search(r"\b(own|enter|type)\b", label, re.I)]
        others = own or others
    return others[0] if others else ""


# -- A run ----------------------------------------------------------------------------------------


@dataclass(frozen=True)
class CommandRun:
    exit_code: int | None
    transcript: str
    prompts: list[Prompt]
    report: list[str]  # the lines printed after the last prompt
    timed_out: bool

    def asked(self, *topics: str) -> list[Prompt]:
        return [p for p in self.prompts if p.topic in topics or p.topic.split(":")[0] in topics]

    @property
    def offers(self) -> list[Prompt]:
        return self.asked("instructions")

    @property
    def value_questions(self) -> list[Prompt]:
        return self.asked("values", "value")

    @property
    def confirmations(self) -> list[Prompt]:
        """The questions about the values asked after the last value line."""
        last = max(
            (i for i, p in enumerate(self.prompts) if p.topic.startswith("value:")), default=None
        )
        if last is None:
            return []
        return [p for p in self.prompts[last + 1 :] if p.topic == "values"]

    @property
    def instructions_report(self) -> str:
        """The closing report's lines about the instructions."""
        hits = [ln for ln in self.report if re.search(r"claude\.md|instructions", ln, re.I)]
        return "\n".join(hits)

    @property
    def says_done(self) -> bool:
        return any(DONE in line for line in self.report)


def run_command(
    root: Path, machine: pu.Machine, person: Person, *, python: str | None = None,
    timeout: float = 300,
) -> CommandRun:  # fmt: skip
    """`bash <root>/install.sh code --complete-install` in the machine's HOME, on a terminal."""
    env = machine.env()
    env["PATH"] = f"{_tool_stand_ins(machine)}{os.pathsep}{env['PATH']}"
    if python is not None:
        env["PATH"] = f"{_python_shim(machine, python)}{os.pathsep}{env['PATH']}"
    master, slave = os.openpty()

    def own_terminal() -> None:
        os.setsid()
        fcntl.ioctl(0, termios.TIOCSCTTY, 0)

    proc = subprocess.Popen(
        ["bash", str(root / "install.sh"), *COMMAND],
        stdin=slave, stdout=slave, stderr=slave, cwd=machine.root / "work", env=env,
        preexec_fn=own_terminal,
    )  # fmt: skip
    os.close(slave)
    try:
        raw, marks, conversation, timed_out = _converse(proc, master, person, timeout)
    finally:
        os.close(master)
        if proc.poll() is None:
            os.killpg(proc.pid, signal.SIGKILL)
            proc.wait()
    report = _clean(raw[marks[-1] :] if marks else raw)
    return CommandRun(
        proc.returncode, _clean(raw), conversation.prompts,
        [line.strip() for line in report.splitlines() if line.strip()], timed_out,
    )  # fmt: skip


def _converse(proc, master: int, person: Person, timeout: float):
    raw, marks = bytearray(), []
    conversation = _Conversation(person)
    start = last = time.monotonic()
    while time.monotonic() - start < timeout and len(conversation.prompts) < MAX_PROMPTS:
        ready, _, _ = select.select([master], [], [], 0.1)
        if ready:
            chunk = _read(master)
            if not chunk:
                return raw, marks, conversation, False
            raw += chunk
            last = time.monotonic()
            continue
        if proc.poll() is not None:
            return raw, marks, conversation, False
        segment = _clean(raw[marks[-1] if marks else 0 :])
        if time.monotonic() - last < STALL_SECONDS or not _waits_for_input(segment):
            continue
        os.write(master, conversation.answer(segment))
        marks.append(len(raw))
        last = time.monotonic()
    return raw, marks, conversation, True


def _read(master: int) -> bytes:
    try:
        return os.read(master, 65536)
    except OSError:  # the terminal's other end closed with the command
        return b""


def _waits_for_input(segment: str) -> bool:
    if not segment.strip() or segment.endswith("\n"):
        return False
    return segment.rstrip()[-1:] in (":", "?", "]", ")", ">")


def _clean(raw: bytes | bytearray) -> str:
    return _ANSI.sub("", bytes(raw).decode("utf-8", errors="replace")).replace("\r", "")


def _tool_stand_ins(machine: pu.Machine) -> Path:
    """A stand-in for each optional tool the installer's shared steps offer to install when it is
    missing (`scc`), so every host holds the same conversation. Without it the offer appears only
    where the host lacks the tool, and its text (a `github.com` install line) reads as the
    instructions offer and takes that answer."""
    stand_ins = machine.root / "tool-stand-ins"
    stand_ins.mkdir(parents=True, exist_ok=True)
    scc = stand_ins / "scc"
    scc.write_text('#!/bin/sh\necho "scc version 3.4.0 (stand-in)"\n', encoding="utf-8")
    scc.chmod(0o755)
    return stand_ins


def _python_shim(machine: pu.Machine, python: str) -> Path:
    shims = machine.root / "older-python"
    shims.mkdir(parents=True, exist_ok=True)
    shim = shims / "python3"
    shim.write_text(f'#!/bin/sh\nexec "{python}" "$@"\n', encoding="utf-8")
    shim.chmod(0o755)
    return shims


# -- Arranging the instructions -------------------------------------------------------------------

HAND_ADDED = "\nA line the person added by hand.\n"


def unreadable(update: pu.Update, how: str) -> str:
    """N's render made unreadable `how`: hand-edited, cut short, or another template's render."""
    text = update.n_render
    return {
        "hand-edited": lambda: text + HAND_ADDED,
        "cut-short": lambda: text[: len(text) // 2],
        "another-template": lambda: pu.render(
            pu.without_github_line(update.n_template) + "\n## Another template\n", update.n_values
        ),
    }[how]()


def point_instructions_at(machine: pu.Machine, target: Path) -> None:
    if machine.instructions.is_symlink() or machine.instructions.exists():
        machine.instructions.unlink()
    machine.instructions.symlink_to(target)


def renders(machine: pu.Machine) -> list[Path]:
    """Every render in the machine's plugin cache."""
    return sorted(machine.cache.glob(f"*/{pu.RENDER}"))


def instructions_state(machine: pu.Machine) -> dict[str, tuple]:
    """`~/.claude/CLAUDE.md` and every render in the cache: kind, link text or digest, inode and
    modification time."""
    state = {}
    for path in [machine.instructions, *renders(machine)]:
        if not (path.is_symlink() or path.exists()):
            state[str(path)] = ("absent",)
            continue
        st = path.lstat()
        what = (
            os.readlink(path)
            if path.is_symlink()
            else hashlib.sha256(path.read_bytes()).hexdigest()
        )
        state[str(path)] = (what, st.st_ino, st.st_mtime_ns)
    return state


def derived_values(update: pu.Update) -> dict[str, str]:
    """The values a fresh install of N+1 uses today: the oracle for each prompt's default."""
    return pu.values_in(update.fresh.instructions, n1_template(update))


def n1_template(update: pu.Update) -> str:
    return (update.n1 / pu.TEMPLATE).read_text(encoding="utf-8")


def files_holding(root: Path, value: str) -> list[Path]:
    """Regular files under `root` whose bytes hold `value`."""
    needle = value.encode()
    return sorted(
        p
        for p in root.rglob("*")
        if p.is_file() and not p.is_symlink() and needle in p.read_bytes()
    )


def links_refreshed(update: pu.Update) -> list[str]:
    """The rule and script links N left that do not point where a fresh install of N+1 links."""
    m, fresh = update.machine, update.fresh
    stale = [
        f"script {name}"
        for name in sorted(fresh.scripts)[len(pu.SCRIPT_ROLES) :]
        if pu.inside(m.bin / name, update.n1) != fresh.scripts[name]
    ]
    stale += [
        f"rule {place}"
        for place in sorted(fresh.rules)[len(pu.RULE_ROLES) :]
        if pu.inside(m.rules / place, update.n1) != fresh.rules[place]
    ]
    return stale


def blocked(paths_and_modes: list[tuple[Path, int]]) -> list[tuple[Path, int]]:
    """Change each path's mode; returns what restores them."""
    restore = []
    for path, mode in paths_and_modes:
        restore.append((path, path.stat().st_mode & 0o7777))
        path.chmod(mode)
    return restore


def restored(restore: list[tuple[Path, int]]) -> None:
    for path, mode in reversed(restore):
        path.chmod(mode)
