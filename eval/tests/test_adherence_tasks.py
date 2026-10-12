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
from praxion_evals.adherence.catalog_rows import DIFF_MODE, ON_DEMAND_MODE, SHADOWING_MODE
from praxion_evals.adherence.checks_process import ACCEPTANCE_DESIGN_MODE, PARALLEL_MODE
from praxion_evals.adherence.model import (
    ROLES,
    WEBFETCH_ROLES,
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
KIT_ROLES = ["researcher", "verifier", "implementer"]  # the full-set roles
SMOKE_ROLES = [role for role in ROLES if role not in tasks.FULL_SET_ROLES]
SMOKE_LIST = 3
ARM_WORDS = re.compile(r"lean|full", re.IGNORECASE)
UNFILLED_TOKEN = re.compile(r"@@[A-Z]+@@")
TEMPLATE = {"researcher": "module-boundaries", "verifier": "plan-adherence"}
FIXTURE = "ledger-cli"
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
    assert tasks.list_size("implementer", 5) == 5 + tasks.SLACK_FLOOR
    assert tasks.list_size("implementer", 100) == 100 + 100 // tasks.SLACK_DIVISOR
    assert tasks.list_size("sentinel", 20) == 3


def test_a_role_with_no_authored_kit_is_refused_by_name(monkeypatch):
    monkeypatch.setattr(tasks, "ROLE_KITS", {})
    tasks.kit_for.cache_clear()
    try:
        with pytest.raises(ValueError, match="sentinel"):
            tasks.generate("sentinel", SEED, 3)
    finally:
        tasks.kit_for.cache_clear()


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
    assert min(caps) >= tasks.WRITE_EARLY_TURNS


TPL = TEMPLATE["researcher"]
FIX = FIXTURE


def test_a_task_naming_a_template_or_fixture_the_kit_lacks_is_refused():
    plant = Standard(Ambiguity("a gap"))

    with pytest.raises(ValueError, match="no template"):
        tasks.make_task("researcher", "mistyped", FIX, plant, SEED)
    with pytest.raises(ValueError, match="no fixture"):
        tasks.make_task("researcher", TPL, "mistyped", plant, SEED)


def test_a_cap_below_the_write_early_window_is_refused():
    with pytest.raises(ValueError, match="below"):
        tasks.make_task("researcher", TPL, FIX, EarlyStop(turn_cap=5), SEED)
    assert tasks.make_task("researcher", TPL, FIX, EarlyStop(turn_cap=6), SEED).variant == (
        EarlyStop(turn_cap=6)
    )


def test_a_standard_task_without_a_plant_is_refused():
    with pytest.raises(ValueError, match="C3 plant"):
        tasks.make_task("researcher", TPL, FIX, Standard(), SEED)


def test_an_injection_is_only_for_a_role_that_holds_webfetch():
    injected = Standard(Ambiguity("a gap"), tasks.PLANTED_INJECTION)

    assert tasks.make_task("researcher", TPL, FIX, injected, SEED).variant == injected
    with pytest.raises(ValueError, match="WebFetch"):
        tasks.make_task("verifier", TEMPLATE["verifier"], FIX, injected, SEED)


@pytest.mark.parametrize("role", ROLES)
def test_a_kit_has_an_injection_variant_exactly_when_the_role_holds_webfetch(role):
    assert ("injection" in tasks.kit_for(role).variants) == (role in WEBFETCH_ROLES)


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
    task = _find(role, label="ambiguity")
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
    assert not UNFILLED_TOKEN.search(brief_a + brief_b)


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
        if UNFILLED_TOKEN.search(tasks._fill(text, task, PAGE_URL))
    ]

    assert leaking == []


def test_a_diff_hunk_header_in_a_template_is_not_an_unfilled_token():
    task = _find("verifier", label="ambiguity")

    filled = tasks._fill("@@ -1,3 +1,4 @@ keep @@SLUG@@", task, None)

    assert filled == f"@@ -1,3 +1,4 @@ keep {task.slug}"
    with pytest.raises(ValueError, match="unfilled"):
        tasks._fill("@@MYSTERY@@", task, None)


def test_building_into_a_directory_that_holds_files_is_refused(tmp_path):
    (tmp_path / "keep.txt").write_text("x", encoding="utf-8")

    with pytest.raises(FileExistsError):
        tasks.build_scratch_repo(tasks.generate("researcher", SEED, 1)[0], tmp_path)


