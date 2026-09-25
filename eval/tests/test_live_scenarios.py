"""Behavioral tests for the per-scenario capture functions in `scenarios.py`.

Each capture function is exercised against a verbatim `claude -p` envelope
recorded from a real session (see `fixtures/live_scenarios/README.md`) —
never against hand-written JSON shaped like what an envelope "should" look
like. `adr-authoring` and `lightweight-fix` capture from a filesystem delta
instead of the envelope; those deltas are built from real files under
`tmp_path` with `scenarios.snapshot`/`compute_fs_delta`, so the test can
still fail the way the real diff would.
"""

from __future__ import annotations

from pathlib import Path

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures" / "live_scenarios"


def _envelope(name: str):
    from praxion_evals.live.session import parse_stream

    return parse_stream((FIXTURES_DIR / f"{name}.stream.jsonl").read_text(encoding="utf-8"))


def _fixtures_by_id() -> dict[str, dict]:
    from praxion_evals.harness.families.seeded_scenarios import load_scenario_fixtures

    return {data["scenario_id"]: data for data in load_scenario_fixtures()}


# ---------------------------------------------------------------------------
# spawn-selection — capture from result.structured_output
# ---------------------------------------------------------------------------


def test_spawn_selection_captures_and_normalizes_tier_and_agents():
    from praxion_evals.live.results import Captured
    from praxion_evals.live.scenarios import SCENARIOS

    envelope = _envelope("spawn_selection_standard_opus")
    case = _fixtures_by_id()["spawn-selection"]["cases"][2]  # the "standard" case

    result = SCENARIOS["spawn-selection"].capture(envelope, None, case)

    assert isinstance(result, Captured)
    assert result.value["recorded_tier"] == "standard"
    # The probe recorded 7 agents (a superset of the 4 expected); every
    # expected member comes first, in the fixture's own order.
    assert result.value["recorded_agents"][:4] == case["expected_agents"]
    assert set(result.value["recorded_agents"]) == {
        "researcher",
        "systems-architect",
        "interface-designer",
        "implementation-planner",
        "implementer",
        "test-engineer",
        "verifier",
    }


def test_spawn_selection_grades_pass_through_the_full_capture_to_grade_pipeline():
    """The amended subset comparison lets a real superset session PASS."""
    import copy

    from praxion_evals.harness.families.seeded_scenarios import grade_mechanical
    from praxion_evals.live.results import Captured
    from praxion_evals.live.scenarios import SCENARIOS

    envelope = _envelope("spawn_selection_standard_opus")
    fixture = _fixtures_by_id()["spawn-selection"]
    case = copy.deepcopy(fixture["cases"][2])

    capture = SCENARIOS["spawn-selection"].capture(envelope, None, case)
    assert isinstance(capture, Captured)
    graded_case = {**case, **capture.value}
    data = {**fixture, "cases": [graded_case]}

    passed, findings = grade_mechanical(data)

    assert passed, findings


def test_spawn_selection_is_not_elicited_when_the_result_has_no_structured_output():
    from praxion_evals.live.results import NotElicited
    from praxion_evals.live.scenarios import SCENARIOS

    envelope = _envelope("isolated_marker_preflight_sonnet")  # a plain-text preflight result

    result = SCENARIOS["spawn-selection"].capture(envelope, None, {"expected_agents": []})

    assert isinstance(result, NotElicited)


# ---------------------------------------------------------------------------
# ui-step-conformance — capture from the subagent's own forwarded text
# ---------------------------------------------------------------------------


def test_ui_step_conformance_captures_the_subagents_own_forwarded_text():
    from praxion_evals.live.results import Captured
    from praxion_evals.live.scenarios import SCENARIOS

    envelope = _envelope("ui_step_conformance")

    result = SCENARIOS["ui-step-conformance"].capture(envelope, None, {})

    assert isinstance(result, Captured)
    assert result.diagnostics["source"] == "subagent_text"
    assert result.value["report"]  # the subagent's own forwarded text, non-empty
    assert result.value["ui_changes"] == {}


