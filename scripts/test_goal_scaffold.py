"""Tests for the `goal` verb (``scripts/_goal_scaffold.py``), through the driver's entry point.

Each test builds a scratch git checkout holding a small pytest project, runs `goal` in it
(in this process, from the checkout as the working directory) and asserts what the checkout
holds afterwards: the documents, the baseline block, the deny rules, and what was refused.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import step_loop  # noqa: E402
from _goal_record import PROGRESS_HEADING, progress_line_count  # noqa: E402
from _goal_scaffold import SETTINGS_FILE, TITLE_LIMIT  # noqa: E402
from _loop_fields import Check, GoalBudget, Unmet, evaluate_check  # noqa: E402
from _plan_steps import Implementer, parse_plan_steps  # noqa: E402
from reconcile_pipeline_state import reconcile  # noqa: E402

PYTHON = sys.executable
SLUG = "scaffold-task"
STEP_NUMBER = "1"
STEP_LABEL = "Step " + STEP_NUMBER
WIDGET, WIDGET_TESTS = "src/widget.py", "tests/test_widget.py"
OUTER_LOOP_TEST = "tests/acceptance/test_contract.py"
E2E_PATH = "tests/e2e/test_journey.py"
PROTECTED_DOC = "docs/contract.md"
PROTECTED_DIRECTORY = "docs/api"
GOAL = "Make every widget test pass."
CHECK = f"{PYTHON} -m pytest {WIDGET_TESTS} -q -p no:cacheprovider"
EXPECTS = "pass=3 fail=0"
FUNCTIONS = (("one", 1), ("two", 2), ("three", 3))
IGNORED = "__pycache__/\n.pytest_cache/\n.ai-work/\n" + SETTINGS_FILE + "\n"
TASK_FILES = ("IMPLEMENTATION_PLAN.md", "WIP.md", "TASK_BRIEF.md", "TEST_RESULTS.md")
EARLIER_SETTINGS = {
    "model": "sonnet",
    "permissions": {"allow": ["Bash(ls:*)"], "deny": ["Read(./.env)", "Edit(/docs/contract.md)"]},
}


def _run(root: Path, *args: str) -> str:
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    done = subprocess.run(
        ["git", *args], cwd=root, check=True, capture_output=True, text=True, env=env
    )
    return done.stdout.strip()


def _widget(implemented: tuple[str, ...]) -> str:
    bodies = [
        f"def {name}():\n    "
        + (f"return {value}" if name in implemented else "raise NotImplementedError")
        + "\n"
        for name, value in FUNCTIONS
    ]
    return "\n\n".join(bodies)


def _widget_tests() -> str:
    names = ", ".join(name for name, _ in FUNCTIONS)
    tests = [f"def test_{n}():\n    assert {n}() == {v}\n" for n, v in FUNCTIONS]
    return f"from src.widget import {names}\n\n\n" + "\n\n".join(tests)


def build_repo(
    workspace: Path, implemented: tuple[str, ...] = ("one", "two"), ignored: str = IGNORED
) -> Path:
    """A committed checkout of a widget project whose check fails on the functions left."""
    root = workspace / "project"
    (root / "src").mkdir(parents=True)
    files = {
        ".gitignore": ignored,
        "pyproject.toml": '[project]\nname = "widget"\nversion = "0"\n\n'
        '[tool.pytest.ini_options]\npythonpath = ["."]\n',
        WIDGET: _widget(implemented),
        WIDGET_TESTS: _widget_tests(),
        OUTER_LOOP_TEST: "def test_contract():\n    assert True\n",
        PROTECTED_DOC: "# contract\n",
        f"{PROTECTED_DIRECTORY}/index.md": "# api\n",
    }
    for rel, text in files.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(text, encoding="utf-8")
    _run(root, "init", "-q")
    for key, value in (("user.name", "T"), ("user.email", "t@example.invalid")):
        _run(root, "config", key, value)
    _run(root, "config", "commit.gpgsign", "false")
    _run(root, "add", "-A")
    _run(root, "commit", "-qm", "base")
    return root


@pytest.fixture
def repo(tmp_path, monkeypatch):
    monkeypatch.delenv("PYTEST_ADDOPTS", raising=False)
    monkeypatch.setenv("PYTHONDONTWRITEBYTECODE", "1")
    root = build_repo(tmp_path)
    monkeypatch.chdir(root)
    return root


def goal_argv(
    slug=SLUG, goal=GOAL, check=CHECK, expects=EXPECTS, paths=(WIDGET,), protect=(PROTECTED_DOC,),
    iterations="4",
) -> list[str]:  # fmt: skip
    argv = ["goal", slug, "--goal", goal, "--check", check, "--expects", expects]
    argv += ["--paths", *paths] if paths else []
    argv += ["--protect", *protect] if protect else []
    return [*argv, "--iterations", str(iterations)]


def scaffold(**options):
    return step_loop.execute(goal_argv(**options))


def tree(root: Path) -> dict[str, bytes]:
    return {
        str(p.relative_to(root)): p.read_bytes()
        for p in sorted(root.rglob("*"))
        if p.is_file() and not {".git", "__pycache__"} & set(p.relative_to(root).parts)
    }


def task_text(root: Path, name: str, slug: str = SLUG) -> str:
    return (root / ".ai-work" / slug / name).read_text(encoding="utf-8")


def goal_step(root: Path):
    (step,) = parse_plan_steps(task_text(root, "IMPLEMENTATION_PLAN.md"))
    return step


def written_files() -> list[str]:
    return [f".ai-work/{SLUG}/{name}" for name in TASK_FILES] + [SETTINGS_FILE]


def mentions(lines: tuple[str, ...], word: str) -> bool:
    return any(word in line for line in lines)


def verdict_words(verdicts: list[dict]) -> list[str]:
    return [verdict["verdict"] for verdict in verdicts]


def not_edit_rules(rules: list[str]) -> list[str]:
    return [rule for rule in rules if not rule.startswith("Edit(/")]


def deny_rules(root: Path) -> list[str]:
    return json.loads((root / SETTINGS_FILE).read_text(encoding="utf-8"))["permissions"]["deny"]


# --- The refusals: nothing is written, and the message names what was refused ------------------


@pytest.mark.parametrize(
    ("options", "named"),
    [
        pytest.param({"expects": "passes three"}, "expect", id="ungrammatical-expectation"),
        pytest.param({"expects": "pass=3"}, "expect", id="expectation-missing-fail"),
        pytest.param({"check": "pytest `tests`"}, "check", id="command-with-a-backtick"),
        pytest.param({"check": "pytest 'tests"}, "check", id="command-that-cannot-be-split"),
        pytest.param({"iterations": "0"}, "iteration", id="zero-iterations"),
        pytest.param({"iterations": "-3"}, "iteration", id="negative-iterations"),
        pytest.param({"iterations": "two"}, "iteration", id="iterations-not-a-number"),
        pytest.param({"iterations": "1.5"}, "iteration", id="iterations-not-whole"),
        pytest.param({"paths": ()}, "--paths", id="no-paths"),
        pytest.param({"paths": (OUTER_LOOP_TEST,)}, "protected", id="path-under-a-default"),
        pytest.param({"paths": (PROTECTED_DOC,)}, "protected", id="path-given-to-protect"),
        pytest.param({"paths": ("../outside.py",)}, "outside", id="path-leaving-the-repository"),
        pytest.param({"slug": "../escape"}, "slug", id="slug-that-is-no-directory-name"),
        pytest.param({"goal": "  "}, "--goal", id="empty-goal"),
        pytest.param({"goal": "Check: `x` expects pass=1 fail=0"}, "read back", id="goal-as-field"),
        pytest.param({"protect": ("Makefile",)}, "read back", id="protect-without-a-directory"),
    ],
)
def test_an_unsafe_goal_is_refused_naming_what_and_nothing_is_written(repo, options, named):
    before = tree(repo)

    refused = scaffold(**options)

    assert refused.exit == 4
    assert refused.doc["outcome"] == "error"
    assert refused.doc["error"]["code"] == "usage"
    assert named in refused.doc["error"]["message"].lower()
    assert tree(repo) == before


def test_a_task_that_already_has_a_plan_is_refused_and_nothing_is_written(repo):
    scaffold()
    before = tree(repo)

    refused = scaffold(iterations="7")

    assert refused.exit == 4
    assert "IMPLEMENTATION_PLAN.md" in refused.doc["error"]["message"]
    assert tree(repo) == before


@pytest.mark.parametrize(
    "held",
    ["[]", "not json", '{"permissions": []}', '{"permissions": {"deny": "Edit(/x)"}}'],
    ids=["array", "not-json", "permissions-not-an-object", "deny-not-a-list"],
)
def test_settings_that_cannot_be_merged_are_refused_and_nothing_is_written(repo, held):
    (repo / SETTINGS_FILE).parent.mkdir(parents=True, exist_ok=True)
    (repo / SETTINGS_FILE).write_text(held, encoding="utf-8")
    before = tree(repo)

    refused = scaffold()

    assert refused.exit == 4
    assert "settings.local.json" in refused.doc["error"]["message"]
    assert tree(repo) == before


def test_a_goal_the_check_already_meets_is_refused_and_nothing_is_written(tmp_path, monkeypatch):
    monkeypatch.setenv("PYTHONDONTWRITEBYTECODE", "1")
    root = build_repo(tmp_path, implemented=("one", "two", "three"))
    monkeypatch.chdir(root)
    before = tree(root)

    refused = scaffold()

    assert refused.exit == 4
    assert "already" in refused.doc["error"]["message"]
    assert tree(root) == before


def test_a_check_that_prints_no_pytest_summary_is_refused_and_nothing_is_written(repo):
    before = tree(repo)

    refused = scaffold(check=f"{PYTHON} --version")

    assert refused.exit == 4
    assert "pytest summary" in refused.doc["error"]["message"]
    assert tree(repo) == before


# --- What is written ----------------------------------------------------------------------------


def test_the_printed_object_names_every_file_written_and_has_no_outcome(repo):
    done = scaffold()

    assert done.exit == 0
    assert done.doc["schema"] == 1
    assert done.doc["slug"] == SLUG
    assert done.doc["files"] == written_files()
    assert "outcome" not in done.doc


def test_the_step_reads_back_as_the_implementers_goal_step(repo):
    scaffold(paths=(WIDGET, "src/helpers.py"), protect=(PROTECTED_DOC, E2E_PATH), iterations="4")

    step = goal_step(repo)

    assert step.assignee == Implementer()
    assert step.files == (WIDGET, "src/helpers.py")
    assert step.read_only == (E2E_PATH, PROTECTED_DOC)
    assert step.check == Check(CHECK, step.check.expectations)
    assert step.bound == GoalBudget(4)
    assert GOAL in step.block
    assert "the check is met and no protected path changed" in step.block


def test_a_long_goal_is_cut_to_the_title_limit_and_stays_whole_in_the_body(repo):
    long_goal = "Make every widget test pass " + "and keep going " * 12

    scaffold(goal=long_goal)

    step = goal_step(repo)
    assert len(step.title) <= TITLE_LIMIT
    assert step.title.endswith("…")
    assert long_goal.strip() in step.block


def test_wip_holds_the_step_unticked_and_an_empty_progress_record(repo):
    scaffold()

    wip = task_text(repo, "WIP.md")

    assert wip.count("- [ ] " + STEP_LABEL) == 1
    assert "- [x]" not in wip
    assert PROGRESS_HEADING in wip
    assert progress_line_count(wip) == 0


def test_the_brief_has_the_goal_as_its_one_key_signal_and_guards_each_protected_path(repo):
    scaffold()

    brief = task_text(repo, "TASK_BRIEF.md")
    signals, guards = brief.split("## Key Signals")[1].split("## Health Guards")

    assert [line for line in signals.splitlines() if line.strip()] == [f"- {GOAL}"]
    assert f"`{PROTECTED_DOC}`" in guards
    assert "`tests/acceptance/**`" in guards


# --- The baseline: an unmet check through every reader ------------------------------


def test_the_baseline_block_holds_the_checks_command_and_its_reading_with_the_goal_pending(repo):
    scaffold()

    results = task_text(repo, "TEST_RESULTS.md")

    assert f"## {STEP_LABEL} — step-loop gate, baseline" in results
    assert f"Command: `{CHECK}`" in results
    assert "Result: pass=2 fail=0 skip=0 pending=1 by=step-loop" in results


def test_the_check_judges_the_baseline_unmet(repo):
    scaffold()

    outcome = evaluate_check(goal_step(repo).check, STEP_NUMBER, task_text(repo, "TEST_RESULTS.md"))

    assert isinstance(outcome, Unmet)
    assert outcome.by_step_loop


def test_the_reconciler_and_status_read_the_scaffold_as_one_step_not_yet_complete(repo):
    scaffold()
    base = _run(repo, "rev-parse", "HEAD")

    verdicts = reconcile(SLUG, repo, base, state_root=repo, include_untracked=True)
    report = step_loop.execute(["status", SLUG, "--json", "--base-ref", base]).doc

    assert len(verdicts) == 1
    assert verdict_words(verdicts) != ["verified-complete"]
    assert len(report["steps"]) == 1
    assert report["steps"][0]["verdict"] != "verified-complete"


# --- The deny rules ----------------------------------------------------------------------------


def test_each_protected_path_gets_one_anchored_edit_rule_and_no_write_rule(repo):
    scaffold(protect=(PROTECTED_DOC, PROTECTED_DIRECTORY))

    rules = deny_rules(repo)

    assert f"Edit(/{PROTECTED_DOC})" in rules
    assert f"Edit(/{PROTECTED_DIRECTORY}/**)" in rules
    assert "Edit(/tests/acceptance/**)" in rules
    assert "Edit(/CLAUDE.md)" in rules
    assert not not_edit_rules(rules)


def test_the_merge_keeps_every_setting_and_entry_and_adds_each_rule_once(repo):
    (repo / SETTINGS_FILE).parent.mkdir(parents=True, exist_ok=True)
    (repo / SETTINGS_FILE).write_text(json.dumps(EARLIER_SETTINGS), encoding="utf-8")

    scaffold()
    scaffold(slug="second-goal")

    settings = json.loads((repo / SETTINGS_FILE).read_text(encoding="utf-8"))
    rules = settings["permissions"]["deny"]
    assert settings["model"] == "sonnet"
    assert settings["permissions"]["allow"] == ["Bash(ls:*)"]
    assert rules[:2] == EARLIER_SETTINGS["permissions"]["deny"]
    assert len(rules) == len(set(rules))
    assert "Edit(/tests/e2e/**)" in rules


def test_a_second_goal_leaves_the_settings_file_byte_for_byte(repo):
    scaffold()
    after_first = (repo / SETTINGS_FILE).read_bytes()

    scaffold(slug="second-goal")

    assert (repo / SETTINGS_FILE).read_bytes() == after_first


# --- The warnings --------------------------------------------------------------------------------


def test_a_primary_checkout_gets_the_additive_warning_naming_the_settings_file(repo):
    done = scaffold()

    (warning,) = done.doc["warnings"]
    assert warning["code"] == "primary-checkout"
    assert SETTINGS_FILE in warning["message"]
    assert mentions(done.lines, "primary-checkout")


def test_a_linked_worktree_gets_no_primary_checkout_warning_and_holds_its_own_rules(
    repo, tmp_path, monkeypatch
):
    linked = tmp_path / "linked"
    _run(repo, "worktree", "add", "-q", str(linked), "-b", "scratch")
    monkeypatch.chdir(linked)

    done = scaffold()

    assert done.exit == 0
    assert done.doc["warnings"] == []
    assert (linked / SETTINGS_FILE).is_file()
    assert not (repo / SETTINGS_FILE).exists()


@pytest.mark.parametrize(
    ("ignored", "warned"),
    [(IGNORED, False), (IGNORED.replace(SETTINGS_FILE, ""), True)],
    ids=["ignored", "not-ignored"],
)
def test_git_not_ignoring_the_settings_file_is_warned_on_standard_error(
    tmp_path, monkeypatch, ignored, warned
):
    monkeypatch.setenv("PYTHONDONTWRITEBYTECODE", "1")
    root = build_repo(tmp_path, ignored=ignored)
    monkeypatch.chdir(root)

    done = scaffold()

    assert done.exit == 0
    assert mentions(done.lines, "settings-not-ignored") is warned


def test_the_goal_verb_accepts_no_location_options(repo):
    refused = step_loop.execute([*goal_argv(), "--repo-root", str(repo)])

    assert refused.exit == 4
    assert refused.doc["error"]["code"] == "usage"


# --- The check that can complete early ------------------------------------------------------------

EARLY = "check-completes-early"


@pytest.fixture
def two_targets(tmp_path, monkeypatch):
    """A checkout with one passing test and two failing ones: the check can stop at two passes."""
    monkeypatch.delenv("PYTEST_ADDOPTS", raising=False)
    monkeypatch.setenv("PYTHONDONTWRITEBYTECODE", "1")
    root = build_repo(tmp_path, implemented=("one",))
    monkeypatch.chdir(root)
    return root


def warning_codes(done) -> list[str]:
    return [warning["code"] for warning in done.doc["warnings"]]


def settings_warning(done) -> dict:
    (warning,) = [w for w in done.doc["warnings"] if w["code"] == "settings-not-ignored"]
    return warning


def early_warning(done) -> dict:
    (warning,) = [w for w in done.doc["warnings"] if w["code"] == EARLY]
    return warning


@pytest.mark.parametrize("expects", ["pass=2 fail=0", "pass>=2 fail=0", "pass=2 fail=0 pending>=0"])
def test_a_check_that_can_complete_with_its_own_failing_test_still_failing_is_warned(
    two_targets, expects
):
    done = scaffold(expects=expects)

    assert done.exit == 0
    message = early_warning(done)["message"]
    assert "up to 1 of the 2 failing" in message
    assert "pending=0" in message
    assert "pass=3" in message
    assert mentions(done.lines, EARLY)


def test_the_warning_leaves_the_check_line_as_given(two_targets):
    scaffold(expects="pass=2 fail=0")

    plan = task_text(two_targets, "IMPLEMENTATION_PLAN.md")
    assert f"**Check**: `{CHECK}` expects pass=2 fail=0" in plan


@pytest.mark.parametrize(
    "expects", ["pass=2 fail=0 pending=0", "pass>=2 fail=0 pending=0"], ids=["exact", "at-least"]
)
def test_a_check_that_expects_no_pending_test_is_not_warned(two_targets, expects):
    done = scaffold(expects=expects)

    assert EARLY not in warning_codes(done)
    assert not mentions(done.lines, EARLY)


@pytest.mark.parametrize("expects", ["pass=3 fail=0", "pass>=3 fail=0", "pass>=5 fail=0"])
def test_a_check_that_expects_every_test_to_pass_is_not_warned(two_targets, expects):
    done = scaffold(expects=expects)

    assert EARLY not in warning_codes(done)


def test_a_check_with_no_failing_target_at_the_baseline_is_not_warned(tmp_path, monkeypatch):
    monkeypatch.setenv("PYTHONDONTWRITEBYTECODE", "1")
    root = build_repo(tmp_path, implemented=tuple(name for name, _ in FUNCTIONS))
    monkeypatch.chdir(root)

    done = scaffold(expects="pass=2 fail=0")

    assert done.exit == 0
    assert EARLY not in warning_codes(done)


def test_the_warning_says_run_refuses_until_the_settings_file_is_ignored(tmp_path, monkeypatch):
    monkeypatch.setenv("PYTHONDONTWRITEBYTECODE", "1")
    root = build_repo(tmp_path, ignored=IGNORED.replace(SETTINGS_FILE, ""))
    monkeypatch.chdir(root)

    done = scaffold()

    warning = settings_warning(done)["message"]
    assert "run refuses to start until it does" in warning
    assert "add it to .gitignore and commit that change" in warning
    assert "first iteration" not in warning


def test_git_not_ignoring_the_settings_file_is_warned_in_the_printed_object_too(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("PYTHONDONTWRITEBYTECODE", "1")
    root = build_repo(tmp_path, ignored=IGNORED.replace(SETTINGS_FILE, ""))
    monkeypatch.chdir(root)

    done = scaffold()

    assert "settings-not-ignored" in warning_codes(done)
    assert mentions(done.lines, "settings-not-ignored")
