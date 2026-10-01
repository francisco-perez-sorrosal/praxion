#!/usr/bin/env python3
"""Footprint criteria check: does a change that moves a footprint carry a measured bound?

    check_footprint_criteria.py <slug> [--stage spec|plan|verify] [--paths PATH ...]
            [--base-ref REF] [--repo-root DIR] [--json]

The grammars of the spec tables, the registry and the measurement log, the
finding table and the stages are specified once, in the docstring of
`_footprint_grammar.py`, which also holds the parsers. This docstring specifies
the command that runs them.

CLI. `--stage` defaults to `verify`. `--paths` is required for `plan` and
rejected for the other stages. `--base-ref` is used only by `verify`; its default
is `git merge-base HEAD main`, and when that cannot be resolved the command exits
2 and asks for `--base-ref`; an inactive check never resolves a base. The repository root is `--repo-root`, else the git
toplevel of the working directory; it is never derived from this file's
location, because managed projects run the command through a `~/.local/bin`
symlink where that location is the plugin. The command reads
`.ai-work/<slug>/SYSTEMS_PLAN.md` (required), `.ai-state/FOOTPRINTS.md` and
`.ai-work/<slug>/MEASUREMENTS.md` (both if present). It runs only `git diff`,
`git ls-files`, `git rev-parse` and `git merge-base`, and never executes a
command named in a table or the registry.

Exit codes: `0` no `fail` finding (the inactive case included, whatever `--base-ref` says);`1` at least one
`fail` finding; `2` input error (bad arguments, the plan missing or without
`## Acceptance Criteria`, the base unresolvable); stderr names the input.

`--json` prints on stdout
`{"schema": 1, "slug", "stage", "active", "registry", "base_ref", "moved":
[{"footprint", "paths"}], "criteria", "not_measured", "measurements", "findings":
[{"code", "severity", "footprint", "criterion", "reason", "message"}]}`.
`active` is false exactly when there is no registry and the spec has neither
table.

Stdlib-only and Python 3.9-safe, like its private siblings. The judge is pure (every
input is a parameter) and sits above the edge, which alone reads files and runs git.
Tests: `scripts/test_check_footprint_criteria_judge.py` (judge),
`scripts/test_check_footprint_criteria.py` (edge and command).
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import posixpath
import re
import shlex
import subprocess
import sys
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path

from _footprint_grammar import (
    ACCEPTANCE_HEADING,
    FAIL,
    STAGES,
    Against,
    Baseline,
    Criterion,
    Finding,
    Footprint,
    LogParse,
    Measured,
    Measurement,
    NoReading,
    NoRegistry,
    Registry,
    RegistryParse,
    SpecTables,
    footprint_key,
    latest,
    make_finding,
    parse_measurements,
    parse_registry,
    parse_spec_tables,
)
from _markdown_tables import find_section, split_lines

PROG = "check_footprint_criteria.py"
SCHEMA_VERSION = 1
STATE_DIR_PREFIX = ".ai-state/"
PATHS_SHOWN_IN_A_MESSAGE = 5
EXIT_OK, EXIT_FAIL, EXIT_INPUT_ERROR = 0, 1, 2
DEFAULT_BASE_BRANCH = "main"
REGISTRY_PATH = ".ai-state/FOOTPRINTS.md"
PLAN_NAME, LOG_NAME = "SYSTEMS_PLAN.md", "MEASUREMENTS.md"
_FRESHNESS_FALLBACK = f"any tracked change outside {STATE_DIR_PREFIX} stales it"
_DECLARED_FALLBACK = "it is declared not measured, and nothing can show a change moved it"
_SLUG = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]*")


class InputError(Exception):
    """Bad input: the message goes to stderr and the exit code is 2."""


# --- the command: gather the world, judge it, report ----------------------------------------


@dataclass(frozen=True)
class Report:
    slug: str
    stage: str
    active: bool
    registry_present: bool
    base_ref: str | None
    moved: tuple[Moved, ...]
    spec: SpecTables
    measurements: tuple[Measurement, ...]  # the authoritative row per criterion and phase
    findings: tuple[Finding, ...]


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        report = run(args)
    except InputError as error:
        print(f"{PROG}: {error}", file=sys.stderr)
        return EXIT_INPUT_ERROR
    print(render_json(report) if args.json else render_text(report))
    return EXIT_FAIL if any(f.severity == FAIL for f in report.findings) else EXIT_OK


def run(args: argparse.Namespace) -> Report:
    """Gather every input at the edge, hand them to the pure judge, and keep what the report needs."""
    root = repo_root(args.repo_root)
    spec = parse_spec_tables(read_plan(root, args.slug))
    registry = parse_registry(read_optional(root / REGISTRY_PATH))
    tracked = tracked_files(root)
    # Decide `active` first: an inactive check reads nothing else, so a stale base cannot fail it.
    verifying = args.stage == "verify" and is_active(registry.registry, spec)
    base_ref = resolve_base_ref(root, args.base_ref) if verifying else None
    log = _read_log(root, args.slug) if verifying else LogParse((), ())
    moved_paths = _moved_paths(root, args, base_ref)
    diffs = read_diffs(root, base_ref, log) if base_ref is not None else Diffs({}, {})
    findings = judge(args.stage, spec, registry, log, moved_paths, diffs, tracked)
    return Report(
        slug=args.slug,
        stage=args.stage,
        active=is_active(registry.registry, spec),
        registry_present=not isinstance(registry.registry, NoRegistry),
        base_ref=base_ref,
        moved=moved_footprints(registry.registry, moved_paths),
        spec=spec,
        measurements=tuple(latest(log.measurements).values()),
        findings=findings,
    )


def _moved_paths(root: Path, args: argparse.Namespace, base_ref: str | None) -> tuple[str, ...]:
    if base_ref is not None:
        return tuple(sorted(changed_paths(root, base_ref)))
    return tuple(args.paths or ())


def _read_log(root: Path, slug: str) -> LogParse:
    text = read_optional(root / ".ai-work" / slug / LOG_NAME)
    return parse_measurements(text) if text is not None else LogParse((), ())


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog=PROG, description="Does a change that moves a footprint carry a measured bound?"
    )
    parser.add_argument("slug", help="task slug: reads .ai-work/<slug>/")
    parser.add_argument("--stage", choices=STAGES, default="verify")
    parser.add_argument("--paths", nargs="+", metavar="PATH", help="repo-relative; plan stage only")
    parser.add_argument(
        "--base-ref", help=f"verify stage; default: merge-base HEAD {DEFAULT_BASE_BRANCH}"
    )
    parser.add_argument("--repo-root", help="default: the git toplevel of the working directory")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    if not _SLUG.fullmatch(args.slug):
        parser.error(f"slug {args.slug!r} is not a plain task slug")
    if (args.stage == "plan") != (args.paths is not None):
        parser.error("--paths is required for --stage plan and rejected for the other stages")
    if args.paths is not None:
        args.paths = [_relative_posix(parser, path) for path in args.paths]
    return args


def _relative_posix(parser: argparse.ArgumentParser, path: str) -> str:
    normal = posixpath.normpath(path)
    if posixpath.isabs(normal) or normal == ".." or normal.startswith("../"):
        parser.error(
            f"--paths entry {path!r} must be a path inside the repository, relative to its root"
        )
    return normal


# --- the pure judge: every input is a parameter; no I/O, no git ------------------------------


@dataclass(frozen=True)
class Moved:
    """A registry footprint that the changed paths touch, and the paths that touch it."""

    footprint: str
    paths: tuple[str, ...]


@dataclass(frozen=True)
class Diffs:
    """What changed, as the edge read it from git. A head missing from a map is one git could not resolve.

    `since_head[h]` is the paths changed between commit h and the working tree
    (uncommitted and untracked work included); `base_to_head[h]` is the paths
    changed between the base and commit h.
    """

    since_head: Mapping[str, frozenset[str]]
    base_to_head: Mapping[str, frozenset[str]]


def judge(
    stage: str,
    spec: SpecTables,
    registry: RegistryParse,
    log: LogParse,
    moved_paths: tuple[str, ...],
    diffs: Diffs,
    tracked_files: tuple[str, ...],
) -> tuple[Finding, ...]:
    """Every finding of one stage, parser findings included: the single list the command reports."""
    if not is_active(registry.registry, spec):
        return ()
    findings = [*spec.findings, *registry.findings]
    findings += _dead_glob_findings(registry.registry, tracked_files)
    findings += _unregistered(registry.registry, spec)
    if stage in ("plan", "verify"):
        findings += _unbounded(registry.registry, spec, moved_paths)
    if stage == "verify":
        findings += log.findings
        findings += _measurement_findings(spec, registry.registry, log.measurements, diffs)
    return tuple(findings)


def is_active(registry: Registry | NoRegistry, spec: SpecTables) -> bool:
    """False exactly when there is no registry and the spec has neither table, not even a broken one."""
    spec_is_empty = not (spec.criteria or spec.not_measured or spec.findings)
    return not (isinstance(registry, NoRegistry) and spec_is_empty)


def glob_match(glob: str, path: str) -> bool:
    """`fnmatch` over a repo-relative POSIX path, where `*` crosses `/`."""
    return fnmatch.fnmatchcase(path, glob)


def footprint_paths(
    footprint: Footprint, paths: tuple[str, ...] | frozenset[str]
) -> tuple[str, ...]:
    """The paths a footprint covers: some include glob matches and no exclude glob does."""
    return tuple(
        sorted(
            path
            for path in paths
            if any(glob_match(g, path) for g in footprint.include_globs)
            and not any(glob_match(g, path) for g in footprint.exclude_globs)
        )
    )


def moved_footprints(
    registry: Registry | NoRegistry, paths: tuple[str, ...] | frozenset[str]
) -> tuple[Moved, ...]:
    """The registry footprints that `paths` touch, each with its matching paths."""
    moved = [Moved(fp.name, footprint_paths(fp, paths)) for fp in _footprints(registry)]
    return tuple(m for m in moved if m.paths)


def dead_globs(
    registry: Registry | NoRegistry, tracked_files: tuple[str, ...]
) -> tuple[tuple[str, str], ...]:
    """The (footprint, include glob) pairs that match no tracked file."""
    return tuple(
        (fp.name, glob)
        for fp in _footprints(registry)
        for glob in fp.include_globs
        if not any(glob_match(glob, tracked) for tracked in tracked_files)
    )


# --- registry and spec findings -------------------------------------------------------------


def _footprints(registry: Registry | NoRegistry) -> tuple[Footprint, ...]:
    return registry.footprints if isinstance(registry, Registry) else ()


def _registered(registry: Registry | NoRegistry, name: str) -> Footprint | None:
    wanted = footprint_key(name)
    return next((fp for fp in _footprints(registry) if footprint_key(fp.name) == wanted), None)


def _dead_glob_findings(registry: Registry | NoRegistry, tracked: tuple[str, ...]) -> list[Finding]:
    return [
        make_finding(
            "FP05",
            "dead-glob",
            f"{name}: the include glob {glob!r} matches no tracked file",
            footprint=name,
        )  # fmt: skip
        for name, glob in dead_globs(registry, tracked)
    ]


def _unregistered(registry: Registry | NoRegistry, spec: SpecTables) -> list[Finding]:
    """A spec footprint with no registry row: freshness falls back to any tracked change."""
    # A bounded footprint is measured, so the fallback is a freshness rule; a declared one is
    # never measured, so what it loses is the means to see a change move it.
    bounded = [(c.footprint, _FRESHNESS_FALLBACK) for c in spec.criteria]
    declared = [(n.footprint, _DECLARED_FALLBACK) for n in spec.not_measured]
    why = (
        "there is no registry" if isinstance(registry, NoRegistry) else "it is not in the registry"
    )
    found, seen = [], set()
    for name, consequence in bounded + declared:
        key = footprint_key(name)
        if key in seen or _registered(registry, name) is not None:
            continue
        seen.add(key)
        message = f"{name}: {why}, so {consequence}"
        found.append(make_finding("FP04", "unregistered", message, footprint=name))
    return found


def _unbounded(
    registry: Registry | NoRegistry, spec: SpecTables, moved_paths: tuple[str, ...]
) -> list[Finding]:
    """A moved registry footprint that has neither a criterion nor a not-measured row."""
    covered = {footprint_key(c.footprint) for c in spec.criteria}
    covered |= {footprint_key(n.footprint) for n in spec.not_measured}
    return [
        make_finding(
            "FP01",
            "unbounded",
            f"{m.footprint}: moved by {_names(m.paths)}, with no criterion and no not-measured row",
            footprint=m.footprint,
        )  # fmt: skip
        for m in moved_footprints(registry, moved_paths)
        if footprint_key(m.footprint) not in covered
    ]


# --- measurement findings (verify) ----------------------------------------------------------


def _measurement_findings(
    spec: SpecTables,
    registry: Registry | NoRegistry,
    measurements: tuple[Measurement, ...],
    diffs: Diffs,
) -> list[Finding]:
    rows = latest(measurements)
    known = {c.id for c in spec.criteria}
    found = [
        make_finding(
            "FP02",
            "unknown-criterion",
            f"log row names {criterion}, which is no spec criterion",
            criterion=criterion,
        )  # fmt: skip
        for criterion in dict.fromkeys(m.criterion for m in measurements)
        if criterion not in known
    ]
    for criterion in spec.criteria:
        baseline = rows.get((criterion.id, "baseline"))
        final = rows.get((criterion.id, "final"))
        footprint = _registered(registry, criterion.footprint)
        found += _criterion_findings(criterion, baseline, final, footprint, diffs)
    return found


def _criterion_findings(
    criterion: Criterion,
    baseline: Measurement | None,
    final: Measurement | None,
    footprint: Footprint | None,
    diffs: Diffs,
) -> list[Finding]:
    """The FP03 findings of one criterion. A baseline row is judged only when the criterion needs one."""
    needs_baseline = isinstance(criterion.against, Baseline)
    baseline = baseline if needs_baseline else None
    found = []
    if final is None:
        found.append(_unmeasured(criterion, "missing-final", "has no final measurement row"))
    if needs_baseline and baseline is None:
        found.append(_unmeasured(criterion, "missing-baseline", "has no baseline measurement row"))
    for row in (baseline, final):
        if row is not None:
            found += _row_defects(criterion, row)
    if baseline is not None and final is not None:
        found += _incomparable(criterion, baseline, final)
    if final is not None:
        found += _stale(criterion, final, footprint, diffs)
    if baseline is not None and footprint is not None:
        found += _late(criterion, baseline, footprint, diffs)
    return found


def _row_defects(criterion: Criterion, row: Measurement) -> list[Finding]:
    found = []
    if isinstance(row.reading, NoReading):
        found.append(
            _unmeasured(
                criterion, "no-reading", f"{row.phase} reading withheld: {row.reading.reason}"
            )
        )
    if not _same_instrument(criterion.command, row.command):
        message = (
            f"{row.phase} row ran {row.command!r}, which is not {criterion.command!r} "
            "with options added"
        )
        found.append(_unmeasured(criterion, "wrong-command", message))
    return found


def _same_instrument(criterion_command: str, logged_command: str) -> bool:
    """The logged command is the criterion's command plus options and their values, nothing else.

    A bare positional after the criterion's tokens (a test path, say) narrows the run to a
    different instrument. A single-dash token is a flag and takes no value, so `-q tests/x.py`
    narrows; a `--name` may take the one value after it, and the criterion's own trailing
    `--name` counts, so `--compare-ref` followed by a sha is the same instrument.
    Placeholders in the criterion (`<name>`, trailing `<name...>`) match what the author
    declared variable, and a logged placeholder means the command was never filled in.
    """
    wanted, ran = _tokens(criterion_command), _tokens(logged_command)
    if any(_PLACEHOLDER.fullmatch(token) for token in ran):
        return False  # a logged placeholder was never filled in, so nothing was run
    consumed = _match_template(wanted, ran)
    if consumed is None:
        return False
    if consumed == len(ran) and wanted and _REST_PLACEHOLDER.fullmatch(wanted[-1]):
        return True
    takes_value = bool(wanted) and _is_long_option(wanted[-1])
    for token in ran[consumed:]:
        if token.startswith("-"):
            takes_value = _is_long_option(token)
        elif takes_value:
            takes_value = False
        else:
            return False
    return True


# A criterion command may declare where a run varies: `<name>` stands for exactly one
# token and a trailing `<name...>` for one or more, so a wrapper (`/usr/bin/time -p
# <command...>`) or an option value (`-m <marker>`) can be bounded without letting an
# undeclared token through.
_PLACEHOLDER = re.compile(r"<[a-z][a-z0-9-]*(\.\.\.)?>")
_REST_PLACEHOLDER = re.compile(r"<[a-z][a-z0-9-]*\.\.\.>")


def _match_template(wanted: list[str], ran: list[str]) -> int | None:
    """How many logged tokens the criterion's tokens consume, or None on a mismatch."""
    for index, token in enumerate(wanted):
        if _REST_PLACEHOLDER.fullmatch(token):
            is_last = index == len(wanted) - 1
            return len(ran) if is_last and len(ran) > index else None
        if index >= len(ran):
            return None
        if not _PLACEHOLDER.fullmatch(token) and ran[index] != token:
            return None
    return len(wanted)


