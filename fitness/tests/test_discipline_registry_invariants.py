"""Extensibility + ledger-ordering fitness test: pure-function invariants and their canaries.

Cites: CLAUDE.md§Context Engineering (adding a discipline must stay a small,
data-only change -- a discipline name leaking into an always-loaded surface,
an unpopulated registry row, or an absent ledger passing silently would let
context drift accumulate one discipline at a time instead of being engineered
out at the source).

Per rules/swe/gate-liveness.md (CODE-kind gate -> canary, not golden-bad-case),
this file splits assertion *logic* from file *reading*: three pure helper
functions taking strings/paths as arguments, each paired with a canary test
proving it fails on a known-bad input. Following this repo's own precedent
(fitness/tests/test_meta_citation.py's `check_file_citation`, tested via
literal synthetic strings before any real file existed to test against), the
inputs here are literal strings and `tmp_path`-built fixtures -- never the
real `agents/discipline-consultant.md` or registry file.

A second layer, added once those real artifacts exist, wires the same pure
helpers against the shipped tree: the consultant agent file, the discipline
registry, `plugin.json`, and every always-loaded rule/CLAUDE.md surface. The
gate-liveness canary for that layer copies the *real* consultant description
into a `tmp_path`-scoped string with a synthetic discipline name appended,
proving the check bites on the shape the real file actually takes -- never by
mutating the committed file itself.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import yaml

# ---------------------------------------------------------------------------
# The seven registry-row fields, in column order.
# ---------------------------------------------------------------------------

REGISTRY_ROW_FIELDS: tuple[str, ...] = (
    "discipline",
    "fires-when",
    "binds-to",
    "challenge-obligations",
    "difficulty-hint",
    "attaches-to",
    "lens-collision",
)


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


def check_no_discipline_name_in_text(text: str, discipline_names: list[str]) -> str | None:
    """Return a failure string if any discipline_names appears (case-insensitively) in text.

    Adding a new discipline must never require touching a generic, always-loaded
    surface (an agent description, a paths:-less rule, a CLAUDE.md) -- each
    discipline name belongs only inside the data-only registry. This helper
    proves that boundary holds for a given piece of text.
    """
    lowered = text.lower()
    for name in discipline_names:
        if name.lower() in lowered:
            return f"discipline name {name!r} found in text"
    return None


def check_registry_row_shape(rows: list[dict[str, str]]) -> list[str]:
    """Return a failure string per row that leaves a registry field missing or blank.

    Every row must carry all seven registry columns (`discipline` through
    `lens-collision`) populated with non-empty content -- substance over
    structure: a field present but blank is as inert as one that is absent.
    """
    failures: list[str] = []
    for index, row in enumerate(rows):
        label = row.get("discipline") or f"row {index}"
        for field in REGISTRY_ROW_FIELDS:
            value = row.get(field, "")
            if not value.strip():
                failures.append(f"{label}: missing or empty field {field!r}")
    return failures


def check_ledger_exists_if_registry_has_rows(
    registry_rows: list[dict[str, str]], ledger_path: Path
) -> str | None:
    """Return a failure string if the registry has >=1 row but ledger_path is absent.

    The disposition ledger must exist before or in the same change as the
    first discipline's registry row, so a dismiss-rate count is derivable from
    day one rather than retrofitted once consultations have already run. An
    empty registry places no requirement on the ledger's existence.
    """
    if registry_rows and not ledger_path.exists():
        return f"registry has {len(registry_rows)} row(s) but ledger {ledger_path} does not exist"
    return None


# ---------------------------------------------------------------------------
# Canary: check_no_discipline_name_in_text fails on a known-bad input
# ---------------------------------------------------------------------------


def test_flags_discipline_name_leaking_into_generic_text() -> None:
    """Canary: a description string with an injected discipline name is flagged."""
    text = (
        "A discipline-generic consultant that resolves a Discipline: directive "
        "and, for statistician requests, loads the bound skill at runtime."
    )
    result = check_no_discipline_name_in_text(text, ["statistician"])
    assert result is not None, (
        "check_no_discipline_name_in_text must return a failure string when a "
        "registry discipline name appears in the text; got None (i.e. the "
        "check passed when it should have failed)"
    )
    assert "statistician" in result


def test_accepts_text_with_no_discipline_names() -> None:
    """Happy path: generic text naming no registry discipline passes."""
    text = "A discipline-generic consultant that resolves a Discipline: directive."
    result = check_no_discipline_name_in_text(text, ["statistician"])
    assert result is None, f"expected no failure for discipline-free text; got: {result!r}"


# ---------------------------------------------------------------------------
# Canary: check_registry_row_shape fails on a known-bad input
# ---------------------------------------------------------------------------


def test_flags_registry_row_missing_lens_collision_field() -> None:
    """Canary: a registry row missing the lens-collision field is flagged."""
    row_missing_lens_collision = {
        "discipline": "statistician",
        "fires-when": "a task claims a statistically significant effect",
        "binds-to": "applied-statistics",
        "challenge-obligations": "power/sample-size adequacy",
        "difficulty-hint": "standard",
        "attaches-to": "researcher, systems-architect",
        # lens-collision deliberately omitted
    }
    failures = check_registry_row_shape([row_missing_lens_collision])
    assert failures, (
        "check_registry_row_shape must return a failure for a row missing "
        "'lens-collision'; got an empty list (i.e. the check passed when it "
        "should have failed)"
    )
    assert any("lens-collision" in failure for failure in failures)


def test_flags_registry_row_with_blank_field_value() -> None:
    """Canary: a registry row with a present-but-empty field is flagged (substance over structure)."""
    row_with_blank_field = {
        "discipline": "statistician",
        "fires-when": "a task claims a statistically significant effect",
        "binds-to": "applied-statistics",
        "challenge-obligations": "power/sample-size adequacy",
        "difficulty-hint": "standard",
        "attaches-to": "researcher, systems-architect",
        "lens-collision": "   ",
    }
    failures = check_registry_row_shape([row_with_blank_field])
    assert failures, (
        "check_registry_row_shape must return a failure for a row whose "
        "'lens-collision' value is blank; got an empty list"
    )
    assert any("lens-collision" in failure for failure in failures)


def test_accepts_registry_row_with_all_seven_fields_populated() -> None:
    """Happy path: a row with all seven registry fields populated passes."""
    complete_row = {
        "discipline": "statistician",
        "fires-when": "a task claims a statistically significant effect",
        "binds-to": "applied-statistics",
        "challenge-obligations": "power/sample-size adequacy",
        "difficulty-hint": "standard",
        "attaches-to": "researcher, systems-architect",
        "lens-collision": "none",
    }
    failures = check_registry_row_shape([complete_row])
    assert not failures, f"expected no failures for a fully-populated row; got: {failures}"


# ---------------------------------------------------------------------------
# Canary: check_ledger_exists_if_registry_has_rows fails on a known-bad input
# ---------------------------------------------------------------------------


def test_flags_missing_ledger_when_registry_has_rows(tmp_path: Path) -> None:
    """Canary: a non-empty row list with no ledger file is flagged."""
    registry_rows = [{"discipline": "statistician"}]
    ledger_path = tmp_path / "CONSULT_LEDGER.md"  # deliberately not created

    result = check_ledger_exists_if_registry_has_rows(registry_rows, ledger_path)

    assert result is not None, (
        "check_ledger_exists_if_registry_has_rows must return a failure when the "
        "registry has rows but the ledger file does not exist; got None"
    )


def test_accepts_empty_registry_without_requiring_ledger(tmp_path: Path) -> None:
    """Happy path: an empty registry places no requirement on the ledger's existence."""
    ledger_path = tmp_path / "CONSULT_LEDGER.md"  # deliberately not created

    result = check_ledger_exists_if_registry_has_rows([], ledger_path)

    assert result is None, f"expected no failure for an empty registry; got: {result!r}"


