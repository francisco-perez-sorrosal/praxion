"""Meta-fitness rule: every fitness rule cites an ADR or CLAUDE.md principle.

Cites: CLAUDE.md§Pragmatism (every action serves a purpose — every line of code,
every fitness rule must earn its place; citations make the rationale auditable
so rules are never silently orphaned from the decisions that motivated them).

Scans:
- `fitness/tests/test_*.py` module docstrings (excluding self)
- `fitness/import-linter.cfg` `description=` fields

Citation regex: `dec-\\d{3,}|CLAUDE\\.md§[A-Z][A-Za-z ]+`

A rule without a citation FAILs the suite. A waiver without anchor + reason
FAILs the suite.
"""

import ast
import configparser
import re
from pathlib import Path


CITATION_REGEX = re.compile(r"dec-\d{3,}|CLAUDE\.md§[A-Z][A-Za-z ]+")
WAIVER_REGEX = re.compile(r"#\s*fitness-waiver:\s*(\S+)\s+(.+)")


# ---------------------------------------------------------------------------
# Callable helpers exposed for the canary and for reuse
# ---------------------------------------------------------------------------


def check_file_citation(source: str, filename: str) -> str | None:
    """Return a failure string if `source` lacks a valid citation, else None.

    Parses the module docstring from `source` and checks it against
    CITATION_REGEX. Returns a human-readable error string if the check fails,
    or None if the citation contract is satisfied.
    """
    try:
        module = ast.parse(source)
    except SyntaxError as exc:
        return f"{filename}: SyntaxError ({exc})"
    docstring = ast.get_docstring(module)
    if docstring is None:
        return f"{filename}: missing module docstring"
    if not CITATION_REGEX.search(docstring):
        return (
            f"{filename}: docstring lacks citation matching {CITATION_REGEX.pattern!r}"
        )
    return None


def test_every_fitness_test_has_citation(project_root: Path) -> None:
    """Every fitness/tests/test_*.py module docstring contains a citation."""
    fitness_tests = sorted((project_root / "fitness" / "tests").glob("test_*.py"))
    failures: list[str] = []
    for test_file in fitness_tests:
        # Skip self
        if test_file.name == "test_meta_citation.py":
            continue
        failure = check_file_citation(test_file.read_text(), test_file.name)
        if failure:
            failures.append(failure)
    assert not failures, "Citation contract violations:\n  " + "\n  ".join(failures)


def test_every_import_linter_contract_has_citation(import_linter_cfg: Path) -> None:
    """Every [importlinter:contract:*] stanza's description= field contains a citation."""
    parser = configparser.ConfigParser(strict=False)
    parser.read(import_linter_cfg)
    failures: list[str] = []
    for section in parser.sections():
        if not section.startswith("importlinter:contract:"):
            continue
        description = parser.get(section, "description", fallback="")
        if not CITATION_REGEX.search(description):
            failures.append(
                f"[{section}]: description= lacks citation matching {CITATION_REGEX.pattern!r}"
            )
    assert not failures, "Citation contract violations:\n  " + "\n  ".join(failures)


def test_every_waiver_has_anchor_and_reason(project_root: Path) -> None:
    """Every fitness-waiver inline comment has a valid citation anchor and a non-empty reason."""
    failures: list[str] = []
    # Search across the repo, but limit to known-relevant trees to keep the scan fast.
    # Exclude fitness/tests/ itself — test files document the waiver contract but never
    # express real waivers; scanning them would trigger false positives from docstrings.
    search_roots = [
        project_root / "scripts",
    ]
    for root in search_roots:
        if not root.exists():
            continue
        for source_file in root.rglob("*.py"):
            for line_no, line in enumerate(
                source_file.read_text().splitlines(), start=1
            ):
                match = WAIVER_REGEX.search(line)
                if match is None:
                    continue
                anchor, reason = match.group(1), match.group(2).strip()
                if not CITATION_REGEX.fullmatch(anchor):
                    failures.append(
                        f"{source_file.relative_to(project_root)}:{line_no} waiver anchor "
                        f"{anchor!r} does not match {CITATION_REGEX.pattern!r}"
                    )
                if not reason:
                    failures.append(
                        f"{source_file.relative_to(project_root)}:{line_no} waiver missing reason"
                    )
    assert not failures, "Waiver violations:\n  " + "\n  ".join(failures)


# ---------------------------------------------------------------------------
# Canary: prove the citation check bites on a known-bad fixture
# ---------------------------------------------------------------------------


def test_flags_fitness_file_missing_citation(tmp_path: Path) -> None:
    """Canary: a fitness file with no citation in its docstring is reported.

    This proves the citation gate fails on a known-bad input — not just passes
    on the current good state.
    """
    source_without_citation = (
        '"""Some fitness rule without any citation.\n\n'
        "It describes something important but forgot to cite the decision.\n"
        '"""\n'
        "def test_something_holds() -> None:\n"
        "    assert True\n"
    )
    result = check_file_citation(source_without_citation, "test_uncited_rule.py")
    assert result is not None, (
        "check_file_citation must return a failure string for a file with no citation; "
        "got None (i.e. check passed when it should have failed)"
    )
    assert "citation" in result.lower() or "docstring" in result.lower(), (
        f"failure message must mention 'citation' or 'docstring'; got: {result!r}"
    )


def test_flags_fitness_file_with_no_docstring(tmp_path: Path) -> None:
    """Canary: a fitness file with no module docstring is reported."""
    source_no_docstring = "def test_something() -> None:\n    assert True\n"
    result = check_file_citation(source_no_docstring, "test_no_docstring.py")
    assert result is not None, (
        "check_file_citation must return a failure for a file with no docstring"
    )


def test_accepts_fitness_file_with_valid_citation(tmp_path: Path) -> None:
    """Happy path: a fitness file with a valid dec-NNN citation passes."""
    source_with_citation = (
        '"""Fitness rule with a proper citation.\n\n'
        "Cites: CLAUDE.md§Pragmatism (every action serves a purpose).\n"
        '"""\n'
        "def test_rule_holds() -> None:\n"
        "    assert True\n"
    )
    result = check_file_citation(source_with_citation, "test_cited_rule.py")
    assert result is None, (
        f"check_file_citation must return None for a file with a valid citation; got: {result!r}"
    )
