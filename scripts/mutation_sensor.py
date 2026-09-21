#!/usr/bin/env python3
"""Per-step mutation sensor: names, by function, the tests that would pass with
the code under test broken.

Safety property, mirrored from `resolve_test_scope.py`: **a count that is not
known to be complete must never be published as one.** A wall-clock timeout, a
non-zero `mutmut run`, or two mutmut outputs that disagree with each other are
all refusals -- exit 2, no survivor count -- never a partial or estimated
reading. This is a sensor, not a gate: a completed run always exits 0, however
many mutants survived (there is no exit 1).

    mutation_sensor.py --targets PATH [PATH ...] --tests PATH [PATH ...]
                       [--timeout SECONDS] [--json] [--debug]

v1 accepts only a **flat** layout: every `--targets`/`--tests` path must
resolve to a file directly inside one single directory (that directory is the
"target directory" throughout this module). No package/nested layout support.

Exit codes: `0` ran (any survivor count), `2` refused with a reason on stderr
and a matching `Mutation: unavailable ...` line on stdout. Tests + fixtures:
`scripts/test_mutation_sensor.py`.


The mutmut recipe -- lives ONLY here, by design
------------------------------------------------
This recipe took four attempts (a prior spike) to find. It is deliberately not
duplicated into any prose document -- point a reader here instead.

1. **cwd is the target directory**, for every `uv run ... mutmut ...` call.
   mutmut reads its own config (`pyproject.toml`) relative to the process cwd,
   not relative to `--project`.
2. **`--project` is the TARGET's own git toplevel**
   (`git -C <target-dir> rev-parse --show-toplevel`), never this script's own
   repository. This is what lets the shipped tool point at a foreign checkout
   (a different worktree, a different repo) and still resolve `uv`'s lockfile
   correctly for dependency installation.
3. The generated `pyproject.toml` carries **only** `[tool.mutmut]` -- no
   `[tool.pytest.ini_options]` -- so a pytest run elsewhere never picks up
   config it does not expect, and the target's own root config discovery (if
   any) is unaffected.
4. `source_paths` is the explicit list of the target directory's own top-level
   `*.py` files (tests included) -- not a package import path.
5. `only_mutate` is the `--targets` file **basenames** only.
6. `pytest_add_cli_args_test_selection` is the `--tests` file **basenames**.
   mutmut's own pytest sub-invocations run with `cwd=mutants/`, so a path
   carrying the target directory's name would read as not-found there.
7. `pytest_add_cli_args = ["--no-cov"]` on every pytest call mutmut makes,
   so a mutation run can never clobber the repo-root `coverage.xml`/`.coverage`
   this tool's own test suite depends on.
8. The generated `pyproject.toml` carries a marker comment
   (`PYPROJECT_MARKER` below) so a run killed mid-flight (SIGKILL, a hard
   turn-budget cutoff) leaves residue this script can recognize and remove on
   its *next* invocation, without ever touching a `pyproject.toml` it did not
   write itself -- see `_self_heal` and the existing-pyproject / unsupported-layout
   refusal checks below.
9. **`--no-project` is added, conditionally, when the target directory is
   itself the git toplevel.** Verified live against real `uv`/`mutmut`, not
   assumed: when point 2's `--project` root is the SAME directory this script
   just wrote a bare `[tool.mutmut]`-only `pyproject.toml` into, `uv` refuses
   with "No `project` table found" -- it expects `[project]` metadata at that
   exact path once one exists there at all. That coincidence can only happen
   for a flat target with no pre-existing `pyproject.toml` anywhere above it
   (the runner already refuses when one exists), so there was never a real set of
   project dependencies at that path to lose access to. See `_mutmut_argv`.

**Totals and attribution come from two different mutmut surfaces, never from
the `mutmut run` progress line** (which carriage-return-rewrites itself inside
a multi-hundred-KB debug log and is not meant to be parsed):

- **Totals** -- `mutmut export-cicd-stats` writes
  `<target-dir>/mutants/mutmut-cicd-stats.json` with
  `{killed, survived, total, no_tests, skipped, suspicious, timeout, segfault,
  check_was_interrupted_by_user}`, read from disk after the run completes.
- **Attribution** -- `mutmut results` (default, non-`--all`) prints one line
  per non-killed mutant, in one of two shapes: a module-level function,
  `    <module>.x_<fn>__mutmut_<n>: <status>`, or -- mutmut 3.8.0's real
  class-bearing shape -- a method trampoline,
  `    <module>.x<sep><Class><sep><method>__mutmut_<n>: <status>`, where
  `<sep>` is U+01C1 (`ǁ`), never an ASCII pipe. Both are parsed by the single
  `_MUTANT_KEY_RE`, anchored on **both** ends -- a naive `x_`-strip or
  `_`-split corrupts any function whose real name starts with `x_` or `_`
  (mutmut's own private-function naming collides with both), and a naive
  greedy word-character class for the class name would itself swallow the
  `ǁ` separator, since Python's `re` classifies U+01C1 as a word character
  too. A method mutant
  attributes as `Class.method` (e.g. `Box.__init__`, `Box.area`); a function
  mutant attributes by its bare name, exactly as before. When more than one
  `--targets` file is given, every label is additionally qualified with its
  owning module (`mod_a.helper` vs. `mod_b.helper`) so two targets defining
  the same function or method name never collapse into one merged count --
  irrelevant, and skipped, for the single-target case.
  *Gotcha, recorded so a future caller does not lose time to it*: `--all` is
  declared without `is_flag=True`, so a bare `--all` errors; it takes a value.
  This design never needs it.

`no tests` counts as a survivor, folded in with `survived`; `timeout`,
`suspicious` and `segfault` are reported separately as `inconclusive=` and
never folded into either bucket -- a mutant no selected test exercises at all
(or one that crashes the test process outright) is a *stronger* signal than
an ordinary survivor, and scoring it as clean would put this sensor's blind
spot exactly where its reason for existing lives.
"""

