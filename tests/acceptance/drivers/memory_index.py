"""Driver for the memory-index audit and the write-time guard, reached only as commands.

The audit is `scripts/check_memory_index.py`, run as a person or the sentinel runs
it: given index paths, or `--all` over a config directory, in text or `--json`.
The guard is `hooks/guard_memory_index.py`, run as the harness runs a PreToolUse
hook: the Write or Edit payload on stdin, `CLAUDE_CONFIG_DIR` pointing at a
sandbox config directory, an optional JSON object read back from stdout.

Every index this driver builds is otherwise clean by the audit's own convention:
each line is a pointer `- [Topic NNN](topic_NNN.md) — <hook>` of at most 150
characters to a topic file that exists beside it, and every topic file is linked
once. Its byte and line counts are exact, so a scenario can stand on either side
of a size boundary. Bytes are UTF-8 bytes (the em dash is three), lines are
newline-terminated lines.

What the writing session reads from the guard is decided by the harness, not by
the hook: for a PreToolUse hook that exits 0, only `hookSpecificOutput.
additionalContext` reaches the model's context; a `permissionDecision` of `deny`
blocks the call (Claude Code hooks documentation, read 2026-11-12).
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[3]
AUDIT = REPO_ROOT / "scripts" / "check_memory_index.py"
GUARD = REPO_ROOT / "hooks" / "guard_memory_index.py"

MAX_LINE_CHARS = 150
PROJECT_KEY = "-acceptance-project"

# The kinds the audit reports for an index's content rather than its size. Any other
# finding on an index this driver built is about the index's size.
CONTENT_KINDS = frozenset({"too-long", "not-a-pointer", "dangling", "duplicate", "unindexed"})


# -- Building an index -----------------------------------------------------------------


def _pointer_stem(number: int) -> str:
    return f"- [Topic {number:03d}](topic_{number:03d}.md) — "


def _byte_len(text: str) -> int:
    return len(text.encode("utf-8"))


def index_lines(lines: int, total_bytes: int, *, first: int = 0) -> list[str]:
    """`lines` pointer lines (no newlines) whose newline-terminated text is `total_bytes`."""
    stems = [_pointer_stem(first + i) for i in range(lines)]
    padding = total_bytes - sum(_byte_len(s) + 1 for s in stems)
    if padding < 0:
        raise ValueError(f"{lines} pointer lines cannot fit in {total_bytes} bytes")
    per_line, extra = divmod(padding, lines)
    built = [s + "h" * (per_line + (1 if i < extra else 0)) for i, s in enumerate(stems)]
    longest = max(len(line) for line in built)
    if longest > MAX_LINE_CHARS:
        raise ValueError(f"{lines} lines of {total_bytes} bytes need a {longest}-char line")
    return built


def text_of(lines: list[str]) -> str:
    return "".join(f"{line}\n" for line in lines)


@dataclass(frozen=True)
class MemoryHome:
    """A sandbox config directory holding one project's auto-memory directory."""

    config_dir: Path
    project_key: str = PROJECT_KEY

    @property
    def memory_dir(self) -> Path:
        return self.config_dir / "projects" / self.project_key / "memory"

    @property
    def index(self) -> Path:
        return self.memory_dir / "MEMORY.md"

    def size(self) -> tuple[int, int]:
        """The index's (bytes, lines) as it stands on disk."""
        data = self.index.read_bytes()
        return len(data), data.count(b"\n")


def memory_home(config_dir: Path, *, project_key: str = PROJECT_KEY) -> MemoryHome:
    return MemoryHome(config_dir=config_dir, project_key=project_key)


def write_topics(home: MemoryHome, lines: list[str]) -> None:
    """Create the topic file every pointer line links to."""
    home.memory_dir.mkdir(parents=True, exist_ok=True)
    for line in lines:
        match = re.search(r"\]\(([^)]+)\)", line)
        if match is not None:
            (home.memory_dir / match.group(1)).write_text("Detail lives here.\n", encoding="utf-8")


def place_index(home: MemoryHome, lines: list[str]) -> MemoryHome:
    """Write the index and every topic file it links to."""
    write_topics(home, lines)
    home.index.write_text(text_of(lines), encoding="utf-8")
    return home


def sized_index(
    config_dir: Path, *, lines: int, total_bytes: int, project_key: str = PROJECT_KEY
) -> MemoryHome:
    """A clean index of exactly `lines` lines and `total_bytes` bytes."""
    home = memory_home(config_dir, project_key=project_key)
    place_index(home, index_lines(lines, total_bytes))
    if home.size() != (total_bytes, lines):
        raise AssertionError(f"built {home.size()}, wanted ({total_bytes}, {lines})")
    return home


# -- Running the audit -----------------------------------------------------------------


