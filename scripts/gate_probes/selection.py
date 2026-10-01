"""Liveness probe for the test-scope resolver: does it still select the tests that read a file?

The oracle is the suite itself. The probe runs the project's default suite once
under the committed tracer (`tracer/`), which records every repository file each
test file opens for reading, in the test process and in any process a test
starts. Then it asks the resolver, in one `--per-path` call, what a change to
each such file alone selects. A pair `(test file, file it read)` the resolver
does not select is a finding, and nobody had to list it in advance: this is the
check that would have caught the 29 reads the resolver missed in September 2026.

The probe fails, with a reason of the form `expected ...; observed ...`, when:

- the resolver is missing or does not answer `--help` (checked first, in seconds);
- the tracer is shadowed, the suite does not run (pytest exit other than 0 or 1),
  or no reads are recorded at all (a dead tracer must not pass as an empty audit);
- a collected test file never ran under the tracer (no heartbeat);
- the resolver fails, or does not answer for a path (a missing or unparseable
  answer selects nothing: fail closed);
- any audited pair is unselected.

A pair is selected when the file's answer widened, or the root pocket selects
the full suite, or the root pocket lists the test. Exit 1 from the suite (failing
tests) is only a note: the suite's health belongs to other jobs. A failing test's
traceback rendering reads source files, so the audit is meant for a green suite.

Declared limit: first-import credit varies run to run, so reads made by the
import machinery are not audited per test. They belong to the module that was
imported and are covered through the resolver's import graph; the verdict's
notes carry the count of imported repository files left unaudited, so the limit
is visible on every run. Only tracked files are audited, because only a tracked
file can appear in a diff.

`judge`-style functions here are pure; `run` and the helpers under "the edge"
are the only effects. Imports are flat siblings, the layout the mutation sensor
reads. Tests: `scripts/gate_probes/test_selection.py`.
"""

from __future__ import annotations

import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from collections.abc import Iterable, Mapping
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

import gate_probes
from gate_probes.verdict import GateId, Verdict

RESOLVER = "scripts/resolve_test_scope.py"
# Found beside the package, not beside this file: the mutation sensor runs a flat copy of the latter.
TRACER_DIR = Path(gate_probes.__file__).resolve().parent / "tracer"

DIRECT, CHILD, IMPORT = "direct", "child", "import"
CHANNELS = (DIRECT, CHILD, IMPORT)

RESOLVER_SCHEMA = 2
ROOT_POCKET_ROOTS = (".", "")
NO_ROOT_POCKET = "absent"
SELECTS_FULL = "full"

# The CLI gives this probe 900 s; the three effects below leave headroom for the rest.
PREFLIGHT_TIMEOUT_S = 30.0
SUITE_TIMEOUT_S = 600.0
RESOLVER_TIMEOUT_S = 240.0
RESOLVER_PROCESSES = min(8, os.cpu_count() or 1)
SUITE_EXIT_CODES = (0, 1)  # 1 = failing tests, a note; anything else means the suite did not run

_TAIL_CHARS = 300
_NAMED_FILES = 5

Pair = tuple[str, str]  # (test file, repository file it read)


class ProbeError(Exception):
    """The audit cannot be trusted; the message is the verdict's `expected ...; observed ...`."""


@dataclass(frozen=True)
class ObservedReads:
    """Everything the tracer saw, parsed once; nothing downstream touches a raw record."""

    pairs_by_channel: Mapping[str, frozenset[Pair]]
    heartbeats: frozenset[str]  # test files that ran under the tracer
    collected: frozenset[str]  # test files the suite collected

    def verdict_pairs(self) -> frozenset[Pair]:
        """The pairs worth auditing: direct reads and reads by a child process."""
        return self.pairs_by_channel[DIRECT] | self.pairs_by_channel[CHILD]


@dataclass(frozen=True)
class Answer:
    """What the resolver said a change to one file selects, reduced to the root pocket."""

    widened: bool
    root_selection: str
    tests: frozenset[str]

    def selects(self, test: str) -> bool:
        return self.widened or self.root_selection == SELECTS_FULL or test in self.tests


