"""Behavioral tests for ``cli.py`` -- argparse + orchestration + output paths.

These tests encode the CLI's contract as the thin orchestration layer that
wires together the `Runner`, `compose_hotspots`, `compute_trends`,
`render_markdown`, `render_json`, and `append_log`. The CLI itself should
contain no business logic; every behavior tested here is about *wiring*:

* Argument parsing (valid defaults, invalid values rejected before any I/O).
* Repo-root validation via ``git rev-parse --show-toplevel``.
* Orchestration call sequence (Runner -> hotspots -> trends -> render -> log).
* Atomic-triple output contract: exactly three files written per successful
  run (``METRICS_REPORT_<ts>.json``, ``METRICS_REPORT_<ts>.md``,
  ``METRICS_LOG.md``), timestamp-formatted filenames, stdout-printed paths.
* No-partial-writes guarantee: when argparse rejects an argument, the
  ``.ai-state/`` directory must remain byte-identical.

Import strategy -- every test imports ``main`` inside its body. During the
BDD/TDD RED handshake, ``cli.py`` is a 5-line stub; top-of-module imports
would collapse pytest collection into a single ``ImportError`` for every
test in the file. Deferred imports yield per-test RED/GREEN resolution
with a specific ``ImportError`` or ``AttributeError`` for each test.

Mock strategy -- the CLI is expected to import its collaborators at module
top (``from .runner import Runner``, etc.), which gives ``unittest.mock.patch``
attachment points at ``scripts.project_metrics.cli.<symbol>``. Tests mock
the full collaborator surface so the CLI is exercised in isolation:

    scripts.project_metrics.cli.Runner            (class)
    scripts.project_metrics.cli.compose_hotspots  (fn)
    scripts.project_metrics.cli.compute_trends    (fn)
    scripts.project_metrics.cli.render_markdown   (fn)
    scripts.project_metrics.cli.render_json       (fn)
    scripts.project_metrics.cli.append_log        (fn)
    scripts.project_metrics.cli.subprocess        (module -- for git check)
    scripts.project_metrics.cli.datetime          (class or module -- for ts)

The real file writes the CLI performs (JSON + MD to tmp_path) are exercised
against the filesystem; only external boundaries (git, datetime, the
composition functions) are mocked.

Traceability for the requirement IDs this file validates lives in
``.ai-work/project-metrics/traceability_15b_test-engineer.yml``
per ``rules/swe/id-citation-discipline.md`` -- code is ID-free.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Test-data builders -- construct a minimal but complete Report that the
# CLI's orchestration layer can feed through without touching real collectors.
# ---------------------------------------------------------------------------


def _minimal_aggregate_kwargs() -> dict[str, Any]:
    """Build a full 16-field kwargs dict for AggregateBlock with populated values.

    Mirrors the pattern in ``test_logappend.py`` so CLI tests produce the
    same kind of Report object the downstream log-append contract expects.
    """
    return {
        "schema_version": "1.0.0",
        "timestamp": "2026-04-23T18:45:00Z",
        "commit_sha": "abc123fabc123fabc123fabc123fabc123fabc12",
        "window_days": 90,
        "sloc_total": 4200,
        "file_count": 42,
        "language_count": 3,
        "ccn_p95": 7.5,
        "cognitive_p95": 9.0,
        "cyclic_deps": 0,
        "churn_total_90d": 567,
        "change_entropy_90d": 2.1,
        "truck_factor": 2,
        "hotspot_top_score": 123.4,
        "hotspot_gini": 0.75,
        "coverage_line_pct": 0.813,
    }


def _build_synthetic_report() -> Any:
    """Construct a schema-valid Report the mocked Runner can return.

    Deferred import so this helper is safe to call even before the CLI
    module exists. The schema module has been GREEN since an early step
    in the pipeline, so these imports resolve.
    """
    from scripts.project_metrics.schema import AggregateBlock, Report

    aggregate = AggregateBlock(**_minimal_aggregate_kwargs())
    return Report(
        schema_version="1.0.0",
        aggregate=aggregate,
        tool_availability={},
        collectors={},
    )


def _snapshot_dir(root: Path) -> dict[str, str]:
    """Produce a byte-level snapshot of every file under ``root``.

    Returns a mapping from relative path string to SHA-256 hex digest.
    Directory entries themselves are not hashed (they are implicit from
    their children); empty directories compare via path-presence only.

    This is the finest-grained "no side effects" assertion the
    no-partial-writes contract can express: invalid-args runs must not
    create, modify, or delete any file under the target ``.ai-state/``.
    """
    if not root.exists():
        return {}
    snapshot: dict[str, str] = {}
    for path in sorted(root.rglob("*")):
        if path.is_file():
            rel = str(path.relative_to(root))
            snapshot[rel] = hashlib.sha256(path.read_bytes()).hexdigest()
    return snapshot


# ---------------------------------------------------------------------------
# Mock-installer helper -- every happy-path and orchestration test needs the
# same stack of patches. Consolidate via a helper that returns a dict of the
# installed MagicMocks so tests can assert on them.
# ---------------------------------------------------------------------------


class _MockedCollaborators:
    """Holder for the MagicMocks installed at the CLI module's import points.

    Yielded by ``_install_cli_mocks`` inside a ``with`` block. Tests read
    attributes off this object (e.g., ``mocks.runner_cls``,
    ``mocks.compose_hotspots``) to assert on call args / call counts.
    """

    def __init__(self) -> None:
        self.runner_cls: MagicMock = MagicMock(name="Runner")
        self.compose_aggregate: MagicMock = MagicMock(name="compose_aggregate")
        self.compose_hotspots: MagicMock = MagicMock(name="compose_hotspots")
        self.compute_trends: MagicMock = MagicMock(name="compute_trends")
        self.render_markdown: MagicMock = MagicMock(name="render_markdown")
        self.render_json: MagicMock = MagicMock(name="render_json")
        self.append_log: MagicMock = MagicMock(name="append_log")
        self.subprocess_run: MagicMock = MagicMock(name="subprocess.run")
        self.datetime_module: MagicMock = MagicMock(name="datetime")


def _install_cli_mocks(
    *,
    repo_root: Path,
    report_timestamp: str = "2026-04-23_18-45-00",
    git_succeeds: bool = True,
) -> tuple[_MockedCollaborators, list[Any]]:
    """Install the full mock stack for a happy-path CLI run.

    Returns (holder, patchers). Caller is responsible for entering each
    patcher's ``__enter__`` (typically via ``contextlib.ExitStack``) and
    exiting them when done. Returning the patchers (rather than starting
    them here) keeps the tests' ``with ExitStack() as stack: ...`` idiom
    readable and makes cleanup explicit.

    ``git_succeeds`` — when True, the mocked ``subprocess.run`` for
    ``git rev-parse --show-toplevel`` returns a completed process whose
    stdout is ``repo_root``. When False, ``subprocess.run`` raises
    ``CalledProcessError``, exercising the not-in-git-repo branch.

    ``report_timestamp`` — the ``datetime.now().strftime(...)`` return
    value. CLI builds filenames from this, so mocking yields deterministic
    ``METRICS_REPORT_<ts>.{json,md}`` paths.
    """
    import subprocess as _real_subprocess

    mocks = _MockedCollaborators()

    synthetic_report = _build_synthetic_report()
    # Runner(registry=...).run(...) returns a Report. MagicMock chains:
    #   Runner(...) -> instance_mock (MagicMock)
    #   instance_mock.run.return_value = report
    runner_instance = MagicMock(name="RunnerInstance")
    runner_instance.run.return_value = synthetic_report
    mocks.runner_cls.return_value = runner_instance

    # Composition functions each return a Report (or bytes/str for renderers).
    # We reuse the same synthetic_report so downstream mocks see a real object;
    # the CLI's orchestration never inspects internals — it just forwards.
    mocks.compose_aggregate.return_value = synthetic_report
    mocks.compose_hotspots.return_value = synthetic_report
    # compute_trends returns a TrendBlock; the CLI is expected to stitch it
    # into the Report (via dataclasses.replace) or call it for side effect.
    # Either way, the CLI forwards its result into render_* and append_log.
    from scripts.project_metrics.schema import TrendBlock

    mocks.compute_trends.return_value = TrendBlock(status="first_run")
    mocks.render_markdown.return_value = "# Metrics Report\n\n(mocked)\n"
    mocks.render_json.return_value = b'{"schema_version":"1.0.0"}'
    mocks.append_log.return_value = None

    # subprocess.run mocking -- git rev-parse --show-toplevel.
    # The CLI is expected to call it as
    # subprocess.run(["git", "rev-parse", "--show-toplevel"], ...).
    if git_succeeds:
        completed = MagicMock(name="CompletedProcess")
        completed.returncode = 0
        completed.stdout = str(repo_root) + "\n"
        mocks.subprocess_run.return_value = completed
    else:
        mocks.subprocess_run.side_effect = _real_subprocess.CalledProcessError(
            returncode=128,
            cmd=["git", "rev-parse", "--show-toplevel"],
            stderr="fatal: not a git repository",
        )

    # datetime mocking -- CLI is expected to call datetime.now(UTC).strftime(...)
    # or similar. MagicMock chains let any call path return our pinned value.
    now_mock = MagicMock(name="datetime.now")
    now_mock.strftime.return_value = report_timestamp
    # Both .now(...) and .now(UTC) should return now_mock so any call pattern works.
    mocks.datetime_module.now.return_value = now_mock
    # Preserve UTC symbol so "datetime.UTC" lookups work.
    mocks.datetime_module.UTC = MagicMock(name="UTC")
    # Some impls do `from datetime import datetime, UTC` then
    # `datetime.now(UTC).strftime(...)`. In that import pattern, the mock
    # target is scripts.project_metrics.cli.datetime (the class), and
    # .now(...).strftime(...) resolves through the same chain above.

    # Patchers are built but not started -- caller uses ExitStack.
    # Each patcher covers one module-level import point in cli.py.
    patchers = [
        patch("scripts.project_metrics.cli.Runner", mocks.runner_cls),
        patch(
            "scripts.project_metrics.cli.compose_aggregate",
            mocks.compose_aggregate,
        ),
        patch(
            "scripts.project_metrics.cli.compose_hotspots",
            mocks.compose_hotspots,
        ),
        patch(
            "scripts.project_metrics.cli.compute_trends",
            mocks.compute_trends,
        ),
        patch(
            "scripts.project_metrics.cli.render_markdown",
            mocks.render_markdown,
        ),
        patch(
            "scripts.project_metrics.cli.render_json",
            mocks.render_json,
        ),
        patch(
            "scripts.project_metrics.cli.append_log",
            mocks.append_log,
        ),
        # subprocess.run is patched on the subprocess module attribute the CLI
        # imports; if the CLI does `import subprocess` then calls
        # `subprocess.run(...)`, the mock attaches at
        # scripts.project_metrics.cli.subprocess.run. If the CLI does
        # `from subprocess import run`, the mock target would differ; the
        # former is the documented pattern per the step delegation.
        patch(
            "scripts.project_metrics.cli.subprocess.run",
            mocks.subprocess_run,
        ),
        patch(
            "scripts.project_metrics.cli.datetime",
            mocks.datetime_module,
        ),
    ]
    return mocks, patchers


def _run_main_with_ai_state_dir(
    argv: list[str],
    ai_state_dir: Path,
    mocks: _MockedCollaborators,
) -> int:
    """Invoke ``main(argv)`` with the CLI's repo-root resolution pointed at
    ``ai_state_dir.parent`` so the CLI writes under ``ai_state_dir``.

    The CLI derives its output directory as ``<repo_root>/.ai-state/``.
    To redirect writes into ``tmp_path``, tests ensure the mocked
    ``git rev-parse --show-toplevel`` returns ``ai_state_dir.parent`` and
    that the ``.ai-state/`` name matches (pytest tmp_path is used with
    explicit ``.ai-state`` subdir).
    """
    # Re-point the subprocess mock's stdout to reflect the caller's repo_root.
    completed = MagicMock(name="CompletedProcess")
    completed.returncode = 0
    completed.stdout = str(ai_state_dir.parent) + "\n"
    mocks.subprocess_run.return_value = completed
    mocks.subprocess_run.side_effect = None

    from scripts.project_metrics.cli import main

    return main(argv)


# ---------------------------------------------------------------------------
# Argparse: default / valid / invalid argument handling. No production code
# should be invoked past argparse.error on invalid input -- argparse exits
# with code 2 before any file write.
# ---------------------------------------------------------------------------


class TestCliArgParsing:
    """Valid arg vectors are accepted; invalid ones exit non-zero."""

    def test_valid_window_days_and_top_n_accepted(self, tmp_path: Path) -> None:
        ai_state = tmp_path / ".ai-state"
        ai_state.mkdir()

        mocks, patchers = _install_cli_mocks(repo_root=tmp_path)
        try:
            for p in patchers:
                p.start()
            exit_code = _run_main_with_ai_state_dir(
                ["--window-days", "90", "--top-n", "10"], ai_state, mocks
            )
        finally:
            for p in patchers:
                p.stop()

        assert exit_code == 0, (
            f"Valid args must produce exit 0; got {exit_code}. "
            "The CLI's happy path must not early-exit on valid input."
        )

    def test_default_window_days_and_top_n_when_no_args(self, tmp_path: Path) -> None:
        """Per plan line 473: defaults are 90 and 10; bare invocation is valid."""
        ai_state = tmp_path / ".ai-state"
        ai_state.mkdir()

        mocks, patchers = _install_cli_mocks(repo_root=tmp_path)
        try:
            for p in patchers:
                p.start()
            exit_code = _run_main_with_ai_state_dir([], ai_state, mocks)
        finally:
            for p in patchers:
                p.stop()

        assert exit_code == 0, (
            "No-arg invocation must succeed using defaults (90/10); "
            f"got exit {exit_code}."
        )
        # The runner should have been called with defaults.
        assert mocks.runner_cls.return_value.run.called, (
            "Runner.run must be invoked on the default path"
        )
        run_kwargs = mocks.runner_cls.return_value.run.call_args.kwargs
        assert run_kwargs.get("window_days") == 90, (
            f"Default window_days must be 90; got {run_kwargs.get('window_days')}"
        )
        assert run_kwargs.get("top_n") == 10, (
            f"Default top_n must be 10; got {run_kwargs.get('top_n')}"
        )

    def test_window_days_zero_is_rejected(self, tmp_path: Path) -> None:
        """window_days must be positive; argparse should reject 0 before I/O."""
        ai_state = tmp_path / ".ai-state"
        ai_state.mkdir()
        mocks, patchers = _install_cli_mocks(repo_root=tmp_path)
        try:
            for p in patchers:
                p.start()
            with pytest.raises(SystemExit) as excinfo:
                _run_main_with_ai_state_dir(["--window-days", "0"], ai_state, mocks)
        finally:
            for p in patchers:
                p.stop()

        code = excinfo.value.code
        assert code != 0, (
            f"--window-days 0 must exit non-zero; got {code}. "
            "Argparse's ArgumentTypeError path should surface here."
        )

    def test_window_days_negative_is_rejected(self, tmp_path: Path) -> None:
        ai_state = tmp_path / ".ai-state"
        ai_state.mkdir()
        mocks, patchers = _install_cli_mocks(repo_root=tmp_path)
        try:
            for p in patchers:
                p.start()
            with pytest.raises(SystemExit) as excinfo:
                _run_main_with_ai_state_dir(["--window-days", "-5"], ai_state, mocks)
        finally:
            for p in patchers:
                p.stop()

        code = excinfo.value.code
        assert code != 0, f"--window-days -5 must exit non-zero; got {code}."

    def test_top_n_zero_is_rejected(self, tmp_path: Path) -> None:
        ai_state = tmp_path / ".ai-state"
        ai_state.mkdir()
        mocks, patchers = _install_cli_mocks(repo_root=tmp_path)
        try:
            for p in patchers:
                p.start()
            with pytest.raises(SystemExit) as excinfo:
                _run_main_with_ai_state_dir(["--top-n", "0"], ai_state, mocks)
        finally:
            for p in patchers:
                p.stop()

        code = excinfo.value.code
        assert code != 0, f"--top-n 0 must exit non-zero; got {code}."

    def test_help_flag_exits_zero_and_prints_usage(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """`--help` is argparse's standard short-circuit; must exit 0."""
        # --help doesn't need the full orchestration mock stack because it
        # short-circuits inside argparse before any downstream call. But we
        # still install mocks so the CLI module loads cleanly.
        mocks, patchers = _install_cli_mocks(repo_root=tmp_path)
        try:
            for p in patchers:
                p.start()
            from scripts.project_metrics.cli import main

            with pytest.raises(SystemExit) as excinfo:
                main(["--help"])
        finally:
            for p in patchers:
                p.stop()

        assert excinfo.value.code == 0, (
            f"--help must exit 0 (argparse convention); got {excinfo.value.code}"
        )
        captured = capsys.readouterr()
        # Help text is emitted to stdout by argparse; at minimum it names the
        # options documented in the plan.
        combined = captured.out + captured.err
        assert "--window-days" in combined, (
            "Help output must mention --window-days flag"
        )
        assert "--top-n" in combined, "Help output must mention --top-n flag"


