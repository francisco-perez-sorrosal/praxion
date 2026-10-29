"""The adr-conventions kit's fixture structures and the older-habit project it builds."""

from __future__ import annotations

import os
import re
import subprocess
from dataclasses import replace
from pathlib import Path

import pytest

from praxion_evals.adherence.moves import checks_adr, checks_git, kit_adr
from praxion_evals.adherence.moves.declaration import kit
from praxion_evals.adherence.moves.fixture_project import CANONICAL_BLOCKS
from praxion_evals.adherence.moves.model import OnlyKind
from praxion_evals.adherence.moves.tasks import MoveTask, target_with_slack

DECLARATION = kit("adr-conventions")

BRANCH = "add-retry-queue"
PRIOR = (
    kit_adr.PriorRecord(1, "use-sqlite", "Use SQLite for storage", "## Context\n\nOne file."),
    kit_adr.PriorRecord(2, "poll-for-jobs", "Poll for jobs", "## Context\n\nNo broker."),
)


def an_adr_fixture(**changes: object) -> kit_adr.AdrFixture:
    fixture = kit_adr.AdrFixture(
        name="job-runner",
        branch=BRANCH,
        summary="failed jobs retry from a queue instead of inline, so a slow job no longer blocks",
        sort=kit_adr.WithinComponent("runner"),
        prior=PRIOR,
        source=(("runner/jobs.py", "def run(job):\n    return job()\n"),),
        history=("Added the runner.", "Added a poller."),
    )
    return replace(fixture, **changes)


def a_task(fixture: kit_adr.AdrFixture) -> MoveTask:
    return MoveTask(
        task_id=f"{fixture.name}-plain",
        fixture=fixture.name,
        fixture_kind="managed",
        wording_variant="plain",
        wording="Record the decision.",
        named_files=(),
    )


