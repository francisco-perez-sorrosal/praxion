"""A move's arms are its declared changes to a copy and nothing else: each channel the lean arm
relies on is observed by running the copy, a copy that is not its declaration is refused naming
the file, and a lean arm that cuts a line of the moved rule is refused naming the line."""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from dataclasses import replace
from pathlib import Path

import pytest
import yaml

from praxion_evals.adherence.moves import arms, declaration, observe
from praxion_evals.adherence.moves.arms import ArmRefusal, ArmSet
from praxion_evals.adherence.moves.model import (
    MOVE_ARMS,
    ArmChange,
    ArmChanges,
    KernelDerive,
    ManifestRowRemoved,
    ManifestRowScoped,
    MoveDeclaration,
    PathMatched,
    RelPath,
    Remove,
    SessionStart,
    Write,
)
from praxion_evals.live.materialize import tree_digest
from tests.landed_move_support import ADR_KERNEL, ADR_KERNEL_ID, MANIFEST, before_the_adr_move

REPO_ROOT = Path(__file__).resolve().parents[2]
GIT_MOVE = "git-conventions"
ADR_MOVE = "adr-conventions"
GIT_RULE = "rules/swe/vcs/git-conventions.md"
GIT_RULE_ID = "swe/vcs/git-conventions"
GIT_KERNEL = "rules/swe/vcs/git-conventions-resident.md"
GIT_HOOK = "inject_git_conventions_at_use.py"
ADR_RULE = "rules/swe/adr-conventions.md"
ADR_RULE_ID = "swe/adr-conventions"
STAGE_LINE = "- Stage specific files by name — avoid `git add -A` or `git add .`"
NOT_IN_THE_KERNEL = "- Prefer small, focused commits over large sweeping ones"
READ_TREES = ("rules", "lib", "hooks")
# Read by the build: both rules exports (reach) and the user-instruction renderer (pinning).
READ_FILES = (
    "cursor/config/export-cursor-rules.py",
    "codex/config/export-codex-rules-bridge.py",
    *(
        f"codex/config/{path.name}"
        for path in (REPO_ROOT / "codex/config").glob("rules_bridge_*.py")
    ),
    "claude/config/CLAUDE.md.tmpl",
    "scripts/render_claude_md.py",
)
COMMIT = {"tool_name": "Bash", "tool_input": {"command": "git commit -m x"}}
SESSION_START = {"source": "startup"}