@pytest.mark.parametrize("role", KIT_ROLES)
def test_the_fixture_commit_ignores_the_hosts_git_configuration(role, tmp_path, monkeypatch):
    home = tmp_path / "home"
    (home / ".config" / "git").mkdir(parents=True)
    (home / ".config" / "git" / "ignore").write_text(".ai-work\n", encoding="utf-8")
    refusing = home / "hooks"
    refusing.mkdir()
    hook = refusing / "pre-commit"
    hook.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
    hook.chmod(0o755)
    (home / ".gitconfig").write_text(
        f"[core]\n\texcludesFile = {home / '.config' / 'git' / 'ignore'}\n"
        f"\thooksPath = {refusing}\n[commit]\n\tgpgsign = true\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(home / ".config"))
    task = _find(role, label="ambiguity")

    commit = tasks.build_scratch_repo(task, tmp_path / "scratch")

    held = _git(tmp_path / "scratch", "ls-tree", "-r", "--name-only", commit).splitlines()
    assert f".ai-work/{task.slug}/{tasks.ROLE_KITS[role].brief}" in held


def test_fixture_code_is_stored_only_as_template_files():
    code = [p for p in tasks.FIXTURES_DIR.rglob("*.py") if "__pycache__" not in p.parts]

    assert code == []


# ---------------------------------------------------------------------------
# The session
# ---------------------------------------------------------------------------


def _arm_pair(role: str, tmp_path: Path, turn_cap: int | None = None) -> tuple[ArmBuild, ArmBuild]:
    builds = []
    for arm in ("full", "lean"):
        root = tmp_path / f"copy-{arm}"
        (root / "agents").mkdir(parents=True)
        shutil.copy(REPO_ROOT / "agents" / f"{role}.md", root / "agents" / f"{role}.md")
        patched = (f"agents/{role}.md",) if arm == "lean" or turn_cap else ()
        builds.append(ArmBuild(role, arm, root, turn_cap, f"digest-{arm}", patched))  # type: ignore[arg-type]
    return builds[0], builds[1]


@pytest.mark.parametrize("role", KIT_ROLES)
def test_the_main_session_is_told_to_spawn_the_role_through_the_agent_tool(role, tmp_path):
    task = _find(role, label="ambiguity")
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
    task = _find("researcher", label="ambiguity")
    other, _ = _arm_pair("verifier", tmp_path)

    with pytest.raises(ValueError, match="cannot run"):
        tasks.session_spec(
            task, other, SandboxPaths(tmp_path), model="m", effort="low", max_budget_usd=1.0
        )


@pytest.mark.parametrize("role", KIT_ROLES)
def test_an_early_stop_task_runs_only_in_copies_capped_at_its_turn_cap(role, tmp_path):
    task = _find(role, label="early-stop")
    sandbox = SandboxPaths(tmp_path / "sandbox")
    cap = tasks.turn_cap_of(task)
    assert cap is not None
    capped, _ = _arm_pair(role, tmp_path / "capped", cap)
    uncapped, _ = _arm_pair(role, tmp_path / "uncapped")
    other, _ = _arm_pair(role, tmp_path / "other", cap + 1)

    spec = tasks.session_spec(task, capped, sandbox, model="m", effort="low", max_budget_usd=1.0)

    assert spec.plugin_dir == capped.copy_root
    for wrong in (uncapped, other):
        with pytest.raises(ValueError, match="capped at"):
            tasks.session_spec(task, wrong, sandbox, model="m", effort="low", max_budget_usd=1.0)


@pytest.mark.parametrize("role", KIT_ROLES)
def test_a_standard_task_is_refused_a_capped_copy(role, tmp_path):
    task = _find(role, label="conflict")
    capped, _ = _arm_pair(role, tmp_path, 6)

    assert tasks.turn_cap_of(task) is None
    with pytest.raises(ValueError, match="capped at"):
        tasks.session_spec(
            task, capped, SandboxPaths(tmp_path), model="m", effort="low", max_budget_usd=1.0
        )


# ---------------------------------------------------------------------------
# A kit refuses material that is missing, rather than building a bare fixture
# ---------------------------------------------------------------------------


@pytest.fixture
def fixtures_clone(tmp_path, monkeypatch):
    clone = tmp_path / "fixtures"
    shutil.copytree(tasks.FIXTURES_DIR, clone)
    monkeypatch.setattr(tasks, "FIXTURES_DIR", clone)
    monkeypatch.setattr(tasks, "REPOS_DIR", clone / "repos")
    monkeypatch.setattr(tasks, "OVERLAYS_DIR", clone / "overlays")
    tasks.kit_for.cache_clear()
    yield clone
    tasks.kit_for.cache_clear()  # the clone's kits must not outlive the patch


@pytest.mark.parametrize("role", KIT_ROLES)
def test_a_template_without_the_roles_brief_refuses_the_kit(role, fixtures_clone):
    brief = tasks.ROLE_KITS[role].brief
    last = sorted((fixtures_clone / role / "templates").iterdir())[-1]
    (last / brief).unlink()

    with pytest.raises(ValueError, match=f"{last.name} lacks {brief}"):
        tasks.kit_for(role)


def test_a_fixture_without_a_repository_refuses_the_kit(fixtures_clone):
    shutil.rmtree(fixtures_clone / "repos" / FIXTURE)

    with pytest.raises(ValueError, match="no repository"):
        tasks.kit_for("researcher")


def test_a_verifier_fixture_without_its_planning_inputs_refuses_the_kit(fixtures_clone):
    (fixtures_clone / "verifier" / "inputs" / FIXTURE / "WIP.md").unlink()

    with pytest.raises(ValueError, match="lacks the input WIP.md"):
        tasks.kit_for("verifier")


def test_the_researcher_needs_no_fixture_inputs_and_the_verifier_needs_three():
    assert tasks.ROLE_KITS["researcher"].fixture_inputs == ()
    assert len(tasks.ROLE_KITS["verifier"].fixture_inputs) == 3


def test_an_overlay_a_kit_names_but_lacks_refuses_the_kit(fixtures_clone):
    shutil.rmtree(fixtures_clone / "overlays" / "ci")

    with pytest.raises(ValueError, match="overlay 'ci'"):
        tasks.kit_for("cicd-engineer")


def test_a_full_set_role_with_fewer_than_five_templates_is_refused(fixtures_clone):
    last = sorted((fixtures_clone / "implementer" / "templates").iterdir())[-1]
    shutil.rmtree(last)

    with pytest.raises(ValueError, match="fewer than 5"):
        tasks.kit_for("implementer")


def test_a_smoke_role_whose_kit_cannot_reach_twenty_tasks_is_refused(fixtures_clone):
    for template in sorted((fixtures_clone / "sentinel" / "templates").iterdir())[:2]:
        shutil.rmtree(template)

    with pytest.raises(ValueError, match="12 tasks"):
        tasks.kit_for("sentinel")


def test_an_implementer_fixture_without_its_learnings_refuses_the_kit(fixtures_clone):
    (fixtures_clone / "implementer" / "inputs" / FIXTURE / "LEARNINGS.md").unlink()

    with pytest.raises(ValueError, match="lacks the input LEARNINGS.md"):
        tasks.kit_for("implementer")


# ---------------------------------------------------------------------------
# Every role: a kit owes twenty tasks, a smoke list of three, and the inputs its definition expects
# ---------------------------------------------------------------------------

# The words that put a role in a mode its definition reads from the spawn prompt, by role.
MODE_OF = {
    "architect-validator": ON_DEMAND_MODE,
    "context-engineer": SHADOWING_MODE,
    "roadmap-cartographer": DIFF_MODE,
}
NON_INTERACTIVE = re.compile(r"non-interactive", re.IGNORECASE)


@pytest.mark.parametrize("role", ROLES)
def test_every_role_can_produce_twenty_distinct_tasks(role):
    pool = _pool(role)

    assert len(pool) >= 20
    assert len({task.task_id for task in pool}) == len(pool)


@pytest.mark.parametrize("role", SMOKE_ROLES)
def test_a_smoke_role_lists_three_distinct_tasks_from_different_templates(role):
    ids = tasks.task_ids(role, SEED)
    listed = tasks.generate(role, SEED, SMOKE_LIST)

    assert ids == [task.task_id for task in listed]
    assert len(set(ids)) == SMOKE_LIST
    assert len({task.template_id for task in listed}) == SMOKE_LIST


@pytest.mark.parametrize("role", ROLES)
def test_no_prompt_names_an_arm_or_puts_the_role_in_a_mode_it_was_not_given(role):
    for task in _pool(role):
        prompt = tasks.main_prompt(task)
        assert not ARM_WORDS.search(prompt), task.task_id
        assert not PARALLEL_MODE.pattern.search(prompt), task.task_id
        assert not ACCEPTANCE_DESIGN_MODE.pattern.search(prompt), task.task_id


@pytest.mark.parametrize("role", MODE_OF)
def test_a_role_that_reads_its_mode_from_the_spawn_prompt_is_given_it(role):
    task = tasks.generate(role, SEED, 1)[0]

    assert MODE_OF[role].pattern.search(tasks.main_prompt(task))


@pytest.mark.parametrize("role", ["promethean", "roadmap-cartographer"])
def test_an_interactive_role_is_told_it_runs_without_a_user(role):
    task = tasks.generate(role, SEED, 1)[0]

    assert NON_INTERACTIVE.search(task.main_prompt)


def test_the_consultant_is_given_a_registered_discipline_and_none_that_cannot_resolve():
    prompt = tasks.generate("discipline-consultant", SEED, 1)[0].main_prompt

    assert prompt.startswith("Discipline: data-structure-specialist\n")
    assert "unresolvable" not in prompt.lower()


@pytest.mark.parametrize("role", ROLES)
def test_every_template_builds_a_repository_with_its_inputs_and_overlays(role, tmp_path):
    kit = tasks.kit_for(role)
    by_template = {task.template_id: task for task in _pool(role) if task.variant != EarlyStop(6)}

    assert set(by_template) == {template.template_id for template in kit.templates}
    for template_id, task in by_template.items():
        dest = tmp_path / template_id
        commit = tasks.build_scratch_repo(task, dest)

        held = set(_git(dest, "ls-tree", "-r", "--name-only", commit).splitlines())
        inputs = f".ai-work/{task.slug}"
        assert f"{inputs}/{kit.spec.brief}" in held
        assert {f"{inputs}/{name}" for name in kit.spec.fixture_inputs} <= held
        for overlay in kit.spec.overlays:
            relative = {
                path.relative_to(tasks.OVERLAYS_DIR / overlay).as_posix().removesuffix(".tmpl")
                for path in (tasks.OVERLAYS_DIR / overlay).rglob("*")
                if path.is_file()
            }
            assert relative <= held, (role, overlay)
        assert not [path for path in held if path.endswith(tasks.TEMPLATE_SUFFIX)]
        assert not any(UNFILLED_TOKEN.search(p.read_text()) for p in (dest / inputs).iterdir())


@pytest.mark.parametrize("role", ROLES)
def test_the_planted_text_is_in_the_brief_of_the_task_that_carries_it(role, tmp_path):
    kit = tasks.kit_for(role)
    for label in ("ambiguity", "conflict"):
        task = _find(role, label=label)
        tasks.build_scratch_repo(task, tmp_path / label)
        template = kit.template(task.template_id)
        plant = task.variant.c3_plant.text  # type: ignore[union-attr]
        held = "".join(p.read_text() for p in (tmp_path / label / ".ai-work" / task.slug).iterdir())
        assert plant in held
        assert plant == (template.ambiguity if label == "ambiguity" else template.conflict).text


@pytest.mark.parametrize("role", ROLES)
def test_the_allowed_tools_come_from_every_roles_definition(role, tmp_path):
    full, _ = _arm_pair(role, tmp_path)

    granted = tasks.allowed_tools(full)

    assert granted[0] == "Agent"
    assert len(granted) > 2


@pytest.mark.parametrize("fixture", ["ledger-cli", "notes-service"])
def test_the_implementer_is_given_a_step_acceptance_tests_to_leave_alone_and_a_sibling(
    fixture, tmp_path
):
    task = next(t for t in _pool("implementer") if t.fixture_id == fixture)
    dest = tmp_path / "scratch"

    tasks.build_scratch_repo(task, dest)

    wip = (dest / ".ai-work" / task.slug / "WIP.md").read_text()
    assert "## Current Step" in wip
    assert "[IN-PROGRESS]" not in wip  # the role must be the one to write the marker
    assert list((dest / "tests" / "acceptance").glob("test_*.py"))
    assert list((dest / "tests").glob("test_*.py"))
    assert (dest / "README.md").is_file()