def _is_long_option(token: str) -> bool:
    """`--name` may be followed by its value; `--name=value` carries its own."""
    return token.startswith("--") and "=" not in token


def _tokens(command: str) -> list[str]:
    try:
        return shlex.split(command)
    except ValueError:  # an unbalanced quote: whitespace split, which cannot match a clean twin
        return command.split()


def _incomparable(criterion: Criterion, baseline: Measurement, final: Measurement) -> list[Finding]:
    withheld = isinstance(baseline.reading, NoReading) or isinstance(final.reading, NoReading)
    if withheld or type(baseline.reading) is type(final.reading):
        return []
    kinds = (
        f"{type(baseline.reading).__name__.lower()} against {type(final.reading).__name__.lower()}"
    )
    return [
        _unmeasured(
            criterion, "incomparable", f"baseline and final differ in reading kind: {kinds}"
        )
    ]


def _stale(
    criterion: Criterion, final: Measurement, footprint: Footprint | None, diffs: Diffs
) -> list[Finding]:
    changed = diffs.since_head.get(final.head)
    if changed is None:
        message = f"final head {final.head} is not a commit git can resolve, so the reading cannot be shown current"
        return [_unmeasured(criterion, "stale-final", message)]
    touched = _touched(footprint, changed)
    if not touched:
        return []
    message = f"changed after the final row's head {final.head}: {_names(touched)}"
    return [_unmeasured(criterion, "stale-final", message)]


