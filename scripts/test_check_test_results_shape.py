"""Canary tests for scripts/check_test_results_shape.py.

Cites: rules/swe/gate-liveness.md -- every CODE gate ships a sibling canary
proving it fails on a known-bad input. These tests feed the detector an
oversized green section and a section with no Result: line and assert both
are flagged, alongside happy-path, red-section, and --ceiling-override cases.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

_SCRIPT_PATH = Path(__file__).resolve().parent / "check_test_results_shape.py"

# The checker imports the shared _step_schema sibling module by bare name
# (works unmodified under `python3 scripts/check_test_results_shape.py ...`,
# since a script's own directory is on sys.path there); loading it in
# isolation via spec_from_file_location needs the same directory added
# explicitly, or that import resolves nothing.
sys.path.insert(0, str(_SCRIPT_PATH.parent))

import _step_schema  # noqa: E402


def _load_module() -> Any:
    spec = importlib.util.spec_from_file_location("check_test_results_shape", _SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["check_test_results_shape"] = mod
    spec.loader.exec_module(mod)
    return mod


_mod = _load_module()
main = _mod.main
find_findings = _mod.find_findings
DEFAULT_CEILING_BYTES = _mod.DEFAULT_CEILING_BYTES


def _write(root: Path, rel: str, body: str) -> Path:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body, encoding="utf-8")
    return p


def _fixed_shape_green(padding: str = "") -> str:
    return (
        "## Step 1 — a step\n"  # id-citation-discipline:ignore
        "\n"
        "Command: `uv run pytest tests/ -q --tb=short -rf`\n"
        "Result: pass=42 fail=0 skip=0\n"
        "Duration: 3.1s\n"
        f"{padding}"
    )


# ---------------------------------------------------------------------------
# Canary: violations are flagged
# ---------------------------------------------------------------------------


def test_green_section_over_ceiling_is_flagged(tmp_path: Path) -> None:
    """A planted green section of ceiling+1 bytes is flagged as green-over-ceiling."""
    padding = "x" * (DEFAULT_CEILING_BYTES + 1)
    body = _fixed_shape_green(padding=padding)
    path = _write(tmp_path, "TEST_RESULTS.md", body)

    rc = main([str(path)])

    assert rc == 1, "a green section over the ceiling must exit 1"
    findings = find_findings(path, DEFAULT_CEILING_BYTES)
    assert len(findings) == 1
    assert findings[0].kind == "green-over-ceiling"


def test_section_with_no_result_line_is_flagged(tmp_path: Path) -> None:
    """A section with no Result: line at all is flagged as missing-result-line."""
    body = "## Step 1 — a step\n\nCommand: `uv run pytest tests/ -q --tb=short -rf`\n"  # id-citation-discipline:ignore
    path = _write(tmp_path, "TEST_RESULTS.md", body)

    rc = main([str(path)])

    assert rc == 1, "a section with no Result: line must exit 1"
    findings = find_findings(path, DEFAULT_CEILING_BYTES)
    assert len(findings) == 1
    assert findings[0].kind == "missing-result-line"


# ---------------------------------------------------------------------------
# Happy path: green at fixed shape, red of any size, --ceiling override
# ---------------------------------------------------------------------------


def test_green_section_at_fixed_shape_passes(tmp_path: Path) -> None:
    """A green section following the fixed shape (well under the ceiling) is clean."""
    path = _write(tmp_path, "TEST_RESULTS.md", _fixed_shape_green())

    rc = main([str(path)])

    assert rc == 0, "a fixed-shape green section must exit 0"


def test_large_red_section_is_not_flagged(tmp_path: Path) -> None:
    """A 5 KB red section (fail > 0) is never flagged for size."""
    failure_block = "### Failures\n" + ("some failure detail line\n" * 200)  # ~5 KB
    body = (
        "## Step 1 — a step\n"  # id-citation-discipline:ignore
        "\n"
        "Command: `uv run pytest tests/ -q --tb=short -rf`\n"
        "Result: pass=10 fail=2 skip=0\n"
        "Duration: 4.0s\n"
        f"{failure_block}"
    )
    path = _write(tmp_path, "TEST_RESULTS.md", body)
    assert len(body.encode("utf-8")) > 5000

    rc = main([str(path)])

    assert rc == 0, "a red section must never be flagged regardless of size"


def test_ceiling_override_is_honoured(tmp_path: Path) -> None:
    """A --ceiling override changes the threshold used for green-over-ceiling."""
    padding = "x" * 200
    body = _fixed_shape_green(padding=padding)
    path = _write(tmp_path, "TEST_RESULTS.md", body)

    # Default ceiling (1024) is not exceeded by this small section.
    assert main([str(path)]) == 0

    # A tiny override ceiling makes the same section exceed it.
    rc = main([str(path), "--ceiling", "10"])
    assert rc == 1, "a lowered --ceiling must flag a section it would otherwise pass"


def test_main_exits_zero_with_no_findings(tmp_path: Path) -> None:
    """end-to-end: main() returns 0 when every section is clean."""
    path = _write(tmp_path, "TEST_RESULTS.md", _fixed_shape_green())

    rc = main([str(path)])

    assert rc == 0, f"main() must return 0 with no findings; got {rc}"


# ---------------------------------------------------------------------------
# --json shape
# ---------------------------------------------------------------------------


def test_json_output_shape(tmp_path: Path, capsys: Any) -> None:
    """--json emits a `findings` list with kind/section/file/detail per entry."""
    padding = "x" * (DEFAULT_CEILING_BYTES + 1)
    path = _write(tmp_path, "TEST_RESULTS.md", _fixed_shape_green(padding=padding))

    rc = main([str(path), "--json"])
    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert rc == 1
    assert "findings" in payload
    assert len(payload["findings"]) == 1
    finding = payload["findings"][0]
    assert finding["kind"] == "green-over-ceiling"
    assert finding["section"] == "Step 1 — a step"  # id-citation-discipline:ignore
    assert "bytes" in finding
    assert "ceiling" in finding


# ---------------------------------------------------------------------------
# Backward compatibility: the optional `Mutation:` step-section line must be
# invisible to this checker, in both its documented shapes.
#
# Both fixture lines below are built by calling the shipped
# scripts/mutation_sensor.py directly (loaded the same way this file loads
# itself, above) rather than hand-copied strings -- so a future change to the
# runner's exact rendering re-derives the fixture instead of silently
# drifting from it.
# ---------------------------------------------------------------------------

_MUTATION_SENSOR_PATH = Path(__file__).resolve().parent / "mutation_sensor.py"


def _load_mutation_sensor() -> Any:
    spec = importlib.util.spec_from_file_location("mutation_sensor", _MUTATION_SENSOR_PATH)
    assert spec is not None
    assert spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["mutation_sensor"] = mod
    spec.loader.exec_module(mod)
    return mod


_ms = _load_mutation_sensor()


def _mutation_survivors_line_at_cap() -> str:
    """The real `survivors=` rendering, sized so it lands exactly at the
    runner's 240-byte hard cap -- the boundary where a regression could
    silently push a green section over the ceiling."""
    per_function = {
        "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa": 19,
        "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb": 9,
        "cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc": 8,
        "d": 4,
        "e": 4,
        "f": 3,
        "g": 2,
    }
    histogram = {
        "killed": 0,
        "survived": sum(per_function.values()),
        "no_tests": 0,
        "skipped": 0,
        "suspicious": 0,
        "timeout": 0,
        "segfault": 0,
    }
    outcome = _ms.Ran(
        targets=("a.py",),
        mutants=sum(per_function.values()),
        histogram=histogram,
        per_function=per_function,
        elapsed_s=1.0,
    )
    line = _ms.render_line(outcome)
    assert len(line.encode("utf-8")) == _ms.LINE_BYTE_CAP, (
        f"fixture drifted off the byte cap: {len(line.encode('utf-8'))} bytes, "
        f"expected exactly {_ms.LINE_BYTE_CAP}"
    )
    return line


def _mutation_unavailable_line() -> str:
    """The real `unavailable` refusal rendering, built the same way the
    runner's own `_emit` renders a `toolchain-missing` refusal."""
    reason = _ms.ReasonCode.TOOLCHAIN_MISSING.value
    detail = _ms._one_line("uv not found on PATH")
    return f"Mutation: unavailable reason={reason} ({detail})"


