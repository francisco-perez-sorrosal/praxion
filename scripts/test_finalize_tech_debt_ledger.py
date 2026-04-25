"""Tests for finalize_tech_debt_ledger.py -- post-merge dedupe of the tech-debt ledger.

Behavioral tests of the tech-debt ledger finalize protocol: rows sharing a
``dedup_key`` collapse to one survivor, status precedence (``resolved >
in-flight > open > wontfix``) picks the survivor, ties break by newer
``last-seen``, and non-conflicting fields (notes, locations) merge.

Tests are ordered to match the public-helper contract the implementer
commits to, with surface discovered by reading ``rules/swe/agent-intermediate-documents.md``
§ ``TECH_DEBT_LEDGER.md`` and the ``SYSTEMS_PLAN.md`` authoritative schema:

    parse_ledger(path) -> (header_lines, rows)      # table round-trip
    collapse_rows(rows) -> rows                     # pure dedupe + merge
    finalize_ledger(ledger_path, dry_run) -> int    # orchestration
    acquire_lock(lock_path)                         # context manager
    main()                                          # CLI entry

Import strategy: mirrors ``scripts/test_finalize_adrs.py`` -- load via
``importlib.util`` so the module does not need to be on ``sys.path`` and
the test file can sit next to the script under ``scripts/``.

RED handshake: on first run before the implementer lands ``scripts/finalize_tech_debt_ledger.py``,
``_SCRIPT_PATH.is_file()`` is ``False`` and every test fails at import-time
collection with ``FileNotFoundError``. The failing surface IS the test
contract the implementer must satisfy.

Policy choices documented as module-level constants below (separator, malformed-row
handling) mirror the authoritative schema in the rule file; when the rule is silent,
the plan (``.ai-work/tech-debt-integration/IMPLEMENTATION_PLAN.md`` Step 3-test) is the
secondary source.
"""

from __future__ import annotations

import fcntl
import importlib.util
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

# -- Constants for the policy contract the implementer must satisfy ----------

# Policy: notes-merge separator between surviving and discarded rows.
# Source: rules/swe/agent-intermediate-documents.md line 157 -- "notes
# concatenated with ` | `". NOT a test-engineer choice.
NOTES_SEPARATOR = " | "

# Policy: status precedence on collapse. Source: rule line 157.
STATUS_PRECEDENCE = ("resolved", "in-flight", "open", "wontfix")

# Policy: malformed-row handling. Source: IMPLEMENTATION_PLAN.md Step 3-test --
# "Malformed table row -> script logs error, skips that row, exits 1
# (manual intervention)." Rule file is silent; plan is the secondary source.
MALFORMED_EXIT_CODE = 1

_SCRIPT_PATH = Path(__file__).resolve().parent / "finalize_tech_debt_ledger.py"


def _load_module() -> Any:
    """Load finalize_tech_debt_ledger as a module.

    Fails loudly at collection time if the script has not been written yet --
    which IS the RED-handshake signal for the paired implementer step.
    """
    if not _SCRIPT_PATH.is_file():
        raise FileNotFoundError(
            f"finalize_tech_debt_ledger.py not found at {_SCRIPT_PATH}. "
            f"This is expected during the BDD/TDD RED handshake; once the "
            f"implementer lands the script, tests will resolve."
        )
    spec = importlib.util.spec_from_file_location(
        "finalize_tech_debt_ledger", _SCRIPT_PATH
    )
    assert spec is not None
    assert spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


# Module-level load: if the script is missing, every test in this file
# errors at collection, which is exactly the RED signal we want.
finalize_td = _load_module()


# -- Test helpers -------------------------------------------------------------

