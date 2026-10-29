"""The adr-conventions lean arm links its path-matched rule beside its resident kernel.

Built over a checkout, the kit's lean copy keeps the moved rule in its rules manifest under its
own entry, scoped to every glob the path-matched delivery declares (the decision directory among
them), lists the resident kernel under an entry of its own loaded at session start, and changes
no other entry; the moved rule's own file carries a `paths:` scope naming every declared glob.
The copy's own installer links both files into a sandbox home, and a session started there
receives the kernel's lines and no other line of the moved rule.

A lean declaration that removes or repoints the moved rule's manifest entry while delivering the
rule path-matched is refused when its arms are built, naming the rule file, before any session
is launched and before any results file is written.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest
import yaml

from tests.acceptance.drivers import move_declarations
from tests.acceptance.drivers.adherence_eval import install_fake_claude
from tests.acceptance.drivers.decision_kit import (
    DECISION_MOVE,
    DECISION_RULE,
    lean_session_start,
    rule_lines,
)
from tests.acceptance.drivers.move_eval import (
    ArmBuild,
    ManifestEdit,
    MoveRun,
    build_arms,
    declare,
    declare_manifest_variant,
    move_checkout,
    run_move,
    tracked_snapshot,
    working_state,
)

MANIFEST = move_declarations.MANIFEST
DECISION_DIRECTORY = ".ai-state/decisions"
RESULTS_DIRECTORY = ".ai-state/eval_ledger/adherence/moves"
MANIFEST_EDITS: tuple[ManifestEdit, ...] = ("removed", "repointed at the kernel")


@dataclass(frozen=True)
class KitArms:
    checkout: Path
    build: ArmBuild
    payload: dict

    @property
    def lean(self) -> Path:
        assert self.build.refusal is None, f"the kit's arms were refused: {self.build.refusal}"
        return self.build.arms["lean"].copy


@pytest.fixture(scope="module")
def kit_arms(tmp_path_factory: pytest.TempPathFactory) -> KitArms:
    workspace = tmp_path_factory.mktemp("decision-arms")
    checkout = move_checkout(workspace)
    build = build_arms(
        declare(DECISION_MOVE, "as declared", workspace), checkout, workspace / "arms"
    )
    return KitArms(checkout, build, move_declarations.kit_payload(DECISION_MOVE))


def _rows(manifest: Path) -> dict[str, dict]:
    """The manifest's entries, by the file each points at (an entry without one by its id)."""
    rows = yaml.safe_load(manifest.read_text(encoding="utf-8"))["rules"]
    return {row.get("path") or f"id:{row['id']}": row for row in rows}


def _frontmatter(path: Path) -> dict:
    lines = path.read_text(encoding="utf-8").splitlines()
    if not lines or lines[0] != "---":
        return {}
    return yaml.safe_load("\n".join(lines[1 : lines.index("---", 1)])) or {}


# -- The lean copy's manifest -----------------------------------------------------------------


def test_the_kit_declares_a_path_matched_delivery_of_the_rule_over_the_decision_directory(
    kit_arms,
):
    globs = move_declarations.path_matched_globs(kit_arms.payload)

    assert any(glob.startswith(DECISION_DIRECTORY) for glob in globs), globs


def test_the_lean_manifest_keeps_the_moved_rule_under_its_own_entry_scoped_to_every_glob(
    kit_arms,
):
    row = _rows(kit_arms.lean / MANIFEST).get(DECISION_RULE)
    globs = move_declarations.path_matched_globs(kit_arms.payload)

    assert row is not None, f"the lean manifest has no entry for {DECISION_RULE}"
    assert row.get("load") == "path_scoped", row
    assert set(globs) <= set(row.get("paths", ())), row


def test_the_lean_manifest_lists_the_kernel_under_its_own_entry_loaded_at_session_start(
    kit_arms,
):
    kernel = move_declarations.kernel_file(kit_arms.payload)

    row = _rows(kit_arms.lean / MANIFEST).get(kernel)

    assert row is not None, f"the lean manifest has no entry for the kernel {kernel}"
    assert row.get("load") == "always_on", row