from __future__ import annotations

import argparse
import enum
import json
import re
import shutil
import subprocess
import sys
import time
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any

EXIT_OK = 0
EXIT_ERROR = 2

MUTMUT_VERSION = "3.8.0"
DEFAULT_TIMEOUT_SECONDS = 600.0
GIT_TIMEOUT_SECONDS = 30.0

# Below this, a subprocess would be started with a sub-millisecond budget --
# not enough to do anything, only enough to be reported as `run-failed` once
# it inevitably times out on its own. `_charge_budget` refuses as
# `run-timeout` itself instead of ever spending a share this thin.
MIN_BUDGET_SECONDS = 1.0

TOP_N_FUNCTIONS = 5
LINE_BYTE_CAP = 240

# Marks a pyproject.toml this script generated, so a leftover from a killed
# run can be told apart from a project's own configuration and self-healed on
# the next invocation (see `_self_heal`). Never written into, or read from,
# a pyproject.toml this script did not create.
PYPROJECT_MARKER = "# generated by scripts/mutation_sensor.py -- safe to delete"

# `mutmut export-cicd-stats`' JSON keys this script depends on. A missing key
# is a `run-failed` refusal -- totals must never be estimated, never a silent
# zero.
HISTOGRAM_KEYS = frozenset(
    {"killed", "survived", "no_tests", "skipped", "suspicious", "timeout", "segfault"}
)

# `mutmut results`' non-killed statuses that count as survivors.
SURVIVOR_STATUSES = frozenset({"survived", "no tests"})