def test_accepts_ledger_present_when_registry_has_rows(tmp_path: Path) -> None:
    """Happy path: a non-empty row list with the ledger file present passes."""
    ledger_path = tmp_path / "CONSULT_LEDGER.md"
    ledger_path.write_text("| timestamp | task-slug |\n", encoding="utf-8")
    registry_rows = [{"discipline": "statistician"}]

    result = check_ledger_exists_if_registry_has_rows(registry_rows, ledger_path)

    assert result is None, f"expected no failure when the ledger exists; got: {result!r}"


# ---------------------------------------------------------------------------
# Live-file parsing helpers -- these read real Markdown/YAML shapes, so each
# gets its own correctness proof before the live assertions below depend on it.
# ---------------------------------------------------------------------------

_FRONTMATTER_BLOCK_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)


def _frontmatter_block(text: str) -> str | None:
    """Return the raw text between a file's `---` frontmatter markers, or None."""
    match = _FRONTMATTER_BLOCK_RE.match(text)
    return match.group(1) if match else None


def _read_frontmatter(text: str) -> dict[str, object]:
    """Parse a Markdown file's YAML frontmatter into a dict; {} if absent/malformed."""
    block = _frontmatter_block(text)
    if block is None:
        return {}
    try:
        parsed = yaml.safe_load(block)
    except yaml.YAMLError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _has_paths_frontmatter(text: str) -> bool:
    """True if the file's frontmatter declares a `paths:` field.

    A path-scoped rule loads conditionally, never as part of the always-loaded
    surface these live assertions protect -- so it is excluded from the
    leakage scan below.
    Matches on presence inside the frontmatter block (mirroring
    scripts/check_paths_syntax.py's own detection), not a full YAML parse, so a
    rule with malformed `paths:` syntax still counts as path-scoped rather than
    silently being swept into the always-loaded set.
    """
    block = _frontmatter_block(text)
    if block is None:
        return False
    return re.search(r"^paths:", block, re.MULTILINE) is not None


def _split_comma_list(raw: str) -> list[str]:
    """Split a comma-separated frontmatter scalar (e.g. an unbracketed `tools:`
    value) into trimmed entries."""
    return [entry.strip() for entry in raw.split(",") if entry.strip()]


def find_discipline_registry_files(project_root: Path) -> list[Path]:
    """Every `discipline-registry.md`-named file anywhere under skills/."""
    return sorted((project_root / "skills").rglob("discipline-registry.md"))


def _split_into_table_blocks(markdown_text: str) -> list[list[str]]:
    """Split markdown_text into contiguous blocks of `|`-prefixed lines.

    A document can contain more than one table (e.g. a schema/example table
    documenting the columns, followed by the actual data table) -- treating
    every `|`-prefixed line in the whole file as one table conflates them. A
    blank or non-pipe line always ends the current block.
    """
    blocks: list[list[str]] = []
    current: list[str] = []
    for line in markdown_text.splitlines():
        if line.strip().startswith("|"):
            current.append(line)
        elif current:
            blocks.append(current)
            current = []
    if current:
        blocks.append(current)
    return blocks