def _late(
    criterion: Criterion, baseline: Measurement, footprint: Footprint, diffs: Diffs
) -> list[Finding]:
    changed = diffs.base_to_head.get(baseline.head)
    if changed is None:
        message = f"baseline head {baseline.head} is not a commit git can resolve, so its timing is unknown"
        return [_unmeasured(criterion, "late-baseline", message)]
    touched = footprint_paths(footprint, changed)
    if not touched:
        return []
    message = f"changed before the baseline row's head {baseline.head}: {_names(touched)}"
    return [_unmeasured(criterion, "late-baseline", message)]


def _touched(footprint: Footprint | None, changed: frozenset[str]) -> tuple[str, ...]:
    """A registered footprint is touched through its paths; an unregistered one by any tracked change."""
    if footprint is not None:
        return footprint_paths(footprint, changed)
    return tuple(sorted(p for p in changed if not p.startswith(STATE_DIR_PREFIX)))


def _unmeasured(criterion: Criterion, reason: str, message: str) -> Finding:
    return make_finding(
        "FP03", reason, f"{criterion.id} {message}",
        footprint=criterion.footprint, criterion=criterion.id,
    )  # fmt: skip


def _names(paths: tuple[str, ...]) -> str:
    shown = ", ".join(paths[:PATHS_SHOWN_IN_A_MESSAGE])
    hidden = len(paths) - PATHS_SHOWN_IN_A_MESSAGE
    return f"{shown} (+{hidden} more)" if hidden > 0 else shown