def _fixed_shape_green_with_mutation(mutation_line: str) -> str:
    """The fixed green shape plus one optional line, placed after `Duration:`
    per `agent-pipeline-details.md § TEST_RESULTS.md Reconciliation`."""
    return _fixed_shape_green() + f"{mutation_line}\n"


def test_green_section_with_mutation_survivors_line_at_byte_cap_is_clean(tmp_path: Path) -> None:
    """A green section carrying the `survivors=` shape at exactly its 240-byte
    hard cap reads as zero findings -- no `green-over-ceiling`."""
    body = _fixed_shape_green_with_mutation(_mutation_survivors_line_at_cap())
    path = _write(tmp_path, "TEST_RESULTS.md", body)

    findings = find_findings(path, DEFAULT_CEILING_BYTES)

    assert findings == [], f"the Mutation: line must not surface a finding: {findings}"
    assert main([str(path)]) == 0


def test_green_section_with_mutation_unavailable_line_is_clean(tmp_path: Path) -> None:
    """A green section carrying the `unavailable` refusal shape reads as zero
    findings -- a legitimate refusal is not itself a shape violation."""
    body = _fixed_shape_green_with_mutation(_mutation_unavailable_line())
    path = _write(tmp_path, "TEST_RESULTS.md", body)

    findings = find_findings(path, DEFAULT_CEILING_BYTES)

    assert findings == []
    assert main([str(path)]) == 0