def run(repo_root: Path, env: Mapping[str, str]) -> Verdict:
    started = time.monotonic()
    try:
        unselected, notes = _audit(repo_root, env)
    except ProbeError as failure:
        return Verdict(
            gate=GateId.SELECTION_AUDIT,
            passed=False,
            reason=str(failure),
            elapsed_s=time.monotonic() - started,
        )
    return verdict_from(unselected, notes, time.monotonic() - started)


def _audit(repo_root: Path, env: Mapping[str, str]) -> tuple[tuple[Pair, ...], tuple[str, ...]]:
    _check_resolver(repo_root, env)
    tracked = _tracked_files(repo_root)
    canary = canary_pair(tracked)
    if canary is not None:
        missed, note = _resolver_canary(repo_root, env, canary)
        if missed:
            return missed, (note,)
    observed, suite_notes = _traced_suite(repo_root, env)
    reason = dead_tracer_reason(observed)
    if reason is not None:
        raise ProbeError(reason)
    pairs = checked_pairs(observed, tracked)
    if not pairs:
        raise ProbeError(_failure("tests to read tracked repository files", "none did"))
    answers = _ask_resolver(repo_root, env, sorted({read for _, read in pairs}))
    return find_unselected(pairs, answers), (*suite_notes, import_note(observed, tracked))


# -- the pure judge ----------------------------------------------------------------


def verdict_from(unselected: tuple[Pair, ...], notes: tuple[str, ...], elapsed_s: float) -> Verdict:
    if not unselected:
        return Verdict(
            gate=GateId.SELECTION_AUDIT, passed=True, reason="", elapsed_s=elapsed_s, notes=notes
        )
    test, read = unselected[0]
    reason = _failure(
        "a change to every file a test read to select that test",
        f"{len(unselected)} reads unselected, first: {test} reads {read}",
    )
    return Verdict(
        gate=GateId.SELECTION_AUDIT,
        passed=False,
        reason=reason,
        elapsed_s=elapsed_s,
        unselected=unselected,
        notes=notes,
    )


def dead_tracer_reason(observed: ObservedReads) -> str | None:
    """Why the trace cannot support an audit; None when it can."""
    if not observed.verdict_pairs():
        return _failure(
            "the traced run to record direct or child reads of repository files",
            "no such reads (empty trace)",
        )
    missing = sorted(observed.collected - observed.heartbeats)
    if missing:
        named = ", ".join(missing[:_NAMED_FILES]) + (", ..." if len(missing) > _NAMED_FILES else "")
        return _failure(
            "every collected test file to run under the tracer",
            f"{len(missing)} without a heartbeat: {named}",
        )
    return None


def checked_pairs(observed: ObservedReads, tracked: frozenset[str]) -> tuple[Pair, ...]:
    """The audited pairs: direct and child reads of tracked files, sorted."""
    return tuple(sorted(pair for pair in observed.verdict_pairs() if pair[1] in tracked))


CANARY_DIR = "scripts/"


def canary_pair(tracked: frozenset[str]) -> Pair | None:
    """A pair the resolver selects whatever the suite reads, or None when the checkout has none.

    The first co-located `scripts/test_<name>.py` beside its `scripts/<name>.py`: a layout
    edge, the resolver's most basic one. Asking about it costs one resolver call, so a dead
    resolver fails the audit in seconds instead of after a traced run of the whole suite.
    """
    for path in sorted(tracked):
        if not path.startswith(CANARY_DIR):
            continue
        head, _, name = path.rpartition("/")
        if name.startswith("test_") and name.endswith(".py"):
            source = f"{head}/{name[len('test_') :]}"
            if source in tracked:
                return (path, source)
    return None


def find_unselected(pairs: Iterable[Pair], answers: Mapping[str, Answer]) -> tuple[Pair, ...]:
    """The pairs whose file's answer does not select the test; no answer selects nothing."""
    return tuple(sorted(pair for pair in set(pairs) if not _selected(pair, answers)))