@dataclass(frozen=True)
class AuditRun:
    exit_code: int
    stdout: str
    stderr: str

    def json(self) -> dict[str, list[dict[str, Any]]]:
        try:
            doc = json.loads(self.stdout)
        except json.JSONDecodeError as exc:
            raise AssertionError(
                f"the audit printed no JSON (exit {self.exit_code}):\n{self.stdout}{self.stderr}"
            ) from exc
        return doc

    def findings_for(self, index: Path) -> list[dict[str, Any]]:
        """The `--json` findings reported for one index, matched by its resolved path."""
        doc = self.json()
        for key, findings in doc.items():
            if Path(key).resolve() == index.resolve():
                return findings
        raise AssertionError(f"the audit reported nothing for {index}: {sorted(doc)}")


def _env(config_dir: Path) -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if not k.startswith(("CLAUDE", "PRAXION_"))}
    env["CLAUDE_CONFIG_DIR"] = str(config_dir)
    return env


def audit(config_dir: Path, *arguments: str) -> AuditRun:
    """`check_memory_index.py <arguments>` with the sandbox config directory."""
    result = subprocess.run(
        [sys.executable, str(AUDIT), *arguments],
        capture_output=True,
        text=True,
        env=_env(config_dir),
        cwd=config_dir,
        timeout=60,
    )
    return AuditRun(result.returncode, result.stdout, result.stderr)


def size_findings(findings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [f for f in findings if f.get("kind") not in CONTENT_KINDS]


def content_kinds(findings: list[dict[str, Any]]) -> list[str]:
    return sorted(f["kind"] for f in findings if f.get("kind") in CONTENT_KINDS)


# -- Running the guard -----------------------------------------------------------------


@dataclass(frozen=True)
class GuardRun:
    exit_code: int
    stdout: str
    stderr: str

    @property
    def output(self) -> dict[str, Any]:
        if not self.stdout.strip():
            return {}
        try:
            doc = json.loads(self.stdout)
        except json.JSONDecodeError as exc:
            raise AssertionError(
                f"the guard printed something that is not JSON: {self.stdout!r}"
            ) from exc
        return doc.get("hookSpecificOutput", {}) if isinstance(doc, dict) else {}

    @property
    def decision(self) -> str | None:
        return self.output.get("permissionDecision")

    @property
    def reason(self) -> str | None:
        return self.output.get("permissionDecisionReason")

    @property
    def session_reads(self) -> str | None:
        """What the writing session reads from an allowed call: the added context."""
        return self.output.get("additionalContext")

    @property
    def lets_the_write_land(self) -> bool:
        return self.exit_code != 2 and self.decision not in ("deny", "ask")


def _guard(home: MemoryHome, payload: dict[str, Any] | str) -> GuardRun:
    stdin = payload if isinstance(payload, str) else json.dumps(payload)
    result = subprocess.run(
        [sys.executable, str(GUARD)],
        input=stdin,
        capture_output=True,
        text=True,
        env=_env(home.config_dir),
        timeout=30,
    )
    return GuardRun(result.returncode, result.stdout, result.stderr)


def guard_write(home: MemoryHome, lines: list[str]) -> GuardRun:
    """A Write of the whole index; the topic files it links to already exist."""
    write_topics(home, lines)
    tool_input = {"file_path": str(home.index), "content": text_of(lines)}
    return _guard(
        home, {"hook_event_name": "PreToolUse", "tool_name": "Write", "tool_input": tool_input}
    )


def guard_edit(home: MemoryHome, old_string: str, new_string: str) -> GuardRun:
    """An Edit replacing `old_string` once; any topic file `new_string` links to exists."""
    write_topics(home, new_string.splitlines())
    tool_input = {"file_path": str(home.index), "old_string": old_string, "new_string": new_string}
    return _guard(
        home, {"hook_event_name": "PreToolUse", "tool_name": "Edit", "tool_input": tool_input}
    )


def guard_raw(home: MemoryHome, stdin: str) -> GuardRun:
    return _guard(home, stdin)


def land_write(home: MemoryHome, lines: list[str]) -> None:
    """What the harness does with a write the guard let through."""
    place_index(home, lines)


def lengthened(lines: list[str], index: int, extra_chars: int) -> list[str]:
    """`lines` with one pointer's hook text longer by `extra_chars` ASCII characters."""
    return [line + "g" * extra_chars if i == index else line for i, line in enumerate(lines)]


# -- Reading numbers out of a message ------------------------------------------------------


def names_number(text: str, value: int) -> bool:
    """Whether `text` states `value` as a whole number, with or without thousands separators."""
    digits = str(value)
    groups = []
    while digits:
        groups.insert(0, digits[-3:])
        digits = digits[:-3]
    pattern = r"[,.   _]?".join(re.escape(g) for g in groups)
    return re.search(rf"(?<![\d,.]){pattern}(?![\d]|[,.]\d)", text) is not None
