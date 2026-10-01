"""Tests for spawn_count.py -- per-slug spawn/resume tally with a budget verdict.

Gate-liveness contract (rules/swe/gate-liveness.md): spawn_count.py is the reader an
orchestrator consults before spawning the next agent, so a miscount is a silent budget
breach. Every WAL fixture below either reproduces a real `agent_start` row verbatim (the
`a65ec99bc016c1ca0` spawn/resume pair, plus a start from an unrelated project -- both
copied from `.ai-state/observations.jsonl.1`) or is exercised through the actual CLI
entrypoint as a subprocess, never a hand-rolled stand-in for the real WAL shape.

Contract under test: a pure counting core (`tally`, `classify_resume`, `verdict`) plus
an I/O shell (the `spawn_count.py` CLI) that reads `.ai-state/observations.jsonl.1` then
`.ai-state/observations.jsonl`, attributes each agent to one slug (the slug its spawn prompt
stated, else its start row's `project`; an agent no row or transcript attributes counts toward
no slug and holds every verdict), and for each agent counts its first record as a spawn and
every later start as a resume. A resume
is classified against the resuming agent's own subagent transcript
(`<projects-dir>/*/<session_id>/subagents/agent-<agent_id>.jsonl`, globbed on the session
UUID since the CLI is never handed the project-hashed directory name Claude Code uses):
`heavy` when the last assistant turn before the resume timestamp carries
`input_tokens + cache_read_input_tokens + cache_creation_input_tokens` at or above
`--heavy-context` (default 250,000), `light` below it, `unsized` when no matching
transcript line exists. `charged = spawns + heavy resumes`; the verdict is `within` only
when both `charged <= budget` AND `charged + unsized + unattributed <= budget` hold (an
unsized resume or an unattributed spawn must never read as `within`), `over` when `charged > budget`, `indeterminate` otherwise,
`no-budget` when `--budget` is omitted. Exit 0 for within/indeterminate/no-budget, 1 for
over, 2 for withheld (absent WAL, an unseen slug, or a plugin-cache-root repo-root) --
withholding never reports a false "0 spawns, within budget".
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest


def _find_repo_root() -> Path:
    """The checkout holding the observation-log package, wherever this file runs from.

    The mutation sensor runs a copy of this file one directory deeper (`scripts/mutants/`),
    so a fixed `parent.parent` would miss the repository.
    """
    for ancestor in Path(__file__).resolve().parents:
        if (ancestor / "hooks" / "_observation_log").is_dir():
            return ancestor
    raise RuntimeError(f"no checkout with hooks/_observation_log above {__file__}")


_REPO_ROOT = _find_repo_root()
_SCRIPT_PATH = _REPO_ROOT / "scripts" / "spawn_count.py"

# spawn_count.py reaches `hooks/` through its own location, which is wrong from a copy.
sys.path.insert(0, str(_REPO_ROOT / "hooks"))

# -- Verbatim WAL rows -----------------------------------------------------------
# Copied byte-for-byte from the main checkout's .ai-state/observations.jsonl.1 (not
# reconstructed): the a65ec99bc016c1ca0 systems-architect spawn (line 3261), its
# paired agent_stop (line 3338), the SendMessage resume trigger (line 3339), and the
# resume's own second agent_start (line 3340, same agent_id) -- proving tally() counts
# by first-start-per-agent_id, not by row count, and that agent_stop/tool_use rows
# never contribute a spawn or a resume. The fifth row (line 186) is a start from an
# unrelated project ("deep-fix-round") kept out of every "praxion"-scoped assertion
# below, proving cross-project rows never leak into another slug's tally.

_ROW_FIRST_START = (
    '{"timestamp": "2026-08-30T23:31:50.032601+00:00", "session_id": '
    '"2bf94c0a-4d02-4788-b750-a4ab0e4076d2", "agent_type": "praxion:systems-architect", '
    '"agent_id": "a65ec99bc016c1ca0", "project": "praxion", "event_type": "agent_start", '
    '"tool_name": null, "summary": "Agent started: praxion:systems-architect", '
    '"file_paths": [], "outcome": null, "classification": null, '
    '"agent_type_source": "payload", "start_correlation": "not-applicable"}'
)
_ROW_PAIRED_STOP = (
    '{"timestamp": "2026-08-30T23:43:32.824576+00:00", "session_id": '
    '"2bf94c0a-4d02-4788-b750-a4ab0e4076d2", "agent_type": "praxion:systems-architect", '
    '"agent_id": "a65ec99bc016c1ca0", "project": "praxion", "event_type": "agent_stop", '
    '"tool_name": null, "summary": "Agent completed: praxion:systems-architect", '
    '"file_paths": [], "outcome": null, "classification": null, '
    '"agent_type_source": "payload", "start_correlation": "paired"}'
)
_ROW_SENDMESSAGE = (
    '{"timestamp": "2026-08-30T23:45:41.543557+00:00", "session_id": '
    '"2bf94c0a-4d02-4788-b750-a4ab0e4076d2", "agent_type": "main", "agent_id": '
    '"2bf94c0a-4d02-4788-b750-a4ab0e4076d2", "project": "praxion", "event_type": '
    '"tool_use", "tool_name": "SendMessage", "summary": "SendMessage", "file_paths": [], '
    '"outcome": "success", "classification": "tool_use", "trace_id": "", "span_id": "", '
    '"parent_span_id": ""}'
)
_ROW_RESUME_START = (
    '{"timestamp": "2026-08-30T23:45:41.543661+00:00", "session_id": '
    '"2bf94c0a-4d02-4788-b750-a4ab0e4076d2", "agent_type": "praxion:systems-architect", '
    '"agent_id": "a65ec99bc016c1ca0", "project": "praxion", "event_type": "agent_start", '
    '"tool_name": null, "summary": "Agent started: praxion:systems-architect", '
    '"file_paths": [], "outcome": null, "classification": null, '
    '"agent_type_source": "payload", "start_correlation": "not-applicable"}'
)
# Verbatim except agent_type/summary: the recorded row predates the plugin rename and
# carried the retired namespace; the count ignores agent_type, so it is normalized.
_ROW_OTHER_PROJECT_START = (
    '{"timestamp": "2026-08-13T07:04:24.695942+00:00", "session_id": '
    '"84edfc44-9ae8-45aa-86c2-bdbcff41aaf9", "agent_type": "praxion:context-engineer", '
    '"agent_id": "adeee2949176052ca", "project": "deep-fix-round", "event_type": '
    '"agent_start", "tool_name": null, "summary": "Agent started: praxion:context-engineer", '
    '"file_paths": [], "outcome": null, "classification": null}'
)

_RESUME_SESSION_ID = "2bf94c0a-4d02-4788-b750-a4ab0e4076d2"
_RESUME_AGENT_ID = "a65ec99bc016c1ca0"


# -- WAL / repo-root fixture helpers ----------------------------------------------


def _write_wal(repo_root: Path, dot1_lines: list[str], live_lines: list[str]) -> None:
    """Write the rotation archive (.1) and the live WAL, mirroring the real read order.

    spawn_count.py must read .ai-state/observations.jsonl.1 THEN
    .ai-state/observations.jsonl -- splitting the verbatim rows across both files (as
    the tests below do) is itself a check that the reader crosses the rotation
    boundary rather than reading only the live file.
    """
    state_dir = repo_root / ".ai-state"
    state_dir.mkdir(parents=True, exist_ok=True)
    if dot1_lines:
        (state_dir / "observations.jsonl.1").write_text(
            "\n".join(dot1_lines) + "\n", encoding="utf-8"
        )
    if live_lines:
        (state_dir / "observations.jsonl").write_text(
            "\n".join(live_lines) + "\n", encoding="utf-8"
        )


def _write_subagent_transcript(
    projects_dir: Path,
    session_id: str,
    agent_id: str,
    *,
    input_tokens: int,
    cache_read_input_tokens: int = 0,
    cache_creation_input_tokens: int = 0,
    timestamp: str = "2026-08-30T23:44:00.000000+00:00",
    model: str = "claude-sonnet-5",
) -> None:
    """Write a synthetic subagent transcript at the globbed layout spawn_count.py reads.

    Layout: <projects_dir>/<some-project-dir>/<session_id>/subagents/agent-<agent_id>.jsonl
    -- the leading project-dir component is globbed (`*`) because the CLI is never handed
    the project-hashed directory name the harness uses, only the session UUID.
    """
    transcript_dir = projects_dir / "-fake-project-dir" / session_id / "subagents"
    transcript_dir.mkdir(parents=True, exist_ok=True)
    line = {
        "type": "assistant",
        "agentId": agent_id,
        "timestamp": timestamp,
        "message": {
            "model": model,
            "usage": {
                "input_tokens": input_tokens,
                "output_tokens": 128,
                "cache_read_input_tokens": cache_read_input_tokens,
                "cache_creation_input_tokens": cache_creation_input_tokens,
            },
        },
    }
    (transcript_dir / f"agent-{agent_id}.jsonl").write_text(
        json.dumps(line) + "\n", encoding="utf-8"
    )


def _run_cli(args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    """Invoke spawn_count.py via `uv run python`, the real production call shape."""
    return subprocess.run(
        ["uv", "run", "python", str(_SCRIPT_PATH), *args],
        capture_output=True,
        text=True,
        cwd=str(cwd),
        timeout=30,
    )


# -- Pure-core tests: tally / classify_resume / verdict ---------------------------


def test_first_start_per_agent_id_is_a_spawn_and_further_starts_are_resumes() -> None:
    """A SendMessage resume re-uses the same agent_id -- one spawn, one resume, not two spawns."""
    import spawn_count

    rows = [
        json.loads(_ROW_FIRST_START),
        json.loads(_ROW_PAIRED_STOP),
        json.loads(_ROW_SENDMESSAGE),
        json.loads(_ROW_RESUME_START),
    ]

    tallies = spawn_count.tally(rows)

    assert len(tallies) == 1, "one distinct agent_id must produce exactly one AgentTally"
    architect = tallies[0]
    assert architect.agent_id == "a65ec99bc016c1ca0"
    assert architect.spawned_at == "2026-08-30T23:31:50.032601+00:00"
    assert len(architect.resumes) == 1, (
        "the second agent_start (same agent_id) is a resume, not a second spawn"
    )
    assert architect.resumes[0].at == "2026-08-30T23:45:41.543661+00:00"


def test_agent_stop_and_tool_use_rows_never_contribute_a_spawn_or_resume() -> None:
    """Only agent_start rows are counted -- a stop or a SendMessage tool_use is not a spawn."""
    import spawn_count

    rows = [
        json.loads(_ROW_FIRST_START),
        json.loads(_ROW_PAIRED_STOP),
        json.loads(_ROW_SENDMESSAGE),
    ]

    tallies = spawn_count.tally(rows)

    assert len(tallies) == 1
    assert len(tallies[0].resumes) == 0, (
        "agent_stop and tool_use rows for the same agent_id must not be read as resumes"
    )


def test_distinct_agent_ids_each_get_their_own_tally() -> None:
    """Two unrelated agents (different agent_id, different project) tally independently."""
    import spawn_count

    rows = [json.loads(_ROW_FIRST_START), json.loads(_ROW_OTHER_PROJECT_START)]

    tallies = spawn_count.tally(rows)

    assert {t.agent_id for t in tallies} == {"a65ec99bc016c1ca0", "adeee2949176052ca"}
    assert all(len(t.resumes) == 0 for t in tallies)


@pytest.mark.parametrize(
    ("context_tokens", "expected_class"),
    [
        (250_000, "heavy"),
        (249_999, "light"),
        (None, "unsized"),
    ],
    ids=["at-threshold-is-heavy", "just-below-threshold-is-light", "no-transcript-is-unsized"],
)
def test_classify_resume_boundary(context_tokens: int | None, expected_class: str) -> None:
    """The heavy/light boundary is inclusive at the threshold; a missing size is unsized."""
    import spawn_count

    assert spawn_count.classify_resume(context_tokens, threshold=250_000) == expected_class


def test_verdict_is_within_when_charged_and_unsized_total_both_fit_budget() -> None:
    import spawn_count

    tallies = (
        spawn_count.AgentTally(
            agent_id="a1",
            agent_type="praxion:implementer",
            spawned_at="t0",
            resumes=(spawn_count.Resume(at="t1", context_tokens=100),),
        ),
    )

    result = spawn_count.verdict(tallies, budget=8, threshold=250_000)

    assert result.label == "within"
    assert result.spawns == 1
    assert result.charged == 1  # the resume is light -- not charged


def test_verdict_is_over_when_charged_spawns_exceed_budget() -> None:
    import spawn_count

    tallies = tuple(
        spawn_count.AgentTally(
            agent_id=f"a{i}", agent_type="praxion:implementer", spawned_at="t0", resumes=()
        )
        for i in range(9)
    )

    result = spawn_count.verdict(tallies, budget=8, threshold=250_000)

    assert result.label == "over"
    assert result.charged == 9


def test_verdict_is_indeterminate_when_an_unsized_resume_would_push_past_budget() -> None:
    """An unsized resume must never let the verdict read `within` (REQ: unsized-never-within).

    charged == budget (5 == 5) satisfies the naive `charged <= budget` check alone, but
    the unsized resume could turn out heavy -- so the verdict must NOT be `within`, and
    must not be `over` either since charged has not actually exceeded budget yet.
    """
    import spawn_count

    tallies = tuple(
        spawn_count.AgentTally(
            agent_id=f"a{i}", agent_type="praxion:implementer", spawned_at="t0", resumes=()
        )
        for i in range(4)
    ) + (
        spawn_count.AgentTally(
            agent_id="resumed",
            agent_type="praxion:implementer",
            spawned_at="t0",
            resumes=(spawn_count.Resume(at="t1", context_tokens=None),),
        ),
    )

    result = spawn_count.verdict(tallies, budget=5, threshold=250_000)

    assert result.charged == 5, "every first start is a definite spawn, resumed or not"
    assert result.label == "indeterminate", (
        f"an unsized resume must never read as 'within'; got {result.label!r}"
    )


def _agents_with_one_unsized_resume(spawn_count, count: int) -> tuple:
    plain = tuple(
        spawn_count.AgentTally(
            agent_id=f"a{i}", agent_type="praxion:implementer", spawned_at="t0", resumes=()
        )
        for i in range(count - 1)
    )
    resumed = spawn_count.AgentTally(
        agent_id="resumed",
        agent_type="praxion:implementer",
        spawned_at="t0",
        resumes=(spawn_count.Resume(at="t1", context_tokens=None),),
    )
    return (*plain, resumed)


def test_an_unsized_resume_never_hides_its_agents_spawn() -> None:
    """Budget-many agents, one of them resumed unsized: the spawns alone meet the budget."""
    import spawn_count

    result = spawn_count.verdict(
        _agents_with_one_unsized_resume(spawn_count, 8), budget=8, threshold=250_000
    )

    assert result.charged == 8
    assert result.label == "indeterminate"


def test_spawns_past_budget_read_over_even_with_an_unsized_resume() -> None:
    """Nine spawns against eight is over, whatever the unsized resume turns out to be."""
    import spawn_count

    result = spawn_count.verdict(
        _agents_with_one_unsized_resume(spawn_count, 9), budget=8, threshold=250_000
    )

    assert result.charged == 9
    assert result.label == "over"


def test_verdict_is_no_budget_label_when_budget_is_none() -> None:
    """Omitting --budget still counts (exit 0) -- it just has nothing to compare against."""
    import spawn_count

    tallies = (
        spawn_count.AgentTally(
            agent_id="a1", agent_type="praxion:implementer", spawned_at="t0", resumes=()
        ),
    )

    result = spawn_count.verdict(tallies, budget=None, threshold=250_000)

    assert result.label == "no-budget"


# -- CLI tests: the production call shape, exit codes, JSON output ----------------


def test_json_output_shape_and_cross_project_filtering(tmp_path: Path) -> None:
    """The real production invocation: `uv run python scripts/spawn_count.py --json`.

    Splits the verbatim rows across the .1 archive and the live file (proving the
    rotation-boundary read), and includes the unrelated "deep-fix-round" start row to
    prove it is excluded from the "praxion"-scoped tally.
    """
    repo = tmp_path / "repo"
    repo.mkdir()
    _write_wal(
        repo,
        dot1_lines=[_ROW_FIRST_START, _ROW_PAIRED_STOP, _ROW_OTHER_PROJECT_START],
        live_lines=[_ROW_SENDMESSAGE, _ROW_RESUME_START],
    )

    # Pin the transcript search to an empty directory: the rows are verbatim, so the
    # host's real ~/.claude/projects may hold this agent's transcript and size the resume.
    empty_projects = tmp_path / "projects"
    empty_projects.mkdir()

    result = _run_cli(
        [
            "--slug",
            "praxion",
            "--repo-root",
            str(repo),
            "--projects-dir",
            str(empty_projects),
            "--json",
        ],
        cwd=_REPO_ROOT,
    )

    assert result.returncode == 0, result.stderr
    data = json.loads(result.stdout)
    for key in (
        "slug",
        "sources",
        "rows_skipped",
        "spawns",
        "resumes",
        "charged",
        "budget",
        "verdict",
        "by_agent_type",
        "agents",
    ):
        assert key in data, f"--json output is missing {key!r}: {data!r}"
    assert data["slug"] == "praxion"
    assert data["spawns"] == 1, "the deep-fix-round row must not be counted for slug=praxion"
    assert data["resumes"]["unsized"] == 1, "no transcript was supplied -- the resume is unsized"
    assert len(data["agents"]) == 1
    assert data["agents"][0]["agent_id"] == "a65ec99bc016c1ca0"


def test_withholds_on_absent_wal(tmp_path: Path) -> None:
    """No .ai-state/observations.jsonl* at all must withhold (exit 2), never report 0 spawns."""
    repo = tmp_path / "repo"
    repo.mkdir()

    result = _run_cli(["--slug", "praxion", "--repo-root", str(repo), "--json"], cwd=_REPO_ROOT)

    assert result.returncode == 2
    assert "wal-absent" in result.stderr


def test_withholds_on_unseen_slug_and_names_projects_it_did_see(tmp_path: Path) -> None:
    """An unrecognised slug withholds and names the projects the WAL actually carries."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _write_wal(repo, dot1_lines=[_ROW_FIRST_START, _ROW_OTHER_PROJECT_START], live_lines=[])

    result = _run_cli(["--slug", "nonexistent-slug", "--repo-root", str(repo)], cwd=_REPO_ROOT)

    assert result.returncode == 2
    assert "slug-unseen" in result.stderr
    assert "praxion" in result.stderr
    assert "deep-fix-round" in result.stderr