def parse_registry_table_rows(markdown_text: str) -> list[dict[str, str]]:
    """Parse the registry table out of markdown_text into a list of row dicts.

    Locates the table whose header row contains all seven registry field names
    (REGISTRY_ROW_FIELDS), ignoring any other table in the same document (a
    schema/example table documenting the columns, for instance). Keys are the
    header row's cell text; the mandatory `---|---|...` separator row is
    skipped explicitly (by position), never counted as data. Returns [] when
    no matching table, or only a header + separator with no data rows, is
    present. A data row whose cell count does not match the header is dropped
    rather than misaligned into the wrong columns.
    """
    for block in _split_into_table_blocks(markdown_text):
        if len(block) < 2:
            continue
        header_cells = [cell.strip() for cell in block[0].strip().strip("|").split("|")]
        if set(REGISTRY_ROW_FIELDS) - set(header_cells):
            continue  # not the registry registry table -- some other table in the same document
        data_lines = block[2:]  # skip the header row and the --- separator row
        rows: list[dict[str, str]] = []
        for line in data_lines:
            cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
            if len(cells) != len(header_cells):
                continue
            rows.append(dict(zip(header_cells, cells, strict=True)))
        return rows
    return []


def _require_file(path: Path, description: str) -> Path:
    """Assert path exists as a file with an actionable message; return it unchanged."""
    assert path.is_file(), f"{description} not found at {path}"
    return path


def _registry_discipline_names(project_root: Path) -> list[str]:
    """The `discipline` column values of every row in the (possibly absent /
    possibly empty) registry. [] is a legitimate result, not an error -- the
    registry has zero rows until the statistician row lands."""
    registry_files = find_discipline_registry_files(project_root)
    if not registry_files:
        return []
    rows = parse_registry_table_rows(registry_files[0].read_text(encoding="utf-8"))
    return [row["discipline"] for row in rows if row.get("discipline")]


_REGISTRY_HEADER_ROW = "| " + " | ".join(REGISTRY_ROW_FIELDS) + " |"
_REGISTRY_SEPARATOR_ROW = "|" + "|".join(["---"] * len(REGISTRY_ROW_FIELDS)) + "|"


def test_parses_registry_table_rows_from_header_and_data_row() -> None:
    """Happy path: a two-row table (header + one data row) parses to one dict
    keyed by the header's column names."""
    table = (
        f"{_REGISTRY_HEADER_ROW}\n{_REGISTRY_SEPARATOR_ROW}\n"
        "| statistician | claims a significant effect | applied-statistics | "
        "power/sample-size adequacy | standard | researcher | none |\n"
    )
    rows = parse_registry_table_rows(table)
    assert rows == [
        {
            "discipline": "statistician",
            "fires-when": "claims a significant effect",
            "binds-to": "applied-statistics",
            "challenge-obligations": "power/sample-size adequacy",
            "difficulty-hint": "standard",
            "attaches-to": "researcher",
            "lens-collision": "none",
        }
    ]


def test_registry_table_rows_returns_empty_for_header_only_table() -> None:
    """Canary: a table with a header + separator but no data rows returns [],
    never miscounting the header or separator row as data (which would inflate
    a downstream row count and mask an empty registry as populated)."""
    header_only_table = f"{_REGISTRY_HEADER_ROW}\n{_REGISTRY_SEPARATOR_ROW}\n"
    rows = parse_registry_table_rows(header_only_table)
    assert rows == [], f"expected no rows for a header-only table; got: {rows!r}"


def test_ignores_a_non_registry_table_sharing_the_same_document() -> None:
    """Canary: a document with an unrelated 2-column example table (e.g. the
    real registry file's own "Field | Purpose" schema-reference table) ahead
    of the real registry table must not have its rows conflated into the
    parse -- proves the table is located by its registry header shape, not by
    "every `|`-prefixed line in the file" (the bug this test was written to
    catch: a document with two tables produced phantom rows from the wrong one).
    """
    document = (
        "| Field | Purpose |\n"
        "|---|---|\n"
        "| `discipline` | Registry key |\n"
        "| `fires-when` | Trigger predicate |\n"
        "\n"
        f"{_REGISTRY_HEADER_ROW}\n{_REGISTRY_SEPARATOR_ROW}\n"
        "| statistician | x | applied-statistics | y | standard | researcher | none |\n"
    )
    rows = parse_registry_table_rows(document)
    assert len(rows) == 1, f"expected exactly one registry row; got: {rows!r}"
    assert rows[0]["discipline"] == "statistician"


def test_detects_paths_frontmatter_when_present() -> None:
    """A rule file whose frontmatter declares `paths:` is detected as path-scoped."""
    text = '---\nname: some-rule\npaths: ["**/*.py"]\n---\n\n## Body\n'
    assert _has_paths_frontmatter(text) is True


def test_detects_paths_frontmatter_absent_when_not_declared() -> None:
    """A rule file with frontmatter but no `paths:` field is not path-scoped."""
    text = "---\nname: some-rule\n---\n\n## Body\n"
    assert _has_paths_frontmatter(text) is False


# ---------------------------------------------------------------------------
# Live assertions -- the extensibility invariants wired against the real,
# shipped tree: the consultant agent, the discipline registry, plugin.json,
# and the always-loaded surface. Each was designed from the architecture's
# registry schema and extensibility contract ahead of those artifacts landing;
# a RED result (a missing file) is the correct initial state and is expected
# to converge to green as the real artifacts land.
# ---------------------------------------------------------------------------


