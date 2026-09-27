"""End-to-end proof: every real writer records exactly what the registry says.

`test_observation_log_writer.py` unit-tests `record()`/`record_tool_call` in
isolation, against the *package* copy of `_observation_log`. This module
drives the real hooks instead -- `capture_session.py`, `capture_observations.py`,
`measure_context_surface.py`, and the `_hook_utils.record_gate_fire` shim --
in-process, once per mode, and treats the appended log file as ground truth.

Why the file, not a spy on `writer.record`: a spy cannot see a writer that
bypasses `record()` and calls `append_observation` directly -- exactly the
historical `record_gate_fire` defect, which ignored the mode kill switch
entirely. A spy-derived check would also make "written iff recorded"
tautological, because `record()` itself computes that predicate.

Why class attribution is declared per scenario step, not inferred: the
scenario table below is this test's own statement of "this writer, given
this input, emits this class." A writer that silently reclassifies its
output (e.g. `measure_context_surface` passing the wrong `EventClass`) is
caught because the declared class and the registry's mode table disagree
about whether a row should have been written at all.

Patch-target rule: this module never imports `hooks._observation_log`. Every
writer, registry, and mode reference below comes from the copy the loaded
hooks themselves imported (`_observation_log`, resolved through `HOOKS_DIR`
on `sys.path`) -- never the dotted `hooks._observation_log` package. Mixing
the two is the dual-copy hazard: a canary patched onto the wrong copy passes
vacuously, because the hooks never call through it.
"""

from __future__ import annotations

import importlib
import importlib.util
import io
import json
import os
import re
import sys
from collections import namedtuple
from pathlib import Path

import pytest

HOOKS_DIR = Path(__file__).resolve().parent
REPO_ROOT = HOOKS_DIR.parent

# One scenario step: `driver` names the writer entry point that executes it
# (a hook module, or `record_gate_fire`); `payload`
# holds the event-specific keys (merged over the base session/cwd/transcript
# payload for hook drivers, or passed as kwargs for `record_gate_fire`);
# `expected` is the tuple of `Expect` this step should produce, in order.
Step = namedtuple("Step", ("name", "driver", "payload", "expected"))

# `event_class` is the registry's EventClass *string value* (e.g.
# "agent_stop"), parsed at run time through the loaded hooks' own
# `EventClass(value)` -- never a class object bound at module scope, so this
# module needs no top-level `_observation_log` import. `absent_ok` binds an
# exemption to this one (step, class), never to a class globally.
Expect = namedtuple("Expect", ("event_class", "absent_ok"))
Expect.__new__.__defaults__ = (frozenset(),)

Violation = namedtuple("Violation", ("step", "kind", "detail"))

# The suspension `agent_stop` (a Stop-time transcript backfill, not a real
# SubagentStop delivery) never has a subagent transcript to sum usage from,
# so it lacks the seven usage fields every other `agent_stop` row carries.
# Consumers already read them with `.get()` -- see
# scripts/project_metrics/collectors/cost_collector.py and
# scripts/workflow_run_cost.py.
_SUSPENSION_ABSENT_OK = frozenset(
    {
        "tokens_in",
        "tokens_out",
        "cache_read",
        "cache_create",
        "duration_ms",
        "model",
        "usage_source",
    }
)

# The only registry class this scenario deliberately does not drive, and why.
_NOT_DRIVEN = {"recovery": "written by /resume-pipeline prose; bypasses the writer"}

# The non-test modules that import the writer today. T2 below keeps this set
# equal to what a repo scan actually finds, so "drives every writer" stays
# true once a new writer module is added.
DRIVEN_WRITER_MODULES = frozenset(
    {
        "hooks/capture_session.py",
        "hooks/capture_observations.py",
        "hooks/measure_context_surface.py",
        "hooks/_hook_utils.py",
    }
)

