"""The ADR rule ships as measured: one resident line at session start, the full rule on a touch.

A session that starts with the plugin's rules installed holds the resident text (the rule's
title and its one sentence) and no other line of the rule; touching any file under the decision
directory delivers the whole rule by its path scope. The shipped rule, the resident file and
their manifest rows are the measured lean arm's, every line of the rule is still delivered, both
files install and neither can be disabled. The move instrument refuses to measure the landed
move again, and the always-loaded reading counts the resident file where it counted the rule.

The measured arm and the base were frozen before the change (`adr_rule_move`).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.acceptance.drivers import adr_rule_move as move
from tests.acceptance.drivers.adherence_eval import install_fake_claude
from tests.acceptance.drivers.decision_kit import DECISION_MOVE
from tests.acceptance.drivers.move_eval import MoveRun, build_arms, declare, move_checkout, run_move

REPO = move.REPO_ROOT
TOUCHED = (
    ".ai-state/decisions/drafts/20261029-1430-fixture-person-main-a-slug.md",
    ".ai-state/decisions/041-keep-orders-in-postgres.md",
    ".ai-state/decisions/DECISIONS_INDEX.md",
)


@pytest.fixture(scope="module")
def installed(tmp_path_factory) -> Path:
    """The scratch HOME's rules directory after `bash install.sh` linked the shipped rules."""
    scratch = tmp_path_factory.mktemp("install")
    result = move.install(scratch)
    assert result.returncode == 0, result.stdout[-2000:] + result.stderr[-2000:]
    return scratch / "home" / ".claude" / "rules"


@pytest.fixture(scope="module")
def session_start_text(installed, tmp_path_factory) -> str:
    """Every rule text resident when a session opens: linked rules with no path scope, plus
    what the registered session-start rule injection adds."""
    resident = [
        path.read_text(encoding="utf-8")
        for path in sorted(installed.rglob("*.md"))
        if "paths" not in move.frontmatter(path.read_text(encoding="utf-8"))
    ]
    project = tmp_path_factory.mktemp("project")
    injected = move.session_start_rules(project, project.parent / f".{project.name}-scratch")
    context = json.loads(injected.stdout or "{}").get("hookSpecificOutput", {})
    return "\n".join([*resident, str(context.get("additionalContext", ""))])


def _resident_lines() -> list[str]:
    _, body = move.split_frontmatter(move.fixture_text("measured_resident.md"))
    return [line for line in body.splitlines() if line.strip()]


# -- At session start -----------------------------------------------------------------------------


def test_a_session_starts_holding_the_resident_title_and_sentence_verbatim(session_start_text):
    lines = set(session_start_text.splitlines())

    assert _resident_lines()[0] == move.RESIDENT_TITLE
    assert [line for line in _resident_lines() if line not in lines] == []


def test_a_session_starts_with_no_other_line_of_the_rule(session_start_text):
    others = move.rule_body_lines(move.fixture_text("base_rule.md")) - set(_resident_lines())

    held = others & {line.strip() for line in session_start_text.splitlines()}

    assert sorted(held) == [], f"{len(held)} lines of the rule are resident at session start"


@pytest.mark.parametrize(
    "instructions", ["CLAUDE.md", "claude/config/CLAUDE.md.tmpl", "claude/canonical-blocks"]
)
def test_no_instruction_file_a_praxion_or_managed_session_loads_carries_the_rule_body(
    instructions,
):
    texts = move.instruction_texts(REPO / instructions)
    others = move.rule_body_lines(move.fixture_text("base_rule.md")) - set(_resident_lines())

    held = others & {line.strip() for text in texts for line in text.splitlines()}

    assert sorted(held) == []


# -- On the first touch of a decision record ------------------------------------------------------


@pytest.mark.parametrize("touched", TOUCHED)
def test_touching_a_decision_file_delivers_the_installed_rule_by_its_path_scope(installed, touched):
    text = (installed / "swe" / "adr-conventions.md").read_text(encoding="utf-8")

    assert move.scope_takes(move.frontmatter(text).get("paths") or [], touched), touched


def test_the_rule_a_touch_delivers_is_the_whole_rule(installed):
    _, delivered = move.split_frontmatter(
        (installed / "swe" / "adr-conventions.md").read_text(encoding="utf-8")
    )

    assert delivered == move.split_frontmatter(move.fixture_text("base_rule.md"))[1]


