"""The arm build, its copy diff and the arm proof decision.

The build tests run over a real materialized copy of this repository; nothing
here starts a ``claude`` process, so whether a spawned role honours the setting
in its copy is proven only by the live smoke run.
"""

from __future__ import annotations

import stat
from pathlib import Path

import pytest
import yaml

from praxion_evals.adherence.arms import (
    NO_MARKER_REPLY,
    PROOF_LABEL,
    ArmCopyError,
    ArmProven,
    ProofObservation,
    build_arm,
    decide_proof,
    plant_proof_marker,
    proof_prompt,
    set_frontmatter_key,
    verify_copy_diff,
)
from praxion_evals.adherence.model import NotBuilt
from praxion_evals.live.materialize import (
    Materialization,
    install_user_scope,
    make_writable,
    materialize_path,
    tree_digest,
)
from praxion_evals.live.session import SandboxPaths

REPO_ROOT = Path(__file__).resolve().parents[2]
ROLE = "researcher"
DEFINITION = f"agents/{ROLE}.md"
LOWERED_CAP = 5


def _split(definition: str) -> tuple[dict, str]:
    assert definition.startswith("---\n")
    frontmatter, body = definition[4:].split("\n---\n", 1)
    return yaml.safe_load(frontmatter), body


def _read(root: Path, relpath: str) -> str:
    return (root / relpath).read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def original(tmp_path_factory: pytest.TempPathFactory) -> Materialization:
    return materialize_path(REPO_ROOT, tmp_path_factory.mktemp("original") / "checkout")


@pytest.fixture(scope="module")
def arms(original: Materialization, tmp_path_factory: pytest.TempPathFactory) -> dict:
    root = tmp_path_factory.mktemp("arms")
    return {
        "full": build_arm(original, root / "full", ROLE, "full"),
        "lean": build_arm(original, root / "lean", ROLE, "lean"),
        "full-capped": build_arm(
            original, root / "full-capped", ROLE, "full", turn_cap=LOWERED_CAP
        ),
        "lean-capped": build_arm(
            original, root / "lean-capped", ROLE, "lean", turn_cap=LOWERED_CAP
        ),
    }


# ---------------------------------------------------------------------------
# The build
# ---------------------------------------------------------------------------


def test_the_lean_frontmatter_is_the_original_plus_the_one_key(original, arms):
    original_frontmatter, original_body = _split(_read(original.root, DEFINITION))

    frontmatter, body = _split(_read(arms["lean"].copy_root, DEFINITION))

    assert frontmatter == {**original_frontmatter, "omitClaudeMd": True}
    assert body == original_body


@pytest.mark.parametrize("relpath", ["hooks/hooks.json", "agents/verifier.md", "CLAUDE.md"])
def test_every_other_file_of_the_lean_copy_is_the_originals(original, arms, relpath):
    assert arms["lean"].patched == (DEFINITION,)
    assert _read(arms["lean"].copy_root, relpath) == _read(original.root, relpath)


def test_the_full_copy_differs_from_the_checkout_nowhere(original, arms):
    full = arms["full"]

    assert full.patched == ()
    assert full.tree_digest == original.tree_digest == tree_digest(full.copy_root)


def test_the_early_stop_twin_differs_only_in_the_turn_cap(original, arms):
    original_frontmatter, original_body = _split(_read(original.root, DEFINITION))

    capped, capped_body = _split(_read(arms["full-capped"].copy_root, DEFINITION))
    lean_capped, lean_capped_body = _split(_read(arms["lean-capped"].copy_root, DEFINITION))

    assert capped == {**original_frontmatter, "maxTurns": LOWERED_CAP}
    assert lean_capped == {**original_frontmatter, "maxTurns": LOWERED_CAP, "omitClaudeMd": True}
    assert capped_body == lean_capped_body == original_body
    assert arms["full-capped"].turn_cap == arms["lean-capped"].turn_cap == LOWERED_CAP
    assert arms["full-capped"].patched == (DEFINITION,)


@pytest.mark.parametrize("name", ["full", "lean", "full-capped", "lean-capped"])
@pytest.mark.parametrize("relpath", [".", DEFINITION, "agents"])
def test_a_built_copy_is_read_only(arms, name, relpath):
    path = arms[name].copy_root / relpath

    assert not path.stat().st_mode & (stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH)


def test_building_the_arms_leaves_the_checkout_copy_as_it_was(original, arms):
    assert arms
    assert tree_digest(original.root) == original.tree_digest