def test_red_section_with_mutation_line_is_never_flagged_for_size(tmp_path: Path) -> None:
    """A red section (fail > 0) carrying a Mutation: line -- even a grossly
    oversized one -- stays exempt from the size check, mirroring the
    pre-existing red-sections-are-never-flagged-for-size behavior."""
    oversized_line = "Mutation: survivors=1 mutants=1 targets=[a.py] (" + "x" * 2000 + ": 1)"
    body = (
        "## Step 1 — a step\n"  # id-citation-discipline:ignore
        "\n"
        "Command: `uv run pytest tests/ -q --tb=short -rf`\n"
        "Result: pass=10 fail=2 skip=0\n"
        "Duration: 4.0s\n"
        f"{oversized_line}\n"
    )
    path = _write(tmp_path, "TEST_RESULTS.md", body)

    findings = find_findings(path, DEFAULT_CEILING_BYTES)

    assert findings == [], (
        "a red section must stay exempt from size checks regardless of what it carries"
    )


def test_mutation_line_that_actually_blows_the_ceiling_is_still_caught(tmp_path: Path) -> None:
    """Canary: if the runner's 240-byte line cap regressed and a Mutation:
    line grew large enough to push a GREEN section's total past the
    1,024-byte ceiling,
    the checker must still flag it -- proving the two clean tests above pass
    because the shipped line legitimately stays under budget, not because
    this checker ignores the line's content."""
    uncapped_line = (
        "Mutation: survivors=1 mutants=1 targets=[a.py] (" + "x" * DEFAULT_CEILING_BYTES + ": 1)"
    )
    body = _fixed_shape_green_with_mutation(uncapped_line)
    path = _write(tmp_path, "TEST_RESULTS.md", body)

    findings = find_findings(path, DEFAULT_CEILING_BYTES)

    assert len(findings) == 1
    assert findings[0].kind == "green-over-ceiling"
    assert main([str(path)]) == 1


# ---------------------------------------------------------------------------
# Script error (exit 2)
# ---------------------------------------------------------------------------


