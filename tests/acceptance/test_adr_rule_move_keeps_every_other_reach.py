"""Moving the ADR rule changes no other reach: kernels, drift checks, Codex, Cursor, the docs.

The drift checks pass on the shipped tree, the role kernels and their index are the base's, and
the kernel check still holds the moved rule to classification: an unclassified section added to
it, or a resident line that is not a line of it, is reported. The Codex bridge keeps the rule
always-on with the base's pointer text and exports no resident rule; the Cursor export is the
base's. No always-loaded file or catalog doc says the rule loads in full at session start.

The base observations were frozen before the change (`adr_rule_move`).
"""

from __future__ import annotations

import re

import pytest

from tests.acceptance.drivers import adr_rule_move as move
from tests.acceptance.drivers import kernel_sandbox, shipped_texts

DRIFT_CHECKS = (
    ["scripts/regenerate_rules_manifest.py", "--check"],
    ["scripts/generate_kernels.py", "--check"],
    ["scripts/check_kernel_manifest.py"],
    ["scripts/sync_canonical_blocks.py", "--check"],
)
READER_TEXTS = (
    "CLAUDE.md",
    "rules/README.md",
    "docs/rules-taxonomy.md",
    "claude/config/praxion-rules.yaml.example",
    "README_DEV.md",
    "skills/rule-crafting/SKILL.md",
)
FULL_AT_START = re.compile(r"always[- ](?:on|loaded)|at session start|every session", re.I)
NAMES_THE_RULE = re.compile(r"adr[- ]conventions", re.I)
NAMES_THE_NEW_DELIVERY = re.compile(r"\.ai-state/decisions|resident|codex|path[- ]scoped", re.I)


# -- Drift checks and kernels ---------------------------------------------------------------------


@pytest.mark.parametrize("argv", DRIFT_CHECKS, ids=lambda argv: argv[0].split("/")[-1])
def test_the_drift_check_passes_on_the_shipped_tree(tmp_path, argv):
    result = move.run_check(argv, tmp_path)

    assert result.returncode == 0, (result.stdout + result.stderr)[-2000:]


def test_the_generated_role_kernels_and_their_index_are_the_bases():
    assert move.kernel_digests() == move.fixture_json("base_kernels.json")


@pytest.fixture
def sandbox(tmp_path) -> kernel_sandbox.Sandbox:
    template = kernel_sandbox.build_template(tmp_path)
    return kernel_sandbox.new_sandbox(template, tmp_path / "plugin")


def _kernel_check(sandbox: kernel_sandbox.Sandbox):
    argv = ["scripts/check_kernel_manifest.py", "--repo-root", str(sandbox.root)]
    return move.run_check(argv, sandbox.scratch, sandbox.root)


def test_an_unclassified_section_added_to_the_moved_rule_is_reported(sandbox):
    sandbox.append(move.MOVED_RULE, "### Unclassified Addition\n\nA section no entry classifies.")

    result = _kernel_check(sandbox)

    assert result.returncode != 0
    assert "Unclassified Addition" in result.stdout + result.stderr


def test_a_resident_line_that_is_no_line_of_the_moved_rule_is_reported(sandbox):
    assert sandbox.path(move.RESIDENT).is_file(), f"{move.RESIDENT} does not ship"
    sandbox.append(move.RESIDENT, "Decision records may be numbered by hand at any time.")

    result = _kernel_check(sandbox)

    assert result.returncode != 0
    assert "numbered by hand" in result.stdout + result.stderr


# -- Codex and Cursor -----------------------------------------------------------------------------


@pytest.fixture(scope="module")
def codex(tmp_path_factory) -> dict:
    return move.codex_reach(tmp_path_factory.mktemp("codex"))


def test_the_codex_bridge_keeps_the_bases_always_on_rule_set(codex):
    assert codex["always_on"] == move.fixture_json("base_codex.json")["always_on"]
    assert move.CODEX_RULE_ID in codex["always_on"]


def test_the_codex_bridge_keeps_the_bases_session_start_pointer_text(codex):
    assert codex["pointer"] == move.fixture_json("base_codex.json")["pointer"]


def test_the_codex_bridge_exports_no_rule_for_the_resident_file(codex):
    assert move.RESIDENT not in codex["rule_paths"]


def test_the_cursor_export_is_the_bases_byte_for_byte(tmp_path):
    assert move.cursor_digests(tmp_path) == move.fixture_json("base_cursor.json")


# -- What readers are told ------------------------------------------------------------------------


def _stale_statements(text: str) -> list[str]:
    return [
        s
        for s in shipped_texts.sentences(shipped_texts.normalize(text))
        if NAMES_THE_RULE.search(s)
        and FULL_AT_START.search(s)
        and not NAMES_THE_NEW_DELIVERY.search(s)
    ]


@pytest.mark.parametrize("relpath", READER_TEXTS)
def test_no_reader_text_says_the_rule_loads_in_full_at_session_start(relpath):
    assert _stale_statements(shipped_texts.read(relpath)) == []


@pytest.mark.parametrize("relpath", READER_TEXTS)
def test_each_reader_text_names_the_rules_path_scope_and_its_resident(relpath):
    text = shipped_texts.read(relpath)

    assert move.PATH_SCOPE in text, f"{relpath} does not name {move.PATH_SCOPE}"
    assert "adr-conventions-resident" in text, f"{relpath} does not name the resident file"
