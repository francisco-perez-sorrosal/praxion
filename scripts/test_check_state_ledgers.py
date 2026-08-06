"""Tests for check_state_ledgers.py -- the `.ai-state/` ledger schema gate.

Every check ships a **canary**: a fixture carrying one known-bad row, asserted
to produce the finding. Per `rules/swe/gate-liveness.md`, a gate proven only to
pass on the current good tree is indistinguishable from no gate at all -- and
each defect shape below was observed live in this repository before the gate
existed, so the fixtures reconstruct real incidents rather than invented ones.

Inverse guards accompany the canaries: a correct fixture must NOT trip the
check. A gate that fires on everything is as useless as one that fires on
nothing, and the CONSULT files' legitimate prose tables are exactly the shape a
careless stray-row detector would flag.

The gate is two modules: `state_ledger_schema.py` describes what a ledger *is*
(registry, parser, `dedup_key` derivation) and `check_state_ledgers.py` decides
what to do when one is wrong. This suite drives the gate module only, reaching
the schema half through its re-exports -- so the seam is exercised end to end
rather than each half being asserted in isolation against a contract neither
side runs.

Import strategy mirrors `scripts/test_check_adr_frontmatter_promotion.py`: load
via `importlib.util` so the gate module need not be on `sys.path`.
"""

from __future__ import annotations

import functools
import importlib.util
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

_SCRIPT_PATH = Path(__file__).resolve().parent / "check_state_ledgers.py"
REPO_ROOT = Path(__file__).resolve().parent.parent


@functools.lru_cache(maxsize=1)
def _gate() -> Any:
    """Load the gate module under test, caching it across tests."""
    spec = importlib.util.spec_from_file_location("check_state_ledgers", _SCRIPT_PATH)
    assert spec is not None, f"gate module not importable at {_SCRIPT_PATH}"
    assert spec.loader is not None, f"gate module has no loader at {_SCRIPT_PATH}"
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


# -- Fixture builders ---------------------------------------------------------

TD_HEADER = (
    "# Technical Debt Ledger\n\n"
    "**Schema**: 14 row fields + 1 structural `dedup_key`.\n\n"
    "| id | severity | class | direction | location | goal-ref-type | goal-ref-value | "
    "source | first-seen | last-seen | owner-role | status | resolved-by | notes | dedup_key |\n"
    "|----|----------|-------|-----------|----------|---------------|----------------|"
    "--------|------------|-----------|-----------|--------|-------------|-------|-----------|\n"
)

CONSULT_HEADER = (
    "# Consultation Disposition Ledger\n\n"
    "**Schema**: 11 columns, one row per dispositioned challenge.\n\n"
    "| timestamp | task-slug | discipline | stage | challenge-id | claim | "
    "decision-at-stake | disposition | rationale-ref | model | difficulty |\n"
    "|---|---|---|---|---|---|---|---|---|---|---|\n"
)

CONSULT_TRAILER = (
    "\n## Column Definitions\n\n"
    "- **timestamp** -- ISO 8601 UTC.\n\n"
    "| Disposition | Durable home |\n"
    "|---|---|\n"
    "| switch-now | The ADR recording the change |\n\n"
    "## Single Writer\n\nOnly the convener appends rows.\n"
)


def _td_row(
    row_id: str = "td-001",
    *,
    klass: str = "complexity",
    direction: str = "code-to-goals",
    location: str = "scripts/example.py",
    goal_ref_type: str = "code-quality",
    goal_ref_value: str = "",
    notes: str = "example finding",
    dedup_key: str | None = None,
) -> str:
    """Build one tech-debt row, defaulting `dedup_key` to the conforming value."""
    module = _gate()
    if dedup_key is None:
        payload = "|".join(
            (klass, module.normalize_location(location), direction, goal_ref_type, goal_ref_value)
        )
        import hashlib

        dedup_key = hashlib.sha1(payload.encode("utf-8")).hexdigest()[:12]
    cells = [
        row_id,
        "suggested",
        klass,
        direction,
        location,
        goal_ref_type,
        goal_ref_value,
        "verifier",
        "2026-01-01",
        "2026-01-01",
        "implementer",
        "open",
        "",
        notes,
        dedup_key,
    ]
    return "| " + " | ".join(cells) + " |\n"


