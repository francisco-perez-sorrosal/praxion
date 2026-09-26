"""Tests for spawn_count.py -- per-slug spawn/resume tally with a budget verdict.

Gate-liveness contract (rules/swe/gate-liveness.md): spawn_count.py is the reader an
orchestrator consults before spawning the next agent, so a miscount is a silent budget
breach. Every WAL fixture below either reproduces a real `agent_start` row verbatim (the
`a65ec99bc016c1ca0` spawn/resume pair, plus a start from an unrelated project -- both
copied from `.ai-state/observations.jsonl.1`) or is exercised through the actual CLI
entrypoint as a subprocess, never a hand-rolled stand-in for the real WAL shape.

Contract under test: a pure counting core (`tally`, `classify_resume`, `verdict`) plus
an I/O shell (the `spawn_count.py` CLI) that reads `.ai-state/observations.jsonl.1` then
`.ai-state/observations.jsonl`, filters `agent_start` rows by `project == slug`, and for
each agent counts its first start as a spawn and every later start as a resume. A resume
is classified against the resuming agent's own subagent transcript
(`<projects-dir>/*/<session_id>/subagents/agent-<agent_id>.jsonl`, globbed on the session
UUID since the CLI is never handed the project-hashed directory name Claude Code uses):
`heavy` when the last assistant turn before the resume timestamp carries
`input_tokens + cache_read_input_tokens + cache_creation_input_tokens` at or above
`--heavy-context` (default 250,000), `light` below it, `unsized` when no matching
transcript line exists. `charged = spawns + heavy resumes`; the verdict is `within` only
when both `charged <= budget` AND `charged + unsized <= budget` hold (an unsized resume
must never read as `within`), `over` when `charged > budget`, `indeterminate` otherwise,
`no-budget` when `--budget` is omitted. Exit 0 for within/indeterminate/no-budget, 1 for
over, 2 for withheld (absent WAL, an unseen slug, or a plugin-cache-root repo-root) --
withholding never reports a false "0 spawns, within budget".

BDD/TDD RED handshake: scripts/spawn_count.py does not exist yet -- every pure-core test
below fails with ModuleNotFoundError (scripts/ is on sys.path via pytest's rootdir
insertion, confirmed empirically for sibling scripts/test_*.py modules) and every CLI
test fails because the subprocess cannot find/import the script, until the implementer
lands it.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent
_SCRIPT_PATH = _REPO_ROOT / "scripts" / "spawn_count.py"

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
