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
import subprocess
from pathlib import Path

import pytest
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


# The escape every CONSULT_* file's § Column Definitions instructs conveners to
# write for a literal pipe inside a free-text cell ("Escape any literal `|`").
# Splitting on a bare `|` reads that escape as a delimiter, so a cell written to
# the documented convention splits into an extra column and trips the row-shape
# gate -- the file's own convention and its own gate disagreeing. That is root
# cause 1 of the ADR narrowing dec-310's G6 clause (see `.ai-state/decisions/`).
# A raw, *unescaped* pipe still splits, which is exactly what the row-shape
# canaries below supply and rely on.
_UNESCAPED_PIPE_RE = re.compile(r"(?<!\\)\|")


def _split_escaped_row(line: str) -> list[str]:
    r"""Split one `|`-delimited markdown row into stripped cell values, reading
    `\|` as a literal pipe inside a cell rather than as a column delimiter.

    Scoped to the four CONSULT_* table parsers (ledger, cost, sealed priors,
    challenge classification) -- those are the tables whose § Column Definitions
    document the escape. The discipline registry documents no such convention
    and is parsed unchanged.
    """
    cells = _UNESCAPED_PIPE_RE.split(line.strip().strip("|"))
    return [cell.strip().replace("\\|", "|") for cell in cells]


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


def check_consultant_agent_file_exists(consultant_path: Path) -> str | None:
    """Return a failure string if consultant_path does not exist.

    Exactly one agent file must declare the discipline-consultant role.
    """
    if not consultant_path.is_file():
        return (
            f"expected exactly one agent file declaring the discipline-consultant "
            f"role at {consultant_path}; file does not exist"
        )
    return None


def check_no_per_discipline_agent_files(agents_dir: Path, discipline_names: list[str]) -> list[str]:
    """Return a failure string per registry discipline that has grown its own
    dedicated `agents/<discipline>.md` file.

    A registry discipline must never grow its own dedicated agent file --
    bindings resolve at runtime through the Skill tool, never a new agent.
    This is a distinct defect class from `check_consultant_agent_file_exists`:
    the consultant file existing says nothing about whether some *other*,
    per-discipline agent file has also leaked into existence.
    """
    return [
        f"a registry discipline must never grow its own dedicated agent file -- "
        f"bindings resolve at runtime through the Skill tool, never a new agent; "
        f"found: {agents_dir / f'{discipline}.md'}"
        for discipline in discipline_names
        if (agents_dir / f"{discipline}.md").is_file()
    ]


def test_exactly_one_agent_declares_the_consultant_role(project_root: Path) -> None:
    """Exactly one agent file declares the consultant role, and no registry
    discipline has grown its own dedicated `agents/<discipline>.md` file --
    new agent files per discipline must stay at zero. Vacuously true while the
    registry has zero rows; meaningfully checked once the first discipline
    row lands."""
    consultant_path = project_root / "agents" / "discipline-consultant.md"
    exists_failure = check_consultant_agent_file_exists(consultant_path)
    assert exists_failure is None, exists_failure

    leaked_failures = check_no_per_discipline_agent_files(
        project_root / "agents", _registry_discipline_names(project_root)
    )
    assert not leaked_failures, "\n  ".join(leaked_failures)


def test_flags_missing_consultant_agent_file(tmp_path: Path) -> None:
    """Canary: check_consultant_agent_file_exists flags an absent file."""
    result = check_consultant_agent_file_exists(tmp_path / "discipline-consultant.md")
    assert result is not None, (
        "check_consultant_agent_file_exists must flag a missing consultant file"
    )


def test_flags_a_per_discipline_agent_file(tmp_path: Path) -> None:
    """Canary: check_no_per_discipline_agent_files flags a discipline that has
    grown its own dedicated agent file -- the exact leak the check exists to
    catch."""
    (tmp_path / "statistician.md").write_text("stub", encoding="utf-8")
    failures = check_no_per_discipline_agent_files(tmp_path, ["statistician"])
    assert failures, (
        "check_no_per_discipline_agent_files must flag a leaked per-discipline agent file"
    )


def test_consultant_description_contains_no_registry_discipline_name(project_root: Path) -> None:
    """The consultant's description: names no registry discipline
    (case-insensitive), keeping the listing-pool cost discipline-count-independent."""
    consultant_path = _require_file(
        project_root / "agents" / "discipline-consultant.md", "discipline-consultant agent"
    )
    frontmatter = _read_frontmatter(consultant_path.read_text(encoding="utf-8"))
    description = frontmatter.get("description", "")
    assert isinstance(description, str), (
        f"consultant description: must be a string; got {description!r}"
    )
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
    assert isinstance(real_description, str), (
        f"expected a string description; got {real_description!r}"
    )
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


def check_consultant_skills_frontmatter_is_pinned(skills: object) -> str | None:
    """Return a failure string if skills != ['multi-perspective-analysis'].

    The discipline->knowledge binding resolves at runtime via the Skill tool,
    so skills: is fixed forever at exactly one entry -- a new discipline costs
    0 skills: growth.
    """
    if skills != ["multi-perspective-analysis"]:
        return (
            "consultant skills: frontmatter must equal exactly "
            f"['multi-perspective-analysis']; got {skills!r}"
        )
    return None


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
    result = check_consultant_skills_frontmatter_is_pinned(skills)
    assert result is None, result


def test_flags_consultant_skills_frontmatter_drifted_from_pinned_value() -> None:
    """Canary: check_consultant_skills_frontmatter_is_pinned flags a skills:
    list that has grown beyond the pinned single entry."""
    result = check_consultant_skills_frontmatter_is_pinned(
        ["multi-perspective-analysis", "some-other-skill"]
    )
    assert result is not None, (
        "check_consultant_skills_frontmatter_is_pinned must flag skills: drift"
    )


def check_consultant_tools_include_skill_tool(tools: list[str]) -> str | None:
    """Return a failure string if tools is empty or omits the exact tool name
    'Skill' (confirmed by a prior runtime probe).

    The consultant needs the Skill tool to resolve a discipline's binds-to
    skill at runtime. The remainder of the tools: set is the implementer's
    discretion -- not pinned here.
    """
    if not tools:
        return f"consultant tools: frontmatter must be non-empty; got {tools!r}"
    if "Skill" not in tools:
        return (
            "consultant tools: frontmatter must include the exact tool name 'Skill' "
            f"(confirmed by a prior runtime probe); got {tools!r}"
        )
    return None


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
    result = check_consultant_tools_include_skill_tool(tools)
    assert result is None, result