def test_exactly_one_agent_declares_the_consultant_role(project_root: Path) -> None:
    """Exactly one agent file declares the consultant role, and no registry
    discipline has grown its own dedicated `agents/<discipline>.md` file --
    new agent files per discipline must stay at zero. Vacuously true while the
    registry has zero rows; meaningfully checked once the first discipline
    row lands."""
    consultant_path = project_root / "agents" / "discipline-consultant.md"
    assert consultant_path.is_file(), (
        f"expected exactly one agent file declaring the discipline-consultant "
        f"role at {consultant_path}; file does not exist"
    )

    leaked = [
        project_root / "agents" / f"{discipline}.md"
        for discipline in _registry_discipline_names(project_root)
        if (project_root / "agents" / f"{discipline}.md").is_file()
    ]
    assert not leaked, (
        "a registry discipline must never grow its own dedicated agent file -- "
        f"bindings resolve at runtime through the Skill tool, never a new agent; "
        f"found: {[str(p) for p in leaked]}"
    )


def test_consultant_description_contains_no_registry_discipline_name(project_root: Path) -> None:
    """The consultant's description: names no registry discipline
    (case-insensitive), keeping the listing-pool cost discipline-count-independent."""
    consultant_path = _require_file(
        project_root / "agents" / "discipline-consultant.md", "discipline-consultant agent"
    )
    frontmatter = _read_frontmatter(consultant_path.read_text(encoding="utf-8"))
    description = frontmatter.get("description", "")
    assert isinstance(
        description, str
    ), f"consultant description: must be a string; got {description!r}"
    assert description, "consultant description: frontmatter field must be non-empty"

    result = check_no_discipline_name_in_text(description, _registry_discipline_names(project_root))
    assert result is None, f"consultant description: {result}"


def test_flags_a_registry_discipline_name_injected_into_the_real_description(
    project_root: Path, tmp_path: Path
) -> None:
    """Gate-liveness canary: proves check_no_discipline_name_in_text bites
    on the real description's actual shape -- not only on an invented string
    unrelated to the shipped file. Copies the real description into a
    tmp_path-scoped file with a synthetic discipline name appended; the
    committed agents/discipline-consultant.md is never mutated.
    """
    consultant_path = _require_file(
        project_root / "agents" / "discipline-consultant.md", "discipline-consultant agent"
    )
    frontmatter = _read_frontmatter(consultant_path.read_text(encoding="utf-8"))
    real_description = frontmatter.get("description", "")
    assert isinstance(
        real_description, str
    ), f"expected a string description; got {real_description!r}"
    assert real_description, "expected a non-empty description to build the canary from"

    synthetic_discipline = "zzz-canary-discipline"
    canary_copy = tmp_path / "description_canary.txt"
    canary_copy.write_text(
        f"{real_description}\n(handles {synthetic_discipline} requests specifically.)",
        encoding="utf-8",
    )

    result = check_no_discipline_name_in_text(
        canary_copy.read_text(encoding="utf-8"), [synthetic_discipline]
    )
    assert result is not None, (
        "check_no_discipline_name_in_text must flag a registry discipline name "
        "injected into a copy of the real description text; got None (the gate "
        "does not bite)"
    )


def test_no_always_loaded_surface_names_a_registry_discipline(project_root: Path) -> None:
    """Adding a discipline must cost 0 bytes on any always-loaded surface.
    Scans every rules/**/*.md lacking `paths:` frontmatter, plus every
    CLAUDE.md in the repo, for a registry discipline name. Vacuously passes
    while the registry has zero rows (there is nothing yet to leak); becomes a
    real scan once the first discipline row lands.
    """
    discipline_names = _registry_discipline_names(project_root)

    rule_candidates = [
        md
        for md in sorted((project_root / "rules").rglob("*.md"))
        if not _has_paths_frontmatter(md.read_text(encoding="utf-8"))
    ]
    claude_md_candidates = [
        md
        for md in sorted(project_root.rglob("CLAUDE.md"))
        if "node_modules" not in md.parts and "worktrees" not in md.parts
    ]

    failures: list[str] = []
    for md in rule_candidates + claude_md_candidates:
        result = check_no_discipline_name_in_text(md.read_text(encoding="utf-8"), discipline_names)
        if result is not None:
            failures.append(f"{md.relative_to(project_root)}: {result}")
    assert not failures, "Discipline name leaked into an always-loaded surface:\n  " + "\n  ".join(
        failures
    )


def test_consultant_skills_frontmatter_is_fixed_to_multi_perspective_analysis(
    project_root: Path,
) -> None:
    """The discipline->knowledge binding resolves at runtime via the Skill
    tool, so skills: is fixed forever at exactly one entry
    (multi-perspective-analysis) -- a gap discipline costs 0 skills: growth."""
    consultant_path = _require_file(
        project_root / "agents" / "discipline-consultant.md", "discipline-consultant agent"
    )
    frontmatter = _read_frontmatter(consultant_path.read_text(encoding="utf-8"))
    skills = frontmatter.get("skills")
    assert skills == ["multi-perspective-analysis"], (
        "consultant skills: frontmatter must equal exactly "
        f"['multi-perspective-analysis']; got {skills!r}"
    )


