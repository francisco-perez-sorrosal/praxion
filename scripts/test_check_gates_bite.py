"""Tests for `check_gates_bite.py` -- the gate-liveness command.

The failure mode this closes: a liveness run that passes because a probe is
missing, crashed, hung, or looked at the wrong checkout. The command must turn
each of those into a failed verdict with an `expected ...; observed ...` reason,
keep running the remaining probes, and exit 1; a usage or root error exits 2.
Probes are stubbed through the registry; the real ones have their own tests.
"""

from __future__ import annotations

import json
import os
import runpy
import subprocess
import sys
import textwrap
import time
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS_DIR))

import check_gates_bite as cgb  # noqa: E402
from gate_probes.verdict import GateId  # noqa: E402

SCRIPT = SCRIPTS_DIR / "check_gates_bite.py"
STUB_MODULE = "liveness_stub_probes"
PASSING = "return Verdict(gate=GateId.{gate}, passed=True, reason='', elapsed_s=0.0)"
FAILING = (
    "return Verdict(gate=GateId.{gate}, passed=False, "
    "reason='expected a catch; observed a pass', elapsed_s=0.0)"
)


def install_probes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, **bodies: str) -> None:
    """Write a stub probe module and register `gate=function` entries for each body.

    `bodies` maps a function name to its source body; the registry then points the
    gate named by the function's `<behaviour>_<gate>` suffix at it.
    """
    source = ["from gate_probes.verdict import GateId, Verdict", "import time", ""]
    registry: dict[GateId, str] = {}
    for name, body in bodies.items():
        source.append(f"def {name}(repo_root, env):\n{textwrap.indent(body, '    ')}\n")
        registry[GateId(name.split("__")[1].replace("_", "-"))] = f"{STUB_MODULE}:{name}"
    (tmp_path / f"{STUB_MODULE}.py").write_text("\n".join(source), encoding="utf-8")
    monkeypatch.syspath_prepend(str(tmp_path))
    monkeypatch.setattr(cgb, "PROBE_ENTRYPOINTS", registry)


def run_report(
    capsys: pytest.CaptureFixture[str], root: Path, *argv: str
) -> tuple[int, dict[str, object]]:
    code = cgb.main(["--json", "--repo-root", str(root), *argv])
    return code, json.loads(capsys.readouterr().out)


def verdict_for(report: dict[str, object], gate: str) -> dict[str, object]:
    return next(entry for entry in report["verdicts"] if entry["gate"] == gate)


def test_probe_exception_becomes_a_failed_verdict_and_later_probes_still_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    install_probes(
        tmp_path,
        monkeypatch,
        explode__mutation_sensor="raise RuntimeError('kaboom')",
        pass__observation_hooks=PASSING.format(gate="OBSERVATION_HOOKS"),
    )

    code, report = run_report(
        capsys, tmp_path, "--gate", "mutation-sensor", "--gate", "observation-hooks"
    )

    crashed = verdict_for(report, "mutation-sensor")
    assert crashed["passed"] is False
    assert crashed["reason"] == (
        "expected the probe to return a verdict; observed it failed with exit 3: "
        "RuntimeError: kaboom"
    )
    assert verdict_for(report, "observation-hooks")["passed"] is True
    assert code == 1


