"""A move declaration is parsed once, at the boundary: each refusal bites, the accepted shape
round-trips into the frozen values."""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from praxion_evals.adherence.moves import declaration
from praxion_evals.adherence.moves.declaration import DeclarationError
from praxion_evals.adherence.moves.model import (
    BothKinds,
    GateRefusal,
    HookContext,
    HookRegistered,
    KernelDerive,
    LaunchOptions,
    ManifestRowRemoved,
    ManifestRowScoped,
    MoveName,
    OnlyKind,
    PathMatched,
    ProjectGating,
    RelPath,
    Remove,
    SessionStart,
    Write,
)

RULE = "rules/swe/vcs/git-conventions.md"
SECTION = "Commit Message Format"
NOTE = "A note only the lean arm holds.\n"


def a_payload() -> dict[str, Any]:
    return {
        "schema": "move-declaration/1",
        "move": "git-conventions",
        "moved_rule": RULE,
        "checks": [
            {"name": "message form", "rule_file": RULE, "section": SECTION, "phrases": ["50"]},
            {"name": "staging", "rule_file": RULE, "section": "Staging Discipline"},
        ],
        "fixture_scope": "both",
        "arms": {
            "full": [],
            "lean": [
                {"op": "write", "path": "docs/note.md", "source": "note.md"},
                {"op": "derive", "path": RULE, "kind": "kernel", "lines": ["- Stage", "- Never"]},
                {"op": "derive", "path": "rules/_manifest.yaml", "kind": "manifest_row_removed"},
                {"op": "derive", "path": "hooks/hooks.json", "kind": "hook_registered"},
            ],
            "floor": [{"op": "remove", "path": RULE}],
        },
        "deliveries": [
            {"channel": "session_start", "file": RULE, "lines": ["- Stage"]},
            {"channel": "path_matched", "file": RULE, "globs": ["**/*.py"]},
            {
                "channel": "hook_context",
                "event": "PreToolUse",
                "matcher": "Bash",
                "reads": RULE,
                "repeat": "once",
            },
            {"channel": "gate_refusal", "matcher": "Bash", "reads": RULE},
            {"channel": "project_gating", "kind": "managed"},
        ],
        "launch": {
            "full": {"model": None, "effort": None, "attribution": None, "user_instructions": None},
            "lean": {"model": "sonnet", "user_instructions": "instructions.md"},
        },
    }


def write(tmp_path: Path, payload: dict[str, Any]) -> Path:
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / "note.md").write_text(NOTE, encoding="utf-8")
    (tmp_path / "instructions.md").write_text("Answer in one line.\n", encoding="utf-8")
    path = tmp_path / "declaration.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def edited(tmp_path: Path, edit: Any) -> Path:
    payload = a_payload()
    edit(payload)
    return write(tmp_path, payload)


def refused_by(path: Path, **kwargs: Any) -> str:
    with pytest.raises(DeclarationError) as refusal:
        declaration.load(path, **kwargs)
    return str(refusal.value)


def a_checkout(root: Path, text: str) -> Path:
    (root / "rules/swe/vcs").mkdir(parents=True)
    (root / RULE).write_text(text, encoding="utf-8")
    return root


# -- The accepted shape ---------------------------------------------------------------------


def test_the_accepted_shape_round_trips_into_the_frozen_values(tmp_path: Path) -> None:
    loaded = declaration.load(write(tmp_path, a_payload()))

    assert loaded.move == MoveName("git-conventions")
    assert loaded.moved_rule == RelPath.parse(RULE)
    assert [c.name for c in loaded.checks.checks] == ["message form", "staging"]
    assert loaded.checks.checks[0].phrases == ("50",)
    assert loaded.checks.checks[1].phrases == ()
    assert loaded.fixture_scope == BothKinds()
    assert loaded.deliveries == (
        SessionStart(RelPath.parse(RULE), ("- Stage",)),
        PathMatched(RelPath.parse(RULE), ("**/*.py",)),
        HookContext("PreToolUse", "Bash", RelPath.parse(RULE), "once"),
        GateRefusal("Bash", RelPath.parse(RULE)),
        ProjectGating("managed"),
    )