def _consult_row(
    timestamp: str = "2026-01-01T00:00:00Z",
    *,
    claim: str = "a falsifiable claim",
    trailing_pipe: bool = True,
) -> str:
    cells = [
        timestamp,
        "example-task",
        "statistician",
        "architecture",
        "CH-01",
        claim,
        "the decision at stake",
        "switch-now",
        "dec-001",
        "opus",
        "standard",
    ]
    return "| " + " | ".join(cells) + (" |\n" if trailing_pipe else "\n")


def _write_tech_debt(root: Path, rows: str, resolved_rows: str = "") -> Path:
    """Materialize a minimal `.ai-state/` holding the tech-debt pair."""
    state = root / ".ai-state"
    state.mkdir(parents=True, exist_ok=True)
    (state / "TECH_DEBT_LEDGER.md").write_text(TD_HEADER + rows, encoding="utf-8")
    (state / "TECH_DEBT_RESOLVED.md").write_text(
        TD_HEADER.replace("# Technical Debt Ledger", "# Resolved Tech Debt") + resolved_rows,
        encoding="utf-8",
    )
    return root


def _write_consult(root: Path, rows: str, trailer: str = CONSULT_TRAILER) -> Path:
    state = root / ".ai-state"
    state.mkdir(parents=True, exist_ok=True)
    (state / "CONSULT_LEDGER.md").write_text(CONSULT_HEADER + rows + trailer, encoding="utf-8")
    return root


def _kinds(findings: list[Any]) -> set[str]:
    return {finding.kind for finding in findings}


# -- Parsing ------------------------------------------------------------------


def test_split_row_keeps_escaped_pipe_inside_its_cell() -> None:
    """`\\|` is a documented escape; splitting naively would mis-count every row."""
    assert _gate().split_row(r"| a | b \| c | d |") == ["a", r"b \| c", "d"]


def test_normalize_location_sorts_and_strips_line_ranges() -> None:
    """Two rows differing only in order or line range share one structural key."""
    module = _gate()
    assert module.normalize_location("b.py:10-20, a.py") == "a.py,b.py"


def test_tech_debt_columns_match_the_finalize_scripts_field_order() -> None:
    """Pin the registry against the finalize script rather than importing it.

    Two copies of a column list is a drift surface; this asserts they are equal
    so the registry can stay uniform across all five ledgers.
    """
    spec = importlib.util.spec_from_file_location(
        "finalize_tech_debt_ledger", REPO_ROOT / "scripts" / "finalize_tech_debt_ledger.py"
    )
    assert spec is not None
    assert spec.loader is not None
    finalize = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = finalize
    spec.loader.exec_module(finalize)
    assert _gate().TECH_DEBT_COLUMNS == finalize.FIELD_ORDER


# -- Canary: field count ------------------------------------------------------


def test_canary_flags_bad_field_count_from_an_unescaped_pipe(tmp_path: Path) -> None:
    """A literal `||` in a notes cell split one row into 16 fields -- observed live."""
    module = _gate()
    row = _td_row(notes="first note || second note")
    findings = module.check_row_shape(module.parse_all(_write_tech_debt(tmp_path, row)))
    assert "field-count" in _kinds(findings)
    assert all(finding.blocking for finding in findings if finding.kind == "field-count")


def test_correct_row_count_produces_no_field_count_finding(tmp_path: Path) -> None:
    module = _gate()
    findings = module.check_row_shape(module.parse_all(_write_tech_debt(tmp_path, _td_row())))
    assert "field-count" not in _kinds(findings)