# Order matters: the first-call marker (steps 5-6) and the WAL lookups
# (steps 10-11, 14) depend on rows written by earlier steps.
SCENARIO: tuple[Step, ...] = (
    Step(
        "session_start",
        "capture_session",
        {"hook_event_name": "SessionStart", "source": "startup"},
        (Expect("session_start"),),
    ),
    Step(
        "context_surface",
        "measure_context_surface",
        {"hook_event_name": "SessionStart"},
        (Expect("context_surface_measurement"),),
    ),
    Step(
        "agent_start a1",
        "capture_session",
        {"hook_event_name": "SubagentStart", "agent_id": "a1", "agent_type": "praxion:researcher"},
        (Expect("agent_start"),),
    ),
    Step(
        "agent_start a2",
        "capture_session",
        {"hook_event_name": "SubagentStart", "agent_id": "a2", "agent_type": "praxion:implementer"},
        (Expect("agent_start"),),
    ),
    Step(
        "tool Read",
        "capture_observations",
        {
            "hook_event_name": "PostToolUse",
            "tool_name": "Read",
            "tool_input": {"file_path": "x.py"},
            "tool_response": {},
            "agent_id": "a1",
            "agent_type": "praxion:researcher",
        },
        (Expect("tool_first_of_subagent"),),
    ),
    Step(
        "tool Grep",
        "capture_observations",
        {
            "hook_event_name": "PostToolUse",
            "tool_name": "Grep",
            "tool_input": {"pattern": "p"},
            "tool_response": {},
            "agent_id": "a1",
            "agent_type": "praxion:researcher",
        },
        (Expect("tool_other"),),
    ),
    Step(
        "tool Write",
        "capture_observations",
        {
            "hook_event_name": "PostToolUse",
            "tool_name": "Write",
            "tool_input": {"file_path": "y.py", "content": "c"},
            "tool_response": {},
            "agent_id": "a1",
            "agent_type": "praxion:researcher",
        },
        (Expect("tool_file_change"),),
    ),
    Step(
        "tool Bash",
        "capture_observations",
        {
            "hook_event_name": "PostToolUse",
            "tool_name": "Bash",
            "tool_input": {"command": "ls"},
            "tool_response": {},
        },
        (Expect("tool_other"),),
    ),
    Step(
        "tool Skill",
        "capture_observations",
        {
            "hook_event_name": "PostToolUse",
            "tool_name": "Skill",
            "tool_input": {"skill": "foo"},
            "tool_response": {},
        },
        (Expect("skill_activation"),),
    ),
    Step(
        "agent_stop a1",
        "capture_session",
        {"hook_event_name": "SubagentStop", "agent_id": "a1", "agent_type": "praxion:researcher"},
        (Expect("agent_stop"),),
    ),
    Step(
        "helper_stop h1",
        "capture_session",
        {"hook_event_name": "SubagentStop", "agent_id": "h1"},
        (Expect("helper_stop"),),
    ),
    Step(
        "compaction",
        "capture_session",
        {"hook_event_name": "PostCompact", "trigger": "auto", "compact_summary": "s"},
        (Expect("compaction"),),
    ),
    Step(
        "gate_fire",
        "record_gate_fire",
        {"hook": "check_x", "decision": "pass", "reason": "ok", "session_id": "S1"},
        (Expect("gate_fire"),),
    ),
    Step(
        "stop + suspension",
        "capture_session",
        {"hook_event_name": "Stop"},
        (Expect("session_stop"), Expect("agent_stop", _SUSPENSION_ABSENT_OK)),
    ),
)


# ---------------------------------------------------------------------------
# Harness: load the real hooks, build the fixture tree, drive the scenario.
# ---------------------------------------------------------------------------