# Anchored on both ends: `mod` up to the literal `.x`, then either the
# function shape (`_<fn>`) or the method shape (`ǁ<cls>ǁ<mname>`),
# both non-greedy up to the literal `__mutmut_<digits>:`. See the module
# docstring's "Attribution" paragraph for why an unanchored strip corrupts
# private (`_name`) functions and dunder methods (`__init__`) alike, and why
# `cls` excludes U+01C1 explicitly rather than relying on `\w` (which matches
# it).
_MUTANT_KEY_RE = re.compile(
    r"^\s*(?P<mod>[\w.]+)\.x"
    r"(?:ǁ(?P<cls>[^ǁ]+)ǁ(?P<mname>.+?)|_(?P<fname>.+?))"
    r"__mutmut_(?P<n>\d+):\s*(?P<status>.+)$"
)


class ReasonCode(enum.Enum):
    """Closed set -- a free-form string would let a caller invent a reason the
    verifier's disposition table (and the refusal stdout line) cannot recognize."""

    NOT_FLAT_LAYOUT = "not-flat-layout"
    PATH_MISSING = "path-missing"
    PYPROJECT_PRESENT = "pyproject-present"
    MUTANTS_DIR_PRESENT = "mutants-dir-present"
    TOOLCHAIN_MISSING = "toolchain-missing"
    RUN_TIMEOUT = "run-timeout"
    RUN_FAILED = "run-failed"


@dataclass(frozen=True)
class Refused:
    """The run never produced a trustworthy count. Exit 2."""

    reason: ReasonCode
    detail: str


@dataclass(frozen=True)
class Ran:
    """A completed, internally-consistent run. Exit 0, regardless of `mutants`.

    `histogram` is the raw `export-cicd-stats` breakdown; `survivors`,
    `inconclusive`, `killed` and `skipped` are properties derived from it
    rather than stored fields, so there is exactly one place each number comes
    from. `__post_init__` is this type's smart constructor: it raises when the
    two mutmut sources (the histogram and the per-function attribution) or the
    histogram and the reported total disagree, rather than let a caller
    publish two numbers that contradict each other.
    """

    targets: tuple[str, ...]
    mutants: int
    histogram: Mapping[str, int]
    per_function: Mapping[str, int]
    elapsed_s: float

    def __post_init__(self) -> None:
        missing = HISTOGRAM_KEYS - self.histogram.keys()
        if missing:
            raise ValueError(f"mutation histogram missing key(s): {', '.join(sorted(missing))}")
        attributed = sum(self.per_function.values())
        if self.survivors != attributed:
            raise ValueError(
                f"survivor count mismatch: histogram reports {self.survivors}, "
                f"per-function attribution sums to {attributed}"
            )
        accounted = self.survivors + self.killed + self.inconclusive + self.skipped
        if accounted != self.mutants:
            raise ValueError(
                f"mutant total mismatch: histogram accounts for {accounted}, "
                f"export-cicd-stats reports {self.mutants}"
            )

    @property
    def survivors(self) -> int:
        return self.histogram["survived"] + self.histogram["no_tests"]

    @property
    def inconclusive(self) -> int:
        return self.histogram["timeout"] + self.histogram["suspicious"] + self.histogram["segfault"]

    @property
    def killed(self) -> int:
        return self.histogram["killed"]

    @property
    def skipped(self) -> int:
        return self.histogram["skipped"]


SensorOutcome = Ran | Refused


class _FlatLayoutError(Exception):
    """`--targets`/`--tests` do not all resolve into one single directory."""


class _ToolchainError(Exception):
    """The target's own git toplevel could not be resolved."""


# ---------------------------------------------------------------------------
# The refusal surface -- every check here runs before any
# mutmut subprocess, so a refusal never touches the target directory except
# via `_self_heal`'s own residue it recognizes as its own.
# ---------------------------------------------------------------------------


def _flat_target_dir(targets: list[str], tests: list[str]) -> Path:
    resolved = [(raw, Path(raw).resolve()) for raw in (*targets, *tests)]
    parents = {rp.parent for _, rp in resolved}
    if len(parents) != 1:
        detail = ", ".join(f"{raw} -> {rp.parent}" for raw, rp in resolved)
        raise _FlatLayoutError(detail)
    return parents.pop()