# -- Canary: stray row (the row that landed past the table) -------------------


def test_canary_detects_row_appended_after_the_trailing_prose(tmp_path: Path) -> None:
    """A row appended at EOF renders to a human and is invisible to every count."""
    module = _gate()
    root = _write_consult(tmp_path, _consult_row(), CONSULT_TRAILER + _consult_row())
    findings = module.check_row_shape(module.parse_all(root))
    stray = [finding for finding in findings if finding.kind == "stray-row"]
    assert len(stray) == 1, findings
    assert stray[0].blocking


def test_prose_tables_after_the_data_table_are_not_stray_rows(tmp_path: Path) -> None:
    """The CONSULT files carry legitimate prose tables; the gate must not fire."""
    module = _gate()
    findings = module.check_row_shape(module.parse_all(_write_consult(tmp_path, _consult_row())))
    assert "stray-row" not in _kinds(findings)


def test_tech_debt_table_running_to_end_of_file_is_not_stray(tmp_path: Path) -> None:
    """Structural asymmetry: the tech-debt table has no trailing prose at all."""
    module = _gate()
    rows = _td_row("td-001") + _td_row("td-002", location="scripts/other.py")
    findings = module.check_row_shape(module.parse_all(_write_tech_debt(tmp_path, rows)))
    assert "stray-row" not in _kinds(findings)


def test_canary_flags_missing_table_header(tmp_path: Path) -> None:
    """No header matching the schema means every row below it is unparseable."""
    module = _gate()
    state = tmp_path / ".ai-state"
    state.mkdir(parents=True)
    (state / "TECH_DEBT_LEDGER.md").write_text(
        "# Technical Debt Ledger\n\n**Schema**: 14 row fields.\n\n" + _td_row(), encoding="utf-8"
    )
    findings = module.check_row_shape(module.parse_all(tmp_path))
    assert "table-missing" in _kinds(findings)


def test_canary_flags_row_missing_its_trailing_delimiter(tmp_path: Path) -> None:
    """Finalize and every published grep recipe silently skip such a row."""
    module = _gate()
    root = _write_consult(tmp_path, _consult_row(trailing_pipe=False))
    findings = module.check_row_shape(module.parse_all(root))
    assert "unterminated-row" in _kinds(findings)


# -- Canary: literal pipe -----------------------------------------------------


def test_canary_flags_escaped_pipe_in_a_tech_debt_cell(tmp_path: Path) -> None:
    """The schema mandates ` // ` precisely so a `|` never reaches a cell."""
    module = _gate()
    row = _td_row(notes=r"first note \| second note")
    findings = module.check_literal_pipes(module.parse_all(_write_tech_debt(tmp_path, row)))
    assert [finding.kind for finding in findings] == ["literal-pipe"]
    assert findings[0].blocking


def test_escaped_pipe_in_a_consult_cell_is_advisory(tmp_path: Path) -> None:
    """CONSULT files document the escape, but read with `cut -d'|'`: warn, not fail."""
    module = _gate()
    root = _write_consult(tmp_path, _consult_row(claim=r"a \| b"))
    findings = module.check_literal_pipes(module.parse_all(root))
    assert [finding.kind for finding in findings] == ["literal-pipe"]
    assert not findings[0].blocking


def test_clean_cells_produce_no_literal_pipe_finding(tmp_path: Path) -> None:
    module = _gate()
    findings = module.check_literal_pipes(module.parse_all(_write_tech_debt(tmp_path, _td_row())))
    assert findings == []


# -- Canary: dedup_key --------------------------------------------------------


def test_canary_flags_wrong_dedup_key(tmp_path: Path) -> None:
    module = _gate()
    row = _td_row(dedup_key="000000000000")
    findings = module.check_dedup_keys(module.parse_all(_write_tech_debt(tmp_path, row)))
    assert [finding.kind for finding in findings] == ["dedup-mismatch"]
    assert findings[0].blocking