# --- the edge: the only code that reads files and runs git ----------------------------------
# It runs `git diff`, `git ls-files`, `git rev-parse` and `git merge-base` and nothing else; a
# command named in a table or the registry is data, never executed.


def repo_root(explicit: str | None) -> Path:
    """`--repo-root`, else the git toplevel of the working directory; never this file's location."""
    if explicit is not None:
        root = Path(explicit)
        if not root.is_dir():
            raise InputError(f"--repo-root {explicit!r} is not a directory")
        return root
    top = _git(Path.cwd(), "rev-parse", "--show-toplevel")
    if top.returncode != 0:
        raise InputError("not inside a git repository; run it from the project or pass --repo-root")
    return Path(top.stdout.strip())


def read_plan(root: Path, slug: str) -> str:
    path = root / ".ai-work" / slug / PLAN_NAME
    text = read_optional(path)
    if text is None:
        raise InputError(f"{path} does not exist")
    if find_section(split_lines(text), 2, ACCEPTANCE_HEADING) is None:
        raise InputError(f"{path} has no '## {ACCEPTANCE_HEADING}' section")
    return text


def read_optional(path: Path) -> str | None:
    """The file's text, or None when it does not exist; an unreadable file is an input error."""
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None
    except (OSError, UnicodeDecodeError) as error:
        raise InputError(f"cannot read {path}: {error}") from error