def _selected(pair: Pair, answers: Mapping[str, Answer]) -> bool:
    test, read = pair
    answer = answers.get(read)
    return answer is not None and answer.selects(test)


def import_note(observed: ObservedReads, tracked: frozenset[str]) -> str:
    """The declared limit, with its size: imported files that no direct or child read audits."""
    audited = {read for _, read in observed.verdict_pairs()}
    imported = {read for _, read in observed.pairs_by_channel[IMPORT] if read in tracked}
    return (
        f"{len(imported - audited)} imported repository files are not audited per test "
        "(first-import credit varies run to run; covered through the resolver's import graph)"
    )


# -- parsing -------------------------------------------------------------------------


def parse_records(lines: Iterable[str]) -> ObservedReads:
    """The tracer's JSON Lines as `ObservedReads`; a line it cannot read is a ValueError."""
    pairs: dict[str, set[Pair]] = {channel: set() for channel in CHANNELS}
    heartbeats: set[str] = set()
    collected: set[str] = set()
    for line in lines:
        if not line.strip():
            continue
        match _json_value(line):
            case {"t": str() as test, "p": str() as read, "c": str() as channel} if (
                channel in pairs
            ):
                pairs[channel].add((test, read))
            case {"heartbeat": str() as test}:
                heartbeats.add(test)
            case {"collected": [*files]} if all(isinstance(name, str) for name in files):
                collected.update(files)
            case _:
                raise ValueError(f"unrecognised trace record: {line.strip()[:_TAIL_CHARS]!r}")
    return ObservedReads(
        pairs_by_channel={channel: frozenset(found) for channel, found in pairs.items()},
        heartbeats=frozenset(heartbeats),
        collected=frozenset(collected),
    )


def parse_answers(stdout: str) -> dict[str, Answer]:
    """The resolver's per-path lines keyed by changed path; a line that is not an answer is dropped."""
    answers: dict[str, Answer] = {}
    for line in stdout.splitlines():
        parsed = _parse_answer(line)
        if parsed is not None:
            answers[parsed[0]] = parsed[1]
    return answers


def _parse_answer(line: str) -> tuple[str, Answer] | None:
    payload = _json_value(line)
    if not isinstance(payload, dict) or payload.get("schema") != RESOLVER_SCHEMA:
        return None
    changed, widen, pockets = payload.get("changed"), payload.get("widen"), payload.get("pockets")
    paths = changed.get("paths") if isinstance(changed, dict) else None
    if not (isinstance(paths, list) and len(paths) == 1 and isinstance(paths[0], str)):
        return None
    if not (isinstance(widen, list) and isinstance(pockets, list)):
        return None
    root_selection, tests = _root_pocket(pockets)
    return paths[0], Answer(widened=bool(widen), root_selection=root_selection, tests=tests)


def _root_pocket(pockets: list[object]) -> tuple[str, frozenset[str]]:
    for pocket in pockets:
        if isinstance(pocket, dict) and pocket.get("root") in ROOT_POCKET_ROOTS:
            listed = pocket.get("tests")
            entries = listed if isinstance(listed, list) else []
            tests = {
                t["path"] for t in entries if isinstance(t, dict) and isinstance(t.get("path"), str)
            }
            return str(pocket.get("selection")), frozenset(tests)
    return NO_ROOT_POCKET, frozenset()


def _json_value(line: str) -> object:
    try:
        return json.loads(line)
    except json.JSONDecodeError:
        return None


# -- the edge: processes and files ----------------------------------------------------


def _resolver_canary(
    repo_root: Path, env: Mapping[str, str], canary: Pair
) -> tuple[tuple[Pair, ...], str]:
    """The canary pair as unselected when the resolver does not select it, with the reason.

    A resolver that crashes, answers nothing or answers garbage selects nothing, which is
    exactly the dead gate this audit exists to catch.
    """
    test, read = canary
    try:
        answers = _ask_resolver(repo_root, env, [read])
    except ProbeError as failure:
        return (canary,), f"resolver canary: changing {read} must select {test}; {failure}"
    missed = find_unselected([canary], answers)
    note = f"resolver canary: changing {read} must select {test}; it did not, so the suite was not traced"
    return missed, note