HEADER = (
    "# Technical Debt Ledger\n"
    "\n"
    "<!-- Living, append-only ledger of grounded debt findings. -->\n"
    "\n"
    "**Schema**: 14 row fields + 1 structural `dedup_key`. "
    "See rules/swe/agent-intermediate-documents.md for field definitions.\n"
    "\n"
    "| id | severity | class | direction | location | goal-ref-type | goal-ref-value | source | first-seen | last-seen | owner-role | status | resolved-by | notes | dedup_key |\n"
    "|----|----------|-------|-----------|----------|---------------|----------------|--------|------------|-----------|-----------|--------|-------------|-------|-----------|\n"
)

FIELD_ORDER = (
    "id",
    "severity",
    "class",
    "direction",
    "location",
    "goal-ref-type",
    "goal-ref-value",
    "source",
    "first-seen",
    "last-seen",
    "owner-role",
    "status",
    "resolved-by",
    "notes",
    "dedup_key",
)


def make_row(
    *,
    id: str = "td-001",
    severity: str = "important",
    cls: str = "duplication",
    direction: str = "code-to-goals",
    location: str = "src/foo.py",
    goal_ref_type: str = "code-quality",
    goal_ref_value: str = "",
    source: str = "verifier",
    first_seen: str = "2026-04-01",
    last_seen: str = "2026-04-01",
    owner_role: str = "implementer",
    status: str = "open",
    resolved_by: str = "",
    notes: str = "initial finding",
    dedup_key: str = "aaaaaaaaaaaa",
) -> str:
    """Build a Markdown-table row line. All fields default to a canonical shape."""
    values = (
        id,
        severity,
        cls,
        direction,
        location,
        goal_ref_type,
        goal_ref_value,
        source,
        first_seen,
        last_seen,
        owner_role,
        status,
        resolved_by,
        notes,
        dedup_key,
    )
    return "| " + " | ".join(values) + " |\n"


def write_ledger(path: Path, rows: list[str]) -> None:
    """Assemble the ledger file from HEADER + data-row lines."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(HEADER + "".join(rows), encoding="utf-8")


def read_rows(path: Path) -> list[str]:
    """Return only the data rows from a ledger file (skipping header)."""
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines(keepends=True)
    data_rows: list[str] = []
    in_table = False
    for line in lines:
        stripped = line.strip()
        # The separator line is `|---|---|...|`. After that, every non-blank
        # `|...|` line is a data row.
        if stripped.startswith("|---") or stripped.startswith("| ---"):
            in_table = True
            continue
        if in_table and stripped.startswith("|") and stripped.endswith("|"):
            data_rows.append(line)
    return data_rows


def parse_row(row_line: str) -> dict[str, str]:
    """Parse a single table row line into a field-name-to-value dict."""
    # Strip leading/trailing `|` and whitespace, then split on ` | `.
    stripped = row_line.strip().strip("|")
    parts = [p.strip() for p in stripped.split("|")]
    if len(parts) != len(FIELD_ORDER):
        raise AssertionError(
            f"row has {len(parts)} columns, expected {len(FIELD_ORDER)}: {row_line!r}"
        )
    return dict(zip(FIELD_ORDER, parts))


@pytest.fixture
def ledger_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Build a minimal repo layout and redirect the script at tmp_path.

    The implementer's script is expected to derive the ledger path from a
    module-level constant (REPO_ROOT or LEDGER_PATH). We rebind whichever
    name(s) exist to the tmp_path equivalent so the script operates on the
    fixture tree rather than the real repo state.
    """
    path = tmp_path / ".ai-state" / "TECH_DEBT_LEDGER.md"
    path.parent.mkdir(parents=True, exist_ok=True)

    for attr, new_value in (
        ("REPO_ROOT", tmp_path),
        ("LEDGER_PATH", path),
        ("LOCK_PATH", tmp_path / ".ai-state" / ".tech_debt_ledger_finalize.lock"),
    ):
        if hasattr(finalize_td, attr):
            monkeypatch.setattr(finalize_td, attr, new_value)

    return path


# -- Empty / trivial inputs ---------------------------------------------------