def test_ui_step_conformance_captures_the_ui_files_the_implementer_changed(tmp_path):
    """The judge grades the change, not the return summary: the capture
    carries each changed file under the UI surface with its content, and
    leaves pipeline bookkeeping (`.ai-work/`) out."""
    from praxion_evals.live.scenarios import SCENARIOS, compute_fs_delta, snapshot

    root = tmp_path / "fixture"
    component = root / "dashboard_app" / "src" / "components" / "AdrList.tsx"
    component.parent.mkdir(parents=True)
    component.write_text("export function AdrList() {}\n")
    wip = root / ".ai-work" / "ui-step" / "WIP.md"
    wip.parent.mkdir(parents=True)
    wip.write_text("Status: TODO\n")
    before = snapshot(root)
    component.write_text("export function AdrList({ state }) { /* loading */ }\n")
    wip.write_text("Status: COMPLETE\n")
    delta = compute_fs_delta(before, snapshot(root))

    result = SCENARIOS["ui-step-conformance"].capture(_envelope("ui_step_conformance"), delta, {})

    assert result.value["ui_changes"] == {
        "dashboard_app/src/components/AdrList.tsx": (
            "export function AdrList({ state }) { /* loading */ }\n"
        )
    }


def test_ui_step_conformance_fails_when_no_ui_file_changed():
    """A `[BLOCKED]` return or a report-only session did not implement the
    step on the UI surface — the one thing checkable without a judge."""
    from praxion_evals.live.scenarios import SCENARIOS

    check = SCENARIOS["ui-step-conformance"].mechanical_check
    assert check is not None

    passed, findings = check({"recorded_output": {"report": "[BLOCKED]", "ui_changes": {}}})

    assert passed is False
    assert findings == ["no file under dashboard_app/ changed: the step was not implemented"]


def test_ui_step_conformance_passes_the_mechanical_gate_on_any_ui_change():
    """Citations in the report are not required: the return contract keeps
    the report terse, and conformance is the judge's call over the code."""
    from praxion_evals.live.scenarios import SCENARIOS

    check = SCENARIOS["ui-step-conformance"].mechanical_check
    assert check is not None
    recorded = {"report": "[COMPLETE] done", "ui_changes": {"dashboard_app/a.tsx": "x"}}

    passed, findings = check({"recorded_output": recorded})

    assert passed is True
    assert findings == []


def test_ui_step_conformance_fixture_seeds_the_full_planning_document_set(tmp_path):
    """A real implementer step always has LEARNINGS.md beside WIP.md and the
    plan; its absence made the implementer correctly return `[BLOCKED]`."""
    from praxion_evals.harness.families.seeded_scenarios import load_scenario_fixtures
    from praxion_evals.live.scenarios import SCENARIOS

    seeded = next(d for d in load_scenario_fixtures() if d["scenario_id"] == "ui-step-conformance")
    root = tmp_path / "fixture"

    SCENARIOS["ui-step-conformance"].build_fixture(root, seeded)

    step_dir = root / ".ai-work" / "ui-step"
    assert {p.name for p in step_dir.iterdir()} == {
        "IMPLEMENTATION_PLAN.md",
        "WIP.md",
        "LEARNINGS.md",
    }


def test_ui_step_conformance_is_not_elicited_without_an_implementer_agent_call():
    from praxion_evals.live.results import NotElicited
    from praxion_evals.live.scenarios import SCENARIOS

    envelope = _envelope("spawn_selection_standard_opus")  # no Agent tool_use at all

    result = SCENARIOS["ui-step-conformance"].capture(envelope, None, {})

    assert isinstance(result, NotElicited)


# ---------------------------------------------------------------------------
# adr-authoring — capture from the created .ai-state/decisions/ file
# ---------------------------------------------------------------------------


def _delta_after_writing(tmp_path: Path, relpath: str, content: str):
    from praxion_evals.live.scenarios import compute_fs_delta, snapshot

    root = tmp_path / "fixture"
    root.mkdir()
    before = snapshot(root)
    target = root / relpath
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return compute_fs_delta(before, snapshot(root))