# -- What ships is what was measured --------------------------------------------------------------


def test_the_shipped_rule_is_the_measured_arms_rule_byte_for_byte():
    assert (REPO / move.MOVED_RULE).read_bytes() == (
        move.FIXTURES / "measured_rule.md"
    ).read_bytes()


def test_the_shipped_rules_body_is_the_bases_body_byte_for_byte():
    _, shipped = move.split_frontmatter((REPO / move.MOVED_RULE).read_text(encoding="utf-8"))

    assert shipped == move.split_frontmatter(move.fixture_text("base_rule.md"))[1]


def test_the_shipped_resident_differs_from_the_measured_one_only_by_a_frontmatter_block():
    resident = REPO / move.RESIDENT
    assert resident.is_file(), f"{move.RESIDENT} does not ship"

    block, body = move.split_frontmatter(resident.read_text(encoding="utf-8"))
    measured_block, measured_body = move.split_frontmatter(
        move.fixture_text("measured_resident.md")
    )

    assert measured_block == ""
    assert body == measured_body


@pytest.mark.parametrize("rule_id", move.RULE_IDS)
def test_the_manifest_row_carries_the_measured_arms_values(rule_id):
    row = move.manifest_rows(REPO).get(rule_id, {})

    shipped = {key: row.get(key) for key in move.MEASURED_KEYS}

    assert shipped == move.fixture_json("measured_rows.json")[rule_id]


# -- Installed, and never disabled ----------------------------------------------------------------


@pytest.mark.parametrize("rule_file", [move.MOVED_RULE, move.RESIDENT])
def test_the_installer_links_the_file_into_the_rules_directory(installed, rule_file):
    linked = installed / Path(rule_file).relative_to("rules")

    assert linked.is_symlink(), linked
    assert linked.resolve() == (REPO / rule_file).resolve(), linked


@pytest.mark.parametrize(
    ("pattern", "named"),
    [
        ("swe/adr-conventions", "swe/adr-conventions"),
        ("swe/adr-conventions-resident", "swe/adr-conventions-resident"),
        ("swe/adr-*", "swe/adr-conventions"),
        ("swe/adr-*", "swe/adr-conventions-resident"),
    ],
)
def test_a_disable_list_naming_either_file_warns_it_is_core_and_keeps_both_loaded(
    tmp_path, pattern, named
):
    project = tmp_path / "project"
    (project / ".claude").mkdir(parents=True)
    (project / ".claude" / "praxion-rules.yaml").write_text(
        f"version: 1\ndisable:\n  - {pattern}\n", encoding="utf-8"
    )

    result = move.session_start_rules(project, tmp_path / "scratch")
    settings = project / ".claude" / "settings.json"
    excluded = (
        json.loads(settings.read_text()).get("claudeMdExcludes", []) if settings.exists() else []
    )

    assert f"cannot disable core rule '{named}'" in result.stderr, result.stderr
    assert [e for e in excluded if "adr-conventions" in e] == []


# -- The always-loaded reading --------------------------------------------------------------------


def test_the_always_loaded_reading_counts_the_resident_where_it_counted_the_rule(tmp_path):
    base = move.fixture_json("base_budget_files.json")
    expected = sorted(
        f"<repo>/{move.RESIDENT}" if f == f"<repo>/{move.MOVED_RULE}" else f for f in base
    )

    assert move.budget_files(tmp_path) == expected


# -- The move instrument and a landed move --------------------------------------------------------


def test_building_the_moves_lean_arm_over_the_shipped_tree_is_refused_naming_why(tmp_path):
    checkout = move_checkout(tmp_path, shipped=True)

    refusal = build_arms(
        declare(DECISION_MOVE, "as declared", tmp_path), checkout, tmp_path / "a"
    ).refusal

    assert refusal is not None, "the landed move's lean arm was built again"
    assert move.RESIDENT in refusal or move.PATH_SCOPE in refusal, refusal


def test_a_run_of_the_landed_move_is_refused_before_any_session_starts(tmp_path):
    checkout = move_checkout(tmp_path, shipped=True)
    stand_in = install_fake_claude(tmp_path)

    result = run_move(MoveRun(DECISION_MOVE, checkout, "floor"), stand_in.bin_dir)

    assert (result.exit_code != 0, len(stand_in.launches())) == (True, 0), result.stdout[-1500:]