class TestEmptyInputIsNoOp:
    """Empty ledger (header-only, zero rows) is a no-op; exit 0."""

    def test_empty_ledger_exits_zero_without_modifying_file(
        self, ledger_path: Path
    ) -> None:
        """Header-only input -> script exits 0, file bytes unchanged."""
        write_ledger(ledger_path, rows=[])
        original_bytes = ledger_path.read_bytes()

        code = finalize_td.finalize_ledger(ledger_path, dry_run=False)

        assert code == 0
        assert ledger_path.read_bytes() == original_bytes


class TestSingleRowIsNoOp:
    """One row cannot be deduped; exit 0, row preserved byte-for-byte."""

    def test_single_row_ledger_exits_zero_without_modifying_file(
        self, ledger_path: Path
    ) -> None:
        """One data row -> no dedup possible -> exit 0, file unchanged."""
        row = make_row(id="td-001", dedup_key="abc123def456")
        write_ledger(ledger_path, [row])
        original_bytes = ledger_path.read_bytes()

        code = finalize_td.finalize_ledger(ledger_path, dry_run=False)

        assert code == 0
        assert ledger_path.read_bytes() == original_bytes


# -- Distinct keys preserved, order preserved --------------------------------


class TestDistinctKeysPreserveAllRows:
    """N rows with N distinct dedup_keys stay N rows; order preserved."""

    def test_three_rows_with_distinct_keys_preserve_order_and_count(
        self, ledger_path: Path
    ) -> None:
        """Three rows with distinct dedup_keys survive unchanged in order."""
        rows = [
            make_row(id="td-001", dedup_key="aaaaaaaaaaaa"),
            make_row(id="td-002", dedup_key="bbbbbbbbbbbb"),
            make_row(id="td-003", dedup_key="cccccccccccc"),
        ]
        write_ledger(ledger_path, rows)

        code = finalize_td.finalize_ledger(ledger_path, dry_run=False)

        assert code == 0
        surviving = read_rows(ledger_path)
        assert len(surviving) == 3
        assert parse_row(surviving[0])["id"] == "td-001"
        assert parse_row(surviving[1])["id"] == "td-002"
        assert parse_row(surviving[2])["id"] == "td-003"


# -- Simple collapse with same key --------------------------------------------


class TestSameDedupKeyCollapsesToOneRow:
    """Two rows with the same dedup_key collapse to one."""

    def test_two_rows_with_same_dedup_key_collapse_to_one(
        self, ledger_path: Path
    ) -> None:
        """Duplicate key -> exactly one row survives."""
        shared_key = "ddddeeeeffff"
        rows = [
            make_row(id="td-001", dedup_key=shared_key, notes="first"),
            make_row(id="td-002", dedup_key=shared_key, notes="second"),
        ]
        write_ledger(ledger_path, rows)

        code = finalize_td.finalize_ledger(ledger_path, dry_run=False)

        assert code == 0
        surviving = read_rows(ledger_path)
        assert len(surviving) == 1


# -- Status precedence --------------------------------------------------------