def git(root: Path, *args: str, home: Path | None = None) -> str:
    env = {k: v for k, v in os.environ.items() if not k.startswith(("GIT_", "CLAUDE"))}
    env.update(GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1")
    if home is not None:
        env["HOME"] = str(home)
    done = subprocess.run(
        ["git", "-C", str(root), *args], env=env, capture_output=True, text=True, check=True
    )
    return done.stdout


@pytest.fixture
def built(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    fixture = an_adr_fixture()
    monkeypatch.setattr(kit_adr, "FIXTURES", (fixture,))
    return kit_adr.build_fixture(DECLARATION, a_task(fixture), tmp_path / "repo")


@pytest.mark.parametrize("branch", ["main", "master", "Feature", "a_b", "a--b", "-a", "a-", ""])
def test_a_branch_that_is_not_a_plain_working_branch_is_refused(branch: str) -> None:
    with pytest.raises(ValueError, match="not a branch a session works on"):
        an_adr_fixture(branch=branch)


@pytest.mark.parametrize(
    ("prior", "message"),
    [
        (PRIOR[:1], "at least two records"),
        ((PRIOR[0], replace(PRIOR[1], number=3)), "numbered 1..n"),
        ((PRIOR[1], PRIOR[0]), "numbered 1..n"),
        ((PRIOR[0], replace(PRIOR[1], slug=PRIOR[0].slug)), "distinct slugs"),
    ],
)
def test_prior_records_are_at_least_two_numbered_in_order_with_distinct_slugs(
    prior: tuple[kit_adr.PriorRecord, ...], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        an_adr_fixture(prior=prior)


def test_a_fixture_with_no_history_is_refused() -> None:
    with pytest.raises(ValueError, match="history of its own"):
        an_adr_fixture(history=())


def test_the_built_tree_holds_the_older_habit_records_and_an_index_that_never_mentions_drafts(
    built: Path,
) -> None:
    record = (built / PRIOR[0].path).read_text(encoding="utf-8")
    index = (built / kit_adr.DECISIONS_INDEX).read_text(encoding="utf-8")

    assert record.startswith('---\nid: dec-001\ntitle: "Use SQLite for storage"\n')
    assert "category" not in record.lower()
    assert "disconfirmation" not in record.lower()
    assert "| dec-002 | Poll for jobs | accepted |" in index
    assert "draft" not in index.lower()
    assert not (built / checks_adr.DRAFTS_DIR).exists()
    assert (built / "runner/jobs.py").is_file()
    assert ".ai-work/" in (built / ".gitignore").read_text(encoding="utf-8")
    assert git(built, "status", "--porcelain") == ""


def test_the_history_is_the_fixtures_own_and_the_records_are_in_the_baseline(built: Path) -> None:
    assert git(built, "log", "--reverse", "--format=%s").splitlines() == [
        "Added the runner.",
        "Added a poller.",
    ]
    assert (
        checks_adr.read_records(
            built, before=checks_adr.baseline_paths(built), branches=frozenset({BRANCH})
        )
        == ()
    )
    assert PRIOR[1].path in checks_adr.baseline_paths(built)


def test_the_refs_name_the_baseline_and_the_branch_the_session_starts_on(built: Path) -> None:
    assert git(built, "rev-parse", checks_git.BASELINE_REF) == git(built, "rev-parse", "HEAD")
    assert git(built, "symbolic-ref", "HEAD").strip() == f"refs/heads/{BRANCH}"
    assert checks_adr.fixture_branch(built) == BRANCH
    assert git(built, "rev-parse", "main") == git(built, "rev-parse", "HEAD")


def test_a_commit_in_a_sandbox_with_no_global_config_is_authored_by_the_fixture_identity(
    built: Path, tmp_path: Path
) -> None:
    home = tmp_path / "sandbox-home"
    home.mkdir()

    git(built, "commit", "--allow-empty", "-m", "Record the decision", home=home)

    assert git(built, "log", "-1", "--format=%ae", home=home) == git(built, "config", "user.email")


def test_the_project_instructions_carry_the_shipped_blocks_but_for_the_sidecar_and_hackathon_ones(
    built: Path,
) -> None:
    claude_md = (built / "CLAUDE.md").read_text(encoding="utf-8")
    shipped = {p.name: p.read_text(encoding="utf-8").strip() for p in CANONICAL_BLOCKS.glob("*.md")}

    assert set(kit_adr.EXCLUDED_BLOCKS) <= set(shipped)
    for name, text in shipped.items():
        assert (text in claude_md) == (name not in kit_adr.EXCLUDED_BLOCKS), name


def test_a_fixture_is_not_built_over_a_directory_that_holds_something(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture = an_adr_fixture()
    monkeypatch.setattr(kit_adr, "FIXTURES", (fixture,))
    (tmp_path / "taken.txt").write_text("x", encoding="utf-8")

    with pytest.raises(ValueError, match="is not empty"):
        kit_adr.build_fixture(DECLARATION, a_task(fixture), tmp_path)


def test_a_declaration_that_does_not_admit_the_managed_kind_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture = an_adr_fixture()
    monkeypatch.setattr(kit_adr, "FIXTURES", (fixture,))
    unmanaged_only = replace(DECLARATION, fixture_scope=OnlyKind("unmanaged"))

    with pytest.raises(ValueError, match="does not admit the managed"):
        kit_adr.build_fixture(unmanaged_only, a_task(fixture), tmp_path / "repo")


def test_a_task_of_no_fixture_here_is_refused(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="no fixture named 'job-runner'"):
        kit_adr.build_fixture(DECLARATION, a_task(an_adr_fixture()), tmp_path / "repo")


# -- The filled kit ---------------------------------------------------------------------------

SEED = 20260101
RULE_LINE_MINIMUM = 20
CATEGORY_VALUES = ("architectural", "behavioral", "implementation", "configuration")
# A backtick; a dollar sign and a space; a slash opening a word, then a letter; or a program
# name standing as a whole word, then a space and an argument.
COMMAND = re.compile(
    r"`|\$ |(?:^|\s)/[A-Za-z]|\b(?:git|python|uv|bash|pytest|npm|make|praxion-[\w-]*) \S"
)
FRONTMATTER = re.compile(r"\A---\n.*?\n---\n", re.DOTALL)


def rule_lines(repo_root: Path) -> frozenset[str]:
    rule = (repo_root / DECLARATION.moved_rule.value).read_text(encoding="utf-8")
    body = FRONTMATTER.sub("", rule, count=1)
    lines = (re.sub(r"^[-*\d.\s]+", "", line).strip().casefold() for line in body.splitlines())
    return frozenset(line for line in lines if len(line) > RULE_LINE_MINIMUM)


def declared_phrases() -> tuple[str, ...]:
    return tuple(p.casefold() for check in DECLARATION.checks.checks for p in check.phrases)


@pytest.fixture(scope="module")
def candidates() -> tuple[MoveTask, ...]:
    return kit_adr.candidates()


def test_the_candidates_outnumber_a_draw_and_pair_every_fixture_with_every_wording(
    candidates: tuple[MoveTask, ...],
) -> None:
    assert len(candidates) == len(kit_adr.FIXTURES) * len(kit_adr.WORDINGS)
    assert len(candidates) > target_with_slack()
    assert len({(t.fixture, t.wording) for t in candidates}) == len(candidates)
    assert {t.fixture_kind for t in candidates} == {"managed"}


@pytest.mark.parametrize("sort", [kit_adr.Architectural, kit_adr.WithinComponent])
def test_each_sort_has_more_candidates_than_a_draw_leaves_out(
    sort: type, candidates: tuple[MoveTask, ...]
) -> None:
    left_out = len(candidates) - target_with_slack()

    assert sum(isinstance(kit_adr.sort_of(t), sort) for t in candidates) > left_out


def test_a_draw_holds_the_target_plus_slack_of_tasks_and_asks_for_both_sorts() -> None:
    drawn = kit_adr.tasks(DECLARATION, SEED)

    assert len(drawn) == target_with_slack()
    assert {type(kit_adr.sort_of(task)) for task in drawn} == {
        kit_adr.Architectural,
        kit_adr.WithinComponent,
    }


def test_a_tasks_sort_is_its_fixtures_sort(candidates: tuple[MoveTask, ...]) -> None:
    fixtures = {fixture.name: fixture for fixture in kit_adr.FIXTURES}

    assert all(kit_adr.sort_of(t) is fixtures[t.fixture].sort for t in candidates)


def test_a_task_of_no_fixture_has_no_sort() -> None:
    with pytest.raises(ValueError, match="no fixture named"):
        kit_adr.sort_of(a_task(an_adr_fixture()))


def test_every_request_asks_for_the_decision_and_describes_it(
    candidates: tuple[MoveTask, ...],
) -> None:
    summaries = {f.name: f.summary for f in kit_adr.FIXTURES}

    assert [t.task_id for t in candidates if "decision" not in t.wording.casefold()] == []
    assert [t.task_id for t in candidates if summaries[t.fixture] not in t.wording] == []


def test_no_request_holds_a_line_of_the_rule_or_a_declared_phrase(
    candidates: tuple[MoveTask, ...], repo_root: Path
) -> None:
    needles = rule_lines(repo_root) | set(declared_phrases())

    carried = [(t.task_id, n) for t in candidates for n in needles if n in t.wording.casefold()]

    assert needles
    assert carried == []


def test_no_request_names_a_category_value_as_a_whole_word(
    candidates: tuple[MoveTask, ...],
) -> None:
    values = re.compile(r"\b(" + "|".join(CATEGORY_VALUES) + r")\b", re.IGNORECASE)

    assert [t.task_id for t in candidates if values.search(t.wording)] == []


def test_no_request_holds_a_command(candidates: tuple[MoveTask, ...]) -> None:
    assert [(t.task_id, m.group(0)) for t in candidates if (m := COMMAND.search(t.wording))] == []


@pytest.mark.parametrize("fixture", [f.name for f in kit_adr.FIXTURES])
def test_a_built_fixture_carries_no_line_of_the_rule_and_no_declared_phrase(
    fixture: str, tmp_path: Path, repo_root: Path
) -> None:
    chosen = next(f for f in kit_adr.FIXTURES if f.name == fixture)
    root = kit_adr.build_fixture(DECLARATION, a_task(chosen), tmp_path / "repo")
    needles = rule_lines(repo_root) | set(declared_phrases())
    files = [p for p in root.rglob("*") if p.is_file() and ".git" not in p.relative_to(root).parts]

    carried = [
        (p.relative_to(root).as_posix(), n)
        for p in files
        for n in needles
        if n in p.read_text(encoding="utf-8", errors="replace").casefold()
    ]

    assert carried == []


@pytest.mark.parametrize("fixture", [f.name for f in kit_adr.FIXTURES])
def test_a_built_fixture_starts_on_the_branch_it_declares(fixture: str, tmp_path: Path) -> None:
    chosen = next(f for f in kit_adr.FIXTURES if f.name == fixture)

    root = kit_adr.build_fixture(DECLARATION, a_task(chosen), tmp_path / "repo")

    assert checks_adr.fixture_branch(root) == chosen.branch