def test_missing_file_exits_two(tmp_path: Path) -> None:
    """A FILE argument that does not exist on disk is a script error, exit 2."""
    rc = main([str(tmp_path / "does_not_exist.md")])

    assert rc == 2, "an unreadable file must exit 2, not be silently skipped"


# ---------------------------------------------------------------------------
# Adoption of the shared _step_schema module: block model, no-run declarations,
# malformed-line naming, and the live p3-5 corpus (td-236(b): 29 findings -> 6)
# ---------------------------------------------------------------------------


def test_all_zero_counts_above_an_oversized_failures_block_is_still_red(tmp_path: Path) -> None:
    """td-214: pass=0 fail=0 above a ### Failures sub-heading reads red even
    when the failure detail alone crosses the byte ceiling -- a red block is
    exempt from the size check regardless of size, and (since only a step
    heading opens a block) the oversized sub-heading never becomes its own
    green or missing section. This is the case that actually distinguishes
    the fix: a same-size all-zero block with a *small* Failures block reads
    green under both the old and the new classifier (it never crosses the
    ceiling either way), so only the oversized case forces the old
    fail=-only classifier to misread it as green-over-ceiling."""
    failure_detail = (
        "Traceback (most recent call last):\n"
        '  File "tests/test_thing.py", line 42, in test_thing\n'
        "    assert result == expected\n"
        "AssertionError: assert None == 'expected value'\n"
    ) * 15
    body = (
        "## Step 1 -- a step\n"  # id-citation-discipline:ignore
        "\n"
        "Command: `uv run pytest tests/ -q --tb=short -rf`\n"
        "Result: pass=0 fail=0 skip=0\n"
        "\n"
        "### Failures\n"
        "\n"
        f"{failure_detail}"
    )
    assert len(body.encode("utf-8")) > DEFAULT_CEILING_BYTES

    path = _write(tmp_path, "TEST_RESULTS.md", body)

    findings = find_findings(path, DEFAULT_CEILING_BYTES)

    assert findings == []
    assert main([str(path)]) == 0

    block = _step_schema.split_step_blocks(path.read_text(encoding="utf-8"))[0]
    kind, _detail = _mod._classify_block(block)
    assert kind == "red"


def test_declared_no_run_block_produces_no_missing_result_line_finding(tmp_path: Path) -> None:
    """A step block that ran no tests declares Result: none and is exempt from
    missing-result-line -- but stays bounded by the byte ceiling."""
    body = (
        "## Step 1 -- a step\n"  # id-citation-discipline:ignore
        "\n"
        "Result: none -- documentation-only step, no tests ran\n"
    )
    path = _write(tmp_path, "TEST_RESULTS.md", body)

    findings = find_findings(path, DEFAULT_CEILING_BYTES)

    assert findings == []
    assert main([str(path)]) == 0


def test_declared_no_run_block_over_the_ceiling_is_no_run_over_ceiling(tmp_path: Path) -> None:
    """A Result: none block cannot dodge the byte bound -- it gets its own
    finding kind, distinct from green-over-ceiling."""
    padding = "x" * (DEFAULT_CEILING_BYTES + 1)
    body = (
        "## Step 1 -- a step\n"  # id-citation-discipline:ignore
        "\n"
        f"Result: none -- {padding}\n"
    )
    path = _write(tmp_path, "TEST_RESULTS.md", body)

    findings = find_findings(path, DEFAULT_CEILING_BYTES)

    assert len(findings) == 1
    assert findings[0].kind == "no-run-over-ceiling"
    assert main([str(path)]) == 1