def test_flags_consultant_tools_frontmatter_missing_the_skill_tool() -> None:
    """Canary: check_consultant_tools_include_skill_tool flags a tools: list
    that omits the required 'Skill' entry."""
    result = check_consultant_tools_include_skill_tool(["Read", "Write"])
    assert result is not None, (
        "check_consultant_tools_include_skill_tool must flag a tools: list missing 'Skill'"
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


def check_plugin_agent_count_matches_agent_files(
    registered_agent_count: int, agent_file_count: int, agent_file_names: list[str]
) -> str | None:
    """Return a failure string if plugin.json's agents array count disagrees
    with agents/*.md's count (excluding README.md/CLAUDE.md).

    plugin.json edits per discipline must stay at zero -- the same invariant
    the ecosystem's own coherence audit checks separately.
    """
    if registered_agent_count != agent_file_count:
        return (
            f"plugin.json registers {registered_agent_count} agents but agents/ contains "
            f"{agent_file_count} agent files (excluding README.md/CLAUDE.md): "
            f"{sorted(agent_file_names)}"
        )
    return None


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

    result = check_plugin_agent_count_matches_agent_files(
        len(registered_agents), len(agent_files), [path.name for path in agent_files]
    )
    assert result is None, result


def test_flags_plugin_json_agent_count_mismatch() -> None:
    """Canary: check_plugin_agent_count_matches_agent_files flags a count
    mismatch between plugin.json's agents array and agents/*.md."""
    result = check_plugin_agent_count_matches_agent_files(3, 4, ["a.md", "b.md", "c.md", "d.md"])
    assert result is not None, (
        "check_plugin_agent_count_matches_agent_files must flag a count mismatch"
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
        header_cells = _split_escaped_row(block[0])
        if header_cells != list(LEDGER_ROW_FIELDS):
            continue  # not the ledger's data table -- some other pipe-prefixed block
        data_lines = block[2:]  # skip the header row and the --- separator row
        return [_split_escaped_row(line) for line in data_lines]
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


def test_accepts_a_ledger_row_whose_escaped_pipe_stays_inside_one_cell() -> None:
    r"""The documented `\|` escape is a literal pipe, not a delimiter: a claim
    cell written to the convention still parses to exactly eleven columns, and
    the cell value carries an unescaped `|`.

    Paired with the canary above: a *raw* pipe still inflates the count. The
    escape is the only thing that changed."""
    escaped_row = (
        r"| 2026-07-30T10:00:00Z | task-a | statistician | architecture | CH-01 | "
        r"the manifest maps kind(dir\|file) | a decision | switch-now | dec-100 | opus | standard |"
    )
    table = f"{_LEDGER_HEADER_ROW}\n{_LEDGER_SEPARATOR_ROW}\n{escaped_row}\n"
    rows = parse_ledger_table_rows(table)

    assert len(rows) == 1, f"expected one parsed row; got: {rows!r}"
    assert len(rows[0]) == len(LEDGER_ROW_FIELDS), (
        f"an escaped pipe must not split a cell; got {len(rows[0])} cells: {rows[0]!r}"
    )
    claim = rows[0][LEDGER_ROW_FIELDS.index("claim")]
    assert claim == "the manifest maps kind(dir|file)", (
        f"the escape must be unescaped to a literal pipe in the cell value; got: {claim!r}"
    )
    assert not check_ledger_row_has_eleven_columns(rows)


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
    """Distinct consults (independent observations) for `discipline` -- the
    discipline-expansion criterion's actual denominator, per the ledger's own
    note that challenges raised within one consult are a cluster sharing a
    consultant/draft/convener, not independent observations.

    Keyed on the (task-slug, stage) pair, not task-slug alone: a consult's
    identity is the (task-slug, discipline, stage) triple -- the same
    convention .ai-state/CONSULT_COSTS.md § Column Definitions documents for
    its own join key -- because one discipline can attach at both `research`
    and `architecture` within a single task, and those are two independent
    consultant spawns (different stage, different draft, different spawn)
    sharing only a task-slug. Keying on task-slug alone collapses them into
    one, undercounting n and biasing the discipline-expansion criterion
    toward "not yet informative"."""
    matched_lines = [
        line
        for line in ledger_text.splitlines()
        if _discipline_column_pattern(discipline).match(line)
    ]
    consult_keys: set[tuple[str, str]] = set()
    for line in matched_lines:
        cells = line.strip().strip("|").split("|")
        consult_keys.add((cells[1].strip(), cells[3].strip()))
    return len(consult_keys)


def collapse_ledger_rows_to_latest_per_challenge(
    ledger_text: str, discipline: str
) -> list[list[str]]:
    """Collapse `discipline`'s ledger rows to one row per (task-slug, stage,
    challenge-id) -- the latest by timestamp.

    The ledger is append-only: a challenge revisited later (e.g. a
    `defer-with-rationale` superseded by a `switch-now`, per
    .ai-state/CONSULT_LEDGER.md § Column Definitions) is written as a
    *second*, later-timestamped row for the same challenge, never as an edit
    to the first. Counting both rows as independent, live observations
    overstates the live-challenge count. Supersession is detected
    structurally -- keeping the row with the latest timestamp per key -- never
    by parsing `rationale-ref` prose, which no grep recipe reads reliably."""
    matched_lines = [
        line
        for line in ledger_text.splitlines()
        if _discipline_column_pattern(discipline).match(line)
    ]
    latest_by_key: dict[tuple[str, str, str], list[str]] = {}
    for line in matched_lines:
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        timestamp, task_slug, _discipline, stage, challenge_id = cells[:5]
        key = (task_slug, stage, challenge_id)
        current_latest = latest_by_key.get(key)
        if current_latest is None or timestamp > current_latest[0]:
            latest_by_key[key] = cells
    return list(latest_by_key.values())


def count_live_challenges_for_discipline(ledger_text: str, discipline: str) -> int:
    """Count of live (non-superseded) dispositioned challenges for
    `discipline`. See collapse_ledger_rows_to_latest_per_challenge."""
    return len(collapse_ledger_rows_to_latest_per_challenge(ledger_text, discipline))


def count_live_dismissed_for_discipline(ledger_text: str, discipline: str) -> int:
    """Dismissed count among live (non-superseded) challenges for
    `discipline`. See collapse_ledger_rows_to_latest_per_challenge."""
    live_rows = collapse_ledger_rows_to_latest_per_challenge(ledger_text, discipline)
    return sum(1 for cells in live_rows if cells[7] == "dismiss-with-rationale")


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


def check_falsifier_recipe_counts_match(
    total: int, dismissed: int, consults: int, naive: int
) -> list[str]:
    """Return a failure string per invariant violated among the disposition-
    counter falsifier's four computed counts.

    Asserts invariants rather than literal counts: the ledger is append-only
    and grows with every consult, so pinning exact totals would make routine
    data growth indistinguishable from a broken recipe.
    """
    failures: list[str] = []
    if not total > 0:
        failures.append(f"expected total > 0 (the shipped ledger carries rows); got {total}")
    if not (0 <= dismissed <= total):
        failures.append(
            f"expected 0 <= dismissed <= total; got dismissed={dismissed}, total={total}"
        )
    if not (1 <= consults <= total):
        failures.append(
            "expected 1 <= consults <= total (challenges cluster within consults); "
            f"got consults={consults}, total={total}"
        )
    if not naive >= total:
        failures.append(
            "the unanchored form must over-count or tie, never under-count -- "
            "if it ever returns fewer rows than the anchored form, the anchoring "
            f"regex has stopped matching real rows; got naive={naive}, total={total}"
        )
    return failures


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

    failures = check_falsifier_recipe_counts_match(total, dismissed, consults, naive)
    assert not failures, "\n  ".join(failures)


def test_flags_falsifier_recipe_count_invariant_violation() -> None:
    """Canary: check_falsifier_recipe_counts_match flags a naive count that
    under-counts relative to the anchored total -- the exact regression the
    anchoring regex exists to prevent."""
    failures = check_falsifier_recipe_counts_match(total=3, dismissed=1, consults=2, naive=2)
    assert failures, "check_falsifier_recipe_counts_match must flag naive < total"


def count_distinct_consults_by_task_slug_only(ledger_text: str, discipline: str) -> int:
    """The DEFECTIVE keying `count_distinct_consults_for_discipline` shipped
    with: task-slug alone. Undercounts whenever a discipline attaches at more
    than one stage within a single task-slug -- reproduced here only so the
    canary below can assert the delta explicitly."""
    matched_lines = [
        line
        for line in ledger_text.splitlines()
        if _discipline_column_pattern(discipline).match(line)
    ]
    slugs = {line.strip().strip("|").split("|")[1].strip() for line in matched_lines}
    return len(slugs)


def test_task_slug_only_keying_undercounts_consults_the_triple_keying_avoids() -> None:
    """Canary reproducing the counting defect found while re-deriving the
    ledger's own numbers: one task-slug, two stages, same discipline -- two
    independent consultant spawns (different stage, different draft,
    different spawn) sharing a task-slug but nothing else, per
    .ai-state/CONSULT_COSTS.md's own (task-slug, discipline, stage)
    consult-identity convention. The task-slug-only recipe collapses them to
    1; keying on (task-slug, stage) correctly returns 2."""
    rows = [
        "| 2026-07-30T23:10:00Z | task-a | statistician | architecture | CH-01 | "
        "claim | decision | switch-now | dec-1 | opus | standard |",
        "| 2026-07-31T00:05:00Z | task-a | statistician | research | CH-01 | "
        "claim | decision | switch-now | dec-2 | opus | standard |",
    ]
    ledger_text = f"{_LEDGER_HEADER_ROW}\n{_LEDGER_SEPARATOR_ROW}\n" + "\n".join(rows) + "\n"

    assert count_distinct_consults_by_task_slug_only(ledger_text, "statistician") == 1, (
        "expected the defective task-slug-only recipe to reproduce the documented "
        "undercount (1 consult for a discipline that has 2) -- if this changes the "
        "canary no longer exercises the defect it exists to guard against"
    )
    assert count_distinct_consults_for_discipline(ledger_text, "statistician") == 2, (
        "keying on (task-slug, stage) must count the two stage-distinct spawns "
        "as two independent consults, not one"
    )


def test_collapses_superseded_rows_to_the_latest_disposition_per_challenge() -> None:
    """Canary reproducing the second counting defect found while re-deriving
    the ledger's own numbers: a challenge revised later (a
    defer-with-rationale superseded by a switch-now, written as a second,
    later-timestamped row rather than an edit to the first, per
    .ai-state/CONSULT_LEDGER.md § Column Definitions) must count once, at its
    live disposition -- not once per row appended."""
    rows = [
        "| 2026-07-30T17:05:00Z | task-a | statistician | architecture | CH-01 | "
        "claim | decision | defer-with-rationale | dec-1 | opus | standard |",
        "| 2026-07-30T17:20:00Z | task-a | statistician | architecture | CH-01 | "
        "claim | decision | switch-now | dec-2 (revises the defer) | opus | standard |",
        "| 2026-07-30T17:05:00Z | task-a | statistician | architecture | CH-02 | "
        "claim | decision | dismiss-with-rationale | dec-3 | opus | standard |",
    ]
    ledger_text = f"{_LEDGER_HEADER_ROW}\n{_LEDGER_SEPARATOR_ROW}\n" + "\n".join(rows) + "\n"

    assert count_ledger_rows_for_discipline(ledger_text, "statistician") == 3, (
        "the raw row count is unchanged -- three rows were appended"
    )
    assert count_live_challenges_for_discipline(ledger_text, "statistician") == 2, (
        "the two CH-01 rows collapse to one live challenge (its latest "
        "disposition, switch-now), leaving 2 live challenges total"
    )
    assert count_live_dismissed_for_discipline(ledger_text, "statistician") == 1, (
        "CH-02's dismiss-with-rationale is live and uncontested; CH-01's "
        "superseded defer-with-rationale must not be counted at all"
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
    assert result is not None, (
        "check_documents_fail_loud_resolution must flag text with no '[BLOCKED]' marker; got None"
    )


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


# ---------------------------------------------------------------------------
# Cost-series coverage gate (td-071) -- .ai-state/CONSULT_COSTS.md carries one
# row per consult spawn (grain differs from the ledger's one-row-per-challenge:
# cost is a property of the consult, not of the challenge, dec-308).
# This gate fails when a post-boundary ledger consult has no matching, positive,
# consistent cost row -- the omission the file exists to make CI-visible.
# ---------------------------------------------------------------------------

COST_ROW_FIELDS: tuple[str, ...] = (
    "timestamp",
    "task-slug",
    "discipline",
    "stage",
    "tokens",
    "model",
    "difficulty",
    "notes",
)

# The gate's source of truth for the series boundary is this constant, not the
# file's own "**Series begins**:" header line -- the gate must still fail when
# the file is absent (a managed project's first consult, or a deletion), and a
# boundary read only from a missing file would silently exempt everything. A
# second check (below) asserts the file's header line equals this constant so
# the two can never silently drift apart.
SERIES_BOUNDARY = "2026-07-31T01:00:00Z"

_COST_HEADER_ROW = "| " + " | ".join(COST_ROW_FIELDS) + " |"
_COST_SEPARATOR_ROW = "|" + "|".join(["---"] * len(COST_ROW_FIELDS)) + "|"
_SERIES_BEGINS_RE = re.compile(r"^\*\*Series begins\*\*:\s*(\S+)", re.MULTILINE)
_TIMESTAMP_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")


def parse_cost_table_rows(cost_text: str) -> list[list[str]]:
    """Parse CONSULT_COSTS.md's data rows into a list of raw cell lists.

    Same block-scan + exact-header-match shape as parse_ledger_table_rows --
    the header row and the `---` separator row are skipped by position, never
    counted as data.
    """
    for block in _split_into_table_blocks(cost_text):
        if len(block) < 2:
            continue
        header_cells = _split_escaped_row(block[0])
        if header_cells != list(COST_ROW_FIELDS):
            continue  # not the cost table -- some other pipe-prefixed block
        data_lines = block[2:]  # skip the header row and the --- separator row
        return [_split_escaped_row(line) for line in data_lines]
    return []


def parse_series_boundary(cost_text: str) -> str | None:
    """Return the ISO timestamp in the file's `**Series begins**:` line, or None."""
    match = _SERIES_BEGINS_RE.search(cost_text)
    return match.group(1) if match else None


def check_cost_row_has_eight_columns(rows: list[list[str]]) -> list[str]:
    """Return a failure string per row whose cell count isn't exactly eight.

    Same unescaped-pipe defect class as the ledger's eleven-column check: an
    extra pipe in a free-text cell (here, only `notes`) inflates the count.
    """
    failures: list[str] = []
    for index, row in enumerate(rows):
        if len(row) != len(COST_ROW_FIELDS):
            failures.append(
                f"row {index}: expected {len(COST_ROW_FIELDS)} columns, got {len(row)}: {row!r}"
            )
    return failures


def check_series_boundary_matches_gate_constant(cost_text: str) -> str | None:
    """Return a failure string unless the file's header boundary line equals
    SERIES_BOUNDARY exactly."""
    found = parse_series_boundary(cost_text)
    if found is None:
        return "no '**Series begins**:' header line found in CONSULT_COSTS.md"
    if found != SERIES_BOUNDARY:
        return f"series boundary header {found!r} does not match gate constant {SERIES_BOUNDARY!r}"
    return None


def check_every_post_boundary_consult_has_a_cost_row(
    ledger_rows: list[list[str]],
    cost_rows: list[list[str]],
    boundary: str,
) -> list[str]:
    """Return one failure string per violation found while checking that every
    post-`boundary` (task-slug, discipline, stage) triple in `ledger_rows` has
    a matching row in `cost_rows`.

    Checks, per triple:
      - presence -- >=1 cost row carries the triple
      - substance -- that row's `tokens` cell is a positive integer (digits
        only, > 0); a "", an "n/a", or a "0" does not count
      - consistency -- the row's `model` and `difficulty` equal the ledger's
        values for the same triple

    A ledger `timestamp` that doesn't match the ISO 8601 shape is itself a
    failure, rather than being silently mis-ordered against `boundary`.
    """
    failures: list[str] = []
    ledger_index = {field: pos for pos, field in enumerate(LEDGER_ROW_FIELDS)}
    cost_index = {field: pos for pos, field in enumerate(COST_ROW_FIELDS)}

    post_boundary_triples: dict[tuple[str, str, str], tuple[str, str]] = {}
    for row in ledger_rows:
        timestamp = row[ledger_index["timestamp"]]
        if not _TIMESTAMP_RE.match(timestamp):
            failures.append(f"ledger row has a malformed timestamp: {timestamp!r}")
            continue
        if timestamp < boundary:
            continue
        triple = (
            row[ledger_index["task-slug"]],
            row[ledger_index["discipline"]],
            row[ledger_index["stage"]],
        )
        post_boundary_triples[triple] = (
            row[ledger_index["model"]],
            row[ledger_index["difficulty"]],
        )

    for triple, (expected_model, expected_difficulty) in post_boundary_triples.items():
        matching_cost_rows = [
            row
            for row in cost_rows
            if (
                row[cost_index["task-slug"]],
                row[cost_index["discipline"]],
                row[cost_index["stage"]],
            )
            == triple
        ]
        if not matching_cost_rows:
            failures.append(f"no CONSULT_COSTS.md row for post-boundary consult {triple!r}")
            continue
        for row in matching_cost_rows:
            tokens = row[cost_index["tokens"]]
            if not tokens.isdigit() or int(tokens) <= 0:
                failures.append(
                    f"consult {triple!r}: tokens cell is not a positive integer: {tokens!r}"
                )
            model = row[cost_index["model"]]
            if model != expected_model:
                failures.append(
                    f"consult {triple!r}: model {model!r} disagrees with ledger {expected_model!r}"
                )
            difficulty = row[cost_index["difficulty"]]
            if difficulty != expected_difficulty:
                failures.append(
                    f"consult {triple!r}: difficulty {difficulty!r} disagrees with ledger "
                    f"{expected_difficulty!r}"
                )

    return failures


# ---------------------------------------------------------------------------
# RECONSTRUCTED: marker substance gate -- a `RECONSTRUCTED:`-prefixed `notes`
# cell is admitted by the schema in place
# of a harness-surfaced observation only when it actually states the four
# things CONSULT_COSTS.md § Column Definitions requires: a derivation, a
# calibration comparison, a transcript path, and a residual direction. Without
# this check the marker is free to become a bare label -- the exact decay mode
# dec-308's own `dissent:` field predicted for this series.
# ---------------------------------------------------------------------------

RECONSTRUCTED_MARKER = "RECONSTRUCTED:"
_CALIBRATION_COMPARISON_RE = re.compile(r"\d+[^\d]{1,40}(?:vs|recorded)[^\d]{1,40}\d+")
_RESIDUAL_DIRECTION_WORDS = ("undercount", "overcount", "residual")


def check_reconstructed_cost_notes_are_substantive(cost_rows: list[list[str]]) -> list[str]:
    """Return one failure string per `notes` cell that either misuses or
    hollows out the `RECONSTRUCTED:` marker.

    A row whose `notes` cell contains the literal marker is checked for:
      - position -- the marker must lead the note, not appear mid-note (a
        mid-note marker reads as someone quoting the convention rather than
        invoking it, and is exempt from the substance checks below)
      - derivation -- the note states the formula (`input_tokens` or
        `tokens =`)
      - calibration -- at least one comparison of two integers via `vs` or
        `recorded`
      - transcript -- a `.jsonl` path to the source transcript
      - residual direction -- `undercount`, `overcount`, or `residual`

    A row whose `notes` cell carries no `RECONSTRUCTED:` marker at all is not
    inspected -- this gate only constrains rows that claim the label.
    """
    failures: list[str] = []
    cost_index = {field: pos for pos, field in enumerate(COST_ROW_FIELDS)}
    for row in cost_rows:
        notes = row[cost_index["notes"]]
        marker_pos = notes.find(RECONSTRUCTED_MARKER)
        if marker_pos == -1:
            continue
        if marker_pos != 0:
            failures.append(
                f"notes cell carries a {RECONSTRUCTED_MARKER!r} marker that does not "
                f"lead the note (found at offset {marker_pos}): {notes!r}"
            )
            continue
        if "input_tokens" not in notes and "tokens =" not in notes:
            failures.append(
                f"RECONSTRUCTED note states no derivation (no 'input_tokens' or "
                f"'tokens =' found): {notes!r}"
            )
        if not _CALIBRATION_COMPARISON_RE.search(notes):
            failures.append(
                f"RECONSTRUCTED note states no calibration comparison (no "
                f"'<int> vs <int>' / '<int> recorded ... <int>' found): {notes!r}"
            )
        if ".jsonl" not in notes:
            failures.append(
                f"RECONSTRUCTED note states no transcript path (no '.jsonl' found): {notes!r}"
            )
        if not any(word in notes for word in _RESIDUAL_DIRECTION_WORDS):
            failures.append(
                f"RECONSTRUCTED note states no residual direction (no "
                f"'undercount'/'overcount'/'residual' found): {notes!r}"
            )
    return failures


# ---------------------------------------------------------------------------
# Canaries: check_every_post_boundary_consult_has_a_cost_row and its siblings
# fail on known-bad inputs.
# ---------------------------------------------------------------------------


def test_flags_a_post_boundary_consult_missing_from_the_cost_series() -> None:
    """Canary: the omission td-071 exists to prevent -- a post-boundary
    ledger consult with zero matching cost rows."""
    ledger_row = (
        "| 2026-08-01T12:00:00Z | task-x | statistician | architecture | CH-01 | "
        "a claim | a decision | switch-now | dec-999 | opus | standard |"
    )
    ledger_table = f"{_LEDGER_HEADER_ROW}\n{_LEDGER_SEPARATOR_ROW}\n{ledger_row}\n"
    cost_table = (
        f"{_COST_HEADER_ROW}\n{_COST_SEPARATOR_ROW}\n"  # header + separator, zero data rows
    )

    ledger_rows = parse_ledger_table_rows(ledger_table)
    cost_rows = parse_cost_table_rows(cost_table)
    failures = check_every_post_boundary_consult_has_a_cost_row(
        ledger_rows, cost_rows, SERIES_BOUNDARY
    )

    assert len(failures) == 1, f"expected exactly one failure; got: {failures}"
    assert "'task-x'" in failures[0]
    assert "'statistician'" in failures[0]
    assert "'architecture'" in failures[0]


def test_flags_a_cost_row_whose_tokens_cell_is_not_a_positive_integer() -> None:
    """Canary: substance over structure -- a present-but-invalid tokens cell
    (blank, non-numeric, or zero) is flagged, not just an absent row."""
    ledger_row = (
        "| 2026-08-01T12:00:00Z | task-y | statistician | architecture | CH-01 | "
        "a claim | a decision | switch-now | dec-999 | opus | standard |"
    )
    ledger_table = f"{_LEDGER_HEADER_ROW}\n{_LEDGER_SEPARATOR_ROW}\n{ledger_row}\n"
    bad_tokens_rows = [
        "| 2026-08-01T12:05:00Z | task-y | statistician | architecture |  | opus | standard | blank |",
        "| 2026-08-01T12:06:00Z | task-y | statistician | architecture | n/a | opus | standard | not-a-number |",
        "| 2026-08-01T12:07:00Z | task-y | statistician | architecture | 0 | opus | standard | zero |",
    ]
    cost_table = f"{_COST_HEADER_ROW}\n{_COST_SEPARATOR_ROW}\n" + "\n".join(bad_tokens_rows) + "\n"

    ledger_rows = parse_ledger_table_rows(ledger_table)
    cost_rows = parse_cost_table_rows(cost_table)
    failures = check_every_post_boundary_consult_has_a_cost_row(
        ledger_rows, cost_rows, SERIES_BOUNDARY
    )

    assert len(failures) == 3, (
        f"expected exactly three failures (one per bad tokens cell); got: {failures}"
    )


def test_flags_a_cost_row_whose_model_disagrees_with_the_ledger() -> None:
    """Canary: the denormalized `model` copy must agree with the ledger's
    recorded model for the same triple."""
    ledger_row = (
        "| 2026-08-01T12:00:00Z | task-z | statistician | architecture | CH-01 | "
        "a claim | a decision | switch-now | dec-999 | opus | standard |"
    )
    ledger_table = f"{_LEDGER_HEADER_ROW}\n{_LEDGER_SEPARATOR_ROW}\n{ledger_row}\n"
    cost_row = (
        "| 2026-08-01T12:05:00Z | task-z | statistician | architecture | 50000 | "
        "sonnet | standard | mismatched model |"
    )
    cost_table = f"{_COST_HEADER_ROW}\n{_COST_SEPARATOR_ROW}\n{cost_row}\n"

    ledger_rows = parse_ledger_table_rows(ledger_table)
    cost_rows = parse_cost_table_rows(cost_table)
    failures = check_every_post_boundary_consult_has_a_cost_row(
        ledger_rows, cost_rows, SERIES_BOUNDARY
    )

    assert len(failures) == 1, f"expected exactly one failure; got: {failures}"
    assert "'sonnet'" in failures[0]
    assert "'opus'" in failures[0]


def test_flags_cost_row_with_unescaped_pipe_inflating_column_count() -> None:
    """Canary: an unescaped pipe in the notes cell inflates the column count
    past eight -- the same defect class as the ledger's eleven-column check."""
    bad_row = (
        "| 2026-08-01T12:00:00Z | task-w | statistician | architecture | 12345 | "
        "opus | standard | note with an unescaped | pipe |"
    )
    table = f"{_COST_HEADER_ROW}\n{_COST_SEPARATOR_ROW}\n{bad_row}\n"
    rows = parse_cost_table_rows(table)
    failures = check_cost_row_has_eight_columns(rows)

    assert len(failures) == 1, f"expected exactly one failure; got: {failures}"
    assert "got 9" in failures[0], f"expected the row to report 9 cells; got: {failures}"


def test_accepts_a_cost_row_whose_escaped_pipe_stays_inside_one_cell() -> None:
    r"""The documented `\|` escape in a `notes` cell parses to exactly eight
    columns and yields a literal pipe in the cell value."""
    escaped_row = (
        r"| 2026-08-01T12:00:00Z | task-w | statistician | architecture | 12345 | "
        r"opus | standard | note about kind(dir\|file) |"
    )
    table = f"{_COST_HEADER_ROW}\n{_COST_SEPARATOR_ROW}\n{escaped_row}\n"
    rows = parse_cost_table_rows(table)

    assert len(rows) == 1, f"expected one parsed row; got: {rows!r}"
    assert len(rows[0]) == len(COST_ROW_FIELDS), (
        f"an escaped pipe must not split a cell; got {len(rows[0])} cells: {rows[0]!r}"
    )
    notes = rows[0][COST_ROW_FIELDS.index("notes")]
    assert notes == "note about kind(dir|file)", (
        f"the escape must be unescaped to a literal pipe in the cell value; got: {notes!r}"
    )
    assert not check_cost_row_has_eight_columns(rows)


def test_flags_series_boundary_header_missing_from_the_cost_file() -> None:
    """Canary: a cost file with no `**Series begins**:` header line is flagged
    -- the gate's file-absent-or-header-absent case must fail, not pass silently."""
    cost_text = f"# Consultation Cost Series\n\n{_COST_HEADER_ROW}\n{_COST_SEPARATOR_ROW}\n"
    result = check_series_boundary_matches_gate_constant(cost_text)
    assert result is not None, (
        "check_series_boundary_matches_gate_constant must flag a cost file with no "
        "'**Series begins**:' header line; got None"
    )


# ---------------------------------------------------------------------------
# Canaries: check_reconstructed_cost_notes_are_substantive fails on known-bad
# inputs -- the marker must not be free to become a bare label.
# ---------------------------------------------------------------------------

_SUBSTANTIVE_RECONSTRUCTED_NOTE = (
    "RECONSTRUCTED: tokens = final assistant message's (input_tokens + "
    "cache_read_input_tokens + cache_creation_input_tokens + output_tokens) from "
    "~/.claude/projects/-Users-fperez-dev-praxion/dee467d0-eb81-475a-9974-e09ee647921b/"
    "subagents/agent-a78b9d5b0d15db26a.jsonl. Calibration: sidecar-placement/"
    "data-structure-specialist recorded 156321 vs reconstructed 156232 (-0.06%) -- a "
    "consistent undercount."
)


def test_flags_reconstructed_note_that_is_a_bare_label() -> None:
    """Canary: a `RECONSTRUCTED:` marker with no derivation, calibration,
    transcript, or residual direction behind it -- the decay mode the check
    exists to catch."""
    bare_row = _cost_row("RECONSTRUCTED: see the async spawn for details")
    failures = check_reconstructed_cost_notes_are_substantive([bare_row])

    assert len(failures) == 4, f"expected all four substance failures; got: {failures}"


def test_flags_reconstructed_note_missing_a_calibration_comparison() -> None:
    """Canary: a note stating a derivation, transcript, and residual direction
    but no calibration comparison against a recorded figure."""
    row = _cost_row(
        "RECONSTRUCTED: tokens = input_tokens + output_tokens from "
        "~/.claude/projects/x/subagents/agent-abc.jsonl, a consistent undercount "
        "of the true figure."
    )
    failures = check_reconstructed_cost_notes_are_substantive([row])

    assert len(failures) == 1, f"expected exactly one failure; got: {failures}"
    assert "calibration comparison" in failures[0]


def test_flags_reconstructed_marker_not_leading_the_note() -> None:
    """Canary: the `RECONSTRUCTED:` marker appearing mid-note, rather than at
    the start, reads as quoting the convention rather than invoking it."""
    row = _cost_row(f"see notes below. {_SUBSTANTIVE_RECONSTRUCTED_NOTE}")
    failures = check_reconstructed_cost_notes_are_substantive([row])

    assert len(failures) == 1, f"expected exactly one failure; got: {failures}"
    assert "does not lead the note" in failures[0]


def test_accepts_a_substantive_reconstructed_note() -> None:
    """Happy path: a note stating derivation, calibration, transcript, and
    residual direction -- the real `rust-first-class` row's shape -- passes."""
    row = _cost_row(_SUBSTANTIVE_RECONSTRUCTED_NOTE)
    failures = check_reconstructed_cost_notes_are_substantive([row])

    assert not failures, f"expected no failures for a substantive note; got: {failures}"


def test_accepts_a_row_with_no_reconstructed_marker() -> None:
    """Happy path: a row whose notes cell never claims the `RECONSTRUCTED:`
    label is out of scope for this gate entirely."""
    row = _cost_row("first consult of the discipline; 8 challenges, 8 switch-now")
    failures = check_reconstructed_cost_notes_are_substantive([row])

    assert not failures, f"expected no failures for a non-RECONSTRUCTED row; got: {failures}"


def test_every_real_reconstructed_cost_note_is_substantive(project_root: Path) -> None:
    """The substance gate, exercised against the real, shipped
    .ai-state/CONSULT_COSTS.md (skips cleanly if the file does not exist yet)."""
    cost_path = project_root / ".ai-state" / "CONSULT_COSTS.md"
    if not cost_path.is_file():
        pytest.skip("CONSULT_COSTS.md does not exist yet")
    rows = parse_cost_table_rows(cost_path.read_text(encoding="utf-8"))
    failures = check_reconstructed_cost_notes_are_substantive(rows)
    assert not failures, "RECONSTRUCTED note substance violations:\n  " + "\n  ".join(failures)


# ---------------------------------------------------------------------------
# Non-canary controls: prove the gate does not over-fire.
# ---------------------------------------------------------------------------


def test_accepts_a_pre_boundary_consult_absent_from_the_cost_series() -> None:
    """Happy path: a pre-boundary ledger consult with zero matching cost rows
    is exempt -- the four pre-adoption consults must not turn the gate red."""
    ledger_row = (
        "| 2026-07-30T17:05:00Z | task-v | statistician | architecture | CH-01 | "
        "a claim | a decision | defer-with-rationale | dec-1 | opus | standard |"
    )
    ledger_table = f"{_LEDGER_HEADER_ROW}\n{_LEDGER_SEPARATOR_ROW}\n{ledger_row}\n"
    cost_table = f"{_COST_HEADER_ROW}\n{_COST_SEPARATOR_ROW}\n"

    ledger_rows = parse_ledger_table_rows(ledger_table)
    cost_rows = parse_cost_table_rows(cost_table)
    failures = check_every_post_boundary_consult_has_a_cost_row(
        ledger_rows, cost_rows, SERIES_BOUNDARY
    )
    assert not failures, f"expected no failures for a pre-boundary consult; got: {failures}"


def test_accepts_a_consult_with_two_cost_rows_for_one_triple() -> None:
    """Happy path: a Round-3 loop-back re-spawn appends a second cost row for
    the same triple rather than mutating the first -- >=1 satisfies the gate."""
    ledger_row = (
        "| 2026-08-01T12:00:00Z | task-u | statistician | architecture | CH-01 | "
        "a claim | a decision | switch-now | dec-999 | opus | standard |"
    )
    ledger_table = f"{_LEDGER_HEADER_ROW}\n{_LEDGER_SEPARATOR_ROW}\n{ledger_row}\n"
    cost_rows_text = [
        "| 2026-08-01T12:05:00Z | task-u | statistician | architecture | 40000 | opus | standard | first spawn |",
        "| 2026-08-01T13:00:00Z | task-u | statistician | architecture | 15000 | opus | standard | loop-back increment |",
    ]
    cost_table = f"{_COST_HEADER_ROW}\n{_COST_SEPARATOR_ROW}\n" + "\n".join(cost_rows_text) + "\n"

    ledger_rows = parse_ledger_table_rows(ledger_table)
    cost_rows = parse_cost_table_rows(cost_table)
    failures = check_every_post_boundary_consult_has_a_cost_row(
        ledger_rows, cost_rows, SERIES_BOUNDARY
    )
    assert not failures, (
        f"expected no failures for two consistent cost rows on one triple; got: {failures}"
    )


# ---------------------------------------------------------------------------
# Real-file tests -- the ones that actually bite in CI.
# ---------------------------------------------------------------------------


def test_every_post_boundary_consult_in_the_real_ledger_has_a_cost_row(project_root: Path) -> None:
    """The coverage gate, exercised against the shipped ledger and cost
    series. Skips only when the cost file is absent AND the ledger carries no
    post-boundary consult yet (nothing the gate could meaningfully check);
    fails when the file is absent but a post-boundary consult exists."""
    ledger_path = _require_file(
        project_root / ".ai-state" / "CONSULT_LEDGER.md", "disposition ledger"
    )
    ledger_rows = parse_ledger_table_rows(ledger_path.read_text(encoding="utf-8"))

    cost_path = project_root / ".ai-state" / "CONSULT_COSTS.md"
    cost_text = cost_path.read_text(encoding="utf-8") if cost_path.is_file() else ""
    cost_rows = parse_cost_table_rows(cost_text) if cost_text else []

    ledger_index = {field: pos for pos, field in enumerate(LEDGER_ROW_FIELDS)}
    has_post_boundary_consult = any(
        _TIMESTAMP_RE.match(row[ledger_index["timestamp"]])
        and row[ledger_index["timestamp"]] >= SERIES_BOUNDARY
        for row in ledger_rows
    )
    if not cost_path.is_file() and not has_post_boundary_consult:
        pytest.skip("CONSULT_COSTS.md absent and no post-boundary consult exists yet")

    failures = check_every_post_boundary_consult_has_a_cost_row(
        ledger_rows, cost_rows, SERIES_BOUNDARY
    )
    assert not failures, "Post-boundary consult(s) missing a cost row:\n  " + "\n  ".join(failures)


def test_every_real_cost_row_has_exactly_eight_columns(project_root: Path) -> None:
    """The row-shape invariant, exercised against the real, shipped
    .ai-state/CONSULT_COSTS.md (skips cleanly if the file does not exist yet)."""
    cost_path = project_root / ".ai-state" / "CONSULT_COSTS.md"
    if not cost_path.is_file():
        pytest.skip("CONSULT_COSTS.md does not exist yet")
    rows = parse_cost_table_rows(cost_path.read_text(encoding="utf-8"))
    failures = check_cost_row_has_eight_columns(rows)
    assert not failures, "Cost row shape violations:\n  " + "\n  ".join(failures)


def test_real_cost_file_boundary_matches_the_gate_constant(project_root: Path) -> None:
    """The series-boundary invariant, exercised against the real, shipped
    .ai-state/CONSULT_COSTS.md (skips cleanly if the file does not exist yet)."""
    cost_path = project_root / ".ai-state" / "CONSULT_COSTS.md"
    if not cost_path.is_file():
        pytest.skip("CONSULT_COSTS.md does not exist yet")
    result = check_series_boundary_matches_gate_constant(cost_path.read_text(encoding="utf-8"))
    assert result is None, result


# ---------------------------------------------------------------------------
# Stray-row-outside-the-table gate (td-079) -- both CONSULT_LEDGER.md and
# CONSULT_COSTS.md instructed their single writer to "append... at the end of
# this file/ledger", which an orchestrator followed literally by landing a row
# after the trailing prose sections (`## Column Definitions`, `## Falsifier`,
# `## Single Writer`) rather than inside the parsed data table. Every parser
# above reads only the table, so that row is invisible to the counting recipe
# and to the cost-coverage gate while still rendering as a plausible stray
# table to a human reader. The instructions themselves were reworded to name
# the table and the section that follows it; this gate is the mechanical
# backstop, reusing parse_ledger_table_rows / parse_cost_table_rows rather
# than a third parser: it counts lines that LOOK like a data row (a
# pipe-delimited ISO 8601 timestamp in the first column, the shared shape of
# both tables) across the WHOLE document and compares that count to what the
# table parser actually captured.
# ---------------------------------------------------------------------------

_TIMESTAMP_ROW_SHAPE_RE = re.compile(r"^\| *\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z *\|", re.MULTILINE)


def check_no_data_row_outside_table(full_text: str, table_rows: list[list[str]]) -> str | None:
    """Return a failure string if a timestamp-shaped data row exists outside
    the rows the table parser returned.

    A mismatch between "rows that look like data, counted anywhere in the
    file" and "rows the table parser actually captured" means a row landed
    outside the parsed table -- invisible to every counting recipe above, but
    still rendering as a plausible stray table to a human reader.

    Paired site: `fitness/tests/test_consult_append_only.py` guards the
    neighbouring defect -- an existing row being edited or deleted rather than
    misplaced. That gate's `extract_data_rows` is whole-file by design, so it
    sees a stray row either way and does not depend on this check; the two
    nonetheless partition one contract between them. Read and update both
    whenever either one's scope changes, per the two-textual-sites
    anti-pattern in `rules/swe/gate-liveness.md`.
    """
    total_shaped_lines = len(_TIMESTAMP_ROW_SHAPE_RE.findall(full_text))
    if total_shaped_lines != len(table_rows):
        return (
            f"found {total_shaped_lines} timestamp-shaped row(s) across the whole "
            f"file but the table parser returned {len(table_rows)} row(s) -- "
            f"{total_shaped_lines - len(table_rows)} row(s) exist outside the parsed table"
        )
    return None


def test_accepts_document_with_no_stray_rows() -> None:
    """Happy path: a well-formed ledger table with no stray row is accepted."""
    good_row = (
        "| 2026-07-30T10:00:00Z | task-a | statistician | architecture | CH-01 | "
        "a claim | a decision | switch-now | dec-100 | opus | standard |"
    )
    document = f"{_LEDGER_HEADER_ROW}\n{_LEDGER_SEPARATOR_ROW}\n{good_row}\n"
    table_rows = parse_ledger_table_rows(document)
    result = check_no_data_row_outside_table(document, table_rows)
    assert result is None, f"expected no failure for a clean table; got: {result!r}"


def test_flags_ledger_row_landing_outside_the_parsed_table() -> None:
    """Canary: a stray data row appended after the ledger's trailing prose
    sections (outside the parsed table) is flagged -- reproduces the exact
    defect an orchestrator following the ledger's former 'append at the end
    of this ledger' instruction literally would produce."""
    good_row = (
        "| 2026-07-30T10:00:00Z | task-a | statistician | architecture | CH-01 | "
        "a claim | a decision | switch-now | dec-100 | opus | standard |"
    )
    stray_row = (
        "| 2026-08-01T09:00:00Z | task-b | statistician | architecture | CH-02 | "
        "a stray claim | a stray decision | switch-now | dec-200 | opus | standard |"
    )
    document = (
        f"{_LEDGER_HEADER_ROW}\n{_LEDGER_SEPARATOR_ROW}\n{good_row}\n\n"
        "## Column Definitions\n\nSome prose describing the columns.\n\n"
        "## Falsifier\n\nSome prose with a recipe.\n\n"
        "## Single Writer\n\nSome trailing prose.\n\n"
        f"{stray_row}\n"
    )
    table_rows = parse_ledger_table_rows(document)
    result = check_no_data_row_outside_table(document, table_rows)
    assert result is not None, (
        "check_no_data_row_outside_table must flag a stray ledger row appended "
        "after the trailing prose sections; got None (the gate does not bite)"
    )


def test_flags_cost_row_landing_outside_the_parsed_table() -> None:
    """Canary: the same defect shape for CONSULT_COSTS.md -- a stray row
    appended after its trailing prose sections."""
    good_row = (
        "| 2026-07-30T17:20:00Z | task-a | statistician | architecture | 101030 | "
        "opus | standard | seed |"
    )
    stray_row = (
        "| 2026-08-01T09:00:00Z | task-b | statistician | architecture | 5000 | "
        "opus | standard | stray |"
    )
    document = (
        f"{_COST_HEADER_ROW}\n{_COST_SEPARATOR_ROW}\n{good_row}\n\n"
        "## Column Definitions\n\nSome prose describing the columns.\n\n"
        "## Reading the series\n\nSome prose with a recipe.\n\n"
        "## Single Writer\n\nSome trailing prose.\n\n"
        f"{stray_row}\n"
    )
    table_rows = parse_cost_table_rows(document)
    result = check_no_data_row_outside_table(document, table_rows)
    assert result is not None, (
        "check_no_data_row_outside_table must flag a stray cost row appended "
        "after the trailing prose sections; got None (the gate does not bite)"
    )


def test_no_ledger_data_row_exists_outside_the_parsed_table(project_root: Path) -> None:
    """The real, shipped .ai-state/CONSULT_LEDGER.md carries no stray data
    row outside the parsed table -- the real-file proof, not just the
    synthetic canary above."""
    ledger_path = _require_file(
        project_root / ".ai-state" / "CONSULT_LEDGER.md", "disposition ledger"
    )
    text = ledger_path.read_text(encoding="utf-8")
    table_rows = parse_ledger_table_rows(text)
    result = check_no_data_row_outside_table(text, table_rows)
    assert result is None, result


def test_no_cost_data_row_exists_outside_the_parsed_table(project_root: Path) -> None:
    """The real, shipped .ai-state/CONSULT_COSTS.md carries no stray data row
    outside the parsed table (skips cleanly if the file does not exist yet)."""
    cost_path = project_root / ".ai-state" / "CONSULT_COSTS.md"
    if not cost_path.is_file():
        pytest.skip("CONSULT_COSTS.md does not exist yet")
    text = cost_path.read_text(encoding="utf-8")
    table_rows = parse_cost_table_rows(text)
    result = check_no_data_row_outside_table(text, table_rows)
    assert result is None, result


# ---------------------------------------------------------------------------
# Sealed-prior-list coverage gate (td-081) -- .ai-state/CONSULT_PRIORS.md carries
# two tables: `## Sealed Priors` (one row per pre-spawn concern, written before
# the consultant spawns) and `## Challenge Classification` (one row per
# dispositioned challenge, written at Round 2). This gate fails when a
# post-boundary ledger consult has no sealed prior, when a sealed prior's
# concern/source/prior-id is malformed, when a challenge carries no
# classification, or when a classification's matched-prior-id or seal-witness
# is malformed or inconsistent -- the omissions the file exists to make
# CI-visible (td-081; see .ai-state/decisions/ for the ADR that resolved it).
# ---------------------------------------------------------------------------

PRIOR_ROW_FIELDS: tuple[str, ...] = (
    "timestamp",
    "task-slug",
    "discipline",
    "stage",
    "prior-id",
    "source",
    "concern",
)

CLASSIFICATION_ROW_FIELDS: tuple[str, ...] = (
    "timestamp",
    "task-slug",
    "discipline",
    "stage",
    "challenge-id",
    "classification",
    "matched-prior-id",
    "seal-witness",
    "prompt-areas",
)

# Same rationale as SERIES_BOUNDARY above: the gate's source of truth is this
# constant, not the file's own header line, so the gate still fails when the
# file is absent. G1 below cross-checks the header line against this constant
# so the two can never silently drift apart.
SEAL_BOUNDARY = "2026-07-31T03:00:00Z"

# Placeholder concern values a shallow lens pass or a rushed convener might
# write instead of a substantive one -- compared lowercased so "TBD"/"N/A"
# also match.
_PLACEHOLDER_CONCERNS = frozenset({"", "-", "--", "n/a", "na", "tbd", "none."})

# The explicit empty declaration -- `.ai-state/CONSULT_PRIORS.md` § Column
# Definitions reserves this `prior-id` value and states it must be the only row
# for its triple.
NONE_PRIOR_ID = "NONE"

_PRIOR_ID_RE = re.compile(r"^P-\d{2}$")
_SEAL_WITNESS_RE = re.compile(r"^[0-9a-f]{7,40}$")
_PROMPT_AREAS_RE = re.compile(r"^\d+$")
_ROUND0_HEAD_RE = re.compile(r"\*\*Round-0 HEAD:\*\*\s*([0-9a-f]{7,40})")

_PRIOR_HEADER_ROW = "| " + " | ".join(PRIOR_ROW_FIELDS) + " |"
_PRIOR_SEPARATOR_ROW = "|" + "|".join(["---"] * len(PRIOR_ROW_FIELDS)) + "|"
_CLASSIFICATION_HEADER_ROW = "| " + " | ".join(CLASSIFICATION_ROW_FIELDS) + " |"
_CLASSIFICATION_SEPARATOR_ROW = "|" + "|".join(["---"] * len(CLASSIFICATION_ROW_FIELDS)) + "|"


def parse_prior_table_rows(priors_text: str) -> list[list[str]]:
    """Parse the `## Sealed Priors` table's data rows into raw cell lists.

    Same block-scan + exact-header-match shape as parse_cost_table_rows -- two
    tables share one file, so matching the header cell-list exactly is what
    keeps `## Sealed Priors` and `## Challenge Classification` from being
    conflated by a naive "every pipe-prefixed block" scan.
    """
    for block in _split_into_table_blocks(priors_text):
        if len(block) < 2:
            continue
        header_cells = _split_escaped_row(block[0])
        if header_cells != list(PRIOR_ROW_FIELDS):
            continue  # not the Sealed Priors table -- some other pipe-prefixed block
        data_lines = block[2:]  # skip the header row and the --- separator row
        return [_split_escaped_row(line) for line in data_lines]
    return []


def parse_classification_table_rows(priors_text: str) -> list[list[str]]:
    """Parse the `## Challenge Classification` table's data rows into raw cell
    lists. Same shape as parse_prior_table_rows, matched on its own header."""
    for block in _split_into_table_blocks(priors_text):
        if len(block) < 2:
            continue
        header_cells = _split_escaped_row(block[0])
        if header_cells != list(CLASSIFICATION_ROW_FIELDS):
            continue  # not the Challenge Classification table -- some other block
        data_lines = block[2:]  # skip the header row and the --- separator row
        return [_split_escaped_row(line) for line in data_lines]
    return []


def check_prior_row_has_seven_columns(rows: list[list[str]]) -> list[str]:
    """Return a failure string per row whose cell count isn't exactly seven
    (G0a) -- an unescaped `|` inside the free-text `concern` cell inflates it."""
    failures: list[str] = []
    for index, row in enumerate(rows):
        if len(row) != len(PRIOR_ROW_FIELDS):
            failures.append(
                f"row {index}: expected {len(PRIOR_ROW_FIELDS)} columns, got {len(row)}: {row!r}"
            )
    return failures


def check_classification_row_has_nine_columns(rows: list[list[str]]) -> list[str]:
    """Return a failure string per row whose cell count isn't exactly eight (G0b)."""
    failures: list[str] = []
    for index, row in enumerate(rows):
        if len(row) != len(CLASSIFICATION_ROW_FIELDS):
            failures.append(
                f"row {index}: expected {len(CLASSIFICATION_ROW_FIELDS)} columns, "
                f"got {len(row)}: {row!r}"
            )
    return failures


def check_seal_boundary_matches_gate_constant(priors_text: str) -> str | None:
    """Return a failure string unless the file's header boundary line equals
    SEAL_BOUNDARY exactly (G1). Reuses parse_series_boundary unchanged -- the
    priors file uses the identical `**Series begins**:` header key, so no
    second regex is introduced."""
    found = parse_series_boundary(priors_text)
    if found is None:
        return "no '**Series begins**:' header line found in CONSULT_PRIORS.md"
    if found != SEAL_BOUNDARY:
        return f"series boundary header {found!r} does not match gate constant {SEAL_BOUNDARY!r}"
    return None


def check_every_post_boundary_consult_has_a_sealed_prior(
    ledger_rows: list[list[str]],
    prior_rows: list[list[str]],
    boundary: str,
) -> list[str]:
    """Return one failure string per violation while checking that every
    post-`boundary` (task-slug, discipline, stage) triple in `ledger_rows` has
    at least one well-formed `## Sealed Priors` row (G2), and that no triple
    carries both a `NONE` row and a listed `P-NN` row (G3).

    Checks, independent of ledger presence:
      - substance -- every prior row's `concern` is non-empty and not a
        placeholder; `source` is `lens` or `prior`; `prior-id` matches
        `P-NN` or is the literal `NONE`
      - G3 -- an explicit-empty `NONE` row cannot coexist with a `P-NN` row
        for the same triple

    Checks, keyed off the ledger:
      - presence -- every post-boundary triple has >=1 matching prior row

    A ledger `timestamp` that doesn't match the ISO 8601 shape is itself a
    failure, rather than being silently mis-ordered against `boundary`.
    """
    failures: list[str] = []
    ledger_index = {field: pos for pos, field in enumerate(LEDGER_ROW_FIELDS)}
    prior_index = {field: pos for pos, field in enumerate(PRIOR_ROW_FIELDS)}

    for row in prior_rows:
        timestamp = row[prior_index["timestamp"]]
        if not _TIMESTAMP_RE.match(timestamp):
            failures.append(f"sealed prior has a malformed timestamp: {timestamp!r}")
        concern = row[prior_index["concern"]]
        if concern.strip().lower() in _PLACEHOLDER_CONCERNS:
            failures.append(f"sealed prior has an empty or placeholder concern: {concern!r}")
        source = row[prior_index["source"]]
        if source not in ("lens", "prior"):
            failures.append(f"sealed prior has an unrecognised source value: {source!r}")
        prior_id = row[prior_index["prior-id"]]
        if not (_PRIOR_ID_RE.match(prior_id) or prior_id == NONE_PRIOR_ID):
            failures.append(f"sealed prior has a malformed prior-id: {prior_id!r}")

    priors_by_triple: dict[tuple[str, str, str], list[str]] = {}
    for row in prior_rows:
        triple = (
            row[prior_index["task-slug"]],
            row[prior_index["discipline"]],
            row[prior_index["stage"]],
        )
        priors_by_triple.setdefault(triple, []).append(row[prior_index["prior-id"]])

    for triple, prior_ids in priors_by_triple.items():
        if NONE_PRIOR_ID in prior_ids and any(pid != NONE_PRIOR_ID for pid in prior_ids):
            failures.append(
                f"consult {triple!r}: a NONE declaration coexists with listed priors: {prior_ids!r}"
            )

    post_boundary_triples: set[tuple[str, str, str]] = set()
    for row in ledger_rows:
        timestamp = row[ledger_index["timestamp"]]
        if not _TIMESTAMP_RE.match(timestamp):
            failures.append(f"ledger row has a malformed timestamp: {timestamp!r}")
            continue
        if timestamp < boundary:
            continue
        post_boundary_triples.add(
            (
                row[ledger_index["task-slug"]],
                row[ledger_index["discipline"]],
                row[ledger_index["stage"]],
            )
        )

    for triple in post_boundary_triples:
        if triple not in priors_by_triple:
            failures.append(
                f"no CONSULT_PRIORS.md Sealed Priors row for post-boundary consult {triple!r}"
            )

    return failures


def check_every_challenge_is_classified(
    ledger_rows: list[list[str]],
    classification_rows: list[list[str]],
    prior_rows: list[list[str]],
    boundary: str,
) -> list[str]:
    """Return one failure string per violation while checking that every
    post-`boundary` `(triple, challenge-id)` pair in `ledger_rows` has exactly
    one classification row present (G4), and that every classification row is
    itself well-formed.

    Checks, independent of ledger presence:
      - substance -- `classification` is `novel` or `matched`; a `matched`
        row's `matched-prior-id` resolves to a Sealed Priors row of the same
        triple; a `novel` row carries an empty `matched-prior-id`;
        `seal-witness` matches `[0-9a-f]{7,40}`
      - consistency -- `seal-witness` agrees across every row of one triple

    Checks, keyed off the ledger:
      - presence -- every post-boundary `(triple, challenge-id)` pair, keyed
        on the *distinct set* so a re-dispositioned challenge with two ledger
        rows still needs exactly one classification row (no use of
        collapse_ledger_rows_to_latest_per_challenge is required)
    """
    failures: list[str] = []
    ledger_index = {field: pos for pos, field in enumerate(LEDGER_ROW_FIELDS)}
    classification_index = {field: pos for pos, field in enumerate(CLASSIFICATION_ROW_FIELDS)}
    prior_index = {field: pos for pos, field in enumerate(PRIOR_ROW_FIELDS)}

    priors_by_triple: dict[tuple[str, str, str], set[str]] = {}
    for row in prior_rows:
        triple = (
            row[prior_index["task-slug"]],
            row[prior_index["discipline"]],
            row[prior_index["stage"]],
        )
        priors_by_triple.setdefault(triple, set()).add(row[prior_index["prior-id"]])

    witness_by_triple: dict[tuple[str, str, str], set[str]] = {}
    for row in classification_rows:
        triple = (
            row[classification_index["task-slug"]],
            row[classification_index["discipline"]],
            row[classification_index["stage"]],
        )
        classification = row[classification_index["classification"]]
        matched_prior_id = row[classification_index["matched-prior-id"]]
        seal_witness = row[classification_index["seal-witness"]]

        if classification not in ("novel", "matched"):
            failures.append(f"classification row has an invalid classification: {classification!r}")
        elif classification == "matched":
            if matched_prior_id not in priors_by_triple.get(triple, set()):
                failures.append(
                    f"consult {triple!r}: matched classification names an absent prior "
                    f"{matched_prior_id!r}"
                )
        elif matched_prior_id:
            failures.append(
                f"consult {triple!r}: novel classification carries a non-empty "
                f"matched-prior-id {matched_prior_id!r}"
            )

        if not _SEAL_WITNESS_RE.match(seal_witness):
            failures.append(f"classification row has a malformed seal-witness: {seal_witness!r}")

        prompt_areas = row[classification_index["prompt-areas"]]
        if not _PROMPT_AREAS_RE.match(prompt_areas):
            failures.append(
                "classification row has a malformed prompt-areas count "
                f"(expected a non-negative integer): {prompt_areas!r}"
            )

        witness_by_triple.setdefault(triple, set()).add(seal_witness)

    for triple, witnesses in witness_by_triple.items():
        if len(witnesses) > 1:
            failures.append(
                f"consult {triple!r}: seal-witness values disagree across rows: "
                f"{sorted(witnesses)!r}"
            )

    classified_pairs: set[tuple[tuple[str, str, str], str]] = set()
    for row in classification_rows:
        triple = (
            row[classification_index["task-slug"]],
            row[classification_index["discipline"]],
            row[classification_index["stage"]],
        )
        classified_pairs.add((triple, row[classification_index["challenge-id"]]))

    post_boundary_pairs: set[tuple[tuple[str, str, str], str]] = set()
    for row in ledger_rows:
        timestamp = row[ledger_index["timestamp"]]
        if not _TIMESTAMP_RE.match(timestamp):
            failures.append(f"ledger row has a malformed timestamp: {timestamp!r}")
            continue
        if timestamp < boundary:
            continue
        triple = (
            row[ledger_index["task-slug"]],
            row[ledger_index["discipline"]],
            row[ledger_index["stage"]],
        )
        post_boundary_pairs.add((triple, row[ledger_index["challenge-id"]]))

    for triple, challenge_id in post_boundary_pairs:
        if (triple, challenge_id) not in classified_pairs:
            failures.append(
                f"no CONSULT_PRIORS.md Challenge Classification row for {challenge_id!r} "
                f"in post-boundary consult {triple!r}"
            )

    return failures


def check_fragment_witness_agrees(fragment_text: str, seal_witness: str) -> str | None:
    """Return a failure string unless the consultant fragment's
    `**Round-0 HEAD:** <sha>` line equals `seal_witness` exactly (G5, the
    live-window independence check -- the one datum in the consult the
    convener did not author)."""
    match = _ROUND0_HEAD_RE.search(fragment_text)
    if match is None:
        return "fragment carries no '**Round-0 HEAD:**' line"
    fragment_sha = match.group(1)
    if fragment_sha != seal_witness:
        return (
            f"fragment witness {fragment_sha!r} disagrees with the recorded "
            f"seal-witness {seal_witness!r}"
        )
    return None


def _rows_for_triple(
    rows: list[list[str]],
    fields: tuple[str, ...],
    triple: tuple[str, str, str],
) -> list[list[str]]:
    """The rows of a `fields`-shaped table whose (task-slug, discipline, stage)
    columns equal `triple`.

    Rows too short to carry the triple are dropped -- they cannot be read at
    all, and G0a/G0b are the gates that report their shape. A row that is too
    *long* (an unescaped pipe) is kept: columns 1-3 are still correct, so it
    matches its triple and fails whatever downstream comparison reads its
    later cells, rather than disappearing from the comparison entirely.
    """
    index = {field: pos for pos, field in enumerate(fields)}
    return [
        row
        for row in rows
        if len(row) >= len(fields)
        and (row[index["task-slug"]], row[index["discipline"]], row[index["stage"]]) == triple
    ]


def _sealed_prior_identities(
    prior_rows: list[list[str]],
    triple: tuple[str, str, str],
    not_after: str | None = None,
) -> set[tuple[str, str, str]]:
    """The `(prior-id, source, concern)` identities sealed for `triple`.

    When `not_after` is supplied, rows timestamped strictly after it are
    dropped -- ISO-8601 UTC strings order correctly under string comparison, so
    no date parsing is needed. That scoping is what lets a legitimate Round-3
    re-seal append further rows without failing the equality below.
    """
    index = {field: pos for pos, field in enumerate(PRIOR_ROW_FIELDS)}
    identities: set[tuple[str, str, str]] = set()
    for row in _rows_for_triple(prior_rows, PRIOR_ROW_FIELDS, triple):
        if not_after is not None and row[index["timestamp"]] > not_after:
            continue
        identities.add((row[index["prior-id"]], row[index["source"]], row[index["concern"]]))
    return identities


# The admission a NONE tombstone owes the cost series (C3 below).
UNSEALED_COST_NOTE_MARKER = "UNSEALED:"


def _seal_declares_no_priors(
    working_prior_rows: list[list[str]], triple: tuple[str, str, str]
) -> bool:
    """True when the working file's seal for `triple` declares `prior-id: NONE`.

    Deliberately `any`, not "exactly one NONE row": a NONE row sitting beside a
    listed prior must enter the exemption path so C1 can fail it loudly, rather
    than quietly falling through to a set-equality comparison that a convener
    could satisfy by appending.
    """
    index = {field: pos for pos, field in enumerate(PRIOR_ROW_FIELDS)}
    return any(
        row[index["prior-id"]] == NONE_PRIOR_ID
        for row in _rows_for_triple(working_prior_rows, PRIOR_ROW_FIELDS, triple)
    )


def check_none_seal_is_exclusive(
    prior_rows: list[list[str]], triple: tuple[str, str, str]
) -> str | None:
    """C1 of the G6 NONE-tombstone exemption: a `prior-id: NONE` declaration
    must be the only Sealed Priors row for its triple.

    `.ai-state/CONSULT_PRIORS.md` § Column Definitions already states the rule;
    making it a *precondition of the exemption* is what closes the cheat the
    exemption releases. G6 exists to catch a convener who reads the challenges,
    appends a prior, and cites it as `matched`; under the exemption that
    convener cannot append, because the appended row breaks exclusivity here.
    """
    rows = _rows_for_triple(prior_rows, PRIOR_ROW_FIELDS, triple)
    index = {field: pos for pos, field in enumerate(PRIOR_ROW_FIELDS)}
    prior_ids = [row[index["prior-id"]] for row in rows]
    if NONE_PRIOR_ID not in prior_ids or len(rows) == 1:
        return None
    listed = sorted(prior_id for prior_id in prior_ids if prior_id != NONE_PRIOR_ID)
    return (
        f"sealed priors for {triple!r} declare {NONE_PRIOR_ID} alongside listed prior(s) "
        f"{listed}; the empty declaration must be the only Sealed Priors row for its triple"
    )


def check_none_seal_challenges_are_all_novel(
    classification_rows: list[list[str]], triple: tuple[str, str, str]
) -> str | None:
    """C2 of the G6 NONE-tombstone exemption: every Challenge Classification row
    for the triple must be `novel` with an empty `matched-prior-id`.

    A `matched` classification under a NONE seal is a contradiction -- it names
    a prior the seal says does not exist -- and must fail loudly rather than be
    released along with the set-equality assertion.

    Row *presence* is G3's contract (`check_every_challenge_is_classified`), not
    this one's: a triple whose classifications have not been written yet is not
    what this check is about. Called only from G6's exemption path, so "the
    triple seals NONE" is a premise here, not something this check re-derives.
    """
    rows = _rows_for_triple(classification_rows, CLASSIFICATION_ROW_FIELDS, triple)
    index = {field: pos for pos, field in enumerate(CLASSIFICATION_ROW_FIELDS)}
    offenders = [
        f"{row[index['challenge-id']]} ({row[index['classification']]!r}, "
        f"matched-prior-id {row[index['matched-prior-id']]!r})"
        for row in rows
        if row[index["classification"]] != "novel" or row[index["matched-prior-id"]]
    ]
    if not offenders:
        return None
    return (
        f"{triple!r} takes the empty-seal ({NONE_PRIOR_ID}) exemption but classifies "
        f"{', '.join(offenders)}; under an empty seal every challenge is novel by "
        "construction, with no prior to match"
    )


def check_none_seal_cost_note_declares_unsealed(
    cost_rows: list[list[str]], triple: tuple[str, str, str]
) -> str | None:
    """C3 of the G6 NONE-tombstone exemption: the triple's `CONSULT_COSTS.md`
    row must carry the `UNSEALED:` marker in its `notes` cell.

    The admission has to exist in the sibling file, where a cost-series reader
    meets it, and not only in the tombstone's own prose -- a novelty rate read
    off an unsealed consult is not informative about the discipline, and the
    reader of the cost series is the one who needs to know that.

    Presence anywhere in the cell, not a leading prefix: the shipped
    `adr-living-view` row states the marker after an introductory sentence, and
    demanding a fixed position would require re-editing an append-only file to
    satisfy a gate -- the exact pressure this exemption exists to remove.
    """
    rows = _rows_for_triple(cost_rows, COST_ROW_FIELDS, triple)
    index = {field: pos for pos, field in enumerate(COST_ROW_FIELDS)}
    if not rows:
        return (
            f"{triple!r} takes the empty-seal ({NONE_PRIOR_ID}) exemption but has no "
            f"CONSULT_COSTS.md row; the exemption is paid for by an "
            f"'{UNSEALED_COST_NOTE_MARKER}' admission in the cost series, so there is "
            "nowhere for that admission to live"
        )
    if any(UNSEALED_COST_NOTE_MARKER in row[index["notes"]] for row in rows):
        return None
    return (
        f"{triple!r} takes the empty-seal ({NONE_PRIOR_ID}) exemption but no "
        f"CONSULT_COSTS.md row for it carries the '{UNSEALED_COST_NOTE_MARKER}' marker in "
        "its notes cell; the empty seal is an admission the cost series must state, not "
        "only the tombstone's own prose"
    )


def check_witness_priors_equal_working_priors(
    witness_prior_rows: list[list[str]],
    working_prior_rows: list[list[str]],
    triple: tuple[str, str, str],
    *,
    classification_rows: list[list[str]] | None = None,
    cost_rows: list[list[str]] | None = None,
) -> str | None:
    """G6. Assert **set equality** -- not containment -- between the sealed
    priors in the witness commit and those in the working file, for `triple`.

    Containment was the original formulation and it failed open in two distinct
    ways, both found by a live `statistician` consult against this design and
    both reproduced before this rewrite:

    1. The original predicate was three unanchored substring tests over the
       whole file (`task_slug in blob and discipline in blob and stage in
       blob`). Both tables carry those three columns, so a witness file holding
       only *Challenge Classification* rows for the triple -- and zero sealed
       priors -- satisfied it.
    2. Containment is monotone under appending. A convener that reads the
       challenges, appends a prior for the same triple, and cites it as
       `matched` fabricates nothing: the fragment is untouched, the sha is
       genuine, and the witness commit still *contains* the original rows. The
       seal then binds the existence of a prior list but not its contents --
       and the contents are the whole measurement.

    Set equality detects an addition and a deletion. Scoping the working-side
    set by the witness commit's own date preserves the legitimate re-seal path.

    **Vacuity exemption** (the ADR narrowing dec-310's G6 clause). A triple whose
    working seal is the empty `prior-id: NONE` declaration is exempt from the equality
    assertion, because the assertion has no content there: the recorded
    seal-witness is the consultant's Round-0 HEAD, a commit that by
    construction predates the consult, so a tombstone recorded honestly after
    the fact can never appear in it. G6-as-written therefore admitted no honest
    tombstone -- only a witness re-pointed to a later commit, which is the
    drift it exists to detect. The exemption is *paid for* by C1, C2 and C3
    above, each of which is an assertion the unexempt path never made; the
    evidence they need is supplied through `classification_rows` and
    `cost_rows`. Omitting either fails closed: an exemption whose payment
    cannot be checked is not granted.
    """
    if _seal_declares_no_priors(working_prior_rows, triple):
        if classification_rows is None or cost_rows is None:
            return (
                f"{triple!r} seals {NONE_PRIOR_ID}, but the compensating evidence for the "
                "vacuity exemption was not supplied (classification_rows and cost_rows); "
                "the exemption is granted only where C1-C3 can be checked"
            )
        for compensating_failure in (
            check_none_seal_is_exclusive(working_prior_rows, triple),
            check_none_seal_challenges_are_all_novel(classification_rows, triple),
            check_none_seal_cost_note_declares_unsealed(cost_rows, triple),
        ):
            if compensating_failure is not None:
                return compensating_failure
        return None

    sealed = _sealed_prior_identities(witness_prior_rows, triple)

    # A legitimate later re-seal appends rows *after* everything the witness
    # sealed, so the scope boundary is the witness set's own latest timestamp --
    # not the git commit date. An earlier revision compared against
    # `git show -s --format=%cI`, which emits the committer's LOCAL offset
    # ("...-07:00") while these rows are UTC ("...Z"). String-comparing across
    # two offset representations is meaningless: it read a row 17 minutes older
    # than the commit as newer, exempted every sealed prior, and reported all
    # eight as deleted on the first real run. Deriving the boundary from the
    # rows keeps both sides in one representation and removes git from the
    # comparison entirely.
    prior_index = {field: pos for pos, field in enumerate(PRIOR_ROW_FIELDS)}

    # Fail closed on a non-canonical timestamp; never exempt on one. The
    # `not_after` scoping below is a *lexical* comparison, so an offset form
    # ("2026-07-31T07:00:00+02:00") sorts as later than the same instant
    # written in UTC ("2026-07-31T05:00:00Z") -- which would silently exempt a
    # row appended AFTER the seal as though it were a legitimate later
    # re-seal. That is the precise cheat this check exists to catch, defeated
    # by one character. The earlier revision fixed the git-date-vs-row-
    # timestamp seam and left this row-vs-row one open, because its canaries
    # supplied both sides in a single representation.
    #
    # Both sides are validated here, not only in G2: G2 parses the *working*
    # file, and never sees the witness commit's copy.
    for side, rows in (("witness", witness_prior_rows), ("working", working_prior_rows)):
        for row in rows:
            if (
                row[prior_index["task-slug"]],
                row[prior_index["discipline"]],
                row[prior_index["stage"]],
            ) != triple:
                continue
            stamp = row[prior_index["timestamp"]]
            if not _TIMESTAMP_RE.match(stamp):
                return (
                    f"sealed prior for {triple!r} in the {side} set carries a non-canonical "
                    f"timestamp {stamp!r}; expected ISO 8601 UTC 'YYYY-MM-DDTHH:MM:SSZ'. The "
                    "witness scope comparison is lexical, so any other representation would "
                    "silently exempt the row instead of comparing it"
                )

    sealed_timestamps = [
        row[prior_index["timestamp"]]
        for row in witness_prior_rows
        if (
            row[prior_index["task-slug"]],
            row[prior_index["discipline"]],
            row[prior_index["stage"]],
        )
        == triple
    ]
    not_after = max(sealed_timestamps) if sealed_timestamps else None
    working = _sealed_prior_identities(working_prior_rows, triple, not_after=not_after)

    added = {identity[0] for identity in working - sealed}
    removed = {identity[0] for identity in sealed - working}
    if not added and not removed:
        return None

    parts = [f"sealed priors for {triple!r} disagree with the witness commit"]
    if added:
        parts.append(f"present in the working file but not sealed: {sorted(added)}")
    if removed:
        parts.append(f"sealed but absent from the working file: {sorted(removed)}")
    return "; ".join(parts)


def novelty_rate_by_consult(
    classification_rows: list[list[str]], discipline: str
) -> dict[tuple[str, str], tuple[int, int]]:
    """`{(task-slug, stage): (novel, total)}` for `discipline` -- the criterion's
    statistic, computed per consult and never pooled.

    This is the authoritative implementation of the primary recipe published in
    `.ai-state/CONSULT_PRIORS.md` § Reading the series; if the shell recipe and
    this function disagree, this function is correct.

    Challenges cluster within a consult -- one convener, one sealed list, one
    draft -- so the consult is the independent unit. Pooling challenges across
    consults reintroduces exactly the defect `dec-304` removed from the sibling
    dismiss rate, and it is not a small effect: see the canary below, where a
    talkative consult drags the pooled figure 0.27 away from the consult mean.
    """
    index = {field: pos for pos, field in enumerate(CLASSIFICATION_ROW_FIELDS)}
    by_consult: dict[tuple[str, str], tuple[int, int]] = {}
    for row in classification_rows:
        if row[index["discipline"]] != discipline:
            continue
        classification = row[index["classification"]]
        if classification not in ("novel", "matched"):
            continue
        key = (row[index["task-slug"]], row[index["stage"]])
        novel, total = by_consult.get(key, (0, 0))
        by_consult[key] = (novel + (classification == "novel"), total + 1)
    return by_consult


# ---------------------------------------------------------------------------
# Canaries: the six checks above fail on known-bad inputs. Each bad input is
# valid in every dimension except the one under test -- the ledger row is
# eleven columns, the prior rows are seven, the classification rows are
# eight, every timestamp is post-boundary, every sha is [0-9a-f]{7,40}.
# ---------------------------------------------------------------------------


def test_flags_a_post_boundary_consult_with_no_sealed_prior() -> None:
    """Canary: a post-boundary ledger consult with zero matching Sealed
    Priors rows is flagged -- the omission this gate exists to catch."""
    ledger_row = (
        "| 2026-08-01T12:00:00Z | task-a | statistician | architecture | CH-01 | "
        "a claim | a decision | switch-now | dec-999 | opus | standard |"
    )
    ledger_table = f"{_LEDGER_HEADER_ROW}\n{_LEDGER_SEPARATOR_ROW}\n{ledger_row}\n"
    priors_table = f"{_PRIOR_HEADER_ROW}\n{_PRIOR_SEPARATOR_ROW}\n"  # zero data rows

    ledger_rows = parse_ledger_table_rows(ledger_table)
    prior_rows = parse_prior_table_rows(priors_table)
    failures = check_every_post_boundary_consult_has_a_sealed_prior(
        ledger_rows, prior_rows, SEAL_BOUNDARY
    )

    assert len(failures) == 1, f"expected exactly one failure; got: {failures}"
    assert "'task-a'" in failures[0]
    assert "'statistician'" in failures[0]
    assert "'architecture'" in failures[0]


def test_flags_a_sealed_prior_whose_concern_cell_is_a_placeholder() -> None:
    """Canary: substance over structure -- an empty, 'n/a', or 'TBD' concern
    cell is flagged, not just an absent row."""
    bad_rows = [
        "| 2026-07-31T02:00:00Z | task-a | statistician | architecture | P-01 | lens |  |",
        "| 2026-07-31T02:00:00Z | task-a | statistician | architecture | P-02 | lens | n/a |",
        "| 2026-07-31T02:00:00Z | task-a | statistician | architecture | P-03 | lens | TBD |",
    ]
    priors_table = f"{_PRIOR_HEADER_ROW}\n{_PRIOR_SEPARATOR_ROW}\n" + "\n".join(bad_rows) + "\n"

    prior_rows = parse_prior_table_rows(priors_table)
    failures = check_every_post_boundary_consult_has_a_sealed_prior([], prior_rows, SEAL_BOUNDARY)

    assert len(failures) == 3, (
        f"expected exactly three failures (one per placeholder concern); got: {failures}"
    )


def test_flags_a_none_declaration_coexisting_with_listed_priors() -> None:
    """Canary: G3 -- an explicit-empty NONE declaration cannot coexist with a
    listed P-NN prior for the same triple."""
    rows = [
        "| 2026-07-31T02:00:00Z | task-a | statistician | architecture | P-01 | lens | "
        "a real concern |",
        "| 2026-07-31T02:01:00Z | task-a | statistician | architecture | NONE | lens | "
        "pass surfaced nothing |",
    ]
    priors_table = f"{_PRIOR_HEADER_ROW}\n{_PRIOR_SEPARATOR_ROW}\n" + "\n".join(rows) + "\n"

    prior_rows = parse_prior_table_rows(priors_table)
    failures = check_every_post_boundary_consult_has_a_sealed_prior([], prior_rows, SEAL_BOUNDARY)

    assert len(failures) == 1, f"expected exactly one failure; got: {failures}"
    assert "NONE" in failures[0]


def test_flags_a_sealed_prior_with_an_unrecognised_source_value() -> None:
    """Canary: `source` must be `lens` or `prior` -- anything else is flagged."""
    row = (
        "| 2026-07-31T02:00:00Z | task-a | statistician | architecture | P-01 | "
        "intuition | a real concern |"
    )
    priors_table = f"{_PRIOR_HEADER_ROW}\n{_PRIOR_SEPARATOR_ROW}\n{row}\n"

    prior_rows = parse_prior_table_rows(priors_table)
    failures = check_every_post_boundary_consult_has_a_sealed_prior([], prior_rows, SEAL_BOUNDARY)

    assert len(failures) == 1, f"expected exactly one failure; got: {failures}"
    assert "'intuition'" in failures[0]


def test_flags_a_challenge_with_no_classification_row() -> None:
    """Canary: a post-boundary challenge with zero classification rows is
    flagged, naming the unclassified challenge-id."""
    ledger_row = (
        "| 2026-08-01T12:00:00Z | task-a | statistician | architecture | CH-01 | "
        "a claim | a decision | switch-now | dec-999 | opus | standard |"
    )
    ledger_table = f"{_LEDGER_HEADER_ROW}\n{_LEDGER_SEPARATOR_ROW}\n{ledger_row}\n"
    prior_row = (
        "| 2026-07-31T02:00:00Z | task-a | statistician | architecture | P-01 | lens | "
        "a real concern |"
    )
    priors_table = f"{_PRIOR_HEADER_ROW}\n{_PRIOR_SEPARATOR_ROW}\n{prior_row}\n"
    classification_table = (
        f"{_CLASSIFICATION_HEADER_ROW}\n{_CLASSIFICATION_SEPARATOR_ROW}\n"  # zero data rows
    )

    ledger_rows = parse_ledger_table_rows(ledger_table)
    prior_rows = parse_prior_table_rows(priors_table)
    classification_rows = parse_classification_table_rows(classification_table)
    failures = check_every_challenge_is_classified(
        ledger_rows, classification_rows, prior_rows, SEAL_BOUNDARY
    )

    assert len(failures) == 1, f"expected exactly one failure; got: {failures}"
    assert "'CH-01'" in failures[0]


def test_flags_a_matched_classification_naming_an_absent_prior() -> None:
    """Canary: a `matched` classification's `matched-prior-id` must resolve
    to a Sealed Priors row of the same triple."""
    prior_row = (
        "| 2026-07-31T02:00:00Z | task-a | statistician | architecture | P-01 | lens | "
        "a real concern |"
    )
    priors_table = f"{_PRIOR_HEADER_ROW}\n{_PRIOR_SEPARATOR_ROW}\n{prior_row}\n"
    classification_row = (
        "| 2026-08-01T12:05:00Z | task-a | statistician | architecture | CH-01 | matched | "
        "P-09 | 0123456789abcdef0123456789abcdef01234567 | 7 |"
    )
    classification_table = (
        f"{_CLASSIFICATION_HEADER_ROW}\n{_CLASSIFICATION_SEPARATOR_ROW}\n{classification_row}\n"
    )

    prior_rows = parse_prior_table_rows(priors_table)
    classification_rows = parse_classification_table_rows(classification_table)
    failures = check_every_challenge_is_classified(
        [], classification_rows, prior_rows, SEAL_BOUNDARY
    )

    assert len(failures) == 1, f"expected exactly one failure; got: {failures}"
    assert "'P-09'" in failures[0]


def test_flags_a_novel_classification_carrying_a_matched_prior_id() -> None:
    """Canary: a `novel` classification must carry an empty `matched-prior-id`."""
    prior_row = (
        "| 2026-07-31T02:00:00Z | task-a | statistician | architecture | P-01 | lens | "
        "a real concern |"
    )
    priors_table = f"{_PRIOR_HEADER_ROW}\n{_PRIOR_SEPARATOR_ROW}\n{prior_row}\n"
    classification_row = (
        "| 2026-08-01T12:05:00Z | task-a | statistician | architecture | CH-01 | novel | "
        "P-01 | 0123456789abcdef0123456789abcdef01234567 | 7 |"
    )
    classification_table = (
        f"{_CLASSIFICATION_HEADER_ROW}\n{_CLASSIFICATION_SEPARATOR_ROW}\n{classification_row}\n"
    )

    prior_rows = parse_prior_table_rows(priors_table)
    classification_rows = parse_classification_table_rows(classification_table)
    failures = check_every_challenge_is_classified(
        [], classification_rows, prior_rows, SEAL_BOUNDARY
    )

    assert len(failures) == 1, f"expected exactly one failure; got: {failures}"


def test_pooled_and_per_consult_novelty_rates_diverge_on_the_consults_worked_example() -> None:
    """The settling test a live `statistician` consult named, committed.

    That consult found the file's published recipes computed the **pooled**
    challenge-level rate `dec-304` removed, while the mandated consult-level
    denominator appeared only in prose one section away. It supplied the
    arithmetic and the falsification condition verbatim: two consults, one with
    12 challenges at 11 novel and one with 3 at 0 novel, give pooled 11/15 =
    0.73 against a consult mean of 0.46 -- *"if a reader following the published
    instructions can reach 0.46, I am wrong."*

    This test pins that divergence so the two readings cannot quietly converge
    in a reader's head, and so a future edit to `novelty_rate_by_consult` that
    silently pools is caught.
    """
    rows: list[str] = []
    for n in range(12):
        classification = "novel" if n < 11 else "matched"
        prior = "" if classification == "novel" else "P-01"
        rows.append(
            f"| 2026-08-01T12:{n:02d}:00Z | talkative | statistician | architecture | "
            f"CH-{n:02d} | {classification} | {prior} | aaaaaaa | 7 |"
        )
    for n in range(3):
        rows.append(
            f"| 2026-08-02T12:{n:02d}:00Z | quiet | statistician | architecture | "
            f"CH-{n:02d} | matched | P-01 | bbbbbbb | 7 |"
        )
    table = (
        f"{_CLASSIFICATION_HEADER_ROW}\n{_CLASSIFICATION_SEPARATOR_ROW}\n" + "\n".join(rows) + "\n"
    )

    by_consult = novelty_rate_by_consult(parse_classification_table_rows(table), "statistician")

    assert by_consult[("talkative", "architecture")] == (11, 12)
    assert by_consult[("quiet", "architecture")] == (0, 3)

    per_consult = [novel / total for novel, total in by_consult.values()]
    consult_mean = sum(per_consult) / len(per_consult)
    pooled = sum(n for n, _ in by_consult.values()) / sum(t for _, t in by_consult.values())

    assert round(pooled, 2) == 0.73, f"pooled rate should be 0.73; got {pooled:.4f}"
    assert round(consult_mean, 2) == 0.46, f"consult mean should be 0.46; got {consult_mean:.4f}"
    assert round(pooled - consult_mean, 2) == 0.27, (
        "the pooled reading must remain materially different from the consult mean -- "
        "if this converges, the fixture no longer exercises the defect it guards"
    )


def test_flags_a_classification_row_whose_prompt_areas_cell_is_not_a_count() -> None:
    """Canary: `prompt-areas` must be a non-negative integer.

    The column exists because the convener authors the *spawn prompt* as well
    as the sealed list, and prompt specificity moves the novelty rate without
    touching a sealed row or a classification -- so it trips no other gate and
    leaves no trace inside the instrumented files. A prose placeholder here
    would make the series unstratifiable on its largest uncontrolled covariate
    while still looking populated, which is the hollow-artifact shape
    `gate-liveness.md` names."""
    prior_row = (
        "| 2026-07-31T02:00:00Z | task-a | statistician | architecture | P-01 | lens | "
        "a real concern |"
    )
    priors_table = f"{_PRIOR_HEADER_ROW}\n{_PRIOR_SEPARATOR_ROW}\n{prior_row}\n"
    classification_row = (
        "| 2026-08-01T12:05:00Z | task-a | statistician | architecture | CH-01 | novel | "
        " | 0123456789abcdef0123456789abcdef01234567 | several |"
    )
    classification_table = (
        f"{_CLASSIFICATION_HEADER_ROW}\n{_CLASSIFICATION_SEPARATOR_ROW}\n{classification_row}\n"
    )

    prior_rows = parse_prior_table_rows(priors_table)
    classification_rows = parse_classification_table_rows(classification_table)
    failures = check_every_challenge_is_classified(
        [], classification_rows, prior_rows, SEAL_BOUNDARY
    )

    assert len(failures) == 1, f"expected exactly one failure; got: {failures}"
    assert "prompt-areas" in failures[0]
    assert "several" in failures[0]


def test_flags_seal_witness_values_disagreeing_within_one_consult() -> None:
    """Canary: `seal-witness` must agree across every classification row of
    one triple -- disagreement means the fragment was fabricated or the
    triple keys collided."""
    rows = [
        "| 2026-08-01T12:05:00Z | task-a | statistician | architecture | CH-01 | novel | "
        " | aaaaaaa | 7 |",
        "| 2026-08-01T12:06:00Z | task-a | statistician | architecture | CH-02 | novel | "
        " | bbbbbbb | 7 |",
    ]
    classification_table = (
        f"{_CLASSIFICATION_HEADER_ROW}\n{_CLASSIFICATION_SEPARATOR_ROW}\n" + "\n".join(rows) + "\n"
    )

    classification_rows = parse_classification_table_rows(classification_table)
    failures = check_every_challenge_is_classified([], classification_rows, [], SEAL_BOUNDARY)

    assert len(failures) == 1, f"expected exactly one failure; got: {failures}"
    assert "aaaaaaa" in failures[0]
    assert "bbbbbbb" in failures[0]


def test_flags_a_prior_row_with_an_unescaped_pipe_inflating_the_column_count() -> None:
    """Canary: an unescaped pipe in the `concern` cell inflates the column
    count past seven -- the same defect class as the ledger's eleven-column
    check."""
    bad_row = (
        "| 2026-07-31T02:00:00Z | task-a | statistician | architecture | P-01 | lens | "
        "a concern with an unescaped | pipe |"
    )
    table = f"{_PRIOR_HEADER_ROW}\n{_PRIOR_SEPARATOR_ROW}\n{bad_row}\n"
    rows = parse_prior_table_rows(table)
    failures = check_prior_row_has_seven_columns(rows)

    assert len(failures) == 1, f"expected exactly one failure; got: {failures}"
    assert "got 8" in failures[0], f"expected the row to report 8 cells; got: {failures}"


def test_flags_a_classification_row_with_an_unescaped_pipe_inflating_the_column_count() -> None:
    """Canary: an unescaped pipe inflates a classification row past nine cells.

    Added by the orchestrator during verification, not by the plan: neutering
    each of the six checks in turn showed that
    `check_classification_row_has_nine_columns` was the one check whose
    canaries did not exist -- zero tests went red when it was stubbed. The gate
    specification listed the check but omitted its canary, and
    `test_gate_canary_coverage.py` could not catch that because it asks whether
    a *file* contains a canary, not whether each *check* has one.
    """
    bad_row = (
        "| 2026-08-01T12:00:00Z | task-a | statistician | architecture | CH-01 | matched | "
        "P-01 | 0123456789abcdef0123456789abcdef01234567 | 7 with an unescaped | pipe |"
    )
    table = f"{_CLASSIFICATION_HEADER_ROW}\n{_CLASSIFICATION_SEPARATOR_ROW}\n{bad_row}\n"
    rows = parse_classification_table_rows(table)
    failures = check_classification_row_has_nine_columns(rows)

    assert len(failures) == 1, f"expected exactly one failure; got: {failures}"
    assert "got 10" in failures[0], f"expected the row to report 10 cells; got: {failures}"


def test_accepts_a_prior_row_whose_escaped_pipe_stays_inside_one_cell() -> None:
    r"""The documented `\|` escape in a `concern` cell parses to exactly seven
    columns and yields a literal pipe in the cell value.

    The payload is the real one: `sidecar-placement`'s P-02 concern, as the
    `41903c16` seal witness records it. Written to the convention the file's own
    § Column Definitions prescribes, it parsed to eight columns under the bare
    splitter -- so the only way to make the row-shape gate green was to edit a
    sealed cell, which is what happened."""
    escaped_row = (
        r"| 2026-07-31T02:00:00Z | task-a | statistician | architecture | P-02 | lens | "
        r"Manifest `shadows: relpath -> kind(dir\|file)` is boolean-blind |"
    )
    table = f"{_PRIOR_HEADER_ROW}\n{_PRIOR_SEPARATOR_ROW}\n{escaped_row}\n"
    rows = parse_prior_table_rows(table)

    assert len(rows) == 1, f"expected one parsed row; got: {rows!r}"
    assert len(rows[0]) == len(PRIOR_ROW_FIELDS), (
        f"an escaped pipe must not split a cell; got {len(rows[0])} cells: {rows[0]!r}"
    )
    concern = rows[0][PRIOR_ROW_FIELDS.index("concern")]
    assert concern == "Manifest `shadows: relpath -> kind(dir|file)` is boolean-blind", (
        f"the escape must be unescaped to a literal pipe in the cell value; got: {concern!r}"
    )
    assert not check_prior_row_has_seven_columns(rows)


def test_accepts_a_classification_row_whose_escaped_pipe_stays_inside_one_cell() -> None:
    r"""The documented `\|` escape parses to exactly nine columns and yields a
    literal pipe in the cell value."""
    escaped_row = (
        r"| 2026-08-01T12:00:00Z | task-a | statistician | architecture | CH-01\|a | novel | "
        r" | 0123456789abcdef0123456789abcdef01234567 | 7 |"
    )
    table = f"{_CLASSIFICATION_HEADER_ROW}\n{_CLASSIFICATION_SEPARATOR_ROW}\n{escaped_row}\n"
    rows = parse_classification_table_rows(table)

    assert len(rows) == 1, f"expected one parsed row; got: {rows!r}"
    assert len(rows[0]) == len(CLASSIFICATION_ROW_FIELDS), (
        f"an escaped pipe must not split a cell; got {len(rows[0])} cells: {rows[0]!r}"
    )
    challenge_id = rows[0][CLASSIFICATION_ROW_FIELDS.index("challenge-id")]
    assert challenge_id == "CH-01|a", (
        f"the escape must be unescaped to a literal pipe in the cell value; got: {challenge_id!r}"
    )
    assert not check_classification_row_has_nine_columns(rows)


def test_flags_the_seal_boundary_header_missing_from_the_priors_file() -> None:
    """Canary: a priors file with no `**Series begins**:` header line is
    flagged -- the gate's file-absent-or-header-absent case must fail, not
    pass silently."""
    priors_text = (
        f"# Consultation Prior Register\n\n{_PRIOR_HEADER_ROW}\n{_PRIOR_SEPARATOR_ROW}\n\n"
        f"{_CLASSIFICATION_HEADER_ROW}\n{_CLASSIFICATION_SEPARATOR_ROW}\n"
    )
    result = check_seal_boundary_matches_gate_constant(priors_text)
    assert result is not None, (
        "check_seal_boundary_matches_gate_constant must flag a priors file with no "
        "'**Series begins**:' header line; got None"
    )


def test_flags_a_fragment_witness_disagreeing_with_the_recorded_seal_witness() -> None:
    """Canary: the consultant fragment's `**Round-0 HEAD:**` sha must equal
    the recorded seal-witness exactly (G5, the live-window independence
    check)."""
    fragment_text = (
        "**Discipline:** statistician\n**Round-0 HEAD:** deadbeefdeadbeefdeadbeefdeadbeefdeadbeef\n"
    )
    recorded_seal_witness = "0123456789abcdef0123456789abcdef01234567"

    result = check_fragment_witness_agrees(fragment_text, recorded_seal_witness)

    assert result is not None, (
        "check_fragment_witness_agrees must flag a fragment witness that disagrees "
        "with the recorded seal-witness; got None"
    )
    assert "deadbeefdeadbeefdeadbeefdeadbeefdeadbeef" in result
    assert "0123456789abcdef0123456789abcdef01234567" in result


_G6_TRIPLE = ("task-a", "statistician", "architecture")


def _prior_row(prior_id: str, concern: str, timestamp: str = "2026-08-01T10:00:00Z") -> list[str]:
    """One well-formed Sealed Priors row for `_G6_TRIPLE`."""
    return [timestamp, "task-a", "statistician", "architecture", prior_id, "lens", concern]


def test_flags_a_witness_holding_no_sealed_priors_for_the_triple() -> None:
    """Canary for the defect the original containment form shipped with: a
    witness commit carrying *Challenge Classification* rows for the triple but
    **zero** Sealed Priors rows for it.

    The superseded predicate was three unanchored substring tests over the
    whole file; both tables carry `task-slug`, `discipline` and `stage`, so it
    returned True on exactly this input. Reproduced against the real file
    before the rewrite."""
    working = [_prior_row("P-01", "a real sealed concern")]

    result = check_witness_priors_equal_working_priors([], working, _G6_TRIPLE)

    assert result is not None, (
        "G6 must flag a witness commit with no sealed priors for the triple; got None -- "
        "this is the fail-open the substring form shipped with"
    )
    assert "P-01" in result


def test_flags_a_prior_appended_after_the_witness_commit() -> None:
    """Canary for the cheat the seal exists to prevent: a convener reads the
    challenges, appends a prior for the same triple, and cites it as `matched`.

    Nothing is fabricated -- the fragment is untouched and the sha is genuine --
    so only set equality catches it. Containment cannot: appending only ever
    increases presence."""
    sealed = [_prior_row("P-01", "sealed before the spawn")]
    working = sealed + [_prior_row("P-02", "appended after reading the challenges")]

    result = check_witness_priors_equal_working_priors(sealed, working, _G6_TRIPLE)

    assert result is not None, (
        "G6 must flag a prior appended after the witness commit; got None -- "
        "containment is monotone under appending and cannot detect an addition"
    )
    assert "P-02" in result
    assert "not sealed" in result


def test_flags_a_prior_appended_after_the_seal_in_an_offset_timezone() -> None:
    """Canary for the representation seam, not the ordering logic.

    The bad input is the SAME cheat as the canary above -- a prior appended
    after reading the challenges -- written with a UTC offset instead of `Z`.
    `2026-08-01T12:00:00+02:00` is `10:00:00Z`, i.e. exactly the seal instant
    and therefore *not* a later re-seal; lexically, though, `1` sorts after
    `0` and the row was silently exempted.

    This is the defect class the previous revision moved rather than removed:
    it fixed a git-date-vs-row-timestamp comparison and left the resulting
    row-vs-row one open, because every canary supplied both sides in a single
    representation. A canary that cannot express the mismatch cannot catch it,
    so this one supplies the two operands in two representations on purpose.
    """
    sealed = [_prior_row("P-01", "sealed before the spawn")]  # 2026-08-01T10:00:00Z
    working = sealed + [
        _prior_row(
            "P-02",
            "appended after reading the challenges, stamped in +02:00",
            timestamp="2026-08-01T12:00:00+02:00",
        )
    ]

    result = check_witness_priors_equal_working_priors(sealed, working, _G6_TRIPLE)

    assert result is not None, (
        "G6 must flag a prior whose timestamp is not canonical UTC; got None -- "
        "the witness scope comparison is lexical, so an offset form silently "
        "exempts the row rather than comparing it"
    )
    assert "non-canonical" in result
    assert "+02:00" in result


def test_flags_a_sealed_prior_with_a_malformed_timestamp() -> None:
    """G2 companion to the canary above: the working file's own rows are
    rejected at parse time, so a non-canonical stamp cannot reach the witness
    comparison in the first place. Defence in depth -- G2 never sees the
    witness commit's copy, which is why G6 validates both sides too."""
    bad_row = (
        "| 2026-08-01T12:00:00+02:00 | task-a | statistician | architecture "
        "| P-01 | lens | a real concern, stamped in +02:00 |"
    )
    priors_table = f"{_PRIOR_HEADER_ROW}\n{_PRIOR_SEPARATOR_ROW}\n{bad_row}\n"

    prior_rows = parse_prior_table_rows(priors_table)
    failures = check_every_post_boundary_consult_has_a_sealed_prior([], prior_rows, SEAL_BOUNDARY)

    assert any("malformed timestamp" in f for f in failures), (
        f"G2 must flag a sealed prior whose timestamp is not ISO 8601 UTC; got {failures!r}"
    )


def test_flags_a_sealed_prior_missing_from_the_working_file() -> None:
    """Canary for the other direction: a row present in the witness commit and
    absent from the working file. The file is documented append-only, so this
    is a deletion -- set equality makes that rule mechanically enforced rather
    than conventional."""
    sealed = [_prior_row("P-01", "sealed"), _prior_row("P-02", "also sealed")]
    working = [_prior_row("P-01", "sealed")]

    result = check_witness_priors_equal_working_priors(sealed, working, _G6_TRIPLE)

    assert result is not None, "G6 must flag a sealed prior deleted from the working file"
    assert "P-02" in result
    assert "absent from the working file" in result


def test_accepts_witness_and_working_priors_that_match_exactly() -> None:
    """Non-firing control: identical sets produce no failure."""
    rows = [_prior_row("P-01", "one"), _prior_row("P-02", "two")]

    assert check_witness_priors_equal_working_priors(rows, list(rows), _G6_TRIPLE) is None


def test_accepts_a_later_reseal_row_scoped_out_by_the_witness_own_latest_timestamp() -> None:
    """Non-firing control: a Round-3 re-seal appends rows later than anything
    the witness sealed, and those must not fail the equality -- otherwise the
    gate forbids a legitimate path and gets disabled within a wave.

    The boundary is the witness set's OWN latest timestamp, not the git commit
    date; see the regression canary below for why."""
    sealed = [_prior_row("P-01", "sealed", timestamp="2026-08-01T10:00:00Z")]
    working = sealed + [_prior_row("P-09", "re-seal", timestamp="2026-08-05T10:00:00Z")]

    assert check_witness_priors_equal_working_priors(sealed, working, _G6_TRIPLE) is None


def test_accepts_identical_sets_whose_rows_postdate_the_witness_commit() -> None:
    """Regression canary for a real failure on this gate's first live run.

    The scoping boundary was originally `git show -s --format=%cI`, which emits
    the committer's LOCAL offset (`2026-07-30T22:42:14-07:00`) while these rows
    are UTC (`2026-07-31T05:25:00Z`). Compared as strings, `31` sorts after
    `30`, so a row seventeen minutes OLDER than the commit read as newer, every
    sealed prior was exempted as a "later re-seal", and the gate reported all
    eight as deleted from a file that was byte-identical.

    The bug survived a canary because that canary supplied both dates in one
    representation. It only appeared on real input, where one side comes from
    git and the other from a human's keyboard. Sets that are equal must pass no
    matter what any clock says."""
    rows = [
        _prior_row("P-01", "one", timestamp="2026-07-31T05:25:00Z"),
        _prior_row("P-02", "two", timestamp="2026-07-31T05:25:00Z"),
    ]

    assert check_witness_priors_equal_working_priors(rows, list(rows), _G6_TRIPLE) is None


def test_flags_a_backdated_prior_sharing_the_witness_latest_timestamp() -> None:
    """Canary: the re-seal exemption must not become the cheat's escape hatch.

    A convener appending a prior after the fact and *backdating* it to the
    instant the real priors carry lands inside the scope boundary, so equality
    still catches it. Only a row strictly later than everything sealed is
    exempt -- which is what an honest re-seal produces."""
    sealed = [_prior_row("P-01", "sealed", timestamp="2026-08-01T10:00:00Z")]
    working = sealed + [_prior_row("P-02", "backdated", timestamp="2026-08-01T10:00:00Z")]

    result = check_witness_priors_equal_working_priors(sealed, working, _G6_TRIPLE)

    assert result is not None, "a backdated prior inside the boundary must still fail"
    assert "P-02" in result


# ---------------------------------------------------------------------------
# G6 vacuity exemption (the ADR narrowing dec-310's G6 clause): a NONE tombstone
# is exempt from the equality assertion, and pays for it with C1, C2 and C3. One canary
# per compensating check, plus one for the fail-closed path -- the exemption
# must never be free, and "free" is exactly what an unchecked carve-out is.
# ---------------------------------------------------------------------------


def _classification_row(
    challenge_id: str,
    classification: str = "novel",
    matched_prior_id: str = "",
    seal_witness: str = "0123456789abcdef0123456789abcdef01234567",
) -> list[str]:
    """One well-formed Challenge Classification row for `_G6_TRIPLE`."""
    return [
        "2026-08-01T12:00:00Z",
        "task-a",
        "statistician",
        "architecture",
        challenge_id,
        classification,
        matched_prior_id,
        seal_witness,
        "5",
    ]


def _cost_row(notes: str) -> list[str]:
    """One well-formed cost row for `_G6_TRIPLE`."""
    return [
        "2026-08-01T12:00:00Z",
        "task-a",
        "statistician",
        "architecture",
        "123456",
        "opus",
        "standard",
        notes,
    ]


_NONE_SEAL = [_prior_row(NONE_PRIOR_ID, "tombstone recorded post-hoc; no priors existed to seal")]
_UNSEALED_NOTE = "UNSEALED: the convener spawned without writing Sealed Priors rows"


def test_flags_a_none_declaration_coexisting_with_a_listed_prior_under_the_exemption() -> None:
    """Canary for C1: appending a listed prior beside the NONE declaration is
    the exact cheat G6 exists to catch, and the exemption must not release it.

    The witness set is empty -- an honest Round-0 HEAD predating the consult --
    so without C1 the exemption would return None and the appended prior would
    ride through unexamined."""
    working = _NONE_SEAL + [_prior_row("P-01", "appended after reading the challenges")]

    result = check_none_seal_is_exclusive(working, _G6_TRIPLE)
    through_gate = check_witness_priors_equal_working_priors(
        [],
        working,
        _G6_TRIPLE,
        classification_rows=[_classification_row("CH-01")],
        cost_rows=[_cost_row(_UNSEALED_NOTE)],
    )

    assert result is not None, "a NONE declaration beside a listed prior must be flagged"
    assert "P-01" in result, f"the failure must name the offending prior; got: {result!r}"
    assert through_gate == result, (
        f"the exemption must surface C1's failure rather than returning None; got: {through_gate!r}"
    )


def test_flags_a_matched_classification_under_a_none_seal() -> None:
    """Canary for C2: a `matched` classification under an empty seal names a
    prior the seal says does not exist -- a contradiction, and the citation half
    of the cheat C1 blocks the append half of."""
    classification_rows = [
        _classification_row("CH-01"),
        _classification_row("CH-02", classification="matched", matched_prior_id="P-01"),
    ]

    result = check_none_seal_challenges_are_all_novel(classification_rows, _G6_TRIPLE)
    through_gate = check_witness_priors_equal_working_priors(
        [],
        _NONE_SEAL,
        _G6_TRIPLE,
        classification_rows=classification_rows,
        cost_rows=[_cost_row(_UNSEALED_NOTE)],
    )

    assert result is not None, "a matched classification under a NONE seal must be flagged"
    assert "CH-02" in result, f"the failure must name the offending challenge; got: {result!r}"
    assert through_gate == result, (
        f"the exemption must surface C2's failure rather than returning None; got: {through_gate!r}"
    )


def test_flags_a_none_seal_whose_cost_note_omits_the_unsealed_marker() -> None:
    """Canary for C3: the admission must reach the cost series, where a reader
    of the novelty rate will meet it -- a tombstone whose sibling cost row reads
    as an ordinary sealed consult is the omission this check exists for."""
    silent_cost_rows = [_cost_row("first consult of the discipline; 8 challenges, 8 switch-now")]

    result = check_none_seal_cost_note_declares_unsealed(silent_cost_rows, _G6_TRIPLE)
    absent = check_none_seal_cost_note_declares_unsealed([], _G6_TRIPLE)
    through_gate = check_witness_priors_equal_working_priors(
        [],
        _NONE_SEAL,
        _G6_TRIPLE,
        classification_rows=[_classification_row("CH-01")],
        cost_rows=silent_cost_rows,
    )

    assert result is not None, "a NONE seal whose cost note omits UNSEALED: must be flagged"
    assert UNSEALED_COST_NOTE_MARKER in result, (
        f"the failure must name the marker the note owes; got: {result!r}"
    )
    assert absent is not None, "a NONE seal with no cost row at all must be flagged too"
    assert through_gate == result, (
        f"the exemption must surface C3's failure rather than returning None; got: {through_gate!r}"
    )


def test_flags_an_exemption_claimed_without_the_compensating_evidence() -> None:
    """Canary for the fail-closed default: a caller that reaches G6 with a NONE
    seal but supplies no classification or cost rows gets a failure, not a free
    pass. An exemption whose payment cannot be checked is not granted -- the
    three-argument call shape must never become the cheap way through."""
    result = check_witness_priors_equal_working_priors([], _NONE_SEAL, _G6_TRIPLE)

    assert result is not None, "an unpaid exemption must fail closed"
    assert "not supplied" in result, f"the failure must name what is missing; got: {result!r}"


def test_accepts_a_none_tombstone_whose_exemption_is_paid_for() -> None:
    """Non-firing control: an honest tombstone -- one NONE row, all-novel
    classifications, an UNSEALED: cost note -- passes G6 without consulting the
    witness commit.

    This is the case G6-as-written could not admit: the recorded seal-witness is
    the consultant's Round-0 HEAD, which predates the consult, so no honest
    post-hoc tombstone can appear in it. Before the exemption, the only green
    path was re-pointing the witness at a later commit."""
    result = check_witness_priors_equal_working_priors(
        [],
        _NONE_SEAL,
        _G6_TRIPLE,
        classification_rows=[_classification_row("CH-01"), _classification_row("CH-02")],
        cost_rows=[_cost_row(_UNSEALED_NOTE)],
    )

    assert result is None, f"a paid-for NONE tombstone must pass G6; got: {result!r}"


# ---------------------------------------------------------------------------
# Non-firing controls: prove the gate does not over-fire.
# ---------------------------------------------------------------------------


def test_accepts_a_pre_boundary_consult_with_no_sealed_prior() -> None:
    """Happy path: a pre-boundary ledger consult with zero matching Sealed
    Priors rows is exempt -- the pre-adoption consults must not turn the
    gate red. The exemption falls out of the boundary rule itself, which is
    why no skip-list is needed."""
    ledger_row = (
        "| 2026-07-31T02:30:00Z | task-a | statistician | architecture | CH-01 | "
        "a claim | a decision | switch-now | dec-309 | opus | high-stakes |"
    )
    ledger_table = f"{_LEDGER_HEADER_ROW}\n{_LEDGER_SEPARATOR_ROW}\n{ledger_row}\n"
    priors_table = f"{_PRIOR_HEADER_ROW}\n{_PRIOR_SEPARATOR_ROW}\n"

    ledger_rows = parse_ledger_table_rows(ledger_table)
    prior_rows = parse_prior_table_rows(priors_table)
    failures = check_every_post_boundary_consult_has_a_sealed_prior(
        ledger_rows, prior_rows, SEAL_BOUNDARY
    )
    assert not failures, f"expected no failures for a pre-boundary consult; got: {failures}"


def test_accepts_a_none_only_seal_as_a_valid_declaration() -> None:
    """Happy path: a single NONE row with a substantive concern cell is a
    valid seal, and a matching novel classification is accepted."""
    ledger_row = (
        "| 2026-08-01T12:00:00Z | task-a | statistician | architecture | CH-01 | "
        "a claim | a decision | switch-now | dec-999 | opus | standard |"
    )
    ledger_table = f"{_LEDGER_HEADER_ROW}\n{_LEDGER_SEPARATOR_ROW}\n{ledger_row}\n"
    prior_row = (
        "| 2026-07-31T02:00:00Z | task-a | statistician | architecture | NONE | lens | "
        "lens pass over the bound skill surfaced no concerns about the draft |"
    )
    priors_table = f"{_PRIOR_HEADER_ROW}\n{_PRIOR_SEPARATOR_ROW}\n{prior_row}\n"
    classification_row = (
        "| 2026-08-01T12:05:00Z | task-a | statistician | architecture | CH-01 | novel | "
        " | 0123456789abcdef0123456789abcdef01234567 | 7 |"
    )
    classification_table = (
        f"{_CLASSIFICATION_HEADER_ROW}\n{_CLASSIFICATION_SEPARATOR_ROW}\n{classification_row}\n"
    )

    ledger_rows = parse_ledger_table_rows(ledger_table)
    prior_rows = parse_prior_table_rows(priors_table)
    classification_rows = parse_classification_table_rows(classification_table)

    prior_failures = check_every_post_boundary_consult_has_a_sealed_prior(
        ledger_rows, prior_rows, SEAL_BOUNDARY
    )
    classification_failures = check_every_challenge_is_classified(
        ledger_rows, classification_rows, prior_rows, SEAL_BOUNDARY
    )
    assert not prior_failures, f"expected no prior failures; got: {prior_failures}"
    assert not classification_failures, (
        f"expected no classification failures; got: {classification_failures}"
    )


def test_accepts_a_superseded_challenge_with_one_classification_row() -> None:
    """Happy path: a Round-3 loop-back re-spawn's re-dispositioned challenge
    (two ledger rows, same triple + challenge-id) still needs exactly one
    classification row -- >=1 satisfies the gate, no double-counting."""
    ledger_rows_text = [
        "| 2026-08-01T12:00:00Z | task-a | statistician | architecture | CH-01 | "
        "a claim | a decision | defer-with-rationale | dec-1 | opus | standard |",
        "| 2026-08-01T14:00:00Z | task-a | statistician | architecture | CH-01 | "
        "a claim | a decision | switch-now | dec-999 | opus | standard |",
    ]
    ledger_table = (
        f"{_LEDGER_HEADER_ROW}\n{_LEDGER_SEPARATOR_ROW}\n" + "\n".join(ledger_rows_text) + "\n"
    )
    classification_row = (
        "| 2026-08-01T14:05:00Z | task-a | statistician | architecture | CH-01 | novel | "
        " | 0123456789abcdef0123456789abcdef01234567 | 7 |"
    )
    classification_table = (
        f"{_CLASSIFICATION_HEADER_ROW}\n{_CLASSIFICATION_SEPARATOR_ROW}\n{classification_row}\n"
    )

    ledger_rows = parse_ledger_table_rows(ledger_table)
    classification_rows = parse_classification_table_rows(classification_table)
    failures = check_every_challenge_is_classified(
        ledger_rows, classification_rows, [], SEAL_BOUNDARY
    )
    assert not failures, f"expected no failures for a superseded challenge; got: {failures}"


# ---------------------------------------------------------------------------
# Real-file tests -- stated separately from the canaries, on purpose.
# ---------------------------------------------------------------------------


def test_every_post_boundary_consult_in_the_real_ledger_has_a_sealed_prior(
    project_root: Path,
) -> None:
    """The coverage gate, exercised against the shipped ledger and the real
    .ai-state/CONSULT_PRIORS.md. Skips only when the priors file is absent
    AND the ledger carries no post-boundary consult yet; fails when a
    post-boundary consult exists and the file is absent."""
    ledger_path = _require_file(
        project_root / ".ai-state" / "CONSULT_LEDGER.md", "disposition ledger"
    )
    ledger_rows = parse_ledger_table_rows(ledger_path.read_text(encoding="utf-8"))

    priors_path = project_root / ".ai-state" / "CONSULT_PRIORS.md"
    priors_text = priors_path.read_text(encoding="utf-8") if priors_path.is_file() else ""
    prior_rows = parse_prior_table_rows(priors_text) if priors_text else []

    ledger_index = {field: pos for pos, field in enumerate(LEDGER_ROW_FIELDS)}
    has_post_boundary_consult = any(
        _TIMESTAMP_RE.match(row[ledger_index["timestamp"]])
        and row[ledger_index["timestamp"]] >= SEAL_BOUNDARY
        for row in ledger_rows
    )
    if not priors_path.is_file() and not has_post_boundary_consult:
        pytest.skip("CONSULT_PRIORS.md absent and no post-boundary consult exists yet")

    failures = check_every_post_boundary_consult_has_a_sealed_prior(
        ledger_rows, prior_rows, SEAL_BOUNDARY
    )
    assert not failures, "Post-boundary consult(s) missing a sealed prior:\n  " + "\n  ".join(
        failures
    )


def test_every_post_boundary_challenge_in_the_real_ledger_is_classified(
    project_root: Path,
) -> None:
    """The classification-coverage gate, exercised against the shipped
    ledger and the real .ai-state/CONSULT_PRIORS.md. Same skip/fail rule as
    the sealed-prior coverage test above, over G4."""
    ledger_path = _require_file(
        project_root / ".ai-state" / "CONSULT_LEDGER.md", "disposition ledger"
    )
    ledger_rows = parse_ledger_table_rows(ledger_path.read_text(encoding="utf-8"))

    priors_path = project_root / ".ai-state" / "CONSULT_PRIORS.md"
    priors_text = priors_path.read_text(encoding="utf-8") if priors_path.is_file() else ""
    prior_rows = parse_prior_table_rows(priors_text) if priors_text else []
    classification_rows = parse_classification_table_rows(priors_text) if priors_text else []

    ledger_index = {field: pos for pos, field in enumerate(LEDGER_ROW_FIELDS)}
    has_post_boundary_consult = any(
        _TIMESTAMP_RE.match(row[ledger_index["timestamp"]])
        and row[ledger_index["timestamp"]] >= SEAL_BOUNDARY
        for row in ledger_rows
    )
    if not priors_path.is_file() and not has_post_boundary_consult:
        pytest.skip("CONSULT_PRIORS.md absent and no post-boundary consult exists yet")

    failures = check_every_challenge_is_classified(
        ledger_rows, classification_rows, prior_rows, SEAL_BOUNDARY
    )
    assert not failures, "Post-boundary challenge(s) missing a classification:\n  " + "\n  ".join(
        failures
    )


def test_the_real_priors_series_boundary_matches_the_gate_constant(project_root: Path) -> None:
    """The series-boundary invariant, exercised against the real, shipped
    .ai-state/CONSULT_PRIORS.md (skips cleanly if the file does not exist yet)."""
    priors_path = project_root / ".ai-state" / "CONSULT_PRIORS.md"
    if not priors_path.is_file():
        pytest.skip("CONSULT_PRIORS.md does not exist yet")
    result = check_seal_boundary_matches_gate_constant(priors_path.read_text(encoding="utf-8"))
    assert result is None, result


def test_no_data_row_outside_the_priors_tables(project_root: Path) -> None:
    """The real, shipped .ai-state/CONSULT_PRIORS.md carries no stray data
    row outside either parsed table (skips cleanly if the file does not
    exist yet). check_no_data_row_outside_table compares a whole-file count
    of timestamp-shaped lines against the parsed rows, so passing the
    concatenation of both tables' rows is correct for a two-table file --
    this is td-079's trap, now guarded here too."""
    priors_path = project_root / ".ai-state" / "CONSULT_PRIORS.md"
    if not priors_path.is_file():
        pytest.skip("CONSULT_PRIORS.md does not exist yet")
    text = priors_path.read_text(encoding="utf-8")
    prior_rows = parse_prior_table_rows(text)
    classification_rows = parse_classification_table_rows(text)
    result = check_no_data_row_outside_table(text, prior_rows + classification_rows)
    assert result is None, result


def test_every_real_prior_row_has_exactly_seven_columns(project_root: Path) -> None:
    """The row-shape invariant, exercised against the real, shipped
    .ai-state/CONSULT_PRIORS.md (skips cleanly if the file does not exist yet)."""
    priors_path = project_root / ".ai-state" / "CONSULT_PRIORS.md"
    if not priors_path.is_file():
        pytest.skip("CONSULT_PRIORS.md does not exist yet")
    rows = parse_prior_table_rows(priors_path.read_text(encoding="utf-8"))
    failures = check_prior_row_has_seven_columns(rows)
    assert not failures, "Sealed Priors row shape violations:\n  " + "\n  ".join(failures)


def test_every_real_classification_row_has_exactly_nine_columns(project_root: Path) -> None:
    """The row-shape invariant for the classification table, exercised
    against the real, shipped .ai-state/CONSULT_PRIORS.md (skips cleanly if
    the file does not exist yet)."""
    priors_path = project_root / ".ai-state" / "CONSULT_PRIORS.md"
    if not priors_path.is_file():
        pytest.skip("CONSULT_PRIORS.md does not exist yet")
    rows = parse_classification_table_rows(priors_path.read_text(encoding="utf-8"))
    failures = check_classification_row_has_nine_columns(rows)
    assert not failures, "Challenge Classification row shape violations:\n  " + "\n  ".join(
        failures
    )


def _post_boundary_triples(ledger_text: str) -> list[tuple[str, str, str]]:
    """The distinct (task-slug, discipline, stage) triples in `ledger_text`
    whose timestamp is >= SEAL_BOUNDARY, in first-seen order.

    Pure over the ledger's text, per this file's split of assertion logic from
    file reading -- the caller does the reading."""
    ledger_rows = parse_ledger_table_rows(ledger_text)
    ledger_index = {field: pos for pos, field in enumerate(LEDGER_ROW_FIELDS)}
    triples: list[tuple[str, str, str]] = []
    for row in ledger_rows:
        timestamp = row[ledger_index["timestamp"]]
        if not _TIMESTAMP_RE.match(timestamp) or timestamp < SEAL_BOUNDARY:
            continue
        triple = (
            row[ledger_index["task-slug"]],
            row[ledger_index["discipline"]],
            row[ledger_index["stage"]],
        )
        if triple not in triples:
            triples.append(triple)
    return triples


# Parametrisation source for the two git-dependent real-file tests below.
# Resolved at *collection* time -- parametrize needs the triples before any
# fixture exists -- so it must agree with conftest.py's `project_root` fixture.
# Both derive the repo root as this directory's grandparent.
_COLLECTION_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


def _post_boundary_triple_params() -> list[object]:
    """One pytest param per post-boundary triple, so each triple is its own test.

    Why parametrize rather than one test looping over the triples: `pytest.skip`
    raises, so a skip taken inside a `for triple in triples` body unwinds the
    *whole* test function and silences every remaining triple's assertions. The
    suite then reports green having checked one triple and abandoned the rest --
    a pass carrying far less information than it appears to. One test per triple
    scopes a skip to the triple that earned it, and leaves the siblings
    independently collected, run and reported. (This is also what
    rules/swe/testing-conventions.md 'No Logic in Tests' asks for: no `for` loop
    asserting over a collection -- use the framework's parametrize mechanism.)

    Deliberately total: an absent or unreadable ledger yields the sentinel param
    rather than a collection error that would take the whole module down. The
    ledger's existence is separately gated by the coverage tests above, which
    fail loudly via `_require_file`.
    """
    ledger_path = _COLLECTION_PROJECT_ROOT / ".ai-state" / "CONSULT_LEDGER.md"
    try:
        triples = (
            _post_boundary_triples(ledger_path.read_text(encoding="utf-8"))
            if ledger_path.is_file()
            else []
        )
    except OSError:
        triples = []
    if not triples:
        return [pytest.param(None, id="no-post-boundary-consult")]
    return [pytest.param(triple, id=f"{triple[0]}-{triple[1]}-{triple[2]}") for triple in triples]


@pytest.mark.parametrize("triple", _post_boundary_triple_params())
def test_the_witness_commit_contains_the_sealed_prior_rows(
    project_root: Path, triple: tuple[str, str, str] | None
) -> None:
    """For this post-boundary triple, resolve its recorded seal-witness sha
    and assert `git show <sha>:.ai-state/CONSULT_PRIORS.md` contains that
    triple's Sealed Priors row. Skips with a named reason -- naming the sha
    and why -- when the sha does not resolve to a reachable commit (a
    shallow clone, or a squash-merged branch).

    A triple whose working seal is the empty `NONE` declaration takes G6's
    vacuity exemption instead, which is why the classification and cost rows
    are read here and handed to the check: they carry the compensating evidence
    (C1-C3) the exemption is paid for with. Reading an absent cost file as zero
    rows rather than as "no evidence supplied" is deliberate -- both are red,
    and the empty-list path reports the more specific reason.

    One triple per test case: a skip here retires only its own triple, never
    a sibling's assertions."""
    if triple is None:
        pytest.skip("no post-boundary consult exists yet")

    priors_path = project_root / ".ai-state" / "CONSULT_PRIORS.md"
    if not priors_path.is_file():
        pytest.skip("CONSULT_PRIORS.md does not exist yet")
    priors_text = priors_path.read_text(encoding="utf-8")
    classification_rows = parse_classification_table_rows(priors_text)
    classification_index = {field: pos for pos, field in enumerate(CLASSIFICATION_ROW_FIELDS)}

    matching = [
        row
        for row in classification_rows
        if (
            row[classification_index["task-slug"]],
            row[classification_index["discipline"]],
            row[classification_index["stage"]],
        )
        == triple
    ]
    if not matching:
        pytest.skip(f"{triple!r} has no recorded seal-witness yet")
    seal_witness = matching[0][classification_index["seal-witness"]]

    reachable = subprocess.run(
        ["git", "cat-file", "-e", f"{seal_witness}^{{commit}}"],
        cwd=project_root,
        capture_output=True,
        check=False,
    )
    if reachable.returncode != 0:
        pytest.skip(
            f"seal-witness {seal_witness!r} for {triple!r} does not resolve to a "
            "reachable commit (shallow clone, or the branch was squash-merged)"
        )

    show = subprocess.run(
        ["git", "show", f"{seal_witness}:.ai-state/CONSULT_PRIORS.md"],
        cwd=project_root,
        capture_output=True,
        text=True,
        check=False,
    )
    assert show.returncode == 0, (
        f"git show {seal_witness}:.ai-state/CONSULT_PRIORS.md failed: {show.stderr}"
    )
    cost_path = project_root / ".ai-state" / "CONSULT_COSTS.md"
    cost_rows = (
        parse_cost_table_rows(cost_path.read_text(encoding="utf-8")) if cost_path.is_file() else []
    )
    witness_prior_rows = parse_prior_table_rows(show.stdout)
    working_prior_rows = parse_prior_table_rows(priors_text)
    failure = check_witness_priors_equal_working_priors(
        witness_prior_rows,
        working_prior_rows,
        triple,
        classification_rows=classification_rows,
        cost_rows=cost_rows,
    )
    assert failure is None, f"witness commit {seal_witness!r}: {failure}"


@pytest.mark.parametrize("triple", _post_boundary_triple_params())
def test_the_live_fragment_witness_agrees_with_the_recorded_seal_witness(
    project_root: Path, triple: tuple[str, str, str] | None
) -> None:
    """For this post-boundary triple, if the consultant's ephemeral
    .ai-work/<task-slug>/CONSULT_<discipline>.md fragment still exists and
    carries a `**Round-0 HEAD:**` line, apply G5. Skips, naming the absent
    fragment -- the fragment is deleted at pipeline cleanup, so this check
    only bites in the live window.

    One triple per test case: the fragment for one triple being past its live
    window must not retire the check for a triple whose fragment is still
    present -- the exact silencing this test shipped with."""
    if triple is None:
        pytest.skip("no post-boundary consult exists yet")
    task_slug, discipline, stage = triple

    priors_path = project_root / ".ai-state" / "CONSULT_PRIORS.md"
    if not priors_path.is_file():
        pytest.skip("CONSULT_PRIORS.md does not exist yet")
    classification_rows = parse_classification_table_rows(priors_path.read_text(encoding="utf-8"))
    classification_index = {field: pos for pos, field in enumerate(CLASSIFICATION_ROW_FIELDS)}

    fragment_path = project_root / ".ai-work" / task_slug / f"CONSULT_{discipline}.md"
    if not fragment_path.is_file():
        pytest.skip(f"fragment {fragment_path} does not exist (past the live window)")
    fragment_text = fragment_path.read_text(encoding="utf-8")
    if "**Round-0 HEAD:**" not in fragment_text:
        pytest.skip(f"fragment {fragment_path} carries no '**Round-0 HEAD:**' line")

    matching = [
        row
        for row in classification_rows
        if (
            row[classification_index["task-slug"]],
            row[classification_index["discipline"]],
            row[classification_index["stage"]],
        )
        == (task_slug, discipline, stage)
    ]
    if not matching:
        pytest.skip(f"{triple!r} has no recorded seal-witness yet")
    seal_witness = matching[0][classification_index["seal-witness"]]
    result = check_fragment_witness_agrees(fragment_text, seal_witness)
    assert result is None, result
