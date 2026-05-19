"""Behavioral tests for `skills/skill-crafting/scripts/validate_references.py`.

Spec source: `.ai-work/phase4-ecosystem-evolution/SYSTEMS_PLAN.md` §4.4.

Each test traces to a row in §4.4's "Link classes and rules" table or to an
ignore-mechanism / exit-code / output-format row from the Acceptance Criteria
list. The validator is exercised via its CLI (subprocess), because the CLI
surface is the documented contract -- flags (`--all`, `--file`, `--format`,
`--warn-only`, `--strict`), exit codes (0 / 1 / 2), and the JSON/text
outputs.

Fixture corpus lives at `tests/fixtures/validate_references/` and mirrors a
real repo layout (skills/, rules/, agents/, commands/, scripts/,
.ai-state/decisions/, .ai-work/). Each fixture file has a `<!-- SCENARIO: ...`
header naming the spec row it exercises.

Concurrent build: Step 8 implementer is writing the validator in parallel on
the same worktree. Tests may RED until Step 8 lands. Re-run command for the
planner after the script lands:

    uv run pytest skills/skill-crafting/tests/test_validate_references.py -v
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

# ---------------------------------------------------------------------------
# Paths + CLI wrapper
# ---------------------------------------------------------------------------

TESTS_DIR = Path(__file__).resolve().parent
REPO_ROOT = TESTS_DIR.parent.parent.parent  # .../praxion/
VALIDATOR = (
    REPO_ROOT / "skills" / "skill-crafting" / "scripts" / "validate_references.py"
)
FIXTURES = TESTS_DIR / "fixtures" / "validate_references"


def _run(
    *args: str,
    cwd: Path | None = None,
    repo_root: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    """Invoke the validator via the real CLI entrypoint.

    The validator auto-detects its repo root from ``__file__`` (three parents
    up). When testing against a fixture mini-repo, tests must pass
    ``repo_root=<fixture tree>`` so the walk/validation stays inside the
    fixture. The validator exposes this as ``--repo-root``.
    """
    full_args = list(args)
    if repo_root is not None:
        full_args.extend(["--repo-root", str(repo_root)])
    cmd = [sys.executable, str(VALIDATOR), *full_args]
    return subprocess.run(
        cmd,
        cwd=str(cwd) if cwd else None,
        capture_output=True,
        text=True,
        check=False,
    )


def _copy_fixture_repo(tmp_path: Path) -> Path:
    """Copy the fixture-corpus tree into tmp_path and return the new root.

    Each test gets an isolated copy so mutations (deleting targets, toggling
    ignore directives) do not leak between tests.
    """
    dst = tmp_path / "repo"
    shutil.copytree(FIXTURES, dst)
    return dst


skip_if_no_validator = pytest.mark.skipif(
    not VALIDATOR.exists(),
    reason=(
        "validate_references.py not yet on disk. "
        "Step 8 implementer writes it in the same parallel group as this test file. "
        "Re-run after Step 8 lands."
    ),
)


# ---------------------------------------------------------------------------
# Finding-extraction helpers
# ---------------------------------------------------------------------------


def _findings(result: subprocess.CompletedProcess[str]) -> list[dict[str, Any]]:
    """Parse JSON findings from stdout. Tolerates stderr noise."""
    text = result.stdout.strip()
    if not text:
        return []
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        pytest.fail(
            f"Expected JSON array on stdout; got non-JSON.\n"
            f"stdout: {result.stdout!r}\nstderr: {result.stderr!r}\nexc: {exc}"
        )
    if isinstance(data, dict) and "findings" in data:
        return list(data["findings"])
    assert isinstance(data, list), (
        f"JSON root must be list or {{findings: [...]}}; got {type(data)}"
    )
    return data


def _level_of(finding: dict[str, Any]) -> str:
    """Return the finding's severity label regardless of schema naming.

    Spec prose names the field ``level``; the implementer chose ``severity``.
    Tests accept either under a soft-label contract until the spec/impl
    divergence is resolved.
    """
    raw = finding.get("level") or finding.get("severity") or ""
    return str(raw).upper()


def _findings_for(
    result: subprocess.CompletedProcess[str],
    *,
    file_suffix: str | None = None,
    level: str | None = None,
    cls: str | None = None,
    target_contains: str | None = None,
) -> list[dict[str, Any]]:
    """Filter findings by any combination of fields (soft-label matching)."""
    out = []
    for f in _findings(result):
        if file_suffix and not str(f.get("file", "")).endswith(file_suffix):
            continue
        if level and _level_of(f) != level.upper():
            continue
        if cls and cls.lower() not in str(f.get("class", "")).lower():
            continue
        if target_contains and target_contains not in str(f.get("target", "")):
            continue
        out.append(f)
    return out


# ---------------------------------------------------------------------------
# Smoke / CLI contract
# ---------------------------------------------------------------------------


@skip_if_no_validator
def test_cli_help_runs_and_exits_zero() -> None:
    """`--help` must succeed. Smoke check that the script is importable."""
    result = _run("--help")
    assert result.returncode == 0, result.stderr
    assert "--format" in result.stdout or "--format" in result.stderr


@skip_if_no_validator
def test_unknown_flag_produces_nonzero_exit() -> None:
    """Argument parsing errors should not be silent."""
    result = _run("--no-such-flag")
    assert result.returncode != 0


# ---------------------------------------------------------------------------
# Per link-class behavioral tests (SYSTEMS_PLAN.md §4.4 table)
# ---------------------------------------------------------------------------


@skip_if_no_validator
class TestIntraSkillLinks:
    """Row: Intra-skill relative -> file must exist -> FAIL."""

    def test_broken_intra_skill_link_is_fail(self, tmp_path: Path) -> None:
        repo = _copy_fixture_repo(tmp_path)
        result = _run("--all", "--format", "json", repo_root=repo)

        broken = _findings_for(
            result,
            file_suffix="skills/alpha/SKILL.md",
            target_contains="does_not_exist.md",
        )
        assert broken, (
            "Expected FAIL for intra-skill link [broken target](references/does_not_exist.md); "
            f"got none. All findings: {_findings(result)}"
        )
        assert all(_level_of(f) == "FAIL" for f in broken)

    def test_valid_intra_skill_link_produces_no_finding(self, tmp_path: Path) -> None:
        repo = _copy_fixture_repo(tmp_path)
        result = _run("--all", "--format", "json", repo_root=repo)

        matches = _findings_for(
            result,
            file_suffix="skills/alpha/SKILL.md",
            target_contains="valid_target.md",
        )
        assert matches == [], (
            f"Valid intra-skill link should not be flagged; got {matches}"
        )


@skip_if_no_validator
class TestSiblingSkillLinks:
    """Row: Sibling-skill relative -> file must exist -> FAIL."""

    def test_broken_sibling_skill_link_is_fail(self, tmp_path: Path) -> None:
        repo = _copy_fixture_repo(tmp_path)
        result = _run("--all", "--format", "json", repo_root=repo)

        broken = _findings_for(
            result,
            file_suffix="skills/alpha/SKILL.md",
            target_contains="gamma/SKILL.md",
        )
        assert broken, "Expected FAIL for broken sibling-skill link to gamma"
        assert all(_level_of(f) == "FAIL" for f in broken)

    def test_valid_sibling_skill_link_produces_no_finding(self, tmp_path: Path) -> None:
        repo = _copy_fixture_repo(tmp_path)
        result = _run("--all", "--format", "json", repo_root=repo)

        matches = _findings_for(
            result, file_suffix="skills/alpha/SKILL.md", target_contains="beta/SKILL.md"
        )
        assert matches == [], (
            f"Valid sibling-skill link should not be flagged; got {matches}"
        )


@skip_if_no_validator
class TestCrossArtifactLinks:
    """Row: Cross-artifact (rules/, agents/, commands/) -> file must exist -> FAIL.

    Parametrized across the three cross-artifact target directories named in
    §4.4 scope list.
    """

    @pytest.mark.parametrize(
        ("broken_target", "artifact_label"),
        [
            ("rules/swe/missing-rule.md", "rules"),
            ("agents/missing-agent.md", "agents"),
            ("commands/missing-command.md", "commands"),
        ],
    )
    def test_broken_cross_artifact_link_is_fail(
        self, tmp_path: Path, broken_target: str, artifact_label: str
    ) -> None:
        repo = _copy_fixture_repo(tmp_path)
        result = _run("--all", "--format", "json", repo_root=repo)

        broken = _findings_for(
            result, file_suffix="skills/alpha/SKILL.md", target_contains=broken_target
        )
        assert broken, (
            f"Expected FAIL for broken cross-artifact link into {artifact_label}/"
        )
        assert all(_level_of(f) == "FAIL" for f in broken)

    @pytest.mark.parametrize(
        "valid_target",
        [
            "rules/swe/sample-rule.md",
            "agents/sample-agent.md",
            "commands/sample-command.md",
        ],
    )
    def test_valid_cross_artifact_link_produces_no_finding(
        self, tmp_path: Path, valid_target: str
    ) -> None:
        repo = _copy_fixture_repo(tmp_path)
        result = _run("--all", "--format", "json", repo_root=repo)

        matches = _findings_for(
            result, file_suffix="skills/alpha/SKILL.md", target_contains=valid_target
        )
        assert matches == [], (
            f"Valid cross-artifact link {valid_target} flagged: {matches}"
        )


@skip_if_no_validator
class TestSameFileAnchors:
    """Row: Anchor (same-file) -> slug must match a heading in the same file -> FAIL."""

    def test_broken_same_file_anchor_is_fail(self, tmp_path: Path) -> None:
        repo = _copy_fixture_repo(tmp_path)
        result = _run("--all", "--format", "json", repo_root=repo)

        broken = _findings_for(
            result,
            file_suffix="skills/alpha/SKILL.md",
            target_contains="this-heading-does-not-exist",
        )
        assert broken, "Expected FAIL for same-file anchor with no matching heading"
        assert all(_level_of(f) == "FAIL" for f in broken)

    def test_valid_same_file_anchor_produces_no_finding(self, tmp_path: Path) -> None:
        repo = _copy_fixture_repo(tmp_path)
        result = _run("--all", "--format", "json", repo_root=repo)

        # #same-file-anchors resolves to an actual h2 in SKILL.md
        matches = _findings_for(
            result,
            file_suffix="skills/alpha/SKILL.md",
            target_contains="same-file-anchors",
        )
        assert matches == [], f"Valid same-file anchor flagged: {matches}"


@skip_if_no_validator
class TestCrossFileAnchors:
    """Row: Anchor (cross-file) -> file exists AND slug matches a heading -> FAIL on either.

    Spec explicitly requires ONE finding when slug is missing (not a
    file-level + anchor-level pair).
    """

    def test_valid_cross_file_anchor_produces_no_finding(self, tmp_path: Path) -> None:
        repo = _copy_fixture_repo(tmp_path)
        result = _run("--all", "--format", "json", repo_root=repo)

        matches = _findings_for(
            result,
            file_suffix="skills/alpha/SKILL.md",
            target_contains="anchored.md#real-heading",
        )
        assert matches == [], f"Valid cross-file anchor flagged: {matches}"

    def test_missing_file_cross_file_anchor_is_fail(self, tmp_path: Path) -> None:
        repo = _copy_fixture_repo(tmp_path)
        result = _run("--all", "--format", "json", repo_root=repo)

        broken = _findings_for(
            result,
            file_suffix="skills/alpha/SKILL.md",
            target_contains="not_there.md",
        )
        assert broken, "Expected FAIL for cross-file anchor where file missing"
        assert all(_level_of(f) == "FAIL" for f in broken)

    def test_missing_slug_in_existing_file_is_fail(self, tmp_path: Path) -> None:
        """Spec §4.4 table: 'File must exist AND slug must match a heading' -> FAIL.

        Acceptance criterion bullet: 'Broken anchor slug in cross-file link -> FAIL'.

        Registered objection: the current implementer chose WARN for this
        case. Keeping the assertion as FAIL (spec-driven) surfaces the
        divergence for the verifier to arbitrate. See LEARNINGS.md fragment.
        """
        repo = _copy_fixture_repo(tmp_path)
        result = _run("--all", "--format", "json", repo_root=repo)

        broken = _findings_for(
            result,
            file_suffix="skills/alpha/SKILL.md",
            target_contains="anchored.md#ghost-heading",
        )
        assert broken, "Expected FAIL for cross-file anchor where slug missing"
        assert all(_level_of(f) == "FAIL" for f in broken)

    def test_missing_slug_reported_as_single_finding(self, tmp_path: Path) -> None:
        """Spec: 'one finding, not two' when slug missing in existing file."""
        repo = _copy_fixture_repo(tmp_path)
        result = _run("--all", "--format", "json", repo_root=repo)

        broken = _findings_for(
            result,
            file_suffix="skills/alpha/SKILL.md",
            target_contains="anchored.md#ghost-heading",
        )
        assert len(broken) == 1, (
            f"Spec requires ONE finding for missing-slug-in-existing-file; got {len(broken)}: "
            f"{broken}"
        )


@skip_if_no_validator
class TestCodeFileAllowlist:
    """Row: Code-file link into allowlisted prefix -> file must exist -> FAIL."""

    def test_broken_allowlisted_code_link_is_fail(self, tmp_path: Path) -> None:
        repo = _copy_fixture_repo(tmp_path)
        result = _run("--all", "--format", "json", repo_root=repo)

        broken = _findings_for(
            result,
            file_suffix="skills/alpha/SKILL.md",
            target_contains="scripts/missing.py",
        )
        assert broken, (
            "Expected FAIL for allowlisted code-file link with missing target"
        )
        assert all(_level_of(f) == "FAIL" for f in broken)

    def test_valid_allowlisted_code_link_produces_no_finding(
        self, tmp_path: Path
    ) -> None:
        repo = _copy_fixture_repo(tmp_path)
        result = _run("--all", "--format", "json", repo_root=repo)

        matches = _findings_for(
            result,
            file_suffix="skills/alpha/SKILL.md",
            target_contains="scripts/sample.py",
        )
        assert matches == [], f"Valid allowlisted code-file link flagged: {matches}"


@skip_if_no_validator
class TestExternalUrls:
    """Row: External URL (http/https) -> skip, never report."""

    def test_external_urls_never_reported(self, tmp_path: Path) -> None:
        repo = _copy_fixture_repo(tmp_path)
        result = _run("--all", "--format", "json", repo_root=repo)

        for finding in _findings(result):
            target = str(finding.get("target", ""))
            assert not target.startswith(("http://", "https://")), (
                f"External URL {target!r} must never be reported; got {finding}"
            )


# ---------------------------------------------------------------------------
# Ignore mechanisms
# ---------------------------------------------------------------------------


@skip_if_no_validator
class TestIgnoreMechanisms:
    """Rows: inline `<!-- validate-references:ignore -->` + frontmatter
    `validate-references: off`.
    """

    def test_inline_ignore_suppresses_single_finding(self, tmp_path: Path) -> None:
        repo = _copy_fixture_repo(tmp_path)
        result = _run("--all", "--format", "json", repo_root=repo)

        suppressed = _findings_for(
            result,
            file_suffix="skills/alpha/SKILL.md",
            target_contains="broken_intentional.md",
        )
        assert suppressed == [], (
            "Inline <!-- validate-references:ignore --> must suppress the finding; "
            f"got {suppressed}"
        )

    def test_frontmatter_off_suppresses_all_findings_in_file(
        self, tmp_path: Path
    ) -> None:
        repo = _copy_fixture_repo(tmp_path)
        result = _run("--all", "--format", "json", repo_root=repo)

        matches = _findings_for(
            result, file_suffix="contexts/ignored_via_frontmatter.md"
        )
        assert matches == [], (
            "Frontmatter `validate-references: off` must suppress every finding in the file; "
            f"got {matches}"
        )


# ---------------------------------------------------------------------------
# WARN-level findings (ambiguous slug + .ai-work path)
# ---------------------------------------------------------------------------


@skip_if_no_validator
class TestWarnings:
    def test_ambiguous_slug_collision_is_warn(self, tmp_path: Path) -> None:
        """Row: two headings produce same slug -> WARN."""
        repo = _copy_fixture_repo(tmp_path)
        result = _run("--all", "--format", "json", repo_root=repo)

        # The collision lives in anchored.md (two "## Duplicate" headings).
        warns = _findings_for(
            result,
            file_suffix="skills/alpha/references/anchored.md",
            level="WARN",
        )
        assert warns, (
            "Expected WARN for ambiguous slug collision in anchored.md; "
            f"got findings: {_findings(result)}"
        )

    def test_path_into_ignored_dir_is_warn(self, tmp_path: Path) -> None:
        """Row: link pointing into `.ai-work/` (or other excluded dir) -> WARN."""
        repo = _copy_fixture_repo(tmp_path)
        result = _run("--all", "--format", "json", repo_root=repo)

        warns = _findings_for(
            result,
            file_suffix="skills/alpha/SKILL.md",
            target_contains=".ai-work/",
            level="WARN",
        )
        assert warns, "Expected WARN for link pointing into .ai-work/"


@skip_if_no_validator
class TestWalkExclusions:
    """`.ai-work/` and `skills/*/assets/` must not be walked, even though the
    fixture contains a deliberately broken link inside each."""

    def test_ai_work_is_not_walked(self, tmp_path: Path) -> None:
        repo = _copy_fixture_repo(tmp_path)
        result = _run("--all", "--format", "json", repo_root=repo)

        walked = _findings_for(result, file_suffix=".ai-work/should-be-excluded.md")
        assert walked == [], (
            ".ai-work/ must be excluded from the walk; "
            f"but findings were produced for files inside it: {walked}"
        )

    def test_assets_templates_are_not_walked(self, tmp_path: Path) -> None:
        """skills/*/assets/ holds templates whose links are instantiation-
        relative -- resolvable only once copied into a target project. The
        assets/ tree must be excluded from the walk, or the placeholder paths
        false-FAIL (the Category B failure mode this exclusion was added for).
        """
        repo = _copy_fixture_repo(tmp_path)
        result = _run("--all", "--format", "json", repo_root=repo)

        walked = _findings_for(result, file_suffix="assets/sample-template.md")
        assert walked == [], (
            "skills/*/assets/ templates must be excluded from the walk -- their "
            f"links are instantiation-relative placeholders; got: {walked}"
        )