def test_a_build_names_its_digest_and_copy(arms):
    assert arms["lean"].tree_digest == tree_digest(arms["lean"].copy_root)
    assert arms["lean"].tree_digest != arms["full"].tree_digest


def test_an_unknown_role_is_refused(original, tmp_path):
    with pytest.raises(ArmCopyError, match="unknown role"):
        build_arm(original, tmp_path / "copy", "not-a-role", "lean")  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# The copy diff
# ---------------------------------------------------------------------------


def _tree(root: Path, files: dict[str, str]) -> Path:
    for relpath, text in files.items():
        (root / relpath).parent.mkdir(parents=True, exist_ok=True)
        (root / relpath).write_text(text, encoding="utf-8")
    return root


def test_a_tampered_second_file_makes_the_diff_raise(original, tmp_path):
    build = build_arm(original, tmp_path / "copy", ROLE, "lean")
    tampered = build.copy_root / "agents" / "verifier.md"
    make_writable(build.copy_root)
    tampered.write_text(tampered.read_text(encoding="utf-8") + "\nextra\n", encoding="utf-8")

    with pytest.raises(ArmCopyError, match=r"verifier\.md"):
        verify_copy_diff(original.root, build.copy_root, expected=(DEFINITION,))


@pytest.mark.parametrize(
    ("copy_files", "culprit"),
    [({"a.md": "a", "b.md": "b", "c.md": "c"}, "c.md"), ({"a.md": "a"}, "b.md")],
    ids=["stray", "missing"],
)
def test_a_stray_or_a_missing_file_is_a_difference(tmp_path, copy_files, culprit):
    original = _tree(tmp_path / "original", {"a.md": "a", "b.md": "b"})
    copy = _tree(tmp_path / "copy", copy_files)

    with pytest.raises(ArmCopyError, match=culprit):
        verify_copy_diff(original, copy, expected=())


def test_an_expected_path_that_did_not_change_is_an_error(tmp_path):
    original = _tree(tmp_path / "original", {"a.md": "a"})
    identical = _tree(tmp_path / "identical", {"a.md": "a"})

    with pytest.raises(ArmCopyError, match="should differ"):
        verify_copy_diff(original, identical, expected=("a.md",))


def test_an_exact_expected_difference_is_returned(tmp_path):
    original = _tree(tmp_path / "original", {"a.md": "a", "b.md": "b"})
    copy = _tree(tmp_path / "copy", {"a.md": "a", "b.md": "B"})

    assert verify_copy_diff(original, copy, expected=("b.md",)) == ("b.md",)


# ---------------------------------------------------------------------------
# The frontmatter patch
# ---------------------------------------------------------------------------

DEFINITION_TEXT = "---\nname: x\nmaxTurns: 80\n---\n\nBody line\n"


def test_a_missing_key_is_added_last_in_the_block():
    assert set_frontmatter_key(DEFINITION_TEXT, "omitClaudeMd", "true") == (
        "---\nname: x\nmaxTurns: 80\nomitClaudeMd: true\n---\n\nBody line\n"
    )


def test_an_existing_key_is_replaced_in_place():
    assert set_frontmatter_key(DEFINITION_TEXT, "maxTurns", "5") == (
        "---\nname: x\nmaxTurns: 5\n---\n\nBody line\n"
    )


def test_a_body_key_look_alike_is_not_touched():
    text = "---\nname: x\n---\nmaxTurns: 80\n"

    assert (
        set_frontmatter_key(text, "maxTurns", "5")
        == "---\nname: x\nmaxTurns: 5\n---\nmaxTurns: 80\n"
    )


@pytest.mark.parametrize("text", ["no frontmatter\n", "---\nname: x\n", ""])
def test_a_definition_without_a_closed_frontmatter_is_refused(text):
    with pytest.raises(ArmCopyError, match="frontmatter"):
        set_frontmatter_key(text, "omitClaudeMd", "true")


# ---------------------------------------------------------------------------
# The proof: marker, prompt, decision
# ---------------------------------------------------------------------------


def test_the_marker_lands_in_the_installed_instruction_file_only(original, arms, tmp_path):
    sandbox = SandboxPaths(tmp_path / "sandbox")
    install_user_scope(original.root, sandbox.root)
    before = (sandbox.config_dir / "CLAUDE.md").read_text(encoding="utf-8")

    nonce = plant_proof_marker(sandbox)

    after = (sandbox.config_dir / "CLAUDE.md").read_text(encoding="utf-8")
    assert after.startswith(before)
    assert after[len(before) :].strip() == f"{PROOF_LABEL}-{nonce}"
    shipped = [
        build.copy_root / relpath
        for build in arms.values()
        for relpath in (DEFINITION, "hooks/hooks.json")
    ]
    assert not any(nonce in path.read_text(encoding="utf-8") for path in shipped)
    assert tree_digest(original.root) == original.tree_digest