def test_unseen_slug_states_what_makes_a_slug_seen(tmp_path: Path) -> None:
    """The withheld count says what would have made the slug seen -- and no longer blames
    the worktree name, since a spawn's stated slug is now what it is charged to."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _write_wal(repo, dot1_lines=[_ROW_FIRST_START], live_lines=[])

    result = _run_cli(["--slug", "praxion-split", "--repo-root", str(repo)], cwd=_REPO_ROOT)

    assert result.returncode == 2
    assert "slug-unseen" in result.stderr
    assert "prompt" in result.stderr
    assert "worktree" not in result.stderr
    assert "praxion" in result.stderr


def test_refuses_a_plugin_cache_repo_root(tmp_path: Path) -> None:
    """A plugin-cache root is refused (exit 2) -- mirrors the existing scripts/ convention."""
    cache_root = tmp_path / "plugins" / "cache" / "some-owner" / "praxion" / "0.1.0"
    cache_root.mkdir(parents=True)
    _write_wal(cache_root, dot1_lines=[_ROW_FIRST_START], live_lines=[])

    result = _run_cli(["--slug", "praxion", "--repo-root", str(cache_root)], cwd=_REPO_ROOT)

    assert result.returncode == 2
    assert "plugin-cache-root" in result.stderr


def test_malformed_wal_line_is_skipped_and_counted_not_zeroed(tmp_path: Path) -> None:
    """A truncated JSONL line must not zero the whole run -- it is skipped and counted."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _write_wal(
        repo,
        dot1_lines=[_ROW_FIRST_START, '{"timestamp": "2026-01-01T00:00:00+00:00", "trunc'],
        live_lines=[],
    )

    # Pin the transcript search to an empty directory: the rows are verbatim, so the
    # host's real ~/.claude/projects may hold this agent's transcript and size the resume.
    empty_projects = tmp_path / "projects"
    empty_projects.mkdir()

    result = _run_cli(
        [
            "--slug",
            "praxion",
            "--repo-root",
            str(repo),
            "--projects-dir",
            str(empty_projects),
            "--json",
        ],
        cwd=_REPO_ROOT,
    )

    assert result.returncode == 0, result.stderr
    data = json.loads(result.stdout)
    assert data["rows_skipped"] >= 1
    assert data["spawns"] == 1, "one malformed sibling line must not zero the real spawn"


