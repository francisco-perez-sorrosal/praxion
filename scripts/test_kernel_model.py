"""Tests for kernel_model.py -- the manifest, the ledger and the index as legal values.

Each illegal shape is one case that must be refused by name; each legal scope and form is
one case that must parse to the value it means. Totality, pins and group coherence run
over synthetic sources, so no test depends on what the repository's rules say today; the
two checks against the live repository (the agent definitions) pin the heuristics that
read prose.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import kernel_model as km  # noqa: E402
import kernel_sources as ks  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent

AGENTS = frozenset(
    {
        "researcher",
        "verifier",
        "sentinel",
        "architect-validator",
        "systems-architect",
        "implementation-planner",
        "interface-designer",
        "agentic-transactions-architect",
        "context-engineer",
        "discipline-consultant",
        "skill-genesis",
        "implementer",
    }
)
SOURCE = "rules/a.md"
SOURCE_TEXT = "## Alpha\n\nAlpha body.\n\n## Beta\n\nBeta body.\n"
SECTIONS = {SOURCE: ks.split_sections(SOURCE, SOURCE_TEXT)}
ALPHA_SHA = SECTIONS[SOURCE][0].sha


# -- Builders: the wire shapes ---------------------------------------------------


def entry(**fields: object) -> dict:
    row = {
        "source": SOURCE,
        "heading": "Alpha",
        "part": None,
        "scope": "core",
        "form": "verbatim",
        "text": None,
        "pin": None,
        "agents": [],
        "groups": [],
        "reason": None,
    }
    return {**row, **fields}


def authored(pin: str | None = ALPHA_SHA) -> dict:
    return {
        "id": "alpha-short",
        "path": "claude/kernels/src/alpha-short.md",
        "module": "core",
        "condenses": f"{SOURCE}#Alpha",
        "pinned_sha": pin,
    }


def manifest(*entries: dict, **extra: object) -> dict:
    return {
        "version": 1,
        "groups": {"adr-author": ["systems-architect"], "ledger-writer": ["verifier"]},
        "modules": {},
        "authored": [],
        "entries": list(entries),
        **extra,
    }


def parse(*entries: dict, **extra: object) -> km.Manifest:
    return km.parse_manifest(manifest(*entries, **extra), AGENTS)


def refusal(*entries: dict, **extra: object) -> str:
    with pytest.raises(km.KernelModelError) as caught:
        parse(*entries, **extra)
    return str(caught.value)


# -- The version key -----------------------------------------------------------------


VERSIONED_READERS = {
    "manifest": lambda v: km.parse_manifest({"version": v}, AGENTS),
    "ledger": lambda v: km.parse_statuses({"version": v}),
    "index": lambda v: km.parse_index(
        {"schema": v, "slots": 1, "kernel_version": "x", "roles": {}}
    ),
}


@pytest.mark.parametrize("version", [None, 2, "1", True])
@pytest.mark.parametrize("reader", list(VERSIONED_READERS))
def test_an_unknown_version_is_refused_until_taught(reader: str, version: object) -> None:
    with pytest.raises(km.KernelModelError, match="not supported"):
        VERSIONED_READERS[reader](version)


# -- Illegal entry shapes ------------------------------------------------------------

ILLEGAL = {
    "an empty audience": (entry(scope=""), "empty audience"),
    "an unknown scope": (entry(scope="everyone", reason="x"), "unknown scope"),
    "a role entry naming no agent or group": (entry(scope="role"), "empty audience"),
    "an unknown agent": (entry(scope="role", agents=["no-such-agent"]), "unknown agent"),
    "an unknown group": (entry(scope="role", groups=["no-such-group"]), "unknown group"),
    "a core entry without a form": (entry(form=None), "form must be"),
    "a condensed form without a pin": (
        entry(form="condensed", text="alpha-short"),
        "without a pin",
    ),
    "an orchestrator-only entry without a reason": (
        entry(scope="orchestrator-only", reason=""),
        "gives no reason",
    ),
    "a no-actor entry without a reason": (entry(scope="no-actor"), "gives no reason"),
    "an orchestrator-only entry naming an agent": (
        entry(scope="orchestrator-only", reason="x", agents=["researcher"]),
        "has no actor to name",
    ),
    "a no-actor entry naming a group": (
        entry(scope="no-actor", reason="x", groups=["adr-author"]),
        "has no actor to name",
    ),
}


@pytest.mark.parametrize("shape", list(ILLEGAL))
def test_an_illegal_entry_shape_is_refused_naming_the_entry(shape: str) -> None:
    row, reason = ILLEGAL[shape]

    message = refusal(row)

    assert f"entry 1 ({SOURCE} 'Alpha')" in message
    assert reason in message


def test_a_condensed_text_without_a_pin_names_the_section_it_condenses() -> None:
    message = refusal(
        entry(form="condensed", text="alpha-short", pin=ALPHA_SHA),
        authored=[authored(pin=None)],
    )

    assert "(rules/a.md#Alpha) carries no pin" in message


def test_a_condensed_form_must_name_registered_text_with_the_same_pin() -> None:
    unregistered = entry(form="condensed", text="alpha-short", pin=ALPHA_SHA)
    assert "not registered" in refusal(unregistered)

    drifted = entry(form="condensed", text="alpha-short", pin="0" * 40)
    assert "differs" in refusal(drifted, authored=[authored()])


def test_a_group_with_no_members_is_refused_by_name() -> None:
    assert "group 'probe-group' has no members" in refusal(groups={"probe-group": []})


def test_a_group_must_name_known_agents_and_not_share_an_agents_name() -> None:
    assert "unknown agent 'ghost'" in refusal(groups={"g": ["ghost"]})
    assert "shares its name" in refusal(groups={"researcher": ["verifier"]})


@pytest.mark.parametrize(
    "rows",
    [
        [entry(), entry(scope="no-actor", reason="x")],
        [entry(part="Alpha body."), entry()],
        [entry(), entry(part="Alpha body.")],
        [entry(part="Alpha body."), entry(part="Alpha body.")],
    ],
    ids=["two whole", "part then whole", "whole then part", "same part twice"],
)
def test_two_entries_for_one_section_are_refused(rows: list[dict]) -> None:
    message = refusal(*rows)

    assert message.startswith("entry 2")
    assert "one audience per section" in message


def test_parts_of_one_section_with_distinct_prefixes_are_two_legal_entries() -> None:
    parsed = parse(
        entry(part="Alpha text:", scope="no-actor", reason="x"),
        entry(part="Beta text:", scope="orchestrator-only", reason="y"),
    )

    assert [getattr(e.target, "prefix", None) for e in parsed.entries] == [
        "Alpha text:",
        "Beta text:",
    ]


# -- Legal scopes, forms and modules -----------------------------------------------


def test_a_core_entry_with_a_verbatim_form_parses() -> None:
    parsed = parse(entry())

    assert parsed.entries[0] == km.AudienceEntry(
        km.SectionTarget(SOURCE, "Alpha"), km.Core(km.Verbatim())
    )


def test_a_condensed_form_carries_its_text_and_its_pin() -> None:
    parsed = parse(
        entry(form="condensed", text="alpha-short", pin=ALPHA_SHA), authored=[authored()]
    )

    assert parsed.entries[0].scope == km.Core(km.Condensed("alpha-short", ALPHA_SHA))
    assert parsed.authored[0].condenses == f"{SOURCE}#Alpha"


def test_a_role_entry_for_one_agent_is_served_by_a_module_of_that_name() -> None:
    parsed = parse(entry(scope="role", agents=["researcher"]))

    assert parsed.entries[0].scope == km.Role("researcher", km.Verbatim())
    assert parsed.modules["researcher"] == ("researcher",)


def test_a_role_entry_for_a_declared_group_parses() -> None:
    parsed = parse(entry(scope="role", groups=["adr-author"]))

    assert parsed.entries[0].scope == km.Role("adr-author", km.Verbatim())


def test_a_declared_module_serves_an_audience_of_several_agents() -> None:
    modules = {"principles-digest": {"audience": ["researcher", "verifier"]}}

    parsed = parse(entry(scope="role", agents=["verifier", "researcher"]), modules=modules)

    assert parsed.entries[0].scope == km.Role("principles-digest", km.Verbatim())


def test_a_condensed_role_entry_is_served_by_the_module_its_authored_text_lives_in() -> None:
    modules = {"first": {"audience": ["researcher"]}, "second": {"audience": ["researcher"]}}
    text = {**authored(), "module": "second"}

    parsed = parse(
        entry(
            scope="role", agents=["researcher"], form="condensed", text="alpha-short", pin=ALPHA_SHA
        ),
        authored=[text],
        modules=modules,
    )

    assert parsed.entries[0].scope == km.Role("second", km.Condensed("alpha-short", ALPHA_SHA))


def test_a_verbatim_role_entry_takes_the_first_of_several_modules_for_its_audience() -> None:
    modules = {"first": {"audience": ["researcher"]}, "second": {"audience": ["researcher"]}}

    parsed = parse(entry(scope="role", agents=["researcher"]), modules=modules)

    assert parsed.entries[0].scope == km.Role("first", km.Verbatim())


def test_several_agents_without_a_declared_module_are_refused() -> None:
    assert "no declared module serves" in refusal(
        entry(scope="role", agents=["verifier", "researcher"])
    )


def test_a_module_cannot_be_core_empty_or_name_unknown_audience() -> None:
    assert "core is implicit" in refusal(modules={"core": {"audience": ["researcher"]}})
    assert "core is implicit" in refusal(modules={"x": {"audience": []}})
    assert "unknown agent or group 'ghost'" in refusal(modules={"x": {"audience": ["ghost"]}})


def test_a_single_name_cannot_borrow_a_module_declared_for_another_audience() -> None:
    modules = {"researcher": {"audience": ["verifier"]}}

    assert "declared with another audience" in refusal(
        entry(scope="role", agents=["researcher"]), modules=modules
    )


@pytest.mark.parametrize(
    ("scope", "kind"),
    [("orchestrator-only", km.OrchestratorOnly), ("no-actor", km.NoActor)],
)
def test_a_resident_only_entry_keeps_its_reason_and_names_no_agent(scope: str, kind: type) -> None:
    parsed = parse(entry(scope=scope, reason="the main session acts on it"))

    assert parsed.entries[0].scope == kind("the main session acts on it")
    assert parsed.entries[0].form is None


# -- Kernel strings and the index --------------------------------------------------


def test_a_kernel_string_at_the_cap_is_legal_and_one_over_is_refused() -> None:
    at_cap = km.KernelString("researcher", 1, "core", None, "x" * km.MAX_STRING_CHARS)
    assert len(at_cap.text) == km.MAX_STRING_CHARS

    with pytest.raises(km.KernelModelError, match="10001 characters exceed the 10000 cap"):
        km.KernelString("researcher", 1, "core", None, "x" * (km.MAX_STRING_CHARS + 1))


def index_wire(**role: object) -> dict:
    body = {"status": "trial", "strings": ["core text"], **role}
    return {"schema": 1, "kernel_version": "abc", "slots": 3, "roles": {"researcher": body}}


def test_an_index_parses_into_role_kernels() -> None:
    index = km.parse_index(index_wire())

    assert (index.slots, index.kernel_version) == (3, "abc")
    assert index.roles["researcher"] == km.RoleKernel("trial", ("core text",))


@pytest.mark.parametrize(
    ("wire", "reason"),
    [
        (index_wire(strings=["x" * 10_001]), "exceed the 10000 cap"),
        (index_wire(status="adopted"), "is not trial, switched or held"),
        ({**index_wire(), "slots": 0}, "slots must be"),
        ({**index_wire(), "kernel_version": ""}, "kernel_version"),
    ],
    ids=["over the cap", "unknown status", "no slots", "no version"],
)
def test_an_illegal_index_is_refused(wire: dict, reason: str) -> None:
    with pytest.raises(km.KernelModelError, match=reason):
        km.parse_index(wire)


# -- Totality, orphans and pins ------------------------------------------------------


def total(*entries: dict, sections: dict | None = None, required: tuple = (SOURCE,)) -> list[str]:
    found = km.check_totality(parse(*entries), sections or SECTIONS, required)
    return [str(f) for f in found]


def classify(heading: str, **fields: object) -> dict:
    return entry(heading=heading, scope="no-actor", reason="x", **fields)


def test_every_section_classified_is_total() -> None:
    assert total(classify("Alpha"), classify("Beta")) == []


def test_an_unclassified_section_is_named() -> None:
    findings = total(classify("Alpha"))

    assert findings == [f"Finding(kind='unclassified', subject=\"{SOURCE} 'Beta'\", detail='')"]


def test_an_entry_for_a_renamed_heading_is_an_orphan_and_the_new_heading_unclassified() -> None:
    kinds = {
        (f.kind, f.subject)
        for f in km.check_totality(
            parse(classify("Alpha"), classify("Beta Old")), SECTIONS, (SOURCE,)
        )
    }

    assert kinds == {
        ("orphan", f"{SOURCE} 'Beta Old'"),
        ("unclassified", f"{SOURCE} 'Beta'"),
    }


def test_an_entry_for_a_missing_source_is_an_orphan() -> None:
    row = classify("Alpha", source="rules/gone.md")

    found = km.check_totality(parse(row), SECTIONS, ())

    assert [(f.kind, f.detail) for f in found] == [("orphan", "the source file does not exist")]


def test_a_source_outside_the_required_set_registers_only_what_it_contributes() -> None:
    assert total(classify("Alpha"), required=()) == []


def test_a_duplicate_heading_is_reported_not_guessed() -> None:
    twice = {SOURCE: ks.split_sections(SOURCE, SOURCE_TEXT + "\n## Alpha\n\nAgain.\n")}

    found = km.check_totality(parse(classify("Alpha"), classify("Beta")), twice, (SOURCE,))

    assert [f.kind for f in found] == ["duplicate-heading"]


MIXED = "## Mixed\n\nAlpha part: for the orchestrator.\n\nBeta part: for nobody.\n"


def mixed_sections() -> dict:
    return {SOURCE: ks.split_sections(SOURCE, MIXED)}


def part(prefix: str) -> dict:
    return classify("Mixed", part=prefix)


def test_a_mixed_section_with_every_part_classified_is_total() -> None:
    found = km.check_totality(
        parse(part("Alpha part:"), part("Beta part:")), mixed_sections(), (SOURCE,)
    )

    assert found == ()


def test_a_mixed_section_whose_leading_part_has_no_entry_is_unclassified() -> None:
    found = km.check_totality(parse(part("Beta part:")), mixed_sections(), (SOURCE,))

    assert [(f.kind, f.subject) for f in found] == [("unclassified", f"{SOURCE} 'Mixed'")]
    assert "Alpha part" in found[0].detail


def test_a_part_prefix_that_starts_no_line_is_an_orphan() -> None:
    found = km.check_totality(parse(part("Gamma part:")), mixed_sections(), (SOURCE,))

    assert [f.kind for f in found] == ["orphan"]
    assert "starts no line" in found[0].detail


def condensed_entry(**fields: object) -> dict:
    return entry(**{"form": "condensed", "text": "alpha-short", "pin": ALPHA_SHA, **fields})


def test_a_pin_that_matches_its_source_is_fresh() -> None:
    parsed = parse(condensed_entry(), authored=[authored()])

    assert km.stale_pins(parsed, SECTIONS) == ()


def test_a_source_changed_after_it_was_condensed_has_a_stale_pin() -> None:
    parsed = parse(condensed_entry(), authored=[authored()])
    reworded = {SOURCE: ks.split_sections(SOURCE, SOURCE_TEXT.replace("Alpha body", "New body"))}

    found = km.stale_pins(parsed, reworded)

    assert [(f.kind, f.subject) for f in found] == [("stale-pin", f"{SOURCE} 'Alpha'")]


def test_a_section_appended_after_a_condensed_one_leaves_its_pin_fresh() -> None:
    beta = SECTIONS[SOURCE][1]
    row = condensed_entry(heading="Beta", pin=beta.sha)
    parsed = parse(row, authored=[{**authored(pin=beta.sha), "condenses": f"{SOURCE}#Beta"}])
    appended = {SOURCE: ks.split_sections(SOURCE, SOURCE_TEXT + "\n## Gamma\n\nGamma body.\n")}

    assert km.stale_pins(parsed, appended) == ()


def test_the_pin_of_a_part_covers_that_part_only() -> None:
    last = ks.split_parts(mixed_sections()[SOURCE][0], ["Alpha part:", "Beta part:"])[1]
    row = condensed_entry(heading="Mixed", part="Beta part:", pin=last.sha)
    parsed = parse(
        classify("Mixed", part="Alpha part:"),
        {**row, "pin": last.sha},
        authored=[authored(pin=last.sha)],
    )
    edited_first = MIXED.replace("for the orchestrator", "for the main session")

    still_fresh = km.stale_pins(parsed, {SOURCE: ks.split_sections(SOURCE, edited_first)})
    edited_last = km.stale_pins(
        parsed, {SOURCE: ks.split_sections(SOURCE, MIXED.replace("for nobody", "for all"))}
    )

    assert still_fresh == ()
    assert [f.kind for f in edited_last] == ["stale-pin"]


# -- Group coherence -------------------------------------------------------------------

AUTHOR_LINE = "Create `.ai-state/decisions/drafts/<name>.md` for each decision.\n"
LEDGER_LINE = "Append a row to `.ai-state/TECH_DEBT_LEDGER.md` per finding.\n"
READ_ONLY = "Read `.ai-state/TECH_DEBT_LEDGER.md` and `.ai-state/decisions/drafts/` only.\n"


def test_groups_equal_to_what_definitions_say_have_no_findings() -> None:
    groups = {"adr-author": ("systems-architect",), "ledger-writer": ("verifier",)}
    definitions = {
        "systems-architect": AUTHOR_LINE,
        "verifier": LEDGER_LINE,
        "implementer": READ_ONLY,
    }

    assert km.group_coherence(groups, definitions) == ()


def test_an_agent_that_writes_but_is_not_a_member_is_reported() -> None:
    groups = {"adr-author": ("systems-architect",), "ledger-writer": ("verifier",)}
    definitions = {
        "systems-architect": AUTHOR_LINE,
        "verifier": LEDGER_LINE,
        "sentinel": LEDGER_LINE,
    }

    found = km.group_coherence(groups, definitions)

    assert [(f.kind, f.subject) for f in found] == [("group-missing", "group ledger-writer")]
    assert "sentinel" in found[0].detail


def test_a_member_whose_definition_does_not_write_is_reported() -> None:
    groups = {"adr-author": ("systems-architect", "implementer"), "ledger-writer": ("verifier",)}
    definitions = {
        "systems-architect": AUTHOR_LINE,
        "verifier": LEDGER_LINE,
        "implementer": READ_ONLY,
    }

    found = km.group_coherence(groups, definitions)

    assert [(f.kind, f.subject) for f in found] == [("group-extra", "group adr-author")]
    assert "implementer" in found[0].detail


def test_an_undeclared_group_leaves_every_writer_missing() -> None:
    found = km.group_coherence({}, {"verifier": LEDGER_LINE, "systems-architect": AUTHOR_LINE})

    assert sorted(f.subject for f in found) == ["group adr-author", "group ledger-writer"]


def test_the_agent_definitions_of_this_repository_write_in_the_groups_the_design_names() -> None:
    definitions = km.agent_definitions(REPO_ROOT)

    authors = {a for a, text in definitions.items() if km.writes_adr_drafts(text)}
    writers = {a for a, text in definitions.items() if km.appends_ledger_rows(text)}

    assert authors == {
        "systems-architect",
        "implementation-planner",
        "interface-designer",
        "agentic-transactions-architect",
    }
    assert writers == {"verifier", "sentinel", "architect-validator"}


def test_agent_definitions_are_files_whose_frontmatter_declares_a_name(tmp_path: Path) -> None:
    agents = tmp_path / "agents"
    agents.mkdir()
    (agents / "scout.md").write_text("---\nname: scout\ndescription: d\n---\nBody\n")
    (agents / "CLAUDE.md").write_text("# A guide with no frontmatter\n")
    (agents / "odd.md").write_text("---\ndescription: no name\n---\nBody\n")

    assert km.agent_definitions(tmp_path) == {
        "scout": "---\nname: scout\ndescription: d\n---\nBody\n"
    }


# -- The edge: files and the parser ---------------------------------------------------


def write(root: Path, relative: str, text: str) -> None:
    (root / relative).parent.mkdir(parents=True, exist_ok=True)
    (root / relative).write_text(text, encoding="utf-8")


def test_the_loaders_read_the_three_files_of_a_checkout(tmp_path: Path) -> None:
    write(
        tmp_path,
        km.MANIFEST_PATH,
        "version: 1\nentries:\n  - {source: a.md, heading: H, scope: no-actor, reason: r}\n",
    )
    write(
        tmp_path,
        km.LEDGER_PATH,
        "version: 1\nroles:\n  researcher: {status: trial, since: d, runs: []}\n",
    )
    write(tmp_path, km.INDEX_PATH, '{"schema": 1, "kernel_version": "k", "slots": 2, "roles": {}}')

    assert km.load_manifest(tmp_path, AGENTS).entries[0].scope == km.NoActor("r")
    assert dict(km.load_statuses(tmp_path)) == {"researcher": "trial"}
    index = km.load_index(tmp_path)
    assert index is not None
    assert index.slots == 2


def test_no_ledger_adopts_nobody_and_no_index_means_no_kernel(tmp_path: Path) -> None:
    assert km.load_statuses(tmp_path) == {}
    assert km.load_index(tmp_path) is None


def test_a_missing_manifest_is_refused_rather_than_read_as_empty(tmp_path: Path) -> None:
    with pytest.raises(km.KernelModelError, match="does not exist"):
        km.load_manifest(tmp_path, AGENTS)


@pytest.mark.parametrize(
    ("path", "text", "load"),
    [
        (km.MANIFEST_PATH, "version: [1\n", lambda r: km.load_manifest(r, AGENTS)),
        (km.LEDGER_PATH, "- a list\n", km.load_statuses),
        (km.INDEX_PATH, "{not json", km.load_index),
    ],
    ids=["bad yaml", "not a mapping", "bad json"],
)
def test_a_file_that_does_not_parse_is_refused_naming_it(tmp_path: Path, path, text, load) -> None:
    write(tmp_path, path, text)

    with pytest.raises(km.KernelModelError, match=Path(path).name):
        load(tmp_path)


def test_a_missing_yaml_parser_is_reported_naming_the_interpreter(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write(tmp_path, km.LEDGER_PATH, "version: 1\n")
    monkeypatch.setitem(sys.modules, "yaml", None)

    with pytest.raises(km.MissingParserError, match="PyYAML is required") as caught:
        km.load_statuses(tmp_path)

    assert sys.executable in str(caught.value)


def test_the_module_imports_and_parses_without_a_yaml_parser() -> None:
    script = (
        "import sys; sys.modules['yaml'] = None; sys.path.insert(0, sys.argv[1]);"
        "import kernel_model as km;"
        "print(km.parse_manifest({'version': 1}, []).entries)"
    )

    done = subprocess.run(
        [sys.executable, "-I", "-c", script, str(Path(__file__).parent)],
        capture_output=True,
        text=True,
        check=False,
    )

    assert done.returncode == 0, done.stderr
    assert done.stdout.strip() == "()"


def test_yaml_text_that_is_not_yaml_is_refused_naming_where_it_came_from() -> None:
    with pytest.raises(km.KernelModelError, match="the old ledger: not valid YAML"):
        km.parse_yaml("roles: [unclosed", "the old ledger")


def test_the_frontmatter_of_a_definition_is_read_as_yaml() -> None:
    definition = "---\nname: scout\n'quoted' : [a, b]\nflag : true\n---\nBody\n"

    assert km.frontmatter(definition, "agents/scout.md") == {
        "name": "scout",
        "quoted": ["a", "b"],
        "flag": True,
    }


def test_a_definition_without_frontmatter_declares_nothing() -> None:
    assert km.frontmatter("Body only\n", "agents/scout.md") == {}


def test_frontmatter_that_is_not_yaml_is_refused_naming_the_definition() -> None:
    with pytest.raises(km.KernelModelError, match="agents/scout.md: not valid YAML"):
        km.frontmatter("---\nname: [unclosed\n---\n", "agents/scout.md")
