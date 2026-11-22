"""Driver for the selection audit's verdict on copies of the checkout, run on a project of its own.

A scenario builds a small throwaway git project and runs the audit on it with the command the
weekly job runs, from this checkout:

    scripts/check_gates_bite.py --gate selection-audit --json --repo-root <project>

The project's `scripts/resolve_test_scope.py` is a stand-in that speaks the resolver's schema-2
contract (`--changed PATH... --json --per-path`, one line per path) and answers from a route table
committed beside it, `scripts/routes.json`. So a scenario decides which change selects which test:
a read no route names is a read no change selects, and the audit must judge it by its own rules.

The audit's contract here is only its command line and its schema-1 JSON report. Nothing here
imports the audit. The runs are held to the project's own declared bound, which is small.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import textwrap
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from tests.acceptance.drivers.gate_liveness import REPO_ROOT, isolated_env

AUDIT_COMMAND = REPO_ROOT / "scripts" / "check_gates_bite.py"
AUDIT_GATE = "selection-audit"
PROJECT_BOUND_SECONDS = 600
RUN_TIMEOUT_SECONDS = 900

ROUTED_DATA = "docs/routed.txt"
ROUTED_TEST = "tests/test_reads_a_routed_file.py"

_STAND_IN_RESOLVER = r'''"""Stand-in test-scope resolver: a changed path selects the tests routes.json lists for it."""

import json
import sys
from pathlib import Path

ROUTES = json.loads((Path(__file__).resolve().parent / "routes.json").read_text(encoding="utf-8"))


def answer(paths):
    because = {test: path for path in paths for test in ROUTES.get(path, [])}
    tests = sorted(because)
    return {
        "schema": 2,
        "changed": {"source": "explicit", "paths": paths},
        "decision": "selected" if tests else "nothing-to-run",
        "widen": [],
        "ignored_non_source": [],
        "pockets": [
            {
                "root": ".",
                "ecosystem": "python",
                "adapter": "python-derived",
                "selection": "tests" if tests else "nothing",
                "tests": [{"path": t, "via": "declared", "because": because[t]} for t in tests],
                "invocations": [{"cwd": ".", "argv": ["pytest", *tests]}] if tests else [],
            }
        ],
    }


def changed_paths(argv):
    paths, collecting, skip = [], False, False
    for arg in argv:
        if skip:
            skip = False
        elif arg == "--repo-root":
            skip, collecting = True, False
        elif arg == "--changed":
            collecting = True
        elif arg.startswith("-"):
            collecting = False
        elif collecting:
            paths.append(arg)
    return sorted(set(paths))


def main(argv):
    if "-h" in argv or "--help" in argv:
        print("usage: resolve_test_scope.py --changed PATH [PATH ...] --json [--per-path]")
        return 0
    paths = changed_paths(argv)
    if "--per-path" in argv:
        for path in paths:
            print(json.dumps(answer([path]), separators=(",", ":")))
    else:
        print(json.dumps(answer(paths)))
    return 0


raise SystemExit(main(sys.argv[1:]))
'''

_ROUTED_TEST_SOURCE = r"""from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_reads_a_file_its_route_names():
    assert (ROOT / "docs" / "routed.txt").read_text(encoding="utf-8").strip() == "routed"
"""

_PYPROJECT = f"""[tool.pytest.ini_options]
testpaths = ["tests"]