def test_consultant_tools_frontmatter_includes_the_skill_tool(project_root: Path) -> None:
    """tools: must grant the Skill tool so the consultant can resolve a
    discipline's binds-to skill at runtime (a prior runtime probe confirmed
    the exact tool name/casing is "Skill"). The remainder of the tools: set is
    the implementer's discretion -- not pinned here, since the architecture
    does not specify a full enumerated list beyond this one required entry.
    """
    consultant_path = _require_file(
        project_root / "agents" / "discipline-consultant.md", "discipline-consultant agent"
    )
    frontmatter = _read_frontmatter(consultant_path.read_text(encoding="utf-8"))
    raw_tools = frontmatter.get("tools", "")
    tools = _split_comma_list(raw_tools) if isinstance(raw_tools, str) else list(raw_tools or [])
    assert tools, f"consultant tools: frontmatter must be non-empty; got {raw_tools!r}"
    assert "Skill" in tools, (
        "consultant tools: frontmatter must include the exact tool name 'Skill' "
        f"(confirmed by a prior runtime probe); got {tools!r}"
    )


def test_registry_is_exactly_one_file_with_fully_populated_rows(project_root: Path) -> None:
    """The registry is a single enumerable structure -- exactly one
    discipline-registry.md under skills/ -- and every row it contains has all
    seven registry fields populated (reuses check_registry_row_shape,
    non-vacuously once the first discipline row lands)."""
    registry_files = find_discipline_registry_files(project_root)
    assert len(registry_files) == 1, (
        "expected exactly one discipline-registry.md under skills/; found "
        f"{len(registry_files)}: {[str(p.relative_to(project_root)) for p in registry_files]}"
    )
    rows = parse_registry_table_rows(registry_files[0].read_text(encoding="utf-8"))
    failures = check_registry_row_shape(rows)
    assert not failures, "Registry row shape violations:\n  " + "\n  ".join(failures)


def test_plugin_json_agents_count_matches_agents_directory(project_root: Path) -> None:
    """plugin.json edits per discipline must stay at zero: the agents array
    count must equal agents/*.md's count (excluding README.md/CLAUDE.md) --
    the same invariant the ecosystem's own coherence audit checks separately."""
    plugin_json_path = _require_file(
        project_root / ".claude-plugin" / "plugin.json", "plugin.json manifest"
    )
    manifest = json.loads(plugin_json_path.read_text(encoding="utf-8"))
    registered_agents = manifest.get("agents", [])

    agent_files = [
        path
        for path in (project_root / "agents").glob("*.md")
        if path.name not in {"README.md", "CLAUDE.md"}
    ]

    assert len(registered_agents) == len(agent_files), (
        f"plugin.json registers {len(registered_agents)} agents but agents/ contains "
        f"{len(agent_files)} agent files (excluding README.md/CLAUDE.md): "
        f"{sorted(path.name for path in agent_files)}"
    )


def test_ledger_exists_given_the_registrys_current_row_count(project_root: Path) -> None:
    """The ledger-ordering invariant, exercised against the real files: if the
    registry ever has >=1 row, .ai-state/CONSULT_LEDGER.md must already exist
    (reuses check_ledger_exists_if_registry_has_rows)."""
    ledger_path = project_root / ".ai-state" / "CONSULT_LEDGER.md"
    registry_files = find_discipline_registry_files(project_root)
    registry_rows: list[dict[str, str]] = []
    if registry_files:
        registry_rows = parse_registry_table_rows(registry_files[0].read_text(encoding="utf-8"))

    result = check_ledger_exists_if_registry_has_rows(registry_rows, ledger_path)
    assert result is None, result


# ---------------------------------------------------------------------------
# Ledger row-shape parsing -- the eleven-column contract documented in
# .ai-state/CONSULT_LEDGER.md § Column Definitions and § Falsifier. Split from
# the registry parsing above because a ledger row is read as a raw cell list,
# not a header-keyed dict: the row-shape check below needs the raw cell
# *count*, and an unescaped `|` inside a free-text cell (claim /
# decision-at-stake / rationale-ref) is exactly what inflates that count.
# ---------------------------------------------------------------------------

LEDGER_ROW_FIELDS: tuple[str, ...] = (
    "timestamp",
    "task-slug",
    "discipline",
    "stage",
    "challenge-id",
    "claim",
    "decision-at-stake",
    "disposition",
    "rationale-ref",
    "model",
    "difficulty",
)


def parse_ledger_table_rows(ledger_text: str) -> list[list[str]]:
    """Parse the ledger's data rows (header + `---` separator skipped by
    position, never counted as data) into a list of raw cell lists.

    Locates the table whose header row is exactly LEDGER_ROW_FIELDS, ignoring
    any other `|`-prefixed lines in the same document -- the real ledger's
    own § Falsifier section embeds a fenced shell snippet whose `grep`/`cut`
    lines also start with `|`, and those must never be swept in as data rows.
    """
    for block in _split_into_table_blocks(ledger_text):
        if len(block) < 2:
            continue
        header_cells = [cell.strip() for cell in block[0].strip().strip("|").split("|")]
        if header_cells != list(LEDGER_ROW_FIELDS):
            continue  # not the ledger's data table -- some other pipe-prefixed block
        data_lines = block[2:]  # skip the header row and the --- separator row
        return [
            [cell.strip() for cell in line.strip().strip("|").split("|")] for line in data_lines
        ]
    return []


