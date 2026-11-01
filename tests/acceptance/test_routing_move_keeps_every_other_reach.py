"""Moving the routing table changes no other reach: Codex, Cursor, the gates, the readers, the evals.

The Codex pipeline adapter still exports the base's tier routes; the Codex rules bridge exports no
rule for the session-start routing text and keeps the routing rule excluded, its entry differing
only by the path scope; the Cursor export is the base's but for the routing rule's restated
directive. The gates pass on the shipped tree and still bite on a disagreeing tier row, an
unclassified section of the rule and a session-start routing line that is no line of the rule.
No reader text still says the rule loads whole at session start, and the eval probes still probe
a rule the session-start injection delivers.

The base observations were frozen before the change (`model_routing_move`).
"""

from __future__ import annotations

import re

import pytest

from tests.acceptance.drivers import kernel_sandbox, shipped_texts
from tests.acceptance.drivers import model_routing_move as move

REPO = move.REPO_ROOT
GATES = (
    ["scripts/check_model_routing_parity.py"],
    ["scripts/regenerate_rules_manifest.py", "--check"],
    ["scripts/check_kernel_manifest.py"],
    ["scripts/generate_kernels.py", "--check"],
    ["scripts/sync_canonical_blocks.py", "--check"],
)
READER_TEXTS = (
    "CLAUDE.md",
    "rules/README.md",
    "docs/rules-taxonomy.md",
    "claude/config/praxion-rules.yaml.example",
    ".claude/praxion-rules.yaml",
    move.HACKATHON_PRESET,
    "README_DEV.md",
    "skills/agent-crafting/SKILL.md",
    move.POLICY_REFERENCE,
)
# The reader texts that described the rule's delivery at the base.
DELIVERY_DESCRIBERS = (
    "CLAUDE.md",
    "docs/rules-taxonomy.md",
    ".claude/praxion-rules.yaml",
    "README_DEV.md",
    "skills/agent-crafting/SKILL.md",
    move.POLICY_REFERENCE,
)
NAMES_THE_RULE = re.compile(r"agent[- ]model[- ]routing|model routing|tier table", re.I)
WHOLE_AT_START = re.compile(
    r"always[- ](?:on|loaded)|at session[- ]start|every session|hook[- ]deliver\w*"
    r"|additionalContext|SessionStart|resident|kept loaded",
    re.I,
)
NAMES_THE_NEW_DELIVERY = re.compile(
    r"agents/\*\*|path[- ]scop\w*|session[- ]start (?:routing )?text", re.I
)
QUOTED_INJECTION_OUTPUT = re.compile(r"\[inject_rules\]|suppressed:")
PATH_SCOPE_KEYS = {"path_globs", "scope", "keywords"}


# -- The Codex pipeline adapter -------------------------------------------------------------------


def test_the_codex_adapters_exports_equal_the_bases_once_the_root_is_normalised(tmp_path):
    assert move.adapter_exports(tmp_path) == move.fixture_json("base_adapter.json")


# -- The Codex rules bridge -----------------------------------------------------------------------


@pytest.fixture(scope="module")
def bridge(tmp_path_factory) -> dict:
    return move.bridge_reach(tmp_path_factory.mktemp("bridge"))


@pytest.mark.parametrize("key", ["always_on", "portable_always_on", "path_scoped", "pointer"])
def test_the_codex_bridge_keeps_the_bases_rule_sets_and_pointer_text(bridge, key):
    assert bridge[key] == move.fixture_json("base_bridge.json")[key]


def test_the_codex_bridge_exports_no_rule_for_the_session_start_routing_text(bridge):
    assert bridge["rule_paths"] == move.fixture_json("base_bridge.json")["rule_paths"]


def test_the_codex_bridge_keeps_the_routing_rule_excluded_from_codex(bridge):
    assert (bridge["routing_entry"] or {}).get("codex_load") == "exclude", bridge["routing_entry"]


def test_the_routing_rules_bridge_entry_differs_from_the_bases_only_by_its_path_scope(bridge):
    base = move.fixture_json("base_bridge.json")["routing_entry"]
    shipped = bridge["routing_entry"] or {}

    differing = move.routing_entry_difference(base, shipped)
    globs = " ".join(shipped.get("path_globs") or [])
    foreign_keywords = [
        k for k in set(shipped.get("keywords", [])) - set(base["keywords"]) if k not in globs
    ]

    assert set(differing) <= PATH_SCOPE_KEYS, differing
    assert move.AGENTS_SCOPE in (shipped.get("path_globs") or []), shipped.get("path_globs")
    assert foreign_keywords == [], f"keywords not drawn from the path scope: {foreign_keywords}"


# -- The Cursor export ----------------------------------------------------------------------------


@pytest.fixture(scope="module")
def cursor(tmp_path_factory) -> dict[str, bytes]:
    return move.cursor_export(tmp_path_factory.mktemp("cursor"))


def test_the_cursor_export_writes_the_bases_set_of_files(cursor):
    assert sorted(cursor) == sorted(move.fixture_json("base_cursor.json"))


def test_every_cursor_file_but_the_routing_rules_is_the_bases_byte_for_byte(cursor):
    base = move.fixture_json("base_cursor.json")

    changed = sorted(
        rel
        for rel, data in cursor.items()
        if rel != move.CURSOR_RULE and move.digest(data) != base.get(rel)
    )

    assert changed == []