[tool.praxion.gate-liveness]
selection-audit-timeout-seconds = {PROJECT_BOUND_SECONDS}
"""


def _git(root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-c", "commit.gpgsign=false", "-c", "core.hooksPath=/dev/null", *args],
        cwd=root,
        capture_output=True,
        text=True,
        timeout=60,
        env=isolated_env(),
    )
    if result.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed in {root}: {result.stderr}")
    return result.stdout


@dataclass(frozen=True)
class Project:
    """A committed throwaway project whose suite the audit traces."""

    root: Path

    def tracked_files(self) -> tuple[str, ...]:
        return tuple(sorted(filter(None, _git(self.root, "ls-files", "-z").split("\0"))))


def build_project(workspace: Path, files: Mapping[str, str]) -> Project:
    """A git project holding the stand-in resolver, a routed read, and `files` on top.

    Every project carries one test whose read a route selects, so an audit of it always has an
    ordinary read to judge alongside whatever the scenario's own tests do.
    """
    root = workspace / "project"
    contents = {
        "pyproject.toml": _PYPROJECT,
        "scripts/resolve_test_scope.py": _STAND_IN_RESOLVER,
        "scripts/routes.json": json.dumps({ROUTED_DATA: [ROUTED_TEST]}, indent=2) + "\n",
        ROUTED_DATA: "routed\n",
        ROUTED_TEST: _ROUTED_TEST_SOURCE,
        **{path: textwrap.dedent(text) for path, text in files.items()},
    }
    for relpath, text in contents.items():
        target = root / relpath
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
    _git(root, "init", "-q")
    _git(root, "add", "-A")
    _git(
        root,
        "-c",
        "user.name=Copy Reads Acceptance",
        "-c",
        "user.email=copy-reads-acceptance@example.invalid",
        "commit",
        "-q",
        "-m",
        "project the audit traces",
    )
    return Project(root)


@dataclass(frozen=True)
class AuditRun:
    """The selection audit's verdict on one project, as its JSON report gives it."""

    exit_code: int | None
    output: str
    passed: bool
    reason: str
    unselected: frozenset[tuple[str, str]]  # (test file, file it read)
    notes: tuple[str, ...]

    def unselected_reads_of(self, test: str) -> set[str]:
        return {read for reader, read in self.unselected if reader == test}

    def describe(self) -> str:
        pairs = "\n".join(f"  {test} read {read}" for test, read in sorted(self.unselected))
        notes = "\n".join(f"  {note}" for note in self.notes)
        return (
            f"exit={self.exit_code} passed={self.passed}\nreason: {self.reason.strip()}\n"
            f"unselected ({len(self.unselected)}):\n{pairs or '  none'}\n"
            f"notes:\n{notes or '  none'}\noutput tail:\n{self.output[-3000:]}"
        )


def run_audit(project: Project) -> AuditRun:
    """Run the selection audit on `project` from this checkout, as the weekly job runs it."""
    command = [sys.executable, str(AUDIT_COMMAND), "--gate", AUDIT_GATE, "--json"]
    command += ["--repo-root", str(project.root)]
    try:
        result = subprocess.run(
            command,
            cwd=project.root,
            env=isolated_env(),
            capture_output=True,
            text=True,
            timeout=RUN_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as expired:
        raise AssertionError(f"the audit outlived {RUN_TIMEOUT_SECONDS} s: {expired}") from None
    return _parse(result.returncode, result.stdout, result.stdout + result.stderr)


def _parse(exit_code: int, stdout: str, output: str) -> AuditRun:
    try:
        report = json.loads(stdout)
    except json.JSONDecodeError:
        raise AssertionError(
            f"the audit printed no JSON report (exit {exit_code}):\n{output[-3000:]}"
        ) from None
    entries = [entry for entry in report.get("verdicts", []) if entry.get("gate") == AUDIT_GATE]
    if len(entries) != 1:
        raise AssertionError(f"expected one {AUDIT_GATE} verdict, found {len(entries)}:\n{stdout}")
    (entry,) = entries
    return AuditRun(
        exit_code=exit_code,
        output=output,
        passed=bool(entry["passed"]),
        reason=entry.get("reason", ""),
        unselected=frozenset((test, read) for test, read in entry.get("unselected", ())),
        notes=tuple(entry.get("notes", ())),
    )


# -- Reading what the verdict says about copies --------------------------------------------------

_ABOUT_COPIES = re.compile(r"\bcop(?:y|ies|ied|ying)\b", re.IGNORECASE)
_NOT_AUDITED = re.compile(r"\bnot audited\b|\bunaudited\b", re.IGNORECASE)
_NONE = re.compile(r"\b0\b|\bno\b|\bnone\b", re.IGNORECASE)
_NUMBER = re.compile(r"\d[\d,]*")


def copy_notes(run: AuditRun) -> str:
    """Every note that speaks of copies, joined: what the verdict says the copy rule set aside."""
    return " | ".join(note for note in run.notes if _ABOUT_COPIES.search(note))


def numbers_in(text: str) -> set[int]:
    return {int(found.replace(",", "")) for found in _NUMBER.findall(text) if found.strip(",")}


def says_not_audited(text: str) -> bool:
    return bool(_NOT_AUDITED.search(text))


def says_none(text: str) -> bool:
    return bool(_NONE.search(text))