def _first_missing_path(paths: list[str]) -> Path | None:
    """A nonexistent, or non-file (e.g. a directory), `--targets`/`--tests`
    path must be refused by name before any subprocess runs, rather than left
    to mutmut's own opaque failure or -- worse -- silently producing a
    trustworthy-looking zero-mutant reading. Checked with `is_file()`, not
    `exists()`, so a directory path is refused here rather than surfacing
    later as an unrelated `not-flat-layout`/`run-failed`."""
    for raw in paths:
        path = Path(raw)
        if not path.is_file():
            return path
    return None


def _self_heal(target_dir: Path) -> None:
    """Remove a marker-bearing `pyproject.toml` (and `mutants/` alongside it)
    left behind by a run this script started but never finished cleaning up
    after -- a SIGKILL or a hard turn-budget cutoff skips the `finally` below.

    Never touches a `pyproject.toml` lacking the marker: that is a project's
    own configuration, and the runner refuses on it rather than guessing.
    """
    pyproject_path = target_dir / "pyproject.toml"
    if not pyproject_path.exists():
        return
    try:
        content = pyproject_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return
    if PYPROJECT_MARKER not in content:
        return
    pyproject_path.unlink()
    mutants_dir = target_dir / "mutants"
    if mutants_dir.exists():
        shutil.rmtree(mutants_dir, ignore_errors=True)


# ---------------------------------------------------------------------------
# The success surface -- mutmut invocation and parsing.
# ---------------------------------------------------------------------------


def _mutmut_argv(target_root: Path, *subcommand: str, no_project: bool) -> list[str]:
    """`--project` is always the target's own git toplevel (asserted by the test
    suite regardless of `no_project`); `--no-project` is added only when the
    target directory IS its own git toplevel.

    That coincidence only arises for a flat-layout target with no pre-existing
    `pyproject.toml` anywhere above it -- the runner already refuses when one
    exists, so this directory can never carry real `[project]` dependencies to
    begin with. Without `--no-project`, uv reads *our own* freshly-generated
    `[tool.mutmut]`-only `pyproject.toml` (there is nowhere else for it to
    live) as project metadata and refuses with "No `project` table found" --
    discovered live against real `uv`/`mutmut`, not assumed from the recipe.
    When the target directory differs from its git toplevel (the common case:
    a `scripts/` subdirectory of a real, dependency-bearing checkout), the
    toplevel's own `pyproject.toml`/lockfile is untouched and `--no-project`
    is never added, so the target's real dependencies are still resolved --
    the reason the toplevel is resolved at all.
    """
    argv = [
        "uv",
        "run",
        "--project",
        str(target_root),
        "--with",
        f"mutmut=={MUTMUT_VERSION}",
    ]
    if no_project:
        argv.append("--no-project")
    argv.extend(["mutmut", *subcommand])
    return argv


def _tail(text: str, limit: int = 200) -> str:
    text = text.strip()
    return text if len(text) <= limit else text[-limit:]


def _git_toplevel(target_dir: Path) -> Path:
    argv = ["git", "-C", str(target_dir), "rev-parse", "--show-toplevel"]
    try:
        result = subprocess.run(argv, capture_output=True, text=True, timeout=GIT_TIMEOUT_SECONDS)
    except (OSError, subprocess.SubprocessError) as exc:
        raise _ToolchainError(f"{' '.join(argv)}: {exc}") from exc
    if result.returncode != 0:
        raise _ToolchainError(f"{' '.join(argv)}: {_tail(result.stderr)}")
    return Path(result.stdout.strip())


