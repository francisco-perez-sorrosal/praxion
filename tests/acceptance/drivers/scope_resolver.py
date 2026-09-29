"""Driver for the test-selection command, reached only through its CLI.

Scenarios build a throwaway git repository, change files in it, and ask the
resolver -- run as a subprocess with `--json`, exactly as an agent or CI job
would -- which tests that change needs. Nothing here imports the resolver: the
only contract is its command line and its schema-2 JSON on stdout.

Test tools. A vitest or jest pocket is served only when its tool is on `PATH`
(otherwise it widens as `tool-unavailable`). The resolver emits invocations
rather than running them, so an executable stub named after the tool is enough
to make the tool "available"; the real vitest and jest never need installing.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]
RESOLVER = _REPO_ROOT / "scripts" / "resolve_test_scope.py"


def _git(root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=root, check=True, capture_output=True, text=True, timeout=30
    )
    return result.stdout.strip()


@dataclass(frozen=True)
class ScratchRepo:
    """A throwaway git repository the resolver is pointed at."""

    root: Path
    tool_dir: Path

    def write(self, relpath: str, text: str = "") -> None:
        target = self.root / relpath
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")

    def remove(self, relpath: str) -> None:
        """Delete a file from the working tree only (the index still has it)."""
        (self.root / relpath).unlink()

    def git(self, *args: str) -> str:
        return _git(self.root, *args)

    def commit_all(self, message: str) -> str:
        self.git("add", "-A")
        self.git("commit", "-qm", message)
        return self.head()

    def head(self) -> str:
        return self.git("rev-parse", "HEAD")

    def provide_tools(self, names: Iterable[str]) -> None:
        """Make each named test tool available on the resolver's `PATH`."""
        self.tool_dir.mkdir(parents=True, exist_ok=True)
        for name in names:
            stub = self.tool_dir / name
            stub.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            stub.chmod(0o755)


def new_scratch_repo(workspace: Path) -> ScratchRepo:
    """An empty repository with commit identity configured.

    The tool stubs live beside the repository, never inside it, so they never
    show up as untracked changes.
    """
    root = workspace / "repo"
    root.mkdir(parents=True)
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "acceptance@example.invalid")
    _git(root, "config", "user.name", "Acceptance Test")
    _git(root, "config", "commit.gpgsign", "false")
    return ScratchRepo(root=root, tool_dir=workspace / "tool-stubs")


class ResolverError(AssertionError):
    pass


def resolve(repo: ScratchRepo, *mode_args: str) -> dict:
    """Run the resolver with `--json` and the given input mode; return its payload.

    `mode_args` is one input mode (`--changed PATH...`, `--changed-from REF`,
    `--full`) or nothing for the working-tree mode.
    """
    env = dict(os.environ)
    env["PATH"] = f"{repo.tool_dir}{os.pathsep}{env.get('PATH', '')}"
    result = subprocess.run(
        [sys.executable, str(RESOLVER), "--repo-root", str(repo.root), "--json", *mode_args],
        cwd=repo.root,
        capture_output=True,
        text=True,
        env=env,
        timeout=120,
    )
    if result.returncode != 0:
        raise ResolverError(
            f"resolver exited {result.returncode} for {list(mode_args)}\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )
    return json.loads(result.stdout)


# -- Reading the payload --------------------------------------------------


def pocket(payload: dict, root: str) -> dict:
    """The pocket whose root is `root` (repo-relative, `.` for the repo root)."""
    for candidate in payload["pockets"]:
        if candidate["root"] == root:
            return candidate
    roots = [p["root"] for p in payload["pockets"]]
    raise AssertionError(f"no pocket rooted at {root!r}; pockets: {roots}")


def widen_entries(payload: dict, reason: str) -> list[dict]:
    return [entry for entry in payload["widen"] if entry["reason"] == reason]


def unmapped_paths(payload: dict) -> set[str]:
    """Every path named by an `unmapped-path` widen."""
    return {path for entry in widen_entries(payload, "unmapped-path") for path in entry["paths"]}


def selected_tests(payload: dict) -> dict[str, dict]:
    """Every selected test across all pockets, keyed by its path."""
    return {test["path"]: test for p in payload["pockets"] for test in p["tests"]}


def all_argv_args(payload: dict) -> list[str]:
    return [
        arg
        for p in payload["pockets"]
        for invocation in p["invocations"]
        for arg in invocation["argv"]
    ]


def args_after(argv: Sequence[str], *marker: str) -> list[str]:
    """The arguments that follow the first occurrence of the `marker` sequence."""
    width = len(marker)
    for index in range(len(argv) - width + 1):
        if tuple(argv[index : index + width]) == marker:
            return list(argv[index + width :])
    raise AssertionError(f"{' '.join(marker)!r} not found in argv {list(argv)}")