def tracked_files(root: Path) -> tuple[str, ...]:
    return tuple(_git_paths(root, "ls-files", "-z"))


def resolve_base_ref(root: Path, requested: str | None) -> str:
    if requested is not None:
        if requested.startswith("-") or not _is_commit(root, requested):
            raise InputError(f"--base-ref {requested!r} is not a commit in this repository")
        return requested
    merged = _git(root, "merge-base", "HEAD", DEFAULT_BASE_BRANCH)
    if merged.returncode != 0:
        raise InputError(
            f"cannot resolve a default base (git merge-base HEAD {DEFAULT_BASE_BRANCH} failed); "
            "pass --base-ref"
        )
    return merged.stdout.strip()


def changed_paths(root: Path, ref: str) -> frozenset[str]:
    """Paths that differ between commit `ref` and the working tree, new untracked files included.

    Renames are listed as a deletion and an addition, so a file moved out of a
    footprint's paths still counts as moving that footprint.
    """
    diffed = _git_paths(root, "diff", "--name-only", "--no-renames", "-z", ref, "--")
    untracked = _git_paths(root, "ls-files", "-z", "--others", "--exclude-standard")
    return frozenset(diffed).union(untracked)


def read_diffs(root: Path, base_ref: str, log: LogParse) -> Diffs:
    """The paths changed since, and before, each head the log records; unresolvable heads are left out."""
    since_head, base_to_head = {}, {}
    for head in sorted({row.head for row in latest(log.measurements).values()}):
        if _is_commit(root, head):
            since_head[head] = changed_paths(root, head)
            between = _git_paths(
                root, "diff", "--name-only", "--no-renames", "-z", base_ref, head, "--"
            )
            base_to_head[head] = frozenset(between)
    return Diffs(since_head, base_to_head)