def _bootstrap_probe(
    target_root: Path, target_dir: Path, timeout: float, *, no_project: bool
) -> Refused | None:
    """A cheap `mutmut --version` call, before `mutmut run` is ever reached, so
    a failure to even resolve/install `mutmut==3.8.0` (no network, no `uv`
    lockfile) is told apart from a real `mutmut run` failure (toolchain-missing
    vs run-failed). A wall-clock exhaustion here is `run-timeout`, same as any
    other of the four mutmut calls -- never folded into `toolchain-missing`,
    which would misreport a slow-but-working toolchain as a broken one.
    Returns `None` on success, a `Refused` otherwise.
    """
    argv = _mutmut_argv(target_root, "--version", no_project=no_project)
    try:
        result = subprocess.run(
            argv, cwd=str(target_dir), capture_output=True, text=True, timeout=timeout
        )
    except subprocess.TimeoutExpired:
        return Refused(ReasonCode.RUN_TIMEOUT, f"{' '.join(argv)}: bootstrap exceeded {timeout}s")
    except (OSError, subprocess.SubprocessError) as exc:
        return Refused(ReasonCode.TOOLCHAIN_MISSING, f"{' '.join(argv)}: {exc}")
    if result.returncode != 0:
        detail = f"{' '.join(argv)}: {_tail(result.stderr) or _tail(result.stdout)}"
        return Refused(ReasonCode.TOOLCHAIN_MISSING, detail)
    return None


def _write_pyproject(
    target_dir: Path, target_names: list[str], test_names: list[str], *, debug: bool
) -> Path:
    source_paths = sorted(p.name for p in target_dir.glob("*.py"))
    body = (
        f"{PYPROJECT_MARKER}\n"
        "[tool.mutmut]\n"
        f"source_paths = {json.dumps(source_paths)}\n"
        f"only_mutate = {json.dumps(target_names)}\n"
        f"pytest_add_cli_args_test_selection = {json.dumps(test_names)}\n"
        'pytest_add_cli_args = ["--no-cov"]\n'
        f"debug = {'true' if debug else 'false'}\n"
    )
    path = target_dir / "pyproject.toml"
    path.write_text(body, encoding="utf-8")
    return path


def _invoke_mutmut_run(
    target_root: Path, target_dir: Path, timeout: float, *, no_project: bool
) -> Refused | None:
    argv = _mutmut_argv(target_root, "run", no_project=no_project)
    try:
        result = subprocess.run(
            argv, cwd=str(target_dir), capture_output=True, text=True, timeout=timeout
        )
    except subprocess.TimeoutExpired:
        return Refused(ReasonCode.RUN_TIMEOUT, f"mutmut run exceeded {timeout}s")
    except (OSError, subprocess.SubprocessError) as exc:
        return Refused(ReasonCode.RUN_FAILED, str(exc))
    if result.returncode != 0:
        detail = _tail(result.stderr) or _tail(result.stdout) or f"exited {result.returncode}"
        return Refused(ReasonCode.RUN_FAILED, detail)
    return None


