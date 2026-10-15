"""The arm build, its copy diff and the arm proof decision.

The build tests run over a real materialized copy of this repository; nothing
here starts a ``claude`` process, so whether a spawned role honours the setting
in its copy is proven only by the live smoke run.
"""

from __future__ import annotations

import stat
from dataclasses import replace
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
    tree_entries,
)
from praxion_evals.live.session import SandboxPaths
from tests.conftest import unswitched

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
    # The checkout as the tests were written against it: the role not yet switched.
    return unswitched(
        materialize_path(REPO_ROOT, tmp_path_factory.mktemp("original") / "checkout"), ROLE
    )


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


def _fake_checkout(original: Materialization, root: Path, files: dict[str, str]) -> Materialization:
    return replace(original, root=_tree(root, files))


@pytest.mark.parametrize("cap", [0, -3])
def test_a_turn_cap_below_one_is_refused_before_anything_is_copied(original, tmp_path, cap):
    with pytest.raises(ArmCopyError, match="turn cap"):
        build_arm(original, tmp_path / "copy", ROLE, "lean", turn_cap=cap)

    assert not (tmp_path / "copy").exists()


def test_a_checkout_without_the_roles_definition_is_refused(original, tmp_path):
    checkout = _fake_checkout(original, tmp_path / "checkout", {"agents/verifier.md": "---\n---\n"})

    with pytest.raises(ArmCopyError, match="no regular file"):
        build_arm(checkout, tmp_path / "copy", ROLE, "lean")

    assert not (tmp_path / "copy").exists()


def test_a_definition_that_is_a_link_is_refused_and_its_target_left_alone(original, tmp_path):
    checkout = _fake_checkout(original, tmp_path / "checkout", {"elsewhere.md": "---\n---\nB\n"})
    (checkout.root / "agents").mkdir()
    (checkout.root / DEFINITION).symlink_to("../elsewhere.md")

    with pytest.raises(ArmCopyError, match="no regular file"):
        build_arm(checkout, tmp_path / "copy", ROLE, "lean")

    assert (checkout.root / "elsewhere.md").read_text(encoding="utf-8") == "---\n---\nB\n"


def test_a_failed_build_leaves_nothing_behind_and_can_be_retried(original, tmp_path):
    checkout = _fake_checkout(original, tmp_path / "checkout", {DEFINITION: "no frontmatter\n"})
    dest = tmp_path / "copy"

    with pytest.raises(ArmCopyError, match="frontmatter"):
        build_arm(checkout, dest, ROLE, "lean")
    assert not dest.exists()

    (checkout.root / DEFINITION).write_text("---\nname: x\n---\nBody\n", encoding="utf-8")
    assert build_arm(checkout, dest, ROLE, "lean").patched == (DEFINITION,)


def test_an_interrupted_copy_leaves_nothing_at_dest(original, tmp_path, monkeypatch):
    dest = tmp_path / "copy"

    def half_copy(source, target, **kwargs):
        (Path(target) / "half").mkdir(parents=True)
        (Path(target) / "half" / "file.md").write_text("partial", encoding="utf-8")
        raise OSError("disk full")

    monkeypatch.setattr("praxion_evals.adherence.arms.shutil.copytree", half_copy)

    with pytest.raises(OSError, match="disk full"):
        build_arm(original, dest, ROLE, "lean")
    assert not dest.exists()


def test_an_existing_dest_is_refused_and_left_as_it_was(original, tmp_path):
    dest = tmp_path / "copy"
    dest.mkdir()
    (dest / "keep.md").write_text("mine", encoding="utf-8")

    with pytest.raises(ArmCopyError, match="already exists"):
        build_arm(original, dest, ROLE, "lean")
    assert (dest / "keep.md").read_text(encoding="utf-8") == "mine"