def check_ledger_row_has_eleven_columns(rows: list[list[str]]) -> list[str]:
    """Return a failure string per row whose cell count isn't exactly eleven.

    A cell count above eleven is the direct symptom of an unescaped `|`
    inside a free-text column: the extra pipe is read as a delimiter both by
    this check and by any markdown renderer, so "wrong column count" and
    "unescaped pipe present" are the same defect under two names.
    """
    failures: list[str] = []
    for index, row in enumerate(rows):
        if len(row) != len(LEDGER_ROW_FIELDS):
            failures.append(
                f"row {index}: expected {len(LEDGER_ROW_FIELDS)} columns, got {len(row)}: {row!r}"
            )
    return failures


_LEDGER_HEADER_ROW = "| " + " | ".join(LEDGER_ROW_FIELDS) + " |"
_LEDGER_SEPARATOR_ROW = "|" + "|".join(["---"] * len(LEDGER_ROW_FIELDS)) + "|"


def test_parses_ledger_table_rows_from_header_and_data_row() -> None:
    """Happy path: a two-row table (header + one well-formed data row) parses
    to one row list with exactly eleven cells."""
    good_row = (
        "| 2026-07-30T10:00:00Z | task-a | statistician | architecture | CH-01 | "
        "a claim | a decision | switch-now | dec-100 | opus | standard |"
    )
    table = f"{_LEDGER_HEADER_ROW}\n{_LEDGER_SEPARATOR_ROW}\n{good_row}\n"
    rows = parse_ledger_table_rows(table)
    assert rows == [
        [
            "2026-07-30T10:00:00Z",
            "task-a",
            "statistician",
            "architecture",
            "CH-01",
            "a claim",
            "a decision",
            "switch-now",
            "dec-100",
            "opus",
            "standard",
        ]
    ]


def test_flags_ledger_row_with_unescaped_pipe_inflating_column_count() -> None:
    """Canary: a decision-at-stake cell containing a raw, unescaped `|`
    splits into an extra column, and check_ledger_row_has_eleven_columns
    flags it -- this is the shape a mis-escaped free-text cell actually
    takes, not an invented malformation."""
    bad_row = (
        "| 2026-07-30T10:00:00Z | task-a | statistician | architecture | CH-01 | "
        "a claim | decision A | B (unescaped pipe above) | switch-now | dec-100 | opus | standard |"
    )
    table = f"{_LEDGER_HEADER_ROW}\n{_LEDGER_SEPARATOR_ROW}\n{bad_row}\n"
    rows = parse_ledger_table_rows(table)
    failures = check_ledger_row_has_eleven_columns(rows)
    assert failures, (
        "check_ledger_row_has_eleven_columns must flag a row whose unescaped "
        "pipe inflates its cell count past eleven; got an empty list"
    )


def test_accepts_ledger_row_with_exactly_eleven_columns() -> None:
    """Happy path: a well-formed, eleven-cell row produces no failures."""
    good_row = (
        "| 2026-07-30T10:00:00Z | task-a | statistician | architecture | CH-01 | "
        "a claim | a decision | switch-now | dec-100 | opus | standard |"
    )
    table = f"{_LEDGER_HEADER_ROW}\n{_LEDGER_SEPARATOR_ROW}\n{good_row}\n"
    rows = parse_ledger_table_rows(table)
    failures = check_ledger_row_has_eleven_columns(rows)
    assert not failures, f"expected no failures for a well-formed row; got: {failures}"


def test_every_real_ledger_row_has_exactly_eleven_columns(project_root: Path) -> None:
    """The row-shape invariant, exercised against the real, shipped
    .ai-state/CONSULT_LEDGER.md."""
    ledger_path = _require_file(
        project_root / ".ai-state" / "CONSULT_LEDGER.md", "disposition ledger"
    )
    rows = parse_ledger_table_rows(ledger_path.read_text(encoding="utf-8"))
    assert rows, "expected at least one data row in the real ledger"
    failures = check_ledger_row_has_eleven_columns(rows)
    assert not failures, "Ledger row shape violations:\n  " + "\n  ".join(failures)


# ---------------------------------------------------------------------------
# Disposition-counter falsifier -- the column-anchored grep+count recipes
# documented in .ai-state/CONSULT_LEDGER.md § Falsifier, reimplemented here as
# pure functions so they can be proven correct against a synthetic ledger
# *and* run against the real one. The recipe was already defective once (an
# unanchored form that matched a discipline name anywhere in the row, not
# only in the discipline column, inflating the denominator and biasing the
# discipline-expansion gate toward passing) -- the canary below reproduces
# that exact defect shape.
# ---------------------------------------------------------------------------


def _discipline_column_pattern(discipline: str) -> re.Pattern[str]:
    """The anchored, column-position regex from the ledger's own documented
    falsifier recipe: matches only when `discipline` occupies the third
    pipe-delimited column, never a free-text cell that happens to mention it."""
    return re.compile(rf"^\|[^|]*\|[^|]*\| *{re.escape(discipline)} *\|", re.MULTILINE)


def count_ledger_rows_for_discipline(ledger_text: str, discipline: str) -> int:
    """Total dispositioned-challenge rows for `discipline` -- the raw count
    the falsifier's first documented command computes."""
    return len(_discipline_column_pattern(discipline).findall(ledger_text))


def count_dismissed_for_discipline(ledger_text: str, discipline: str) -> int:
    """Dismissed rows for `discipline`, among the rows matched above."""
    matched_lines = [
        line
        for line in ledger_text.splitlines()
        if _discipline_column_pattern(discipline).match(line)
    ]
    return sum(1 for line in matched_lines if "dismiss-with-rationale" in line)


