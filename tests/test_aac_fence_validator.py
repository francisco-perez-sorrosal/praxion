"""Behavioral tests for scripts/aac_fence_validator.py — TDD RED state.

This file encodes the behavioral contract the fence validator must satisfy,
derived from the decision points in dec-098.  Production code does not exist
yet; these tests are expected to fail with ModuleNotFoundError until Step 1.4
(the implementer's concurrent step) lands.

=== Public API contract (Step 1.4 implementer: please adopt this shape) ===

    from scripts.aac_fence_validator import validate, ValidationResult, Finding, Severity

    validate(path: Path | str) -> ValidationResult

    @dataclass
    class ValidationResult:
        verdict: str          # one of: "PASS", "PASS_WITH_WARNINGS", "FAIL"
        findings: list[Finding]

    @dataclass
    class Finding:
        severity: str         # one of: "WARN", "FAIL"  (no "PASS" finding needed)
        code: str             # machine-stable string, e.g. "unbalanced-fence",
                              # "missing-attribute", "source-path-not-found",
                              # "validator-unable-to-verify-drift"
        message: str          # human-readable, may contain details
        line: int | None      # 1-based line number of the offending fence opener,
                              # None when not attributable to a specific line

=== Disable hook for likec4 (test_likec4_unavailable_emits_warn_not_fail) ===

    Set the environment variable AAC_FENCE_VALIDATOR_LIKEC4=disabled.
    When this variable is present and its value is "disabled", the validator
    must skip all subprocess / MCP calls to likec4 and emit exactly one WARN
    per aac:generated fence with code "validator-unable-to-verify-drift".

    The implementer may wire this by checking:
        os.environ.get("AAC_FENCE_VALIDATOR_LIKEC4") == "disabled"
    before dispatching to likec4.  The env-var approach is preferred over
    monkeypatching an internal function because it works regardless of
    whether the implementation uses subprocess shelling or MCP tool calls.

=== Import strategy ===

    Production module: scripts/aac_fence_validator.py
    Import path: scripts.aac_fence_validator  (works because pyproject.toml
    sets  pythonpath = ["."] so the repo root is on sys.path)

    Imports are placed *inside* each test body (deferred import pattern) so
    that pytest collection succeeds even before the production module exists.
    Each test independently resolves to RED (ModuleNotFoundError) or GREEN
    (when the implementation is present), without failing collection.
"""

from __future__ import annotations