def test_heavy_resume_is_charged_as_a_spawn(tmp_path: Path) -> None:
    """A resume whose transcript shows >= the heavy-context threshold counts against budget."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _write_wal(
        repo,
        dot1_lines=[_ROW_FIRST_START, _ROW_PAIRED_STOP],
        live_lines=[_ROW_SENDMESSAGE, _ROW_RESUME_START],
    )
    projects_dir = tmp_path / "claude-projects"
    _write_subagent_transcript(
        projects_dir,
        _RESUME_SESSION_ID,
        _RESUME_AGENT_ID,
        input_tokens=200_000,
        cache_read_input_tokens=40_000,
        cache_creation_input_tokens=20_000,  # sum = 260,000 >= 250,000 default threshold
    )

    result = _run_cli(
        [
            "--slug",
            "praxion",
            "--repo-root",
            str(repo),
            "--projects-dir",
            str(projects_dir),
            "--budget",
            "1",
            "--json",
        ],
        cwd=_REPO_ROOT,
    )

    data = json.loads(result.stdout)
    assert data["resumes"]["heavy"] == 1
    assert data["charged"] == 2, "spawns(1) + heavy resumes(1) must both count against budget"
    assert data["verdict"] == "over"
    assert result.returncode == 1


def test_light_resume_under_threshold_is_not_charged(tmp_path: Path) -> None:
    """A resume below the heavy-context threshold stays a free resume, not a charged spawn."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _write_wal(
        repo,
        dot1_lines=[_ROW_FIRST_START, _ROW_PAIRED_STOP],
        live_lines=[_ROW_SENDMESSAGE, _ROW_RESUME_START],
    )
    projects_dir = tmp_path / "claude-projects"
    _write_subagent_transcript(
        projects_dir,
        _RESUME_SESSION_ID,
        _RESUME_AGENT_ID,
        input_tokens=100_000,
        cache_read_input_tokens=50_000,  # sum = 150,000 < 250,000 default threshold
    )

    result = _run_cli(
        [
            "--slug",
            "praxion",
            "--repo-root",
            str(repo),
            "--projects-dir",
            str(projects_dir),
            "--json",
        ],
        cwd=_REPO_ROOT,
    )

    assert result.returncode == 0, result.stderr
    data = json.loads(result.stdout)
    assert data["resumes"]["light"] == 1
    assert data["resumes"]["heavy"] == 0
    assert data["charged"] == 1