def _check_resolver(repo_root: Path, env: Mapping[str, str]) -> None:
    """Fail in seconds, before any tracing, when the gate under audit is absent or dead."""
    resolver = repo_root / RESOLVER
    if not resolver.is_file():
        raise ProbeError(_failure(f"{RESOLVER} in the checkout", "it is missing"))
    done = _capture(
        [sys.executable, str(resolver), "--help"],
        repo_root,
        env,
        PREFLIGHT_TIMEOUT_S,
        f"`{RESOLVER} --help`",
    )
    if done.returncode != 0:
        raise ProbeError(
            _failure(
                f"`{RESOLVER} --help` to exit 0",
                f"exit code {done.returncode}: {_tail(done.stderr)}",
            )
        )


def _traced_suite(repo_root: Path, env: Mapping[str, str]) -> tuple[ObservedReads, tuple[str, ...]]:
    out_dir = Path(tempfile.mkdtemp(prefix="gate-liveness-trace-"))
    try:
        traced = _traced_env(env, repo_root, out_dir)
        _check_tracer_loads(repo_root, traced)
        argv = [
            sys.executable, "-m", "pytest", "--no-cov", "-p", "no:cacheprovider",
            "-p", "selection_trace_plugin", "--continue-on-collection-errors",
        ]  # fmt: skip
        done = _capture(argv, repo_root, traced, SUITE_TIMEOUT_S, "the traced default suite")
        if done.returncode not in SUITE_EXIT_CODES:
            observed = f"pytest exit code {done.returncode}: {_tail(done.stderr or done.stdout)}"
            raise ProbeError(_failure("the default suite to run under the tracer", observed))
        return _read_trace(out_dir), _suite_notes(done.returncode, done.stdout)
    finally:
        shutil.rmtree(out_dir, ignore_errors=True)


def _traced_env(env: Mapping[str, str], repo_root: Path, out_dir: Path) -> dict[str, str]:
    traced = {key: value for key, value in env.items() if not key.startswith("PX_TRACE_")}
    inherited = traced.get("PYTHONPATH")
    traced["PYTHONPATH"] = os.pathsep.join([str(TRACER_DIR), *([inherited] if inherited else [])])
    traced["PYTHONDONTWRITEBYTECODE"] = (
        "1"  # else the tracer's own modules leave bytecode in the tree
    )
    traced["PX_TRACE_ROOT"] = str(repo_root)
    traced["PX_TRACE_OUT"] = str(out_dir)
    return traced


def _check_tracer_loads(repo_root: Path, traced: Mapping[str, str]) -> None:
    """The interpreter must start our `sitecustomize`, not another one earlier on its path."""
    code = "import os, sitecustomize; print(os.path.realpath(sitecustomize.__file__))"
    done = _capture(
        [sys.executable, "-c", code], repo_root, traced, PREFLIGHT_TIMEOUT_S, "the tracer probe"
    )
    ours = os.path.realpath(TRACER_DIR / "sitecustomize.py")
    loaded = done.stdout.strip() if done.returncode == 0 else _tail(done.stderr)
    if loaded != ours:
        raise ProbeError(_failure(f"the tracer's sitecustomize ({ours}) to load first", loaded))


def _read_trace(out_dir: Path) -> ObservedReads:
    lines = (
        line
        for path in sorted(out_dir.glob("trace-*.jsonl"))
        for line in path.read_text().splitlines()
    )
    try:
        return parse_records(lines)
    except ValueError as exc:
        raise ProbeError(_failure("readable trace records", str(exc))) from exc


def _suite_notes(exit_code: int, stdout: str) -> tuple[str, ...]:
    notes: list[str] = []
    if exit_code == 1:
        notes.append("the suite exited 1 (failing tests); its health belongs to other jobs")
    uncollected = collection_errors(stdout)
    if uncollected:
        named = ", ".join(uncollected[:_NAMED_FILES])
        notes.append(
            f"{len(uncollected)} test file(s) failed to collect, so their reads were not audited: {named}"
        )
    return tuple(notes)


