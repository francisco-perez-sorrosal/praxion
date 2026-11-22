"""Driver for the test-scope resolver's answer to a change of one file alone, on a copy of this checkout.

The resolver is reached only through its command line, `--changed PATH... --json --per-path`,
which prints for each path exactly what `--changed <path> --json` prints for that path alone. It
runs from a copy (`make_copy`, built from git objects), so the files it opens while walking the
tree are the copy's, never this checkout's: a selection audit tracing the suite does not see a
test here read the whole repository.

A pocket whose adapter needs a tool on `PATH` answers by what the machine has installed (the
dashboard's vitest pocket widens as `tool-unavailable` without it). Every answer here is taken
with no vitest and no jest on `PATH`, so an answer never depends on what the machine installed.

A test is selected for a file when the answer of the pocket holding the test is that pocket's full
suite or a list naming the test.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from collections.abc import Iterable, Mapping
from pathlib import Path

from tests.acceptance.drivers.gate_liveness import RepoCopy

RESOLVER = "scripts/resolve_test_scope.py"
ROOT_POCKET = "."
FULL = "full"
TOOLS_KEPT_OFF_PATH = ("vitest", "jest")
RESOLVE_TIMEOUT_SECONDS = 900


def _path_without_tools(value: str) -> str:
    kept = [
        entry
        for entry in value.split(os.pathsep)
        if entry and not any((Path(entry) / tool).exists() for tool in TOOLS_KEPT_OFF_PATH)
    ]
    return os.pathsep.join(kept)


def tracked_files(copy: RepoCopy) -> tuple[str, ...]:
    listed = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=copy.root,
        capture_output=True,
        text=True,
        check=True,
        timeout=60,
    ).stdout
    return tuple(sorted(filter(None, listed.split("\0"))))


def answers_for(copy: RepoCopy, paths: Iterable[str]) -> dict[str, dict]:
    """The resolver's schema-2 answer for each path changed alone, keyed by the path."""
    wanted = sorted(set(paths))
    env = dict(os.environ)
    env["PATH"] = _path_without_tools(env.get("PATH", ""))
    result = subprocess.run(
        [sys.executable, str(copy.path(RESOLVER)), "--repo-root", str(copy.root), "--json"]
        + ["--per-path", "--changed", *wanted],
        cwd=copy.root,
        capture_output=True,
        text=True,
        env=env,
        timeout=RESOLVE_TIMEOUT_SECONDS,
    )
    if result.returncode != 0:
        raise AssertionError(f"the resolver exited {result.returncode}:\n{result.stderr[-3000:]}")
    answers = {}
    for line in filter(None, result.stdout.splitlines()):
        payload = json.loads(line)
        (path,) = payload["changed"]["paths"]
        answers[path] = payload
    missing = [path for path in wanted if path not in answers]
    if missing:
        raise AssertionError(f"the resolver gave no answer for {missing[:20]}")
    return answers


def pocket_answer(answer: Mapping, root: str) -> str | frozenset[str] | None:
    """`"full"`, the set of tests the pocket at `root` selected, or None when it is absent."""
    for pocket in answer["pockets"]:
        if pocket["root"] == root:
            if pocket["selection"] == FULL:
                return FULL
            return frozenset(test["path"] for test in pocket["tests"])
    return None


def selects(answer: Mapping, test: str, pocket_root: str = ROOT_POCKET) -> bool:
    chosen = pocket_answer(answer, pocket_root)
    return chosen == FULL or (chosen is not None and test in chosen)


def describe_root_answer(answer: Mapping) -> str:
    chosen = pocket_answer(answer, ROOT_POCKET)
    if chosen is None or chosen == FULL:
        return f"root pocket: {chosen}"
    return f"root pocket selected {len(chosen)} tests: {sorted(chosen)[:25]}"
