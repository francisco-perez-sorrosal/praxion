"""Behavioral tests for the eval-ledger producer `append_eval_log_row`.

Target: `skills/agent-evals/scripts/append_eval_log.py::append_eval_log_row`
(the pipeline-finalized producer interface). The file does
not exist yet at test-authoring time — every test loads it fresh inside its
own body via `importlib.util.spec_from_file_location` (mirroring
`hooks/test_measure_context_surface.py`'s pattern for hyphenated,
non-package-importable script directories), so collection succeeds before
the production code lands and the RED signal is a `FileNotFoundError`
raised at call time, not a collection-time import error.

The expected 11-column shape is parsed from
`skills/agent-evals/references/run-ledger-schema.md` at test run time (the
schema-parse pattern from `tests/test_run_store_backend.py`, dec-220) rather
than hand-copied here a second time — if the schema's column set ever
changes, these tests change with it automatically.

Hermetic: every test builds its `project_root` under `tmp_path`; no network,
no real credentials, no committed fixtures.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = PROJECT_ROOT / "skills" / "agent-evals" / "scripts" / "append_eval_log.py"
SCHEMA_FILE = PROJECT_ROOT / "skills" / "agent-evals" / "references" / "run-ledger-schema.md"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _load_module():
    """Load append_eval_log.py as a module inside a test body.

    `skills/agent-evals/scripts/` is a hyphenated skill directory, not an
    importable package path, so the script is loaded directly by file
    location. Deferred inside each test body (never at module import time)
    so pytest collection succeeds even before the file exists on disk — the
    RED signal is the `FileNotFoundError` `exec_module` raises here.
    """
    spec = importlib.util.spec_from_file_location("append_eval_log", SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _eval_log_columns() -> list[str]:
    """Parse the 11-column header row from run-ledger-schema.md's own example table.

    Anchors on the '## EVAL_LOG.md Column Set' heading, then the first
    ```markdown fence after it, mirroring
    tests/test_run_store_backend.py's heading-anchored block extraction —
    the schema stays the single source of truth for the column list.
    """
    heading = "## EVAL_LOG.md Column Set"
    schema_text = SCHEMA_FILE.read_text(encoding="utf-8")
    anchor_pos = schema_text.find(heading)
    if anchor_pos == -1:
        raise ValueError(f"Could not locate section heading in schema file: {heading!r}")
    fence_open = schema_text.find("```markdown", anchor_pos)
    if fence_open == -1:
        raise ValueError(f"No ```markdown block found after section heading: {heading!r}")
    header_start = schema_text.index("\n", fence_open) + 1
    header_end = schema_text.index("\n", header_start)
    header_line = schema_text[header_start:header_end]
    return [col.strip() for col in header_line.strip().strip("|").split("|")]


def _valid_row_fields(**overrides: object) -> dict:
    """Minimal valid row_fields covering all 11 EVAL_LOG.md columns.

    Field names mirror the producer's documented interface — hash-like
    fields use their documented SHORT widths by default so
    tests other than the prefix-width test aren't coupled to truncation behavior.
    """
    fields: dict[str, object] = {
        "run_id": "eval-run-a1b2c3",
        "task": "swebench_verified",
        "generation": 1,
        "primary_metric": 0.641,
        "held_out_delta": -0.012,
        "model_id": "claude-sonnet-5",
        "prompt_hash": "f3a9d2b7",
        "dataset_sha": "9e3c2a1b",
        "cost_usd": 7.23,
        "git_sha": "a1b2c3d",
        "store_uri": "~/.myproject/runs/eval-run-a1b2c3/",
    }
    fields.update(overrides)
    return fields


def _ledger_path(project_root: Path) -> Path:
    return project_root / ".ai-state" / "eval_ledger" / "EVAL_LOG.md"


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_first_write_creates_ledger_dir_with_canonical_header(tmp_path: Path) -> None:
    """First call for a project with no prior ledger creates the dir, header, and one row."""
    mod = _load_module()
    columns = _eval_log_columns()

    mod.append_eval_log_row(tmp_path, _valid_row_fields())

    ledger_path = _ledger_path(tmp_path)
    assert ledger_path.exists()
    lines = ledger_path.read_text(encoding="utf-8").splitlines()

    header_cols = [c.strip() for c in lines[0].strip().strip("|").split("|")]
    assert header_cols == columns, "written header must match the schema's documented column order"

    separator_cols = [c.strip() for c in lines[1].strip().strip("|").split("|")]
    assert len(separator_cols) == len(columns)
    assert all(set(cell) <= {"-"} and cell for cell in separator_cols), (
        "separator row must be dashes only, one cell per column"
    )

    assert len(lines) == 3, "header + separator + exactly one data row on first write"