def collection_errors(stdout: str) -> tuple[str, ...]:
    """The test files pytest's short summary reports as `ERROR <file>` collection errors, sorted.

    The suite runs with `--continue-on-collection-errors`: one file that cannot be imported
    must not hide the reads of every other test, but it must stay visible in the verdict.
    """
    files = set()
    for line in stdout.splitlines():
        if line.startswith("ERROR ") and " - " in line:
            target = line[len("ERROR ") :].split(" - ", 1)[0].strip()
            if "::" not in target:
                files.add(target)
    return tuple(sorted(files))


def _tracked_files(repo_root: Path) -> frozenset[str]:
    done = _capture(
        ["git", "-C", str(repo_root), "ls-files", "-z"],
        repo_root,
        os.environ,
        PREFLIGHT_TIMEOUT_S,
        "`git ls-files`",
    )
    if done.returncode != 0:
        raise ProbeError(_failure("`git ls-files` to list tracked files", _tail(done.stderr)))
    return frozenset(name for name in done.stdout.split("\0") if name)


def spread(reads: list[str], ways: int) -> list[list[str]]:
    """`reads` dealt round-robin into at most `ways` non-empty chunks, each still sorted."""
    return [chunk for chunk in (reads[start::ways] for start in range(ways)) if chunk]


def _ask_resolver(repo_root: Path, env: Mapping[str, str], reads: list[str]) -> dict[str, Answer]:
    """One resolver process per chunk of reads, concurrently.

    A path's answer depends on that path alone (the resolver's `--per-path` lines are
    pinned equal to single-path calls), so chunking cannot change an answer; it only
    divides the per-path derivation, the cost that grows with the suite, across cores.
    """
    chunks = spread(reads, RESOLVER_PROCESSES)
    with ThreadPoolExecutor(max_workers=len(chunks)) as pool:
        stdouts = list(pool.map(lambda chunk: _resolve_chunk(repo_root, env, chunk), chunks))
    return parse_answers("\n".join(stdouts))


def _resolve_chunk(repo_root: Path, env: Mapping[str, str], reads: list[str]) -> str:
    argv = [
        sys.executable, str(repo_root / RESOLVER), "--repo-root", str(repo_root),
        "--json", "--per-path", "--changed", *reads,
    ]  # fmt: skip
    done = _capture(argv, repo_root, env, RESOLVER_TIMEOUT_S, f"`{RESOLVER}`")
    if done.returncode != 0:
        raise ProbeError(
            _failure(
                f"the resolver to answer for {len(reads)} read files",
                f"exit code {done.returncode}: {_tail(done.stderr)}",
            )
        )
    return done.stdout


def _capture(
    argv: list[str], cwd: Path, env: Mapping[str, str], timeout: float, what: str
) -> subprocess.CompletedProcess[str]:
    """Run `argv` (described as `what`) in its own process group; on timeout kill the group and fail."""
    try:
        child = subprocess.Popen(
            argv, cwd=cwd, env=dict(env), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, start_new_session=True,
        )  # fmt: skip
    except OSError as exc:
        raise ProbeError(_failure(f"{what} to start", f"{type(exc).__name__}: {exc}")) from exc
    try:
        stdout, stderr = child.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        os.killpg(child.pid, signal.SIGKILL)
        child.communicate()
        raise ProbeError(
            _failure(f"{what} to finish within {timeout:g} s", "it was still running")
        ) from None
    return subprocess.CompletedProcess(argv, child.returncode, stdout, stderr)


def _failure(expected: str, observed: str) -> str:
    return f"expected {expected}; observed {observed}"


def _tail(text: str) -> str:
    """The last non-empty line of `text`, bounded: the exception line, not the traceback."""
    lines = [line.strip() for line in text.strip().splitlines() if line.strip()]
    return lines[-1][:_TAIL_CHARS] if lines else "no output"