def test_probe_timeout_fails_the_gate_with_a_reason(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    install_probes(
        tmp_path,
        monkeypatch,
        hang__spawn_count="time.sleep(120)",
        pass__selection_audit=PASSING.format(gate="SELECTION_AUDIT"),
    )
    monkeypatch.setattr(cgb, "TIME_LIMITS_S", dict.fromkeys(GateId, 1.0))
    started = time.monotonic()

    code, report = run_report(
        capsys, tmp_path, "--gate", "spawn-count", "--gate", "selection-audit"
    )

    hung = verdict_for(report, "spawn-count")
    assert hung["passed"] is False
    assert (
        hung["reason"] == "expected the probe to finish within 1 s; observed it was still running"
    )
    assert verdict_for(report, "selection-audit")["passed"] is True
    assert time.monotonic() - started < 30
    assert code == 1


def test_plugin_cache_root_is_rejected_with_exit_two(
    capsys: pytest.CaptureFixture[str],
) -> None:
    code = cgb.main(["--json", "--repo-root", "/home/u/.claude/plugins/cache/owner/praxion/1.0"])

    assert code == 2
    assert "plugin cache" in capsys.readouterr().err


def test_unimplemented_probe_fails_instead_of_passing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(
        cgb, "PROBE_ENTRYPOINTS", {gate: f"no_such_probe_module_{gate.name}:run" for gate in GateId}
    )

    code, report = run_report(capsys, tmp_path)

    assert [entry["gate"] for entry in report["verdicts"]] == [gate.value for gate in GateId]
    assert all(entry["passed"] is False for entry in report["verdicts"])
    assert [entry["reason"] for entry in report["verdicts"]] == [
        f"expected a probe module no_such_probe_module_{gate.name}; observed probe not "
        f"implemented (ModuleNotFoundError: No module named 'no_such_probe_module_{gate.name}')"
        for gate in GateId
    ]
    assert report["passed"] is False
    assert code == 1


def test_probe_stdout_noise_does_not_corrupt_the_report(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    install_probes(
        tmp_path,
        monkeypatch,
        noisy__spawn_count="print('progress...')\n" + PASSING.format(gate="SPAWN_COUNT"),
    )

    code, report = run_report(capsys, tmp_path, "--gate", "spawn-count")

    assert verdict_for(report, "spawn-count")["passed"] is True
    assert code == 0


def test_probe_that_exits_without_a_verdict_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    install_probes(tmp_path, monkeypatch, quit__spawn_count="raise SystemExit(0)")

    code, report = run_report(capsys, tmp_path, "--gate", "spawn-count")

    failed = verdict_for(report, "spawn-count")
    assert failed["reason"] == (
        "expected the probe to return a verdict; observed it failed with exit 3: SystemExit: 0"
    )
    assert code == 1


def test_missing_dependency_inside_a_probe_is_not_reported_as_unimplemented(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    install_probes(tmp_path, monkeypatch, broken__spawn_count="import no_such_dependency_xyz")

    _, report = run_report(capsys, tmp_path, "--gate", "spawn-count")

    reason = verdict_for(report, "spawn-count")["reason"]
    assert "no_such_dependency_xyz" in reason
    assert "not implemented" not in reason


def test_exit_code_is_one_when_any_gate_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    install_probes(
        tmp_path,
        monkeypatch,
        pass__mutation_sensor=PASSING.format(gate="MUTATION_SENSOR"),
        fail__spawn_count=FAILING.format(gate="SPAWN_COUNT"),
    )

    code, report = run_report(
        capsys, tmp_path, "--gate", "mutation-sensor", "--gate", "spawn-count"
    )

    assert code == 1
    assert report["passed"] is False


def test_exit_code_is_zero_when_every_selected_gate_passes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    install_probes(
        tmp_path,
        monkeypatch,
        pass__mutation_sensor=PASSING.format(gate="MUTATION_SENSOR"),
        pass__spawn_count=PASSING.format(gate="SPAWN_COUNT"),
    )

    code, report = run_report(
        capsys, tmp_path, "--gate", "spawn-count", "--gate", "mutation-sensor"
    )

    assert code == 0
    assert report["passed"] is True
    assert [entry["gate"] for entry in report["verdicts"]] == ["mutation-sensor", "spawn-count"]
    assert all(entry["elapsed_s"] > 0 for entry in report["verdicts"])


def test_probe_reporting_another_gate_or_no_verdict_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    install_probes(
        tmp_path,
        monkeypatch,
        wrong__mutation_sensor=PASSING.format(gate="SPAWN_COUNT"),
        none__spawn_count="return None",
    )

    code, report = run_report(
        capsys, tmp_path, "--gate", "mutation-sensor", "--gate", "spawn-count"
    )

    assert [entry["reason"] for entry in report["verdicts"]] == [
        "expected a verdict for mutation-sensor; observed one for spawn-count",
        "expected the probe to return a verdict; observed it failed with exit 3: "
        "TypeError: the probe returned None, not a Verdict",
    ]
    assert code == 1


def test_probe_env_is_scrubbed_of_session_and_credential_variables(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    leaked = (
        "CLAUDE_CODE_X",
        "PRAXION_Y",
        "GIT_DIR",
        "ANTHROPIC_API_KEY",
        "GH_TOKEN",
        "GITHUB_TOKEN",
    )
    for name in leaked:
        monkeypatch.setenv(name, "secret")
    monkeypatch.setenv("LIVENESS_KEPT", "1")
    install_probes(
        tmp_path,
        monkeypatch,
        env__spawn_count=(
            "bad = sorted(k for k in env if k.startswith(('CLAUDE', 'PRAXION_', 'GIT_', "
            "'ANTHROPIC_')) or k in ('GH_TOKEN', 'GITHUB_TOKEN'))\n"
            "kept = 'LIVENESS_KEPT' in env\n"
            "return Verdict(gate=GateId.SPAWN_COUNT, passed=True, reason='', elapsed_s=0.0, "
            "notes=(','.join(bad), str(kept)))"
        ),
    )

    _, report = run_report(capsys, tmp_path, "--gate", "spawn-count")

    assert verdict_for(report, "spawn-count")["notes"] == ["", "True"]


def test_human_output_names_each_failing_gate_and_its_reason(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    install_probes(
        tmp_path,
        monkeypatch,
        pass__mutation_sensor=PASSING.format(gate="MUTATION_SENSOR"),
        fail__spawn_count=FAILING.format(gate="SPAWN_COUNT"),
    )

    code = cgb.main(
        ["--repo-root", str(tmp_path), "--gate", "mutation-sensor", "--gate", "spawn-count"]
    )

    out = capsys.readouterr().out
    assert code == 1
    assert "FAIL spawn-count" in out
    assert "expected a catch; observed a pass" in out
    assert "PASS mutation-sensor" in out


def test_repo_root_comes_from_git_when_no_flag_is_given(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    project = tmp_path / "project"
    (project / "sub").mkdir(parents=True)
    subprocess.run(["git", "init", "-q", str(project)], check=True)
    install_probes(
        tmp_path,
        monkeypatch,
        where__spawn_count=(
            "return Verdict(gate=GateId.SPAWN_COUNT, passed=True, reason='', elapsed_s=0.0, "
            "notes=(str(repo_root),))"
        ),
    )
    monkeypatch.chdir(project / "sub")

    cgb.main(["--json", "--gate", "spawn-count"])

    notes = json.loads(capsys.readouterr().out)["verdicts"][0]["notes"]
    assert notes == [str(project.resolve())]


def test_run_outside_any_repository_is_rejected_with_exit_two(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "argv", [str(SCRIPT), "--json"])

    with pytest.raises(SystemExit) as raised:
        runpy.run_path(str(SCRIPT), run_name="__main__")

    assert raised.value.code == 2
    assert "repository" in capsys.readouterr().err


def test_unknown_gate_is_rejected_with_exit_two(tmp_path: Path) -> None:
    assert cgb.main(["--repo-root", str(tmp_path), "--gate", "no-such-gate"]) == 2


def test_run_leaves_the_checkout_unchanged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = tmp_path / "checkout"
    root.mkdir()
    (root / "tracked.txt").write_text("a", encoding="utf-8")
    install_probes(tmp_path, monkeypatch, pass__spawn_count=PASSING.format(gate="SPAWN_COUNT"))

    run_report(capsys, root, "--gate", "spawn-count")

    assert [p.name for p in root.rglob("*")] == ["tracked.txt"]


def test_script_is_executable_with_a_python_shebang() -> None:
    assert os.access(SCRIPT, os.X_OK)
    assert SCRIPT.read_text(encoding="utf-8").startswith("#!/usr/bin/env python3\n")
