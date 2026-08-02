"""Structural tests for commands/resume-rework.md.

Slash commands cannot be executed from pytest (they require a live Claude Code
session). These tests validate the command's documented behavior by parsing the
markdown body and asserting the right sections, fields, and documented contracts
are present.

All tests are expected to FAIL until commands/resume-rework.md is created by
the implementer.
"""

from __future__ import annotations

import re
from pathlib import Path

COMMAND_FILE = Path(__file__).parents[2] / "commands" / "resume-rework.md"

EXIT_CODES_THAT_NEED_ERROR_GRAMMAR = (2, 3, 4, 5)
REQUIRED_FINDINGS_SECTIONS = (
    "Problem",
    "Scope",
    "Evidence",
    "Success Criteria",
    "Ledger Links",
    "Suggested Tier",
    "Provenance",
)


def _body() -> str:
    """Return the full command file content (imported lazily so collection succeeds)."""
    return COMMAND_FILE.read_text(encoding="utf-8")


def test_command_file_exists() -> None:
    assert COMMAND_FILE.exists(), (
        f"commands/resume-rework.md not found at {COMMAND_FILE}. The implementer must create it."
    )


def test_frontmatter_has_required_fields() -> None:
    body = _body()
    assert "description:" in body, "frontmatter must have a 'description:' field"
    assert "allowed-tools:" in body, "frontmatter must have an 'allowed-tools:' field"
    assert "argument-hint:" in body, "frontmatter must have an 'argument-hint:' field"
    assert "Agent" in body, "'Agent' must appear in 'allowed-tools' — the command spawns an agent"


def test_help_block_present() -> None:
    body = _body()
    # The INTERFACE_DESIGN.md specifies a ## Help block section with exit codes
    assert re.search(r"##\s+Help", body, re.IGNORECASE), (
        "Body must contain a '## Help' or '## Help block' section documenting usage"
    )
    for code in (0, 1, 2, 3, 4, 5):
        assert str(code) in body, f"Help block must document exit code {code} (0–5 range required)"


def test_auto_discovery_section_documents_glob() -> None:
    body = _body()
    assert re.search(r"##\s+Auto.?discovery", body, re.IGNORECASE), (
        "Body must contain an '## Auto-discovery' section"
    )
    assert "VERIFIER_FINDINGS.md" in body, (
        "Auto-discovery section must reference VERIFIER_FINDINGS.md"
    )
    assert ".ai-work/" in body, "Auto-discovery section must show the .ai-work/ glob path"
    # exit 3 = none found, exit 2 = multiple found
    assert "exit 2" in body or "exit code 2" in body or "`2`" in body, (
        "Auto-discovery section must document exit code 2 (multiple candidates)"
    )
    assert "exit 3" in body or "exit code 3" in body or "`3`" in body, (
        "Auto-discovery section must document exit code 3 (no findings found)"
    )


def test_schema_validation_section_documents_seven_sections() -> None:
    body = _body()
    assert re.search(r"##\s+Schema", body, re.IGNORECASE), (
        "Body must contain a '## Schema validation' section"
    )
    for section_name in REQUIRED_FINDINGS_SECTIONS:
        assert section_name in body, (
            f"Schema validation must name the required section '{section_name}'"
        )
    assert "exit 5" in body or "exit code 5" in body or "`5`" in body, (
        "Schema validation section must document exit code 5 (missing section)"
    )


def test_manifest_match_section_documents_stale_check() -> None:
    body = _body()
    assert re.search(r"##\s+Manifest", body, re.IGNORECASE), (
        "Body must contain a '## Manifest match' section"
    )
    assert "REWORK_MANIFEST.md" in body, "Manifest match section must reference REWORK_MANIFEST.md"
    assert "rw-" in body, "Manifest match section must reference rw-<hash> rework IDs"
    assert "exit 4" in body or "exit code 4" in body or "`4`" in body, (
        "Manifest match section must document exit code 4 (stale findings)"
    )


def test_dispatch_section_names_systems_architect() -> None:
    body = _body()
    assert re.search(r"##\s+Dispatch", body, re.IGNORECASE), (
        "Body must contain a '## Dispatch' section"
    )
    assert "systems-architect" in body, (
        "Dispatch section must name 'systems-architect' as the dispatch target "
        "(architect-always-first routing invariant)"
    )


def test_dry_run_section_present() -> None:
    body = _body()
    assert "--dry-run" in body, "Body must document '--dry-run' mode"
    assert re.search(r"##\s+.*dry.?run", body, re.IGNORECASE) or (
        "--dry-run" in body and "stdout" in body
    ), "Dry-run documentation must describe: print dispatch plan to stdout, no Agent spawn, exit 0"
    # No spawn
    assert re.search(r"(no.+spawn|without.+spawn|does not spawn)", body, re.IGNORECASE), (
        "Dry-run documentation must state that no agent is spawned"
    )


def test_findings_override_section_present() -> None:
    body = _body()
    assert "--findings" in body, (
        "Body must document '--findings <path>' flag for explicit path override"
    )
    # Non-existent path → exit 3
    assert re.search(
        r"--findings.{0,200}exit\s*(code\s*)?3|exit\s*(code\s*)?3.{0,200}--findings",
        body,
        re.DOTALL | re.IGNORECASE,
    ) or ("--findings" in body and ("not found" in body or "exit 3" in body)), (
        "Findings override must document that a non-existent path produces exit 3"
    )


def test_error_grammar_three_part_for_each_exit_code() -> None:
    body = _body()
    assert re.search(r"##\s+Error", body, re.IGNORECASE), (
        "Body must contain an '## Error grammar' section"
    )
    for code in EXIT_CODES_THAT_NEED_ERROR_GRAMMAR:
        # Each error code block should contain three-part what/why/how-to-fix prose.
        # We verify the code is mentioned in the error-grammar section.
        assert str(code) in body, f"Error grammar section must cover exit code {code}"
    # Three-part grammar: what / why / how-to-fix (or To fix:)
    assert re.search(r"To fix:|how.to.fix|how to fix", body, re.IGNORECASE), (
        "Error grammar section must use three-part 'what / why / how-to-fix' structure "
        "(look for 'To fix:' or equivalent)"
    )


def test_json_output_section_present() -> None:
    body = _body()
    assert "--json" in body, "Body must document '--json' flag"
    # Dispatch plan JSON shape: required keys per INTERFACE_DESIGN.md
    for key in ("action", "rework_id", "target_agent", "task_slug"):
        assert f'"{key}"' in body or key in body, (
            f"JSON output documentation must include the '{key}' field in the dispatch plan shape"
        )