def _load(name: str):
    """Load a hook module from its file, the same idiom as
    `test_capture_session_helper_stop.py`'s `_load_module`. Puts `HOOKS_DIR`
    on `sys.path` first so the hook's own `from _observation_log import ...`
    and `from _hook_utils import ...` resolve.
    """
    if str(HOOKS_DIR) not in sys.path:
        sys.path.insert(0, str(HOOKS_DIR))
    spec = importlib.util.spec_from_file_location(name, HOOKS_DIR / f"{name}.py")
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _build_project(tmp_path: Path) -> tuple[Path, Path, Path]:
    """Build the fixture tree the scenario drives against.

    Returns `(proj, parent_transcript, marker_dir)`. `proj/CLAUDE.md` is
    non-empty so `measure_context_surface`'s `measure()` reports non-zero
    bytes; the parent transcript carries one suspended-subagent
    task-notification for `a2` (step 14 backfills its `agent_stop`); a1's
    own subagent transcript exists so its stop sums real usage instead of
    falling back to the parent's.
    """
    proj = tmp_path / "proj"
    (proj / ".ai-state").mkdir(parents=True)
    (proj / "CLAUDE.md").write_text("# fixture project\n", encoding="utf-8")

    tx = tmp_path / "tx"
    tx.mkdir()
    parent = tx / "S1.jsonl"
    parent.write_text(
        json.dumps(
            {
                "type": "user",
                "message": {
                    "content": (
                        "<task-notification><task-id>a2</task-id>"
                        "<summary>Agent x stopped at its 80-turn limit</summary>"
                        "</task-notification>"
                    )
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )
    own_transcript = tx / "S1" / "subagents" / "agent-a1.jsonl"
    own_transcript.parent.mkdir(parents=True)
    own_transcript.write_text(
        json.dumps(
            {
                "type": "assistant",
                "agentId": "a1",
                "timestamp": "2026-09-26T00:00:00+00:00",
                "message": {"model": "m", "usage": {"input_tokens": 1, "output_tokens": 1}},
            }
        )
        + "\n",
        encoding="utf-8",
    )

    marker_dir = tmp_path / "marker-tmp"
    marker_dir.mkdir()
    return proj, parent, marker_dir


def _isolate_env(monkeypatch: pytest.MonkeyPatch, mode: str, marker_dir: Path) -> None:
    """No host `PRAXION_*` value, no network, and a private marker dir --
    `os.environ` is a single object, so this reaches both `writer.record`'s
    `env=os.environ` default and `capture_session`'s own `resolve_mode`.
    """
    for key in list(os.environ):
        if key.startswith("PRAXION_"):
            monkeypatch.delenv(key, raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("PRAXION_OBSERVATION_LOG", mode)
    monkeypatch.setenv("TMPDIR", str(marker_dir))


def _prepare(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mode: str) -> dict:
    """Load the hooks, build the fixture tree, and isolate the environment
    for one test's scenario run under `mode`."""
    proj, parent, marker_dir = _build_project(tmp_path)
    _isolate_env(monkeypatch, mode, marker_dir)
    cs = _load("capture_session")
    co = _load("capture_observations")
    mc = _load("measure_context_surface")
    hu = importlib.import_module("_hook_utils")
    return {
        "cs": cs,
        "hooks": {
            "capture_session": cs,
            "capture_observations": co,
            "measure_context_surface": mc,
            "record_gate_fire": hu.record_gate_fire,
        },
        "base": {"session_id": "S1", "cwd": str(proj), "transcript_path": str(parent)},
        "proj": proj,
    }


def _rows(reader_mod, ai_state_dir: Path) -> list[dict]:
    path = reader_mod.log_path(ai_state_dir)
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def _drive_step(
    step: Step, *, hooks: dict, base: dict, proj: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    if step.driver == "record_gate_fire":
        hooks["record_gate_fire"](**{**step.payload, "project_dir": proj})
        return
    module = hooks[step.driver]
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps({**base, **step.payload})))
    module.main()


def _run_scenario(
    *, hooks: dict, reader_mod, ai_state_dir: Path, base: dict, proj: Path, monkeypatch
) -> list[tuple[str, tuple, list[dict]]]:
    """Drive every SCENARIO step once, in order, attributing each step's new
    rows by counting the log before and after it runs."""
    outcomes = []
    for step in SCENARIO:
        before = len(_rows(reader_mod, ai_state_dir))
        _drive_step(step, hooks=hooks, base=base, proj=proj, monkeypatch=monkeypatch)
        new_rows = _rows(reader_mod, ai_state_dir)[before:]
        outcomes.append((step.name, step.expected, new_rows))
    return outcomes


# ---------------------------------------------------------------------------
# The checker: pure, with registry state passed in as parameters -- the same
# convention as `_consumer_contract_violations` in test_observation_log_registry.py.
# ---------------------------------------------------------------------------


def _violations(outcomes, mode, events, records_fn, event_class) -> list[Violation]:
    registered_types = {spec.event_type for spec in events.values()}
    violations: list[Violation] = []
    for step_name, expected, new_rows in outcomes:
        for row in new_rows:
            if row.get("event_type") not in registered_types:
                violations.append(Violation(step_name, "unregistered", row.get("event_type")))

        recording_classes = [e for e in expected if records_fn(event_class(e.event_class), mode)]
        actual_types = [row.get("event_type") for row in new_rows]
        expected_types = [events[event_class(e.event_class)].event_type for e in recording_classes]
        if actual_types != expected_types:
            violations.append(
                Violation(step_name, "written-mismatch", (actual_types, expected_types))
            )
            continue

        for row, expect in zip(new_rows, recording_classes, strict=True):
            spec = events[event_class(expect.event_class)]
            undeclared = sorted(set(row) - set(spec.fields))
            if undeclared:
                violations.append(Violation(step_name, "undeclared", undeclared))
            missing = sorted(set(spec.fields) - set(row) - expect.absent_ok)
            if missing:
                violations.append(Violation(step_name, "declared-but-absent", missing))
    return violations


# ---------------------------------------------------------------------------
# The gate: every writer, every mode, no violations.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("mode", ["full", "standard", "off"])
def test_every_writer_records_exactly_what_the_registry_declares(tmp_path, monkeypatch, mode):
    ctx = _prepare(tmp_path, monkeypatch, mode)
    cs = ctx["cs"]
    outcomes = _run_scenario(
        hooks=ctx["hooks"],
        reader_mod=cs.reader,
        ai_state_dir=ctx["proj"] / ".ai-state",
        base=ctx["base"],
        proj=ctx["proj"],
        monkeypatch=monkeypatch,
    )

    violations = _violations(
        outcomes,
        cs.Mode(mode),
        cs.writer.registry.EVENTS,
        cs.writer.registry.records,
        cs.EventClass,
    )
    assert violations == []


def test_scenario_drives_every_recorded_event_class(tmp_path, monkeypatch):
    """Totalising check: the scenario's classes equal every registered class
    except the one that bypasses the writer entirely (`_NOT_DRIVEN`)."""
    ctx = _prepare(tmp_path, monkeypatch, "full")
    registry = ctx["cs"].writer.registry

    covered = {expect.event_class for step in SCENARIO for expect in step.expected}
    all_classes = {event_class.value for event_class in registry.EventClass}

    assert covered == all_classes - set(_NOT_DRIVEN)


def test_hooks_share_one_observation_log_writer_copy(tmp_path, monkeypatch):
    """The patch-target rule: every hook, before and after driving the
    scenario (`_hook_utils.record_gate_fire` imports `_observation_log`
    lazily, on its first call), shares one `_observation_log.writer` --
    never `hooks._observation_log.writer`. Every canary below depends on
    patching the object this test proves is shared.
    """
    ctx = _prepare(tmp_path, monkeypatch, "full")
    cs, co, mc = (
        ctx["hooks"]["capture_session"],
        ctx["hooks"]["capture_observations"],
        ctx["hooks"]["measure_context_surface"],
    )
    modes_mod = importlib.import_module("_observation_log.modes")

    assert cs.writer is co.writer is mc.writer is sys.modules["_observation_log.writer"]
    assert cs.Mode is modes_mod.Mode

    _run_scenario(
        hooks=ctx["hooks"],
        reader_mod=cs.reader,
        ai_state_dir=ctx["proj"] / ".ai-state",
        base=ctx["base"],
        proj=ctx["proj"],
        monkeypatch=monkeypatch,
    )

    assert cs.writer is co.writer is mc.writer is sys.modules["_observation_log.writer"]


# ---------------------------------------------------------------------------
# T2: the writer-importer inventory. Mirrors the scan in
# test_observation_log_private_reader.py:34-76.
# ---------------------------------------------------------------------------

_OWNER_PACKAGE_PREFIX = "hooks/_observation_log/"
_TEST_FILE_RE = re.compile(r"(^|/)(test_[^/]+|conftest)\.py$")
# `.ai-work/` and `tmp/` are gitignored scratch space (pipeline notes, probe copies
# of hooks/): a local checkout carries them and CI does not. td-273 tracks
# replacing this walk with a `git ls-files` lister shared by both scans.
_EXCLUDED_DIR_MARKERS = (
    ".venv/",
    "/plugins/cache/",
    "/.claude/worktrees/",
    "/node_modules/",
    "/.ai-work/",
    "/tmp/",
)
_WRITER_IMPORT_RE = re.compile(r"_observation_log(\.writer\b|\s+import\s+[^\n#]*\bwriter\b)")


def _writer_importing_modules(root: Path) -> set[str]:
    """Repo-relative paths of non-test `.py` files (outside the owner
    package) whose source references the writer submodule."""
    findings = set()
    for path in sorted(root.rglob("*.py")):
        rel = path.relative_to(root).as_posix()
        if rel.startswith(_OWNER_PACKAGE_PREFIX) or _TEST_FILE_RE.search(rel):
            continue
        if any(marker in f"/{rel}" for marker in _EXCLUDED_DIR_MARKERS):
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        if _WRITER_IMPORT_RE.search(text):
            findings.add(rel)
    return findings


def test_every_writer_importing_module_is_in_the_driven_set():
    assert _writer_importing_modules(REPO_ROOT) == DRIVEN_WRITER_MODULES


def test_canary_an_undriven_writer_importer_is_caught(tmp_path):
    """Gate-liveness canary: a module outside the driven set that imports the
    writer must be flagged."""
    rogue = tmp_path / "scripts" / "rogue_writer.py"
    rogue.parent.mkdir(parents=True)
    rogue.write_text("from _observation_log import writer\n", encoding="utf-8")

    assert _writer_importing_modules(tmp_path) == {"scripts/rogue_writer.py"}


# ---------------------------------------------------------------------------
# Canaries: each injects one specific drift and asserts the checker names it.
# Injection point is the hooks' copy of `writer.append_observation` -- the
# single funnel below `record()`'s gate for every entry point.
# ---------------------------------------------------------------------------


def _run_with_injection(tmp_path, monkeypatch, mode, inject) -> list[Violation]:
    ctx = _prepare(tmp_path, monkeypatch, mode)
    cs = ctx["cs"]
    real_append = cs.writer.append_observation
    monkeypatch.setattr(cs.writer, "append_observation", lambda p, o: real_append(p, inject(o)))

    outcomes = _run_scenario(
        hooks=ctx["hooks"],
        reader_mod=cs.reader,
        ai_state_dir=ctx["proj"] / ".ai-state",
        base=ctx["base"],
        proj=ctx["proj"],
        monkeypatch=monkeypatch,
    )
    return _violations(
        outcomes,
        cs.Mode(mode),
        cs.writer.registry.EVENTS,
        cs.writer.registry.records,
        cs.EventClass,
    )


def test_canary_undeclared_row_key_is_flagged_at_every_step(tmp_path, monkeypatch):
    violations = _run_with_injection(
        tmp_path, monkeypatch, "full", lambda o: {**o, "undeclared_canary_key": True}
    )

    flagged = {
        v.step for v in violations if v.kind == "undeclared" and "undeclared_canary_key" in v.detail
    }
    assert flagged == {step.name for step in SCENARIO}


def test_canary_unregistered_event_type_is_flagged(tmp_path, monkeypatch):
    def inject(observation: dict) -> dict:
        if observation.get("event_type") != "gate_fire":
            return observation
        return {**observation, "event_type": "gate_fire_unregistered"}

    violations = _run_with_injection(tmp_path, monkeypatch, "full", inject)

    assert Violation("gate_fire", "unregistered", "gate_fire_unregistered") in violations


def test_canary_dropped_declared_field_is_flagged_exactly(tmp_path, monkeypatch):
    def inject(observation: dict) -> dict:
        if observation.get("event_type") != "gate_fire":
            return observation
        return {k: v for k, v in observation.items() if k != "hook"}

    violations = _run_with_injection(tmp_path, monkeypatch, "full", inject)

    assert violations == [Violation("gate_fire", "declared-but-absent", ["hook"])]


def test_canary_writer_ignoring_mode_flags_every_step(tmp_path, monkeypatch):
    ctx = _prepare(tmp_path, monkeypatch, "off")
    cs = ctx["cs"]
    modes_mod = importlib.import_module("_observation_log.modes")

    def ignore_mode(env):
        return modes_mod.Mode.FULL, modes_mod.ModeSource.SETTING

    # The recording path reads the mode in three places: the writer, and the two
    # hooks that return before any work under `off`. Patching only the writer
    # would leave those early returns in charge, so the steps they own could
    # never show a mismatch.
    monkeypatch.setattr(cs.writer, "resolve_mode", ignore_mode)
    monkeypatch.setattr(cs, "resolve_mode", ignore_mode)
    monkeypatch.setattr(ctx["hooks"]["measure_context_surface"], "resolve_mode", ignore_mode)

    outcomes = _run_scenario(
        hooks=ctx["hooks"],
        reader_mod=cs.reader,
        ai_state_dir=ctx["proj"] / ".ai-state",
        base=ctx["base"],
        proj=ctx["proj"],
        monkeypatch=monkeypatch,
    )
    violations = _violations(
        outcomes,
        cs.Mode("off"),
        cs.writer.registry.EVENTS,
        cs.writer.registry.records,
        cs.EventClass,
    )

    mismatched = {v.step for v in violations if v.kind == "written-mismatch"}
    assert mismatched == {step.name for step in SCENARIO}