def test_canary_flags_invalid_dedup_key_format(tmp_path: Path) -> None:
    """Seven live rows carried a slug where the schema declares 12 hex characters."""
    module = _gate()
    row = _td_row(dedup_key="readiness-section-tsx-complexity")
    findings = module.check_dedup_keys(module.parse_all(_write_tech_debt(tmp_path, row)))
    assert [finding.kind for finding in findings] == ["dedup-format"]


def test_canary_flags_duplicate_dedup_key_across_the_pair(tmp_path: Path) -> None:
    """Two rows sharing a written key collapse into one at the next finalize run."""
    module = _gate()
    active = _td_row("td-001")
    resolved = _td_row("td-002")  # same 5-tuple -> same key, in the sibling file
    findings = module.check_dedup_keys(
        module.parse_all(_write_tech_debt(tmp_path, active, resolved))
    )
    assert "dedup-duplicate" in _kinds(findings)


def test_conforming_dedup_key_produces_no_finding(tmp_path: Path) -> None:
    module = _gate()
    findings = module.check_dedup_keys(module.parse_all(_write_tech_debt(tmp_path, _td_row())))
    assert findings == []


def test_collision_blocked_row_is_advisory_and_never_backfilled(tmp_path: Path) -> None:
    """A repair that would collide is worse than the bad data it repairs.

    The conforming row already owns the key; recomputing the stale one would let
    the next finalize run collapse two distinct findings, erasing a `td-NNN`.
    """
    module = _gate()
    conforming = _td_row("td-001")
    stale = _td_row("td-002", dedup_key="ffffffffffff")  # same 5-tuple, wrong key
    root = _write_tech_debt(tmp_path, conforming, stale)

    findings = module.check_dedup_keys(module.parse_all(root))
    blocked = [finding for finding in findings if finding.kind == "dedup-collision-blocked"]
    assert [finding.row_id for finding in blocked] == ["td-002"]
    assert not blocked[0].blocking
    assert "td-001" in blocked[0].message

    before = (root / ".ai-state" / "TECH_DEBT_RESOLVED.md").read_text(encoding="utf-8")
    assert module.backfill_dedup_keys(root) == []
    assert (root / ".ai-state" / "TECH_DEBT_RESOLVED.md").read_text(encoding="utf-8") == before


def test_backfill_repairs_only_the_dedup_key_cell(tmp_path: Path) -> None:
    module = _gate()
    root = _write_tech_debt(tmp_path, _td_row(dedup_key="000000000000"))
    ledger = root / ".ai-state" / "TECH_DEBT_LEDGER.md"
    before = ledger.read_text(encoding="utf-8")

    updated = module.backfill_dedup_keys(root)
    assert [(entry[1], entry[2]) for entry in updated] == [("td-001", "000000000000")]

    after = ledger.read_text(encoding="utf-8")
    assert before.replace("000000000000", updated[0][3]) == after
    assert module.check_dedup_keys(module.parse_all(root)) == []


# -- Canary: registry coverage ------------------------------------------------


def test_canary_flags_unregistered_ledger(tmp_path: Path) -> None:
    """A sixth ledger written to the same convention must not ship ungated."""
    module = _gate()
    state = tmp_path / ".ai-state"
    state.mkdir(parents=True)
    (state / "NEW_LEDGER.md").write_text(
        "# New Ledger\n\n**Schema**: 3 columns.\n\n| a | b | c |\n|---|---|---|\n",
        encoding="utf-8",
    )
    findings = module.check_registry_coverage(tmp_path)
    assert [finding.kind for finding in findings] == ["unregistered-ledger"]


def test_prose_state_file_without_a_schema_line_is_not_flagged(tmp_path: Path) -> None:
    module = _gate()
    state = tmp_path / ".ai-state"
    state.mkdir(parents=True)
    (state / "DESIGN.md").write_text(
        "# Design\n\n| a | b |\n|---|---|\n| 1 | 2 |\n", encoding="utf-8"
    )
    assert module.check_registry_coverage(tmp_path) == []