def test_each_arm_change_form_parses_and_a_write_carries_the_digest_of_its_content(
    tmp_path: Path,
) -> None:
    loaded = declaration.load(write(tmp_path, a_payload()))

    note, kernel, manifest, hook = loaded.arms.for_arm("lean")
    assert note == Write(
        RelPath.parse("docs/note.md"),
        (tmp_path / "note.md").resolve(),
        hashlib.sha256(NOTE.encode()).hexdigest(),
    )
    assert kernel == KernelDerive(RelPath.parse(RULE), ("- Stage", "- Never"))
    assert manifest == ManifestRowRemoved(RelPath.parse("rules/_manifest.yaml"))
    assert hook == HookRegistered(RelPath.parse("hooks/hooks.json"))
    assert loaded.arms.for_arm("floor") == (Remove(RelPath.parse(RULE)),)
    assert loaded.arms.for_arm("full") == ()


def test_launch_options_default_per_arm_and_the_instruction_file_is_read_beside_the_declaration(
    tmp_path: Path,
) -> None:
    loaded = declaration.load(write(tmp_path, a_payload()))

    assert loaded.launch["full"] == LaunchOptions()
    assert loaded.launch["lean"] == LaunchOptions(
        model="sonnet", user_instructions="Answer in one line.\n"
    )
    assert loaded.launch["floor"] == LaunchOptions()


@pytest.mark.parametrize(
    ("word", "scope"), [("managed", OnlyKind("managed")), ("unmanaged", OnlyKind("unmanaged"))]
)
def test_a_fixture_scope_of_one_kind_parses_to_that_kind(
    tmp_path: Path, word: str, scope: OnlyKind
) -> None:
    path = edited(tmp_path, lambda p: p.update(fixture_scope=word))

    assert declaration.load(path).fixture_scope == scope


# -- Refusals -------------------------------------------------------------------------------


@pytest.mark.parametrize("count", [0, 3])
def test_zero_or_three_governed_checks_are_refused(tmp_path: Path, count: int) -> None:
    def edit(payload: dict[str, Any]) -> None:
        template = payload["checks"][0]
        payload["checks"] = [{**template, "name": f"check {i}"} for i in range(count)]

    assert "one or two" in refused_by(edited(tmp_path, edit))


def test_a_section_its_rule_file_lacks_is_refused_naming_it(tmp_path: Path) -> None:
    path = write(tmp_path, a_payload())
    checkout = a_checkout(tmp_path / "checkout", f"### {SECTION}\nkeep it to 50\n")

    message = refused_by(path, checkout=checkout)

    assert "Staging Discipline" in message
    assert RULE in message


def test_a_rule_file_the_checkout_lacks_is_refused_naming_it(tmp_path: Path) -> None:
    (tmp_path / "checkout").mkdir()

    message = refused_by(write(tmp_path, a_payload()), checkout=tmp_path / "checkout")

    assert RULE in message


def test_every_section_held_is_accepted_against_the_checkout(tmp_path: Path) -> None:
    checkout = a_checkout(
        tmp_path / "checkout", f"## {SECTION}\nkeep it to 50\n\n### Staging Discipline  \n"
    )

    assert declaration.load(write(tmp_path, a_payload()), checkout=checkout).checks.checks


def test_a_phrase_its_section_does_not_hold_is_refused_naming_check_phrase_section_and_rule(
    tmp_path: Path,
) -> None:
    checkout = a_checkout(tmp_path / "checkout", f"## {SECTION}\nno number here\n")

    message = refused_by(write(tmp_path, a_payload()), checkout=checkout)

    named = ("message form", "'50'", SECTION, RULE)
    assert [value for value in named if value not in message] == [], message


def test_a_phrase_differing_only_in_letter_case_is_accepted(tmp_path: Path) -> None:
    payload = a_payload()
    payload["checks"][0]["phrases"] = ["FIFTY chars"]
    checkout = a_checkout(
        tmp_path / "checkout", f"## {SECTION}\nKeep it to fifty Chars\n\n## Staging Discipline\n"
    )

    assert declaration.load(write(tmp_path, payload), checkout=checkout).checks.checks


def test_a_phrase_held_only_outside_its_section_is_refused(tmp_path: Path) -> None:
    checkout = a_checkout(
        tmp_path / "checkout",
        f"## Before\n50\n\n## {SECTION}\ntext\n\n## After\n50\n\n## Staging Discipline\n",
    )

    message = refused_by(write(tmp_path, a_payload()), checkout=checkout)

    assert "'50'" in message