class TestStatusPrecedenceOnCollapse:
    """Status precedence on collapse is ``resolved > in-flight > open > wontfix``."""

    @pytest.mark.parametrize(
        ("status_a", "status_b", "expected_winner"),
        [
            ("resolved", "open", "resolved"),
            ("open", "resolved", "resolved"),
            ("resolved", "in-flight", "resolved"),
            ("in-flight", "resolved", "resolved"),
            ("resolved", "wontfix", "resolved"),
            ("in-flight", "open", "in-flight"),
            ("open", "in-flight", "in-flight"),
            ("in-flight", "wontfix", "in-flight"),
            ("open", "wontfix", "open"),
            ("wontfix", "open", "open"),
        ],
    )
    def test_higher_precedence_status_wins_regardless_of_order(
        self,
        ledger_path: Path,
        status_a: str,
        status_b: str,
        expected_winner: str,
    ) -> None:
        """Across every pairing, the higher-precedence status wins."""
        shared_key = "statuspriorty"
        rows = [
            make_row(id="td-001", dedup_key=shared_key, status=status_a),
            make_row(id="td-002", dedup_key=shared_key, status=status_b),
        ]
        write_ledger(ledger_path, rows)

        code = finalize_td.finalize_ledger(ledger_path, dry_run=False)

        assert code == 0
        surviving = read_rows(ledger_path)
        assert len(surviving) == 1
        assert parse_row(surviving[0])["status"] == expected_winner

    def test_three_way_collapse_honors_full_precedence_chain(
        self, ledger_path: Path
    ) -> None:
        """Three rows with resolved + in-flight + open collapse to resolved."""
        shared_key = "threewaychain"
        rows = [
            make_row(id="td-001", dedup_key=shared_key, status="open"),
            make_row(id="td-002", dedup_key=shared_key, status="in-flight"),
            make_row(id="td-003", dedup_key=shared_key, status="resolved"),
        ]
        write_ledger(ledger_path, rows)

        code = finalize_td.finalize_ledger(ledger_path, dry_run=False)

        assert code == 0
        surviving = read_rows(ledger_path)
        assert len(surviving) == 1
        assert parse_row(surviving[0])["status"] == "resolved"


# -- last-seen tie-break ------------------------------------------------------


class TestLastSeenTieBreak:
    """Same status on collapse -> newer ``last-seen`` wins."""

    def test_same_status_collapse_keeps_newer_last_seen(
        self, ledger_path: Path
    ) -> None:
        """Two open rows with same key -> newer last-seen wins."""
        shared_key = "tiebreakkey01"
        rows = [
            make_row(
                id="td-001",
                dedup_key=shared_key,
                status="open",
                last_seen="2026-04-01",
                notes="older",
            ),
            make_row(
                id="td-002",
                dedup_key=shared_key,
                status="open",
                last_seen="2026-04-20",
                notes="newer",
            ),
        ]
        write_ledger(ledger_path, rows)

        code = finalize_td.finalize_ledger(ledger_path, dry_run=False)

        assert code == 0
        surviving = read_rows(ledger_path)
        assert len(surviving) == 1
        assert parse_row(surviving[0])["last-seen"] == "2026-04-20"


# -- first-seen preservation --------------------------------------------------


class TestFirstSeenPreservation:
    """On collapse, ``first-seen`` is the earliest of the two (never the newer)."""

    def test_collapse_preserves_earliest_first_seen(self, ledger_path: Path) -> None:
        """Two rows with different first-seen -> surviving first-seen is earlier."""
        shared_key = "firstseenearly"
        rows = [
            make_row(
                id="td-001",
                dedup_key=shared_key,
                status="open",
                first_seen="2026-01-15",
                last_seen="2026-02-01",
            ),
            make_row(
                id="td-002",
                dedup_key=shared_key,
                status="open",
                first_seen="2026-04-20",
                last_seen="2026-04-20",
            ),
        ]
        write_ledger(ledger_path, rows)

        code = finalize_td.finalize_ledger(ledger_path, dry_run=False)

        assert code == 0
        surviving = read_rows(ledger_path)
        assert len(surviving) == 1
        assert parse_row(surviving[0])["first-seen"] == "2026-01-15"


# -- Notes merge --------------------------------------------------------------


