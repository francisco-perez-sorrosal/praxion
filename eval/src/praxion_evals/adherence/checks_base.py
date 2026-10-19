"""What the check modules share and none of them owns: where a session's writes land.

``checks_common`` builds the table from the checks in ``checks_fetch`` and ``checks_judged``,
so the helpers those two read live here, below all of them, and every import in the check
modules is at module level.
"""

from __future__ import annotations

import os
from collections.abc import Mapping

from praxion_evals.adherence.model import SessionEvidence

AI_WORK = ".ai-work"
# The tools whose input names the file they write, and the input key that names it;
# Bash writes show only in the repository.
WRITE_TOOLS: Mapping[str, str] = {
    "Write": "file_path",
    "Edit": "file_path",
    "MultiEdit": "file_path",
    "NotebookEdit": "notebook_path",
}


def slug_dir(slug: str) -> str:
    return f"{AI_WORK}/{slug}"


def written_paths(evidence: SessionEvidence) -> frozenset[str]:
    """Every path the session changed: the repository's delta and the role's own Write/Edit calls."""
    cwd = evidence.envelope.init.cwd if evidence.envelope.init else None
    named = {
        _repo_relative(str(use.input[WRITE_TOOLS[use.name]]), cwd)
        for use in evidence.role_tool_uses
        if use.name in WRITE_TOOLS and WRITE_TOOLS[use.name] in use.input
    }
    return frozenset(evidence.repo.files) | evidence.repo.deleted | named


def _repo_relative(file_path: str, cwd: str | None) -> str:
    if cwd is None or not os.path.isabs(file_path):
        return os.path.normpath(file_path)
    root, target = os.path.realpath(cwd), os.path.realpath(file_path)
    return os.path.relpath(target, root) if target.startswith(root + os.sep) else target
