"""Tests for `refactoring_move.py` -- the reversible move of the refactoring skill.

Every scenario moves temporary copies of the live definitions; none writes to the checkout.
The copies are first brought to the preloaded state by the tool itself, so the scenarios hold
whether the checkout is still preloaded or the move has since been applied to it.
"""

from __future__ import annotations

import importlib.util
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

# The checkout root is found by a marker, not by counting parents: the mutation sensor runs this
# file from a `mutants/` copy one directory deeper.
LIVE_ROOT = next(
    p for p in Path(__file__).resolve().parents if (p / "agents" / "implementer.md").is_file()
)
sys.path.append(str(LIVE_ROOT / "hooks"))
sys.path.append(str(LIVE_ROOT / "scripts"))

import _skill_delivery as delivery  # noqa: E402
import artifact_registry  # noqa: E402
import refactoring_move as move  # noqa: E402

ROLES = ("implementer", "test-engineer")
SKILL = "refactoring"
EXPORTER = LIVE_ROOT / "codex" / "config" / "export-codex-agents.py"


def _definition(root: Path, role: str) -> Path:
    return root / "agents" / f"{role}.md"


def _snapshot(root: Path) -> dict[str, bytes]:
    return {role: _definition(root, role).read_bytes() for role in ROLES}


def _edit(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    assert old in text, f"{path.name} does not hold the text to edit"
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


def _run(root: Path, to: str, *flags: str) -> int:
    return move.main(["--to", to, "--root", str(root), *flags])


def _preloaded_skills(root: Path, role: str) -> list[str]:
    text = _definition(root, role).read_text(encoding="utf-8")
    frontmatter = text.split("\n---\n", 1)[0].removeprefix("---\n")
    return list(yaml.safe_load(frontmatter)["skills"])


def _wrapper_passages(root: Path, role: str) -> list[str]:
    spec = importlib.util.spec_from_file_location("export_codex_agents", EXPORTER)
    assert spec is not None
    assert spec.loader is not None
    exporter = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(exporter)
    path = _definition(root, role)
    return exporter.extract_wrapper_passages(path.read_text(encoding="utf-8"), path)


@pytest.fixture
def preloaded(tmp_path: Path) -> Path:
    for role in ROLES:
        _definition(tmp_path, role).parent.mkdir(exist_ok=True)
        shutil.copyfile(_definition(LIVE_ROOT, role), _definition(tmp_path, role))
    assert _run(tmp_path, "preloaded") == 0
    return tmp_path


# -- The live definitions ----------------------------------------------------------------------


def test_the_live_definitions_hold_one_state_wholly() -> None:
    preloaded_holds = _run(LIVE_ROOT, "preloaded", "--check") == 0
    delivered_holds = _run(LIVE_ROOT, "delivered", "--check") == 0

    assert preloaded_holds != delivered_holds, "the live definitions hold neither state wholly"


# -- What each state means for the preload reader ---------------------------------------------


@pytest.mark.parametrize("role", ROLES)
def test_the_preloaded_state_reads_as_preloaded(preloaded: Path, role: str) -> None:
    assert delivery.preload_state(preloaded, role) == delivery.Preloaded()


@pytest.mark.parametrize("role", ROLES)
def test_the_delivered_state_reads_as_not_preloaded(preloaded: Path, role: str) -> None:
    assert _run(preloaded, "delivered") == 0

    assert delivery.preload_state(preloaded, role) == delivery.NotPreloaded()


@pytest.mark.parametrize("role", ROLES)
def test_the_delivered_state_drops_only_the_refactoring_preload(preloaded: Path, role: str) -> None:
    before = _preloaded_skills(preloaded, role)

    _run(preloaded, "delivered")

    assert SKILL in before
    assert _preloaded_skills(preloaded, role) == [s for s in before if s != SKILL]


# -- Reversal and idempotence ------------------------------------------------------------------


def test_moving_to_delivered_and_back_restores_the_bytes(preloaded: Path) -> None:
    original = _snapshot(preloaded)

    assert _run(preloaded, "delivered") == 0
    assert _snapshot(preloaded) != original
    assert _run(preloaded, "preloaded") == 0

    assert _snapshot(preloaded) == original


@pytest.mark.parametrize("state", move.STATES)
def test_applying_a_state_already_held_changes_nothing(preloaded: Path, state: str) -> None:
    _run(preloaded, state)
    held = _snapshot(preloaded)

    assert _run(preloaded, state) == 0

    assert _snapshot(preloaded) == held


def test_applying_reports_each_definition_it_moved_and_a_held_state_as_held(
    preloaded: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _run(preloaded, "delivered")
    moved_report = capsys.readouterr().out.splitlines()

    _run(preloaded, "delivered")
    held_report = capsys.readouterr().out.splitlines()

    assert moved_report == [
        "refactoring-move: moved agents/implementer.md to delivered",
        "refactoring-move: moved agents/test-engineer.md to delivered",
    ]
    assert held_report == ["refactoring-move: already delivered"]


# -- --check -----------------------------------------------------------------------------------


def test_check_exits_1_when_the_state_differs_and_writes_nothing(
    preloaded: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    original = _snapshot(preloaded)

    assert _run(preloaded, "delivered", "--check") == 1

    assert _snapshot(preloaded) == original
    assert capsys.readouterr().out.splitlines() == [
        "refactoring-move: agents/implementer.md does not hold the delivered state",
        "refactoring-move: agents/test-engineer.md does not hold the delivered state",
    ]


def test_check_exits_0_when_the_state_holds(preloaded: Path) -> None:
    assert _run(preloaded, "preloaded", "--check") == 0
    _run(preloaded, "delivered")

    assert _run(preloaded, "delivered", "--check") == 0


# -- Drift -------------------------------------------------------------------------------------

# Each move starts from the state opposite to its target, so it has work to do at every site.
MOVES = (("preloaded", "delivered"), ("delivered", "preloaded"))
SITE_AND_MOVE = [
    pytest.param(site, start, to, id=f"{site.definition.split('/')[1]}-{site.name}-to-{to}")
    for site in move.SITES
    for start, to in MOVES
]
# The inserted passage is what marks a Codex site, so a rename of a site's label cannot empty these.
CODEX_SITES = [site for site in move.SITES if site.inserted_trace is not None]
CODEX_SITE_AND_TARGET = [
    pytest.param(site, to, id=f"{site.definition.split('/')[1]}-to-{to}")
    for site in CODEX_SITES
    for to in move.STATES
]


def test_the_parametrized_site_cases_are_not_empty() -> None:
    assert {site.definition for site in CODEX_SITES} == {move.IMPLEMENTER, move.TEST_ENGINEER}
    assert len(CODEX_SITE_AND_TARGET) == len(CODEX_SITES) * len(move.STATES)
    assert len(SITE_AND_MOVE) == len(move.SITES) * len(MOVES)


@pytest.mark.parametrize(("site", "start", "to"), SITE_AND_MOVE)
def test_a_drifted_site_is_refused_by_name_and_nothing_is_written(
    preloaded: Path, capsys: pytest.CaptureFixture[str], site: move.Site, start: str, to: str
) -> None:
    _run(preloaded, start)
    _edit(preloaded / site.definition, site.text(start), "edited elsewhere")
    before = _snapshot(preloaded)

    assert _run(preloaded, to) == 1

    assert _snapshot(preloaded) == before
    assert capsys.readouterr().err.splitlines() == [
        f"refactoring-move: DRIFT -- {site.definition} ({site.name}): "
        "the preloaded text is found 0 times; the delivered text is found 0 times"
    ]


@pytest.mark.parametrize(("site", "to"), CODEX_SITE_AND_TARGET)
def test_a_reworded_codex_passage_is_drift_in_either_direction(
    preloaded: Path, capsys: pytest.CaptureFixture[str], site: move.Site, to: str
) -> None:
    _run(preloaded, "delivered")
    _edit(preloaded / site.definition, "is verified against", "is checked against")
    before = _snapshot(preloaded)

    assert _run(preloaded, to) == 1

    assert _snapshot(preloaded) == before
    assert capsys.readouterr().err.splitlines() == [
        f"refactoring-move: DRIFT -- {site.definition} ({site.name}): "
        "the preloaded text is followed by a passage that was reworded; "
        "the delivered text is found 0 times"
    ]


def test_a_text_found_twice_is_drift_not_a_guess(
    preloaded: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    site = move.SITES[0]
    _edit(preloaded / site.definition, site.preloaded, f"{site.preloaded}\n{site.preloaded}")

    assert _run(preloaded, "delivered") == 1

    assert capsys.readouterr().err.splitlines() == [
        f"refactoring-move: DRIFT -- {site.definition} ({site.name}): "
        "the preloaded text is found 2 times; the delivered text is found 0 times"
    ]


def test_a_site_holding_both_states_is_drift_with_a_reason() -> None:
    site = move.Site("agents/x.md", "same", "one text", "one text")

    assert site.drift("one text") == "the preloaded and the delivered text are both found"


def test_every_drifted_site_is_named_in_one_run(
    preloaded: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _edit(_definition(preloaded, "implementer"), "skills: [software", "skills: [x, software")
    _edit(_definition(preloaded, "test-engineer"), "skills: [software", "skills: [x, software")

    assert _run(preloaded, "delivered") == 1

    err = capsys.readouterr().err
    assert "agents/implementer.md (skills list)" in err
    assert "agents/test-engineer.md (skills list)" in err


# -- Usage errors ------------------------------------------------------------------------------


@pytest.mark.parametrize("argv", [[], ["--to", "elsewhere"], ["--to"], ["--unknown"]])
def test_a_malformed_command_line_exits_2(argv: list[str]) -> None:
    with pytest.raises(SystemExit) as exit_info:
        move.main(argv)

    assert exit_info.value.code == 2


def test_a_root_without_the_definitions_is_a_usage_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert _run(tmp_path, "delivered") == 2

    assert capsys.readouterr().err.startswith("refactoring-move: ERROR -- ")


def test_the_default_root_is_the_git_toplevel(
    preloaded: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(move, "git_toplevel_from_cwd", lambda: preloaded)

    assert move.main(["--to", "delivered"]) == 0

    assert delivery.preload_state(preloaded, "implementer") == delivery.NotPreloaded()


def test_no_root_and_no_git_repository_is_a_usage_error_not_a_guess(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(move, "git_toplevel_from_cwd", lambda: None)

    assert move.main(["--to", "delivered"]) == 2

    assert capsys.readouterr().err.splitlines() == [
        "refactoring-move: ERROR -- no --root given and the working directory is not in a git "
        "repository"
    ]


def test_an_installed_plugin_cache_is_never_moved(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    cache = tmp_path / "plugins" / "cache" / "owner" / "praxion" / "1.0.0"
    cache.mkdir(parents=True)

    assert _run(cache, "delivered") == 2

    assert "plugin cache" in capsys.readouterr().err


def test_a_definition_that_cannot_be_written_is_a_usage_error_naming_it(
    preloaded: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    write_bytes = Path.write_bytes

    def write_unless_test_engineer(self: Path, data: bytes) -> int:
        if self.name == "test-engineer.md":
            raise PermissionError("read-only")
        return write_bytes(self, data)

    monkeypatch.setattr(Path, "write_bytes", write_unless_test_engineer)

    assert _run(preloaded, "delivered") == 2

    assert "cannot write agents/test-engineer.md" in capsys.readouterr().err


def _fail_the_first_write_of(monkeypatch: pytest.MonkeyPatch, definition: str) -> None:
    write_bytes = Path.write_bytes
    failed = []

    def write(self: Path, data: bytes) -> int:
        if self.name == definition and not failed:
            failed.append(self.name)
            raise PermissionError("read-only")
        return write_bytes(self, data)

    monkeypatch.setattr(Path, "write_bytes", write)


def test_a_failed_second_write_puts_the_first_definition_back(
    preloaded: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    original = _snapshot(preloaded)
    _fail_the_first_write_of(monkeypatch, "test-engineer.md")

    assert _run(preloaded, "delivered") == 2

    captured = capsys.readouterr()
    assert _snapshot(preloaded) == original
    assert captured.out == ""
    assert captured.err.splitlines() == [
        "refactoring-move: ERROR -- cannot write agents/test-engineer.md: read-only"
    ]


def test_a_definition_that_cannot_be_put_back_is_named_beside_the_failed_write(
    preloaded: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    write_bytes = Path.write_bytes
    writes: list[str] = []

    def write(self: Path, data: bytes) -> int:
        writes.append(self.name)
        if self.name == "test-engineer.md" or writes.count("implementer.md") > 1:
            raise PermissionError("read-only")
        return write_bytes(self, data)

    monkeypatch.setattr(Path, "write_bytes", write)

    assert _run(preloaded, "delivered") == 2

    assert capsys.readouterr().err.splitlines() == [
        "refactoring-move: ERROR -- cannot write agents/test-engineer.md: read-only "
        "(and could not restore agents/implementer.md)"
    ]


def test_every_definition_that_cannot_be_put_back_is_named(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    names = ["agents/a.md", "agents/b.md"]
    monkeypatch.setattr(Path, "write_bytes", _always_read_only)

    note = move._restore(tmp_path, names, dict.fromkeys(names, ""))

    assert note == " (and could not restore agents/a.md, agents/b.md)"


def _always_read_only(self: Path, data: bytes) -> int:
    raise PermissionError("read-only")


def test_the_move_is_applied_to_the_git_toplevel_found_by_git_itself(
    preloaded: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    for name in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE"):
        monkeypatch.delenv(name, raising=False)
    subprocess.run(["git", "init", "-q", str(preloaded)], check=True)
    monkeypatch.chdir(preloaded / "agents")

    assert move.main(["--to", "delivered"]) == 0

    assert delivery.preload_state(preloaded, "implementer") == delivery.NotPreloaded()
    assert delivery.preload_state(preloaded, "test-engineer") == delivery.NotPreloaded()


# -- What the move writes ----------------------------------------------------------------------

# Every registered pipeline artifact, a placeholder name by its fixed prefix.
_PIPELINE_FILES = "|".join(
    re.escape(name.split("<")[0]) for name in sorted(artifact_registry.all_names())
)
_EPHEMERAL = re.compile(
    rf"\bdec-\d+|\bdec-draft|\bREQ-\d+|\bAC-\d+|\bStep \d+|\.ai-work|\b(?:{_PIPELINE_FILES})"
)


@pytest.mark.parametrize("state", move.STATES)
@pytest.mark.parametrize("site", move.SITES, ids=lambda s: f"{s.definition}-{s.name}")
def test_the_texts_of_both_states_cite_no_decision_number_or_pipeline_file(
    site: move.Site, state: str
) -> None:
    assert _EPHEMERAL.search(site.text(state)) is None


def test_the_phase_tag_sentence_is_state_neutral_wording() -> None:
    (site,) = [s for s in move.SITES if s.name == "phase-tag sentence"]

    assert "always-loaded" in site.preloaded
    assert "always-loaded" not in site.delivered
    assert "preloaded by your frontmatter or delivered with the delegation" in site.delivered


# -- The Codex passage -------------------------------------------------------------------------


@pytest.mark.parametrize("role", ROLES)
def test_the_delivered_state_marks_one_codex_passage_naming_the_marker_and_the_skill(
    preloaded: Path, role: str
) -> None:
    named = [p for p in _wrapper_passages(preloaded, role) if "skills/refactoring/SKILL.md" in p]
    assert named == []

    _run(preloaded, "delivered")

    (passage,) = [p for p in _wrapper_passages(preloaded, role) if "[Phase: Refactoring]" in p]
    assert "skills/refactoring/SKILL.md" in passage
    assert "not already in your context" in passage


@pytest.mark.parametrize("site", CODEX_SITES, ids=str)
def test_the_codex_passage_stands_in_its_own_paragraph_after_its_anchor(
    preloaded: Path, site: move.Site
) -> None:
    _run(preloaded, "delivered")

    text = (preloaded / site.definition).read_text(encoding="utf-8")

    assert f"{site.preloaded}\n\n<!-- codex-wrapper:begin -->\nA step whose" in text
    assert "the step.\n<!-- codex-wrapper:end -->\n" in text