def test_each_marker_is_fresh(tmp_path):
    sandbox = SandboxPaths(tmp_path)
    sandbox.config_dir.mkdir(parents=True)
    (sandbox.config_dir / "CLAUDE.md").write_text("rules\n", encoding="utf-8")

    first, second = plant_proof_marker(sandbox), plant_proof_marker(sandbox)

    assert first != second
    assert len(first) == len(second) >= 16


def test_a_marker_needs_an_installed_instruction_file(tmp_path):
    with pytest.raises(ArmCopyError, match="not installed"):
        plant_proof_marker(SandboxPaths(tmp_path))


def test_the_prompt_asks_for_the_marker_without_carrying_a_nonce():
    prompt = proof_prompt()

    assert PROOF_LABEL in prompt
    assert NO_MARKER_REPLY in prompt
    assert not any(ch.isdigit() for ch in prompt.replace(PROOF_LABEL, ""))


NONCE = "0123456789abcdef"
ECHO = ProofObservation(f"{PROOF_LABEL}-{NONCE}", 9000)
SILENT = ProofObservation(NO_MARKER_REPLY, 4000)


def test_both_arms_proven_when_full_echoes_lean_does_not_and_lean_is_smaller():
    verdicts = decide_proof(NONCE, {"full": ECHO, "lean": SILENT})

    assert verdicts == {
        "full": ArmProven("full", 9000, cross_checked=True),
        "lean": ArmProven("lean", 4000, cross_checked=True),
    }


def test_a_nonce_echoed_in_lean_leaves_lean_not_built_and_full_proven():
    verdicts = decide_proof(NONCE, {"full": ECHO, "lean": ECHO})

    assert isinstance(verdicts["full"], ArmProven)
    assert isinstance(verdicts["lean"], NotBuilt)
    assert "omitClaudeMd had no effect" in verdicts["lean"].reason


def test_a_nonce_missing_in_full_leaves_full_not_built():
    verdicts = decide_proof(NONCE, {"full": SILENT, "lean": SILENT})

    assert isinstance(verdicts["full"], NotBuilt)
    assert isinstance(verdicts["lean"], ArmProven)


def test_a_role_that_was_never_spawned_is_not_built_with_the_reason():
    verdicts = decide_proof(NONCE, {"full": None, "lean": SILENT})

    assert isinstance(verdicts["full"], NotBuilt)
    assert "never spawned" in verdicts["full"].reason
    assert verdicts["lean"] == ArmProven("lean", 4000, cross_checked=False)


@pytest.mark.parametrize("lean_tokens", [9000, 12000, 0])
def test_lean_tokens_that_are_not_smaller_leave_only_lean_not_built(lean_tokens):
    lean = ProofObservation(NO_MARKER_REPLY, lean_tokens)

    verdicts = decide_proof(NONCE, {"full": ECHO, "lean": lean})

    assert isinstance(verdicts["full"], ArmProven)
    assert isinstance(verdicts["lean"], NotBuilt)
    assert "not smaller" in verdicts["lean"].reason


def test_a_missing_token_figure_leaves_lean_unconfirmed():
    unknown = ProofObservation(NO_MARKER_REPLY, None)

    verdicts = decide_proof(NONCE, {"full": ECHO, "lean": unknown})

    assert isinstance(verdicts["lean"], NotBuilt)


def test_a_single_lean_run_decides_on_the_nonce_and_records_the_figure():
    assert decide_proof(NONCE, {"lean": SILENT}) == {"lean": ArmProven("lean", 4000, False)}
    assert isinstance(decide_proof(NONCE, {"lean": ECHO})["lean"], NotBuilt)


def test_a_single_full_run_decides_on_the_nonce_alone():
    assert decide_proof(NONCE, {"full": ECHO}) == {"full": ArmProven("full", 9000, False)}
    assert isinstance(decide_proof(NONCE, {"full": SILENT})["full"], NotBuilt)


def test_an_empty_nonce_or_an_unknown_arm_is_refused():
    with pytest.raises(ValueError, match="nonce"):
        decide_proof("", {"full": ECHO})
    with pytest.raises(ValueError, match="arms"):
        decide_proof(NONCE, {"middle": ECHO})  # type: ignore[dict-item]