class TestNotesMerge:
    """On collapse, discarded row's ``notes`` are merged into the survivor with ``|``."""

    def test_collapse_merges_notes_with_pipe_separator(self, ledger_path: Path) -> None:
        """Two rows with distinct notes -> surviving notes contain both, ``|``-joined.

        Source of separator: ``rules/swe/agent-intermediate-documents.md`` line 157
        ("notes concatenated with ` | `"). Not a test-engineer choice.
        """
        shared_key = "notesmergekey1"
        rows = [
            make_row(
                id="td-001",
                dedup_key=shared_key,
                status="open",
                last_seen="2026-04-20",
                notes="kept-note",
            ),
            make_row(
                id="td-002",
                dedup_key=shared_key,
                status="open",
                last_seen="2026-04-01",
                notes="discarded-note",
            ),
        ]
        write_ledger(ledger_path, rows)

        code = finalize_td.finalize_ledger(ledger_path, dry_run=False)

        assert code == 0
        surviving = read_rows(ledger_path)
        assert len(surviving) == 1
        merged_notes = parse_row(surviving[0])["notes"]
        # Both notes survive; separator is the rule-specified " | ".
        assert "kept-note" in merged_notes
        assert "discarded-note" in merged_notes
        assert NOTES_SEPARATOR in merged_notes


# -- Locations union-sorted ---------------------------------------------------


class TestLocationsUnion:
    """On collapse, ``location`` is the sorted-union of both rows' locations."""

    def test_collapse_unions_locations_sorted_and_deduplicated(
        self, ledger_path: Path
    ) -> None:
        """Overlapping but non-identical locations -> sorted dedup union.

        Source: ``rules/swe/agent-intermediate-documents.md`` line 157
        ("locations union-sorted").
        """
        shared_key = "locationunion1"
        rows = [
            make_row(
                id="td-001",
                dedup_key=shared_key,
                status="open",
                last_seen="2026-04-20",
                location="src/beta.py, src/alpha.py",
            ),
            make_row(
                id="td-002",
                dedup_key=shared_key,
                status="open",
                last_seen="2026-04-01",
                location="src/alpha.py, src/gamma.py",
            ),
        ]
        write_ledger(ledger_path, rows)

        code = finalize_td.finalize_ledger(ledger_path, dry_run=False)

        assert code == 0
        surviving = read_rows(ledger_path)
        assert len(surviving) == 1
        merged_locations = parse_row(surviving[0])["location"]
        # Union, sorted, no duplicates.
        paths = [p.strip() for p in merged_locations.split(",")]
        assert paths == sorted(set(paths))
        assert set(paths) == {"src/alpha.py", "src/beta.py", "src/gamma.py"}


# -- Idempotency --------------------------------------------------------------


class TestIdempotency:
    """Running the script twice produces byte-identical output on the second run."""

    def test_second_run_produces_no_further_changes(self, ledger_path: Path) -> None:
        """After the first collapse, the second run is a byte-for-byte no-op."""
        shared_key = "idempotencytst"
        rows = [
            make_row(id="td-001", dedup_key=shared_key, status="open"),
            make_row(id="td-002", dedup_key=shared_key, status="resolved"),
            make_row(id="td-003", dedup_key="distinctkey01", status="open"),
        ]
        write_ledger(ledger_path, rows)

        first_code = finalize_td.finalize_ledger(ledger_path, dry_run=False)
        assert first_code == 0
        after_first = ledger_path.read_bytes()

        second_code = finalize_td.finalize_ledger(ledger_path, dry_run=False)
        assert second_code == 0

        assert ledger_path.read_bytes() == after_first, (
            "second run must be byte-equivalent -- finalize is not idempotent"
        )


# -- Dry-run ------------------------------------------------------------------


class TestDryRunDoesNotWrite:
    """``dry_run=True`` reports what would change without mutating the ledger."""

    def test_dry_run_leaves_file_unchanged_when_collapse_would_happen(
        self, ledger_path: Path
    ) -> None:
        """Dry-run on a file that would collapse -> bytes unchanged, exit 0."""
        shared_key = "dryrunkey0001"
        rows = [
            make_row(id="td-001", dedup_key=shared_key, status="open"),
            make_row(id="td-002", dedup_key=shared_key, status="resolved"),
        ]
        write_ledger(ledger_path, rows)
        original_bytes = ledger_path.read_bytes()

        code = finalize_td.finalize_ledger(ledger_path, dry_run=True)

        assert code == 0
        assert ledger_path.read_bytes() == original_bytes, (
            "dry-run must not write -- ledger bytes drifted"
        )


