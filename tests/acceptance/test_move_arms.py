"""A move's arms are declared changes to the runner's copy, and a move relocates, never cuts.

Building the full, lean and floor arms of a move changes exactly each arm's declared files in
the runner's copy, each proven by its content digest, and never the checkout. Before any
session the runner refuses: an arm copy with an undeclared change or missing a declared one
(naming the file); a lean declaration leaving a line of the moved rule neither resident nor
delivered (naming the line); a move with no governed check or more than two; arms that would
differ in the commit-attribution setting, the model, the effort or the user instruction file
(naming it); and a lean arm that would leave a host without hooks (Cursor, Codex) reaching
less of the rule than it reaches today (naming the section and the host). Reach is measured
line by line by running both exports over each tree: a section is reached when every non-blank
line it holds in the checkout's rule file appears unchanged in a file the export carries (for
Codex, a file its manifest lists with a load other than excluded), and a section Codex reaches
through an always-on listing today must still be reached through one. The second ranked move,
adr-conventions, builds its arms from its own kit's declaration and passes the same checks.

The kit's own arms are built once per move and shared; each known-bad variant builds its own.
"""

from __future__ import annotations

import hashlib
import shutil
from dataclasses import dataclass
from pathlib import Path

import pytest

from tests.acceptance.drivers.move_eval import (
    FIRST_MOVE,
    HOSTS,
    MOVE_ARMS,
    MOVED_RULES,
    SECOND_MOVE,
    ArmBuild,
    Variant,
    build_arms,
    check_arm_copy,
    declare,
    move_checkout,
    reach,
    rule_sections,
    tracked_snapshot,
    working_state,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class Built:
    move: str
    checkout: Path
    build: ArmBuild
    before: tuple[dict[str, str], tuple[str, str]]
    after: tuple[dict[str, str], tuple[str, str]]


def _build(workspace: Path, move: str, variant: Variant) -> Built:
    checkout = move_checkout(workspace)
    before = (tracked_snapshot(checkout), working_state(checkout))
    build = build_arms(declare(move, variant, workspace), checkout, workspace / "arms")
    return Built(
        move, checkout, build, before, (tracked_snapshot(checkout), working_state(checkout))
    )


@pytest.fixture(scope="module")
def first_move(tmp_path_factory: pytest.TempPathFactory) -> Built:
    return _build(tmp_path_factory.mktemp("first-move-arms"), FIRST_MOVE, "as declared")


@pytest.fixture(scope="module")
def second_move(tmp_path_factory: pytest.TempPathFactory) -> Built:
    return _build(tmp_path_factory.mktemp("second-move-arms"), SECOND_MOVE, "as declared")


@pytest.fixture(params=("first", "second"))
def built(request, first_move, second_move) -> Built:
    return {"first": first_move, "second": second_move}[request.param]


def _file_digests(root: Path) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in root.rglob("*")
        if path.is_file() and ".git" not in path.relative_to(root).parts
    }


def _differing(copy: Path, checkout: Path) -> set[str]:
    ours, theirs = _file_digests(copy), _file_digests(checkout)
    return {path for path in ours.keys() | theirs.keys() if ours.get(path) != theirs.get(path)}


# -- Each arm is exactly its declaration ------------------------------------------------------


def test_a_moves_declared_arms_build_with_no_refusal(built):
    assert built.build.refusal is None, f"{built.move}: {built.build.refusal}"
    assert set(built.build.arms) == set(MOVE_ARMS)


@pytest.mark.parametrize("arm", MOVE_ARMS)
def test_each_arm_copy_differs_from_the_checkout_in_exactly_its_declared_files(built, arm):
    built_arm = built.build.arms[arm]

    differing = _differing(built_arm.copy, built.checkout)

    assert differing == {change.path for change in built_arm.declared}, (
        f"{built.move} {arm}: changed but undeclared "
        f"{sorted(differing - {c.path for c in built_arm.declared})}"
    )


@pytest.mark.parametrize("arm", MOVE_ARMS)
def test_each_declared_change_is_recorded_with_the_digest_of_its_content(built, arm):
    built_arm = built.build.arms[arm]
    present = _file_digests(built_arm.copy)

    mismatched = [
        c.path for c in built_arm.declared if c.path in present and c.sha256 != present[c.path]
    ]

    assert mismatched == [], f"{built.move} {arm}: digests not of the content: {mismatched}"


def test_the_full_arm_declares_no_change_to_the_moved_rule(built):
    full = built.build.arms["full"]

    assert MOVED_RULES[built.move] not in {change.path for change in full.declared}


def test_building_the_arms_leaves_the_checkout_byte_identical(built):
    assert built.after == built.before, f"{built.move}: building the arms changed the checkout"


# -- A copy that is not its declaration is refused --------------------------------------------


def _altered_lean_copy(first_move: Built, workspace: Path) -> Path:
    copy = workspace / "altered-lean"
    shutil.copytree(first_move.build.arms["lean"].copy, copy, symlinks=True)
    return copy


def _revert(copy: Path, checkout: Path, relpath: str) -> None:
    """Undo one change in an arm copy: the checkout's file back, or the added file gone."""
    original = checkout / relpath
    if original.is_file():
        shutil.copy2(original, copy / relpath)
    else:
        (copy / relpath).unlink()