def _invoke_export_cicd_stats(
    target_root: Path, target_dir: Path, timeout: float, *, no_project: bool
) -> dict[str, Any] | Refused:
    argv = _mutmut_argv(target_root, "export-cicd-stats", no_project=no_project)
    try:
        result = subprocess.run(
            argv, cwd=str(target_dir), capture_output=True, text=True, timeout=timeout
        )
    except subprocess.TimeoutExpired:
        return Refused(ReasonCode.RUN_TIMEOUT, f"export-cicd-stats exceeded {timeout}s")
    except (OSError, subprocess.SubprocessError) as exc:
        return Refused(ReasonCode.RUN_FAILED, str(exc))
    if result.returncode != 0:
        return Refused(ReasonCode.RUN_FAILED, _tail(result.stderr) or f"exited {result.returncode}")
    stats_path = target_dir / "mutants" / "mutmut-cicd-stats.json"
    try:
        return json.loads(stats_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return Refused(ReasonCode.RUN_FAILED, f"could not read {stats_path.name}: {exc}")


def _attribution_label(match: re.Match[str], *, module_qualify: bool) -> str:
    """`Class.method` for a method trampoline, the bare name for a function --
    then, only when more than one `--targets` file was given, prefixed with
    the owning module so two targets defining the same name never merge into
    one count (see the module docstring's "Attribution" paragraph)."""
    cls = match.group("cls")
    label = f"{cls}.{match.group('mname')}" if cls is not None else match.group("fname")
    # A nested class's method name still carries `ǁ` between the outer and
    # inner class (mutmut's own separator, captured whole by `mname`'s
    # non-greedy match) -- normalize every occurrence to `.` so the rendered
    # label always reads as a dotted path.
    label = label.replace("ǁ", ".")
    return f"{match.group('mod')}.{label}" if module_qualify else label


def _parse_results_text(text: str, *, module_qualify: bool) -> dict[str, int]:
    per_function: dict[str, int] = {}
    for line in text.splitlines():
        match = _MUTANT_KEY_RE.match(line)
        if not match:
            continue
        if match.group("status").strip() not in SURVIVOR_STATUSES:
            continue
        key = _attribution_label(match, module_qualify=module_qualify)
        per_function[key] = per_function.get(key, 0) + 1
    return per_function


def _invoke_results(
    target_root: Path, target_dir: Path, timeout: float, *, no_project: bool, module_qualify: bool
) -> dict[str, int] | Refused:
    argv = _mutmut_argv(target_root, "results", no_project=no_project)
    try:
        result = subprocess.run(
            argv, cwd=str(target_dir), capture_output=True, text=True, timeout=timeout
        )
    except subprocess.TimeoutExpired:
        return Refused(ReasonCode.RUN_TIMEOUT, f"results exceeded {timeout}s")
    except (OSError, subprocess.SubprocessError) as exc:
        return Refused(ReasonCode.RUN_FAILED, str(exc))
    if result.returncode != 0:
        return Refused(ReasonCode.RUN_FAILED, _tail(result.stderr) or f"exited {result.returncode}")
    return _parse_results_text(result.stdout, module_qualify=module_qualify)


def _build_ran(
    targets: list[str], stats: dict[str, Any], per_function: dict[str, int], elapsed_s: float
) -> Ran:
    missing = HISTOGRAM_KEYS - stats.keys()
    if missing:
        raise ValueError(f"mutmut-cicd-stats.json missing key(s): {', '.join(sorted(missing))}")
    if "total" not in stats:
        raise ValueError("mutmut-cicd-stats.json missing key: total")
    total = int(stats["total"])
    if total == 0:
        # A vacuous green: mutmut generated no mutants at all for these targets
        # (e.g. an empty or non-mutable file), which is indistinguishable from
        # "everything killed" unless refused explicitly -- see the module's
        # safety property in the header docstring.
        raise ValueError("mutmut generated zero mutants for the given targets")
    histogram = MappingProxyType({key: int(stats[key]) for key in HISTOGRAM_KEYS})
    return Ran(
        targets=tuple(targets),
        mutants=total,
        histogram=histogram,
        per_function=MappingProxyType(dict(per_function)),
        elapsed_s=elapsed_s,
    )


def _cleanup(target_dir: Path, pyproject_path: Path | None) -> None:
    """Runs on every exit path from `_run_mutmut` -- success, refusal, timeout,
    or an unhandled exception -- so no sensor residue can be swept into a
    commit by a careless whole-tree stage."""
    if pyproject_path is not None and pyproject_path.exists():
        pyproject_path.unlink()
    mutants_dir = target_dir / "mutants"
    if mutants_dir.exists():
        shutil.rmtree(mutants_dir, ignore_errors=True)


def _charge_budget(elapsed_since: float, timeout: float, stage: str) -> float | Refused:
    """One `--timeout` is a single wall-clock budget for the whole sequence
    (bootstrap probe, `mutmut run`, `export-cicd-stats`, `results`) -- not a
    fresh ceiling re-applied to each subprocess in turn, which would let a
    completed run take up to 4x the stated budget. Returns the remaining
    share to hand the next subprocess, or a `RUN_TIMEOUT` refusal the moment
    that share drops below `MIN_BUDGET_SECONDS` -- no further subprocess is
    ever invoked with a budget too thin to do anything but time out on its
    own and be misreported as a failure of that subprocess."""
    remaining = timeout - elapsed_since
    if remaining < MIN_BUDGET_SECONDS:
        return Refused(ReasonCode.RUN_TIMEOUT, f"budget exhausted before {stage} ({timeout}s)")
    return remaining


def _run_mutmut(
    target_dir: Path, targets: list[str], tests: list[str], timeout: float, *, debug: bool
) -> Ran | Refused:
    pyproject_path: Path | None = None
    start = time.monotonic()

    def next_remaining(stage: str) -> float | Refused:
        return _charge_budget(time.monotonic() - start, timeout, stage)

    try:
        try:
            target_root = _git_toplevel(target_dir)
        except _ToolchainError as exc:
            return Refused(ReasonCode.TOOLCHAIN_MISSING, str(exc))

        no_project = target_dir.resolve() == target_root.resolve()

        target_names = [Path(t).name for t in targets]
        test_names = [Path(t).name for t in tests]
        pyproject_path = _write_pyproject(target_dir, target_names, test_names, debug=debug)

        remaining = next_remaining("bootstrap probe")
        if isinstance(remaining, Refused):
            return remaining
        probe_refusal = _bootstrap_probe(target_root, target_dir, remaining, no_project=no_project)
        if probe_refusal is not None:
            return probe_refusal

        remaining = next_remaining("mutmut run")
        if isinstance(remaining, Refused):
            return remaining
        run_refusal = _invoke_mutmut_run(target_root, target_dir, remaining, no_project=no_project)
        if run_refusal is not None:
            return run_refusal

        remaining = next_remaining("export-cicd-stats")
        if isinstance(remaining, Refused):
            return remaining
        stats_or_refusal = _invoke_export_cicd_stats(
            target_root, target_dir, remaining, no_project=no_project
        )
        if isinstance(stats_or_refusal, Refused):
            return stats_or_refusal

        remaining = next_remaining("results")
        if isinstance(remaining, Refused):
            return remaining
        module_qualify = len(targets) > 1
        results_or_refusal = _invoke_results(
            target_root, target_dir, remaining, no_project=no_project, module_qualify=module_qualify
        )
        if isinstance(results_or_refusal, Refused):
            return results_or_refusal

        elapsed_s = time.monotonic() - start
        try:
            return _build_ran(targets, stats_or_refusal, results_or_refusal, elapsed_s)
        except (ValueError, TypeError, KeyError) as exc:
            return Refused(ReasonCode.RUN_FAILED, str(exc))
    finally:
        _cleanup(target_dir, pyproject_path)


# ---------------------------------------------------------------------------
# Rendering -- the runner is the sole author
# of both the human line and the JSON payload; agents copy stdout verbatim.
# ---------------------------------------------------------------------------


def _render_functions(per_function: Mapping[str, int], cap_n: int) -> str:
    if not per_function:
        return "()"
    items = sorted(per_function.items(), key=lambda kv: (-kv[1], kv[0]))
    shown = items[:cap_n]
    remaining = len(items) - len(shown)
    parts = [f"{fn}: {count}" for fn, count in shown]
    if remaining > 0:
        parts.append(f"+{remaining} more")
    return "(" + ", ".join(parts) + ")"


def render_line(outcome: Ran) -> str:
    """Top-5 survivor functions by count, `+<k> more` for the rest, hard-capped
    at `LINE_BYTE_CAP` bytes -- so this line can never push a green
    `TEST_RESULTS.md` step section past `check_test_results_shape.py`'s
    1,024-byte ceiling. Progressively drops shown functions before ever
    truncating mid-character; the loop only ever runs past `cap_n=5` in a
    pathological case no fixture reaches today.
    """
    prefix_parts = [f"Mutation: survivors={outcome.survivors} mutants={outcome.mutants}"]
    if outcome.inconclusive:
        prefix_parts.append(f"inconclusive={outcome.inconclusive}")
    target_names = ", ".join(Path(t).name for t in outcome.targets)
    prefix_parts.append(f"targets=[{target_names}]")
    prefix = " ".join(prefix_parts)

    candidate = prefix
    for cap_n in range(TOP_N_FUNCTIONS, -1, -1):
        candidate = f"{prefix} {_render_functions(outcome.per_function, cap_n)}"
        if len(candidate.encode("utf-8")) <= LINE_BYTE_CAP:
            return candidate
    return candidate.encode("utf-8")[:LINE_BYTE_CAP].decode("utf-8", errors="ignore")


def _one_line(text: str) -> str:
    return " ".join(text.split())


def _emit(outcome: Ran | Refused, *, json_mode: bool) -> int:
    if isinstance(outcome, Refused):
        print(f"{outcome.reason.value}: {outcome.detail}", file=sys.stderr)
        if json_mode:
            print(
                json.dumps(
                    {"outcome": "refused", "reason": outcome.reason.value, "detail": outcome.detail}
                )
            )
        else:
            print(
                f"Mutation: unavailable reason={outcome.reason.value} ({_one_line(outcome.detail)})"
            )
        return EXIT_ERROR

    line = render_line(outcome)
    if json_mode:
        payload = {
            "outcome": "ran",
            "targets": list(outcome.targets),
            "mutants": outcome.mutants,
            "survivors": outcome.survivors,
            "inconclusive": outcome.inconclusive,
            "counts": dict(outcome.histogram),
            "per_function": dict(outcome.per_function),
            "elapsed_s": outcome.elapsed_s,
            "line": line,
        }
        print(json.dumps(payload))
    else:
        print(line)
    return EXIT_OK


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Per-step mutation sensor: names, by function, the tests that would "
            "pass with the code under test broken."
        ),
        epilog="Exit 0 whenever the run completed, however many mutants survived; exit 2 only for a refusal.",
    )
    parser.add_argument(
        "--targets", nargs="+", required=True, metavar="PATH", help="the file(s) under mutation"
    )
    parser.add_argument(
        "--tests",
        nargs="+",
        required=True,
        metavar="PATH",
        help="the test file(s) exercising the targets",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=DEFAULT_TIMEOUT_SECONDS,
        help=f"wall-clock seconds before the run is refused as run-timeout (default: {DEFAULT_TIMEOUT_SECONDS:g})",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="emit the machine-readable object instead of the human line",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="turn on mutmut's own debug field in the generated pyproject.toml",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    json_mode = bool(args.json)

    # Missing-path check runs first: a typo'd path that happens to live in a
    # different directory must refuse as `path-missing`, not `not-flat-layout`
    # -- the flat-layout check only makes sense once every path is known to
    # resolve to a real file.
    missing = _first_missing_path([*args.targets, *args.tests])
    if missing is not None:
        return _emit(
            Refused(ReasonCode.PATH_MISSING, f"no such file: {missing}"), json_mode=json_mode
        )

    try:
        target_dir = _flat_target_dir(args.targets, args.tests)
    except _FlatLayoutError as exc:
        return _emit(Refused(ReasonCode.NOT_FLAT_LAYOUT, str(exc)), json_mode=json_mode)

    _self_heal(target_dir)

    pyproject_path = target_dir / "pyproject.toml"
    if pyproject_path.exists():
        return _emit(
            Refused(ReasonCode.PYPROJECT_PRESENT, str(pyproject_path)), json_mode=json_mode
        )

    mutants_dir = target_dir / "mutants"
    if mutants_dir.exists():
        return _emit(Refused(ReasonCode.MUTANTS_DIR_PRESENT, str(mutants_dir)), json_mode=json_mode)

    if shutil.which("uv") is None:
        return _emit(
            Refused(ReasonCode.TOOLCHAIN_MISSING, "uv not found on PATH"), json_mode=json_mode
        )

    outcome = _run_mutmut(target_dir, args.targets, args.tests, args.timeout, debug=args.debug)
    return _emit(outcome, json_mode=json_mode)


if __name__ == "__main__":
    sys.exit(main())
