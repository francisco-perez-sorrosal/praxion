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
real `agents/discipline-consultant.md` or registry file, neither of which
exists yet. Live file-scanning assertions against those real artifacts are
added once they are created.
"""

from __future__ import annotations

from pathlib import Path

# ---------------------------------------------------------------------------
# The seven I2 registry-row fields, in column order.
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
    """Return a failure string per row that leaves an I2 field missing or blank.

    Every row must carry all seven I2 columns (`discipline` through
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
    """Happy path: a row with all seven I2 fields populated passes."""
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