def test_the_routing_rules_cursor_file_differs_only_by_the_restated_directive(cursor):
    before = move.paragraphs(move.fixture_text("base_cursor_rule.md"))
    after = move.paragraphs(cursor[move.CURSOR_RULE].decode("utf-8"))

    dropped, added = move.replaced_paragraphs(before, after)

    assert [p[: len(move.DIRECTIVE_OPENING)] for p in dropped] == [move.DIRECTIVE_OPENING], dropped
    assert added, "the directive paragraph was removed, not restated"


# -- The gates ------------------------------------------------------------------------------------


@pytest.mark.parametrize("argv", GATES, ids=lambda argv: argv[0].split("/")[-1])
def test_the_gate_passes_on_the_shipped_tree(tmp_path, argv):
    result = move.run_check(argv, tmp_path)

    assert result.returncode == 0, (result.stdout + result.stderr)[-2000:]


def test_the_generated_role_kernels_and_their_index_are_the_bases():
    assert move.kernel_digests() == move.fixture_json("base_kernels.json")


@pytest.fixture
def sandbox(tmp_path) -> kernel_sandbox.Sandbox:
    return kernel_sandbox.new_sandbox(kernel_sandbox.build_template(tmp_path), tmp_path / "plugin")


def _gate(argv: list[str], sandbox: kernel_sandbox.Sandbox):
    return move.run_check([*argv, "--repo-root", str(sandbox.root)], sandbox.scratch, sandbox.root)


def test_the_parity_gate_reports_a_tier_row_that_disagrees_with_its_definition(sandbox):
    sandbox.replace(move.RULE, "| `sentinel` | M | `sonnet` |", "| `sentinel` | M | `opus` |")

    result = _gate(["scripts/check_model_routing_parity.py"], sandbox)

    assert result.returncode == 1, result.stdout + result.stderr
    assert "sentinel" in result.stdout + result.stderr


def test_the_kernel_gate_reports_an_unclassified_section_added_to_the_routing_rule(sandbox):
    sandbox.append(move.RULE, "### Unclassified Routing Addition\n\nA section no entry classifies.")

    result = _gate(["scripts/check_kernel_manifest.py"], sandbox)

    assert result.returncode != 0
    assert "Unclassified Routing Addition" in result.stdout + result.stderr


def test_the_kernel_gate_reports_a_session_start_routing_line_that_is_no_line_of_the_rule(
    sandbox, tmp_path
):
    resident = move.session_start_routing_file(tmp_path / "reading")
    assert resident is not None, "the always-loaded reading counts no session-start routing text"
    assert sandbox.path(resident).is_file(), f"{resident} is not in the plugin checkout under test"
    sandbox.append(resident, "Spawns may pass any model they like at any time.")

    result = _gate(["scripts/check_kernel_manifest.py"], sandbox)

    assert result.returncode != 0
    assert "any model they like" in result.stdout + result.stderr


# -- What readers are told ------------------------------------------------------------------------


def _stale_statements(text: str) -> list[str]:
    return [
        s
        for s in shipped_texts.sentences(shipped_texts.normalize(text))
        if NAMES_THE_RULE.search(s)
        and WHOLE_AT_START.search(s)
        and not NAMES_THE_NEW_DELIVERY.search(s)
        and not QUOTED_INJECTION_OUTPUT.search(s)
    ]


@pytest.mark.parametrize("relpath", READER_TEXTS)
def test_no_reader_text_says_the_routing_rule_loads_whole_at_session_start(relpath):
    assert _stale_statements(shipped_texts.read(relpath)) == []


@pytest.mark.parametrize("relpath", DELIVERY_DESCRIBERS)
def test_each_reader_text_that_told_the_delivery_names_the_path_scope_and_the_session_start_text(
    relpath,
):
    text = shipped_texts.read(relpath)

    naming_start = shipped_texts.sentences_matching(
        text, NAMES_THE_RULE.pattern, r"session[- ]start"
    )

    assert move.AGENTS_SCOPE in text, f"{relpath} does not name the {move.AGENTS_SCOPE} path scope"
    assert naming_start, f"{relpath} does not name the routing rule's session-start text"


# -- The eval probes ------------------------------------------------------------------------------


def test_the_live_evals_hook_delivered_example_still_arrives_by_the_session_start_injection(
    sandbox, tmp_path
):
    rule = move.materializer_hook_delivered_rule()
    sandbox.append(rule, "Nonce line PRXLIVE-routing-move-probe.")

    injection = move.session_start(tmp_path / "session", plugin_root=sandbox.root)

    assert "PRXLIVE-routing-move-probe" in injection.context, (
        f"{rule} is not delivered at session start"
    )


def test_the_inheritance_probes_heading_arrives_only_by_the_session_start_injection(tmp_path):
    heading = move.inheritance_probe_heading()
    linked_always_on = [
        row["path"]
        for row in move.manifest_rows().values()
        if row.get("install") == "symlink" and not row.get("paths")
    ]

    injection = move.session_start(tmp_path)
    carriers = [
        p
        for p in linked_always_on
        if heading in (REPO / p).read_text(encoding="utf-8").splitlines()
    ]

    assert heading in injection.context.splitlines(), (
        f"{heading!r} does not arrive at session start"
    )
    assert carriers == [], (
        f"linked always-on rules carry {heading!r}, so subagents inherit it: {carriers}"
    )
