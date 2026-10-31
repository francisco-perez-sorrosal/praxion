#!/usr/bin/env python3
"""PreToolUse gate: a session may not leave the decisions directory in a shape finalize cannot carry.

Write and Edit are judged on the file they would leave behind; a whole Read of the decisions
index is refused so the Discovery Protocol's bounded read happens at the moment it applies.
The judgement lives in ``scripts/_decision_records.py`` and its refusal text in
``scripts/_decision_record_refusal.py``, which ship with this hook in the plugin, so they are
imported from this file's location. ``decisions_gate.sh`` runs this file only for a payload that
could concern the decisions tree.

A refusal is the only output. An allowed call prints nothing and writes nothing to stderr.
Fail-open: any error in this adapter lets the call through, and the commit gate still holds.

Declared limit: a path is judged only when addressed lexically through the project's
``.ai-state`` (a sidecar's shadow link included); a write through the state mount's real path
is not recognised.

Python 3.9-safe: the ambient ``python3`` runs it.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Union

SCRIPTS_DIR = "scripts"
GATE_CORE = "_decision_records.py"


def _scripts_dir() -> Path:
    """The ``scripts`` directory that ships beside this hook, found from this file's location.

    Nearest ancestor first: in the plugin it is ``../scripts``; the walk also finds it when a
    test harness runs a copy of this file one level deeper.
    """
    here = Path(__file__).resolve()
    candidates = [ancestor / SCRIPTS_DIR for ancestor in here.parents]
    return next(
        (c for c in candidates if (c / GATE_CORE).is_file()), here.parent.parent / SCRIPTS_DIR
    )


sys.path.insert(0, str(_scripts_dir()))

from _decision_record_refusal import find_rule_text, refusal_text  # noqa: E402
from _decision_records import (  # noqa: E402
    DECISIONS_PARTS,
    WRITE_TIME_CONTEXT,
    Change,
    Read,
    Refused,
    judge_change,
    judge_read,
)

GIT_ENTRY = ".git"
READ_TOOL = "Read"
WRITE_TOOL = "Write"
EDIT_TOOL = "Edit"

Request = Union[Change, Read]  # noqa: UP007 -- runtime alias on 3.9


def main() -> None:
    payload = json.loads(sys.stdin.read())
    request = build_request(
        payload.get("tool_name", ""), payload.get("tool_input") or {}, payload.get("cwd") or ""
    )
    if request is None:
        return
    if isinstance(request, Read):
        verdict = judge_read(request)
    else:
        verdict = judge_change(request, WRITE_TIME_CONTEXT)
    if isinstance(verdict, Refused):
        print(json.dumps(deny_output(refusal_text(verdict, find_rule_text()))))


def deny_output(reason: str) -> dict:
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }


def build_request(tool_name: str, tool_input: dict, cwd: str) -> Request | None:
    """The change or read the call would make, or ``None`` when it is not the gate's to judge."""
    file_path = tool_input.get("file_path")
    if not isinstance(file_path, str) or not file_path:
        return None
    absolute = os.path.normpath(os.path.join(cwd, file_path))
    relpath = repo_relative(absolute)
    if relpath is None:
        return None
    if tool_name == READ_TOOL:
        return Read(relpath, bounded=tool_input.get("limit") is not None)
    if tool_name not in (WRITE_TOOL, EDIT_TOOL):
        return None
    before = _read_before(Path(absolute))
    after = _after(tool_name, tool_input, before)
    return None if after is None else Change(relpath, before, after)


def repo_relative(absolute: str) -> str | None:
    """The path from its ``.ai-state/decisions`` anchor on, when the anchor sits at a repo root.

    Anchored on the path's own text, never resolved: a sidecar's ``.ai-state`` is a link, and the
    link's name is what the gate's classifier expects. The repo-root test (a ``.git`` entry,
    which a worktree holds as a file) keeps a fixture tree that merely contains such a
    directory from being judged as the project's own.
    """
    parts = Path(absolute).parts
    for index in range(1, len(parts) - 1):
        anchor = tuple(part.lower() for part in parts[index : index + len(DECISIONS_PARTS)])
        if anchor == DECISIONS_PARTS and (Path(*parts[:index]) / GIT_ENTRY).exists():
            return "/".join(parts[index:])
    return None


def _read_before(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None


def _after(tool_name: str, tool_input: dict, before: str | None) -> str | None:
    """The file text the pending write would leave, or ``None`` when it cannot be known."""
    if tool_name == WRITE_TOOL:
        content = tool_input.get("content")
        return content if isinstance(content, str) else None
    return apply_edit(
        before,
        tool_input.get("old_string"),
        tool_input.get("new_string"),
        bool(tool_input.get("replace_all")),
    )


def apply_edit(before: str | None, old: object, new: object, replace_all: bool) -> str | None:
    """``before`` with ``old`` replaced by ``new``; ``None`` when the harness would refuse the edit."""
    if before is None or not isinstance(old, str) or not isinstance(new, str):
        return None
    if not old or old not in before:
        return None
    return before.replace(old, new) if replace_all else before.replace(old, new, 1)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