def test_the_lean_manifest_changes_no_other_entry(kit_arms):
    own = {DECISION_RULE, move_declarations.kernel_file(kit_arms.payload)}
    today = {k: v for k, v in _rows(kit_arms.checkout / MANIFEST).items() if k not in own}
    lean = {k: v for k, v in _rows(kit_arms.lean / MANIFEST).items() if k not in own}

    changed = sorted(k for k in lean.keys() | today.keys() if lean.get(k) != today.get(k))

    assert changed == [], changed


def test_the_lean_copys_moved_rule_carries_a_paths_scope_naming_every_declared_glob(kit_arms):
    paths = _frontmatter(kit_arms.lean / DECISION_RULE).get("paths") or []

    assert set(move_declarations.path_matched_globs(kit_arms.payload)) <= set(paths), paths


# -- What the lean copy's own installer links, and what a session starts with -----------------


@pytest.fixture(scope="module")
def lean_start(kit_arms, tmp_path_factory):
    return lean_session_start(kit_arms.lean, tmp_path_factory.mktemp("lean-sandbox"))


def test_the_lean_copys_own_installer_links_the_moved_rule_and_its_kernel(kit_arms, lean_start):
    kernel = move_declarations.kernel_file(kit_arms.payload)

    assert {DECISION_RULE, kernel} <= lean_start.linked_rules, sorted(lean_start.linked_rules)


def test_a_lean_session_starts_with_every_kernel_line(kit_arms, lean_start):
    kernel = move_declarations.resident_kernel(kit_arms.payload).splitlines()
    started = set(lean_start.session_start_text.splitlines())

    assert kernel, "the kit keeps no line of the rule resident"
    assert [line for line in kernel if line not in started] == []


def test_a_lean_session_starts_with_no_other_line_of_the_moved_rule(kit_arms, lean_start):
    kernel = rule_lines(move_declarations.resident_kernel(kit_arms.payload))
    others = rule_lines((kit_arms.checkout / DECISION_RULE).read_text(encoding="utf-8")) - kernel
    started = rule_lines(lean_start.session_start_text)

    assert sorted(others & started) == []


# -- A path-matched rule the manifest would not link is refused at build ----------------------


@pytest.mark.parametrize("edit", MANIFEST_EDITS)
def test_a_lean_manifest_that_would_not_link_the_path_matched_rule_is_refused_naming_it(
    kit_arms, tmp_path, edit
):
    declared = declare_manifest_variant(DECISION_MOVE, edit, kit_arms.lean, tmp_path)

    refusal = build_arms(declared, move_checkout(tmp_path), tmp_path / "arms").refusal

    assert refusal is not None, f"a lean manifest with the rule's entry {edit} was accepted"
    assert DECISION_RULE in refusal, refusal


@dataclass(frozen=True)
class RefusedRun:
    exit_code: int
    output: str
    launches: int
    results: list[str]
    unchanged: bool


@pytest.fixture(scope="module")
def refused_run(kit_arms, tmp_path_factory) -> RefusedRun:
    workspace = tmp_path_factory.mktemp("refused-floor-run")
    declared = declare_manifest_variant(DECISION_MOVE, "removed", kit_arms.lean, workspace)
    checkout = move_checkout(workspace)
    stand_in = install_fake_claude(workspace)
    before = (tracked_snapshot(checkout), working_state(checkout))
    result = run_move(
        MoveRun(DECISION_MOVE, checkout, "floor", declared=declared), stand_in.bin_dir
    )
    results = checkout / RESULTS_DIRECTORY
    written = sorted(p.name for p in results.rglob("*") if p.is_file()) if results.is_dir() else []
    after = (tracked_snapshot(checkout), working_state(checkout))
    return RefusedRun(
        result.exit_code,
        result.stdout + result.stderr,
        len(stand_in.launches()),
        written,
        before == after,
    )


def test_a_run_whose_path_matched_rule_would_never_load_is_refused_naming_the_rule(refused_run):
    assert refused_run.exit_code != 0, "the run was not refused"
    assert DECISION_RULE in refused_run.output, refused_run.output[-2000:]


def test_a_refused_run_launches_no_session_and_writes_no_results_file(refused_run):
    assert (refused_run.launches, refused_run.results) == (0, [])
    assert refused_run.unchanged, "the refused run changed the checkout"
