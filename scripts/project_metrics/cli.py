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
   ``<repo_root>/.ai-state/METRICS_REPORT_<ts>.{json,md}``, then append one
   aggregate row to ``METRICS_LOG.md`` via ``logappend.append_log``.
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
from scripts.project_metrics.schema import RunMetadata
from scripts.project_metrics.trends import compute_trends

__all__ = ["main"]


# ---------------------------------------------------------------------------
# Constants — paths and filename conventions.
# ---------------------------------------------------------------------------

_AI_STATE_DIRNAME = ".ai-state"
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
# Orchestration entry point.
# ---------------------------------------------------------------------------


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

    # time.monotonic is used (not datetime) so that tests which patch
    # `cli.datetime` to freeze the filename timestamp still get a real
    # wall-clock duration here.
    run_start = time.monotonic()
    registry = default_registry(repo_root)
    runner = Runner(registry=registry)
    report = runner.run(window_days=args.window_days, top_n=args.top_n)
    report = compose_aggregate(report, repo_root=repo_root)
    report = compose_hotspots(report)
    trend_block = compute_trends(report, ai_state_dir)
    run_metadata = RunMetadata(
        command_version="1.0.0",
        python_version=sys.version.split(" ", 1)[0],
        wall_clock_seconds=time.monotonic() - run_start,
        window_days=args.window_days,
        top_n=args.top_n,
    )
    report = dataclasses.replace(report, trends=trend_block, run_metadata=run_metadata)

    md_text = render_markdown(report)
    json_bytes = render_json(report)

    timestamp = datetime.now(UTC).strftime(_TIMESTAMP_FORMAT)
    json_basename = f"{_REPORT_BASENAME_PREFIX}{timestamp}.json"
    md_basename = f"{_REPORT_BASENAME_PREFIX}{timestamp}.md"
    json_path = ai_state_dir / json_basename
    md_path = ai_state_dir / md_basename
    log_path = ai_state_dir / _METRICS_LOG_BASENAME

    _atomic_write_bytes(json_path, json_bytes)
    _atomic_write_bytes(md_path, md_text.encode("utf-8"))

    append_log(report, ai_state_dir, md_basename)

    for written in (json_path, md_path, log_path):
        print(str(written.resolve()))

    return 0