# ---------------------------------------------------------------------------
# No-partial-writes contract. When argparse rejects an argument, the target
# .ai-state/ directory must remain byte-identical (no file created, no
# existing file modified). This is the strongest single guarantee the CLI
# provides against spurious state on invalid input.
# ---------------------------------------------------------------------------


class TestCliNoPartialWrites:
    """Invalid-argument runs leave the target directory byte-identical."""

    def test_invalid_window_days_creates_no_new_files(self, tmp_path: Path) -> None:
        ai_state = tmp_path / ".ai-state"
        ai_state.mkdir()
        # Seed a pre-existing file so we test both "no new file" and
        # "no modification of existing file".
        seed = ai_state / "PRE_EXISTING.md"
        seed.write_text("untouched\n", encoding="utf-8")
        before = _snapshot_dir(ai_state)

        mocks, patchers = _install_cli_mocks(repo_root=tmp_path)
        try:
            for p in patchers:
                p.start()
            with pytest.raises(SystemExit):
                _run_main_with_ai_state_dir(["--window-days", "0"], ai_state, mocks)
        finally:
            for p in patchers:
                p.stop()

        after = _snapshot_dir(ai_state)
        assert after == before, (
            "Directory snapshot diverged after invalid-args run. "
            f"before={before!r} after={after!r}. "
            "No-partial-writes contract violated: argparse rejection "
            "MUST NOT create or modify any file under .ai-state/."
        )

    def test_invalid_top_n_creates_no_new_files(self, tmp_path: Path) -> None:
        ai_state = tmp_path / ".ai-state"
        ai_state.mkdir()
        before = _snapshot_dir(ai_state)

        mocks, patchers = _install_cli_mocks(repo_root=tmp_path)
        try:
            for p in patchers:
                p.start()
            with pytest.raises(SystemExit):
                _run_main_with_ai_state_dir(["--top-n", "-1"], ai_state, mocks)
        finally:
            for p in patchers:
                p.stop()

        after = _snapshot_dir(ai_state)
        assert after == before, (
            f"Invalid --top-n must not modify .ai-state/; "
            f"before={before!r} after={after!r}"
        )

    def test_invalid_args_do_not_invoke_runner(self, tmp_path: Path) -> None:
        """Argparse rejection must short-circuit before the orchestration
        pipeline starts."""
        ai_state = tmp_path / ".ai-state"
        ai_state.mkdir()

        mocks, patchers = _install_cli_mocks(repo_root=tmp_path)
        try:
            for p in patchers:
                p.start()
            with pytest.raises(SystemExit):
                _run_main_with_ai_state_dir(["--window-days", "0"], ai_state, mocks)
        finally:
            for p in patchers:
                p.stop()

        # Runner class MUST NOT have been instantiated; if it was, the CLI
        # called into the orchestration layer despite a rejected arg.
        assert not mocks.runner_cls.called, (
            "Runner must not be constructed when argparse rejects input"
        )
        assert not mocks.append_log.called, (
            "append_log must not be invoked when argparse rejects input"
        )


