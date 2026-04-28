"""CLI argument parsing, orchestration, exit codes, and output paths.

Thin wiring layer over the collector fleet and the composition modules.
No business logic lives here: every metric, delta, hotspot, and trend is
computed by a dedicated module (``runner``, ``hotspot``, ``trends``,
``report``, ``logappend``). The CLI's sole responsibility is to:

1. Parse ``--window-days`` and ``--top-n`` with strict positive-integer
   validation; reject invalid input via :class:`argparse.ArgumentTypeError`
   BEFORE any filesystem operation touches ``.ai-state/``.
2. Resolve the repository root via ``git rev-parse --show-toplevel``. A
   non-zero ``git`` exit surfaces as a clear stderr message and a non-zero
   process exit — the CLI refuses to invent an ``.ai-state/`` location.
3. Drive the six-step composition pipeline in its documented order:
   ``Runner.run -> compose_hotspots -> compute_trends -> render_json &
   render_markdown -> atomic writes -> append_log``.
4. Atomically write the JSON+MD report pair (tempfile + ``os.replace``) to
   ``<repo_root>/.ai-state/metrics_reports/METRICS_REPORT_<ts>.{json,md}``,
   then append one aggregate row to the sibling ``METRICS_LOG.md`` via
   ``logappend.append_log``.
5. Print the three absolute paths that were touched, one per line, on
   stdout so a shell wrapper can consume them.

No-partial-writes contract: argparse rejection exits before step 2; repo-
root failure exits before step 3. No file under ``.ai-state/`` is created,
modified, or deleted before the render layer has produced both the JSON
bytes and the MD string in memory.
"""

from __future__ import annotations

import argparse
import dataclasses
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path

from scripts.project_metrics.aggregate import compose_aggregate
from scripts.project_metrics.hotspot import compose_hotspots
from scripts.project_metrics.logappend import append_log
from scripts.project_metrics.report import render_json, render_markdown
from scripts.project_metrics.runner import Runner, default_registry
from scripts.project_metrics.schema import Report, RunMetadata
from scripts.project_metrics.trends import compute_trends

__all__ = ["main"]


# ---------------------------------------------------------------------------
# Constants — paths and filename conventions.
# ---------------------------------------------------------------------------

_AI_STATE_DIRNAME = ".ai-state"
_REPORTS_SUBDIR_NAME = "metrics_reports"
_REPORT_BASENAME_PREFIX = "METRICS_REPORT_"
_TIMESTAMP_FORMAT = "%Y-%m-%d_%H-%M-%S"
_METRICS_LOG_BASENAME = "METRICS_LOG.md"

_DEFAULT_WINDOW_DAYS = 90
_DEFAULT_TOP_N = 10


# ---------------------------------------------------------------------------
# Argparse type converter — positive integers only.
# ---------------------------------------------------------------------------


def _positive_int(raw: str) -> int:
    """Argparse ``type=`` converter: parse ``raw`` as a strictly positive int.

    Raises :class:`argparse.ArgumentTypeError` on non-integers or on zero /
    negative values so argparse turns the failure into its standard
    ``usage: ... error: ...`` message + process exit 2. The CLI never sees
    the exception because argparse catches it inside ``parse_args``.
    """

    try:
        value = int(raw)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"invalid int value: {raw!r}") from exc
    if value <= 0:
        raise argparse.ArgumentTypeError(f"must be positive (got {value!r})")
    return value


def _build_parser() -> argparse.ArgumentParser:
    """Construct the CLI's argument parser.

    Split out so tests (and ``--help``) can exercise parsing without
    triggering the orchestration pipeline as a side effect.
    """

    parser = argparse.ArgumentParser(
        prog="project-metrics",
        description=(
            "Collect repository metrics and write a JSON/MD report pair "
            "plus a one-row log append under .ai-state/."
        ),
    )
    parser.add_argument(
        "--window-days",
        type=_positive_int,
        default=_DEFAULT_WINDOW_DAYS,
        help=(
            "Sliding window, in days, for churn-based metrics. "
            f"Default: {_DEFAULT_WINDOW_DAYS}."
        ),
    )
    parser.add_argument(
        "--top-n",
        type=_positive_int,
        default=_DEFAULT_TOP_N,
        help=(
            "Number of hotspot files to surface in the top-N block. "
            f"Default: {_DEFAULT_TOP_N}."
        ),
    )
    parser.add_argument(
        "--refresh-coverage",
        action="store_true",
        default=False,
        help=(
            "Opt-in: before the read-only metrics pipeline runs, invoke the "
            "project's canonical coverage target (via the test-coverage "
            "skill's probe order) to refresh coverage.xml. A refresh failure "
            "degrades to a stderr warning and the pipeline still runs. "
            "Default: off (pipeline remains read-only)."
        ),
    )
    return parser


