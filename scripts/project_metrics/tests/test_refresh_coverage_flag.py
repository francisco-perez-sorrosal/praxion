"""Behavioral tests for the ``--refresh-coverage`` opt-in flag on ``cli.py``.

These tests encode the contract the implementer must satisfy when wiring
the test-coverage skill's refresh path into ``scripts/project_metrics/cli.py``:

* The default (no-flag) orchestration sequence remains byte-equivalent to
  the pre-change behavior -- no skill invocation, no extra subprocess.
* With ``--refresh-coverage`` present, the refresh runs exactly once and
  strictly before the existing read-only ``Runner.run(...)`` call.
* Refresh failures (any raised exception from the skill-invocation helper)
  are swallowed: a stderr warning is emitted, the pipeline continues, and
  the process exits 0. ``/project-metrics`` must never hard-fail because
  of a refresh failure.
* The "no coverage target discoverable" branch is a sub-case of the above
  -- the helper raises, the CLI warns and continues.

Interface contract mocked here (the implementer owns the name and
shape):

    scripts.project_metrics.cli._refresh_coverage_artifact(repo_root: Path) -> None

Failure contract: the helper raises an exception on any failure condition
(missing target, tool absent, non-zero exit from the invoked target).
The CLI catches ``Exception`` broadly, writes a stderr warning, and
continues into the existing read-only orchestration. The specific
exception type is not part of the contract -- the CLI's handling is type-
agnostic by design.

Call-site contract: the helper is imported at module top of ``cli.py``
(so ``scripts.project_metrics.cli._refresh_coverage_artifact`` is a
stable ``unittest.mock.patch`` attachment point, consistent with the
pattern used for ``Runner``, ``compose_hotspots``, etc.) and is invoked
exactly once per ``--refresh-coverage`` run, strictly before
``Runner(...).run(...)``.

Import strategy -- every test imports ``main`` inside its body so the
pytest collection phase does not collapse into a single ``ImportError``
during the BDD/TDD RED handshake (the helper does not yet exist in
``cli.py``). Deferred imports yield per-test RED/GREEN resolution with a
specific ``ImportError`` or ``AttributeError`` per test.

Mock surface parallels ``test_cli.py``: we install the same stack of
patches for the existing orchestration collaborators plus one additional
patch for the new ``_refresh_coverage_artifact`` helper. This keeps the
CLI exercised in isolation and makes the ``--refresh-coverage`` wiring
the only real code under test.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, call, patch

import pytest

# ---------------------------------------------------------------------------
# Test-data builders -- mirror the structure in ``test_cli.py`` so a mocked
# Runner returns a fully-populated Report object the downstream orchestration
# can forward unchanged.
# ---------------------------------------------------------------------------


def _minimal_aggregate_kwargs() -> dict[str, Any]:
    """Build a full 16-field kwargs dict for AggregateBlock with populated values."""
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
    """Construct a schema-valid Report the mocked Runner can return."""
    from scripts.project_metrics.schema import AggregateBlock, Report

    aggregate = AggregateBlock(**_minimal_aggregate_kwargs())
    return Report(
        schema_version="1.0.0",
        aggregate=aggregate,
        tool_availability={},
        collectors={},
    )


# ---------------------------------------------------------------------------
# Mock installer -- same philosophy as ``test_cli.py``'s ``_install_cli_mocks``
# but extended with the new ``_refresh_coverage_artifact`` patch point.
# ---------------------------------------------------------------------------


class _MockedCollaborators:
    """Holder for the MagicMocks installed at the CLI module's import points.

    Extends the base CLI mock set with the new helper the implementer will
    expose for the refresh path: ``_refresh_coverage_artifact``.
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
        self.refresh_coverage: MagicMock = MagicMock(name="_refresh_coverage_artifact")