def test_second_call_appends_without_disturbing_the_first_row(tmp_path: Path) -> None:
    """A second call with a different run_id appends a row; the first row and header survive untouched."""
    mod = _load_module()

    mod.append_eval_log_row(tmp_path, _valid_row_fields(run_id="eval-run-a1b2c3"))
    ledger_path = _ledger_path(tmp_path)
    lines_after_first = ledger_path.read_text(encoding="utf-8").splitlines()
    header_line, separator_line, first_data_row = lines_after_first

    mod.append_eval_log_row(tmp_path, _valid_row_fields(run_id="eval-run-d4e5f6"))

    lines_after_second = ledger_path.read_text(encoding="utf-8").splitlines()
    assert lines_after_second[0] == header_line
    assert lines_after_second[1] == separator_line
    assert lines_after_second[2] == first_data_row, "first data row must be byte-for-byte unchanged"
    assert len(lines_after_second) == 4, "header + separator + two data rows; header not duplicated"


def test_full_length_hashes_are_truncated_to_documented_prefix_widths(tmp_path: Path) -> None:
    """prompt_hash/dataset_sha/git_sha are stored as 8/8/7-char prefixes even when passed in full."""
    mod = _load_module()
    columns = _eval_log_columns()

    full_prompt_hash = "f3a9d2b7c1e84f6a2d0b9c3e7f1a4d8b"  # 32 chars
    full_dataset_sha = "9e3c2a1b4d7f0e5c8a2b6d9f3e1c4a7b"  # 32 chars
    full_git_sha = "a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0"  # 40 chars

    mod.append_eval_log_row(
        tmp_path,
        _valid_row_fields(
            prompt_hash=full_prompt_hash,
            dataset_sha=full_dataset_sha,
            git_sha=full_git_sha,
        ),
    )

    data_row_line = _ledger_path(tmp_path).read_text(encoding="utf-8").splitlines()[2]
    row = dict(
        zip(columns, [c.strip() for c in data_row_line.strip().strip("|").split("|")], strict=True)
    )

    assert row["prompt_hash"] == full_prompt_hash[:8]
    assert row["dataset_sha"] == full_dataset_sha[:8]
    assert row["git_sha"] == full_git_sha[:7]


def test_written_row_has_exactly_eleven_columns(tmp_path: Path) -> None:
    """The written data row's field count matches the schema's documented 11-column contract."""
    mod = _load_module()
    columns = _eval_log_columns()
    assert len(columns) == 11, "sanity check on the schema itself, not the producer"

    mod.append_eval_log_row(tmp_path, _valid_row_fields())

    data_row_line = _ledger_path(tmp_path).read_text(encoding="utf-8").splitlines()[2]
    fields = data_row_line.strip().strip("|").split("|")
    assert len(fields) == len(columns)


def test_missing_required_field_raises_value_error_naming_it(tmp_path: Path) -> None:
    """A row_fields dict missing a required column raises ValueError naming it, with no file side effect.

    This is the gate-liveness canary: it proves the required-field check
    actually bites on a known-bad input, and that the rejection happens
    before any write — not merely that the happy path works.
    """
    mod = _load_module()

    incomplete_fields = _valid_row_fields()
    del incomplete_fields["cost_usd"]

    with pytest.raises(ValueError, match="cost_usd"):
        mod.append_eval_log_row(tmp_path, incomplete_fields)

    ledger_path = _ledger_path(tmp_path)
    assert not ledger_path.exists(), "a rejected call must not create the ledger file"
    assert not ledger_path.parent.exists(), "a rejected call must not create the eval_ledger dir"


def test_no_invocation_leaves_ledger_absent(tmp_path: Path) -> None:
    """With no eval run ever recorded for this project, EVAL_LOG.md stays absent (optional-lazy)."""
    _load_module()  # forces the same RED signal as every other test in this file

    assert not _ledger_path(tmp_path).exists()
