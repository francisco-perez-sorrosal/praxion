"""One main session of a move: launched into a sandbox that holds only the arm's own copy, under
an environment that bills the session token and never the API key, with the arm carried by the
plugin directory and the task by the working directory, and its envelope and record handed back
for assessment before the sandbox is removed. A stand-in `claude` plays the harness."""

from __future__ import annotations

import json
import os
import shutil
import sys
from dataclasses import dataclass, replace
from pathlib import Path

import pytest

from praxion_evals.adherence.model import Errored
from praxion_evals.adherence.moves import declaration, launch, pinning
from praxion_evals.adherence.moves.launch import Finished, MoveLaunch
from praxion_evals.adherence.moves.model import Pinned
from praxion_evals.adherence.moves.tasks import MoveTask
from praxion_evals.live.spend import SpendLedger

REPO_ROOT = Path(__file__).resolve().parents[2]
READ_TREES = ("rules", "lib")
READ_FILES = ("claude/config/CLAUDE.md.tmpl", "scripts/render_claude_md.py")
TOKEN = "oauth-subscription-token-0123456789"
API_KEY = "sk-ant-api03-ambient-key-value"
AUTH_TOKEN = "ambient-auth-token-value"
BUDGET = 1.5
COST = 0.25
TASK = MoveTask(
    "tidy-notes-plain", "tidy-notes", "managed", "plain", "Commit notes.txt.", ("notes.txt",)
)

# The stand-in session: logs how it was started, answers as `control` says, and leaves its own
# record where Claude Code keeps one.
STAND_IN = """#!{python}
import json, os, re, sys
control = json.load(open({control!r}))
argv = sys.argv[1:]
cwd = os.getcwd()
json.dump({{"argv": argv, "cwd": cwd, "env": dict(os.environ)}}, open({log!r}, "w"))
plugin = control.get("plugin") or argv[argv.index("--plugin-dir") + 1]
leak = control.get("leak", "")
print(json.dumps({{"type": "system", "subtype": "init", "cwd": cwd, "session_id": "sess-1",
    "model": "claude-opus-5-5", "mcp_servers": [],
    "plugins": [{{"name": "praxion", "path": plugin, "source": "praxion@inline"}}]}}))
failed = control.get("fail", False)
print(json.dumps({{"type": "result", "subtype": "error_during_execution" if failed else "success",
    "is_error": failed, "result": "done " + leak, "session_id": "sess-1",
    "total_cost_usd": {cost}}}))
sys.stderr.write("stderr " + leak)
if control.get("record", True):
    name = re.sub(r"[^A-Za-z0-9]", "-", cwd)
    path = os.path.join(os.environ["CLAUDE_CONFIG_DIR"], "projects", name, "sess-1.jsonl")
    os.makedirs(os.path.dirname(path))
    open(path, "w").write(json.dumps({{"type": "user", "timestamp": "2026-10-27T09:00:00Z"}}) + "\\n")
sys.exit(1 if failed else 0)
"""