def test_adr_authoring_captures_the_created_drafts_file_content(tmp_path):
    from praxion_evals.live.results import Captured
    from praxion_evals.live.scenarios import SCENARIOS

    delta = _delta_after_writing(
        tmp_path,
        ".ai-state/decisions/drafts/20260907-split-hook.md",
        "---\nid: dec-draft-abc\n---\n",
    )

    result = SCENARIOS["adr-authoring"].capture(_envelope("adr_authoring"), delta, {})

    assert isinstance(result, Captured)
    assert "dec-draft-abc" in result.value


def test_adr_authoring_prefers_a_drafts_file_over_a_non_drafts_one(tmp_path):
    from praxion_evals.live.scenarios import compute_fs_delta, snapshot

    root = tmp_path / "fixture"
    root.mkdir()
    before = snapshot(root)
    (root / ".ai-state" / "decisions").mkdir(parents=True)
    (root / ".ai-state" / "decisions" / "099-finalized.md").write_text("finalized\n")
    (root / ".ai-state" / "decisions" / "drafts").mkdir()
    (root / ".ai-state" / "decisions" / "drafts" / "20260907-x.md").write_text("draft\n")
    delta = compute_fs_delta(before, snapshot(root))

    from praxion_evals.live.results import Captured
    from praxion_evals.live.scenarios import SCENARIOS

    result = SCENARIOS["adr-authoring"].capture(_envelope("adr_authoring"), delta, {})

    assert isinstance(result, Captured)
    assert result.value == "draft\n"


def test_adr_authoring_is_not_elicited_when_no_decisions_file_was_created(tmp_path):
    from praxion_evals.live.results import NotElicited
    from praxion_evals.live.scenarios import SCENARIOS

    delta = _delta_after_writing(tmp_path, "README.md", "unrelated\n")

    result = SCENARIOS["adr-authoring"].capture(_envelope("adr_authoring"), delta, {})

    assert isinstance(result, NotElicited)


# ---------------------------------------------------------------------------
# commit-staging — capture from the session's own Bash commands
# ---------------------------------------------------------------------------


def test_commit_staging_captures_the_staging_command_from_a_real_envelope():
    from praxion_evals.live.results import Captured
    from praxion_evals.live.scenarios import SCENARIOS

    result = SCENARIOS["commit-staging"].capture(_envelope("commit_staging"), None, {})

    assert isinstance(result, Captured)
    assert result.value == "git add scripts/foo.py scripts/test_foo.py"


def test_commit_staging_ignores_dash_a_inside_a_quoted_commit_message():
    from praxion_evals.live.results import NotElicited
    from praxion_evals.live.scenarios import SCENARIOS
    from praxion_evals.live.session import SessionEnvelope, ToolUse

    envelope = SessionEnvelope(
        init=None,
        tool_uses=(
            ToolUse(
                id="t1",
                name="Bash",
                input={"command": 'git commit -m "Use -A carefully, not --all lightly."'},
                parent_tool_use_id=None,
            ),
        ),
        subagent_texts=(),
        task_notifications=(),
        hook_outputs=(),
        final_result=None,
        result_count=0,
        unparseable=False,
    )

    result = SCENARIOS["commit-staging"].capture(envelope, None, {})

    assert isinstance(result, NotElicited)


def test_commit_staging_keeps_git_dash_c_prefixed_staging_and_git_commit_dash_a():
    from praxion_evals.live.results import Captured
    from praxion_evals.live.scenarios import SCENARIOS
    from praxion_evals.live.session import SessionEnvelope, ToolUse

    envelope = SessionEnvelope(
        init=None,
        tool_uses=(
            ToolUse(
                id="t1",
                name="Bash",
                input={"command": "git -C repo add foo.py && git commit -am 'fix'"},
                parent_tool_use_id=None,
            ),
        ),
        subagent_texts=(),
        task_notifications=(),
        hook_outputs=(),
        final_result=None,
        result_count=0,
        unparseable=False,
    )

    result = SCENARIOS["commit-staging"].capture(envelope, None, {})

    assert isinstance(result, Captured)
    assert result.value == "git -C repo add foo.py ; git commit -am 'fix'"