def _install_cli_mocks(
    *,
    repo_root: Path,
    report_timestamp: str = "2026-04-23_18-45-00",
) -> tuple[_MockedCollaborators, list[Any]]:
    """Install the full mock stack for a CLI run under test.

    Returns (holder, patchers). Caller starts the patchers in order; the
    ``_refresh_coverage_artifact`` patcher is added to the tail of the list
    so that tests which mutate its ``side_effect`` (to simulate a refresh
    failure) can reach it consistently before entering the ``with`` region.
    """

    mocks = _MockedCollaborators()

    synthetic_report = _build_synthetic_report()
    runner_instance = MagicMock(name="RunnerInstance")
    runner_instance.run.return_value = synthetic_report
    mocks.runner_cls.return_value = runner_instance

    mocks.compose_aggregate.return_value = synthetic_report
    mocks.compose_hotspots.return_value = synthetic_report

    from scripts.project_metrics.schema import TrendBlock

    mocks.compute_trends.return_value = TrendBlock(status="first_run")
    mocks.render_markdown.return_value = "# Metrics Report\n\n(mocked)\n"
    mocks.render_json.return_value = b'{"schema_version":"1.0.0"}'
    mocks.append_log.return_value = None

    # git rev-parse --show-toplevel always succeeds in these tests; we are
    # exercising the refresh-flag branch, not the repo-detection branch.
    completed = MagicMock(name="CompletedProcess")
    completed.returncode = 0
    completed.stdout = str(repo_root) + "\n"
    mocks.subprocess_run.return_value = completed

    # datetime mocking -- pin the filename timestamp.
    now_mock = MagicMock(name="datetime.now")
    now_mock.strftime.return_value = report_timestamp
    mocks.datetime_module.now.return_value = now_mock
    mocks.datetime_module.UTC = MagicMock(name="UTC")

    # The refresh helper defaults to a no-op returning None.
    mocks.refresh_coverage.return_value = None

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
        patch(
            "scripts.project_metrics.cli.subprocess.run",
            mocks.subprocess_run,
        ),
        patch(
            "scripts.project_metrics.cli.datetime",
            mocks.datetime_module,
        ),
        # The new helper. Mocked at module-top import site so the call-site
        # in ``main`` resolves through this patched symbol; this matches the
        # convention documented in ``LEARNINGS.md`` (import the helper at
        # module top, not inside ``main``, so ``patch`` attachment is stable).
        patch(
            "scripts.project_metrics.cli._refresh_coverage_artifact",
            mocks.refresh_coverage,
        ),
    ]
    return mocks, patchers


def _run_main(argv: list[str], ai_state_dir: Path, mocks: _MockedCollaborators) -> int:
    """Invoke ``main(argv)`` pointed at a pytest-managed ``.ai-state/`` dir.

    The CLI derives its output directory as ``<repo_root>/.ai-state/``, so
    we set the mocked ``subprocess.run`` stdout to ``ai_state_dir.parent``.
    """
    completed = MagicMock(name="CompletedProcess")
    completed.returncode = 0
    completed.stdout = str(ai_state_dir.parent) + "\n"
    mocks.subprocess_run.return_value = completed
    mocks.subprocess_run.side_effect = None

    from scripts.project_metrics.cli import main

    return main(argv)


# ---------------------------------------------------------------------------
# Default (no-flag) behavior. The CLI without ``--refresh-coverage`` must be
# byte-equivalent to the pre-change orchestration: no refresh-helper invocation,
# no additional subprocess, no stderr noise.
# ---------------------------------------------------------------------------