@pytest.fixture(scope="module")
def copy(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """What the user instructions render from and the rules link from, as the repository has it."""
    root = tmp_path_factory.mktemp("launch") / "full"
    for tree in READ_TREES:
        shutil.copytree(REPO_ROOT / tree, root / tree, ignore=shutil.ignore_patterns("__pycache__"))
    for relpath in READ_FILES:
        (root / relpath).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(REPO_ROOT / relpath, root / relpath)
    return root


@pytest.fixture(scope="module")
def pinned(copy: Path) -> Pinned:
    return pinning.pin(declaration.kit("git-conventions"), {"full": copy})


@dataclass(frozen=True)
class Harness:
    root: Path
    config: MoveLaunch

    @property
    def log(self) -> dict:
        return json.loads((self.root / "log.json").read_text(encoding="utf-8"))

    @property
    def started(self) -> bool:
        return (self.root / "log.json").exists()

    def script(self, **control: object) -> None:
        (self.root / "control.json").write_text(json.dumps(control), encoding="utf-8")


@pytest.fixture
def harness(tmp_path: Path, pinned: Pinned) -> Harness:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    claude = bin_dir / "claude"
    claude.write_text(
        STAND_IN.format(
            python=sys.executable,
            control=str(tmp_path / "control.json"),
            log=str(tmp_path / "log.json"),
            cost=COST,
        ),
        encoding="utf-8",
    )
    claude.chmod(0o755)
    token_file = tmp_path / "token"
    token_file.write_text(TOKEN + "\n", encoding="utf-8")
    ambient = {
        "PATH": f"{bin_dir}{os.pathsep}{os.defpath}",
        "ANTHROPIC_API_KEY": API_KEY,
        "ANTHROPIC_AUTH_TOKEN": AUTH_TOKEN,
    }
    config = MoveLaunch(tmp_path / "run", pinned, BUDGET, ambient, session_token_file=token_file)
    result = Harness(tmp_path, config)
    result.script()
    return result


@dataclass(frozen=True)
class Seen:
    """What a session leaves for its assessor, read before the sandbox is removed."""

    record: Path | None
    record_text: str
    repo: Path
    home: Path
    plugin_installs: bool
    memory_indexes: tuple[Path, ...]
    rules: tuple[Path, ...]
    sandbox: Path


def _inspect(finished: Finished) -> Seen:
    home = finished.sandbox / "home"
    text = "" if finished.record is None else finished.record.read_text(encoding="utf-8")
    return Seen(
        finished.record,
        text,
        finished.repo,
        home,
        (home / ".claude" / "plugins").exists(),
        tuple(home.rglob("MEMORY.md")),
        tuple(p.resolve() for p in (home / ".claude" / "rules").rglob("*") if p.is_file()),
        finished.sandbox,
    )


def _build(where: Path) -> None:
    where.mkdir(parents=True)
    (where / "notes.txt").write_text("notes\n", encoding="utf-8")


def _kind_of(attempt) -> str:
    assert isinstance(attempt.result, Errored), f"the launch did not error: {attempt.result!r}"
    return attempt.result.kind


def _launch(harness: Harness, copy: Path, ledger: SpendLedger | None = None, config=None):
    return launch.launch_session(
        config or harness.config,
        ledger or SpendLedger(cap_usd=10.0),
        TASK,
        "full",
        copy,
        _build,
        _inspect,
    )


# --- a launch returns the envelope and the record ---


def test_a_launch_hands_the_assessor_the_parsed_envelope_and_the_sessions_own_record(harness, copy):
    captured: list[Finished] = []

    def assess(finished: Finished) -> Seen:
        captured.append(finished)
        return _inspect(finished)

    _, attempt = launch.launch_session(
        harness.config, SpendLedger(cap_usd=10.0), TASK, "full", copy, _build, assess
    )

    seen = attempt.result
    assert isinstance(seen, Seen)
    assert captured[0].envelope.final_result.session_id == "sess-1"
    assert seen.record is not None
    assert seen.record_text.startswith('{"type": "user"')
    assert (attempt.charged_usd, attempt.model) == (COST, "claude-opus-5-5")


def test_a_session_the_harness_left_no_record_for_reads_as_having_none(harness, copy):
    harness.script(record=False)

    _, attempt = _launch(harness, copy)

    assert attempt.result.record is None


def test_the_cost_the_session_reported_is_what_the_ledger_settles_at(harness, copy):
    ledger, _ = _launch(harness, copy, SpendLedger(cap_usd=10.0))

    assert ledger.spent_usd == pytest.approx(COST)


# --- the arm and the task travel by argument and working directory ---


def test_the_arm_is_the_plugin_directory_and_the_task_a_component_of_the_working_directory(
    harness, copy
):
    _launch(harness, copy)

    log = harness.log
    argv = log["argv"]
    assert argv[argv.index("--plugin-dir") + 1] == str(copy.resolve())
    assert TASK.task_id in Path(log["cwd"]).parts


def test_the_prompt_is_the_tasks_wording_alone(harness, copy):
    _launch(harness, copy)

    argv = harness.log["argv"]
    assert argv[argv.index("-p") + 1] == TASK.wording


def test_every_session_keeps_its_budget_cap_and_the_pinned_model_and_effort(harness, copy, pinned):
    _launch(harness, copy)

    argv = harness.log["argv"]
    flags = {
        flag: argv[argv.index(flag) + 1] for flag in ("--max-budget-usd", "--model", "--effort")
    }
    assert flags == {
        "--max-budget-usd": str(BUDGET),
        "--model": pinned.model,
        "--effort": pinned.effort,
    }


# --- billing: the token, never the key ---


def test_given_a_token_file_the_session_carries_the_token_and_neither_api_key(harness, copy):
    _launch(harness, copy)

    env = harness.log["env"]
    assert env["CLAUDE_CODE_OAUTH_TOKEN"] == TOKEN
    assert "ANTHROPIC_API_KEY" not in env
    assert "ANTHROPIC_AUTH_TOKEN" not in env


def test_home_and_config_dir_are_the_sandboxs_own(harness, copy):
    _launch(harness, copy)

    env = harness.log["env"]
    assert Path(env["CLAUDE_CONFIG_DIR"]) == Path(env["HOME"]) / ".claude"
    assert harness.config.run_root in Path(env["HOME"]).parents


def test_an_empty_token_file_is_refused_before_anything_starts_or_is_spent(harness, copy):
    harness.config.session_token_file.write_text("\n", encoding="utf-8")

    ledger, attempt = _launch(harness, copy, SpendLedger(cap_usd=10.0))

    assert (harness.started, ledger.spent_usd, attempt.charged_usd) == (False, 0.0, 0.0)
    assert _kind_of(attempt) == "evaluation_exception"


@pytest.mark.parametrize("stream", ["error_tail", "result_tail"])
def test_no_error_tail_or_result_text_carries_the_token(harness, copy, stream):
    harness.script(fail=True, leak=f"token={TOKEN} and key={API_KEY}")

    _, attempt = _launch(harness, copy)

    tails = attempt.result.tails
    assert _kind_of(attempt) == "result_error"
    assert TOKEN not in getattr(tails, stream)
    assert API_KEY not in getattr(tails, stream)
    assert "[REDACTED]" in getattr(tails, stream)


# --- the sandbox holds only the arm's own ---


def test_the_sandbox_home_holds_no_plugin_install_and_no_memory_index(harness, copy):
    _, attempt = _launch(harness, copy)

    assert (attempt.result.plugin_installs, attempt.result.memory_indexes) == (False, ())


def test_every_rule_in_the_sandbox_is_one_of_the_arms_own_copy(harness, copy):
    _, attempt = _launch(harness, copy)

    rules = attempt.result.rules
    assert rules, "the sandbox links no rule at all, so this proves nothing"
    assert all(rule.is_relative_to(copy.resolve()) for rule in rules)


def _plant_plugin(config_dir: Path, copy: Path) -> None:
    (config_dir / "plugins" / "praxion").mkdir(parents=True)


def _plant_memory(config_dir: Path, copy: Path) -> None:
    (config_dir / "projects" / "p" / "memory").mkdir(parents=True)
    (config_dir / "projects" / "p" / "memory" / "MEMORY.md").write_text("- a\n", encoding="utf-8")


def _plant_foreign_rule(config_dir: Path, copy: Path) -> None:
    elsewhere = config_dir.parent.parent / "elsewhere.md"
    elsewhere.write_text("# not the arm's\n", encoding="utf-8")
    (config_dir / "rules" / "foreign.md").symlink_to(elsewhere)


def _plant_other_instructions(config_dir: Path, copy: Path) -> None:
    (config_dir / "CLAUDE.md").write_text("Answer in one line.\n", encoding="utf-8")


@pytest.mark.parametrize(
    ("plant", "named"),
    [
        (_plant_plugin, "installed plugin"),
        (_plant_memory, "MEMORY.md"),
        (_plant_foreign_rule, "rule outside its copy"),
        (_plant_other_instructions, "user instructions other than the pinned ones"),
    ],
)
def test_a_sandbox_that_leaks_starts_nothing_and_is_refused_as_a_breach(
    harness, copy, monkeypatch, plant, named
):
    populate = launch.install_user_scope

    def leaking(copy_root: Path, root: Path) -> None:
        populate(copy_root, root)
        plant(root / "home" / ".claude", copy_root)

    monkeypatch.setattr(launch, "install_user_scope", leaking)

    ledger, attempt = _launch(harness, copy, SpendLedger(cap_usd=10.0))

    assert _kind_of(attempt) == "isolation_breach"
    assert named in attempt.result.detail
    assert attempt.result.detail.startswith("the full arm's")
    assert (harness.started, ledger.spent_usd, attempt.charged_usd) == (False, 0.0, 0.0)


def test_a_session_that_loaded_another_plugin_directory_is_a_breach_not_a_graded_session(
    harness, copy
):
    harness.script(plugin="/somewhere/else")

    _, attempt = _launch(harness, copy)

    assert _kind_of(attempt) == "isolation_breach"


# --- refusals, failures and cleanup ---


def test_a_launch_the_spend_cap_refuses_starts_nothing(harness, copy):
    _, attempt = _launch(harness, copy, SpendLedger(cap_usd=BUDGET / 2))

    assert _kind_of(attempt) == "launch_refused"
    assert (harness.started, attempt.charged_usd) == (False, 0.0)


def test_a_session_that_failed_is_an_errored_launch_charged_what_it_reported(harness, copy):
    harness.script(fail=True)

    _, attempt = _launch(harness, copy)

    assert _kind_of(attempt) == "result_error"
    assert attempt.charged_usd == COST


def test_the_sandbox_is_removed_after_the_assessment_unless_the_run_keeps_it(harness, copy):
    _, removed = _launch(harness, copy)
    _, kept = _launch(harness, copy, config=replace(harness.config, keep_sandbox=True))

    assert (removed.result.sandbox.exists(), kept.result.sandbox.exists()) == (False, True)