def test_a_malformed_result_line_names_its_malformation_distinct_from_a_missing_line(
    tmp_path: Path,
) -> None:
    """A malformed Result: line still counts as missing-result-line, but the
    checker must say *why* -- a repeated/garbled line and a block with no
    Result: line at all are different problems for a writer to fix, so their
    finding detail text must differ."""
    malformed_body = "## Step 1 -- a step\n\nResult: banana\n"  # id-citation-discipline:ignore
    missing_body = (
        "## Step 2 -- a step\n\nCommand: `uv run pytest`\n"  # id-citation-discipline:ignore
    )
    malformed_path = _write(tmp_path, "malformed.md", malformed_body)
    missing_path = _write(tmp_path, "missing.md", missing_body)

    malformed_findings = find_findings(malformed_path, DEFAULT_CEILING_BYTES)
    missing_findings = find_findings(missing_path, DEFAULT_CEILING_BYTES)

    assert malformed_findings[0].kind == "missing-result-line"
    assert missing_findings[0].kind == "missing-result-line"
    assert malformed_findings[0].detail != missing_findings[0].detail


# ---------------------------------------------------------------------------
# Live corpus: the harvested pipeline's own TEST_RESULTS.md (td-236(b))
# ---------------------------------------------------------------------------

_CORPUS_FIXTURE_PATH = (
    Path(__file__).resolve().parent.parent
    / "tests"
    / "fixtures"
    / "test_results_step_sections_corpus.md"
)
_P3_5_TEST_RESULTS_MD = _CORPUS_FIXTURE_PATH.read_text(encoding="utf-8")


def test_live_corpus_drops_from_29_findings_to_exactly_6(tmp_path: Path) -> None:
    """The harvested pipeline's own TEST_RESULTS.md reports 29 findings under
    the old any-``## ``-heading-is-a-section model, several of which name a
    sub-heading (Command, Failures, Lint / format, Id-citation discipline,
    Scope confirmation, Validator outputs, Manual path verification) as the
    ``section`` -- misreadings of blocks that were never violations. Splitting
    on step headings alone drops that to the 6 real findings below, and no
    finding's section is ever a sub-heading title."""
    path = _write(tmp_path, "TEST_RESULTS.md", _P3_5_TEST_RESULTS_MD)

    findings = find_findings(path, DEFAULT_CEILING_BYTES)

    kinds_and_sections = sorted((f.kind, f.section) for f in findings)
    assert kinds_and_sections == sorted(
        [
            ("missing-result-line", "Step 6"),  # id-citation-discipline:ignore
            ("missing-result-line", "Step 12 (doc-engineer)"),  # id-citation-discipline:ignore
            (
                "missing-result-line",
                "Step 13 (health-guards gauntlet, orchestrator)",  # id-citation-discipline:ignore
            ),
            (
                "missing-result-line",
                "Step 14 (dogfood, orchestrator)",  # id-citation-discipline:ignore
            ),
            (
                "green-over-ceiling",
                "Step 6 (post-review addendum, F1 fix)",  # id-citation-discipline:ignore
            ),
            ("green-over-ceiling", "Step 10"),  # id-citation-discipline:ignore
        ]
    )

    sub_heading_titles = {
        "Command",
        "Failures",
        "Lint / format",
        "Id-citation discipline",
        "Scope confirmation",
        "Validator outputs",
        "Manual path verification",
    }
    assert not {f.section for f in findings} & sub_heading_titles


def test_live_corpus_green_over_ceiling_byte_counts_match_the_measured_sections(
    tmp_path: Path,
) -> None:
    path = _write(tmp_path, "TEST_RESULTS.md", _P3_5_TEST_RESULTS_MD)

    findings = find_findings(path, DEFAULT_CEILING_BYTES)
    by_section = {f.section: f for f in findings if f.kind == "green-over-ceiling"}

    addendum_section = "Step 6 (post-review addendum, F1 fix)"  # id-citation-discipline:ignore
    final_section = "Step 10"  # id-citation-discipline:ignore
    assert by_section[addendum_section].byte_count == 3014
    assert by_section[final_section].byte_count == 1902


def test_live_corpus_cli_reports_six_findings_and_exits_one(tmp_path: Path, capsys: Any) -> None:
    path = _write(tmp_path, "TEST_RESULTS.md", _P3_5_TEST_RESULTS_MD)

    rc = main([str(path), "--json"])
    payload = json.loads(capsys.readouterr().out)

    assert rc == 1
    assert len(payload["findings"]) == 6
