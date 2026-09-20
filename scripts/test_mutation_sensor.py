"""Tests for scripts/mutation_sensor.py -- the per-step mutation sensor.

Safety property, mirrored from `resolve_test_scope.py`: *a count that is not known
to be complete must never be published as one.* Every refusal test therefore also
asserts the runner's `Mutation: unavailable reason=<code> (<detail>)` stdout shape
-- folded into the shared `_assert_refusal` helper below rather than a separate
test per reason code.

This file is written **before `scripts/mutation_sensor.py` exists** (concurrent-mode
BDD/TDD -- the test-engineer runs ahead of the implementer). The first collection of
this suite is expected to fail with `ModuleNotFoundError` for `mutation_sensor`; that
RED state is recorded in the test-engineer's test-results fragment, not silently
worked around.

Boundary discipline: the mutmut/uv subprocess is the only external system in scope,
and it is faked at the `subprocess.run` seam (`_install_fake_uv` below) for every
test except `TestRealMutmutSmoke`, which performs one genuinely real invocation --
required because the coverage-isolation claim below is about mutmut's *own* pytest
sub-invocations (`cwd=mutants/`, `--no-cov`), which no fake can exercise. The real
`git` binary is never faked -- `_install_fake_uv` passes any non-`uv` executable
through to the real `subprocess.run` unchanged, so the foreign-project-root lookup
(`git -C <dir> rev-parse --show-toplevel`) always runs for real.

Committed parser fixtures: `POST_RESULTS_TEXT` / `PRE_RESULTS_TEXT` below are copied
verbatim from a prior spike's real mutmut output (gitignored source under
`.ai-work/`) -- the only ground truth for the mutant-key regex. They carry the exact
shapes that defeat a naive `x_`-strip: `_base_ref_candidates` and `_step_owned_paths`
are private (leading underscore) functions, so their mutant keys read
`x__base_ref_candidates__mutmut_N` (double underscore) -- `str.lstrip("x_")` would eat
the leading `_` of the real name; only an anchored `^x_(?P<fn>.+?)__mutmut_` capture
preserves it.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS_DIR))

import mutation_sensor as ms  # noqa: E402

# ---------------------------------------------------------------------------
# Committed parser fixtures -- real `mutmut results` text, copied verbatim from
# a prior spike's gitignored output under .ai-work/.
# ---------------------------------------------------------------------------

POST_RESULTS_TEXT = """\
    _handoff_inputs.x_resolve_base_ref__mutmut_1: survived
    _handoff_inputs.x_resolve_base_ref__mutmut_14: survived
    _handoff_inputs.x__base_ref_candidates__mutmut_1: survived
    _handoff_inputs.x__base_ref_candidates__mutmut_2: survived
    _handoff_inputs.x__base_ref_candidates__mutmut_5: survived
    _handoff_inputs.x__base_ref_candidates__mutmut_6: survived
    _handoff_inputs.x__base_ref_candidates__mutmut_7: survived
    _handoff_inputs.x__base_ref_candidates__mutmut_8: survived
    _handoff_inputs.x__base_ref_candidates__mutmut_9: survived
    _handoff_inputs.x__base_ref_candidates__mutmut_10: survived
    _handoff_inputs.x__base_ref_candidates__mutmut_11: survived
    _handoff_inputs.x__base_ref_candidates__mutmut_12: survived
    _handoff_inputs.x__base_ref_candidates__mutmut_13: survived
    _handoff_inputs.x__base_ref_candidates__mutmut_14: survived
    _handoff_inputs.x__base_ref_candidates__mutmut_15: survived
    _handoff_inputs.x__base_ref_candidates__mutmut_16: survived
    _handoff_inputs.x__base_ref_candidates__mutmut_17: survived
    _handoff_inputs.x__base_ref_candidates__mutmut_18: survived
    _handoff_inputs.x__base_ref_candidates__mutmut_19: survived
    _handoff_inputs.x__base_ref_candidates__mutmut_20: survived
    _handoff_inputs.x__base_ref_candidates__mutmut_21: survived
    _handoff_inputs.x_artifact_names__mutmut_3: survived
    _handoff_inputs.x_artifact_names__mutmut_4: survived
    _handoff_inputs.x_artifact_names__mutmut_5: survived
    _handoff_inputs.x_artifact_names__mutmut_6: survived
    _handoff_inputs.x_recent_log__mutmut_6: survived
    _handoff_inputs.x_recent_log__mutmut_9: survived
    _handoff_inputs.x_recent_log__mutmut_10: survived
    _handoff_inputs.x__step_owned_paths__mutmut_1: survived
    _handoff_inputs.x__step_owned_paths__mutmut_2: survived
    _handoff_inputs.x__step_owned_paths__mutmut_4: survived
    _handoff_inputs.x__step_owned_paths__mutmut_6: survived
    _handoff_inputs.x__step_owned_paths__mutmut_7: survived
    _handoff_inputs.x__step_owned_paths__mutmut_8: survived
    _handoff_inputs.x__step_owned_paths__mutmut_9: survived
    _handoff_inputs.x__step_owned_paths__mutmut_10: survived
    _handoff_inputs.x_first_unfinished__mutmut_4: survived
    _handoff_inputs.x_first_unfinished__mutmut_5: survived
    _handoff_inputs.x_first_unfinished__mutmut_6: survived
    _handoff_inputs.x_first_unfinished__mutmut_7: survived
    _handoff_inputs.x_declared_files__mutmut_2: survived
    _handoff_inputs.x_declared_files__mutmut_7: survived
    _handoff_inputs.x_declared_files__mutmut_8: survived
    _handoff_inputs.x_declared_files__mutmut_11: survived
    _handoff_inputs.x_declared_files__mutmut_15: survived
    _handoff_inputs.x_declared_files__mutmut_16: survived
    _handoff_inputs.x_declared_files__mutmut_18: survived
    _handoff_inputs.x_declared_files__mutmut_22: survived
    _handoff_inputs.x_declared_files__mutmut_23: survived
    _handoff_readiness.x_dirty_paths__mutmut_8: survived
    _handoff_readiness.x_parse_porcelain_z__mutmut_9: timeout
    _handoff_readiness.x_parse_porcelain_z__mutmut_10: timeout
    _handoff_readiness.x_parse_porcelain_z__mutmut_12: survived
    _handoff_readiness.x_parse_porcelain_z__mutmut_13: survived
    _handoff_readiness.x_parse_porcelain_z__mutmut_16: timeout
    _handoff_readiness.x_parse_porcelain_z__mutmut_17: timeout
