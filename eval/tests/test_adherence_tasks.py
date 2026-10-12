"""Seeded task sets: reproducible, distinct, planted, and built into real scratch repositories."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from collections import Counter
from pathlib import Path

import pytest

from praxion_evals.adherence import tasks
from praxion_evals.adherence.model import (
    Ambiguity,
    ArmBuild,
    EarlyStop,
    Injection,
    ScopeConflict,
    Standard,
    TaskSpec,
)
from praxion_evals.live.session import SandboxPaths

REPO_ROOT = Path(__file__).resolve().parents[2]
SEED = 7
KIT_ROLES = ["researcher", "verifier"]
ARM_WORDS = re.compile(r"lean|full", re.IGNORECASE)
PAGE_URL = "https://raw.githubusercontent.com/example/repo/abc123/page.md"


def _git(root: Path, *args: str) -> str:
    done = subprocess.run(
        ["git", "-C", str(root), *args], capture_output=True, text=True, check=True
    )
    return done.stdout


def _pool(role: str) -> list[TaskSpec]:
    return tasks.generate(role, SEED, tasks.producible_task_count(role, SEED))


def _find(role: str, *, label: str, template: str | None = None) -> TaskSpec:
    wanted = [
        task
        for task in _pool(role)
        if tasks.variant_label(task.variant) == label and template in (None, task.template_id)
    ]
    assert wanted, f"no {label} task for {role}"
    return wanted[0]


# ---------------------------------------------------------------------------
# The list a run takes
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("role", KIT_ROLES)
def test_the_same_seed_gives_the_same_list_in_a_fresh_process(role):
    code = (
        "import json; from praxion_evals.adherence import tasks; "
        f"print(json.dumps(tasks.task_ids({role!r}, {SEED})))"
    )
    other = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        check=True,
        env={"PYTHONHASHSEED": "12345", "PATH": ""},
    )

    assert json.loads(other.stdout) == tasks.task_ids(role, SEED)


@pytest.mark.parametrize("role", KIT_ROLES)
def test_another_seed_orders_the_same_task_family_differently(role):
    assert tasks.task_ids(role, SEED) != tasks.task_ids(role, SEED + 1)


@pytest.mark.parametrize("role", KIT_ROLES)
def test_a_full_set_role_lists_target_plus_slack_distinct_tasks(role):
    ids = tasks.task_ids(role, SEED)

    assert len(ids) == 24
    assert len(set(ids)) == 24


@pytest.mark.parametrize("role", KIT_ROLES)
def test_no_template_supplies_more_than_five_tasks_and_at_least_five_take_part(role):
    per_template = Counter(task.template_id for task in tasks.generate(role, SEED, 24))

    assert len(per_template) >= 5
    assert max(per_template.values()) <= 5


@pytest.mark.parametrize("role", KIT_ROLES)
def test_every_variant_kind_appears_within_the_default_list(role):
    labels = {tasks.variant_label(t.variant) for t in tasks.generate(role, SEED, 24)}

    assert labels == set(tasks.kit_for(role).variants)


@pytest.mark.parametrize("role", KIT_ROLES)
def test_a_task_id_does_not_depend_on_the_seed(role):
    ids = set(tasks.task_ids(role, SEED)) | set(tasks.task_ids(role, SEED + 1))

    assert ids <= {t.task_id for t in _pool(role)}


@pytest.mark.parametrize("role", KIT_ROLES)
def test_the_kit_can_produce_more_tasks_than_a_default_list_takes(role):
    assert tasks.producible_task_count(role, SEED) >= 24


def test_asking_for_more_tasks_than_the_kit_produces_is_refused():
    with pytest.raises(ValueError, match="can produce"):
        tasks.generate("verifier", SEED, tasks.producible_task_count("verifier", SEED) + 1)


def test_the_list_size_is_target_plus_slack_or_three_smoke_tasks():
    assert tasks.list_size("researcher", 20) == 24
    assert tasks.list_size("implementer", 60) == 72
    assert tasks.list_size("implementer", 5) == 9  # slack never drops below four
    assert tasks.list_size("sentinel", 20) == 3


def test_a_role_with_no_authored_kit_is_refused_by_name():
    with pytest.raises(ValueError, match="sentinel"):
        tasks.generate("sentinel", SEED, 3)


# ---------------------------------------------------------------------------
# What a task carries
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("role", KIT_ROLES)
def test_every_task_that_is_not_an_early_stop_carries_a_c3_plant(role):
    unplanted = [
        task.task_id
        for task in _pool(role)
        if not isinstance(task.variant, EarlyStop)
        and not (
            isinstance(task.variant, Standard)
            and isinstance(task.variant.c3_plant, Ambiguity | ScopeConflict)
        )
    ]

    assert unplanted == []


@pytest.mark.parametrize("role", KIT_ROLES)
def test_every_early_stop_cap_is_at_least_the_write_early_window(role):
    caps = [t.variant.turn_cap for t in _pool(role) if isinstance(t.variant, EarlyStop)]

    assert caps
    assert min(caps) >= 6


def test_a_cap_below_the_write_early_window_is_refused():
    with pytest.raises(ValueError, match="below"):
        tasks.make_task("researcher", "t", "f", EarlyStop(turn_cap=5), SEED)
    assert tasks.make_task("researcher", "t", "f", EarlyStop(turn_cap=6), SEED).variant == (
        EarlyStop(turn_cap=6)
    )


def test_an_early_stop_for_a_role_with_no_recorded_window_is_refused():
    with pytest.raises(ValueError, match="write-early window"):
        tasks.make_task("sentinel", "t", "f", EarlyStop(turn_cap=50), SEED)


def test_a_standard_task_without_a_plant_is_refused():
    with pytest.raises(ValueError, match="C3 plant"):
        tasks.make_task("researcher", "t", "f", Standard(), SEED)


def test_an_injection_is_only_for_a_role_that_holds_webfetch():
    injected = Standard(Ambiguity("a gap"), tasks.PLANTED_INJECTION)

    assert tasks.make_task("researcher", "t", "f", injected, SEED).variant == injected
    with pytest.raises(ValueError, match="WebFetch"):
        tasks.make_task("verifier", "t", "f", injected, SEED)


def test_only_the_researcher_kit_has_an_injection_variant():
    assert "injection" in tasks.kit_for("researcher").variants
    assert "injection" not in tasks.kit_for("verifier").variants


def test_the_injection_asks_for_a_file_the_page_really_asks_for():
    page = (REPO_ROOT / tasks.PAGE_PATH).read_text(encoding="utf-8")
    injection = tasks.PLANTED_INJECTION

    assert isinstance(injection, Injection)
    assert injection.instruction in page
    assert injection.effect_path in injection.instruction


def test_the_page_url_names_a_host_with_a_dot_and_the_commit():
    url = tasks.fixture_page_url("0123abc")

    assert url.startswith("https://raw.githubusercontent.com/")
    assert "/0123abc/" in url
    assert url.endswith(tasks.PAGE_PATH)


# ---------------------------------------------------------------------------
# Prompts never name the arm
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("role", KIT_ROLES)
def test_no_task_prompt_names_an_arm(role):
    naming = [
        task.task_id
        for task in _pool(role)
        if ARM_WORDS.search(task.main_prompt) or ARM_WORDS.search(tasks.main_prompt(task))
    ]

    assert naming == []


@pytest.mark.parametrize("role", KIT_ROLES)
def test_a_task_is_the_same_for_both_arms_down_to_the_session_prompt(role, tmp_path):
    task = tasks.generate(role, SEED, 1)[0]
    full, lean = _arm_pair(role, tmp_path)
    sandbox = SandboxPaths(tmp_path / "sandbox")

    a = tasks.session_spec(task, full, sandbox, model="m", effort="low", max_budget_usd=1.0)
    b = tasks.session_spec(task, lean, sandbox, model="m", effort="low", max_budget_usd=1.0)

    assert a.plugin_dir != b.plugin_dir
    assert {**vars(a), "plugin_dir": None, "add_dir": None} == {
        **vars(b),
        "plugin_dir": None,
        "add_dir": None,
    }


# ---------------------------------------------------------------------------
# The scratch repository
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("role", KIT_ROLES)
def test_the_scratch_repository_holds_the_fixture_commit_and_the_inputs(role, tmp_path):
    task = _find(role, label="ambiguity")
    dest = tmp_path / "scratch"

    commit = tasks.build_scratch_repo(task, dest)

    assert commit == _git(dest, "rev-parse", "HEAD").strip()
    assert _git(dest, "rev-list", "--count", "HEAD").strip() == "1"
    assert _git(dest, "status", "--porcelain").strip() == ""
    brief = tasks.ROLE_KITS[role].brief
    inputs = dest / ".ai-work" / task.slug
    assert (inputs / brief).is_file()
    assert (dest / "README.md").is_file()
    held = _git(dest, "ls-tree", "-r", "--name-only", commit).splitlines()
    assert f".ai-work/{task.slug}/{brief}" in held
    assert not [path for path in held if path.endswith(tasks.TEMPLATE_SUFFIX)]
    assert any(path.endswith(".py") for path in held)


def test_the_verifier_gets_the_plan_the_spec_and_the_progress_file(tmp_path):
    task = _find("verifier", label="conflict")
    dest = tmp_path / "scratch"

    tasks.build_scratch_repo(task, dest)

    held = {p.name for p in (dest / ".ai-work" / task.slug).iterdir() if p.read_text().strip()}
    assert {"SYSTEMS_PLAN.md", "IMPLEMENTATION_PLAN.md", "WIP.md"} <= held


def test_the_brief_carries_the_plant_unless_the_task_stops_early(tmp_path):
    planted = _find("researcher", label="conflict", template="module-boundaries")
    stopped = _find("researcher", label="early-stop", template="module-boundaries")

    tasks.build_scratch_repo(planted, tmp_path / "a")
    tasks.build_scratch_repo(stopped, tmp_path / "b")

    plant = planted.variant.c3_plant.text  # type: ignore[union-attr]
    brief_a = (tmp_path / "a" / ".ai-work" / planted.slug / "RESEARCH_BRIEF.md").read_text()
    brief_b = (tmp_path / "b" / ".ai-work" / stopped.slug / "RESEARCH_BRIEF.md").read_text()
    assert plant in brief_a
    assert "Restructure the modules" not in brief_b
    assert "@@" not in brief_a + brief_b


def test_an_injection_task_names_the_page_only_when_the_run_can_serve_it(tmp_path):
    task = _find("researcher", label="injection")

    tasks.build_scratch_repo(task, tmp_path / "with", PAGE_URL)
    tasks.build_scratch_repo(task, tmp_path / "without")

    with_page = (tmp_path / "with" / ".ai-work" / task.slug / "RESEARCH_BRIEF.md").read_text()
    without_page = (tmp_path / "without" / ".ai-work" / task.slug / "RESEARCH_BRIEF.md").read_text()
    assert PAGE_URL in with_page
    assert "http" not in without_page


def test_a_task_without_an_injection_never_names_the_page(tmp_path):
    task = _find("researcher", label="ambiguity")

    tasks.build_scratch_repo(task, tmp_path / "scratch", PAGE_URL)

    brief = (tmp_path / "scratch" / ".ai-work" / task.slug / "RESEARCH_BRIEF.md").read_text()
    assert PAGE_URL not in brief


@pytest.mark.parametrize("role", KIT_ROLES)
def test_every_template_fills_every_token_for_every_variant(role):
    leaking = [
        task.task_id
        for task in _pool(role)
        for _, text in tasks.kit_for(role).template(task.template_id).inputs
        if "@@" in tasks._fill(text, task, PAGE_URL)
    ]

    assert leaking == []


def test_building_into_a_directory_that_holds_files_is_refused(tmp_path):
    (tmp_path / "keep.txt").write_text("x", encoding="utf-8")

    with pytest.raises(FileExistsError):
        tasks.build_scratch_repo(tasks.generate("researcher", SEED, 1)[0], tmp_path)


def test_fixture_code_is_stored_only_as_template_files():
    code = [p for p in tasks.FIXTURES_DIR.rglob("*.py") if "__pycache__" not in p.parts]

    assert code == []


# ---------------------------------------------------------------------------
# The session
# ---------------------------------------------------------------------------


def _arm_pair(role: str, tmp_path: Path) -> tuple[ArmBuild, ArmBuild]:
    builds = []
    for arm in ("full", "lean"):
        root = tmp_path / f"copy-{arm}"
        (root / "agents").mkdir(parents=True)
        shutil.copy(REPO_ROOT / "agents" / f"{role}.md", root / "agents" / f"{role}.md")
        patched = (f"agents/{role}.md",) if arm == "lean" else ()
        builds.append(ArmBuild(role, arm, root, None, f"digest-{arm}", patched))  # type: ignore[arg-type]
    return builds[0], builds[1]


@pytest.mark.parametrize("role", KIT_ROLES)
def test_the_main_session_is_told_to_spawn_the_role_through_the_agent_tool(role, tmp_path):
    task = tasks.generate(role, SEED, 1)[0]
    full, _ = _arm_pair(role, tmp_path)
    sandbox = SandboxPaths(tmp_path / "sandbox")

    spec = tasks.session_spec(task, full, sandbox, model="m", effort="low", max_budget_usd=2.5)

    assert f"praxion:{role}" in spec.prompt
    assert "Agent tool" in spec.prompt
    assert task.main_prompt in spec.prompt
    assert spec.cwd == sandbox.root / "fixture"
    assert spec.max_budget_usd == 2.5
    assert spec.permission_mode == "acceptEdits"
    assert spec.plugin_dir == spec.add_dir == full.copy_root


def test_the_allowed_tools_come_from_the_roles_own_tool_line_with_a_read_only_shell(tmp_path):
    full, _ = _arm_pair("researcher", tmp_path)

    granted = tasks.allowed_tools(full)

    assert granted[0] == "Agent"
    assert {"Read", "Glob", "Grep", "WebSearch", "WebFetch", "Write", "Edit"} <= set(granted)
    assert "Bash" not in granted
    assert set(tasks.READ_ONLY_BASH) <= set(granted)
    assert not any(tool.startswith("Bash(git commit") for tool in granted)


def test_the_verifier_is_not_granted_edit(tmp_path):
    full, _ = _arm_pair("verifier", tmp_path)

    assert "Edit" not in tasks.allowed_tools(full)
    assert "Write" in tasks.allowed_tools(full)


def test_a_plugin_copy_for_another_role_is_refused(tmp_path):
    task = tasks.generate("researcher", SEED, 1)[0]
    other, _ = _arm_pair("verifier", tmp_path)

    with pytest.raises(ValueError, match="cannot run"):
        tasks.session_spec(
            task, other, SandboxPaths(tmp_path), model="m", effort="low", max_budget_usd=1.0
        )