# ---------------------------------------------------------------------------
# Repo-root resolution — refuse to run outside a git working tree.
# ---------------------------------------------------------------------------


def _resolve_repo_root() -> Path:
    """Return the repository root via ``git rev-parse --show-toplevel``.

    Raises :class:`subprocess.CalledProcessError` on non-zero git exit so
    callers can translate it into a user-facing error. The check=True
    flag makes the "not in a git repo" case loud rather than silent.
    """

    completed = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        check=True,
        capture_output=True,
        text=True,
    )
    return Path(completed.stdout.strip())


# ---------------------------------------------------------------------------
# Atomic write — tempfile + os.replace, same-directory for same-filesystem rename.
# ---------------------------------------------------------------------------


def _atomic_write_bytes(path: Path, payload: bytes) -> None:
    """Write ``payload`` to ``path`` atomically via tempfile + ``os.replace``.

    Temp file lives in the same directory as ``path`` so ``os.replace`` is a
    POSIX atomic rename. A crash mid-write leaves ``path`` byte-identical to
    its pre-call state (or absent, if it did not yet exist).
    """

    parent = path.parent
    fd, tmp_name = tempfile.mkstemp(
        prefix=path.name + ".", suffix=".tmp", dir=str(parent)
    )
    try:
        with os.fdopen(fd, "wb") as tmp_fh:
            tmp_fh.write(payload)
        os.replace(tmp_name, path)
    except BaseException:
        # Best-effort cleanup — swallow errors on the cleanup path so the
        # original exception reaches the caller unobscured.
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


# ---------------------------------------------------------------------------
# Coverage refresh — test-coverage skill dispatcher (probe → invoke → verify).
# ---------------------------------------------------------------------------

_COVERAGE_ARTIFACT_BASENAME = "coverage.xml"
_COVERAGE_INVOKE_TIMEOUT_SECONDS: float = 600.0
_PIXI_COVERAGE_TASK_NAMES: tuple[str, ...] = ("coverage", "test-coverage", "cov")
_MAKE_COVERAGE_TARGET_NAMES: tuple[str, ...] = ("coverage", "test-coverage", "cov")


