"""Tests for the handoff composer's two additions: a caller-supplied next action and the writer.

``ComposeContext.next_action`` replaces section 2 and nothing else; ``write_handoff`` is the one
writer, shared by the command line and the step-loop driver. The command line's own behaviour is
pinned by ``test_compose_handoff.py``, which this file leaves alone.

Pure cases drive ``compose()`` over a hand-built context (no file, no git). Writer cases build a
throwaway git repository, a quiescent observation log and, for the readiness cases, a step whose
declared file is dirty: the state the driver is in when it stops with uncommitted work.
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

import _handoff_inputs  # noqa: E402
import compose_handoff  # noqa: E402
from compose_handoff import (  # noqa: E402
    ComposeContext,
    HandoffBlockedError,
    HandoffError,
    compose,
    write_handoff,
)

SLUG = "demo-task"
STEP_LABEL = "Step "
STEP_ID = "1"
STEP_FILE = "src/thing.py"
BOUNDARY = "planning-to-implementation"
NEXT_ACTION = "Fix the failing check in `src/thing.py`, then run the step again."
OTHER_HEADINGS = [h for h in compose_handoff.SECTION_HEADINGS if not h.startswith("§2")]
NEXT_ACTION_HEADING = compose_handoff.SECTION_HEADINGS[2]
DIRTY_STEP_FILES = "dirty-step-files"


def _sections(text: str) -> dict[str, str]:
    """Every `## ` section of a handoff, keyed by its heading."""
    parts = re.split(r"^## (.+)$", text, flags=re.MULTILINE)
    return {parts[i]: parts[i + 1].strip() for i in range(1, len(parts), 2)}


def _context(**fields) -> ComposeContext:
    return ComposeContext(
        branch="work", base_sha="abc123", composed_at="2026-01-01T00:00:00Z", **fields
    )


def _composed(next_action: str | None, existing: str | None = None) -> str:
    context = _context(next_action=next_action)
    return compose(SLUG, "/repo", BOUNDARY, existing, context=context)["text"]


def _prior_handoff() -> str:
    return compose_handoff.compose(SLUG, "/repo", BOUNDARY, None, context=_context())[
        "text"
    ].replace(compose_handoff.PLACEHOLDER, "carried body")


# -- the override, pure ----------------------------------------------------------------------


def test_with_a_next_action_section_two_holds_exactly_that_text():
    assert _sections(_composed(NEXT_ACTION))[NEXT_ACTION_HEADING] == NEXT_ACTION


def test_without_a_next_action_section_two_is_the_derived_one():
    derived = _sections(_composed(None))[NEXT_ACTION_HEADING]

    assert derived.startswith("No tracked steps yet")


def test_a_multi_line_next_action_is_kept_verbatim():
    action = "First line.\n\n- a bullet\n- another\n\nLast line."

    assert _sections(_composed(action))[NEXT_ACTION_HEADING] == action


def test_an_empty_next_action_still_replaces_the_derived_text():
    assert _sections(_composed(""))[NEXT_ACTION_HEADING] == ""


@pytest.mark.parametrize("heading", OTHER_HEADINGS)
def test_the_other_seven_sections_are_the_same_with_and_without_a_next_action(heading):
    without = _sections(_composed(None))
    with_action = _sections(_composed(NEXT_ACTION))

    assert with_action[heading] == without[heading]


def test_the_header_is_the_same_with_and_without_a_next_action():
    without = _composed(None).split("## ")[0]
    with_action = _composed(NEXT_ACTION).split("## ")[0]

    assert with_action == without


def test_the_carried_sections_still_carry_forward_byte_for_byte_with_a_next_action():
    prior = _prior_handoff()

    carried = _sections(_composed(NEXT_ACTION, existing=prior))
    before = _sections(prior)

    assert [carried[h] for h in compose_handoff.CARRIED_HEADINGS] == [
        before[h] for h in compose_handoff.CARRIED_HEADINGS
    ]


def test_a_next_action_does_not_change_the_composition_report():
    without = compose(SLUG, "/repo", BOUNDARY, None, context=_context())
    with_action = compose(SLUG, "/repo", BOUNDARY, None, context=_context(next_action=NEXT_ACTION))

    keys = ("byte_count", "over_8kib", "conflicts", "input_state", "boundary")
    assert {k: with_action[k] for k in keys} == {k: without[k] for k in keys}


# -- the writer ------------------------------------------------------------------------------


def _git(repo: Path, *args: str) -> str:
    done = subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True)
    return done.stdout.strip()


def _repo(tmp_path: Path, *, step_file_dirty: bool = False, with_step: bool = False) -> Path:
    """A repo on a branch forked from `main`, a quiescent observation log, and a pipeline.

    With `with_step`, WIP claims one step complete whose declared file is written but never
    committed when `step_file_dirty` (the readiness gate's dirty-step-files case).
    """
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test User")
    (repo / "README.md").write_text("seed\n", encoding="utf-8")
    _git(repo, "add", "README.md")
    _git(repo, "commit", "-q", "-m", "seed")
    _git(repo, "branch", "-M", "main")
    _git(repo, "checkout", "-q", "-b", "work")

    rows = [
        {"event_type": "agent_start", "agent_id": "agent-1", "session_id": "s1"},
        {"event_type": "agent_stop", "agent_id": "agent-1", "session_id": "s1"},
    ]
    (repo / ".ai-state").mkdir()
    (repo / ".ai-state" / "observations.jsonl").write_text(
        "\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8"
    )
    task_dir = repo / ".ai-work" / SLUG
    task_dir.mkdir(parents=True)
    wip = "# WIP\n\n## Progress\n\nNo steps tracked yet.\n"
    if with_step:
        wip = f"# WIP\n\n## Progress\n\n- [x] {STEP_LABEL}{STEP_ID}: build the thing\n"
        plan = f"### {STEP_LABEL}{STEP_ID}: Build the thing\n\n**Files**: {STEP_FILE}\n"
        (task_dir / "IMPLEMENTATION_PLAN.md").write_text(plan, encoding="utf-8")
    (task_dir / "WIP.md").write_text(wip, encoding="utf-8")
    if step_file_dirty:
        (repo / "src").mkdir()
        (repo / STEP_FILE).write_text("# first version\n", encoding="utf-8")
        _git(repo, "add", STEP_FILE)
        _git(repo, "commit", "-q", "-m", "first version")
        (repo / STEP_FILE).write_text("# work in progress\n", encoding="utf-8")
    return repo


def _handoff(repo: Path) -> Path:
    return repo / ".ai-work" / SLUG / "HANDOFF.md"


def test_the_writer_writes_the_handoff_with_the_next_action_as_section_two(tmp_path):
    repo = _repo(tmp_path)

    result = write_handoff(SLUG, repo, boundary=BOUNDARY, force=False, next_action=NEXT_ACTION)

    written = _handoff(repo).read_text(encoding="utf-8")
    assert result["path"] == _handoff(repo)
    assert result["text"] == written
    assert _sections(written)[NEXT_ACTION_HEADING] == NEXT_ACTION


def test_the_writer_without_a_next_action_writes_the_derived_section_two(tmp_path):
    repo = _repo(tmp_path)

    write_handoff(SLUG, repo, boundary=BOUNDARY, force=False)

    section = _sections(_handoff(repo).read_text(encoding="utf-8"))[NEXT_ACTION_HEADING]
    assert section.startswith("No tracked steps yet")


def test_a_dry_run_composes_but_writes_nothing(tmp_path):
    repo = _repo(tmp_path)

    result = write_handoff(SLUG, repo, boundary=BOUNDARY, force=False, dry_run=True)

    assert result["text"]
    assert not _handoff(repo).exists()


def test_a_base_ref_given_to_the_writer_is_the_base_sha_in_the_header(tmp_path):
    repo = _repo(tmp_path)
    seed = _git(repo, "rev-parse", "main")
    (repo / "later.txt").write_text("later\n", encoding="utf-8")
    _git(repo, "add", "later.txt")
    _git(repo, "commit", "-q", "-m", "later")

    write_handoff(SLUG, repo, boundary=BOUNDARY, force=False, base_ref=seed)

    assert f"base_sha: {seed}" in _handoff(repo).read_text(encoding="utf-8")


def test_no_boundary_names_a_mid_phase_boundary_at_the_current_step(tmp_path):
    repo = _repo(tmp_path, with_step=True)
    result = write_handoff(SLUG, repo, boundary=None, force=False)

    assert result["boundary"] == f"{compose_handoff.MID_PHASE_PREFIX}{STEP_LABEL}{STEP_ID}"


def test_no_boundary_and_no_tracked_step_is_a_refusal_that_writes_nothing(tmp_path):
    repo = _repo(tmp_path)

    with pytest.raises(HandoffError, match="no tracked step"):
        write_handoff(SLUG, repo, boundary=None, force=False)

    assert not _handoff(repo).exists()


def test_an_unparseable_prior_handoff_is_a_refusal_that_leaves_it_untouched(tmp_path):
    repo = _repo(tmp_path)
    _handoff(repo).write_text("not a handoff\n", encoding="utf-8")

    with pytest.raises(HandoffError, match="refusing to overwrite"):
        write_handoff(SLUG, repo, boundary=BOUNDARY, force=False)

    assert _handoff(repo).read_text(encoding="utf-8") == "not a handoff\n"


def test_a_second_write_carries_the_judgement_sections_forward_unchanged(tmp_path):
    repo = _repo(tmp_path)
    write_handoff(SLUG, repo, boundary=BOUNDARY, force=False)
    first = _sections(_handoff(repo).read_text(encoding="utf-8"))
    edited = (
        _handoff(repo)
        .read_text(encoding="utf-8")
        .replace(compose_handoff.PLACEHOLDER, "a standing instruction", 1)
    )
    _handoff(repo).write_text(edited, encoding="utf-8")

    write_handoff(SLUG, repo, boundary=BOUNDARY, force=False, next_action=NEXT_ACTION)

    second = _sections(_handoff(repo).read_text(encoding="utf-8"))
    kept = compose_handoff.CARRIED_HEADINGS
    assert [second[h] for h in kept] == [_sections(edited)[h] for h in kept]
    assert first[NEXT_ACTION_HEADING] != second[NEXT_ACTION_HEADING]


# -- the readiness gate when the driver stops with uncommitted work -------------------------------


def test_a_tree_dirty_in_the_steps_files_blocks_the_write_and_names_the_paths(tmp_path):
    repo = _repo(tmp_path, step_file_dirty=True, with_step=True)

    with pytest.raises(HandoffBlockedError) as blocked:
        write_handoff(SLUG, repo, boundary=BOUNDARY, force=False, next_action=NEXT_ACTION)

    assert blocked.value.verdict["reasons"] == [DIRTY_STEP_FILES]
    assert blocked.value.dirty_step_paths == (STEP_FILE,)
    assert not _handoff(repo).exists()


def test_the_block_is_a_handoff_error_so_a_caller_that_catches_only_that_still_sees_it(tmp_path):
    repo = _repo(tmp_path, step_file_dirty=True, with_step=True)

    with pytest.raises(HandoffError):
        write_handoff(SLUG, repo, boundary=BOUNDARY, force=False)


def test_forcing_writes_over_a_dirty_tree_and_records_the_override_in_the_header(tmp_path):
    repo = _repo(tmp_path, step_file_dirty=True, with_step=True)

    write_handoff(SLUG, repo, boundary=BOUNDARY, force=True, next_action=NEXT_ACTION)

    written = _handoff(repo).read_text(encoding="utf-8")
    assert "readiness: overridden" in written
    assert _sections(written)[NEXT_ACTION_HEADING] == NEXT_ACTION


def test_a_clean_tree_is_written_without_forcing_and_the_header_says_clean(tmp_path):
    repo = _repo(tmp_path, with_step=True)
    (repo / "src").mkdir()
    (repo / STEP_FILE).write_text("# done\n", encoding="utf-8")
    _git(repo, "add", STEP_FILE)
    _git(repo, "commit", "-q", "-m", "implement")

    write_handoff(SLUG, repo, boundary=BOUNDARY, force=False)

    assert "readiness: clean" in _handoff(repo).read_text(encoding="utf-8")


# -- the names the session composer and the older tests reach ------------------------------------


def test_the_private_reader_name_is_the_moved_reader():
    assert compose_handoff._read_existing is _handoff_inputs.read_existing


def test_the_handoff_error_the_composer_exports_is_the_one_the_readers_raise():
    assert compose_handoff.HandoffError is _handoff_inputs.HandoffError