def test_a_phrase_held_by_a_sub_heading_of_its_section_counts_as_inside(tmp_path: Path) -> None:
    checkout = a_checkout(
        tmp_path / "checkout",
        f"## {SECTION}\ntext\n\n### Detail\nkeep it to 50\n\n## Staging Discipline\n",
    )

    assert declaration.load(write(tmp_path, a_payload()), checkout=checkout).checks.checks


def test_a_number_sign_line_inside_a_fenced_block_ends_no_section(tmp_path: Path) -> None:
    checkout = a_checkout(
        tmp_path / "checkout",
        f"## {SECTION}\n```\n## not a heading\n```\nkeep it to 50\n\n## Staging Discipline\n",
    )

    assert declaration.load(write(tmp_path, a_payload()), checkout=checkout).checks.checks


def test_a_section_heading_only_inside_a_fenced_block_is_no_section(tmp_path: Path) -> None:
    checkout = a_checkout(tmp_path / "checkout", f"```\n## {SECTION}\nkeep it to 50\n```\n")

    assert SECTION in refused_by(write(tmp_path, a_payload()), checkout=checkout)


def levels(*lines: str) -> list[int | None]:
    return [heading and heading.level for heading in declaration.markdown_headings(list(lines))]


@pytest.mark.parametrize(
    ("lines", "expected"),
    [
        pytest.param(("# a", "text", "### b  "), [1, None, 3], id="plain-headings"),
        pytest.param(("```", "# a", "```", "# b"), [None, None, None, 1], id="backtick-fence"),
        pytest.param(("~~~", "# a", "~~~", "# b"), [None, None, None, 1], id="tilde-fence"),
        pytest.param(("   ```", "# a", "   ```", "# b"), [None, None, None, 1], id="indented-3"),
        pytest.param(("    ```", "# a"), [None, 1], id="indented-4-is-no-fence"),
        pytest.param(
            ("````", "```", "# a", "````", "# b"), [None, None, None, None, 1], id="longer"
        ),
        pytest.param(("```", "~~~", "# a", "```", "# b"), [None, None, None, None, 1], id="mixed"),
        pytest.param(("```", "# a", "``` x", "# b"), [None, None, None, None], id="close-bare"),
        pytest.param(("```python", "# a"), [None, None], id="unclosed-runs-to-the-end"),
    ],
)
def test_headings_are_found_outside_fenced_code_only(lines, expected) -> None:
    assert levels(*lines) == expected


@pytest.mark.parametrize(
    "path", ["../outside.md", "/etc/passwd", "a/../../b", ".ai-state/eval_ledger/x.json"]
)
def test_a_path_outside_the_checkout_or_under_the_eval_ledger_is_refused(
    tmp_path: Path, path: str
) -> None:
    def edit(payload: dict[str, Any]) -> None:
        payload["arms"]["floor"] = [{"op": "remove", "path": path}]

    assert path in refused_by(edited(tmp_path, edit))


def test_a_delivery_reading_a_path_outside_the_checkout_is_refused(tmp_path: Path) -> None:
    def edit(payload: dict[str, Any]) -> None:
        payload["deliveries"] = [{"channel": "gate_refusal", "matcher": "Bash", "reads": "../x"}]

    assert "../x" in refused_by(edited(tmp_path, edit))


def test_an_unknown_channel_is_refused(tmp_path: Path) -> None:
    def edit(payload: dict[str, Any]) -> None:
        payload["deliveries"].append({"channel": "telepathy"})

    assert "telepathy" in refused_by(edited(tmp_path, edit))


def test_a_scoped_manifest_row_derive_parses_to_its_value(tmp_path: Path) -> None:
    def edit(payload: dict[str, Any]) -> None:
        payload["arms"]["lean"][2]["kind"] = "manifest_row_scoped"

    loaded = declaration.load(edited(tmp_path, edit))

    assert loaded.arms.for_arm("lean")[2] == ManifestRowScoped(
        RelPath.parse("rules/_manifest.yaml")
    )