def _refresh_coverage_artifact(repo_root: Path) -> None:
    """Invoke the project's canonical coverage target to refresh ``coverage.xml``.

    Implements the test-coverage skill's Python probe order (pixi task →
    pyproject ``pytest-cov`` config → raw ``pytest --cov=<pkg>`` fallback →
    Makefile target), stops at the first hit, runs the discovered target,
    and raises :class:`RuntimeError` if no target is discoverable, the
    subprocess exits non-zero, or ``<repo_root>/coverage.xml`` is absent
    after invocation.

    Called only from the ``--refresh-coverage`` branch in :func:`main`.
    Exceptions propagate so the caller can warn + continue — the helper
    itself never swallows a failure.
    """

    target = _discover_coverage_target(repo_root)
    if target is None:
        raise RuntimeError(
            "test-coverage: no coverage target discoverable "
            "(no pixi coverage task, no pyproject pytest-cov config, "
            "no pytest-cov dependency for raw fallback, no Makefile target). "
            "See skills/test-coverage/references/python.md for setup."
        )

    try:
        completed = subprocess.run(
            target,
            cwd=str(repo_root),
            env=_coverage_invocation_env(repo_root),
            timeout=_COVERAGE_INVOKE_TIMEOUT_SECONDS,
            check=False,
        )
    except FileNotFoundError as exc:
        raise RuntimeError(
            f"test-coverage: invocation {target!r} failed — executable not found: {exc}"
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(
            f"test-coverage: invocation {target!r} timed out after "
            f"{int(_COVERAGE_INVOKE_TIMEOUT_SECONDS)}s"
        ) from exc

    if completed.returncode != 0:
        raise RuntimeError(
            f"test-coverage: {target!r} exited with status {completed.returncode}"
        )

    artifact = repo_root / _COVERAGE_ARTIFACT_BASENAME
    if not artifact.is_file():
        raise RuntimeError(
            f"test-coverage: {target!r} produced no {_COVERAGE_ARTIFACT_BASENAME} "
            f"at {artifact} (skill default requires the project root path)"
        )


def _discover_coverage_target(repo_root: Path) -> list[str] | None:
    """Return the argv for the first probe that hits, or ``None`` if all miss.

    Probe order matches ``skills/test-coverage/references/python.md``:

    1. A pixi task named ``coverage`` / ``test-coverage`` / ``cov``.
    2. A ``pyproject.toml`` with ``[tool.pytest.ini_options].addopts``
       containing ``--cov``, or a ``[tool.coverage.run]`` /
       ``[tool.coverage.report]`` block — invoke plain ``pytest``.
    3. ``pytest-cov`` declared anywhere in the project's dependency manifest
       (PEP 735 groups, poetry groups, optional-dependencies, requirements
       files, uv/poetry lockfiles) — fallback to bare ``pytest --cov=<pkg>``.
    4. A ``Makefile`` target named ``coverage`` / ``test-coverage`` / ``cov``.
    """

    pixi_task = _probe_pixi_coverage_task(repo_root)
    if pixi_task is not None:
        return ["pixi", "run", pixi_task]

    if _probe_pyproject_has_pytest_cov_config(repo_root):
        return _pytest_invocation(repo_root)

    if _probe_pytest_cov_dependency(repo_root):
        package = _infer_package_name(repo_root)
        argv = _pytest_invocation(repo_root)
        argv.append(f"--cov={package}")
        return argv

    make_target = _probe_makefile_coverage_target(repo_root)
    if make_target is not None:
        return ["make", make_target]

    return None


def _pytest_invocation(repo_root: Path) -> list[str]:
    """Return the preferred ``pytest`` argv — ``uv run pytest`` when uv is in use.

    Matches the skill's invocation convention: prefer the project's
    package/environment manager when one is detected so the correct
    virtualenv is active. Fall back to bare ``pytest`` otherwise.
    """

    if (repo_root / "uv.lock").is_file() and shutil.which("uv") is not None:
        return ["uv", "run", "pytest"]
    return ["pytest"]


def _coverage_invocation_env(repo_root: Path) -> dict[str, str]:
    """Return the environment for the coverage-refresh subprocess.

    Prepends ``repo_root`` to ``PYTHONPATH`` so flat-layout projects whose
    tests import first-party modules by package path resolve imports
    correctly. Runner-mediated invocations (``pixi run``, ``uv run``,
    ``make``) manage their own environment — the PYTHONPATH addition is
    harmless noise on those paths and load-bearing on the bare-``pytest``
    fallback.
    """

    env = dict(os.environ)
    existing = env.get("PYTHONPATH", "")
    repo_root_str = str(repo_root)
    if existing:
        env["PYTHONPATH"] = f"{repo_root_str}{os.pathsep}{existing}"
    else:
        env["PYTHONPATH"] = repo_root_str
    return env


def _probe_pixi_coverage_task(repo_root: Path) -> str | None:
    """Return the first known pixi task name present under ``[tasks]``.

    Reads ``pixi.toml`` as text and matches ``coverage|test-coverage|cov``
    as a bare key in the ``[tasks]`` section. TOML parsing is intentionally
    lightweight — the skill declines to take a TOML-library dependency
    for what is a simple convention check.
    """

    pixi_toml = repo_root / "pixi.toml"
    if not pixi_toml.is_file():
        return None
    try:
        text = pixi_toml.read_text(encoding="utf-8")
    except OSError:
        return None

    tasks_block = _extract_toml_section(text, "tasks")
    if tasks_block is None:
        return None

    for candidate in _PIXI_COVERAGE_TASK_NAMES:
        if re.search(rf"(?m)^\s*{re.escape(candidate)}\s*=", tasks_block):
            return candidate
    return None


def _probe_pyproject_has_pytest_cov_config(repo_root: Path) -> bool:
    """Return True when ``pyproject.toml`` carries pytest-cov-style config.

    Hits on either:
    * ``[tool.pytest.ini_options].addopts`` containing ``--cov``, OR
    * a ``[tool.coverage.run]`` or ``[tool.coverage.report]`` section.
    """

    pyproject = repo_root / "pyproject.toml"
    if not pyproject.is_file():
        return False
    try:
        text = pyproject.read_text(encoding="utf-8")
    except OSError:
        return False

    ini_block = _extract_toml_section(text, "tool.pytest.ini_options")
    if ini_block is not None:
        addopts_match = re.search(
            r"(?m)^\s*addopts\s*=\s*(.+)$",
            ini_block,
        )
        if addopts_match and "--cov" in addopts_match.group(1):
            return True

    if _extract_toml_section(text, "tool.coverage.run") is not None:
        return True
    if _extract_toml_section(text, "tool.coverage.report") is not None:
        return True
    return False


def _probe_pytest_cov_dependency(repo_root: Path) -> bool:
    """Return True when any dependency manifest declares ``pytest-cov``.

    Scans the most common Python dependency surfaces as plain text. A
    substring match is sufficient: the distribution name ``pytest-cov``
    is distinctive enough that false positives are not a realistic risk.
    """

    manifest_candidates = [
        repo_root / "pyproject.toml",
        repo_root / "uv.lock",
        repo_root / "poetry.lock",
        repo_root / "requirements.txt",
        repo_root / "requirements-dev.txt",
    ]
    for manifest in manifest_candidates:
        if not manifest.is_file():
            continue
        try:
            if "pytest-cov" in manifest.read_text(encoding="utf-8"):
                return True
        except OSError:
            continue
    return False


def _probe_makefile_coverage_target(repo_root: Path) -> str | None:
    """Return the first Makefile target that matches one of the known names."""

    makefile = repo_root / "Makefile"
    if not makefile.is_file():
        return None
    try:
        text = makefile.read_text(encoding="utf-8")
    except OSError:
        return None

    for candidate in _MAKE_COVERAGE_TARGET_NAMES:
        if re.search(rf"(?m)^{re.escape(candidate)}\s*:", text):
            return candidate
    return None


def _infer_package_name(repo_root: Path) -> str:
    """Infer a ``--cov=<pkg>`` target for the raw-fallback branch.

    Prefers ``[project].name`` in ``pyproject.toml``; falls back to a
    top-level ``src/`` child directory; ultimately defaults to ``.`` so
    ``pytest --cov=.`` still produces an artifact.
    """

    pyproject = repo_root / "pyproject.toml"
    if pyproject.is_file():
        try:
            text = pyproject.read_text(encoding="utf-8")
        except OSError:
            text = ""
        project_block = _extract_toml_section(text, "project")
        if project_block is not None:
            name_match = re.search(
                r'(?m)^\s*name\s*=\s*"([^"]+)"\s*$',
                project_block,
            )
            if name_match:
                return name_match.group(1)

    src_dir = repo_root / "src"
    if src_dir.is_dir():
        for child in sorted(src_dir.iterdir()):
            if child.is_dir() and not child.name.startswith("."):
                return child.name

    return "."


def _extract_toml_section(text: str, section: str) -> str | None:
    """Return the body of a named TOML section, or ``None`` if absent.

    Matches the literal ``[section]`` header (not inline tables) and
    returns everything up to the next top-level section header or end of
    file. The match is case-sensitive and whitespace-tolerant on the
    header line. This is a convention-level check, not a TOML parser.
    """

    pattern = rf"(?ms)^\s*\[{re.escape(section)}\]\s*$\n(.*?)(?=^\s*\[|\Z)"
    match = re.search(pattern, text)
    if match is None:
        return None
    return match.group(1)


# ---------------------------------------------------------------------------
# Orchestration entry point.
# ---------------------------------------------------------------------------


def _maybe_refresh_coverage(args: argparse.Namespace, repo_root: Path) -> None:
    """Run the opt-in coverage refresh pre-pass; degrade failures to a warning.

    The broad ``except Exception`` is load-bearing: the skill-invocation layer
    surfaces heterogeneous failures (missing target, subprocess exit code,
    absent artifact) without a narrow type hierarchy. /project-metrics must
    never hard-fail because the refresh pre-pass did not succeed.
    """

    if not args.refresh_coverage:
        return
    try:
        _refresh_coverage_artifact(repo_root)
    except Exception as exc:  # noqa: BLE001 — graceful-degradation contract
        sys.stderr.write(
            f"warning: --refresh-coverage failed ({exc}); "
            "continuing with existing coverage artifact\n"
        )


def _run_pipeline(
    args: argparse.Namespace, repo_root: Path, ai_state_dir: Path
) -> Report:
    """Execute the read-only metrics pipeline and return the composed report.

    ``time.monotonic`` is used (not ``datetime``) so that tests which patch
    ``cli.datetime`` to freeze the filename timestamp still get a real
    wall-clock duration here.
    """

    run_start = time.monotonic()
    registry = default_registry(repo_root)
    runner = Runner(registry=registry)
    report = runner.run(window_days=args.window_days, top_n=args.top_n)
    report = compose_aggregate(report, repo_root=repo_root)
    report = compose_hotspots(report)
    trend_block = compute_trends(report, ai_state_dir / _REPORTS_SUBDIR_NAME)
    run_metadata = RunMetadata(
        command_version="1.0.0",
        python_version=sys.version.split(" ", 1)[0],
        wall_clock_seconds=time.monotonic() - run_start,
        window_days=args.window_days,
        top_n=args.top_n,
    )
    return dataclasses.replace(report, trends=trend_block, run_metadata=run_metadata)


def _write_report(report: Report, ai_state_dir: Path) -> None:
    """Render the report triple, atomically write it, log it, print the paths."""

    md_text = render_markdown(report)
    json_bytes = render_json(report)

    timestamp = datetime.now(UTC).strftime(_TIMESTAMP_FORMAT)
    json_basename = f"{_REPORT_BASENAME_PREFIX}{timestamp}.json"
    md_basename = f"{_REPORT_BASENAME_PREFIX}{timestamp}.md"
    reports_dir = ai_state_dir / _REPORTS_SUBDIR_NAME
    reports_dir.mkdir(parents=True, exist_ok=True)
    json_path = reports_dir / json_basename
    md_path = reports_dir / md_basename
    log_path = reports_dir / _METRICS_LOG_BASENAME

    _atomic_write_bytes(json_path, json_bytes)
    _atomic_write_bytes(md_path, md_text.encode("utf-8"))

    # Log lives co-located with the reports; the link cell uses a bare basename.
    append_log(report, reports_dir, md_basename)

    for written in (json_path, md_path, log_path):
        print(str(written.resolve()))


def main(argv: list[str]) -> int:
    """Drive the metrics pipeline end-to-end; return a process exit code.

    Argparse failures exit process via ``SystemExit(2)`` before this function
    returns. Every other failure mode yields a ``return <non-zero>`` with a
    stderr diagnostic — no silent failure paths.
    """

    parser = _build_parser()
    args = parser.parse_args(argv)

    try:
        repo_root = _resolve_repo_root()
    except subprocess.CalledProcessError as exc:
        sys.stderr.write(
            "error: not inside a git repository "
            f"(git rev-parse --show-toplevel exited {exc.returncode})\n"
        )
        return 1

    ai_state_dir = repo_root / _AI_STATE_DIRNAME
    ai_state_dir.mkdir(parents=True, exist_ok=True)

    _maybe_refresh_coverage(args, repo_root)
    report = _run_pipeline(args, repo_root, ai_state_dir)
    _write_report(report, ai_state_dir)

    return 0