def test_an_arm_copy_with_one_undeclared_changed_file_is_refused_naming_the_file(
    first_move, tmp_path
):
    copy = _altered_lean_copy(first_move, tmp_path)
    (copy / "README.md").write_text("an undeclared change\n", encoding="utf-8")

    refusal = check_arm_copy(
        declare(FIRST_MOVE, "as declared", tmp_path), "lean", copy, first_move.checkout
    )

    assert refusal is not None, "an arm copy with an undeclared change was accepted"
    assert "README.md" in refusal, refusal


def test_an_arm_copy_missing_one_declared_change_is_refused_naming_the_file(first_move, tmp_path):
    copy = _altered_lean_copy(first_move, tmp_path)
    reverted = first_move.build.arms["lean"].declared[0].path
    _revert(copy, first_move.checkout, reverted)

    refusal = check_arm_copy(
        declare(FIRST_MOVE, "as declared", tmp_path), "lean", copy, first_move.checkout
    )

    assert refusal is not None, "an arm copy missing a declared change was accepted"
    assert reverted in refusal, refusal


def test_the_runner_accepts_its_own_lean_copy_as_declared(first_move, tmp_path):
    copy = _altered_lean_copy(first_move, tmp_path)

    refusal = check_arm_copy(
        declare(FIRST_MOVE, "as declared", tmp_path), "lean", copy, first_move.checkout
    )

    assert refusal is None


# -- A move relocates text, it never cuts it --------------------------------------------------


def test_a_lean_declaration_leaving_a_rule_line_neither_resident_nor_delivered_is_refused_naming_it(
    tmp_path,
):
    rule_lines = [
        line.strip()
        for line in (REPO_ROOT / MOVED_RULES[FIRST_MOVE]).read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    ]

    refusal = _build(
        tmp_path, FIRST_MOVE, "a lean line neither resident nor delivered"
    ).build.refusal

    assert refusal is not None, "a lean declaration that cuts a rule line was accepted"
    assert any(line in refusal for line in rule_lines), f"the refusal names no line: {refusal}"


@pytest.mark.parametrize("variant", ["no governed check", "three governed checks"])
def test_a_move_declaring_no_governed_check_or_more_than_two_is_refused(tmp_path, variant):
    refusal = _build(tmp_path, FIRST_MOVE, variant).build.refusal

    assert refusal is not None, f"a move with {variant} was accepted"
    assert "governed check" in refusal.lower(), refusal


@pytest.mark.parametrize(
    ("variant", "named"),
    [
        ("the arms differ in the commit-attribution setting", "attribution"),
        ("the arms differ in the model", "model"),
        ("the arms differ in the effort", "effort"),
        ("the arms differ in the user instruction file", "instruction"),
    ],
)
def test_arms_that_would_differ_in_a_pinned_setting_are_refused_naming_it(tmp_path, variant, named):
    refusal = _build(tmp_path, FIRST_MOVE, variant).build.refusal

    assert refusal is not None, f"arms that differ ({variant}) were accepted"
    assert named in refusal.lower(), refusal


# -- Hosts without hooks keep at least today's reach ------------------------------------------


@pytest.mark.parametrize("host", HOSTS)
def test_the_lean_arm_reaches_on_a_host_without_hooks_every_section_reached_today(
    built, host, tmp_path
):
    today = reach(built.checkout, built.checkout, built.move, host, tmp_path / "today")
    lean_copy = built.build.arms["lean"].copy
    lean = reach(lean_copy, built.checkout, built.move, host, tmp_path / "lean")

    assert today.sections, f"{host} reaches no section of {MOVED_RULES[built.move]} today"
    assert today.sections <= lean.sections, (
        f"{host} loses {sorted(today.sections - lean.sections)} under the lean arm of {built.move}"
    )


def test_on_codex_every_section_reached_always_on_today_stays_always_on_under_the_lean_arm(
    built, tmp_path
):
    today = reach(built.checkout, built.checkout, built.move, "codex", tmp_path / "today")
    lean_copy = built.build.arms["lean"].copy
    lean = reach(lean_copy, built.checkout, built.move, "codex", tmp_path / "lean")

    assert today.always_on, f"Codex reaches no section of {built.move} always-on today"
    assert today.always_on <= lean.always_on, (
        f"no longer always-on on Codex: {sorted(today.always_on - lean.always_on)}"
    )


def test_a_section_delivered_only_by_hook_text_read_from_no_exported_rule_file_is_refused(tmp_path):
    sections = rule_sections((REPO_ROOT / MOVED_RULES[FIRST_MOVE]).read_text(encoding="utf-8"))
    variant: Variant = "a section delivered only by hook text read from no exported rule file"

    refusal = _build(tmp_path, FIRST_MOVE, variant).build.refusal

    assert refusal is not None, "a lean arm leaving a host without hooks with less was accepted"
    assert any(section in refusal for section in sections), f"no section named: {refusal}"
    assert any(host in refusal.lower() for host in HOSTS), f"no host named: {refusal}"


def test_a_section_turned_from_always_on_to_path_scoped_on_codex_is_refused_naming_it(tmp_path):
    sections = rule_sections((REPO_ROOT / MOVED_RULES[FIRST_MOVE]).read_text(encoding="utf-8"))
    variant: Variant = "a file holding a section turned from always-on to path-scoped on Codex"

    refusal = _build(tmp_path, FIRST_MOVE, variant).build.refusal

    assert refusal is not None, "a lean arm narrowing Codex's always-on listing was accepted"
    assert any(section in refusal for section in sections), f"no section named: {refusal}"
    assert "codex" in refusal.lower(), f"the host is not named: {refusal}"