def test_no_context_flag_forces_unsized_even_with_a_heavy_transcript_available(
    tmp_path: Path,
) -> None:
    """--no-context skips transcript globbing entirely -- the resume reads unsized, not heavy."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _write_wal(
        repo,
        dot1_lines=[_ROW_FIRST_START, _ROW_PAIRED_STOP],
        live_lines=[_ROW_SENDMESSAGE, _ROW_RESUME_START],
    )
    projects_dir = tmp_path / "claude-projects"
    _write_subagent_transcript(
        projects_dir, _RESUME_SESSION_ID, _RESUME_AGENT_ID, input_tokens=999_999
    )

    result = _run_cli(
        [
            "--slug",
            "praxion",
            "--repo-root",
            str(repo),
            "--projects-dir",
            str(projects_dir),
            "--no-context",
            "--json",
        ],
        cwd=_REPO_ROOT,
    )

    assert result.returncode == 0, result.stderr
    data = json.loads(result.stdout)
    assert data["resumes"]["unsized"] == 1
    assert data["resumes"]["heavy"] == 0


# -- An unreadable log withholds; it is never read as an empty one (td-276) ------


@pytest.mark.skipif(os.geteuid() == 0, reason="root reads a chmod-000 file")
def test_withholds_on_an_unreadable_wal(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _write_wal(repo, dot1_lines=[], live_lines=[_ROW_FIRST_START])
    live = repo / ".ai-state" / "observations.jsonl"
    live.chmod(0o000)
    try:
        result = _run_cli(["--slug", "praxion", "--repo-root", str(repo), "--json"], cwd=_REPO_ROOT)
    finally:
        live.chmod(0o644)

    assert result.returncode == 2, result.stdout
    assert "wal-unreadable" in result.stderr


# -- Attribution: which slug a spawn counts toward ---------------------------------
# Rows below follow the on-disk row contract. A new-format `agent_start` carries
# `slug_attribution`; the `Agent` result is a `tool_use` row naming the spawned agent in
# `spawned_agent_id` with the slug the prompt stated (or null) in `task_slug`.

_T0 = "2026-09-30T10:00:00+00:00"
_T1 = "2026-09-30T10:01:00+00:00"
_T2 = "2026-09-30T10:02:00+00:00"
_CHECKOUT = "parent-repo"


def _start(agent_id: str, *, at: str = _T0, project: str = _CHECKOUT, legacy: bool = False) -> dict:
    row = {
        "timestamp": at,
        "session_id": "sess-1",
        "agent_type": "praxion:implementer",
        "agent_id": agent_id,
        "project": project,
        "event_type": "agent_start",
    }
    if not legacy:
        row["slug_attribution"] = "spawn-prompt"
    return row


def _result(
    agent_id: str, task_slug: str | None, *, at: str = _T1, project: str = _CHECKOUT
) -> dict:
    return {
        "timestamp": at,
        "session_id": "sess-1",
        "agent_type": "main",
        "agent_id": "sess-1",
        "project": project,
        "event_type": "tool_use",
        "tool_name": "Agent",
        "spawned_agent_id": agent_id,
        "spawned_agent_type": "praxion:verifier",
        "task_slug": task_slug,
    }


def _owners(rows: list[dict]) -> dict[str, str | None]:
    import spawn_count

    return {t.agent_id: t.owner for t in spawn_count.tally(rows)}


def test_a_row_written_before_slug_attribution_counts_toward_its_project() -> None:
    assert _owners([_start("a1", project="old-checkout", legacy=True)]) == {"a1": "old-checkout"}


def test_a_spawn_counts_toward_the_slug_its_result_row_states() -> None:
    rows = [_start("a1"), _result("a1", "stated-slug")]

    assert _owners(rows) == {"a1": "stated-slug"}


def test_a_result_row_stating_no_slug_counts_toward_its_own_project() -> None:
    rows = [_start("a1"), _result("a1", None, project="result-checkout")]

    assert _owners(rows) == {"a1": "result-checkout"}


def test_a_legacy_start_outranks_a_result_row() -> None:
    rows = [_start("a1", project="old-checkout", legacy=True), _result("a1", "stated-slug")]

    assert _owners(rows) == {"a1": "old-checkout"}


def test_a_new_start_without_a_result_row_is_unattributed() -> None:
    assert _owners([_start("a1")]) == {"a1": None}


def test_the_result_row_may_arrive_before_the_start() -> None:
    rows = [_result("a1", "stated-slug", at=_T0), _start("a1", at=_T1)]

    assert _owners(rows) == {"a1": "stated-slug"}


def test_a_result_row_alone_makes_a_spawn_dated_and_typed_by_that_row() -> None:
    import spawn_count

    (only,) = spawn_count.tally([_result("a1", "stated-slug", at=_T1)])

    assert (only.agent_id, only.owner, only.spawned_at, only.agent_type) == (
        "a1",
        "stated-slug",
        _T1,
        "praxion:verifier",
    )
    assert only.resumes == ()


def test_a_start_dates_and_types_the_spawn_even_when_the_result_came_first() -> None:
    import spawn_count

    rows = [_result("a1", "stated-slug", at=_T0), _start("a1", at=_T2)]

    (only,) = spawn_count.tally(rows)

    assert (only.spawned_at, only.agent_type) == (_T2, "praxion:implementer")
    assert only.resumes == ()


def test_many_records_naming_one_agent_make_one_spawn_and_every_later_start_a_resume() -> None:
    import spawn_count

    rows = [
        _start("a1", at=_T0),
        _result("a1", "stated-slug", at=_T1),
        _result("a1", "stated-slug", at=_T1),
        _start("a1", at=_T2),
        _start("a1", at=_T2),
    ]

    (only,) = spawn_count.tally(rows)

    assert [r.at for r in only.resumes] == [_T2, _T2]


def test_a_second_result_row_never_moves_the_owner() -> None:
    rows = [_result("a1", "first-slug"), _result("a1", "second-slug")]

    assert _owners(rows) == {"a1": "first-slug"}


def test_agents_are_kept_in_the_order_their_first_record_was_logged() -> None:
    rows = [_result("late", "s", at=_T0), _start("early", at=_T1), _start("late", at=_T2)]

    assert list(_owners(rows)) == ["late", "early"]


@pytest.mark.parametrize(
    "response_row",
    [
        {"event_type": "tool_use", "tool_name": "Read"},
        {"event_type": "tool_use", "spawned_agent_id": ""},
        {"event_type": "tool_use", "spawned_agent_id": None},
        {"event_type": "tool_use", "spawned_agent_id": 7},
        {"event_type": "agent_stop", "spawned_agent_id": "a1"},
    ],
    ids=["plain-tool-use", "empty-id", "null-id", "non-text-id", "not-a-tool-use"],
)
def test_a_record_that_does_not_name_a_spawned_agent_is_no_spawn(response_row: dict) -> None:
    assert _owners([response_row]) == {}


def test_a_spawn_keeps_the_session_and_project_of_its_first_record() -> None:
    import spawn_count

    start = _start("a1", project="start-checkout") | {"session_id": "sess-start"}
    result = _result("a1", "s", project="result-checkout") | {"session_id": "sess-result"}

    (via_start,) = spawn_count.tally([result, start])
    (via_result,) = spawn_count.tally([result])

    assert (via_start.session_id, via_start.project) == ("sess-start", "start-checkout")
    assert (via_result.session_id, via_result.project) == ("sess-result", "result-checkout")


# -- The seen set ------------------------------------------------------------------


def _seen(rows: list[dict]) -> set[str]:
    import spawn_count

    return spawn_count.seen_slugs(rows, spawn_count.tally(rows))


def test_the_project_of_any_row_makes_a_slug_seen() -> None:
    rows = [{"event_type": "tool_use", "tool_name": "Read", "project": "quiet-checkout"}]

    assert _seen(rows) == {"quiet-checkout"}


def test_a_stated_slug_makes_a_slug_seen() -> None:
    assert _seen([_start("a1"), _result("a1", "stated-slug")]) == {_CHECKOUT, "stated-slug"}


def test_a_spawn_of_unknown_attribution_makes_no_slug_seen_beyond_its_project() -> None:
    assert _seen([_start("a1")]) == {_CHECKOUT}


def test_a_resume_never_makes_a_slug_seen() -> None:
    rows = [_start("a1"), _result("a1", "owner-slug"), _start("a1", at=_T2)]
    rows[-1]["task_slug"] = "slug-in-the-resume-message"

    assert _seen(rows) == {_CHECKOUT, "owner-slug"}


def test_a_row_without_a_project_makes_nothing_seen() -> None:
    assert _seen([{"event_type": "tool_use"}, {"event_type": "tool_use", "project": ""}]) == set()


# -- The verdict holds for spawns of unknown attribution --------------------------


def _one_spawn_with_an_unsized_resume():
    import spawn_count

    return (
        spawn_count.AgentTally(
            agent_id="definite",
            agent_type="praxion:implementer",
            spawned_at="t0",
            resumes=(spawn_count.Resume(at="t1", context_tokens=None),),
            owner="slug",
        ),
    )


@pytest.mark.parametrize(
    ("budget", "label"),
    [(0, "over"), (1, "indeterminate"), (2, "indeterminate"), (3, "indeterminate"), (4, "within")],
)
def test_the_budget_must_fit_the_charge_and_everything_pending_at_once(
    budget: int, label: str
) -> None:
    import spawn_count

    result = spawn_count.verdict(
        _one_spawn_with_an_unsized_resume(), budget, threshold=250_000, pending_spawns=2
    )

    assert (result.charged, result.label) == (1, label)


def test_pending_spawns_default_to_none() -> None:
    import spawn_count

    result = spawn_count.verdict(_one_spawn_with_an_unsized_resume(), 2, threshold=250_000)

    assert result.label == "within"


def test_pending_spawns_never_change_what_is_charged() -> None:
    import spawn_count

    held = spawn_count.verdict(
        _one_spawn_with_an_unsized_resume(), None, threshold=250_000, pending_spawns=5
    )

    assert (held.spawns, held.charged, held.label) == (1, 1, "no-budget")


# -- The command: scoping, the held verdict, the report ----------------------------


def _report(
    capsys: pytest.CaptureFixture[str], repo: Path, slug: str, *extra: str
) -> tuple[int, dict | None, str]:
    """Run `main` in-process with `--json`; returns exit code, parsed report, stderr."""
    import spawn_count

    argv = ["--slug", slug, "--repo-root", str(repo), "--no-context", "--json", *extra]
    with pytest.raises(SystemExit) as stopped:
        spawn_count.main(argv)
    captured = capsys.readouterr()
    report = json.loads(captured.out) if captured.out.strip() else None
    return stopped.value.code, report, captured.err


def _repo_with_rows(tmp_path: Path, rows: list[dict]) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _write_wal(repo, dot1_lines=[], live_lines=[json.dumps(row) for row in rows])
    return repo


def _log_with_one_definite_and_two_unattributed_spawns() -> list[dict]:
    return [
        _start("adhoc", at=_T0),
        _result("adhoc", None, at=_T0),
        _start("definite", at=_T0),
        _result("definite", "held"),
        _start("pending-x", at=_T1),
        _start("pending-y", at=_T1),
    ]


def test_a_spawn_counts_toward_its_stated_slug_and_not_toward_the_checkout(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = _repo_with_rows(tmp_path, [_start("a1"), _result("a1", "stated-slug")])

    _, stated, _ = _report(capsys, repo, "stated-slug")
    _, checkout, _ = _report(capsys, repo, _CHECKOUT)

    assert (stated["spawns"], [a["agent_id"] for a in stated["agents"]]) == (1, ["a1"])
    assert (checkout["spawns"], checkout["agents"]) == (0, [])


def test_a_resume_is_reported_under_its_spawns_slug(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    rows = [_start("a1"), _result("a1", "stated-slug"), _start("a1", at=_T2)]
    repo = _repo_with_rows(tmp_path, rows)

    _, stated, _ = _report(capsys, repo, "stated-slug")
    _, checkout, _ = _report(capsys, repo, _CHECKOUT)

    assert (stated["spawns"], stated["resumes"]["unsized"]) == (1, 1)
    assert (checkout["spawns"], checkout["resumes"]["unsized"]) == (0, 0)


def test_a_slug_only_a_spawn_states_is_not_withheld_as_unseen(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = _repo_with_rows(tmp_path, [_start("a1"), _result("a1", "fresh-slug")])

    code, report, err = _report(capsys, repo, "fresh-slug", "--budget", "8")

    assert (code, report["verdict"], err) == (0, "within", "")


def test_a_slug_nothing_states_is_withheld_as_unseen(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = _repo_with_rows(tmp_path, [_start("a1")])

    code, report, err = _report(capsys, repo, "never-stated")

    assert (code, report) == (2, None)
    assert "slug-unseen" in err


def test_unattributed_spawns_are_listed_and_left_out_of_every_slugs_count(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = _repo_with_rows(tmp_path, _log_with_one_definite_and_two_unattributed_spawns())

    _, held, _ = _report(capsys, repo, "held")

    assert held["spawns"] == 1
    assert held["unattributed"] == [
        {"agent_id": "pending-x", "agent_type": "praxion:implementer", "spawned_at": _T1},
        {"agent_id": "pending-y", "agent_type": "praxion:implementer", "spawned_at": _T1},
    ]


@pytest.mark.parametrize(
    ("budget", "code", "label"),
    [(0, 1, "over"), (1, 0, "indeterminate"), (2, 0, "indeterminate"), (3, 0, "within")],
)
def test_unattributed_spawns_hold_the_verdict_for_every_slug(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], budget: int, code: int, label: str
) -> None:
    repo = _repo_with_rows(tmp_path, _log_with_one_definite_and_two_unattributed_spawns())

    for slug in ("held", _CHECKOUT):
        got_code, report, _ = _report(capsys, repo, slug, "--budget", str(budget))
        assert (got_code, report["charged"], report["verdict"]) == (code, 1, label), slug


def test_the_human_report_names_how_many_spawns_are_unattributed(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    import spawn_count

    repo = _repo_with_rows(tmp_path, _log_with_one_definite_and_two_unattributed_spawns())

    with pytest.raises(SystemExit):
        spawn_count.main(["--slug", "held", "--repo-root", str(repo), "--no-context"])

    assert "unattributed=2" in capsys.readouterr().out


def test_a_log_of_prior_rows_reports_no_unattributed_key_and_no_human_line(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    import spawn_count

    rows = [json.loads(_ROW_FIRST_START), json.loads(_ROW_RESUME_START)]
    repo = _repo_with_rows(tmp_path, rows)

    _, report, _ = _report(capsys, repo, "praxion")
    with pytest.raises(SystemExit):
        spawn_count.main(["--slug", "praxion", "--repo-root", str(repo), "--no-context"])

    assert "unattributed" not in report
    assert "unattributed" not in capsys.readouterr().out


def test_a_spawn_attributed_elsewhere_adds_nothing_to_a_prior_rows_slug(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    rows = [
        _start("old", project="old-checkout", legacy=True),
        _start("new", project="old-checkout"),
        _result("new", "other-slug", project="old-checkout"),
    ]
    repo = _repo_with_rows(tmp_path, rows)

    _, old, _ = _report(capsys, repo, "old-checkout", "--budget", "1")

    assert (old["spawns"], old["verdict"], "unattributed" in old) == (1, "within", False)


# -- The record as reported: every field the tally carries ---------------------------


def test_a_non_row_in_the_log_does_not_stop_the_rows_after_it() -> None:
    assert _owners(["not a row", None, _start("a1", legacy=True)]) == {"a1": _CHECKOUT}


def test_a_row_missing_its_fields_reads_as_blank_ones() -> None:
    import spawn_count

    (bare,) = spawn_count.tally([{"event_type": "agent_start", "agent_id": "a1"}])
    (bare_result,) = spawn_count.tally([{"event_type": "tool_use", "spawned_agent_id": "a2"}])

    for agent in (bare, bare_result):
        assert (agent.agent_type, agent.spawned_at, agent.session_id, agent.project) == ("",) * 4
        assert agent.owner is None


def test_a_resume_keeps_its_time_and_its_session() -> None:
    import spawn_count

    resumed = _start("a1", at=_T2) | {"session_id": "sess-resume"}

    (only,) = spawn_count.tally([_start("a1"), resumed, {**resumed, "session_id": None}])

    assert [(r.at, r.session_id, r.context_tokens) for r in only.resumes] == [
        (_T2, "sess-resume", None),
        (_T2, "", None),
    ]
    bare = spawn_count.tally([_start("a2"), {"event_type": "agent_start", "agent_id": "a2"}])
    assert [(r.at, r.session_id) for r in bare[0].resumes] == [("", "")]


def test_the_verdict_counts_light_and_heavy_resumes_apart() -> None:
    import spawn_count

    resumes = tuple(
        spawn_count.Resume(at="t", context_tokens=tokens) for tokens in (10, 20, 300_000, None)
    )
    agent = spawn_count.AgentTally("a1", "t", "t0", resumes, owner="slug")

    result = spawn_count.verdict((agent,), budget=9, threshold=250_000)

    assert (
        result.spawns,
        result.charged,
        result.resumes_light,
        result.resumes_heavy,
        result.resumes_unsized,
        result.budget,
    ) == (1, 2, 2, 1, 1, 9)


def test_a_heavy_resume_is_found_by_the_given_threshold() -> None:
    import spawn_count

    agent = spawn_count.AgentTally(
        "a1", "t", "t0", (spawn_count.Resume(at="t", context_tokens=500),), owner="slug"
    )

    assert spawn_count.verdict((agent,), None, threshold=500).resumes_heavy == 1
    assert spawn_count.verdict((agent,), None, threshold=501).resumes_light == 1


# -- The command, end to end: what is printed and why it is withheld ---------------


def _human(capsys: pytest.CaptureFixture[str], repo: Path, slug: str, *extra: str) -> str:
    import spawn_count

    with pytest.raises(SystemExit):
        spawn_count.main(["--slug", slug, "--repo-root", str(repo), "--no-context", *extra])
    return capsys.readouterr().out


def _a_spawn_resumed_once_under(slug: str) -> list[dict]:
    return [
        _start("a1", at=_T0),
        _result("a1", slug, at=_T1),
        _start("a1", at=_T2),
    ]


def test_the_json_report_is_the_whole_envelope(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    import spawn_count

    repo = _repo_with_rows(tmp_path, _a_spawn_resumed_once_under("stated-slug"))
    argv = ["--slug", "stated-slug", "--repo-root", str(repo), "--no-context", "--json"]

    with pytest.raises(SystemExit):
        spawn_count.main([*argv, "--budget", "5"])

    expected = {
        "slug": "stated-slug",
        "sources": [".ai-state/observations.jsonl"],
        "rows_skipped": 0,
        "spawns": 1,
        "resumes": {"light": 0, "heavy": 0, "unsized": 1},
        "charged": 1,
        "budget": 5,
        "verdict": "within",
        "by_agent_type": {"praxion:implementer": 1},
        "agents": [
            {
                "agent_id": "a1",
                "agent_type": "praxion:implementer",
                "spawned_at": _T0,
                "resumes": [{"at": _T2, "context_tokens": None, "class": "unsized"}],
            }
        ],
    }
    assert capsys.readouterr().out == json.dumps(expected, indent=2) + "\n"


def test_agent_types_are_counted_per_type(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    rows = [_start("a1"), _start("a2"), _start("a3") | {"agent_type": "praxion:verifier"}]
    rows += [_result(agent, "s") for agent in ("a1", "a2", "a3")]
    repo = _repo_with_rows(tmp_path, rows)

    _, report, _ = _report(capsys, repo, "s")

    assert report["by_agent_type"] == {"praxion:implementer": 2, "praxion:verifier": 1}


def test_the_human_report_is_four_lines_of_counts(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = _repo_with_rows(tmp_path, _a_spawn_resumed_once_under("stated-slug"))

    out = _human(capsys, repo, "stated-slug", "--budget", "5")

    assert out == (
        "spawn_count: slug='stated-slug' verdict=within\n"
        "  spawns=1 charged=1 budget=5\n"
        "  resumes: light=0 heavy=0 unsized=1\n"
        "  sources=['.ai-state/observations.jsonl'] rows_skipped=0\n"
    )


def test_the_human_report_ends_with_the_unattributed_count(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = _repo_with_rows(tmp_path, [_start("a1"), _result("a1", "s"), _start("a2")])

    out = _human(capsys, repo, "s")

    assert out.endswith("rows_skipped=0\n  unattributed=1\n")


def test_a_withheld_slug_is_named_with_every_slug_that_was_seen(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    rows = [_start("a1"), _result("a1", "stated-slug"), _start("a2", project="other-checkout")]
    repo = _repo_with_rows(tmp_path, rows)

    code, report, err = _report(capsys, repo, "never-stated")

    assert (code, report) == (2, None)
    assert err == (
        "slug-unseen: slug 'never-stated' not seen in the WAL. Slugs seen: "
        f"other-checkout, {_CHECKOUT}, stated-slug. A slug is seen when some row's project "
        "names it or some spawn's prompt states it (`Task slug: <slug>`); a resume's "
        "message and a spawn of unknown attribution never make one seen.\n"
    )


def test_a_log_with_no_project_at_all_withholds_with_none_seen(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = _repo_with_rows(tmp_path, [{"event_type": "tool_use"}])

    code, _, err = _report(capsys, repo, "any-slug")

    assert code == 2
    assert "Slugs seen: (none)." in err


def test_an_absent_log_is_withheld_by_name(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()

    code, _, err = _report(capsys, repo, "any-slug")

    assert (code, err) == (
        2,
        f"wal-absent: no observation log found under {repo} (checked .ai-state/).\n",
    )


def test_a_plugin_cache_root_is_refused_by_name(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    cache_root = tmp_path / "plugins" / "cache" / "owner" / "praxion" / "1.0.0"
    cache_root.mkdir(parents=True)

    code, _, err = _report(capsys, cache_root, "any-slug")

    assert (code, err) == (
        2,
        f"plugin-cache-root: refusing to operate on a plugin-cache path: {cache_root}\n",
    )


@pytest.mark.skipif(os.geteuid() == 0, reason="root reads a chmod-000 file")
def test_an_unreadable_log_is_withheld_by_name(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = _repo_with_rows(tmp_path, [_start("a1")])
    live = repo / ".ai-state" / "observations.jsonl"
    live.chmod(0o000)
    try:
        code, _, err = _report(capsys, repo, _CHECKOUT)
    finally:
        live.chmod(0o644)

    assert code == 2
    assert err.startswith(f"wal-unreadable: {live}: ")


def test_the_heavy_context_flag_decides_which_resumes_are_charged(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    import spawn_count

    repo = _repo_with_rows(tmp_path, _a_spawn_resumed_once_under("stated-slug"))
    projects = tmp_path / "projects"
    _write_subagent_transcript(
        projects, "sess-1", "a1", input_tokens=900, timestamp="2026-09-30T10:01:30+00:00"
    )

    def charged_at(threshold: str) -> int:
        argv = ["--slug", "stated-slug", "--repo-root", str(repo), "--projects-dir", str(projects)]
        with pytest.raises(SystemExit):
            spawn_count.main([*argv, "--heavy-context", threshold, "--json"])
        return json.loads(capsys.readouterr().out)["charged"]

    assert (charged_at("900"), charged_at("901")) == (2, 1)


def test_resumes_are_sized_from_the_default_projects_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    import spawn_count

    home = tmp_path / "home"
    _write_subagent_transcript(
        home / ".claude" / "projects",
        "sess-1",
        "a1",
        input_tokens=900,
        timestamp="2026-09-30T10:01:30+00:00",
    )
    monkeypatch.setenv("HOME", str(home))
    repo = _repo_with_rows(tmp_path, _a_spawn_resumed_once_under("stated-slug"))

    with pytest.raises(SystemExit):
        spawn_count.main(["--slug", "stated-slug", "--repo-root", str(repo), "--json"])

    report = json.loads(capsys.readouterr().out)
    assert report["resumes"] == {"light": 1, "heavy": 0, "unsized": 0}
    assert report["agents"][0]["resumes"][0]["class"] == "light"


# -- An unattributed spawn is read from its own transcript --------------------------
# The first user message of an agent's transcript is the prompt it was spawned with, so a
# `Task slug:` stated there attributes an agent whose result row never arrived.


def _user_line(content: object) -> str:
    return json.dumps({"type": "user", "message": {"role": "user", "content": content}})


def _write_agent_transcript(
    projects_dir: Path,
    agent_id: str,
    lines: list[str],
    *,
    session_id: str = "sess-1",
    layout: str = "subagents",
) -> Path:
    directory = projects_dir / "-some-project" / session_id / layout
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"agent-{agent_id}.jsonl"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _unattributed(agent_id: str = "a1", project: str = _CHECKOUT):
    import spawn_count

    (agent,) = spawn_count.tally([_start(agent_id, project=project)])
    assert agent.owner is None
    return agent


def _owner_read_from(projects_dir: Path, agent) -> str | None:
    import spawn_count

    return spawn_count.resolve_owner(agent, projects_dir).owner


def test_the_slug_a_transcripts_first_message_states_attributes_its_agent(tmp_path: Path) -> None:
    _write_agent_transcript(tmp_path, "a1", [_user_line("Task slug: stated-slug\n\nDo the work.")])

    assert _owner_read_from(tmp_path, _unattributed()) == "stated-slug"


def test_a_transcript_stating_no_slug_attributes_its_agent_to_the_start_rows_project(
    tmp_path: Path,
) -> None:
    _write_agent_transcript(tmp_path, "a1", [_user_line("Look around the repository.")])

    assert _owner_read_from(tmp_path, _unattributed(project="start-checkout")) == "start-checkout"


def test_a_slug_in_a_later_message_is_ignored(tmp_path: Path) -> None:
    lines = [_user_line("Look around."), _user_line("Task slug: late-slug\n\nNow do this.")]
    _write_agent_transcript(tmp_path, "a1", lines)

    assert _owner_read_from(tmp_path, _unattributed()) == _CHECKOUT


def test_the_first_message_is_read_through_records_that_are_not_user_messages(
    tmp_path: Path,
) -> None:
    lines = [
        "",
        "not json at all",
        json.dumps(["not", "an", "object"]),
        json.dumps({"type": "summary", "summary": "Task slug: wrong-slug"}),
        json.dumps({"type": "assistant", "message": {"content": "Task slug: wrong-slug"}}),
        _user_line("Task slug: first-user-slug"),
        _user_line("Task slug: later-slug"),
    ]
    _write_agent_transcript(tmp_path, "a1", lines)

    assert _owner_read_from(tmp_path, _unattributed()) == "first-user-slug"


def test_a_slug_stated_in_a_list_of_text_blocks_is_found(tmp_path: Path) -> None:
    blocks = [
        {"type": "tool_result", "content": "ignored"},
        {"type": "text", "text": "Preamble."},
        {"type": "text", "text": "Task slug: block-slug"},
    ]
    _write_agent_transcript(tmp_path, "a1", [_user_line(blocks)])

    assert _owner_read_from(tmp_path, _unattributed()) == "block-slug"


def test_a_workflow_runs_agent_is_read_from_its_run_directory(tmp_path: Path) -> None:
    _write_agent_transcript(
        tmp_path,
        "a1",
        [_user_line("Task slug: workflow-slug")],
        layout="subagents/workflows/wf_1",
    )

    assert _owner_read_from(tmp_path, _unattributed()) == "workflow-slug"


@pytest.mark.parametrize(
    "lines",
    [
        [],
        [""],
        ["{not json"],
        [json.dumps({"type": "assistant", "message": {"content": "hello"}})],
        [_user_line(None)],
        [_user_line(7)],
        [_user_line([{"type": "image"}])],
        [json.dumps({"type": "user"})],
        [json.dumps({"type": "user", "message": "text"})],
    ],
    ids=[
        "empty-file",
        "blank-line",
        "unparseable",
        "no-user-message",
        "null-content",
        "number-content",
        "no-text-block",
        "no-message",
        "message-not-an-object",
    ],
)
def test_a_transcript_with_no_readable_prompt_leaves_its_agent_unattributed(
    tmp_path: Path, lines: list[str]
) -> None:
    _write_agent_transcript(tmp_path, "a1", lines)

    assert _owner_read_from(tmp_path, _unattributed()) is None


def test_a_non_text_first_message_is_not_skipped_for_a_later_one(tmp_path: Path) -> None:
    _write_agent_transcript(tmp_path, "a1", [_user_line(None), _user_line("Task slug: late-slug")])

    assert _owner_read_from(tmp_path, _unattributed()) is None


def test_an_undecodable_transcript_leaves_its_agent_unattributed(tmp_path: Path) -> None:
    path = _write_agent_transcript(tmp_path, "a1", [""])
    path.write_bytes(b'\xff\xfe{"type": "user"}\n')

    assert _owner_read_from(tmp_path, _unattributed()) is None


def test_no_transcript_leaves_its_agent_unattributed(tmp_path: Path) -> None:
    assert _owner_read_from(tmp_path, _unattributed()) is None


def test_another_agents_transcript_is_not_read(tmp_path: Path) -> None:
    _write_agent_transcript(tmp_path, "someone-else", [_user_line("Task slug: wrong-slug")])
    _write_agent_transcript(
        tmp_path, "a1", [_user_line("Task slug: wrong-slug")], session_id="another-session"
    )

    assert _owner_read_from(tmp_path, _unattributed()) is None


def test_an_agent_with_no_session_is_never_looked_up(tmp_path: Path) -> None:
    import spawn_count

    _write_agent_transcript(tmp_path, "a1", [_user_line("Task slug: wrong-slug")], session_id="")
    (agent,) = spawn_count.tally([_start("a1") | {"session_id": None}])

    assert spawn_count.resolve_owner(agent, tmp_path).owner is None


def test_an_agent_the_rows_attribute_is_never_read_from_a_transcript(tmp_path: Path) -> None:
    import spawn_count

    _write_agent_transcript(tmp_path, "a1", [_user_line("Task slug: transcript-slug")])
    (agent,) = spawn_count.tally([_start("a1"), _result("a1", "row-slug")])

    assert spawn_count.resolve_owner(agent, tmp_path) is agent


def test_a_resolved_agent_keeps_everything_but_its_owner(tmp_path: Path) -> None:
    import dataclasses

    import spawn_count

    _write_agent_transcript(tmp_path, "a1", [_user_line("Task slug: stated-slug")])
    agent = _unattributed()

    resolved = spawn_count.resolve_owner(agent, tmp_path)

    assert dataclasses.replace(resolved, owner=None) == agent


def test_a_workflow_runs_resume_is_sized_from_its_run_directory(tmp_path: Path) -> None:
    import spawn_count

    directory = tmp_path / "-some-project" / "sess-1" / "subagents" / "workflows" / "wf_1"
    directory.mkdir(parents=True)
    usage = {"input_tokens": 700, "cache_read_input_tokens": 50, "cache_creation_input_tokens": 5}
    turn = {
        "type": "assistant",
        "agentId": "a1",
        "timestamp": "2026-09-30T10:01:30+00:00",
        "message": {"usage": usage},
    }
    (directory / "agent-a1.jsonl").write_text(json.dumps(turn) + "\n", encoding="utf-8")

    sized = spawn_count._lookup_transcript_context(tmp_path, "sess-1", "a1", _T2)

    assert sized == 755


def test_the_subagent_directory_is_searched_before_the_workflow_directories(
    tmp_path: Path,
) -> None:
    _write_agent_transcript(tmp_path, "a1", [_user_line("Task slug: direct-slug")])
    _write_agent_transcript(
        tmp_path, "a1", [_user_line("Task slug: workflow-slug")], layout="subagents/workflows/wf_1"
    )

    assert _owner_read_from(tmp_path, _unattributed()) == "direct-slug"


# -- The command reads transcripts for unattributed spawns --------------------------


def _unattributed_pair_log() -> list[dict]:
    return [
        _start("adhoc"),
        _result("adhoc", None),
        _start("definite"),
        _result("definite", "held"),
        _start("pending-x"),
        _start("pending-y"),
    ]


def _transcripts_for_the_pending_pair(projects: Path) -> None:
    _write_agent_transcript(projects, "pending-x", [_user_line("Task slug: held\n\nReview.")])
    _write_agent_transcript(projects, "pending-y", [_user_line("Task slug: other\n\nReview.")])


def _with_transcripts(
    capsys: pytest.CaptureFixture[str], repo: Path, projects: Path, slug: str, *extra: str
) -> tuple[int, dict | None, str]:
    import spawn_count

    argv = ["--slug", slug, "--repo-root", str(repo), "--projects-dir", str(projects), "--json"]
    with pytest.raises(SystemExit) as stopped:
        spawn_count.main([*argv, *extra])
    captured = capsys.readouterr()
    report = json.loads(captured.out) if captured.out.strip() else None
    return stopped.value.code, report, captured.err


def test_transcripts_attribute_the_spawns_whose_results_never_arrived(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = _repo_with_rows(tmp_path, _unattributed_pair_log())
    _transcripts_for_the_pending_pair(tmp_path / "projects")

    _, held, _ = _with_transcripts(capsys, repo, tmp_path / "projects", "held", "--budget", "2")
    _, other, _ = _with_transcripts(capsys, repo, tmp_path / "projects", "other")

    assert [a["agent_id"] for a in held["agents"]] == ["definite", "pending-x"]
    assert (held["verdict"], "unattributed" in held) == ("within", False)
    assert [a["agent_id"] for a in other["agents"]] == ["pending-y"]


def test_a_slug_only_a_transcript_states_is_not_withheld_as_unseen(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = _repo_with_rows(tmp_path, [_start("pending-x")])
    _write_agent_transcript(
        tmp_path / "projects", "pending-x", [_user_line("Task slug: fresh-slug\n\nGo.")]
    )

    code, report, _ = _with_transcripts(capsys, repo, tmp_path / "projects", "fresh-slug")

    assert (code, report["spawns"]) == (0, 1)


def test_agents_with_no_transcript_stay_unattributed_and_hold_the_verdict(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = _repo_with_rows(tmp_path, _unattributed_pair_log())
    (tmp_path / "projects").mkdir()

    _, held, _ = _with_transcripts(capsys, repo, tmp_path / "projects", "held", "--budget", "2")

    assert held["verdict"] == "indeterminate"
    assert [u["agent_id"] for u in held["unattributed"]] == ["pending-x", "pending-y"]


def test_no_context_reads_no_transcript(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    repo = _repo_with_rows(tmp_path, _unattributed_pair_log())
    _transcripts_for_the_pending_pair(tmp_path / "projects")

    _, held, _ = _with_transcripts(capsys, repo, tmp_path / "projects", "held", "--no-context")

    assert [a["agent_id"] for a in held["agents"]] == ["definite"]
    assert len(held["unattributed"]) == 2


def test_transcripts_are_looked_up_in_the_default_projects_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    import spawn_count

    home = tmp_path / "home"
    _write_agent_transcript(
        home / ".claude" / "projects", "pending-x", [_user_line("Task slug: held")]
    )
    monkeypatch.setenv("HOME", str(home))
    repo = _repo_with_rows(tmp_path, _unattributed_pair_log())

    with pytest.raises(SystemExit):
        spawn_count.main(["--slug", "held", "--repo-root", str(repo), "--json"])

    assert json.loads(capsys.readouterr().out)["spawns"] == 2


# -- Sizing a resume from the transcript ----------------------------------------------


def _turn(agent_id: str, at: str | None, **usage: int) -> str:
    row: dict = {"type": "assistant", "agentId": agent_id, "message": {"usage": usage}}
    if at is not None:
        row["timestamp"] = at
    return json.dumps(row)


def _context_at(tmp_path: Path, lines: list[str], before: str) -> int | None:
    import spawn_count

    _write_agent_transcript(tmp_path, "a1", lines)
    return spawn_count._lookup_transcript_context(tmp_path, "sess-1", "a1", before)


def test_a_resume_is_sized_by_the_last_turn_at_or_before_it(tmp_path: Path) -> None:
    lines = [
        "",
        "{not json",
        _user_line("Task slug: s"),
        _turn("someone-else", _T1, input_tokens=9_000_000),
        _turn("a1", _T0, input_tokens=100),
        _turn(
            "a1", _T1, input_tokens=200, cache_read_input_tokens=20, cache_creation_input_tokens=3
        ),
        _turn("a1", _T2, input_tokens=900),
    ]

    assert _context_at(tmp_path, lines, _T1) == 223


def test_of_two_turns_at_the_same_instant_the_later_line_sizes_the_resume(tmp_path: Path) -> None:
    lines = [_turn("a1", _T1, input_tokens=100), _turn("a1", _T1, input_tokens=400)]

    assert _context_at(tmp_path, lines, _T1) == 400


def test_a_turn_missing_its_usage_fields_counts_what_it_has(tmp_path: Path) -> None:
    lines = [_turn("a1", _T1, cache_read_input_tokens=5)]

    assert _context_at(tmp_path, lines, _T2) == 5


def test_zero_usage_sizes_a_resume_at_zero(tmp_path: Path) -> None:
    lines = [_turn("a1", _T1, input_tokens=0, cache_read_input_tokens=0)]

    assert _context_at(tmp_path, lines, _T2) == 0


def test_a_bare_assistant_turn_sizes_a_resume_at_zero(tmp_path: Path) -> None:
    bare = json.dumps({"type": "assistant", "agentId": "a1"})

    assert _context_at(tmp_path, [bare], "") == 0


def test_a_turn_without_a_time_is_never_after_the_resume(tmp_path: Path) -> None:
    assert _context_at(tmp_path, [_turn("a1", None, input_tokens=11)], _T0) == 11


def test_a_transcript_without_a_turn_of_the_agent_leaves_the_resume_unsized(
    tmp_path: Path,
) -> None:
    lines = [_user_line("hello"), _turn("someone-else", _T0, input_tokens=100)]

    assert _context_at(tmp_path, lines, _T2) is None


def test_every_resume_is_sized_up_to_its_own_time(tmp_path: Path) -> None:
    import spawn_count

    _write_agent_transcript(
        tmp_path, "a1", [_turn("a1", _T0, input_tokens=10), _turn("a1", _T2, input_tokens=70)]
    )
    resumes = (
        spawn_count.Resume(at=_T1, context_tokens=None, session_id="sess-1"),
        spawn_count.Resume(at=_T2, context_tokens=None, session_id="sess-1"),
    )
    agent = spawn_count.AgentTally("a1", "t", _T0, resumes, owner="s")

    sized = spawn_count.resolve_resume_context(agent, tmp_path)

    assert [r.context_tokens for r in sized.resumes] == [10, 70]


def test_text_blocks_of_one_message_are_joined_by_a_line_break(tmp_path: Path) -> None:
    # A slug never continues onto the next line: joined by a line break the marker states
    # nothing and the agent falls back to its project; joined by a space it would read
    # "real-slug".
    blocks = [{"type": "text", "text": "Task slug:"}, {"type": "text", "text": "real-slug"}]
    _write_agent_transcript(tmp_path, "a1", [_user_line(blocks)])

    assert _owner_read_from(tmp_path, _unattributed()) == _CHECKOUT


def test_a_turn_logged_out_of_order_does_not_hide_the_earlier_ones(tmp_path: Path) -> None:
    lines = [_turn("a1", _T2, input_tokens=900), _turn("a1", _T0, input_tokens=100)]

    assert _context_at(tmp_path, lines, _T1) == 100


# A resume of a spawn nobody has attributed yet could belong to this slug and turn out heavy,
# so it waits in the pending pool beside the spawn itself.
@pytest.mark.parametrize(
    ("budget", "code", "label"),
    [(0, 1, "over"), (1, 0, "indeterminate"), (2, 0, "indeterminate"), (3, 0, "within")],
)
def test_a_resume_of_an_unattributed_spawn_holds_the_verdict_too(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], budget: int, code: int, label: str
) -> None:
    rows = [
        _start("definite"),
        _result("definite", "held"),
        _start("pending-x", at=_T1),
        _start("pending-x", at=_T2),
    ]
    repo = _repo_with_rows(tmp_path, rows)

    got_code, report, _ = _report(capsys, repo, "held", "--budget", str(budget))

    assert (got_code, report["charged"], report["verdict"]) == (code, 1, label)
    assert [u["agent_id"] for u in report["unattributed"]] == ["pending-x"]