class TestDefaultBehaviorUnchanged:
    """Without the flag, the refresh helper is never invoked."""

    def test_absent_flag_does_not_invoke_refresh_helper(self, tmp_path: Path) -> None:
        ai_state = tmp_path / ".ai-state"
        ai_state.mkdir()

        mocks, patchers = _install_cli_mocks(repo_root=tmp_path)
        try:
            for p in patchers:
                p.start()
            exit_code = _run_main(["--window-days", "90", "--top-n", "10"], ai_state, mocks)
        finally:
            for p in patchers:
                p.stop()

        assert exit_code == 0, (
            f"Default invocation must exit 0; got {exit_code}. "
            "The flag-absent path must remain identical to pre-change behavior."
        )
        assert not mocks.refresh_coverage.called, (
            "Without --refresh-coverage, the refresh helper must NOT be called. "
            f"Observed calls: {mocks.refresh_coverage.call_args_list!r}. "
            "The opt-in semantic is broken if the helper runs by default."
        )

    def test_absent_flag_preserves_runner_invocation(self, tmp_path: Path) -> None:
        """Sanity: the pre-change Runner.run(...) orchestration still runs."""
        ai_state = tmp_path / ".ai-state"
        ai_state.mkdir()

        mocks, patchers = _install_cli_mocks(repo_root=tmp_path)
        try:
            for p in patchers:
                p.start()
            _run_main(["--window-days", "90", "--top-n", "10"], ai_state, mocks)
        finally:
            for p in patchers:
                p.stop()

        assert mocks.runner_cls.return_value.run.call_count == 1, (
            "Default path must still call Runner.run exactly once; "
            f"got {mocks.runner_cls.return_value.run.call_count}."
        )

    def test_absent_flag_emits_no_stderr_warning(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """No refresh attempted -> no refresh-related warning on stderr."""
        ai_state = tmp_path / ".ai-state"
        ai_state.mkdir()

        mocks, patchers = _install_cli_mocks(repo_root=tmp_path)
        try:
            for p in patchers:
                p.start()
            _run_main(["--window-days", "90", "--top-n", "10"], ai_state, mocks)
        finally:
            for p in patchers:
                p.stop()

        err = capsys.readouterr().err.lower()
        # The pre-change cli.py emits stderr only on git-rev-parse failure.
        # Without the flag, there must be no "refresh"/"coverage" warning.
        assert "refresh" not in err, (
            f"Default path must not mention 'refresh' on stderr; stderr was: {err!r}"
        )


# ---------------------------------------------------------------------------
# Flag-present, helper succeeds. The helper runs exactly once, strictly
# before the existing ``Runner.run(...)`` call.
# ---------------------------------------------------------------------------


class TestFlagInvokesRefreshBeforeRunner:
    """With ``--refresh-coverage`` and a succeeding helper, ordering is strict."""

    def test_flag_present_invokes_refresh_helper_exactly_once(self, tmp_path: Path) -> None:
        ai_state = tmp_path / ".ai-state"
        ai_state.mkdir()

        mocks, patchers = _install_cli_mocks(repo_root=tmp_path)
        try:
            for p in patchers:
                p.start()
            exit_code = _run_main(
                ["--refresh-coverage", "--window-days", "90", "--top-n", "10"],
                ai_state,
                mocks,
            )
        finally:
            for p in patchers:
                p.stop()

        assert exit_code == 0, f"--refresh-coverage happy path must exit 0; got {exit_code}."
        assert mocks.refresh_coverage.call_count == 1, (
            "--refresh-coverage must invoke the refresh helper exactly once; "
            f"got {mocks.refresh_coverage.call_count} invocations."
        )

    def test_flag_present_invokes_refresh_before_runner(self, tmp_path: Path) -> None:
        """Strict ordering: the refresh helper runs strictly before Runner.run.

        Asserted via a shared parent ``MagicMock`` so ``mock_calls`` records a
        single totally-ordered sequence across both the helper and the Runner
        instance. If the implementer reverses the order, this test fails with
        an index mismatch the failure message explains.
        """
        ai_state = tmp_path / ".ai-state"
        ai_state.mkdir()

        mocks, patchers = _install_cli_mocks(repo_root=tmp_path)

        # Wire a shared parent so mock_calls is globally ordered.
        parent = MagicMock(name="OrderParent")
        parent.attach_mock(mocks.refresh_coverage, "refresh_coverage")
        parent.attach_mock(mocks.runner_cls, "Runner")

        try:
            for p in patchers:
                p.start()
            _run_main(
                ["--refresh-coverage", "--window-days", "90", "--top-n", "10"],
                ai_state,
                mocks,
            )
        finally:
            for p in patchers:
                p.stop()

        # Collect the names of the top-level method calls on the parent, in
        # order. Filter to the two we attached so intermediate ``_.mock_calls``
        # chatter (from internal MagicMock machinery) does not distort order.
        top_level = [
            name.split(".")[0]
            for name, _args, _kwargs in parent.mock_calls
            if name and name.split(".")[0] in {"refresh_coverage", "Runner"}
        ]
        assert "refresh_coverage" in top_level, (
            "refresh_coverage helper was never recorded in the ordered call "
            f"sequence. Observed: {top_level!r}."
        )
        assert "Runner" in top_level, (
            f"Runner was never recorded in the ordered call sequence. Observed: {top_level!r}."
        )
        refresh_index = top_level.index("refresh_coverage")
        runner_index = top_level.index("Runner")
        assert refresh_index < runner_index, (
            "Ordering violation: the refresh helper must run BEFORE "
            "Runner(...) / Runner.run(...). "
            f"Ordered sequence observed: {top_level!r}. "
            f"refresh_coverage at index {refresh_index}, Runner at {runner_index}."
        )

    def test_flag_present_passes_repo_root_to_refresh_helper(self, tmp_path: Path) -> None:
        """The helper receives the resolved repo root -- same Path the CLI derives
        for ``.ai-state/`` and hands to ``compute_trends``."""
        ai_state = tmp_path / ".ai-state"
        ai_state.mkdir()

        mocks, patchers = _install_cli_mocks(repo_root=tmp_path)
        try:
            for p in patchers:
                p.start()
            _run_main(
                ["--refresh-coverage", "--window-days", "90", "--top-n", "10"],
                ai_state,
                mocks,
            )
        finally:
            for p in patchers:
                p.stop()

        assert mocks.refresh_coverage.called, (
            "Precondition failed: helper must be called on --refresh-coverage path"
        )
        call_args = mocks.refresh_coverage.call_args
        # Accept positional or keyword -- the implementer's choice.
        args_and_kwargs = list(call_args.args) + list(call_args.kwargs.values())
        path_args = [a for a in args_and_kwargs if isinstance(a, Path)]
        assert len(path_args) == 1, (
            "Refresh helper must receive exactly one Path argument (the repo root); "
            f"got call_args={call_args!r}."
        )
        received_path = path_args[0]
        assert Path(received_path).resolve() == tmp_path.resolve(), (
            f"Refresh helper must receive the repo root; "
            f"expected {tmp_path.resolve()}, got {Path(received_path).resolve()}."
        )


# ---------------------------------------------------------------------------
# Flag-present, helper fails. The CLI must warn on stderr and continue into
# the existing pipeline -- graceful degradation per the plan.
# ---------------------------------------------------------------------------


class TestFlagFailureIsGracefullyDegraded:
    """Any exception from the helper is swallowed: warn + continue + exit 0."""

    def test_helper_raises_generic_exception_still_exits_zero(self, tmp_path: Path) -> None:
        """The helper raises a generic ``RuntimeError`` (representative of
        "skill invocation failed" -- tool absent, non-zero exit, etc.). The
        CLI must catch, warn, and continue."""
        ai_state = tmp_path / ".ai-state"
        ai_state.mkdir()

        mocks, patchers = _install_cli_mocks(repo_root=tmp_path)
        mocks.refresh_coverage.side_effect = RuntimeError("coverage target exited non-zero")
        try:
            for p in patchers:
                p.start()
            exit_code = _run_main(
                ["--refresh-coverage", "--window-days", "90", "--top-n", "10"],
                ai_state,
                mocks,
            )
        finally:
            for p in patchers:
                p.stop()

        assert exit_code == 0, (
            "A refresh failure must NOT break /project-metrics. "
            f"Expected exit 0 (graceful degradation); got {exit_code}."
        )

    def test_helper_raises_and_runner_still_runs(self, tmp_path: Path) -> None:
        """Graceful-degradation contract: after the helper raises, the existing
        read-only orchestration still runs to completion."""
        ai_state = tmp_path / ".ai-state"
        ai_state.mkdir()

        mocks, patchers = _install_cli_mocks(repo_root=tmp_path)
        mocks.refresh_coverage.side_effect = RuntimeError("simulated refresh failure")
        try:
            for p in patchers:
                p.start()
            _run_main(
                ["--refresh-coverage", "--window-days", "90", "--top-n", "10"],
                ai_state,
                mocks,
            )
        finally:
            for p in patchers:
                p.stop()

        assert mocks.runner_cls.return_value.run.call_count == 1, (
            "After a helper failure, Runner.run must STILL be invoked exactly "
            "once (graceful degradation). "
            f"Got {mocks.runner_cls.return_value.run.call_count} invocations."
        )
        assert mocks.append_log.called, (
            "After a helper failure, append_log must still run (the read-only "
            "pipeline proceeds to completion)."
        )

    def test_helper_raises_emits_stderr_warning(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """A refresh failure is a warning, not a silent swallow. The user must
        see something on stderr naming 'refresh' or 'coverage' so they know
        the fresh-numbers pre-pass did not happen."""
        ai_state = tmp_path / ".ai-state"
        ai_state.mkdir()

        mocks, patchers = _install_cli_mocks(repo_root=tmp_path)
        mocks.refresh_coverage.side_effect = RuntimeError("no coverage target discoverable")
        try:
            for p in patchers:
                p.start()
            _run_main(
                ["--refresh-coverage", "--window-days", "90", "--top-n", "10"],
                ai_state,
                mocks,
            )
        finally:
            for p in patchers:
                p.stop()

        err = capsys.readouterr().err.lower()
        # Minimal content contract: stderr mentions the refresh/coverage
        # context so the user can connect the warning to the flag they used.
        assert "refresh" in err or "coverage" in err, (
            "Helper failure must emit a stderr warning naming 'refresh' or "
            "'coverage' so the user knows the pre-pass was skipped. "
            f"stderr was: {err!r}."
        )


# ---------------------------------------------------------------------------
# Flag-present, no coverage target discoverable. This is a specific case of
# "helper fails" -- the helper raises and the CLI warns + continues. Treated
# as a separate test so a future regression that special-cases
# ``FileNotFoundError`` differently from other failures is caught.
# ---------------------------------------------------------------------------


class TestFlagNoTargetDiscoverableFallsThrough:
    """The "no target found" branch is indistinguishable from other failures."""

    def test_helper_raises_file_not_found_is_handled_the_same(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        ai_state = tmp_path / ".ai-state"
        ai_state.mkdir()

        mocks, patchers = _install_cli_mocks(repo_root=tmp_path)
        mocks.refresh_coverage.side_effect = FileNotFoundError(
            "no pixi tasks, no pyproject pytest-cov config, no Makefile target"
        )
        try:
            for p in patchers:
                p.start()
            exit_code = _run_main(
                ["--refresh-coverage", "--window-days", "90", "--top-n", "10"],
                ai_state,
                mocks,
            )
        finally:
            for p in patchers:
                p.stop()

        assert exit_code == 0, (
            "A 'no target discoverable' outcome must still exit 0; "
            f"got {exit_code}. The CLI cannot hard-fail on missing coverage infra."
        )
        assert mocks.runner_cls.return_value.run.call_count == 1, (
            "Missing-target must not block the read-only pipeline from running."
        )
        err = capsys.readouterr().err.lower()
        assert "refresh" in err or "coverage" in err, (
            f"Missing-target case must still emit a stderr warning; got: {err!r}."
        )


# ---------------------------------------------------------------------------
# Argparse surface. The flag must be recognized by argparse and default to
# absent/False. A bare ``--refresh-coverage`` with no value (store_true) is
# the documented shape.
# ---------------------------------------------------------------------------


class TestArgparseRecognizesFlag:
    """``--refresh-coverage`` is accepted by argparse without a value."""

    def test_flag_accepted_without_value(self, tmp_path: Path) -> None:
        """store_true shape: the flag takes no argument."""
        ai_state = tmp_path / ".ai-state"
        ai_state.mkdir()

        mocks, patchers = _install_cli_mocks(repo_root=tmp_path)
        try:
            for p in patchers:
                p.start()
            # If argparse rejected the flag, this would raise SystemExit(2).
            exit_code = _run_main(["--refresh-coverage"], ai_state, mocks)
        finally:
            for p in patchers:
                p.stop()

        assert exit_code == 0, (
            "--refresh-coverage with no other args must be accepted by argparse "
            f"and run under defaults; got exit {exit_code}. If this test fails "
            "with SystemExit(2), the argparse surface is missing the flag."
        )

    def test_help_output_mentions_refresh_coverage_flag(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """--help must advertise --refresh-coverage so users discover the opt-in."""
        mocks, patchers = _install_cli_mocks(repo_root=tmp_path)
        try:
            for p in patchers:
                p.start()
            from scripts.project_metrics.cli import main

            with pytest.raises(SystemExit):
                main(["--help"])
        finally:
            for p in patchers:
                p.stop()

        combined = capsys.readouterr().out + capsys.readouterr().err
        # capsys.readouterr() consumes the buffer; one call is enough but we
        # combine stdout+stderr from a single call to be safe across pytest
        # configuration variants.
        # (The above sequence actually consumes twice; rebuild via re-capture.)
        # Simpler, reliable approach: the Python argparse convention is that
        # --help writes to stdout. We check the prior combined string -- if
        # empty, fall back to the structural assertion that the flag name is
        # in the parser's help formatting.
        if "--refresh-coverage" not in combined:
            # Fallback: build the parser directly and check its help string.
            from scripts.project_metrics.cli import _build_parser

            help_text = _build_parser().format_help()
            assert "--refresh-coverage" in help_text, (
                "Help output must advertise --refresh-coverage; "
                f"format_help() returned:\n{help_text}"
            )


# ---------------------------------------------------------------------------
# Edge: the flag does not accidentally re-invoke on a retry path. One flag,
# one call, even if the helper's side-effect structure tempts a retry.
# ---------------------------------------------------------------------------


class TestFlagSingleInvocationPerRun:
    """One ``--refresh-coverage`` invocation yields exactly one helper call."""

    def test_helper_called_once_on_success(self, tmp_path: Path) -> None:
        ai_state = tmp_path / ".ai-state"
        ai_state.mkdir()

        mocks, patchers = _install_cli_mocks(repo_root=tmp_path)
        try:
            for p in patchers:
                p.start()
            _run_main(["--refresh-coverage"], ai_state, mocks)
        finally:
            for p in patchers:
                p.stop()

        assert (
            mocks.refresh_coverage.call_args_list
            == [
                call(tmp_path),
            ]
            or mocks.refresh_coverage.call_count == 1
        ), (
            "The refresh helper must be invoked exactly once per run; "
            f"got {mocks.refresh_coverage.call_count} invocations. "
            f"call_args_list={mocks.refresh_coverage.call_args_list!r}."
        )

    def test_helper_called_once_even_on_failure(self, tmp_path: Path) -> None:
        """A failing refresh must NOT be retried silently."""
        ai_state = tmp_path / ".ai-state"
        ai_state.mkdir()

        mocks, patchers = _install_cli_mocks(repo_root=tmp_path)
        mocks.refresh_coverage.side_effect = RuntimeError("boom")
        try:
            for p in patchers:
                p.start()
            _run_main(["--refresh-coverage"], ai_state, mocks)
        finally:
            for p in patchers:
                p.stop()

        assert mocks.refresh_coverage.call_count == 1, (
            "A failing refresh must not be retried; "
            f"got {mocks.refresh_coverage.call_count} invocations."
        )