def test_commit_staging_is_not_elicited_with_no_bash_calls_at_all():
    from praxion_evals.live.results import NotElicited
    from praxion_evals.live.scenarios import SCENARIOS

    result = SCENARIOS["commit-staging"].capture(
        _envelope("spawn_selection_standard_opus"), None, {}
    )

    assert isinstance(result, NotElicited)


# ---------------------------------------------------------------------------
# lightweight-fix — capture from the filesystem delta
# ---------------------------------------------------------------------------


def test_lightweight_fix_captures_created_and_modified_paths_sorted(tmp_path):
    from praxion_evals.live.results import Captured
    from praxion_evals.live.scenarios import SCENARIOS, compute_fs_delta, snapshot

    root = tmp_path / "fixture"
    root.mkdir()
    (root / "scripts").mkdir()
    (root / "scripts" / "paginate.py").write_text("buggy\n")
    before = snapshot(root)
    (root / "scripts" / "paginate.py").write_text("fixed\n")
    (root / ".ai-state").mkdir()
    (root / ".ai-state" / "calibration_log.md").write_text("| row |\n")
    delta = compute_fs_delta(before, snapshot(root))

    result = SCENARIOS["lightweight-fix"].capture(_envelope("lightweight_fix"), delta, {})

    assert isinstance(result, Captured)
    assert result.value == [".ai-state/calibration_log.md", "scripts/paginate.py"]


def test_lightweight_fix_is_not_elicited_when_nothing_changed(tmp_path):
    from praxion_evals.live.results import NotElicited
    from praxion_evals.live.scenarios import SCENARIOS, compute_fs_delta, snapshot

    root = tmp_path / "fixture"
    root.mkdir()
    before = snapshot(root)
    delta = compute_fs_delta(before, snapshot(root))

    result = SCENARIOS["lightweight-fix"].capture(_envelope("lightweight_fix"), delta, {})

    assert isinstance(result, NotElicited)


# ---------------------------------------------------------------------------
# Filesystem delta helpers
# ---------------------------------------------------------------------------


def test_snapshot_excludes_the_dot_git_directory(tmp_path):
    from praxion_evals.live.scenarios import snapshot

    root = tmp_path / "fixture"
    (root / ".git").mkdir(parents=True)
    (root / ".git" / "HEAD").write_text("ref: refs/heads/main\n")
    (root / "README.md").write_text("hi\n")

    result = snapshot(root)

    assert set(result) == {"README.md"}


def test_compute_fs_delta_detects_modification_by_hash_not_by_presence(tmp_path):
    from praxion_evals.live.scenarios import compute_fs_delta, snapshot

    root = tmp_path / "fixture"
    root.mkdir()
    (root / "a.txt").write_text("one\n")
    before = snapshot(root)
    (root / "a.txt").write_text("two\n")
    delta = compute_fs_delta(before, snapshot(root))

    assert delta.created == {}
    assert delta.modified == {"a.txt": "two\n"}
    assert delta.changed_paths == ("a.txt",)


# ---------------------------------------------------------------------------
# Every scenario grants the harmless inspection utilities, never a wildcard
# ---------------------------------------------------------------------------


def test_every_tool_using_scenario_grants_the_harmless_inspection_utilities():
    """spawn-selection is the one exception: a glob allowlist cannot tell
    `tail` on stdin from `tail ~/.ssh/…`, so it gets no tools at all rather
    than even the harmless set — see the no-Bash-tools test below."""
    from praxion_evals.live.scenarios import HARMLESS_UTILITIES, SCENARIOS

    for scenario_id, spec in SCENARIOS.items():
        if scenario_id == "spawn-selection":
            continue
        tools = set(spec.allowed_tools)

        assert set(HARMLESS_UTILITIES) <= tools, scenario_id


def test_spawn_selection_grants_no_tools_at_all():
    from praxion_evals.live.scenarios import SCENARIOS

    assert SCENARIOS["spawn-selection"].allowed_tools == ()


