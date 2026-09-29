"""Structural tests for the onboarding capability-ID vocabulary + defaults.

`skills/onboard-project/SKILL.md` is a Claude Code skill body — it cannot be
invoked from pytest. These tests validate the documented contract by parsing
the skill file structurally, matching the precedent set by
`tests/commands/test_onboard_ci_autofix_install.py`.

`SKILL.md` publishes the capability-ID -> phase-id mapping table (the
capability-ID flags are dec-346) and the Mode x Phase Matrix.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parents[2]
SKILL_FILE = REPO_ROOT / "skills" / "onboard-project" / "SKILL.md"
CLAUDE_MD_BLOCKS = REPO_ROOT / "skills" / "onboard-project" / "references" / "claude-md-blocks.md"
ONBOARD_SCRIPT = REPO_ROOT / "scripts" / "onboard-project"

# The nine capability ids the skill's mapping table publishes (dec-346).
CAPABILITY_IDS = (
    "core",
    "arch",
    "quality",
    "tests",
    "ci",
    "aac",
    "ml",
    "obsidian",
    "observability",
)

# Every phase id the skill's Mode x Phase Matrix enumerates.
MODE_PHASE_MATRIX_IDS = (
    "0",
    "0s",
    "0.5",
    "1",
    "2",
    "3",
    "4",
    "5",
    "5b",
    "5b.t",
    "6",
    "7",
    "8",
    "8b",
    "8c",
    "8d",
    "8e.1",
    "8e.2",
    "8e.3",
    "8e.4",
    "8e.5",
    "8e.6",
    "8e.7",
    "8e.8",
    "8e.9",
    "8e.10",
    "8e.11",
    "8e.12",
    "8e.13",
    "9",
)

# Two phase ids the vocabulary deliberately leaves unmapped -- they are
# mode-implied, not user-selectable.
_NOT_USER_SELECTABLE = ("0", "0s", "5b", "5b.t")


def _skill_body() -> str:
    """Return the full SKILL.md content (read lazily so collection succeeds)."""
    return SKILL_FILE.read_text(encoding="utf-8")


def _capability_table_section() -> str:
    """Return the capability-ID mapping table section, or '' if absent."""
    # Two-step extraction rather than one combined regex -- see the identical
    # note in test_onboard_gate_consolidation.py's `_gates_section()`:
    # MULTILINE `^`/`$` anchors and a DOTALL greedy `.*` before "Capability"
    # are mutually defeating in a single pattern.
    body = _skill_body()
    heading = re.search(r"^##\s*.*Capability.*$", body, re.MULTILINE)
    if not heading:
        return ""
    rest = body[heading.start() :]
    next_heading = re.search(r"\n##\s", rest)
    return rest[: next_heading.start()] if next_heading else rest


def test_capability_id_table_is_published_once_in_skill_md() -> None:
    section = _capability_table_section()
    assert section, (
        "SKILL.md must publish the capability-ID -> phase-id mapping table as "
        "the single join point between the user-facing and internal "
        "vocabularies (dec-345)"
    )
    for capability_id in CAPABILITY_IDS:
        assert re.search(rf"`{re.escape(capability_id)}`", section), (
            f"Capability table must list `{capability_id}` as a row"
        )


def test_obsidian_defaults_on_only_when_cli_and_marketplace_plugin_detected() -> None:
    section = _capability_table_section()
    assert section, "Capability table not documented yet"
    row_match = re.search(r"`obsidian`.*", section)
    assert row_match, "Capability table must have an `obsidian` row"
    row = row_match.group(0)
    assert re.search(r"claude.{0,20}cli", row, re.IGNORECASE), (
        "`obsidian`'s default derivation must require the `claude` CLI to be present"
    )
    assert re.search(r"obsidian-skills|marketplace", row, re.IGNORECASE), (
        "`obsidian`'s default derivation must require the "
        "obsidian@obsidian-skills marketplace plugin to be present"
    )


def test_ci_defaults_off_unless_profile_all() -> None:
    section = _capability_table_section()
    assert section, "Capability table not documented yet"
    row_match = re.search(r"`ci`.*", section)
    assert row_match, "Capability table must have a `ci` row"
    row = row_match.group(0)
    assert re.search(r"\boff\b", row, re.IGNORECASE), (
        "`ci` must default off -- it is the only capability with out-of-band "
        "prerequisites (two `gh secret set` calls)"
    )
    assert re.search(r"profile.{0,10}all", row, re.IGNORECASE), (
        "`ci` must document turning on only under `--profile all`"
    )


def test_ml_defaults_on_iff_ml_signals_detected() -> None:
    section = _capability_table_section()
    assert section, "Capability table not documented yet"
    row_match = re.search(r"`ml`.*", section)
    assert row_match, "Capability table must have an `ml` row"
    row = row_match.group(0)
    assert re.search(r"ml signals?", row, re.IGNORECASE), (
        "`ml`'s default derivation must be conditioned on detected ML signals"
    )


def test_capability_to_phase_mapping_is_a_total_function_over_the_matrix() -> None:
    """Every phase id in the Mode x Phase Matrix resolves to exactly one capability.

    A capability vocabulary that silently omits a phase id -- or double-maps
    one -- breaks the "single join point" invariant the plan requires
    (dec-345): the internal phase grammar and the user-facing
    surface must agree on a total, unambiguous mapping.
    """
    section = _capability_table_section()
    assert section, "Capability table not documented yet"

    # Build capability_id -> {phase ids it covers}, from each row's "Phases" cell.
    mapping: dict[str, set[str]] = {}
    for capability_id in CAPABILITY_IDS:
        row_match = re.search(rf"`{re.escape(capability_id)}`\s*\|([^\n]*)", section)
        assert row_match, f"Capability table must have a `{capability_id}` row"
        cell = row_match.group(1)
        ids_in_cell = {token.strip("` .") for token in re.split(r"[,\s]+", cell) if token.strip()}
        mapping[capability_id] = {i for i in ids_in_cell if re.fullmatch(r"[0-9][0-9a-z.]*", i)}

    covered: dict[str, list[str]] = {}
    for capability_id, phase_ids in mapping.items():
        for phase_id in phase_ids:
            covered.setdefault(phase_id, []).append(capability_id)

    selectable_ids = [pid for pid in MODE_PHASE_MATRIX_IDS if pid not in _NOT_USER_SELECTABLE]
    missing = [pid for pid in selectable_ids if pid not in covered]
    assert not missing, (
        f"Mode x Phase Matrix phase id(s) {missing} are not covered by any "
        "capability -- the capability->phase mapping must be a total function "
        "over every user-selectable phase id"
    )
    ambiguous = {pid: caps for pid, caps in covered.items() if len(caps) > 1}
    assert not ambiguous, (
        f"Phase id(s) mapped to more than one capability: {ambiguous} -- the "
        "mapping must be unambiguous (each phase belongs to exactly one capability)"
    )


def test_tests_defaults_on_in_new_mode_only_and_under_profile_all() -> None:
    section = _capability_table_section()
    row_match = re.search(r"`tests`.*", section)
    assert row_match, "Capability table must have a `tests` row"
    row = row_match.group(0)
    assert re.search(r"\bon\b[^|]*`new`", row, re.IGNORECASE), (
        "`tests` must default on in `new` mode"
    )
    assert re.search(r"\boff\b[^|]*`existing`", row, re.IGNORECASE), (
        "`tests` must default off in `existing` mode"
    )
    assert "--with tests" in row, "`tests` must name its `--with tests` opt-in"
    assert re.search(r"profile.{0,10}all", row, re.IGNORECASE), (
        "`tests` must be included under `--profile all`"
    )


# -- Project Essentials item 2: two fills, neither dangling ------------------


def _project_essentials_note() -> str:
    text = CLAUDE_MD_BLOCKS.read_text(encoding="utf-8")
    match = re.search(
        r"^## §Project Essentials Block\n(.*?)(?=^## §)", text, re.DOTALL | re.MULTILINE
    )
    assert match, "claude-md-blocks.md must carry a §Project Essentials Block section"
    return match.group(1)


def test_project_essentials_test_item_points_to_testing_when_tests_is_selected() -> None:
    note = _project_essentials_note()
    assert re.search(r"`tests` capability is selected[^.]*`<test command>`[^.]*## Testing", note), (
        "When `tests` is selected, item 2 (`<test command>`) must be filled with a "
        "pointer to the `## Testing` block"
    )


def test_project_essentials_test_item_keeps_the_detected_command_otherwise() -> None:
    note = _project_essentials_note()
    assert re.search(r"Otherwise fill it with the detected test command", note), (
        "Without `tests`, item 2 must keep today's detected-command fill"
    )


def test_testing_block_is_registered_but_not_refreshable() -> None:
    text = CLAUDE_MD_BLOCKS.read_text(encoding="utf-8")
    assert "<!-- canonical-source: claude/canonical-blocks/testing.md" in text
    assert re.search(r"```markdown\n## Testing\n", text), "the synced `## Testing` fence is missing"
    assert "never refreshed" in text


# -- scripts/onboard-project resolves the `tests` default per mode -----------

_ISOLATED_GIT_ENV = {
    "GIT_CONFIG_GLOBAL": os.devnull,
    "GIT_CONFIG_SYSTEM": os.devnull,
    "GIT_CONFIG_NOSYSTEM": "1",
}


def _resolved_capabilities(tmp_path: Path, cwd: Path, *args: str) -> set[str]:
    home = tmp_path / "home"
    plugins = home / ".claude" / "plugins"
    plugins.mkdir(parents=True, exist_ok=True)
    # The script refuses to onboard without an installed plugin entry.
    (plugins / "installed_plugins.json").write_text(
        json.dumps({"praxion@bit-agora": {"version": "test"}}), encoding="utf-8"
    )
    # ...and without a `claude` executable on PATH (absent on CI runners);
    # `--no-launch` never calls it, so a no-op stub is enough.
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    stub = bin_dir / "claude"
    stub.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
    stub.chmod(0o755)
    env = {
        **os.environ,
        "HOME": str(home),
        "PATH": f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}",
        **_ISOLATED_GIT_ENV,
    }
    result = subprocess.run(
        ["bash", str(ONBOARD_SCRIPT), "--no-launch", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=90,
        env=env,
    )
    match = re.search(r"^# Capabilities: (.*)$", result.stdout, re.MULTILINE)
    assert match, f"no resolved capability line (rc={result.returncode}):\n{result.stderr}"
    return set(match.group(1).split(","))


@pytest.fixture
def existing_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "existing"
    repo.mkdir()
    subprocess.run(
        ["git", "init", "-q", "."],
        cwd=repo,
        check=True,
        env={**os.environ, **_ISOLATED_GIT_ENV},
    )
    (repo / "README.md").write_text("existing project\n", encoding="utf-8")
    return repo


@pytest.mark.parametrize(
    ("args", "expect_tests"),
    [
        ((), False),
        (("--with", "tests"), True),
        (("--profile", "all"), True),
        (("--profile", "all", "--without", "tests"), False),
    ],
)
def test_existing_mode_tests_capability_is_opt_in(
    tmp_path: Path, existing_repo: Path, args: tuple[str, ...], expect_tests: bool
) -> None:
    capabilities = _resolved_capabilities(tmp_path, existing_repo, *args)
    assert ("tests" in capabilities) is expect_tests, capabilities


def test_new_mode_tests_capability_defaults_on(tmp_path: Path) -> None:
    capabilities = _resolved_capabilities(
        tmp_path, tmp_path, "fresh-app", "--yes", "--editor", "none"
    )
    assert "tests" in capabilities, capabilities