def count_distinct_consults_for_discipline(ledger_text: str, discipline: str) -> int:
    """Distinct task-slugs (independent consults) for `discipline` -- the
    discipline-expansion criterion's actual denominator, per the ledger's own
    note that challenges raised within one consult are a cluster sharing a
    consultant/draft/convener, not independent observations."""
    matched_lines = [
        line
        for line in ledger_text.splitlines()
        if _discipline_column_pattern(discipline).match(line)
    ]
    slugs = {line.strip().strip("|").split("|")[1].strip() for line in matched_lines}
    return len(slugs)


def count_rows_naive_substring_match(ledger_text: str, discipline: str) -> int:
    """The DEFECTIVE recipe form the falsifier documents having shipped once:
    an unanchored substring search that also matches a *different*
    discipline's row whose free-text cell happens to mention the name."""
    return sum(
        1
        for line in ledger_text.splitlines()
        if line.strip().startswith("|") and discipline in line
    )


def test_unanchored_discipline_match_inflates_count_the_anchored_form_avoids() -> None:
    """Canary reproducing the falsifier's own documented defect: three rows
    exist, but only two belong to `statistician` -- the third is a
    `linguist` row whose decision-at-stake cell happens to mention
    'statistician'. The anchored recipe returns 2; the unanchored one
    inflates to 3, exactly as the ledger's own Falsifier section warns."""
    rows = [
        "| 2026-07-30T10:00:00Z | task-a | statistician | architecture | CH-01 | "
        "claim | decision | switch-now | dec-1 | opus | standard |",
        "| 2026-07-30T10:00:00Z | task-a | statistician | architecture | CH-02 | "
        "claim | decision | defer-with-rationale | dec-2 | opus | standard |",
        "| 2026-07-30T11:00:00Z | task-b | linguist | architecture | CH-01 | "
        "claim | statistician should have weighed in here | switch-now | dec-3 | opus | standard |",
    ]
    ledger_text = f"{_LEDGER_HEADER_ROW}\n{_LEDGER_SEPARATOR_ROW}\n" + "\n".join(rows) + "\n"

    assert count_ledger_rows_for_discipline(ledger_text, "statistician") == 2
    assert count_rows_naive_substring_match(ledger_text, "statistician") == 3, (
        "expected the unanchored recipe to reproduce the documented inflation "
        "(3 rows matched for a discipline that has 2) -- if this drops to 2 the "
        "canary no longer exercises the defect it exists to guard against"
    )


def test_counts_dismissed_and_distinct_consults_for_a_discipline() -> None:
    """Happy path: dismissed-row count and distinct-consult count are computed
    correctly against a small synthetic ledger with a known-by-construction
    answer (2 statistician rows in task-a, 1 in task-b; 1 of the 3 is
    dismissed)."""
    rows = [
        "| 2026-07-30T10:00:00Z | task-a | statistician | architecture | CH-01 | "
        "claim | decision | dismiss-with-rationale | dec-1 | opus | standard |",
        "| 2026-07-30T10:00:00Z | task-a | statistician | architecture | CH-02 | "
        "claim | decision | switch-now | dec-2 | opus | standard |",
        "| 2026-07-30T11:00:00Z | task-b | statistician | architecture | CH-01 | "
        "claim | decision | defer-with-rationale | dec-3 | opus | standard |",
    ]
    ledger_text = f"{_LEDGER_HEADER_ROW}\n{_LEDGER_SEPARATOR_ROW}\n" + "\n".join(rows) + "\n"

    assert count_ledger_rows_for_discipline(ledger_text, "statistician") == 3
    assert count_dismissed_for_discipline(ledger_text, "statistician") == 1
    assert count_distinct_consults_for_discipline(ledger_text, "statistician") == 2


def test_ledger_falsifier_recipe_returns_correct_counts_on_the_real_ledger(
    project_root: Path,
) -> None:
    """The disposition-counter falsifier, exercised against the shipped
    .ai-state/CONSULT_LEDGER.md: the documented column-anchored recipe must
    return the actual dispositioned-challenge counts for `statistician`,
    proving the recipe bites on the real file rather than only on invented
    strings.

    Asserts invariants rather than literal counts: the ledger is append-only
    and grows with every consult, so pinning exact totals would make routine
    data growth indistinguishable from a broken recipe."""
    ledger_path = _require_file(
        project_root / ".ai-state" / "CONSULT_LEDGER.md", "disposition ledger"
    )
    ledger_text = ledger_path.read_text(encoding="utf-8")

    total = count_ledger_rows_for_discipline(ledger_text, "statistician")
    dismissed = count_dismissed_for_discipline(ledger_text, "statistician")
    consults = count_distinct_consults_for_discipline(ledger_text, "statistician")
    naive = count_rows_naive_substring_match(ledger_text, "statistician")

    assert total > 0, "the shipped ledger carries statistician rows"
    assert 0 <= dismissed <= total
    assert 1 <= consults <= total, "challenges cluster within consults"
    assert naive >= total, (
        "the unanchored form must over-count or tie, never under-count -- "
        "if it ever returns fewer rows than the anchored form, the anchoring "
        "regex has stopped matching real rows"
    )


# ---------------------------------------------------------------------------
# fires-when predicate strength -- the registry's own Row Schema says "any
# numeric claim" is not a predicate; this check gives that prose a mechanical
# floor so a future row can't slip in a one-word or empty trigger.
# ---------------------------------------------------------------------------

_MIN_FIRES_WHEN_WORDS = 6


