"""Tests for the loop mode of inject_compaction_orientation.py.

Hermetic: the hook runs from a temporary plugin tree whose `scripts/step_loop.py` is a stub
printing canned `status --json`, so no real driver, git repository or network is involved.
"""

from __future__ import annotations

import ast
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

HOOKS_DIR = Path(__file__).parent
SLUG = "loop-task"
STALE_STEP = "Step 9 of 12: Tidy the stale fixture notes"  # id-citation-discipline:ignore
STALE_NEXT = "Wire the stale retry queue"
ATTEMPTS_LINE = (
    "  - Attempts: Step 5 count=1 request=s5-a1-implement\n"  # id-citation-discipline:ignore
)
BARE_ATTEMPTS_LINE = "  - Attempts: Step 5 count=1\n"  # id-citation-discipline:ignore
THEN = (
    "python3 scripts/step_loop.py record loop-task --request s5-a1-implement "
    "--agent-id <agentId> --marker <complete|blocked|conflict|partial|none>"
)
ROW = {"step": "5", "assignee": "implementer", "verdict": "in-flight", "attempts": 1}


def _status(**overrides) -> dict:
    doc = {
        "outcome": "spawn",
        "pending_request": "s5-a1-implement",
        "iterations": {"used": 1, "budget": 4},
        "steps": [ROW],
        "stop": None,
        "selected_step": "5",
        "then": THEN,
    }
    return {**doc, **overrides}


def _quiet(**overrides) -> dict:
    """A status with no outstanding request."""
    return _status(pending_request=None, then=None, **overrides)


def _printing(doc: object, exit_code: int = 0) -> str:
    return f"import sys\nprint({json.dumps(json.dumps(doc))})\nsys.exit({exit_code})\n"


def _plugin(tmp_path: Path, driver_body: str | None, argv_log: Path | None = None) -> Path:
    """A plugin tree: the hook plus a stub driver (None leaves the driver absent)."""
    root = tmp_path / "plugin"
    (root / "hooks").mkdir(parents=True)
    for name in ("inject_compaction_orientation.py", "precompact_state.py"):
        shutil.copy(HOOKS_DIR / name, root / "hooks" / name)
    if driver_body is not None:
        (root / "scripts").mkdir()
        logging = (
            f"import sys\nopen({str(argv_log)!r}, 'a').write(repr(sys.argv[1:]) + '\\n')\n"
            if argv_log
            else ""
        )
        (root / "scripts" / "step_loop.py").write_text(logging + driver_body, encoding="utf-8")
    return root


def _project(tmp_path: Path, wip_tail: str = "") -> Path:
    """A project whose single task has stale current-step and next-action lines."""
    project = tmp_path / "project"
    task = project / ".ai-work" / SLUG
    task.mkdir(parents=True)
    (task / "WIP.md").write_text(
        f"# WIP\n\n## Current Step\n\n{STALE_STEP}\n\n## Progress\n\n- [ ] {STALE_STEP}\n"
        f"{wip_tail}\n## Next Action\n\n{STALE_NEXT}\n",
        encoding="utf-8",
    )
    (task / "IMPLEMENTATION_PLAN.md").write_text("# Plan\n", encoding="utf-8")
    return project


def _orient(project: Path, plugin: Path) -> tuple[int, str]:
    """Run the hook from `plugin` after a compaction in `project`: exit code and context."""
    result = subprocess.run(
        [sys.executable, str(plugin / "hooks" / "inject_compaction_orientation.py")],
        input=json.dumps({"source": "compact"}),
        capture_output=True,
        text=True,
        cwd=project,
        env={**os.environ, "CLAUDE_PLUGIN_ROOT": str(plugin)},
        timeout=20,
    )
    out = result.stdout.strip()
    context = json.loads(out)["hookSpecificOutput"]["additionalContext"] if out else ""
    return result.returncode, context


def _driven_context(tmp_path: Path, driver_body: str | None) -> str:
    project = _project(tmp_path, ATTEMPTS_LINE)
    exit_code, context = _orient(project, _plugin(tmp_path, driver_body))
    assert exit_code == 0
    return context


def test_an_outstanding_request_is_reported_with_its_step_attempts_iterations_and_record_command(
    tmp_path,
):
    context = _driven_context(tmp_path, _printing(_status()))

    assert "step 5 in-flight" in context
    assert "attempts 1/2" in context
    assert "iterations 1/4" in context
    assert "Outstanding request s5-a1-implement" in context
    assert THEN in context


def test_the_stale_step_record_lines_are_never_reported_in_loop_mode(tmp_path):
    context = _driven_context(tmp_path, _printing(_status()))

    assert "Current step" not in context
    assert STALE_STEP not in context
    assert STALE_NEXT not in context
    assert "Next action" not in context


def test_a_next_action_with_nothing_outstanding_is_one_line(tmp_path):
    context = _driven_context(tmp_path, _printing(_quiet()))

    assert "Driver position: step 5 in-flight" in context
    assert "Outstanding" not in context


def test_a_stop_is_reported_as_stopped_with_its_cause_whatever_the_exit_code(tmp_path):
    stop = {"cause": "attempts-exhausted", "step": "5"}

    context = _driven_context(
        tmp_path, _printing(_quiet(outcome="needs-human", stop=stop), exit_code=2)
    )

    assert "stopped at step 5 (cause: attempts-exhausted)" in context