from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Fixture paths — relative to the repo root (resolved in tests via the
# FIXTURES constant below so there are no hardcoded absolute paths).
# ---------------------------------------------------------------------------

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "aac_fence_validator"


# ===========================================================================
# 1. Unbalanced fence opener → FAIL
# ===========================================================================


def test_unbalanced_opener_fails(tmp_path):
    """A markdown file with an aac:generated opener but no aac:end closer
    must produce a FAIL result with a finding that identifies the offending
    line.

    This validates the fence-balance-tracking requirement: an opener without
    a matching closer is a structural contract violation.
    """
    from scripts.aac_fence_validator import validate  # noqa: PLC0415

    md = FIXTURES / "unbalanced_opener.md"
    result = validate(md)

    assert result.verdict == "FAIL", f"Expected FAIL for unbalanced fence, got {result.verdict!r}"
    assert len(result.findings) >= 1
    fail_findings = [f for f in result.findings if f.severity == "FAIL"]
    assert fail_findings, "Expected at least one FAIL finding"
    codes = {f.code for f in fail_findings}
    assert "unbalanced-fence" in codes, f"Expected finding code 'unbalanced-fence', got {codes!r}"


# ===========================================================================
# 2. Missing required attributes → FAIL
# ===========================================================================


@pytest.mark.parametrize(
    ("fixture_name", "description"),
    [
        ("missing_source_attr.md", "aac:generated without source= attribute"),
        ("missing_view_attr.md", "aac:generated without view= attribute"),
        ("missing_owner_attr.md", "aac:authored without owner= attribute"),
    ],
)
def test_missing_required_attribute_fails(fixture_name, description):
    """Missing required fence attributes produce a FAIL result.

    For aac:generated fences both source= and view= are required.
    For aac:authored fences owner= is required.
    Each missing attribute is its own FAIL — the validator must not stop at
    the first missing attribute but report all violations found.
    """
    from scripts.aac_fence_validator import validate  # noqa: PLC0415

    md = FIXTURES / fixture_name
    result = validate(md)

    assert result.verdict == "FAIL", f"{description}: expected FAIL, got {result.verdict!r}"
    fail_findings = [f for f in result.findings if f.severity == "FAIL"]
    assert fail_findings, f"{description}: expected at least one FAIL finding"
    codes = {f.code for f in fail_findings}
    assert "missing-attribute" in codes, (
        f"{description}: expected finding code 'missing-attribute', got {codes!r}"
    )


# ===========================================================================
# 3. source= path that does not exist → FAIL
# ===========================================================================


def test_source_path_must_resolve(tmp_path):
    """An aac:generated fence whose source= value points to a non-existent
    file must produce a FAIL result with a path-not-found finding.

    The source= path is resolved relative to the markdown file being validated
    (or to the repo root — either is acceptable; document the chosen behaviour
    in scripts/aac_fence_validator.py).
    """
    from scripts.aac_fence_validator import validate  # noqa: PLC0415

    md_content = """\
# Architecture

<!-- aac:generated source=does-not-exist.c4 view=L1 -->
Some content here.
<!-- aac:end -->
"""
    md = tmp_path / "arch.md"
    md.write_text(md_content, encoding="utf-8")

    result = validate(md)

    assert result.verdict == "FAIL", (
        f"Expected FAIL when source path is missing, got {result.verdict!r}"
    )
    fail_findings = [f for f in result.findings if f.severity == "FAIL"]
    codes = {f.code for f in fail_findings}
    assert "source-path-not-found" in codes, (
        f"Expected finding code 'source-path-not-found', got {codes!r}"
    )


# ===========================================================================
# 4. aac:authored region must not trigger any drift check → PASS
# ===========================================================================


def test_authored_region_skips_drift_check():
    """An aac:authored region with arbitrary content must produce PASS.

    The validator must never compare authored content against any generated
    output.  Even if the text looks nothing like what LikeC4 would produce,
    the authored region is always accepted as-is.
    """
    from scripts.aac_fence_validator import validate  # noqa: PLC0415

    md = FIXTURES / "authored_region_valid.md"
    result = validate(md)

    assert result.verdict in {"PASS", "PASS_WITH_WARNINGS"}, (
        f"Expected PASS (or PASS_WITH_WARNINGS) for authored region, "
        f"got {result.verdict!r}.  Findings: {result.findings!r}"
    )
    # No FAIL findings must be present
    fail_findings = [f for f in result.findings if f.severity == "FAIL"]
    assert not fail_findings, (
        f"No FAIL findings expected for authored region; got {fail_findings!r}"
    )


# ===========================================================================
# 5. likec4 unavailable → WARN not FAIL
# ===========================================================================


def test_likec4_unavailable_emits_warn_not_fail(monkeypatch):
    """When likec4 is unavailable, the validator emits exactly one WARN per
    aac:generated fence (code "validator-unable-to-verify-drift") and the
    overall verdict is PASS_WITH_WARNINGS (or PASS), NOT FAIL.

    Disable hook: the implementer must respect the environment variable
        AAC_FENCE_VALIDATOR_LIKEC4=disabled
    When this variable is set to "disabled", every attempt to call likec4
    (subprocess or MCP) is skipped and replaced with a WARN.

    If the implementer prefers a different disable hook (e.g. monkeypatching
    a specific function), they may adapt this test — but must document the
    chosen hook in scripts/aac_fence_validator.py and update the contract
    block at the top of this test file.
    """
    from scripts.aac_fence_validator import validate  # noqa: PLC0415

    monkeypatch.setenv("AAC_FENCE_VALIDATOR_LIKEC4", "disabled")

    # Use the fixture that contains a valid aac:generated fence with a
    # source= path that actually exists (tests/fixtures/minimal.c4).
    md = FIXTURES / "generated_real_source.md"
    result = validate(md)

    assert result.verdict in {"PASS", "PASS_WITH_WARNINGS"}, (
        f"Expected PASS or PASS_WITH_WARNINGS when likec4 is disabled, "
        f"got {result.verdict!r}.  Findings: {result.findings!r}"
    )
    warn_findings = [
        f
        for f in result.findings
        if f.severity == "WARN" and f.code == "validator-unable-to-verify-drift"
    ]
    assert len(warn_findings) == 1, (
        f"Expected exactly 1 WARN with code 'validator-unable-to-verify-drift'; "
        f"got {warn_findings!r}.  Full findings: {result.findings!r}"
    )


# ===========================================================================
# 6. Idempotent: two sequential runs on the same file produce identical output
# ===========================================================================


def test_idempotent_double_run_identical_output(tmp_path, monkeypatch):
    """Running the validator twice on the same file must produce equal results.

    "Equal" means the verdict string and the set of (severity, code) pairs on
    findings are identical.  The validator is side-effect-free, so the second
    run cannot see any output from the first.
    """
    from scripts.aac_fence_validator import validate  # noqa: PLC0415

    # Disable likec4 so we don't depend on it being installed.
    monkeypatch.setenv("AAC_FENCE_VALIDATOR_LIKEC4", "disabled")

    md_content = """\
# Architecture

<!-- aac:generated source=does-not-exist.c4 view=L1 -->
Some content.
<!-- aac:end -->

<!-- aac:authored owner=alice -->
Some authored narrative.
<!-- aac:end -->
"""
    md = tmp_path / "arch.md"
    md.write_text(md_content, encoding="utf-8")

    result_a = validate(md)
    result_b = validate(md)

    assert result_a.verdict == result_b.verdict, (
        f"Idempotence violation: first run verdict={result_a.verdict!r}, "
        f"second run verdict={result_b.verdict!r}"
    )
    findings_a = sorted((f.severity, f.code) for f in result_a.findings)
    findings_b = sorted((f.severity, f.code) for f in result_b.findings)
    assert findings_a == findings_b, (
        f"Idempotence violation: first run findings={findings_a!r}, "
        f"second run findings={findings_b!r}"
    )


# ===========================================================================
# 7. No file mutation: the validator must never write to the input file
# ===========================================================================


def test_no_file_mutation(tmp_path, monkeypatch):
    """The validator must not write to, truncate, or otherwise modify the
    markdown file being validated.

    This is verified by comparing raw bytes before and after validation.
    """
    from scripts.aac_fence_validator import validate  # noqa: PLC0415

    # Disable likec4 to isolate the file-mutation check from any subprocess.
    monkeypatch.setenv("AAC_FENCE_VALIDATOR_LIKEC4", "disabled")

    content = """\
# Architecture

<!-- aac:generated source=tests/fixtures/minimal.c4 view=index -->
| Element | Kind  |
|---------|-------|
| user    | actor |
<!-- aac:end -->

<!-- aac:authored owner=bob -->
Authored rationale paragraph.
<!-- aac:end -->
"""
    md = tmp_path / "arch.md"
    md.write_bytes(content.encode("utf-8"))
    bytes_before = md.read_bytes()

    validate(md)

    bytes_after = md.read_bytes()
    assert bytes_before == bytes_after, (
        "Validator mutated the input file — before and after bytes differ"
    )


# ===========================================================================
# 8. Fences inside backtick code blocks are ignored → PASS
# ===========================================================================


def test_fence_inside_markdown_code_block_is_ignored():
    """aac: markers inside a backtick fenced code block must be ignored.

    Documentation files commonly show the convention syntax as examples inside
    code blocks.  The validator must not treat these as real fence regions —
    otherwise every doc that demonstrates the syntax would produce false FAILs.
    """
    from scripts.aac_fence_validator import validate  # noqa: PLC0415

    md = FIXTURES / "fence_inside_backtick_code_block.md"
    result = validate(md)

    assert result.verdict in {"PASS", "PASS_WITH_WARNINGS"}, (
        f"Expected PASS (or PASS_WITH_WARNINGS) for aac: markers inside a "
        f"backtick code block, got {result.verdict!r}.  Findings: {result.findings!r}"
    )
    fail_findings = [f for f in result.findings if f.severity == "FAIL"]
    assert not fail_findings, (
        f"No FAIL findings expected; the inner fence markers should be ignored. "
        f"Got: {fail_findings!r}"
    )


# ===========================================================================
# 9. Fences inside tilde code blocks are ignored → PASS
# ===========================================================================


def test_fence_inside_tilde_code_block_is_ignored():
    """aac: markers inside a tilde fenced code block must be ignored.

    CommonMark allows both backtick (```) and tilde (~~~) fence delimiters.
    The validator must respect both forms when deciding to skip inner content.
    """
    from scripts.aac_fence_validator import validate  # noqa: PLC0415

    md = FIXTURES / "fence_inside_tilde_code_block.md"
    result = validate(md)

    assert result.verdict in {"PASS", "PASS_WITH_WARNINGS"}, (
        f"Expected PASS (or PASS_WITH_WARNINGS) for aac: markers inside a "
        f"tilde code block, got {result.verdict!r}.  Findings: {result.findings!r}"
    )
    fail_findings = [f for f in result.findings if f.severity == "FAIL"]
    assert not fail_findings, (
        f"No FAIL findings expected; the inner fence markers should be ignored. "
        f"Got: {fail_findings!r}"
    )


# ===========================================================================
# 10. Real aac fence after a code block is still parsed → PASS or WARN
# ===========================================================================


def test_aac_fence_after_code_block_still_parses():
    """A real aac: region that follows a closed code block must still be parsed.

    The in_code_block flag must reset to False when the code block closes so
    that subsequent aac: fence regions are recognized and validated normally.
    A valid aac:authored region after a code block should produce PASS
    (or PASS_WITH_WARNINGS — never FAIL).
    """
    from scripts.aac_fence_validator import validate  # noqa: PLC0415

    md = FIXTURES / "real_aac_fence_after_code_block.md"
    result = validate(md)

    assert result.verdict in {"PASS", "PASS_WITH_WARNINGS"}, (
        f"Expected PASS (or PASS_WITH_WARNINGS) for a valid aac:authored region "
        f"after a code block, got {result.verdict!r}.  Findings: {result.findings!r}"
    )
    fail_findings = [f for f in result.findings if f.severity == "FAIL"]
    assert not fail_findings, (
        f"No FAIL findings expected for the authored region after the code block. "
        f"Got: {fail_findings!r}"
    )