def _is_commit(root: Path, ref: str) -> bool:
    return _git(root, "rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}").returncode == 0


def _git_paths(root: Path, *args: str) -> list[str]:
    done = _git(root, *args)
    if done.returncode != 0:
        raise InputError(f"git {' '.join(args)} failed: {done.stderr.strip()}")
    return [path for path in done.stdout.split("\0") if path]


def _git(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, check=False)
    except OSError as error:
        raise InputError(f"cannot run git: {error}") from error


# --- the report ------------------------------------------------------------------------------


def render_text(report: Report) -> str:
    if not report.active:
        return "footprint criteria: inactive (no registry and no footprint table in the spec)"
    lines = [f"{f.severity.upper()} {f.code} {f.reason}: {f.message}" for f in report.findings]
    counts = {
        s: sum(1 for f in report.findings if f.severity == s) for s in ("fail", "warn", "info")
    }
    summary = ", ".join(f"{n} {severity}" for severity, n in counts.items())
    return "\n".join([*lines, f"footprint criteria ({report.stage}): {summary}"])


def render_json(report: Report) -> str:
    envelope = {
        "schema": SCHEMA_VERSION,
        "slug": report.slug,
        "stage": report.stage,
        "active": report.active,
        "registry": report.registry_present,
        "base_ref": report.base_ref,
        "moved": [{"footprint": m.footprint, "paths": list(m.paths)} for m in report.moved],
        "criteria": [_criterion_json(c) for c in report.spec.criteria],
        "not_measured": [asdict(n) for n in report.spec.not_measured],
        "measurements": [_measurement_json(m) for m in report.measurements],
        "findings": [asdict(f) for f in report.findings],
    }
    return json.dumps(envelope, indent=2)


def _criterion_json(criterion: Criterion) -> dict[str, object]:
    return {**asdict(criterion), "against": _against_json(criterion.against)}


def _against_json(against: Against) -> dict[str, str]:
    kind = "baseline" if isinstance(against, Baseline) else "reference"
    return {"kind": kind, "text": against.text}


def _measurement_json(measurement: Measurement) -> dict[str, object]:
    reading = measurement.reading
    if isinstance(reading, NoReading):
        kind, reason = "none", reading.reason
    else:
        kind, reason = ("measured" if isinstance(reading, Measured) else "estimate"), None
    return {**asdict(measurement), "reading": {"kind": kind, "reason": reason}}


if __name__ == "__main__":
    sys.exit(main())