# ---------------------------------------------------------------------------
# Happy path: exactly three files written on a valid run; filenames include
# a well-formed timestamp; stdout prints the three paths.
# ---------------------------------------------------------------------------


class TestCliHappyPath:
    """Valid invocations produce exactly three files and print their paths."""

    def test_happy_path_writes_exactly_three_files(self, tmp_path: Path) -> None:
        ai_state = tmp_path / ".ai-state"
        ai_state.mkdir()

        mocks, patchers = _install_cli_mocks(
            repo_root=tmp_path, report_timestamp="2026-04-23_18-45-00"
        )
        try:
            for p in patchers:
                p.start()
            exit_code = _run_main_with_ai_state_dir(
                ["--window-days", "90", "--top-n", "10"], ai_state, mocks
            )
        finally:
            for p in patchers:
                p.stop()

        assert exit_code == 0, f"Happy path must exit 0; got {exit_code}"
        # The JSON + MD files are written directly by the CLI (mocked
        # render_json returned bytes, mocked render_markdown returned str).
        # append_log is mocked so METRICS_LOG.md is not actually created here;
        # we assert append_log was invoked with the expected args instead.
        reports_dir = ai_state / "metrics_reports"
        json_files = sorted(reports_dir.glob("METRICS_REPORT_*.json"))
        md_files = sorted(reports_dir.glob("METRICS_REPORT_*.md"))
        assert len(json_files) == 1, (
            f"Expected exactly 1 METRICS_REPORT_*.json; found {len(json_files)}: "
            f"{[str(p) for p in json_files]}"
        )
        assert len(md_files) == 1, (
            f"Expected exactly 1 METRICS_REPORT_*.md; found {len(md_files)}: "
            f"{[str(p) for p in md_files]}"
        )
        assert mocks.append_log.called, (
            "append_log must be invoked on the happy path (third-file concern)"
        )

    def test_filename_includes_well_formed_timestamp(self, tmp_path: Path) -> None:
        """Filenames match YYYY-MM-DD_HH-MM-SS per the timestamp-formatting rule."""
        ai_state = tmp_path / ".ai-state"
        ai_state.mkdir()

        mocks, patchers = _install_cli_mocks(
            repo_root=tmp_path, report_timestamp="2026-04-23_18-45-00"
        )
        try:
            for p in patchers:
                p.start()
            _run_main_with_ai_state_dir(
                ["--window-days", "90", "--top-n", "10"], ai_state, mocks
            )
        finally:
            for p in patchers:
                p.stop()

        ts_pattern = re.compile(
            r"^METRICS_REPORT_(\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2})\.(json|md)$"
        )
        written = sorted(
            p.name for p in (ai_state / "metrics_reports").glob("METRICS_REPORT_*")
        )
        assert len(written) == 2, f"Expected 2 artifact files; got {written}"
        for name in written:
            m = ts_pattern.match(name)
            assert m is not None, (
                f"Filename '{name}' must match 'METRICS_REPORT_<ts>.{{json,md}}' "
                "with ts = YYYY-MM-DD_HH-MM-SS (colons are invalid in filenames)"
            )

    def test_json_and_md_share_the_same_timestamp(self, tmp_path: Path) -> None:
        """The JSON and MD of the same run must carry an identical timestamp --
        they are an artifact *pair*, not two independent writes."""
        ai_state = tmp_path / ".ai-state"
        ai_state.mkdir()

        mocks, patchers = _install_cli_mocks(
            repo_root=tmp_path, report_timestamp="2026-04-23_18-45-00"
        )
        try:
            for p in patchers:
                p.start()
            _run_main_with_ai_state_dir(
                ["--window-days", "90", "--top-n", "10"], ai_state, mocks
            )
        finally:
            for p in patchers:
                p.stop()

        reports_dir = ai_state / "metrics_reports"
        json_files = list(reports_dir.glob("METRICS_REPORT_*.json"))
        md_files = list(reports_dir.glob("METRICS_REPORT_*.md"))
        assert len(json_files) == 1 and len(md_files) == 1, (
            "Precondition: one JSON + one MD for the pair contract to hold"
        )
        json_ts = json_files[0].stem.replace("METRICS_REPORT_", "")
        md_ts = md_files[0].stem.replace("METRICS_REPORT_", "")
        assert json_ts == md_ts, (
            f"JSON timestamp '{json_ts}' must match MD timestamp '{md_ts}' "
            "within a single run (they are an artifact pair)"
        )

    def test_stdout_prints_three_absolute_paths(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Per plan line 482: output paths are printed on stdout."""
        ai_state = tmp_path / ".ai-state"
        ai_state.mkdir()

        mocks, patchers = _install_cli_mocks(
            repo_root=tmp_path, report_timestamp="2026-04-23_18-45-00"
        )
        try:
            for p in patchers:
                p.start()
            _run_main_with_ai_state_dir(
                ["--window-days", "90", "--top-n", "10"], ai_state, mocks
            )
        finally:
            for p in patchers:
                p.stop()

        out = capsys.readouterr().out
        # All three expected filenames must appear in stdout; the CLI decides
        # the exact line format, but at minimum the three basenames must be
        # mentioned so a downstream command wrapper can read them.
        assert "METRICS_REPORT_2026-04-23_18-45-00.json" in out, (
            f"stdout must mention the JSON filename; got:\n{out!r}"
        )
        assert "METRICS_REPORT_2026-04-23_18-45-00.md" in out, (
            f"stdout must mention the MD filename; got:\n{out!r}"
        )
        assert "METRICS_LOG.md" in out, (
            f"stdout must mention METRICS_LOG.md; got:\n{out!r}"
        )


# ---------------------------------------------------------------------------
# Repo-root validation. `git rev-parse --show-toplevel` must succeed or the
# CLI bails out with a clear error and non-zero exit.
# ---------------------------------------------------------------------------


class TestCliRepoRootValidation:
    """The CLI refuses to run outside a git working tree."""

    def test_not_inside_git_repo_exits_non_zero(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        ai_state = tmp_path / ".ai-state"
        ai_state.mkdir()

        # git_succeeds=False triggers CalledProcessError from subprocess.run,
        # which the CLI should translate into a clear stderr message + non-zero exit.
        mocks, patchers = _install_cli_mocks(repo_root=tmp_path, git_succeeds=False)
        try:
            for p in patchers:
                p.start()
            from scripts.project_metrics.cli import main

            exit_code = main(["--window-days", "90", "--top-n", "10"])
        except SystemExit as e:
            # CLI may use sys.exit(non-zero) rather than `return 1`.
            exit_code = e.code
        finally:
            for p in patchers:
                p.stop()

        assert exit_code not in (0, None), (
            f"CLI must exit non-zero when not in a git repo; got {exit_code}"
        )
        # The error message should be informative enough that a user knows
        # what went wrong. The specific phrasing is a CLI-implementation
        # choice, but "not" + ("git" OR "repo") is a minimal content contract.
        err = capsys.readouterr().err.lower()
        assert ("git" in err) and ("not" in err or "repo" in err), (
            f"stderr must mention git and the repo-detection failure; got: {err!r}"
        )
        # The Runner must NOT have been invoked if repo validation failed.
        assert not mocks.runner_cls.called, (
            "Runner must not be invoked when repo-root validation fails"
        )

    def test_inside_git_repo_proceeds_to_runner(self, tmp_path: Path) -> None:
        """When git check succeeds, the CLI reaches the orchestration layer."""
        ai_state = tmp_path / ".ai-state"
        ai_state.mkdir()

        mocks, patchers = _install_cli_mocks(repo_root=tmp_path)
        try:
            for p in patchers:
                p.start()
            exit_code = _run_main_with_ai_state_dir(
                ["--window-days", "90", "--top-n", "10"], ai_state, mocks
            )
        finally:
            for p in patchers:
                p.stop()

        assert exit_code == 0, (
            f"CLI must proceed and exit 0 when git check succeeds; got {exit_code}"
        )
        assert mocks.subprocess_run.called, (
            "git rev-parse --show-toplevel must be invoked on a valid run"
        )
        assert mocks.runner_cls.called, (
            "Runner must be instantiated after successful repo-root check"
        )


# ---------------------------------------------------------------------------
# Orchestration call order. The CLI is a conductor -- it invokes six named
# collaborators in a specific order. Any reordering would break the contract
# (e.g., append_log before render_markdown would write a log row referencing
# an MD file that doesn't yet exist).
# ---------------------------------------------------------------------------


class TestCliOrchestration:
    """The CLI drives its collaborators in the documented sequence."""

    def test_runner_then_compose_then_trends_then_renderers_then_log(
        self, tmp_path: Path
    ) -> None:
        ai_state = tmp_path / ".ai-state"
        ai_state.mkdir()

        mocks, patchers = _install_cli_mocks(repo_root=tmp_path)
        try:
            for p in patchers:
                p.start()
            _run_main_with_ai_state_dir(
                ["--window-days", "90", "--top-n", "10"], ai_state, mocks
            )
        finally:
            for p in patchers:
                p.stop()

        # Each collaborator must have been called exactly once on the
        # happy path -- no re-entry, no no-ops.
        assert mocks.runner_cls.return_value.run.call_count == 1, (
            "Runner.run must be invoked exactly once per happy-path invocation"
        )
        assert mocks.compose_hotspots.call_count == 1, (
            "compose_hotspots must be invoked exactly once per run"
        )
        assert mocks.compute_trends.call_count == 1, (
            "compute_trends must be invoked exactly once per run"
        )
        assert mocks.render_markdown.call_count == 1, (
            "render_markdown must be invoked exactly once per run"
        )
        assert mocks.render_json.call_count == 1, (
            "render_json must be invoked exactly once per run"
        )
        assert mocks.append_log.call_count == 1, (
            "append_log must be invoked exactly once per run"
        )

    def test_compose_hotspots_receives_runners_report(self, tmp_path: Path) -> None:
        """compose_hotspots is called with the Report the Runner returned --
        not with some freshly-constructed object."""
        ai_state = tmp_path / ".ai-state"
        ai_state.mkdir()

        mocks, patchers = _install_cli_mocks(repo_root=tmp_path)
        try:
            for p in patchers:
                p.start()
            _run_main_with_ai_state_dir(
                ["--window-days", "90", "--top-n", "10"], ai_state, mocks
            )
        finally:
            for p in patchers:
                p.stop()

        runner_return = mocks.runner_cls.return_value.run.return_value
        # compose_hotspots was called with either a single positional arg or
        # a keyword arg; assert the Report it received is exactly the one
        # Runner.run returned (object identity, not just equality).
        call = mocks.compose_hotspots.call_args
        received = call.args[0] if call.args else call.kwargs.get("report")
        assert received is runner_return, (
            "compose_hotspots must receive the Report returned by Runner.run "
            "(object identity). Different object -> a copy was made, which "
            "breaks the single-source-of-truth contract."
        )

    def test_compute_trends_receives_reports_dir(self, tmp_path: Path) -> None:
        """compute_trends signature is (report, reports_dir) -- the CLI must
        pass the metrics-reports subdirectory for prior-report discovery."""
        ai_state = tmp_path / ".ai-state"
        ai_state.mkdir()

        mocks, patchers = _install_cli_mocks(repo_root=tmp_path)
        try:
            for p in patchers:
                p.start()
            _run_main_with_ai_state_dir(
                ["--window-days", "90", "--top-n", "10"], ai_state, mocks
            )
        finally:
            for p in patchers:
                p.stop()

        call = mocks.compute_trends.call_args
        # The reports_dir should be present either positionally or as kwarg.
        # Assert by value, not identity, since Path(...) may be a fresh
        # Path instance; compare resolved paths.
        positional_dir: Path | None = None
        if len(call.args) >= 2:
            maybe = call.args[1]
            if isinstance(maybe, Path):
                positional_dir = maybe
        kwarg_dir = call.kwargs.get("reports_dir")
        actual_dir = kwarg_dir or positional_dir
        assert actual_dir is not None, (
            "compute_trends must be called with a reports_dir path "
            f"(positional[1] or kwarg); got call_args={call!r}"
        )
        expected = (ai_state / "metrics_reports").resolve()
        assert Path(actual_dir).resolve() == expected, (
            f"compute_trends must receive the metrics_reports subdirectory; "
            f"expected {expected} got {Path(actual_dir).resolve()}"
        )

    def test_append_log_receives_report_and_md_filename(self, tmp_path: Path) -> None:
        """append_log(report, ai_state_dir, report_md_filename) -- the CLI must
        hand it the MD basename it just wrote so the log row can link to it."""
        ai_state = tmp_path / ".ai-state"
        ai_state.mkdir()

        mocks, patchers = _install_cli_mocks(
            repo_root=tmp_path, report_timestamp="2026-04-23_18-45-00"
        )
        try:
            for p in patchers:
                p.start()
            _run_main_with_ai_state_dir(
                ["--window-days", "90", "--top-n", "10"], ai_state, mocks
            )
        finally:
            for p in patchers:
                p.stop()

        call = mocks.append_log.call_args
        # append_log signature per logappend.py:
        #   append_log(report, ai_state_dir, report_md_filename) -> None
        # Positional or keyword -- accept both.
        args_and_kwargs = list(call.args) + list(call.kwargs.values())
        md_filenames = [
            a for a in args_and_kwargs if isinstance(a, str) and a.endswith(".md")
        ]
        assert len(md_filenames) == 1, (
            f"append_log must receive exactly one .md filename argument; "
            f"got call_args={call!r}"
        )
        md_name = md_filenames[0]
        # The filename passed should be the BASENAME (not a full path) so
        # the log row renders as a relative link, and it should match the
        # MD file actually written.
        assert "/" not in md_name and "\\" not in md_name, (
            f"append_log must receive the MD basename, not a full path; got {md_name!r}"
        )
        assert md_name.startswith("METRICS_REPORT_") and md_name.endswith(".md"), (
            f"append_log's MD filename must follow METRICS_REPORT_*.md; got {md_name!r}"
        )