@pytest.fixture(scope="module")
def checkout(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """The files an arm build reads, as the repository has them; no test writes here."""
    root = tmp_path_factory.mktemp("arms") / "checkout"
    for tree in READ_TREES:
        shutil.copytree(REPO_ROOT / tree, root / tree, ignore=shutil.ignore_patterns("__pycache__"))
    for relpath in READ_FILES:
        (root / relpath).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(REPO_ROOT / relpath, root / relpath)
    before_the_adr_move(root)
    subprocess.run(["git", "init", "-q", str(root)], check=True)  # arms copy what git lists
    return root


@pytest.fixture(scope="module")
def first_move(checkout: Path, tmp_path_factory: pytest.TempPathFactory) -> ArmSet:
    return _built(declaration.kit(GIT_MOVE), checkout, tmp_path_factory.mktemp("first"))


@pytest.fixture(scope="module")
def second_move(checkout: Path, tmp_path_factory: pytest.TempPathFactory) -> ArmSet:
    return _built(declaration.kit(ADR_MOVE), checkout, tmp_path_factory.mktemp("second"))


def _built(declared: MoveDeclaration, checkout: Path, workspace: Path) -> ArmSet:
    built = arms.build(declared, checkout, workspace)
    assert isinstance(built, ArmSet), built
    return built


def _refusal(declared: MoveDeclaration, checkout: Path, workspace: Path) -> str:
    built = arms.build(declared, checkout, workspace)
    assert isinstance(built, ArmRefusal), "the arms were built"
    return built.reason


def _lean_with(declared: MoveDeclaration, *changes: ArmChange) -> MoveDeclaration:
    """The declaration with its lean changes replaced by ``changes``."""
    return replace(declared, arms=ArmChanges.of({"lean": changes, "floor": declared.arms.floor}))


def _kernel(*prefixes: str) -> KernelDerive:
    return KernelDerive(RelPath.parse(GIT_KERNEL), prefixes)


def _lean_without(declared: MoveDeclaration, kind: type) -> MoveDeclaration:
    return _lean_with(declared, *(c for c in declared.arms.lean if not isinstance(c, kind)))


# -- Building ---------------------------------------------------------------------------------


@pytest.mark.parametrize("built", ["first_move", "second_move"])
def test_a_moves_three_arms_build_over_the_copy(built, request):
    assert set(request.getfixturevalue(built).arms) == {"full", "lean", "floor"}


@pytest.mark.parametrize("arm", ["full", "lean", "floor"])
def test_the_runner_accepts_each_arm_copy_it_built(first_move, checkout, arm):
    refusal = arms.check_copy(declaration.kit(GIT_MOVE), arm, first_move.arms[arm].copy, checkout)

    assert refusal is None


def test_building_the_arms_leaves_the_checkout_byte_identical(checkout, tmp_path):
    before = tree_digest(checkout)

    _built(declaration.kit(GIT_MOVE), checkout, tmp_path)

    assert tree_digest(checkout) == before


def test_an_arm_copy_holds_what_git_lists_and_none_of_the_ignored_trees(checkout, tmp_path):
    working = tmp_path / "working"
    shutil.copytree(checkout, working, symlinks=True)
    (working / ".gitignore").write_text("linked-worktrees/\n", encoding="utf-8")
    ignored = working / "linked-worktrees" / "another-checkout" / "rules" / "big.md"
    ignored.parent.mkdir(parents=True)
    ignored.write_text("a linked worktree's copy of the rules\n", encoding="utf-8")
    (working / "notes.md").write_text("untracked and not ignored\n", encoding="utf-8")

    built = _built(declaration.kit(GIT_MOVE), working, tmp_path / "arms")

    copies = {arm: built.arms[arm].copy for arm in MOVE_ARMS}
    assert {arm for arm, copy in copies.items() if (copy / "linked-worktrees").exists()} == set()
    assert {arm for arm, copy in copies.items() if (copy / "notes.md").is_file()} == set(MOVE_ARMS)


def test_each_change_is_recorded_with_the_digest_of_the_content_it_wrote(first_move):
    lean = first_move.arms["lean"]
    recorded = {change.path: change.sha256 for change in lean.changes}

    kernel = (lean.copy / GIT_KERNEL).read_bytes()

    assert recorded[GIT_KERNEL] == hashlib.sha256(kernel).hexdigest()
    assert recorded[f"hooks/{GIT_HOOK}"] is not None


def test_a_removal_is_recorded_without_a_digest(first_move):
    floor = {change.path: change.sha256 for change in first_move.arms["floor"].changes}

    assert floor[GIT_RULE] is None


def test_a_building_arm_leaves_no_bytecode_cache_in_its_copy(first_move):
    assert list(first_move.arms["lean"].copy.rglob("__pycache__")) == []


# -- The derived changes ----------------------------------------------------------------------


def test_the_kernel_is_the_moved_rules_lines_in_the_rules_order(first_move):
    kernel = (first_move.arms["lean"].copy / GIT_KERNEL).read_text(encoding="utf-8").splitlines()

    assert kernel[0] == "## Git Conventions"  # the title keeps the file a rule both exporters read
    assert kernel[1] == STAGE_LINE
    assert len(kernel) == 7
    assert NOT_IN_THE_KERNEL not in kernel


def test_the_manifest_row_of_the_moved_rule_is_pointed_at_the_kernel_in_the_lean_arm(first_move):
    manifest = (first_move.arms["lean"].copy / "rules/_manifest.yaml").read_text(encoding="utf-8")

    assert f"- id: {GIT_RULE_ID}\n  path: {GIT_KERNEL}\n" in manifest
    assert GIT_RULE not in manifest.replace("  - " + GIT_RULE, "")


def test_the_manifest_row_of_the_moved_rule_is_removed_in_the_floor_arm(first_move):
    manifest = (first_move.arms["floor"].copy / "rules/_manifest.yaml").read_text(encoding="utf-8")

    assert f"- id: {GIT_RULE_ID}\n" not in manifest


def test_the_lean_hook_is_registered_under_the_declared_event_and_matcher(first_move):
    path = first_move.arms["lean"].copy / "hooks/hooks.json"
    groups = json.loads(path.read_text(encoding="utf-8"))["hooks"]["PreToolUse"]

    commands = [h["command"] for g in groups if g["matcher"] == "Bash" for h in g["hooks"]]

    assert f"python3 ${{CLAUDE_PLUGIN_ROOT}}/hooks/{GIT_HOOK}" in commands


def test_a_kernel_prefix_matching_no_line_is_refused_naming_it(checkout, tmp_path):
    declared = declaration.kit(GIT_MOVE)
    bent = replace(declared, arms=_swapped_kernel(declared, "- No such line"))

    assert "- No such line" in _refusal(bent, checkout, tmp_path)


def test_a_kernel_prefix_matching_two_lines_is_refused_naming_it(checkout, tmp_path):
    declared = declaration.kit(GIT_MOVE)
    bent = replace(declared, arms=_swapped_kernel(declared, "- Never commit"))

    reason = _refusal(bent, checkout, tmp_path)

    assert "- Never commit" in reason
    assert "matches 2" in reason


def _swapped_kernel(declared: MoveDeclaration, prefix: str) -> ArmChanges:
    lean = [_kernel(prefix) if isinstance(c, KernelDerive) else c for c in declared.arms.lean]
    return ArmChanges.of({"lean": lean, "floor": declared.arms.floor})


def test_a_removal_of_a_file_the_checkout_lacks_is_refused_naming_it(checkout, tmp_path):
    declared = declaration.kit(GIT_MOVE)
    gone = Remove(RelPath.parse("docs/not-there.md"))
    bent = replace(declared, arms=ArmChanges.of({"floor": [*declared.arms.floor, gone]}))

    assert "docs/not-there.md" in _refusal(bent, checkout, tmp_path)


def test_a_write_whose_source_changed_since_it_was_declared_is_refused(checkout, tmp_path):
    declared = declaration.kit(GIT_MOVE)
    source = tmp_path / "note.md"
    source.write_text("a note\n", encoding="utf-8")
    stale = Write(RelPath.parse("docs/note.md"), source, "0" * 64)

    reason = _refusal(_lean_with(declared, stale), checkout, tmp_path / "ws")

    assert "docs/note.md" in reason


# -- The scoped manifest row ------------------------------------------------------------------


def _scoped(declared: MoveDeclaration) -> MoveDeclaration:
    """The declaration with the moved rule's row kept path-scoped instead of removed."""
    scoped = ManifestRowScoped(RelPath.parse(MANIFEST))
    return _lean_with(
        declared, *(scoped if isinstance(c, ManifestRowRemoved) else c for c in declared.arms.lean)
    )


def _rows(manifest: Path) -> list[dict]:
    return yaml.safe_load(manifest.read_text(encoding="utf-8"))["rules"]


def _with_manifest(checkout: Path, where: Path, edit) -> Path:
    """A copy of the checkout whose manifest text has been through ``edit``."""
    changed = where / "checkout"
    shutil.copytree(checkout, changed, symlinks=True)
    manifest = changed / MANIFEST
    manifest.write_text(edit(manifest.read_text(encoding="utf-8")), encoding="utf-8")
    return changed


@pytest.fixture(scope="module")
def scoped_move(checkout: Path, tmp_path_factory: pytest.TempPathFactory) -> ArmSet:
    return _built(_scoped(declaration.kit(ADR_MOVE)), checkout, tmp_path_factory.mktemp("scoped"))


def test_the_kept_row_is_path_scoped_to_the_deliverys_globs_with_the_written_rules_chars(
    scoped_move,
):
    lean = scoped_move.arms["lean"].copy
    kept = next(row for row in _rows(lean / MANIFEST) if row["id"] == ADR_RULE_ID)

    assert kept == {
        "id": ADR_RULE_ID,
        "path": ADR_RULE,
        "load": "path_scoped",
        "core": True,
        "install": "symlink",
        "chars": len((lean / ADR_RULE).read_text(encoding="utf-8")),
        "paths": [".ai-state/decisions/**"],
    }


def test_the_kernel_row_follows_the_kept_row_and_is_always_on(scoped_move):
    lean = scoped_move.arms["lean"].copy
    rows = _rows(lean / MANIFEST)
    kept = next(i for i, row in enumerate(rows) if row["id"] == ADR_RULE_ID)

    assert rows[kept + 1] == {
        "id": ADR_KERNEL_ID,
        "path": ADR_KERNEL,
        "load": "always_on",
        "core": True,
        "install": "symlink",
        "chars": len((lean / ADR_KERNEL).read_text(encoding="utf-8")),
    }


def test_no_other_manifest_entry_changes(scoped_move, checkout):
    lean = _rows(scoped_move.arms["lean"].copy / MANIFEST)
    original = _rows(checkout / MANIFEST)

    others = [row for row in lean if row["id"] not in (ADR_RULE_ID, ADR_KERNEL_ID)]

    assert others == [row for row in original if row["id"] != ADR_RULE_ID]


def test_the_scoped_row_without_a_kernel_sibling_adds_no_kernel_row(checkout):
    declared = _scoped(declaration.kit(ADR_MOVE))
    no_kernel = _lean_without(declared, KernelDerive)

    planned = {p.path: p for p in arms.plan(no_kernel, "lean", checkout)}
    rows = yaml.safe_load(planned[MANIFEST].content)["rules"]

    assert [row["id"] for row in rows if row["id"].startswith(ADR_RULE_ID)] == [ADR_RULE_ID]


@pytest.mark.parametrize("copies", [0, 2], ids=["none", "two"])
def test_a_scoped_row_needs_exactly_one_path_matched_delivery_of_the_moved_rule(
    checkout, tmp_path, copies
):
    declared = _scoped(declaration.kit(ADR_MOVE))
    matched = [d for d in declared.deliveries if isinstance(d, PathMatched)]
    others = [d for d in declared.deliveries if not isinstance(d, PathMatched)]
    bent = replace(declared, deliveries=(*others, *matched * copies))

    reason = _refusal(bent, checkout, tmp_path)

    assert MANIFEST in reason
    assert "path-matched" in reason


def test_a_path_matched_delivery_of_another_file_does_not_count_for_the_scoped_row(
    checkout, tmp_path
):
    declared = _scoped(declaration.kit(ADR_MOVE))
    elsewhere = tuple(
        replace(d, file=RelPath.parse(GIT_RULE)) if isinstance(d, PathMatched) else d
        for d in declared.deliveries
    )

    reason = _refusal(replace(declared, deliveries=elsewhere), checkout, tmp_path)

    assert MANIFEST in reason
    assert ADR_RULE in reason


def test_a_scoped_row_whose_arm_does_not_write_the_moved_rule_is_refused_naming_the_manifest(
    checkout, tmp_path
):
    declared = _scoped(declaration.kit(ADR_MOVE))

    reason = _refusal(_lean_without(declared, Write), checkout, tmp_path)

    assert MANIFEST in reason
    assert "write" in reason
    assert ADR_RULE in reason


def test_a_scoped_row_for_a_rule_that_is_not_symlinked_is_refused_naming_the_manifest(
    checkout, tmp_path
):
    hook_delivered = _with_manifest(
        checkout,
        tmp_path / "edited",
        lambda text: text.replace(
            f"path: {ADR_RULE}\n  load: always_on\n  core: true\n  install: symlink",
            f"path: {ADR_RULE}\n  load: always_on\n  core: true\n  install: hook-deliver",
        ),
    )

    reason = _refusal(_scoped(declaration.kit(ADR_MOVE)), hook_delivered, tmp_path / "ws")

    assert MANIFEST in reason
    assert "hook-deliver" in reason


def test_a_scoped_row_whose_kernel_id_is_already_taken_is_refused_naming_the_manifest(
    checkout, tmp_path
):
    taken = _with_manifest(
        checkout,
        tmp_path / "edited",
        lambda text: text + f"- id: {ADR_KERNEL_ID}\n  path: rules/other.md\n  load: always_on\n",
    )

    reason = _refusal(_scoped(declaration.kit(ADR_MOVE)), taken, tmp_path / "ws")

    assert MANIFEST in reason
    assert ADR_KERNEL_ID in reason


def test_a_scoped_row_with_two_kernels_is_refused_as_a_removed_row_is(checkout, tmp_path):
    declared = _scoped(declaration.kit(ADR_MOVE))
    second = KernelDerive(RelPath.parse("rules/swe/second-resident.md"), ("Architecture",))

    reason = _refusal(_lean_with(declared, *declared.arms.lean, second), checkout, tmp_path)

    assert MANIFEST in reason
    assert "one kernel" in reason


# -- A copy that is not its declaration is refused --------------------------------------------


def test_a_copy_with_an_undeclared_changed_file_is_refused_naming_it(
    first_move, checkout, tmp_path
):
    copy = _copy_of(first_move, "lean", tmp_path)
    (copy / "rules/swe/agent-model-routing.md").write_text("changed\n", encoding="utf-8")

    refusal = arms.check_copy(declaration.kit(GIT_MOVE), "lean", copy, checkout)

    assert refusal is not None
    assert "rules/swe/agent-model-routing.md" in refusal


def test_a_copy_missing_a_declared_change_is_refused_naming_it(first_move, checkout, tmp_path):
    copy = _copy_of(first_move, "lean", tmp_path)
    shutil.copy2(checkout / "hooks/hooks.json", copy / "hooks/hooks.json")

    refusal = arms.check_copy(declaration.kit(GIT_MOVE), "lean", copy, checkout)

    assert refusal is not None
    assert "hooks/hooks.json" in refusal


def test_a_copy_holding_other_content_than_a_declared_change_is_refused_naming_it(
    first_move, checkout, tmp_path
):
    copy = _copy_of(first_move, "lean", tmp_path)
    (copy / GIT_KERNEL).write_text("- another line\n", encoding="utf-8")

    refusal = arms.check_copy(declaration.kit(GIT_MOVE), "lean", copy, checkout)

    assert refusal is not None
    assert GIT_KERNEL in refusal


def test_the_full_arm_is_the_checkout_and_a_changed_file_is_refused(checkout, tmp_path):
    copy = tmp_path / "full"
    shutil.copytree(checkout, copy, symlinks=True)
    (copy / "rules/_manifest.yaml").write_text("changed\n", encoding="utf-8")

    refusal = arms.check_copy(declaration.kit(GIT_MOVE), "full", copy, checkout)

    assert refusal is not None
    assert "rules/_manifest.yaml" in refusal


def _copy_of(built: ArmSet, arm: str, where: Path) -> Path:
    copy = where / f"altered-{arm}"
    shutil.copytree(built.arms[arm].copy, copy, symlinks=True)
    return copy


# -- What each arm has resident, observed -----------------------------------------------------


def test_the_full_arm_has_the_whole_rule_resident_at_session_start(first_move):
    assert NOT_IN_THE_KERNEL in first_move.arms["full"].session_start


def test_the_lean_arm_has_the_kernel_resident_and_the_rest_of_the_rule_not(first_move):
    resident = first_move.arms["lean"].session_start

    assert STAGE_LINE in resident
    assert NOT_IN_THE_KERNEL not in resident


def test_the_floor_arm_has_no_line_of_the_rule_resident(first_move):
    resident = first_move.arms["floor"].session_start

    assert STAGE_LINE not in resident
    assert NOT_IN_THE_KERNEL not in resident


# -- A move relocates text, it never cuts it --------------------------------------------------


def test_a_lean_arm_delivering_only_the_kernel_is_refused_naming_a_line_it_cuts(checkout, tmp_path):
    declared = declaration.kit(ADR_MOVE)
    removed_row = _lean_with(
        declared,
        *(
            ManifestRowRemoved(c.path) if isinstance(c, ManifestRowScoped) else c
            for c in declared.arms.lean
        ),
    )
    kernel_only = tuple(d for d in removed_row.deliveries if isinstance(d, SessionStart))

    reason = _refusal(replace(removed_row, deliveries=kernel_only), checkout, tmp_path)

    assert "neither resident nor delivered" in reason
    assert ADR_RULE in reason


def test_a_declared_resident_kernel_that_is_not_resident_is_refused_naming_its_line(
    checkout, tmp_path
):
    declared = declaration.kit(ADR_MOVE)

    reason = _refusal(_lean_without(declared, ManifestRowScoped), checkout, tmp_path)

    assert "declared resident" in reason
    assert "Architecture Decision Records live in" in reason


def test_a_path_matched_file_without_the_declared_globs_is_refused_naming_the_file(
    checkout, tmp_path
):
    declared = declaration.kit(ADR_MOVE)
    unscoped = tuple(
        replace(d, globs=("elsewhere/**",)) if isinstance(d, PathMatched) else d
        for d in declared.deliveries
    )

    reason = _refusal(replace(declared, deliveries=unscoped), checkout, tmp_path)

    assert ADR_RULE in reason
    assert "elsewhere/**" in reason


# -- A path-matched rule the lean installer does not link is refused ---------------------------


def test_a_lean_manifest_without_the_path_matched_rules_row_is_refused_naming_the_rule(
    checkout, tmp_path
):
    declared = declaration.kit(ADR_MOVE)
    row_removed = _lean_with(
        declared,
        *(
            ManifestRowRemoved(c.path) if isinstance(c, ManifestRowScoped) else c
            for c in declared.arms.lean
        ),
    )

    reason = _refusal(row_removed, checkout, tmp_path)

    assert (
        f"{ADR_RULE} is declared path-matched but the lean copy's installer does not link it"
        in (reason)
    )


def test_a_build_declaring_no_path_matched_delivery_is_not_refused_for_linking(first_move):
    declared = declaration.kit(GIT_MOVE)

    assert not any(isinstance(d, PathMatched) for d in declared.deliveries)
    assert "lean" in first_move.arms


# -- The channels honour the project's rule disable list --------------------------------------


@pytest.fixture
def disabling_project(tmp_path: Path) -> Path:
    project = tmp_path / "project"
    (project / ".claude").mkdir(parents=True)
    (project / ".claude/praxion-rules.yaml").write_text(
        f"version: 1\ndisable:\n  - '{GIT_RULE_ID}'\n", encoding="utf-8"
    )
    return project


def test_the_lean_hook_emits_nothing_for_a_project_that_disables_the_rule(
    first_move, disabling_project
):
    copy = first_move.arms["lean"].copy
    payload = {**COMMIT, "cwd": str(disabling_project)}

    observed = observe.hook_output(copy, "PreToolUse", payload, script=GIT_HOOK)

    assert observed == observe.Observed(())


def test_the_lean_hook_emits_the_rule_for_a_project_that_does_not_disable_it(first_move, tmp_path):
    copy = first_move.arms["lean"].copy
    payload = {**COMMIT, "cwd": str(tmp_path)}

    observed = observe.hook_output(copy, "PreToolUse", payload, script=GIT_HOOK)

    assert isinstance(observed, observe.Observed)
    assert NOT_IN_THE_KERNEL in observed.lines


def test_the_resident_kernel_is_not_injected_for_a_project_that_disables_the_rule(
    first_move, disabling_project
):
    copy = first_move.arms["lean"].copy
    payload = {**SESSION_START, "cwd": str(disabling_project)}

    observed = observe.hook_output(copy, "SessionStart", payload, script="inject_rules.py")

    assert isinstance(observed, observe.Observed)
    assert STAGE_LINE not in observed.lines


def test_the_resident_kernel_is_injected_for_a_project_that_does_not_disable_the_rule(
    first_move, tmp_path
):
    copy = first_move.arms["lean"].copy
    payload = {**SESSION_START, "cwd": str(tmp_path)}

    observed = observe.hook_output(copy, "SessionStart", payload, script="inject_rules.py")

    assert isinstance(observed, observe.Observed)
    assert STAGE_LINE in observed.lines