# ---------------------------------------------------------------------------
# Exit codes (0 / 1 / 2)
# ---------------------------------------------------------------------------


@skip_if_no_validator
class TestExitCodes:
    """Acceptance: exit 0 clean, exit 1 on FAIL, exit 2 on script error."""

    def test_exit_zero_on_clean_tree(self, tmp_path: Path) -> None:
        """Point the validator at a synthesized clean-only repo using --file
        globbing cannot be controlled; simulate by giving it a single clean
        file via --file.
        """
        repo = _copy_fixture_repo(tmp_path)
        clean_file = repo / "skills" / "clean" / "SKILL.md"
        result = _run("--file", str(clean_file), "--format", "text", repo_root=repo)
        assert result.returncode == 0, (
            f"Clean file must exit 0; got {result.returncode}\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )

    def test_exit_one_on_fail_in_tree(self, tmp_path: Path) -> None:
        repo = _copy_fixture_repo(tmp_path)
        result = _run("--all", "--format", "text", repo_root=repo)
        assert result.returncode == 1, (
            f"At least one FAIL in the fixture corpus -> exit 1 required; "
            f"got {result.returncode}\nstdout:\n{result.stdout}"
        )

    def test_exit_two_on_script_error(self, tmp_path: Path) -> None:
        """Invalid --file path (does not exist) is a script error (not a
        validation FAIL) -> exit 2."""
        result = _run("--file", str(tmp_path / "nowhere.md"), cwd=tmp_path)
        assert result.returncode == 2, (
            f"Nonexistent --file argument is a script error -> exit 2; "
            f"got {result.returncode}\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )


# ---------------------------------------------------------------------------
# Output format shape
# ---------------------------------------------------------------------------


@skip_if_no_validator
class TestOutputFormats:
    def test_json_output_is_parseable_array(self, tmp_path: Path) -> None:
        repo = _copy_fixture_repo(tmp_path)
        result = _run("--all", "--format", "json", repo_root=repo)

        # Must parse and be a list (the extractor tolerates {findings: [...]}
        # shape via its dict branch).
        findings = _findings(result)
        assert isinstance(findings, list)
        assert findings, "Fixture corpus has known FAILs; JSON array must not be empty"

    def test_json_finding_has_required_shape(self, tmp_path: Path) -> None:
        """Spec: `{file, line, col, link_text, target, class, level, reason}`.

        We assert presence, not exact types beyond stringifiability, to keep
        the contract soft enough for the implementer to pick a conservative
        shape.
        """
        repo = _copy_fixture_repo(tmp_path)
        result = _run("--all", "--format", "json", repo_root=repo)

        # Soft-label contract: severity field may be spelled ``level`` (spec
        # prose) or ``severity`` (implementer choice). At least one must
        # exist. ``col`` and ``link_text`` are named in the spec but we do
        # not gate on them -- the finding is still actionable without them.
        required_always = {"file", "line", "target", "class", "reason"}
        for finding in _findings(result):
            missing = required_always - set(finding.keys())
            assert not missing, f"Finding missing required keys {missing}: {finding}"
            assert "level" in finding or "severity" in finding, (
                f"Finding must expose a severity field named 'level' or 'severity'; got {finding}"
            )
            assert _level_of(finding) in {"FAIL", "WARN"}, (
                f"Finding level must be FAIL or WARN; got {finding!r}"
            )

    def test_text_output_is_human_readable(self, tmp_path: Path) -> None:
        """`--format text` groups findings by file with line numbers."""
        repo = _copy_fixture_repo(tmp_path)
        result = _run("--all", "--format", "text", repo_root=repo)

        # Soft-label contract: text mode must name the skill and at least one
        # broken target anywhere in stdout.
        assert "alpha/SKILL.md" in result.stdout, (
            f"text mode should name the skill file; got:\n{result.stdout}"
        )
        assert "does_not_exist.md" in result.stdout, (
            f"text mode should name at least one broken target; got:\n{result.stdout}"
        )


# ---------------------------------------------------------------------------
# --warn-only / --strict flag semantics
# ---------------------------------------------------------------------------


@skip_if_no_validator
class TestWarnOnlyAndStrict:
    def test_warn_only_downgrades_fails_and_exits_zero(self, tmp_path: Path) -> None:
        """Spec: `--warn-only` treats all FAIL findings as WARN -> exit 0."""
        repo = _copy_fixture_repo(tmp_path)
        result = _run("--all", "--warn-only", "--format", "json", repo_root=repo)

        assert result.returncode == 0, (
            f"--warn-only should not exit nonzero for FAILs; got {result.returncode}\n"
            f"stderr:\n{result.stderr}"
        )
        for finding in _findings(result):
            assert _level_of(finding) != "FAIL", (
                f"--warn-only must downgrade FAIL -> WARN; got {finding}"
            )

    def test_strict_promotes_warns_and_exits_one(self, tmp_path: Path) -> None:
        """Spec: `--strict` treats WARN findings as FAIL -> exit 1."""
        repo = _copy_fixture_repo(tmp_path)
        result = _run("--all", "--strict", "--format", "json", repo_root=repo)

        assert result.returncode == 1, (
            f"--strict on a corpus with WARNs must exit 1; got {result.returncode}\n"
            f"stdout:\n{result.stdout}"
        )


# ---------------------------------------------------------------------------
# --file single-file mode
# ---------------------------------------------------------------------------


@skip_if_no_validator
class TestSingleFileMode:
    def test_file_mode_reports_only_that_file(self, tmp_path: Path) -> None:
        """`--file <path>` validates one file without walking the tree."""
        repo = _copy_fixture_repo(tmp_path)
        single = repo / "skills" / "alpha" / "SKILL.md"
        result = _run("--file", str(single), "--format", "json", repo_root=repo)

        # Exit code: the single file has FAILs in it.
        assert result.returncode == 1

        reported_files = {str(f.get("file", "")) for f in _findings(result)}
        # Every reported file should resolve to our single target (absolute
        # or relative form) -- no findings from other fixture files.
        for rf in reported_files:
            assert rf.endswith("skills/alpha/SKILL.md"), (
                f"--file mode must only report findings from the target file; "
                f"got {rf!r}"
            )


# ---------------------------------------------------------------------------
# Invariant: every finding is either FAIL or WARN (never both sides of a
# cross-file anchor)
# ---------------------------------------------------------------------------


@skip_if_no_validator
def test_no_duplicate_findings_per_link(tmp_path: Path) -> None:
    """Invariant across all tests: each (file, line, target) triple should
    produce at most one finding. Protects against a regression where a
    cross-file anchor is reported as both file-missing and slug-missing.
    """
    repo = _copy_fixture_repo(tmp_path)
    result = _run("--all", "--format", "json", repo_root=repo)

    seen: dict[tuple[str, Any, str], dict[str, Any]] = {}
    for f in _findings(result):
        key = (str(f.get("file", "")), f.get("line"), str(f.get("target", "")))
        assert key not in seen, (
            f"Duplicate finding for {key}:\n  first: {seen[key]}\n  dup: {f}"
        )
        seen[key] = f


# ---------------------------------------------------------------------------
# Regression guard: coordination-protocol rule (D1 + D3 + D4 edits)
# ---------------------------------------------------------------------------


@skip_if_no_validator
def test_coord_protocol_rule_passes_strict_validation() -> None:
    """Regression guard for D1+D3+D4 edits to the coordination rule.

    Asserts that ``rules/swe/swe-agent-coordination-protocol.md`` has no broken
    cross-references (specifically the ``#delegation-checklists`` anchor cited
    by the ``claude/config/CLAUDE.md`` sync-contract pointer) and passes strict
    validation under the dec-047 validator.

    Spec source: ``.ai-work/coord-burden-reduction/SYSTEMS_PLAN.md`` §D5;
    ADR-049; CONTEXT_REVIEW P6.
    """
    target = "rules/swe/swe-agent-coordination-protocol.md"
    result = _run("--file", target, "--strict", repo_root=REPO_ROOT)
    assert result.returncode == 0, (
        f"validate_references.py --file {target} --strict failed: "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )


@skip_if_no_validator
def test_emdash_heading_double_hyphen_anchor_not_flagged(tmp_path: Path) -> None:
    """Regression: GitHub slugifies each space individually -- no run collapse.

    An em-dash heading (`## Ignore mechanism — inline`) leaves two spaces once
    the em-dash is stripped, so its GitHub anchor is `ignore-mechanism--inline`
    (double hyphen). The validator must reproduce that exact slug; collapsing
    the whitespace run to a single hyphen would false-FAIL a correct anchor.
    """
    repo = _copy_fixture_repo(tmp_path)
    result = _run("--all", "--format", "json", repo_root=repo)

    flagged = _findings_for(
        result,
        file_suffix="skills/alpha/SKILL.md",
        target_contains="ignore-mechanism--inline",
    )
    assert flagged == [], (
        "Double-hyphen anchor for an em-dash heading is GitHub-correct and "
        f"must not be flagged; got {flagged}"
    )