def test_a_definition_with_crlf_line_endings_keeps_them_outside_the_patched_line(
    original, tmp_path
):
    checkout = _fake_checkout(
        original, tmp_path / "checkout", {DEFINITION: "---\r\nname: x\r\n---\r\nBody\r\n"}
    )

    build = build_arm(checkout, tmp_path / "copy", ROLE, "lean")

    assert (build.copy_root / DEFINITION).read_bytes() == (
        b"---\r\nname: x\r\nomitClaudeMd: true\n---\r\nBody\r\n"
    )


def test_a_switched_role_has_no_lean_arm_to_build(original, tmp_path):
    # Its full arm would carry the flag too, so the run would compare nothing; say so.
    checkout = _fake_checkout(
        original,
        tmp_path / "checkout",
        {DEFINITION: "---\nname: x\nomitClaudeMd: true\n---\nBody\n"},
    )

    with pytest.raises(ArmCopyError, match="switched in this checkout"):
        build_arm(checkout, tmp_path / "copy", ROLE, "lean")

    assert not (tmp_path / "copy").exists()


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


def test_a_retargeted_link_is_a_difference(tmp_path):
    original = _tree(tmp_path / "original", {"a.md": "a", "b.md": "b"})
    copy = _tree(tmp_path / "copy", {"a.md": "a", "b.md": "b"})
    (original / "link.md").symlink_to("a.md")
    (copy / "link.md").symlink_to("b.md")

    with pytest.raises(ArmCopyError, match=r"link\.md"):
        verify_copy_diff(original, copy, expected=())
    assert verify_copy_diff(original, copy, expected=("link.md",)) == ("link.md",)


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


def test_the_marker_lands_in_the_installed_instruction_file_only(original, tmp_path):
    sandbox = SandboxPaths(tmp_path / "sandbox")
    install_user_scope(original.root, sandbox.root)
    before_entries = tree_entries(sandbox.root)
    before = (sandbox.config_dir / "CLAUDE.md").read_text(encoding="utf-8")

    nonce = plant_proof_marker(sandbox)

    after_entries = tree_entries(sandbox.root)
    changed = {
        path
        for path in before_entries.keys() | after_entries.keys()
        if before_entries.get(path) != after_entries.get(path)
    }
    assert changed == {sandbox.config_dir.relative_to(sandbox.root).as_posix() + "/CLAUDE.md"}
    after = (sandbox.config_dir / "CLAUDE.md").read_text(encoding="utf-8")
    assert after.startswith(before)
    assert after[len(before) :].strip() == f"{PROOF_LABEL}-{nonce}"
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


@pytest.mark.parametrize(
    "answer",
    [
        "",
        "   ",
        "I could not tell.",
        "Error: request failed",
        f"I was told to reply with exactly {NO_MARKER_REPLY}, but I will not.",
        f"{NO_MARKER_REPLY} and nothing else",
    ],
)
@pytest.mark.parametrize("both_arms", [False, True], ids=["lean-only", "both"])
def test_a_lean_answer_that_is_not_the_no_marker_reply_is_not_built(answer, both_arms):
    observed = {"lean": ProofObservation(answer, 4000)}
    if both_arms:
        observed["full"] = ECHO

    lean = decide_proof(NONCE, observed)["lean"]

    assert isinstance(lean, NotBuilt)
    assert NO_MARKER_REPLY in lean.reason


def test_a_lean_reply_is_the_declared_one_whatever_its_surrounding_whitespace():
    padded = ProofObservation(f"\n  {NO_MARKER_REPLY}\n", 4000)

    assert decide_proof(NONCE, {"lean": padded}) == {"lean": ArmProven("lean", 4000, False)}


@pytest.mark.parametrize(
    ("fields", "message"),
    [
        (("middle", 4000, False), "must be one of"),
        (("lean", -1, False), "cannot hold"),
        (("lean", None, True), "cross-check"),
    ],
)
def test_a_proven_arm_that_breaks_its_invariants_cannot_be_built(fields, message):
    with pytest.raises(ValueError, match=message):
        ArmProven(*fields)


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