# -- Malformed-row handling ---------------------------------------------------


class TestMalformedRowHandling:
    """Malformed rows trigger a non-zero exit for manual intervention.

    Policy source: ``IMPLEMENTATION_PLAN.md`` Step 3-test -- "Malformed table
    row -> script logs error, skips that row, exits 1 (manual intervention)."
    The rule file is silent; the plan is the secondary source. Implementer
    may choose whether to leave malformed rows in place (preferred for
    safety) or drop them; this test asserts only on exit code, not on
    post-mutation content.
    """

    def test_row_with_wrong_column_count_triggers_manual_intervention_exit(
        self, ledger_path: Path
    ) -> None:
        """Row missing columns -> exit == ``MALFORMED_EXIT_CODE`` (non-zero)."""
        good_row = make_row(id="td-001", dedup_key="goodkey000001")
        # Intentionally malformed: 5 columns instead of 15.
        bad_row = "| td-002 | important | duplication | open | malformed |\n"
        write_ledger(ledger_path, [good_row, bad_row])

        code = finalize_td.finalize_ledger(ledger_path, dry_run=False)

        assert code == MALFORMED_EXIT_CODE, (
            f"malformed row must trigger non-zero exit for manual intervention, "
            f"got exit={code}"
        )


# -- Advisory lock ------------------------------------------------------------


class TestAdvisoryLock:
    """The script acquires + releases an advisory lock for concurrency safety."""

    def test_acquire_lock_is_exclusive_and_releases_on_context_exit(
        self, tmp_path: Path
    ) -> None:
        """``acquire_lock`` context manager holds LOCK_EX; re-acquirable on exit.

        Mirrors the pattern in ``scripts/test_finalize_adrs.py::TestFinalizeLock``
        -- if the context-manager semantics are wrong, two concurrent
        post-merge invocations would race.
        """
        lock_path = tmp_path / ".ai-state" / ".tech_debt_ledger_finalize.lock"
        lock_path.parent.mkdir(parents=True, exist_ok=True)

        with finalize_td.acquire_lock(lock_path):
            assert lock_path.exists()

        # After release, non-blocking LOCK_EX must succeed.
        with open(lock_path, "a") as f:
            fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)


# -- CLI contract -------------------------------------------------------------


class TestCLIContract:
    """The CLI exposes ``--dry-run`` and exits 0 on a clean no-op input."""

    def test_cli_on_empty_ledger_exits_zero_as_no_op(self, ledger_path: Path) -> None:
        """Running the script via subprocess on an empty ledger -> exit 0."""
        write_ledger(ledger_path, rows=[])

        result = subprocess.run(
            [sys.executable, str(_SCRIPT_PATH), "--dry-run"],
            capture_output=True,
            text=True,
            cwd=ledger_path.parent.parent.parent,  # tmp_path
            check=False,
        )

        assert result.returncode == 0, (
            f"empty-ledger dry-run should exit 0, got rc={result.returncode}. "
            f"stdout={result.stdout!r} stderr={result.stderr!r}"
        )

    def test_cli_accepts_dry_run_flag(self, ledger_path: Path) -> None:
        """``--dry-run`` is a recognized flag and does not error-out on parse.

        A missing ``--dry-run`` flag surfaces as a non-zero exit (argparse
        error). This test is a minimal parse-only contract -- actual dry-run
        behavior is covered in TestDryRunDoesNotWrite.
        """
        write_ledger(ledger_path, rows=[])

        result = subprocess.run(
            [sys.executable, str(_SCRIPT_PATH), "--dry-run", "--help"],
            capture_output=True,
            text=True,
            check=False,
        )

        # --help exits 0 after printing help; if argparse rejects --dry-run,
        # the exit is 2.
        assert result.returncode == 0
        assert "--dry-run" in result.stdout
