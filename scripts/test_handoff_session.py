"""Tests for session-mode handoffs and the continuation prompt.

A session handoff serves work that ran outside a pipeline -- no
``.ai-work/<slug>/WIP.md`` for the reconciler to read -- so its mechanical half
is the repository's position rather than a step position. Every test runs the
real CLI against a throwaway git repository with a quiescent observations log,
so the readiness gate, git reads and the carry-forward rule all execute as in
production.

Run: ``pytest scripts/test_handoff_session.py``.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import compose_handoff  # noqa: E402

SLUG = "demo-programme"
PLACEHOLDER = "_[to fill at the checkpoint]_"
HEADINGS = compose_handoff.SECTION_HEADINGS


def _git(repo: Path, *args: str) -> str:
    done = subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True)
    return done.stdout.strip()


def _commit(repo: Path, name: str, subject: str) -> None:
    (repo / name).write_text(subject + "\n", encoding="utf-8")
    _git(repo, "add", name)
    _git(repo, "commit", "-q", "-m", subject)


def _wal(rows: list[dict]) -> str:
    return "".join(json.dumps(row) + "\n" for row in rows)


QUIESCENT = [
    {"session_id": "s1", "event_type": "agent_start", "agent_id": "a1"},
    {"session_id": "s1", "event_type": "agent_stop", "agent_id": "a1"},
]


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    _git(tmp_path, "init", "-q", "-b", "main")
    _git(tmp_path, "config", "user.email", "t@example.com")
    _git(tmp_path, "config", "user.name", "Test")
    (tmp_path / ".gitignore").write_text(".ai-work/\n", encoding="utf-8")
    (tmp_path / ".ai-state").mkdir()
    (tmp_path / ".ai-state" / "observations.jsonl").write_text(_wal(QUIESCENT), encoding="utf-8")
    _git(tmp_path, "add", ".gitignore", ".ai-state/observations.jsonl")
    _git(tmp_path, "commit", "-q", "-m", "chore: seed the repository")
    return tmp_path


def _main(monkeypatch: pytest.MonkeyPatch, repo: Path, *args: str) -> int:
    monkeypatch.setattr(compose_handoff, "resolve_repo_root", lambda *_a, **_k: repo)
    monkeypatch.setattr(compose_handoff, "is_plugin_cache_path", lambda *_a, **_k: False)
    return compose_handoff.main([SLUG, "--repo-root", str(repo), *args])


def _handoff(repo: Path) -> Path:
    return repo / ".ai-work" / SLUG / "HANDOFF.md"


def _section(text: str, heading: str) -> str:
    start = text.index(f"## {heading}") + len(f"## {heading}")
    following = [text.find(f"## {h}", start) for h in HEADINGS]
    end = min([pos for pos in following if pos != -1], default=len(text))
    return text[start:end].strip()


def _fill(path: Path, bodies: dict[str, str]) -> None:
    text = path.read_text(encoding="utf-8")
    for heading, body in bodies.items():
        text = text.replace(f"## {heading}\n\n{_section(text, heading)}", f"## {heading}\n\n{body}")
    path.write_text(text, encoding="utf-8")


# --- writing a session handoff where no pipeline exists ---------------------------


def test_session_mode_writes_all_eight_sections_without_a_pipeline(monkeypatch, repo):
    assert _main(monkeypatch, repo, "--session", "--boundary", "session:w1") == 0

    text = _handoff(repo).read_text(encoding="utf-8")
    assert [h for h in HEADINGS if f"## {h}" in text] == list(HEADINGS)
    assert "boundary: session:w1" in text
    assert _git(repo, "rev-parse", "--short", "HEAD") in _section(text, HEADINGS[0])
    assert all(_section(text, h) == PLACEHOLDER for h in HEADINGS[2:7])


def test_a_missing_pipeline_without_the_session_flag_still_exits_nothing_to_compose(
    monkeypatch, repo
):
    assert _main(monkeypatch, repo) == 2
    assert not _handoff(repo).exists()


def test_session_boundary_defaults_to_the_compose_date(monkeypatch, repo):
    assert _main(monkeypatch, repo, "--session") == 0

    header = _handoff(repo).read_text(encoding="utf-8").split("## ", 1)[0]
    assert re.search(r"^boundary: session:\d{4}-\d{2}-\d{2}$", header, re.M)


def test_a_boundary_outside_the_session_namespace_is_rejected_in_session_mode(monkeypatch, repo):
    assert _main(monkeypatch, repo, "--session", "--boundary", "planning-to-implementation") == 3
    assert not _handoff(repo).exists()


# --- carrying the user's instructions across windows ---------------------------------


def test_a_new_session_label_carries_sections_4_to_6_verbatim_and_resets_the_digest(
    monkeypatch, repo
):
    _main(monkeypatch, repo, "--session", "--boundary", "session:w1")
    carried = {
        HEADINGS[4]: "- Ask before pushing.\n  - A push approval does not carry.",
        HEADINGS[5]: "- (1) Probe premises first.",
        HEADINGS[6]: "- The rejected merge.",
    }
    _fill(_handoff(repo), {HEADINGS[3]: "- window-one digest", **carried})

    assert _main(monkeypatch, repo, "--session", "--boundary", "session:w2") == 0

    text = _handoff(repo).read_text(encoding="utf-8")
    assert {h: _section(text, h) for h in carried} == carried
    assert _section(text, HEADINGS[3]) == PLACEHOLDER


def test_recomposing_under_the_same_session_label_keeps_the_digest(monkeypatch, repo):
    _main(monkeypatch, repo, "--session", "--boundary", "session:w1")
    _fill(_handoff(repo), {HEADINGS[3]: "- window-one digest"})

    assert _main(monkeypatch, repo, "--session", "--boundary", "session:w1") == 0

    assert (
        _section(_handoff(repo).read_text(encoding="utf-8"), HEADINGS[3]) == "- window-one digest"
    )


def test_an_unparseable_existing_handoff_is_left_untouched(monkeypatch, repo):
    path = _handoff(repo)
    path.parent.mkdir(parents=True)
    path.write_text("# notes someone wrote by hand\n", encoding="utf-8")

    assert _main(monkeypatch, repo, "--session") == 3
    assert path.read_text(encoding="utf-8") == "# notes someone wrote by hand\n"


# --- the repository position ---------------------------------------------------------------


def test_state_lists_only_the_commits_made_since_the_prior_handoff(monkeypatch, repo):
    _main(monkeypatch, repo, "--session", "--boundary", "session:w1")
    _commit(repo, "a.txt", "feat: work done in window two")

    _main(monkeypatch, repo, "--session", "--boundary", "session:w2")

    state = _section(_handoff(repo).read_text(encoding="utf-8"), HEADINGS[1])
    assert "feat: work done in window two" in state
    assert "chore: seed the repository" not in state


def test_dirty_paths_are_reported_without_refusing_the_handoff(monkeypatch, repo):
    (repo / "scratch.py").write_text("x = 1\n", encoding="utf-8")

    assert _main(monkeypatch, repo, "--session") == 0

    assert "scratch.py" in _section(_handoff(repo).read_text(encoding="utf-8"), HEADINGS[0])


def test_a_spawn_in_flight_refuses_and_writes_nothing(monkeypatch, repo):
    rows = [*QUIESCENT, {"session_id": "s1", "event_type": "agent_start", "agent_id": "a2"}]
    (repo / ".ai-state" / "observations.jsonl").write_text(_wal(rows), encoding="utf-8")

    assert _main(monkeypatch, repo, "--session") == 1
    assert not _handoff(repo).exists()


# --- the continuation prompt ------------------------------------------------------------------


def _json_report(monkeypatch, repo, capsys, *args: str) -> dict:
    capsys.readouterr()
    assert _main(monkeypatch, repo, *args, "--json") == 0
    return json.loads(capsys.readouterr().out)


def test_session_report_carries_a_prompt_that_points_at_the_handoff_file(monkeypatch, repo, capsys):
    prompt = _json_report(monkeypatch, repo, capsys, "--session")["continuation_prompt"]

    assert f".ai-work/{SLUG}/HANDOFF.md" in prompt
    assert str(repo) in prompt
    assert "§0" in prompt
    assert "§2" in prompt
    assert "/resume-pipeline" not in prompt


def test_pipeline_report_prompt_ends_in_resume_pipeline(monkeypatch, repo, capsys):
    task_dir = repo / ".ai-work" / SLUG
    task_dir.mkdir(parents=True)
    (task_dir / "WIP.md").write_text("# WIP\n\nNo steps yet.\n", encoding="utf-8")

    report = _json_report(monkeypatch, repo, capsys, "--boundary", "architecture-to-planning")

    assert f"/resume-pipeline {SLUG}" in report["continuation_prompt"]
