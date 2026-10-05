"""The reconciler's `--json` output is the verdict array, whatever `WIP.md` holds.

An `Attempts:` line that names no step is a human matter: the reconciler reports it
on stderr in both output modes and exits 2, and stdout stays what a consumer of the
verdict array expects.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import reconcile_pipeline_state as rps  # noqa: E402

SLUG = "demo-task"
STEP = "Step "
PLAN = f"### {STEP}1: build\n**Files**: `src/foo.py`\n"
UNNAMED_LINES = ["step 3 count=5", "3 count=2"]
NEEDS_A_HUMAN = 2


def wip_with(attempts_lines: list[str]) -> str:
    return f"- [x] {STEP}1: build\n" + "".join(f"  - Attempts: {t}\n" for t in attempts_lines)


@pytest.fixture
def run_main(tmp_path, monkeypatch, capsys):
    """Run `main` over a one-step pipeline; return (exit code, stdout, stderr)."""

    def run(wip: str, *argv: str) -> tuple[int, str, str]:
        task_dir = tmp_path / ".ai-work" / SLUG
        task_dir.mkdir(parents=True)
        (task_dir / "WIP.md").write_text(wip, encoding="utf-8")
        (task_dir / "IMPLEMENTATION_PLAN.md").write_text(PLAN, encoding="utf-8")
        monkeypatch.setattr(rps, "resolve_repo_root", lambda *_a, **_k: tmp_path)
        monkeypatch.setattr(rps, "is_plugin_cache_path", lambda *_a, **_k: False)
        monkeypatch.setattr(rps, "_git_changed_files", lambda *_a, **_k: {"src/foo.py"})
        exit_code = rps.main([SLUG, *argv])
        captured = capsys.readouterr()
        return exit_code, captured.out, captured.err

    return run


@pytest.mark.parametrize("text", UNNAMED_LINES)
def test_json_stdout_is_the_verdict_array_when_a_line_names_no_step(run_main, text):
    exit_code, out, _ = run_main(wip_with([text]), "--json")

    verdicts = json.loads(out)
    assert [v["step"] for v in verdicts] == [f"{STEP}1"]
    assert exit_code == NEEDS_A_HUMAN


@pytest.mark.parametrize("flags", [("--json",), ()], ids=["json", "human"])
def test_every_unnamed_line_is_reported_on_stderr_in_either_output_mode(run_main, flags):
    _, _, err = run_main(wip_with(UNNAMED_LINES), *flags)

    assert [ln for ln in err.splitlines() if "names no step" in ln] == [
        f"reconcile_pipeline_state: WIP.md Attempts line names no step: {t}" for t in UNNAMED_LINES
    ]


def test_the_human_report_is_the_verdict_lines_alone_on_stdout(run_main):
    exit_code, out, _ = run_main(wip_with(UNNAMED_LINES))

    assert len(out.splitlines()) == 1
    assert out.split()[:2] == f"{STEP}1".split()
    assert exit_code == NEEDS_A_HUMAN


def test_json_stdout_is_the_array_and_stderr_is_silent_when_every_line_names_its_step(run_main):
    exit_code, out, err = run_main(wip_with([f"{STEP}1 count=2"]), "--json")

    assert isinstance(json.loads(out), list)
    assert "names no step" not in err
    assert exit_code == rps._exit_code(json.loads(out))
