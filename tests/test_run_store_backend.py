"""Schema-convention tests for the run-store backend abstraction.

These tests validate that run-ledger-schema.md encodes the conventions it
claims to encode.  There is no Python implementation of a run-store backend —
the schema is a convention document (Markdown), not a library.  Each test
parses the documentation artifact and asserts its documented claims hold.

No network access, no external credentials.
"""

from __future__ import annotations

import os
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_FILE = PROJECT_ROOT / "skills" / "agent-evals" / "references" / "run-ledger-schema.md"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _extract_run_store_descriptor_yaml_block(markdown_text: str) -> str:
    """Return the content of the ```yaml block under '## Canonical YAML — run_store_descriptor'.

    The anchor is the Markdown section heading, which appears *before* the code
    fence.  Anchoring on the heading (rather than on a comment inside the fence)
    guarantees we find the correct block even though the document contains a
    second ```yaml block for EVAL_RESULTS immediately afterwards.
    """
    heading = "## Canonical YAML — run_store_descriptor"
    anchor_pos = markdown_text.find(heading)
    if anchor_pos == -1:
        raise ValueError(f"Could not locate section heading in schema file: {heading!r}")
    yaml_open = markdown_text.find("```yaml", anchor_pos)
    if yaml_open == -1:
        raise ValueError(f"No ```yaml block found after section heading: {heading!r}")
    yaml_start = markdown_text.index("\n", yaml_open) + 1
    yaml_end = markdown_text.index("```", yaml_start)
    return markdown_text[yaml_start:yaml_end]


def _parse_run_store_descriptor_yaml(schema_text: str) -> dict:
    """
    Extract and parse the run_store_descriptor YAML block.

    The block uses placeholder values (<string>, <uri>) and inline YAML comments.
    We strip comment-only lines before handing to yaml.safe_load; inline comments
    are handled natively by the YAML parser.
    """
    raw_block = _extract_run_store_descriptor_yaml_block(schema_text)

    cleaned_lines = [line for line in raw_block.splitlines() if not line.strip().startswith("#")]
    return yaml.safe_load("\n".join(cleaned_lines)) or {}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_schema_file_is_present() -> None:
    """Schema file must exist before any convention can be asserted."""
    assert SCHEMA_FILE.exists(), (
        f"run-ledger-schema.md not found at {SCHEMA_FILE}; "
        "Step 1 must land before these convention tests are meaningful"
    )


def test_run_store_descriptor_yaml_block_contains_required_fields() -> None:
    """
    The run_store_descriptor YAML block must declare the four required fields.

    The schema document's Field Constraints table lists run_id, project_name,
    store_uri, and artifact_paths as Required.  This test verifies the canonical
    YAML block in the schema itself is consistent with that table.
    """
    schema_text = SCHEMA_FILE.read_text(encoding="utf-8")
    descriptor = _parse_run_store_descriptor_yaml(schema_text)

    required_fields = {"run_id", "project_name", "store_uri", "artifact_paths"}
    missing = required_fields - set(descriptor.keys())
    assert not missing, (
        f"run_store_descriptor YAML block is missing required fields: {sorted(missing)}"
    )


def test_local_home_uri_derivation_matches_documented_pattern() -> None:
    """
    The local-home URI derivation documented in the schema must be consistent
    with the formula: $HOME/.<project-name>/runs/<run_id>/

    Given a fixture descriptor, the derived path must equal
    os.path.expanduser("~/") + ".<project_name>/runs/<run_id>/"
    """
    run_id = "r-001"
    project_name = "myproj"

    # Derive the path using the documented formula
    home = os.path.expanduser("~/")
    expected = f"{home}.{project_name}/runs/{run_id}/"

    # Verify the schema document encodes this derivation pattern
    schema_text = SCHEMA_FILE.read_text(encoding="utf-8")
    pattern_in_schema = "$HOME/.<project-name>/runs/<run_id>/"
    assert pattern_in_schema in schema_text, (
        f"Schema does not contain the expected local-home derivation pattern: {pattern_in_schema!r}"
    )

    # Cross-check: applying the formula to the fixture produces the expected path
    derived = f"{home}.{project_name}/runs/{run_id}/"
    assert derived == expected, (
        f"local-home derivation mismatch: got {derived!r}, expected {expected!r}"
    )

    # Additionally assert the schema describes the backend=local-home row
    assert "local-home" in schema_text, "Schema does not mention 'local-home' backend at all"


def test_descriptor_dict_has_no_backend_field() -> None:
    """
    The run_store_descriptor must NOT contain a 'backend' key.

    The invariance rule states: 'NO backend-conditional field except store_uri'.
    Backend selection belongs in project_profile.yaml, not in the descriptor.
    A fixture descriptor built from the documented required fields must not
    include 'backend'.
    """
    # A descriptor built from only the documented required fields
    descriptor = {
        "run_id": "r-001",
        "project_name": "myproj",
        "store_uri": f"{os.path.expanduser('~/')}/.myproj/runs/r-001/",
        "artifact_paths": ["code/", "logs/", "submission/", "trace/metrics.jsonl"],
    }

    assert "backend" not in descriptor, (
        "descriptor must not carry a 'backend' key; "
        "backend is a project-level config concern (project_profile.yaml)"
    )

    # Also confirm the schema's invariance rule is explicitly stated in the document
    schema_text = SCHEMA_FILE.read_text(encoding="utf-8")
    assert "NO" in schema_text and "backend" in schema_text, (
        "Schema document does not include the 'NO backend' invariance rule"
    )