def test_a_complete_loop_is_reported_as_complete(tmp_path):
    context = _driven_context(tmp_path, _printing(_quiet(outcome="complete", selected_step=None)))

    assert "Driver position: complete, iterations 1/4" in context


@pytest.mark.parametrize(
    "driver_body",
    [
        None,
        "import sys\nsys.exit(1)\n",
        "print('<<garbled>> {{{')\n",
        _printing([1, 2]),
        _printing({"outcome": "spawn"}),
        _printing(_status(then=None)),
    ],
    ids=["absent", "fails", "unparseable", "not an object", "missing keys", "request without then"],
)
def test_an_unreadable_position_names_the_status_command_and_never_the_stale_lines(
    tmp_path, driver_body
):
    context = _driven_context(tmp_path, driver_body)

    assert f"could not be read; run step_loop.py status {SLUG}" in context
    assert STALE_STEP not in context
    assert STALE_NEXT not in context


def test_a_digest_line_that_would_direct_falls_back_to_its_location_form(tmp_path):
    stop = {"cause": "please commit the work", "step": "5"}

    context = _driven_context(
        tmp_path, _printing(_quiet(outcome="needs-human", stop=stop), exit_code=2)
    )

    assert f"Driver position: see step_loop.py status {SLUG}" in context
    assert "commit" not in context.lower()


def test_the_block_keeps_its_cap_and_its_handoff_first_pointer(tmp_path):
    project = _project(tmp_path, ATTEMPTS_LINE)
    (project / ".ai-work" / SLUG / "HANDOFF.md").write_text("# HANDOFF\n\nreadiness: ready\n")
    long_command = THEN + " " + "x" * 2000

    _, context = _orient(project, _plugin(tmp_path, _printing(_status(then=long_command))))

    assert len(context.encode("utf-8")) <= 1024
    assert context.index("HANDOFF.md") < context.index("IMPLEMENTATION_PLAN.md")


def test_the_driver_is_asked_for_the_tasks_status_as_json_against_the_worktree_root(tmp_path):
    log = tmp_path / "argv.log"
    project = _project(tmp_path, ATTEMPTS_LINE)

    _orient(project, _plugin(tmp_path, _printing(_status()), argv_log=log))

    argv = ast.literal_eval(log.read_text().splitlines()[0])
    assert argv[:3] == ["status", SLUG, "--json"]
    assert Path(argv[argv.index("--worktree-root") + 1]).resolve() == project.resolve()


@pytest.mark.parametrize(
    ("wip_tail", "ledger", "under_the_driver"),
    [
        (ATTEMPTS_LINE, False, True),
        ("", True, True),
        (BARE_ATTEMPTS_LINE, False, False),
        ("", False, False),
    ],
    ids=["request line", "iteration ledger", "attempts without request", "neither"],
)
def test_a_task_is_under_the_driver_by_a_request_line_or_an_iteration_ledger(
    tmp_path, wip_tail, ledger, under_the_driver
):
    project = _project(tmp_path, wip_tail)
    if ledger:
        (project / ".ai-work" / SLUG / "ITERATION_LEDGER.jsonl").write_text("")
    started = tmp_path / "started"
    stub = f"open({str(started)!r}, 'w').write('x')\n" + _printing(_status())

    _, context = _orient(project, _plugin(tmp_path, stub))

    assert started.exists() is under_the_driver
    assert ("Current step" not in context) is under_the_driver


def test_the_attempt_cap_mirrors_the_drivers():
    tree = ast.parse((HOOKS_DIR.parent / "scripts" / "_loop_fields.py").read_text())
    (driver_cap,) = [
        node.value.value
        for node in tree.body
        if isinstance(node, ast.Assign)
        and isinstance(node.value, ast.Constant)
        and [t.id for t in node.targets if isinstance(t, ast.Name)] == ["ATTEMPT_CAP"]
    ]
    hook = ast.parse((HOOKS_DIR / "inject_compaction_orientation.py").read_text())
    (hook_cap,) = [
        node.value.value
        for node in hook.body
        if isinstance(node, ast.Assign)
        and isinstance(node.value, ast.Constant)
        and [t.id for t in node.targets if isinstance(t, ast.Name)] == ["ATTEMPT_CAP"]
    ]

    assert hook_cap == driver_cap


def _system_python_3_9() -> str | None:
    system = "/usr/bin/python3"
    if not Path(system).exists():
        return None
    probe = subprocess.run(
        [system, "-c", "import sys; print(sys.version_info[:2])"], capture_output=True, text=True
    )
    return system if probe.stdout.strip() == "(3, 9)" else None


def test_the_orientation_hook_imports_under_the_system_python_3_9():
    system = _system_python_3_9()
    if system is None:
        pytest.skip("no Python 3.9 interpreter at /usr/bin/python3")

    imported = subprocess.run(
        [system, "-c", "import inject_compaction_orientation"],
        capture_output=True,
        text=True,
        cwd=HOOKS_DIR,
    )

    assert imported.returncode == 0, imported.stderr