def check_fires_when_is_restrictive(rows: list[dict[str, str]]) -> list[str]:
    """Return a failure per row whose fires-when reads as a placeholder
    rather than an authored predicate (fewer than _MIN_FIRES_WHEN_WORDS
    words -- a short generic phrase like "any numeric claim" is exactly the
    shape this rejects)."""
    failures: list[str] = []
    for row in rows:
        label = row.get("discipline") or "row"
        value = row.get("fires-when", "")
        word_count = len(value.split())
        if word_count < _MIN_FIRES_WHEN_WORDS:
            failures.append(
                f"{label}: fires-when has only {word_count} word(s), reads as a "
                f"placeholder rather than an authored predicate: {value!r}"
            )
    return failures


def test_flags_fires_when_that_reads_as_a_placeholder_predicate() -> None:
    """Canary: a row whose fires-when is the registry's own named
    non-example ("any numeric claim") is flagged as too weak to be a
    predicate."""
    row = {"discipline": "statistician", "fires-when": "any numeric claim"}
    failures = check_fires_when_is_restrictive([row])
    assert failures, (
        "check_fires_when_is_restrictive must flag a row whose fires-when is "
        "the registry's own named non-example ('any numeric claim'); got an "
        "empty list"
    )


def test_accepts_fires_when_that_reads_as_an_authored_predicate() -> None:
    """Happy path: a long, specific trigger predicate is accepted."""
    row = {
        "discipline": "statistician",
        "fires-when": (
            "A load-bearing decision rests on a quantitative claim: an asserted "
            "effect or regression, a chosen sample or run count"
        ),
    }
    failures = check_fires_when_is_restrictive([row])
    assert not failures, f"expected no failures for a specific predicate; got: {failures}"


def test_registrys_fires_when_column_is_a_restrictive_predicate_for_every_row(
    project_root: Path,
) -> None:
    """The predicate-strength invariant, exercised against the real registry:
    every row's fires-when must read as an authored trigger, never a
    one-word or near-empty placeholder."""
    registry_files = find_discipline_registry_files(project_root)
    assert registry_files, "expected at least one discipline-registry.md under skills/"
    rows = parse_registry_table_rows(registry_files[0].read_text(encoding="utf-8"))
    assert rows, "expected at least one registry row"
    failures = check_fires_when_is_restrictive(rows)
    assert not failures, "fires-when predicate-strength violations:\n  " + "\n  ".join(failures)


# ---------------------------------------------------------------------------
# Fail-loud resolution contract -- an unresolvable Discipline: value must
# produce [BLOCKED], never a silently degraded consult. Checked as a
# documentation invariant over the two files that state the contract, since
# no test harness spawns the real consultant agent here.
# ---------------------------------------------------------------------------


def check_documents_fail_loud_resolution(text: str) -> str | None:
    """Return a failure string unless text documents both halves of the
    fail-loud resolution contract: a `[BLOCKED]` outcome, and that it fires
    on an unresolvable Discipline: value."""
    if "[BLOCKED]" not in text:
        return "no '[BLOCKED]' marker found"
    if re.search(r"unresolvable", text, re.IGNORECASE) is None:
        return "'[BLOCKED]' present but no mention of an unresolvable directive/value"
    return None


def test_flags_text_missing_the_blocked_marker() -> None:
    """Canary: text describing only a generic error path, with no
    `[BLOCKED]` marker, fails the fail-loud check."""
    text = "If the discipline cannot be resolved, the consultant stops and reports an error."
    result = check_documents_fail_loud_resolution(text)
    assert (
        result is not None
    ), "check_documents_fail_loud_resolution must flag text with no '[BLOCKED]' marker; got None"


def test_flags_blocked_marker_not_tied_to_an_unresolvable_value() -> None:
    """Canary: `[BLOCKED]` present, but never connected to an unresolvable
    directive/value, still fails -- the marker alone isn't the contract."""
    text = "On any failure the agent may return [BLOCKED] with a generic message."
    result = check_documents_fail_loud_resolution(text)
    assert result is not None, (
        "check_documents_fail_loud_resolution must flag '[BLOCKED]' text that "
        "never mentions an unresolvable directive/value; got None"
    )


def test_accepts_text_documenting_both_halves_of_the_fail_loud_contract() -> None:
    """Happy path: text naming both the [BLOCKED] outcome and the
    unresolvable-value trigger passes."""
    text = "An unresolvable Discipline: value returns [BLOCKED] naming the value."
    result = check_documents_fail_loud_resolution(text)
    assert result is None, f"expected no failure; got: {result!r}"


def test_consultant_agent_documents_the_fail_loud_resolution_contract(project_root: Path) -> None:
    """The real agents/discipline-consultant.md documents the fail-loud
    contract for an unresolvable Discipline: value."""
    consultant_path = _require_file(
        project_root / "agents" / "discipline-consultant.md", "discipline-consultant agent"
    )
    result = check_documents_fail_loud_resolution(consultant_path.read_text(encoding="utf-8"))
    assert result is None, f"discipline-consultant agent: {result}"


def test_agents_claude_md_documents_the_fail_loud_resolution_contract(project_root: Path) -> None:
    """The real agents/CLAUDE.md documents the same fail-loud contract for
    the consultant's caller-facing summary."""
    claude_md_path = _require_file(project_root / "agents" / "CLAUDE.md", "agents/CLAUDE.md")
    result = check_documents_fail_loud_resolution(claude_md_path.read_text(encoding="utf-8"))
    assert result is None, f"agents/CLAUDE.md: {result}"