def test_every_registered_ledger_exists_in_this_repo() -> None:
    """Scope fidelity: the registry must describe real files, not aspirational ones."""
    missing = [spec.path for spec in _gate().LEDGERS if not (REPO_ROOT / spec.path).is_file()]
    assert missing == []


# -- Wiring: existence is not operation ---------------------------------------

HOOK_ID = "state-ledger-schema"


def _precommit_hook_files_pattern() -> str:
    """Extract this gate's `files:` pattern from `.pre-commit-config.yaml`.

    Parsed with a text scan rather than PyYAML: this suite runs under the bare
    interpreter the gate itself prescribes, and a third-party import here would
    make the gate a finding of `check_gate_liveness.py`'s `ambient-import` check.
    """
    config = (REPO_ROOT / ".pre-commit-config.yaml").read_text(encoding="utf-8")
    marker = f"- id: {HOOK_ID}\n"
    assert marker in config, f"{HOOK_ID} is not registered in .pre-commit-config.yaml"
    block = config.split(marker, 1)[1].split("- id: ", 1)[0]
    for line in block.splitlines():
        stripped = line.strip()
        if stripped.startswith("files:"):
            return stripped.split("files:", 1)[1].strip().strip("'\"")
    raise AssertionError(f"{HOOK_ID} declares no `files:` pattern")


def test_precommit_pattern_covers_every_registered_ledger() -> None:
    """Documented scope vs computed scope: adding a ledger must widen the hook.

    Without this, registering a sixth ledger silently ships it ungated at commit
    time -- the hook would simply never fire on the file it is meant to guard.
    """
    import re

    pattern = re.compile(_precommit_hook_files_pattern())
    unmatched = [spec.path for spec in _gate().LEDGERS if not pattern.search(spec.path)]
    assert unmatched == [], f"{HOOK_ID} `files:` pattern does not match: {unmatched}"


def test_precommit_pattern_does_not_match_unrelated_state_files() -> None:
    import re

    pattern = re.compile(_precommit_hook_files_pattern())
    assert not pattern.search(".ai-state/DESIGN.md")


def test_gate_is_invoked_by_ci() -> None:
    """A gate nothing calls in the environment it guards is indistinguishable from none."""
    workflow = (REPO_ROOT / ".github" / "workflows" / "test.yml").read_text(encoding="utf-8")
    assert "scripts/check_state_ledgers.py --check" in workflow


# -- CLI + repo state ---------------------------------------------------------


def _run_cli(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(_SCRIPT_PATH), *args], capture_output=True, text=True, check=False
    )


def test_cli_exits_nonzero_on_a_bad_tree(tmp_path: Path) -> None:
    """The gate must bite through its CLI, not only through its functions."""
    _write_tech_debt(tmp_path, _td_row(dedup_key="000000000000"))
    result = _run_cli(["--check", "--repo-root", str(tmp_path)])
    assert result.returncode == 1
    assert "dedup-mismatch" in result.stdout


def test_cli_json_payload_reports_blocking_count(tmp_path: Path) -> None:
    import json

    _write_tech_debt(tmp_path, _td_row(dedup_key="000000000000"))
    result = _run_cli(["--check", "--json", "--repo-root", str(tmp_path)])
    payload = json.loads(result.stdout)
    assert payload["status"] == "violations"
    assert payload["counts"]["blocking"] == 1


@pytest.mark.parametrize("mode", [[], ["--json"]])
def test_repo_state_is_clean(mode: list[str]) -> None:
    """The live `.ai-state/` tree passes -- the gate's own dogfooding assertion."""
    result = _run_cli(["--check", *mode, "--repo-root", str(REPO_ROOT)])
    assert result.returncode == 0, result.stdout