def test_no_scenario_grants_a_broad_git_or_python3_wildcard():
    from praxion_evals.live.scenarios import SCENARIOS

    broad = {"Bash(git *)", "Bash(python3 *)", "Bash(python *)", "Bash", "Bash(*)"}
    for scenario_id, spec in SCENARIOS.items():
        tools = set(spec.allowed_tools)

        assert tools.isdisjoint(broad), (scenario_id, sorted(tools & broad))


# ---------------------------------------------------------------------------
# commit-staging: ground truth from the commit history, not the command text
# ---------------------------------------------------------------------------


def _git_repo(tmp_path):
    import subprocess

    root = tmp_path / "repo"
    root.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.name", "scenario"], cwd=root, check=True)
    subprocess.run(
        ["git", "config", "user.email", "scenario@example.invalid"], cwd=root, check=True
    )
    return root


def _commit(root, files):
    import subprocess

    for relpath, content in files.items():
        path = root / relpath
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=root, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "c"], cwd=root, check=True)
    return subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True, check=True
    ).stdout.strip()


def test_commit_fs_delta_lists_exactly_the_paths_the_new_commit_touched(tmp_path):
    from praxion_evals.live.scenarios import commit_fs_delta

    root = _git_repo(tmp_path)
    baseline_sha = _commit(root, {"scripts/foo.py": "a\n"})
    _commit(root, {"scripts/foo.py": "b\n", "scripts/test_foo.py": "t\n"})

    delta = commit_fs_delta(root, baseline_sha)

    assert delta.changed_paths == ("scripts/foo.py", "scripts/test_foo.py")


def test_commit_fs_delta_is_empty_when_no_new_commit_was_made(tmp_path):
    from praxion_evals.live.scenarios import commit_fs_delta

    root = _git_repo(tmp_path)
    baseline_sha = _commit(root, {"scripts/foo.py": "a\n"})

    delta = commit_fs_delta(root, baseline_sha)

    assert delta.changed_paths == ()


def test_commit_staging_catches_a_trap_file_committed_via_a_directory_pathspec():
    """The verifier's exact reproduction: `git add scripts .ai-state` sweeps
    in the untracked trap file through a directory pathspec the syntactic
    check cannot see; ground truth from what was actually committed must
    still surface it so the unchanged forbidden-path check can catch it."""
    from praxion_evals.live.results import Captured
    from praxion_evals.live.scenarios import FsDelta, capture_commit_staging
    from praxion_evals.live.session import SessionEnvelope, ToolUse

    envelope = SessionEnvelope(
        init=None,
        tool_uses=(
            ToolUse(
                id="t1",
                name="Bash",
                input={"command": "git add scripts .ai-state && git commit -m x"},
                parent_tool_use_id=None,
            ),
        ),
        subagent_texts=(),
        task_notifications=(),
        hook_outputs=(),
        final_result=None,
        result_count=0,
        unparseable=False,
    )
    ground_truth = FsDelta(
        created={
            "scripts/foo.py": "",
            "scripts/test_foo.py": "",
            ".ai-state/observations.jsonl": "",
        },
        modified={},
    )

    capture = capture_commit_staging(envelope, ground_truth, {})

    assert isinstance(capture, Captured)
    assert ".ai-state/observations.jsonl" in capture.value


def test_commit_staging_stays_unchanged_when_no_ground_truth_is_available():
    """Existing callers that never pass a filesystem delta (e.g. the
    envelope-only tests against the recorded fixtures) must see the exact
    same recorded string as before this change."""
    from praxion_evals.live.results import Captured
    from praxion_evals.live.scenarios import capture_commit_staging
    from praxion_evals.live.session import SessionEnvelope, ToolUse

    envelope = SessionEnvelope(
        init=None,
        tool_uses=(
            ToolUse(
                id="t1",
                name="Bash",
                input={"command": "git add scripts/foo.py scripts/test_foo.py"},
                parent_tool_use_id=None,
            ),
        ),
        subagent_texts=(),
        task_notifications=(),
        hook_outputs=(),
        final_result=None,
        result_count=0,
        unparseable=False,
    )

    capture = capture_commit_staging(envelope, None, {})

    assert isinstance(capture, Captured)
    assert capture.value == "git add scripts/foo.py scripts/test_foo.py"