"""

PRE_RESULTS_TEXT = """\
    _handoff_readiness.x_dirty_paths__mutmut_1: survived
    _handoff_readiness.x_dirty_paths__mutmut_2: survived
    _handoff_readiness.x_dirty_paths__mutmut_5: survived
    _handoff_readiness.x_dirty_paths__mutmut_6: survived
    _handoff_readiness.x_dirty_paths__mutmut_7: survived
    _handoff_readiness.x_dirty_paths__mutmut_8: survived
    _handoff_readiness.x_dirty_paths__mutmut_9: survived
    _handoff_readiness.x_dirty_paths__mutmut_10: survived
    _handoff_readiness.x_dirty_paths__mutmut_11: survived
    _handoff_readiness.x_dirty_paths__mutmut_15: survived
    _handoff_readiness.x_dirty_paths__mutmut_16: survived
    _handoff_readiness.x_dirty_paths__mutmut_17: survived
    _handoff_readiness.x_dirty_paths__mutmut_18: survived
    _handoff_readiness.x_dirty_paths__mutmut_19: survived
    _handoff_readiness.x_dirty_paths__mutmut_22: survived
"""

# POST_RESULTS_TEXT's 56 lines: 52 survived + 4 timeout. `mutmut results` (non-`--all`)
# never shows killed mutants at all -- these totals are this fixture's ground truth,
# not invented: 52 + 149 (killed) + 4 (timeout) + 0 = 205, satisfying the runner's own
# cross-check invariant between its two mutmut sources.
CICD_STATS_FIXTURE = {
    "killed": 149,
    "survived": 52,
    "total": 205,
    "no_tests": 0,
    "skipped": 0,
    "suspicious": 0,
    "timeout": 4,
    "segfault": 0,
    "check_was_interrupted_by_user": False,
}

# PRE_RESULTS_TEXT's 15 lines are all survived, all `dirty_paths`. Totals invented
# (the source spike did not capture this run's JSON) but internally consistent with
# the runner's cross-check invariant.
PRE_CICD_STATS_FIXTURE = {
    "killed": 9,
    "survived": 15,
    "total": 24,
    "no_tests": 0,
    "skipped": 0,
    "suspicious": 0,
    "timeout": 0,
    "segfault": 0,
    "check_was_interrupted_by_user": False,
}

_UNAVAILABLE_LINE_RE = re.compile(
    r"^Mutation: unavailable reason=(?P<code>[a-z-]+) \((?P<detail>.+)\)$"
)


# ---------------------------------------------------------------------------
# Helpers -- the "how", kept out of test bodies (DAMP: what/why stays inline)
# ---------------------------------------------------------------------------


def _flat_git_dir(tmp_path: Path, *, name: str = "target") -> Path:
    """A flat directory (all files directly inside it) that is also a git repo,
    so the foreign-project-root lookup (`git -C <dir> rev-parse --show-toplevel`)
    resolves for real."""
    d = tmp_path / name
    d.mkdir()
    (d / "mod.py").write_text("def f(x):\n    return x + 1\n", encoding="utf-8")
    (d / "test_mod.py").write_text(
        "from mod import f\n\n\ndef test_f():\n    assert f(1) == 2\n", encoding="utf-8"
    )
    subprocess.run(["git", "init", "-q"], cwd=d, check=True)
    return d


def _install_fake_uv(monkeypatch: pytest.MonkeyPatch, plan: dict) -> list[list[str]]:
    """Patch `subprocess.run` so any `uv ...` invocation is faked per `plan`
    (keyed by the mutmut subcommand -- "run" | "export-cicd-stats" | "results" --
    or "__any__" for a failure before mutmut is ever reached, e.g. a bootstrap
    failure). Every other executable, `git` in particular, passes through to the
    real `subprocess.run` unchanged. Returns the captured argv lists, in call
    order, for every intercepted `uv` invocation.

    A behavior dict may set: `exit_code` (default 0), `stdout`, `stderr`,
    `raise_timeout` (raises `subprocess.TimeoutExpired` instead of returning),
    `write` (a `{relative_path: content}` map written under the call's `cwd`).
    """
    real_run = subprocess.run
    calls: list[list[str]] = []

    def fake_run(args, *a, **kw):
        argv = [str(x) for x in args]
        if Path(argv[0]).name != "uv":
            return real_run(args, *a, **kw)
        calls.append(argv)
        subcmd = None
        if "mutmut" in argv:
            idx = argv.index("mutmut")
            if idx + 1 < len(argv):
                subcmd = argv[idx + 1]
        behavior = plan.get(subcmd) or plan.get("__any__") or {"exit_code": 0}
        if behavior.get("raise_timeout"):
            raise subprocess.TimeoutExpired(cmd=argv, timeout=kw.get("timeout"))
        cwd = Path(kw.get("cwd") or ".")
        for rel, content in behavior.get("write", {}).items():
            p = cwd / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content, encoding="utf-8")
        return subprocess.CompletedProcess(
            args=argv,
            returncode=behavior.get("exit_code", 0),
            stdout=behavior.get("stdout", ""),
            stderr=behavior.get("stderr", ""),
        )

    monkeypatch.setattr(subprocess, "run", fake_run)
    return calls


def _success_plan() -> dict:
    return {
        "run": {},
        "export-cicd-stats": {
            "write": {"mutants/mutmut-cicd-stats.json": json.dumps(CICD_STATS_FIXTURE)}
        },
        "results": {"stdout": POST_RESULTS_TEXT},
    }


def _assert_refusal(rc: int, captured, reason: str) -> None:
    """Shared assertion for every refusal scenario below: exit code, the stderr
    detail line naming the reason, and the stdout `Mutation: unavailable` shape --
    discharging the stdout-shape assertion for every refusal test that calls this,
    rather than repeating it per reason code."""
    assert rc == ms.EXIT_ERROR, f"a refusal must exit {ms.EXIT_ERROR}, got {rc}"
    assert captured.err.lstrip().startswith(f"{reason}:"), (
        f"stderr must start with '{reason}: ' naming the offending path(s); got {captured.err!r}"
    )
    line = captured.out.strip()
    match = _UNAVAILABLE_LINE_RE.match(line)
    assert match, (
        f"stdout must be exactly one 'Mutation: unavailable reason=...' line; got {captured.out!r}"
    )
    assert match.group("code") == reason


# ---------------------------------------------------------------------------
# Flat-layout refusal: targets/tests spanning more than one directory
# ---------------------------------------------------------------------------


class TestFlatLayoutRefusal:
    def test_targets_and_tests_split_across_directories_refuses_before_any_run(
        self, tmp_path: Path, capsys: pytest.CaptureFixture, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        dir_a = tmp_path / "a"
        dir_b = tmp_path / "b"
        dir_a.mkdir()
        dir_b.mkdir()
        (dir_a / "mod.py").write_text("x = 1\n", encoding="utf-8")
        (dir_b / "test_mod.py").write_text("def test_x():\n    assert True\n", encoding="utf-8")
        calls = _install_fake_uv(monkeypatch, {})

        rc = ms.main(["--targets", str(dir_a / "mod.py"), "--tests", str(dir_b / "test_mod.py")])

        _assert_refusal(rc, capsys.readouterr(), "not-flat-layout")
        assert not calls, "a non-flat layout must never reach the mutmut invocation"


# ---------------------------------------------------------------------------
# An existing pyproject.toml is a refusal, and is never touched
# ---------------------------------------------------------------------------


class TestPyprojectPresentRefusal:
    def test_existing_pyproject_toml_refuses_and_is_left_byte_identical(
        self, tmp_path: Path, capsys: pytest.CaptureFixture, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        d = tmp_path / "target"
        d.mkdir()
        (d / "mod.py").write_text("x = 1\n", encoding="utf-8")
        (d / "test_mod.py").write_text("def test_x():\n    assert True\n", encoding="utf-8")
        existing = d / "pyproject.toml"
        existing.write_text("[tool.custom]\nkeep = true\n", encoding="utf-8")
        before = existing.read_bytes()
        calls = _install_fake_uv(monkeypatch, {})

        rc = ms.main(["--targets", str(d / "mod.py"), "--tests", str(d / "test_mod.py")])

        _assert_refusal(rc, capsys.readouterr(), "pyproject-present")
        assert existing.read_bytes() == before, "an existing pyproject.toml must never be clobbered"
        assert not calls, "a pyproject-present refusal must never reach the mutmut invocation"


# ---------------------------------------------------------------------------
# An existing mutants/ directory is a refusal, and is never touched
# ---------------------------------------------------------------------------


class TestMutantsDirPresentRefusal:
    def test_existing_mutants_dir_refuses_and_is_left_untouched(
        self, tmp_path: Path, capsys: pytest.CaptureFixture, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        d = tmp_path / "target"
        d.mkdir()
        (d / "mod.py").write_text("x = 1\n", encoding="utf-8")
        (d / "test_mod.py").write_text("def test_x():\n    assert True\n", encoding="utf-8")
        residue_dir = d / "mutants"
        residue_dir.mkdir()
        residue_file = residue_dir / "leftover.txt"
        residue_file.write_text("residue from a prior killed run\n", encoding="utf-8")
        calls = _install_fake_uv(monkeypatch, {})

        rc = ms.main(["--targets", str(d / "mod.py"), "--tests", str(d / "test_mod.py")])

        _assert_refusal(rc, capsys.readouterr(), "mutants-dir-present")
        assert residue_file.exists(), "the runner must never delete residue it did not create"
        assert not calls, "a mutants-dir-present refusal must never reach the mutmut invocation"


# ---------------------------------------------------------------------------
# uv missing from PATH, or the uv bootstrap itself fails
# ---------------------------------------------------------------------------


class TestToolchainMissingRefusal:
    def test_uv_not_on_path_refuses_toolchain_missing(
        self, tmp_path: Path, capsys: pytest.CaptureFixture, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        d = _flat_git_dir(tmp_path)
        # A restricted PATH carrying `git` (needed for the foreign-project-root
        # lookup, whichever check order the implementer chooses) but never `uv`.
        restricted_bin = tmp_path / "restricted-bin"
        restricted_bin.mkdir()
        git_path = shutil.which("git")
        assert git_path, "this test environment must have a real git on PATH"
        (restricted_bin / "git").symlink_to(git_path)
        monkeypatch.setenv("PATH", str(restricted_bin))

        rc = ms.main(["--targets", str(d / "mod.py"), "--tests", str(d / "test_mod.py")])

        _assert_refusal(rc, capsys.readouterr(), "toolchain-missing")

    def test_uv_bootstrap_failure_refuses_toolchain_missing(
        self, tmp_path: Path, capsys: pytest.CaptureFixture, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        d = _flat_git_dir(tmp_path)
        # uv is genuinely on PATH; every invocation of it fails immediately (e.g.
        # no network to resolve mutmut==3.8.0) before mutmut is ever reached.
        _install_fake_uv(
            monkeypatch, {"__any__": {"exit_code": 1, "stderr": "could not resolve mutmut==3.8.0"}}
        )

        rc = ms.main(["--targets", str(d / "mod.py"), "--tests", str(d / "test_mod.py")])

        _assert_refusal(rc, capsys.readouterr(), "toolchain-missing")


# ---------------------------------------------------------------------------
# A wall-clock timeout or a non-zero `mutmut run` is a refusal, not a partial
# reading -- and cleanup must still run.
#
# NOTE (surfaced to the planner, see the test-engineer's learnings fragment):
# these two tests require the runner to actually invoke `uv run ... mutmut run`
# and catch its failure, which is planned as a later increment than the runner
# skeleton this file is first tested against. They are expected to stay red
# until that invocation lands, not merely until the skeleton lands.
# ---------------------------------------------------------------------------


class TestRunTimeoutAndRunFailedRefusal:
    def test_mutmut_run_timeout_refuses_with_no_survivor_count(
        self, tmp_path: Path, capsys: pytest.CaptureFixture, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        d = _flat_git_dir(tmp_path)
        _install_fake_uv(
            monkeypatch, {"run": {"raise_timeout": True, "write": {"mutants/.marker": "x"}}}
        )

        rc = ms.main(
            ["--targets", str(d / "mod.py"), "--tests", str(d / "test_mod.py"), "--timeout", "1"]
        )

        captured = capsys.readouterr()
        _assert_refusal(rc, captured, "run-timeout")
        assert "survivors=" not in captured.out, (
            "a timeout must never publish a partial survivor count"
        )
        assert not (d / "mutants").exists(), "cleanup must run on the timeout path too"

    def test_mutmut_run_nonzero_exit_refuses_run_failed(
        self, tmp_path: Path, capsys: pytest.CaptureFixture, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        d = _flat_git_dir(tmp_path)
        _install_fake_uv(
            monkeypatch,
            {
                "run": {
                    "exit_code": 1,
                    "stderr": "mutmut crashed",
                    "write": {"mutants/.marker": "x"},
                }
            },
        )

        rc = ms.main(["--targets", str(d / "mod.py"), "--tests", str(d / "test_mod.py")])

        captured = capsys.readouterr()
        _assert_refusal(rc, captured, "run-failed")
        assert "survivors=" not in captured.out
        assert not (d / "mutants").exists(), "cleanup must run on the run-failed path too"


# ---------------------------------------------------------------------------
# The success line's shape: exit 0 regardless of survivor count, "no tests"
# folded into survivors, timeouts kept separate, top-5 + byte cap
# ---------------------------------------------------------------------------


class TestSurvivorCountingAndAttribution:
    def test_real_spike_fixture_produces_the_documented_line_shape(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
    ) -> None:
        d = _flat_git_dir(tmp_path)
        _install_fake_uv(monkeypatch, _success_plan())

        rc = ms.main(["--targets", str(d / "mod.py"), "--tests", str(d / "test_mod.py")])

        assert rc == ms.EXIT_OK, "a run exits 0 regardless of how many mutants survived"
        line = capsys.readouterr().out.strip()
        assert line.startswith("Mutation: survivors=52 mutants=205"), line
        assert "inconclusive=4" in line, (
            "the 4 timeout mutants must be reported separately, never folded in"
        )
        # 9 distinct functions carry survivors; top 5 by count are unambiguous
        # (19, 9, 8, 4, 4 vs. the next-highest 3).
        for fn_count in ("_base_ref_candidates: 19", "declared_files: 9", "_step_owned_paths: 8"):
            assert fn_count in line, line
        assert "artifact_names: 4" in line, line
        assert "first_unfinished: 4" in line, line
        assert "recent_log" not in line, "recent_log (count 3) must be excluded from the top-5"
        assert "+4 more" in line, "9 functions total, top-5 shown -- the truncation tail"
        assert len(line.encode("utf-8")) <= 240, (
            f"the line's hard byte cap, got {len(line.encode('utf-8'))}"
        )

    def test_no_tests_status_counts_as_a_survivor_not_as_clean(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
    ) -> None:
        d = _flat_git_dir(tmp_path)
        stats = dict(CICD_STATS_FIXTURE, survived=1, no_tests=1, killed=0, total=2, timeout=0)
        plan = {
            "run": {},
            "export-cicd-stats": {"write": {"mutants/mutmut-cicd-stats.json": json.dumps(stats)}},
            "results": {
                "stdout": ("    mod.x_f__mutmut_1: survived\n    mod.x_f__mutmut_2: no tests\n")
            },
        }
        _install_fake_uv(monkeypatch, plan)

        rc = ms.main(["--targets", str(d / "mod.py"), "--tests", str(d / "test_mod.py")])

        assert rc == ms.EXIT_OK
        line = capsys.readouterr().out.strip()
        assert "survivors=2" in line, (
            f"'no tests' must count as a survivor alongside 'survived' -- got {line!r}"
        )
        assert "f: 2" in line


# ---------------------------------------------------------------------------
# --json carries the full per-function map and the exact rendered line
# ---------------------------------------------------------------------------


class TestJsonOutput:
    def test_json_carries_the_full_per_function_map_and_the_rendered_line(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
    ) -> None:
        d = _flat_git_dir(tmp_path)
        _install_fake_uv(monkeypatch, _success_plan())

        rc = ms.main(["--targets", str(d / "mod.py"), "--tests", str(d / "test_mod.py"), "--json"])

        assert rc == ms.EXIT_OK
        payload = json.loads(capsys.readouterr().out)
        assert payload["outcome"] == "ran"
        assert payload["per_function"]["_base_ref_candidates"] == 19
        assert payload["per_function"]["dirty_paths"] == 1, (
            "the full map, not just the top-5 shown on stdout"
        )
        assert sum(payload["per_function"].values()) == 52
        assert isinstance(payload["elapsed_s"], (int, float))
        assert str(d / "mod.py") in payload["targets"]
        assert payload["line"].startswith("Mutation: survivors=52"), (
            "the JSON carries the exact rendered line too"
        )

    def test_json_refused_outcome_names_the_reason(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
    ) -> None:
        d = tmp_path / "target"
        d.mkdir()
        (d / "mod.py").write_text("x = 1\n", encoding="utf-8")
        (d / "test_mod.py").write_text("def test_x():\n    assert True\n", encoding="utf-8")
        (d / "pyproject.toml").write_text("[tool.custom]\n", encoding="utf-8")
        _install_fake_uv(monkeypatch, {})

        rc = ms.main(["--targets", str(d / "mod.py"), "--tests", str(d / "test_mod.py"), "--json"])

        assert rc == ms.EXIT_ERROR
        payload = json.loads(capsys.readouterr().out)
        assert payload["outcome"] == "refused"
        assert payload["reason"] == "pyproject-present"


# ---------------------------------------------------------------------------
# Cleanup on the success path (the timeout/run-failed paths are covered in
# TestRunTimeoutAndRunFailedRefusal above)
# ---------------------------------------------------------------------------


class TestCleanupOnSuccessPath:
    def test_successful_run_leaves_no_mutants_dir_or_generated_pyproject(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        d = _flat_git_dir(tmp_path)
        _install_fake_uv(monkeypatch, _success_plan())

        rc = ms.main(["--targets", str(d / "mod.py"), "--tests", str(d / "test_mod.py")])

        assert rc == ms.EXIT_OK
        assert not (d / "mutants").exists(), "mutants/ must be removed after a successful run too"
        assert not (d / "pyproject.toml").exists(), "the generated pyproject.toml must be removed"


# ---------------------------------------------------------------------------
# The uv --project root comes from the TARGET's own git toplevel, never the
# runner's own repository
# ---------------------------------------------------------------------------


class TestForeignProjectRootDerivation:
    def test_project_root_is_the_targets_git_toplevel_not_the_runners_own(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        outer = tmp_path / "outer_repo"
        outer.mkdir()
        subprocess.run(["git", "init", "-q"], cwd=outer, check=True)
        d = outer / "pkg"
        d.mkdir()
        (d / "mod.py").write_text("def f(x):\n    return x + 1\n", encoding="utf-8")
        (d / "test_mod.py").write_text(
            "from mod import f\n\n\ndef test_f():\n    assert f(1) == 2\n", encoding="utf-8"
        )
        calls = _install_fake_uv(monkeypatch, _success_plan())

        rc = ms.main(["--targets", str(d / "mod.py"), "--tests", str(d / "test_mod.py")])

        assert rc == ms.EXIT_OK
        expected_root = str(outer.resolve())
        assert any(
            "--project" in c and c[c.index("--project") + 1] == expected_root for c in calls
        ), (
            f"--project must be the target's own git toplevel ({expected_root}), not the runner's; got {calls}"
        )


# ---------------------------------------------------------------------------
# One real end-to-end invocation. Every assertion above fakes uv/mutmut at the
# subprocess boundary; this is the deliberate exception -- the coverage
# isolation claim below is about mutmut's *own* pytest sub-invocations, which
# no fake can exercise. Needs `uv` on PATH and network access to resolve
# mutmut==3.8.0 on a cold cache; a two-mutant fixture module is expected to run
# in low single-digit seconds once cached.
# ---------------------------------------------------------------------------


class TestRealMutmutSmoke:
    def test_real_run_reports_survivors_and_leaves_repo_coverage_untouched(
        self, tmp_path: Path
    ) -> None:
        d = tmp_path / "target"
        d.mkdir()
        (d / "flaky.py").write_text("def add_one(x):\n    return x + 1\n", encoding="utf-8")
        (d / "test_flaky.py").write_text(
            "from flaky import add_one\n\n\n"
            "def test_add_one_is_deliberately_loose():\n"
            "    # Accepts both 2 and 3 so mutmut's off-by-one mutant survives --\n"
            "    # this smoke test needs a mixed killed/survived run, not all-killed.\n"
            "    assert add_one(1) in (2, 3)\n",
            encoding="utf-8",
        )
        subprocess.run(["git", "init", "-q"], cwd=d, check=True)

        repo_root = SCRIPTS_DIR.parent
        coverage_xml = repo_root / "coverage.xml"
        dot_coverage = repo_root / ".coverage"
        before_xml = coverage_xml.read_bytes() if coverage_xml.exists() else None
        before_cov = dot_coverage.read_bytes() if dot_coverage.exists() else None

        rc = ms.main(
            [
                "--targets",
                str(d / "flaky.py"),
                "--tests",
                str(d / "test_flaky.py"),
                "--timeout",
                "120",
            ]
        )

        after_xml = coverage_xml.read_bytes() if coverage_xml.exists() else None
        after_cov = dot_coverage.read_bytes() if dot_coverage.exists() else None
        assert rc == ms.EXIT_OK, "exit 0 regardless of survivor count"
        assert before_xml == after_xml, (
            "repo-root coverage.xml must be byte-identical around the run"
        )
        assert before_cov == after_cov, "repo-root .coverage must be byte-identical around the run"
        assert not (d / "mutants").exists(), "cleanup must run after a real invocation too"
        assert not (d / "pyproject.toml").exists()
