"""Arms run under equal competing settings: the commit-attribution setting, the model, the effort and
the rendered user instruction file are resolved for every arm and a difference is refused naming
the setting; a sandbox carrying a memory index is refused."""

from __future__ import annotations

import hashlib
import shutil
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

import pytest

from praxion_evals.adherence.moves import declaration, pinning
from praxion_evals.adherence.moves.model import LaunchOptions, MoveDeclaration, Pinned
from praxion_evals.adherence.moves.pinning import PinningError

REPO_ROOT = Path(__file__).resolve().parents[2]
READ_TREES = ("rules", "lib")
READ_FILES = ("claude/config/CLAUDE.md.tmpl", "scripts/render_claude_md.py")
SAME = Pinned("harness default", "opus", "medium", "a" * 64)


@pytest.fixture(scope="module")
def copy(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """What the user instructions render from and the rules link from, as the repository has it."""
    root = tmp_path_factory.mktemp("pinning") / "copy"
    for tree in READ_TREES:
        shutil.copytree(REPO_ROOT / tree, root / tree, ignore=shutil.ignore_patterns("__pycache__"))
    for relpath in READ_FILES:
        (root / relpath).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(REPO_ROOT / relpath, root / relpath)
    return root


def _declared(**lean: str | None) -> MoveDeclaration:
    return replace(declaration.kit("git-conventions"), launch={"lean": LaunchOptions(**lean)})


def _pinned(declared: MoveDeclaration, copy: Path, **run: str) -> Pinned:
    return pinning.pin(declared, {"full": copy, "lean": copy, "floor": copy}, **run)


# -- Equal arms -------------------------------------------------------------------------------


def test_arms_with_no_declared_difference_share_the_entry_defaults(copy):
    pinned = _pinned(_declared(), copy)

    assert (pinned.commit_attribution, pinned.model, pinned.effort) == (
        pinning.DEFAULT_ATTRIBUTION,
        pinning.DEFAULT_MODEL,
        pinning.DEFAULT_EFFORT,
    )


def test_the_user_instructions_are_pinned_as_the_digest_of_their_rendered_text(copy):
    pinned = _pinned(_declared(), copy)

    rendered = hashlib.sha256((_render(copy)).encode()).hexdigest()
    assert pinned.user_instructions == rendered


def test_the_runs_own_model_and_effort_are_what_the_arms_share(copy):
    pinned = _pinned(_declared(), copy, model="sonnet", effort="high")

    assert (pinned.model, pinned.effort) == ("sonnet", "high")


def test_equal_launch_options_declared_on_every_arm_are_equal_settings(copy):
    option = LaunchOptions(model="sonnet")
    declared = replace(
        declaration.kit("git-conventions"), launch={"full": option, "lean": option, "floor": option}
    )

    assert _pinned(declared, copy).model == "sonnet"


# -- Arms that differ -------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("lean", "named"),
    [
        ({"attribution": "set-on-the-lean-arm-only"}, "commit-attribution setting"),
        ({"model": "sonnet"}, "model"),
        ({"effort": "high"}, "effort"),
        ({"user_instructions": "Answer in one line.\n"}, "user instruction file"),
    ],
)
def test_arms_differing_in_a_pinned_setting_are_refused_naming_it(copy, lean, named):
    with pytest.raises(PinningError) as refused:
        _pinned(_declared(**lean), copy)

    assert named in str(refused.value)
    assert "lean and full" in str(refused.value)


def test_a_differing_floor_arm_is_refused_as_well_as_a_differing_lean_arm(copy):
    declared = replace(
        declaration.kit("git-conventions"), launch={"floor": LaunchOptions(effort="low")}
    )

    with pytest.raises(PinningError, match="floor and full arms differ in the effort"):
        _pinned(declared, copy)


def test_the_differing_values_are_shown_with_the_digest_shortened():
    other = replace(SAME, user_instructions="b" * 64)

    with pytest.raises(PinningError) as refused:
        pinning.require_equal({"full": SAME, "lean": other})

    assert "b" * pinning.DIGEST_CHARS in str(refused.value)
    assert "b" * (pinning.DIGEST_CHARS + 1) not in str(refused.value)


def test_equal_settings_come_back_as_the_one_value_they_share():
    assert pinning.require_equal({"full": SAME, "lean": replace(SAME)}) == SAME


# -- The sandbox ------------------------------------------------------------------------------


def test_a_sandbox_carrying_a_memory_index_is_refused_naming_it(tmp_path):
    memory = tmp_path / "home/.claude/projects/p/memory"
    memory.mkdir(parents=True)
    (memory / pinning.MEMORY_INDEX).write_text("- a remembered instruction\n", encoding="utf-8")

    with pytest.raises(PinningError, match=r"lean arm's sandbox carries a MEMORY.md"):
        pinning.require_no_memory(tmp_path / "home", "lean")


def test_a_sandbox_without_a_memory_index_is_accepted(tmp_path):
    (tmp_path / "home/.claude").mkdir(parents=True)
    (tmp_path / "home/.claude/CLAUDE.md").write_text("instructions\n", encoding="utf-8")

    pinning.require_no_memory(tmp_path / "home", "lean")


def test_a_copy_whose_user_instructions_cannot_be_rendered_is_refused_naming_the_arm(tmp_path):
    with pytest.raises(PinningError, match="arm's user instructions cannot be rendered"):
        _pinned(_declared(), tmp_path)


def _render(copy: Path) -> str:
    out = copy.parent / "rendered.md"
    subprocess.run(
        [
            sys.executable,
            str(copy / "scripts/render_claude_md.py"),
            str(copy / READ_FILES[0]),
            str(out),
        ],
        check=True,
        capture_output=True,
        cwd=copy.parent,
    )
    return out.read_text(encoding="utf-8")