def test_an_unknown_derive_kind_or_op_is_refused(tmp_path: Path) -> None:
    def derive(payload: dict[str, Any]) -> None:
        payload["arms"]["lean"].append({"op": "derive", "path": RULE, "kind": "guess"})

    def op(payload: dict[str, Any]) -> None:
        payload["arms"]["lean"].append({"op": "rename", "path": RULE})

    assert "guess" in refused_by(edited(tmp_path / "a", derive))
    assert "rename" in refused_by(edited(tmp_path / "b", op))


def test_a_full_arm_that_declares_a_change_is_refused(tmp_path: Path) -> None:
    def edit(payload: dict[str, Any]) -> None:
        payload["arms"]["full"] = [{"op": "remove", "path": RULE}]

    assert "full arm" in refused_by(edited(tmp_path, edit))


def test_a_write_source_that_is_missing_is_refused(tmp_path: Path) -> None:
    def edit(payload: dict[str, Any]) -> None:
        payload["arms"]["lean"][0]["source"] = "gone.md"

    assert "gone.md" in refused_by(edited(tmp_path, edit))


def test_a_write_source_outside_the_declarations_directory_is_refused(tmp_path: Path) -> None:
    (tmp_path / "outside.md").write_text("x", encoding="utf-8")

    def edit(payload: dict[str, Any]) -> None:
        payload["arms"]["lean"][0]["source"] = "../outside.md"

    assert "outside" in refused_by(edited(tmp_path / "kit", edit))


def test_an_instruction_file_that_is_missing_is_refused(tmp_path: Path) -> None:
    def edit(payload: dict[str, Any]) -> None:
        payload["launch"]["lean"]["user_instructions"] = "absent.md"

    assert "absent.md" in refused_by(edited(tmp_path, edit))


@pytest.mark.parametrize(
    ("edit", "named"),
    [
        (lambda p: p.update(schema="move-declaration/2"), "schema"),
        (lambda p: p.pop("checks"), "checks"),
        (lambda p: p.pop("fixture_scope"), "fixture_scope"),
        (lambda p: p.update(fixture_scope="sometimes"), "sometimes"),
        (lambda p: p.update(move="Not A Name"), "Not A Name"),
        (lambda p: p.update(arms={"full": [], "ceiling": []}), "ceiling"),
        (lambda p: p["launch"].update(ceiling={}), "ceiling"),
        (lambda p: p["launch"]["lean"].update(temperature="0"), "temperature"),
        (lambda p: p["deliveries"][2].update(repeat="always"), "always"),
        (lambda p: p["deliveries"][1].update(globs=[]), "glob"),
        (lambda p: p["arms"]["lean"][1].update(lines=[]), "prefix"),
        (lambda p: p["arms"]["lean"].append(copy.deepcopy(p["arms"]["lean"][0])), "once"),
    ],
)
def test_a_malformed_declaration_is_refused_naming_the_defect(
    tmp_path: Path, edit: Any, named: str
) -> None:
    assert named in refused_by(edited(tmp_path, edit))


def test_a_file_that_is_not_json_or_not_an_object_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "declaration.json"
    path.write_text("{not json", encoding="utf-8")
    assert "not JSON" in refused_by(path)

    path.write_text("[]", encoding="utf-8")
    assert "JSON object" in refused_by(path)


def test_a_declaration_file_that_is_missing_is_refused(tmp_path: Path) -> None:
    assert "cannot be read" in refused_by(tmp_path / "none.json")


# -- The kit registry -----------------------------------------------------------------------


def test_a_kit_the_registry_lacks_is_refused(tmp_path: Path) -> None:
    for name in ("no-such-move", "../escape", "Bad Name"):
        with pytest.raises(DeclarationError, match="no move kit"):
            declaration.kit(name)


def test_a_kit_is_read_from_its_own_directory_and_must_declare_its_own_move(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    kits = tmp_path / "kits"
    (kits / "git-conventions").mkdir(parents=True)
    write(kits / "git-conventions", a_payload())
    monkeypatch.setattr(declaration, "KITS_ROOT", kits)

    assert declaration.kit("git-conventions").move == MoveName("git-conventions")

    (kits / "other-move").mkdir()
    write(kits / "other-move", a_payload())
    with pytest.raises(DeclarationError, match="declares the move 'git-conventions'"):
        declaration.kit("other-move")
