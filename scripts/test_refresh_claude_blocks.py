"""Unit tests for scripts/refresh_claude_blocks.py (consumer refresh script).

Tests are designed from the classification/self-onboard-guard behavioral
contract in SYSTEMS_PLAN.md and IMPLEMENTATION_PLAN.md, not from reading the
production implementation, which does not exist yet at the time these tests
are written.

Two test layers, mirroring test_sync_canonical_blocks.py's split:

1. **Pure classification unit tests** (`classify_block`): given an already
   extracted live body (or None) and a single slug's manifest entry, exercise
   the four-way absent/current/stale/modified decision in isolation -- no
   file I/O, no CLI.
2. **CLI black-box tests** (`main`): build a synthetic manifest + synthetic
   target CLAUDE.md in tmp_path (hermetic; avoids the gitignored-fixture
   trap) and drive the full extract-then-classify pipeline through
   `main(["--check" | "--json", "--repo-root", ..., "--manifest", ...])`.
   Covers the self-onboard guard, the refresh-eligible scope boundary, the
   duplicate-heading determinism edge case, and the R1 normalization
   robustness canary (a stale block in its real Phase-6-appended shape must
   classify `stale`, never `modified`). One test drives the real shipped
   manifest against a real canonical body for an end-to-end round trip.
3. **Apply-mode black-box tests** (`main(["--apply", ...])`): drive the same
   extract-then-classify pipeline through to a mutating action. Covers the
   three post-classification actions (append on absent, in-place replace on
   stale, refuse-and-report on modified) plus the refuse-to-clobber
   gate-liveness canary, atomicity across a mixed-classification file, and
   the index-shift regression risk of replacing more than one stale block in
   a single pass. `--apply` does not exist yet at the time these tests are
   written -- they are expected to fail with an argparse "unrecognized
   arguments" `SystemExit` until a later step adds it. These tests assume a
   `CANONICAL_DIR` module attribute (mirroring `sync_canonical_blocks.py`'s
   existing override convention) that apply-mode reads the current canonical
   body text from -- the manifest itself carries only hashes, never body
   text, so appending/replacing content must come from somewhere else. Later
   additions (closing intra-step light-review WARNs against the already-GREEN
   implementation) cover the no-truncation byte-length invariant, the
   self-onboard guard firing under `--apply` specifically, and a duplicate
   eligible heading under `--apply`.
"""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SCRIPTS_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPTS_DIR.parent

sys.path.insert(0, str(SCRIPTS_DIR))
from canonical_block_identity import find_heading_span, hash_block_body  # noqa: E402

# Synthetic bodies for a single refresh-eligible slug, shaped like a real
# canonical block (heading line + prose) without depending on any specific
# real canonical file's content.
_AGENT_PIPELINE_CURRENT_BODY = "## Agent Pipeline\n\nCurrent revision content for tests.\n"
_AGENT_PIPELINE_STALE_BODY = "## Agent Pipeline\n\nOlder revision content for tests.\n"
_AGENT_PIPELINE_MODIFIED_BODY = (
    "## Agent Pipeline\n\nA bespoke locally-customized paragraph nobody shipped.\n"
)

# A single-slug manifest entry: current == the last history entry, mirroring
# the real shipped schema's invariant.
_SINGLE_SLUG_BLOCKS = {
    "agent-pipeline": {
        "current": hash_block_body(_AGENT_PIPELINE_CURRENT_BODY),
        "history": [
            hash_block_body(_AGENT_PIPELINE_STALE_BODY),
            hash_block_body(_AGENT_PIPELINE_CURRENT_BODY),
        ],
    }
}

# The three non-current classifications, each as a ready-made target
# CLAUDE.md body -- precomputed here (tuple-form parametrize) so the test
# body itself contains no branching logic.
_NON_CURRENT_CASES = (
    ("absent", "# Project\n\nProse.\n"),
    ("stale", "# Project\n\nProse.\n\n" + _AGENT_PIPELINE_STALE_BODY),
    ("modified", "# Project\n\nProse.\n\n" + _AGENT_PIPELINE_MODIFIED_BODY),
)


# ---------------------------------------------------------------------------
# Module loader
# ---------------------------------------------------------------------------


def _load_module():
    """Import refresh_claude_blocks lazily (ensures a fresh module each call)."""
    sys.path.insert(0, str(SCRIPTS_DIR))
    import refresh_claude_blocks as mod

    return importlib.reload(mod)


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------


def _write_repo(directory: Path, claude_md_text: str, *, plugin_source: bool = False) -> Path:
    """Build a minimal target repo containing CLAUDE.md, returning its root.

    When `plugin_source` is True, also plant `.claude-plugin/plugin.json` --
    the self-onboard guard's detection signal.
    """
    repo = directory / "repo"
    repo.mkdir()
    (repo / "CLAUDE.md").write_text(claude_md_text, encoding="utf-8")
    if plugin_source:
        plugin_dir = repo / ".claude-plugin"
        plugin_dir.mkdir()
        (plugin_dir / "plugin.json").write_text("{}", encoding="utf-8")
    return repo


def _write_manifest(directory: Path, blocks: dict) -> Path:
    """Write a manifest file matching the shipped schema, returning its path."""
    manifest = {"schema_version": "1.0", "blocks": blocks}
    path = directory / "block-history.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    return path


def _write_canonical_dir(directory: Path, bodies: dict[str, str]) -> Path:
    """Write each slug's canonical body to <dir>/canonical-blocks/<slug>.md.

    Apply-mode actions (append/replace) need a slug's current canonical body
    *text*, not just its hash -- the manifest only ever stores hashes. Tests
    redirect apply-mode's lookup via an overridable `CANONICAL_DIR` module
    attribute, mirroring the established `sync_canonical_blocks.py` test
    convention of the same name.
    """
    canonical_dir = directory / "canonical-blocks"
    canonical_dir.mkdir(exist_ok=True)
    for slug, body in bodies.items():
        (canonical_dir / f"{slug}.md").write_text(body, encoding="utf-8")
    return canonical_dir


# ---------------------------------------------------------------------------
# classify_block: pure four-way classification (no file I/O)
# ---------------------------------------------------------------------------


def test_classify_block_reports_absent_when_live_body_is_none() -> None:
    """A block whose heading was never installed (no live body to compare) is
    classified `absent` -- there is nothing to hash or look up."""
    mod = _load_module()

    result = mod.classify_block(None, _SINGLE_SLUG_BLOCKS["agent-pipeline"])

    assert result == "absent"


def test_classify_block_reports_current_when_hash_matches_manifest_current() -> None:
    """A live body whose hash equals the manifest's current hash is
    classified `current` -- the block is already up to date and must be left
    untouched."""
    mod = _load_module()

    result = mod.classify_block(_AGENT_PIPELINE_CURRENT_BODY, _SINGLE_SLUG_BLOCKS["agent-pipeline"])

    assert result == "current"


def test_classify_block_reports_stale_when_hash_matches_a_historical_entry() -> None:
    """A live body whose hash matches a historical (non-current) manifest
    entry is classified `stale` -- outdated but unmodified boilerplate that
    can be safely replaced."""
    mod = _load_module()

    result = mod.classify_block(_AGENT_PIPELINE_STALE_BODY, _SINGLE_SLUG_BLOCKS["agent-pipeline"])

    assert result == "stale"


def test_classify_block_reports_modified_when_hash_matches_no_manifest_entry() -> None:
    """A live body whose hash matches neither the current hash nor any
    historical hash is classified `modified` -- a locally-customized block
    that must be protected from replacement."""
    mod = _load_module()

    result = mod.classify_block(
        _AGENT_PIPELINE_MODIFIED_BODY, _SINGLE_SLUG_BLOCKS["agent-pipeline"]
    )

    assert result == "modified"


# ---------------------------------------------------------------------------
# Self-onboard guard
# ---------------------------------------------------------------------------


def test_main_refuses_when_repo_root_is_a_plugin_source_repo_without_override(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A target repo carrying `.claude-plugin/plugin.json` at its root refuses
    to run, exiting non-zero, when the override env var is unset. The single
    manifest slug is genuinely current in this fixture -- if the guard did
    NOT fire, `--check` would exit 0 -- so a non-zero result here is
    non-vacuous proof the guard actually bit."""
    monkeypatch.delenv("PRAXION_ALLOW_SELF_ONBOARD", raising=False)
    repo = _write_repo(
        tmp_path,
        "# Project\n\nProse.\n\n" + _AGENT_PIPELINE_CURRENT_BODY,
        plugin_source=True,
    )
    manifest_path = _write_manifest(tmp_path, _SINGLE_SLUG_BLOCKS)

    mod = _load_module()
    exit_code = mod.main(["--check", "--repo-root", str(repo), "--manifest", str(manifest_path)])
    captured = capsys.readouterr()
    output = captured.out + captured.err

    assert exit_code != 0, "refresh must refuse to run against a plugin-source repo root"
    assert "PRAXION_ALLOW_SELF_ONBOARD" in output, (
        f"the refusal message must name the override env var. Got:\n{output}"
    )


def test_main_proceeds_when_self_onboard_override_env_var_is_set(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Setting PRAXION_ALLOW_SELF_ONBOARD=1 lets refresh run against a
    plugin-source repo root and classify normally. The fixture's single slug
    is genuinely current, so exit 0 here proves both that the guard was
    bypassed and that classification proceeded (not merely a vacuous no-op)."""
    monkeypatch.setenv("PRAXION_ALLOW_SELF_ONBOARD", "1")
    repo = _write_repo(
        tmp_path,
        "# Project\n\nProse.\n\n" + _AGENT_PIPELINE_CURRENT_BODY,
        plugin_source=True,
    )
    manifest_path = _write_manifest(tmp_path, _SINGLE_SLUG_BLOCKS)

    mod = _load_module()
    exit_code = mod.main(["--check", "--repo-root", str(repo), "--manifest", str(manifest_path)])

    assert exit_code == 0, "the override env var must let refresh proceed and classify normally"


# ---------------------------------------------------------------------------
# --check: exit-code contract (exit 1 unless every manifest slug is current)
# ---------------------------------------------------------------------------


def test_check_exits_zero_when_all_manifest_slugs_are_current(tmp_path: Path) -> None:
    """--check exits 0 when every eligible slug in the manifest classifies
    `current` -- the clean-repo, nothing-to-do case."""
    repo = _write_repo(tmp_path, "# Project\n\nProse.\n\n" + _AGENT_PIPELINE_CURRENT_BODY)
    manifest_path = _write_manifest(tmp_path, _SINGLE_SLUG_BLOCKS)

    mod = _load_module()
    exit_code = mod.main(["--check", "--repo-root", str(repo), "--manifest", str(manifest_path)])

    assert exit_code == 0, "--check must exit 0 when every manifest slug is current"


@pytest.mark.parametrize(("classification", "claude_md_text"), _NON_CURRENT_CASES)
def test_check_exits_nonzero_when_the_only_eligible_block_is_not_current(
    tmp_path: Path, classification: str, claude_md_text: str
) -> None:
    """--check exits non-zero whenever the only eligible block is absent,
    stale, or modified -- it never mutates the file, only reports."""
    repo = _write_repo(tmp_path, claude_md_text)
    manifest_path = _write_manifest(tmp_path, _SINGLE_SLUG_BLOCKS)
    before = (repo / "CLAUDE.md").read_text(encoding="utf-8")

    mod = _load_module()
    exit_code = mod.main(["--check", "--repo-root", str(repo), "--manifest", str(manifest_path)])

    assert exit_code != 0, (
        f"--check must exit non-zero when the only eligible block is '{classification}'"
    )
    assert (repo / "CLAUDE.md").read_text(encoding="utf-8") == before, (
        "--check must never mutate the target file"
    )


# ---------------------------------------------------------------------------
# --json: machine-readable classification, unconditional exit 0
# ---------------------------------------------------------------------------


def test_json_flag_prints_machine_readable_classification_dict(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """--json prints a JSON object mapping each eligible slug in the manifest
    to its classification string."""
    repo = _write_repo(tmp_path, "# Project\n\nProse.\n\n" + _AGENT_PIPELINE_CURRENT_BODY)
    manifest_path = _write_manifest(tmp_path, _SINGLE_SLUG_BLOCKS)

    mod = _load_module()
    mod.main(["--json", "--repo-root", str(repo), "--manifest", str(manifest_path)])

    result = json.loads(capsys.readouterr().out)
    assert result == {"agent-pipeline": "current"}


def test_json_flag_exits_zero_even_when_a_block_is_modified(tmp_path: Path) -> None:
    """--json carries no exit-code semantics beyond script errors -- it exits
    0 regardless of what the classification turns out to be, unlike --check."""
    repo = _write_repo(tmp_path, "# Project\n\nProse.\n\n" + _AGENT_PIPELINE_MODIFIED_BODY)
    manifest_path = _write_manifest(tmp_path, _SINGLE_SLUG_BLOCKS)

    mod = _load_module()
    exit_code = mod.main(["--json", "--repo-root", str(repo), "--manifest", str(manifest_path)])

    assert exit_code == 0, "--json must exit 0 even when a block classifies 'modified'"


# ---------------------------------------------------------------------------
# Scope protection: non-eligible slugs are never classified or inspected
# ---------------------------------------------------------------------------


def test_never_classifies_a_slug_outside_the_refreshable_set_even_if_manifest_carries_it(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A manifest entry for a non-eligible slug (defense in depth against a
    malformed or hand-edited manifest) is never surfaced in the
    classification output, even when the target CLAUDE.md carries that
    heading too -- REFRESHABLE_SLUGS is a hard membership boundary, not a
    filter applied only at manifest-generation time."""
    claude_md_text = (
        "## Working in this project\n\nTemplate-filled local content.\n\n"
        + _AGENT_PIPELINE_CURRENT_BODY
    )
    repo = _write_repo(tmp_path, claude_md_text)
    blocks = dict(_SINGLE_SLUG_BLOCKS)
    blocks["project-essentials"] = {
        "current": hash_block_body("## Working in this project\n\nSomething else entirely.\n"),
        "history": [],
    }
    manifest_path = _write_manifest(tmp_path, blocks)

    mod = _load_module()
    mod.main(["--json", "--repo-root", str(repo), "--manifest", str(manifest_path)])

    result = json.loads(capsys.readouterr().out)
    assert "project-essentials" not in result, (
        f"a non-eligible slug must never appear in the classification output. Got: {result}"
    )
    assert result == {"agent-pipeline": "current"}


# ---------------------------------------------------------------------------
# Duplicate heading: deterministic first-occurrence classification, no crash
# ---------------------------------------------------------------------------


def test_classifies_deterministically_on_first_occurrence_when_heading_is_duplicated(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A target CLAUDE.md carrying the same eligible heading twice classifies
    using the FIRST occurrence only, deterministically, and never raises --
    protects against a duplicate-heading target crashing the refresh or
    silently picking a nondeterministic occurrence."""
    claude_md_text = (
        _AGENT_PIPELINE_CURRENT_BODY
        + "\n"
        + "## Compaction Guidance\n\nUnrelated block.\n\n"
        + _AGENT_PIPELINE_MODIFIED_BODY  # second occurrence -- must be ignored
    )
    repo = _write_repo(tmp_path, claude_md_text)
    manifest_path = _write_manifest(tmp_path, _SINGLE_SLUG_BLOCKS)

    mod = _load_module()
    mod.main(["--json", "--repo-root", str(repo), "--manifest", str(manifest_path)])
    first_result = json.loads(capsys.readouterr().out)

    mod.main(["--json", "--repo-root", str(repo), "--manifest", str(manifest_path)])
    second_result = json.loads(capsys.readouterr().out)

    assert first_result == {"agent-pipeline": "current"}, (
        "classification must use the FIRST occurrence's body (current), never the "
        f"second (modified). Got: {first_result}"
    )
    assert second_result == first_result, (
        "classifying the same duplicate-heading target twice must be deterministic"
    )


# ---------------------------------------------------------------------------
# R1 robustness canary: a stale block in its real Phase-6-appended shape
# ---------------------------------------------------------------------------


def test_classifies_stale_when_historical_body_is_appended_in_realistic_shape(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A stale (historical, non-current) block embedded in the exact shape
    Phase 6 actually produces -- a leading blank-line separator from
    preceding content, its own trailing newline, then a following heading --
    classifies `stale`, never `modified`. This is the R1 falsifier: a
    normalization or extraction gap here would misclassify safe, unmodified
    boilerplate as locally customized."""
    claude_md_text = (
        "# Some Project\n\nSome existing prose.\n"
        "\n"  # leading blank-line separator, exactly as Phase 6 appends
        + _AGENT_PIPELINE_STALE_BODY  # ends with its own trailing newline
        + "\n"
        "## Some Other Heading\n\nUnrelated trailing content.\n"
    )
    repo = _write_repo(tmp_path, claude_md_text)
    manifest_path = _write_manifest(tmp_path, _SINGLE_SLUG_BLOCKS)

    mod = _load_module()
    mod.main(["--json", "--repo-root", str(repo), "--manifest", str(manifest_path)])

    result = json.loads(capsys.readouterr().out)
    assert result == {"agent-pipeline": "stale"}, (
        f"a historical body appended in its real on-disk shape must classify 'stale', "
        f"never 'modified'. Got: {result}"
    )


# ---------------------------------------------------------------------------
# Integration round trip: real canonical body vs. the real shipped manifest
# ---------------------------------------------------------------------------


def test_real_canonical_body_against_real_shipped_manifest_classifies_current(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The real, shipped praxion-process canonical body, embedded into a
    target CLAUDE.md in the real Phase-6 append shape, classifies `current`
    against the real shipped claude/canonical-blocks/block-history.json --
    not a synthetic manifest. Proves the manifest schema and the
    classification pipeline agree on the real production artifact, not just
    hand-built fixtures."""
    real_manifest_path = REPO_ROOT / "claude" / "canonical-blocks" / "block-history.json"
    real_canonical_body = (
        REPO_ROOT / "claude" / "canonical-blocks" / "praxion-process.md"
    ).read_text(encoding="utf-8")
    claude_md_text = "# Some Project\n\nExisting prose.\n\n" + real_canonical_body
    repo = _write_repo(tmp_path, claude_md_text)

    mod = _load_module()
    mod.main(["--json", "--repo-root", str(repo), "--manifest", str(real_manifest_path)])

    result = json.loads(capsys.readouterr().out)
    assert result["praxion-process"] == "current", (
        f"the real praxion-process canonical body, freshly appended, must classify "
        f"'current' against the real shipped manifest. Got: {result}"
    )


# ---------------------------------------------------------------------------
# --apply: absent -> append current canonical body at file end
# ---------------------------------------------------------------------------


def test_apply_appends_current_canonical_block_when_absent(tmp_path: Path) -> None:
    """A missing block is installed: --apply appends the current canonical
    heading and body at file end, separated from the existing content by
    exactly one blank line, leaving the existing content itself untouched."""
    before = "# Project\n\nExisting prose untouched by refresh.\n"
    repo = _write_repo(tmp_path, before)
    manifest_path = _write_manifest(tmp_path, _SINGLE_SLUG_BLOCKS)
    canonical_dir = _write_canonical_dir(tmp_path, {"agent-pipeline": _AGENT_PIPELINE_CURRENT_BODY})

    mod = _load_module()
    mod.CANONICAL_DIR = canonical_dir  # type: ignore[attr-defined]
    exit_code = mod.main(["--apply", "--repo-root", str(repo), "--manifest", str(manifest_path)])

    after = (repo / "CLAUDE.md").read_text(encoding="utf-8")
    assert exit_code == 0, "--apply must exit 0 after installing an absent block"
    assert after == before + "\n" + _AGENT_PIPELINE_CURRENT_BODY, (
        f"an absent block must be appended (heading+body, one blank-line separator) "
        f"at file end, with existing content untouched. Got:\n{after!r}"
    )


# ---------------------------------------------------------------------------
# --apply: stale -> in-place replacement, surrounding content untouched
# ---------------------------------------------------------------------------


def test_apply_replaces_stale_body_in_place_at_end_of_file(tmp_path: Path) -> None:
    """A stale (historical, unmodified) block at the very end of the file is
    replaced in place with the current canonical body; the preceding content
    is untouched."""
    prefix = "# Project\n\nExisting prose untouched by refresh.\n\n"
    before = prefix + _AGENT_PIPELINE_STALE_BODY
    repo = _write_repo(tmp_path, before)
    manifest_path = _write_manifest(tmp_path, _SINGLE_SLUG_BLOCKS)
    canonical_dir = _write_canonical_dir(tmp_path, {"agent-pipeline": _AGENT_PIPELINE_CURRENT_BODY})

    mod = _load_module()
    mod.CANONICAL_DIR = canonical_dir  # type: ignore[attr-defined]
    exit_code = mod.main(["--apply", "--repo-root", str(repo), "--manifest", str(manifest_path)])

    after = (repo / "CLAUDE.md").read_text(encoding="utf-8")
    assert exit_code == 0, "--apply must exit 0 after replacing a stale block"
    assert after == prefix + _AGENT_PIPELINE_CURRENT_BODY, (
        f"a stale block must be replaced in place with the current canonical body; "
        f"preceding content must be untouched. Got:\n{after!r}"
    )


def test_apply_replaces_stale_body_preserving_separator_before_next_heading(
    tmp_path: Path,
) -> None:
    """A stale block followed by another section is replaced in place, and
    the blank-line separator before the following heading survives -- it is
    surrounding structure, not part of the block being replaced -- and the
    following section's content is untouched."""
    prefix = "# Project\n\nExisting prose.\n\n"
    suffix = "\n## Trailing Heading\n\nTrailing prose untouched.\n"
    before = prefix + _AGENT_PIPELINE_STALE_BODY + suffix
    repo = _write_repo(tmp_path, before)
    manifest_path = _write_manifest(tmp_path, _SINGLE_SLUG_BLOCKS)
    canonical_dir = _write_canonical_dir(tmp_path, {"agent-pipeline": _AGENT_PIPELINE_CURRENT_BODY})

    mod = _load_module()
    mod.CANONICAL_DIR = canonical_dir  # type: ignore[attr-defined]
    mod.main(["--apply", "--repo-root", str(repo), "--manifest", str(manifest_path)])

    after = (repo / "CLAUDE.md").read_text(encoding="utf-8")
    assert after == prefix + _AGENT_PIPELINE_CURRENT_BODY + suffix, (
        f"replacing a stale block must not swallow the blank-line separator before "
        f"the next heading, and must not touch the following section. Got:\n{after!r}"
    )


# ---------------------------------------------------------------------------
# --apply: modified -> the refuse-to-clobber gate-liveness canary (primary
# proof that locally-customized blocks are never silently overwritten)
# ---------------------------------------------------------------------------


def test_apply_leaves_modified_block_byte_identical_and_emits_diff_and_pointer(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Golden case (mirrors the real-world precedent of a project with a
    bespoke paragraph appended inside the block section): a locally
    customized block classifies `modified`, and --apply must never touch the
    file in this case. Capture the raw bytes before running and assert the
    full file is byte-identical after -- not merely 'looks the same' -- plus
    a unified diff and a pointer to the interactive command for a human to
    resolve."""
    claude_md_text = "# Project\n\nProse.\n\n" + _AGENT_PIPELINE_MODIFIED_BODY
    repo = _write_repo(tmp_path, claude_md_text)
    manifest_path = _write_manifest(tmp_path, _SINGLE_SLUG_BLOCKS)
    canonical_dir = _write_canonical_dir(tmp_path, {"agent-pipeline": _AGENT_PIPELINE_CURRENT_BODY})
    before_bytes = (repo / "CLAUDE.md").read_bytes()

    mod = _load_module()
    mod.CANONICAL_DIR = canonical_dir  # type: ignore[attr-defined]
    exit_code = mod.main(["--apply", "--repo-root", str(repo), "--manifest", str(manifest_path)])
    output = capsys.readouterr().out

    after_bytes = (repo / "CLAUDE.md").read_bytes()
    assert exit_code == 0, "--apply must exit 0 even when a block is refused as modified"
    assert after_bytes == before_bytes, (
        "a modified block must leave the target file byte-identical after --apply -- "
        "not just textually equal, the raw bytes must match exactly"
    )
    assert "/refresh-claude-blocks" in output, (
        f"--apply must point the user at the interactive command for a modified "
        f"block. Got:\n{output}"
    )
    assert "---" in output, f"--apply must emit a unified diff for a modified block. Got:\n{output}"
    assert "+++" in output, f"--apply must emit a unified diff for a modified block. Got:\n{output}"


# ---------------------------------------------------------------------------
# --apply: atomicity across a mixed-classification file (pre-mortem #3)
# ---------------------------------------------------------------------------


def test_apply_handles_mixed_classifications_in_one_file_without_touching_other_blocks(
    tmp_path: Path,
) -> None:
    """A single file carrying one stale, one modified, and one current block
    is processed atomically: the stale block is replaced, the modified and
    current blocks and every other byte in the file are left exactly as they
    were, and no heading is duplicated or corrupted by the multi-block pass."""
    cg_current = "## Compaction Guidance\n\nCurrent compaction body for tests.\n"
    cg_modified = (
        "## Compaction Guidance\n\nA bespoke locally-customized paragraph nobody shipped.\n"
    )
    bc_current = "## Behavioral Contract\n\nCurrent behavioral-contract body for tests.\n"
    blocks = {
        "agent-pipeline": _SINGLE_SLUG_BLOCKS["agent-pipeline"],
        "compaction-guidance": {
            "current": hash_block_body(cg_current),
            "history": [hash_block_body(cg_current)],
        },
        "behavioral-contract": {
            "current": hash_block_body(bc_current),
            "history": [hash_block_body(bc_current)],
        },
    }

    prefix = "# Project\n\nIntro prose untouched by refresh.\n\n"
    before = (
        prefix
        + _AGENT_PIPELINE_STALE_BODY  # stale -- must be replaced
        + "\n"
        + cg_modified  # modified -- must be left exactly alone
        + "\n"
        + bc_current  # current -- must be left exactly alone, ends the file
    )
    repo = _write_repo(tmp_path, before)
    manifest_path = _write_manifest(tmp_path, blocks)
    canonical_dir = _write_canonical_dir(
        tmp_path,
        {
            "agent-pipeline": _AGENT_PIPELINE_CURRENT_BODY,
            "compaction-guidance": cg_current,
            "behavioral-contract": bc_current,
        },
    )

    mod = _load_module()
    mod.CANONICAL_DIR = canonical_dir  # type: ignore[attr-defined]
    exit_code = mod.main(["--apply", "--repo-root", str(repo), "--manifest", str(manifest_path)])

    after = (repo / "CLAUDE.md").read_text(encoding="utf-8")
    expected = prefix + _AGENT_PIPELINE_CURRENT_BODY + "\n" + cg_modified + "\n" + bc_current
    assert exit_code == 0, "--apply must exit 0 on a mixed-classification file"
    assert after == expected, (
        f"only the stale block may change; the modified and current blocks and every "
        f"other byte must be untouched. Got:\n{after!r}"
    )
    for heading in ("## Agent Pipeline", "## Compaction Guidance", "## Behavioral Contract"):
        assert after.count(heading) == 1, (
            f"heading {heading!r} must appear exactly once -- a multi-block apply pass "
            f"must never duplicate or fuse headings. Got:\n{after!r}"
        )


# ---------------------------------------------------------------------------
# --apply: multi-block ordering -- index-shift regression seed
# ---------------------------------------------------------------------------


def test_apply_replaces_two_stale_blocks_in_one_pass_without_index_shift_corruption(
    tmp_path: Path,
) -> None:
    """Two stale blocks in one file are both replaced correctly in a single
    --apply pass. The first block's replacement body has a different line
    count than its stale original -- a naive forward-order splice would shift
    the second block's line indices and corrupt its replacement; the
    reverse-order splice technique must avoid this."""
    ap_stale = "## Agent Pipeline\n\nOlder revision line one.\nOlder revision line two.\n"
    ap_current = _AGENT_PIPELINE_CURRENT_BODY
    cg_stale = "## Compaction Guidance\n\nOlder compaction body for tests.\n"
    cg_current = "## Compaction Guidance\n\nCurrent compaction body for tests.\n"
    blocks = {
        "agent-pipeline": {
            "current": hash_block_body(ap_current),
            "history": [hash_block_body(ap_stale), hash_block_body(ap_current)],
        },
        "compaction-guidance": {
            "current": hash_block_body(cg_current),
            "history": [hash_block_body(cg_stale), hash_block_body(cg_current)],
        },
    }

    prefix = "# Project\n\nIntro prose untouched by refresh.\n\n"
    before = prefix + ap_stale + "\n" + cg_stale
    repo = _write_repo(tmp_path, before)
    manifest_path = _write_manifest(tmp_path, blocks)
    canonical_dir = _write_canonical_dir(
        tmp_path, {"agent-pipeline": ap_current, "compaction-guidance": cg_current}
    )

    mod = _load_module()
    mod.CANONICAL_DIR = canonical_dir  # type: ignore[attr-defined]
    mod.main(["--apply", "--repo-root", str(repo), "--manifest", str(manifest_path)])

    after = (repo / "CLAUDE.md").read_text(encoding="utf-8")
    expected = prefix + ap_current + "\n" + cg_current
    assert after == expected, (
        f"both stale blocks must be replaced correctly in one pass, regardless of "
        f"processing order or line-count differences between old and new bodies. "
        f"Got:\n{after!r}"
    )


# ---------------------------------------------------------------------------
# --apply: no-truncation canary (pre-mortem #3) -- byte-length delta guard
# ---------------------------------------------------------------------------


def test_apply_output_byte_length_matches_exact_stale_replacement_delta_no_truncation(
    tmp_path: Path,
) -> None:
    """--apply's write reflects exactly the stale-replacement-plus-append
    delta -- never a truncated subset of it. Mixing a stale replacement (byte
    count changes), an untouched modified block, an untouched current block,
    and an appended absent block in one file, the output's total byte length
    must equal the arithmetic delta derivable purely from the fixture's known
    text -- independent of reading the implementation. A truncated write
    (partial flush, dropped append, chopped replacement) would produce a
    shorter file than this exact expectation."""
    cg_current = "## Compaction Guidance\n\nCurrent compaction body for tests.\n"
    cg_modified = (
        "## Compaction Guidance\n\nA bespoke locally-customized paragraph nobody shipped.\n"
    )
    bc_current = "## Behavioral Contract\n\nCurrent behavioral-contract body for tests.\n"
    pp_current = "## Praxion Process\n\nCurrent praxion-process body for tests.\n"
    blocks = {
        "agent-pipeline": _SINGLE_SLUG_BLOCKS["agent-pipeline"],
        "compaction-guidance": {
            "current": hash_block_body(cg_current),
            "history": [hash_block_body(cg_current)],
        },
        "behavioral-contract": {
            "current": hash_block_body(bc_current),
            "history": [hash_block_body(bc_current)],
        },
        "praxion-process": {
            "current": hash_block_body(pp_current),
            "history": [hash_block_body(pp_current)],
        },
    }

    prefix = "# Project\n\nIntro prose untouched by refresh.\n\n"
    before_text = (
        prefix
        + _AGENT_PIPELINE_STALE_BODY  # stale -- replaced
        + "\n"
        + cg_modified  # modified -- untouched
        + "\n"
        + bc_current  # current -- untouched, ends the pre-apply file
        # praxion-process is entirely absent from the file -- appended at the end
    )
    repo = _write_repo(tmp_path, before_text)
    manifest_path = _write_manifest(tmp_path, blocks)
    canonical_dir = _write_canonical_dir(
        tmp_path,
        {
            "agent-pipeline": _AGENT_PIPELINE_CURRENT_BODY,
            "compaction-guidance": cg_current,
            "behavioral-contract": bc_current,
            "praxion-process": pp_current,
        },
    )
    before_bytes = (repo / "CLAUDE.md").read_bytes()

    mod = _load_module()
    mod.CANONICAL_DIR = canonical_dir  # type: ignore[attr-defined]
    mod.main(["--apply", "--repo-root", str(repo), "--manifest", str(manifest_path)])

    after_bytes = (repo / "CLAUDE.md").read_bytes()

    removed = _AGENT_PIPELINE_STALE_BODY.encode("utf-8")
    inserted = _AGENT_PIPELINE_CURRENT_BODY.encode("utf-8")
    appended = ("\n" + pp_current).encode("utf-8")
    expected_length = len(before_bytes) - len(removed) + len(inserted) + len(appended)

    assert len(after_bytes) == expected_length, (
        "the write must reflect exactly the stale-replacement delta plus the appended "
        f"absent block -- no truncation. before={len(before_bytes)}b "
        f"after={len(after_bytes)}b expected={expected_length}b"
    )
    assert len(after_bytes) >= len(before_bytes) - len(removed), (
        "the output must never be shorter than the original minus the replaced span -- "
        "a shorter result is the signature of a truncated write"
    )
    for heading in (
        "## Agent Pipeline",
        "## Compaction Guidance",
        "## Behavioral Contract",
        "## Praxion Process",
    ):
        assert after_bytes.decode("utf-8").count(heading) == 1, (
            f"heading {heading!r} must appear exactly once in a well-formed output. "
            f"Got:\n{after_bytes.decode('utf-8')!r}"
        )


# ---------------------------------------------------------------------------
# --apply: self-onboard guard fires before any mutation is attempted
# ---------------------------------------------------------------------------


def test_apply_refuses_when_repo_root_is_a_plugin_source_repo_without_override(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The self-onboard guard is not classify-mode-only: --apply against a
    plugin-source repo root refuses identically to --check, exiting
    non-zero, naming the override env var, and leaving the target file
    byte-identical. The fixture's live body is genuinely stale (an unguarded
    apply run WOULD replace it) -- so byte-identity here is non-vacuous proof
    the guard fired before any mutation was even attempted, not an accident
    of nothing needing to change."""
    monkeypatch.delenv("PRAXION_ALLOW_SELF_ONBOARD", raising=False)
    claude_md_text = "# Project\n\nProse.\n\n" + _AGENT_PIPELINE_STALE_BODY
    repo = _write_repo(tmp_path, claude_md_text, plugin_source=True)
    manifest_path = _write_manifest(tmp_path, _SINGLE_SLUG_BLOCKS)
    before_bytes = (repo / "CLAUDE.md").read_bytes()

    mod = _load_module()
    exit_code = mod.main(["--apply", "--repo-root", str(repo), "--manifest", str(manifest_path)])
    captured = capsys.readouterr()
    output = captured.out + captured.err
    after_bytes = (repo / "CLAUDE.md").read_bytes()

    assert exit_code != 0, "--apply must refuse to run against a plugin-source repo root"
    assert "PRAXION_ALLOW_SELF_ONBOARD" in output, (
        f"the refusal message must name the override env var. Got:\n{output}"
    )
    assert after_bytes == before_bytes, (
        "a refused --apply run must never mutate the target file, even though the "
        "fixture's block is genuinely stale and would otherwise have been replaced"
    )


# ---------------------------------------------------------------------------
# --apply: duplicate eligible heading -- only the first occurrence is touched
# ---------------------------------------------------------------------------


def test_apply_replaces_only_first_occurrence_when_heading_is_duplicated(
    tmp_path: Path,
) -> None:
    """A target CLAUDE.md that already carries the same eligible heading
    twice has only its FIRST occurrence classified and replaced by --apply.
    The second occurrence is left completely untouched -- byte-identical to
    its pre-apply text -- and no heading is fused or further duplicated by
    the replacement pass."""
    second_occurrence = "## Agent Pipeline\n\nA second occurrence that apply must never touch.\n"
    before = (
        _AGENT_PIPELINE_STALE_BODY  # first occurrence -- stale, must be replaced
        + "\n"
        + "## Some Other Heading\n\nUnrelated content untouched by refresh.\n"
        + "\n"
        + second_occurrence  # second occurrence -- must be left untouched
    )
    repo = _write_repo(tmp_path, before)
    manifest_path = _write_manifest(tmp_path, _SINGLE_SLUG_BLOCKS)
    canonical_dir = _write_canonical_dir(tmp_path, {"agent-pipeline": _AGENT_PIPELINE_CURRENT_BODY})

    mod = _load_module()
    mod.CANONICAL_DIR = canonical_dir  # type: ignore[attr-defined]
    exit_code = mod.main(["--apply", "--repo-root", str(repo), "--manifest", str(manifest_path)])

    after = (repo / "CLAUDE.md").read_text(encoding="utf-8")
    expected = (
        _AGENT_PIPELINE_CURRENT_BODY
        + "\n"
        + "## Some Other Heading\n\nUnrelated content untouched by refresh.\n"
        + "\n"
        + second_occurrence
    )
    assert exit_code == 0, "--apply must exit 0 on a duplicate-heading target"
    assert after == expected, (
        "only the first occurrence's body may change; the second occurrence must be "
        f"byte-identical to its pre-apply text. Got:\n{after!r}"
    )
    assert after.endswith(second_occurrence), (
        "the second occurrence must remain byte-untouched at the file's end"
    )
    assert after.count("## Agent Pipeline") == 2, (
        "a pre-existing duplicate heading must stay a duplicate -- apply must never fuse "
        f"or further duplicate headings. Got:\n{after!r}"
    )


# ---------------------------------------------------------------------------
# td-056: apply-mode's span lookup is the shared primitive, not a re-implementation
# ---------------------------------------------------------------------------


def test_module_no_longer_defines_its_own_block_span_scanner() -> None:
    """`refresh_claude_blocks` must not carry a private re-implementation of
    the heading-boundary scan -- `_find_block_span` (the historical name) is
    gone, and every consumer calls `canonical_block_identity.find_heading_span`
    directly. A resurrected private copy is exactly how classify-time and
    apply-time boundaries silently diverged before."""
    mod = _load_module()

    assert not hasattr(mod, "_find_block_span"), (
        "a private _find_block_span means the module re-implemented the shared "
        "boundary primitive instead of calling canonical_block_identity.find_heading_span"
    )


def test_apply_replace_span_matches_classification_span_on_an_h3_nested_fixture() -> None:
    """Behavioral divergence canary: feed the SAME H3-nested fixture through
    both the classify-time path (`extract_live_body`) and the apply-time path
    (`_apply_stale_replacements`'s span lookup, now `find_heading_span`) and
    assert they bound the identical span. Before td-056, the two paths were
    separate implementations that happened to agree; this proves they are now
    structurally the same call, not just coincidentally identical output."""
    from canonical_block_identity import extract_live_body

    claude_md_text = (
        "# Project\n\nProse.\n\n"
        + _AGENT_PIPELINE_STALE_BODY.rstrip("\n")
        + "\n\n### Not a section boundary\n\nMore prose under the block.\n\n"
        "## Trailing Heading\n\nTrailing prose.\n"
    )
    heading = "## Agent Pipeline"

    classify_time_body = extract_live_body(claude_md_text, heading)

    lines = claude_md_text.splitlines(keepends=True)
    span = find_heading_span(lines, heading)
    assert span is not None
    apply_time_body = "".join(lines[span[0] : span[1]])

    assert apply_time_body == classify_time_body, (
        "classify-time extraction and apply-time span lookup disagree on an "
        f"H3-nested fixture. classify={classify_time_body!r} apply={apply_time_body!r}"
    )


def test_apply_reads_claude_md_from_disk_exactly_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`--apply` reads CLAUDE.md exactly once (in `main()`'s classification
    read) and threads that text through to `run_apply` -- it must never
    perform a second, independent `read_text` of the same file (the TOCTOU
    double-read td-056 also flagged)."""
    before = "# Project\n\nExisting prose untouched by refresh.\n\n" + _AGENT_PIPELINE_STALE_BODY
    repo = _write_repo(tmp_path, before)
    manifest_path = _write_manifest(tmp_path, _SINGLE_SLUG_BLOCKS)
    canonical_dir = _write_canonical_dir(tmp_path, {"agent-pipeline": _AGENT_PIPELINE_CURRENT_BODY})

    mod = _load_module()
    mod.CANONICAL_DIR = canonical_dir  # type: ignore[attr-defined]

    read_calls = {"count": 0}
    original_read_text = Path.read_text

    def _counting_read_text(self: Path, *args: object, **kwargs: object) -> str:
        if self == repo / "CLAUDE.md":
            read_calls["count"] += 1
        return original_read_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", _counting_read_text)

    exit_code = mod.main(["--apply", "--repo-root", str(repo), "--manifest", str(manifest_path)])

    assert exit_code == 0
    assert read_calls["count"] == 1, (
        f"CLAUDE.md was read {read_calls['count']} time(s) during --apply; expected exactly "
        "one read, threaded from classification into run_apply"
    )


# ---------------------------------------------------------------------------
# Placement-resolved target (sidecar-owned projects never mutate the
# tracked CLAUDE.md; blocks land in the shadowed CLAUDE.local.md instead)
# ---------------------------------------------------------------------------


def test_apply_under_sidecar_placement_writes_shadow_and_leaves_tracked_file_untouched(
    tmp_path: Path,
) -> None:
    """A sidecar-placed project whose manifest marks `CLAUDE.md` `untouched`
    must have `--apply` append the absent block to `.praxion-state/CLAUDE.local.md`
    (`block_target()`'s fallback redirect) -- never to the tracked
    `CLAUDE.md`, which stays byte-identical."""
    from test_state_repo import _build_sidecar_owned_fixture

    tracked_claude_md = "# Team Project\n\nHand-written, tracked prose.\n"
    fixture = _build_sidecar_owned_fixture(
        tmp_path,
        origin=None,
        extra_manifest=(
            "paths:\n  CLAUDE.md:\n    intent: untouched\n    reason: preexisting-team-file\n"
            "autocommit: manual\nremote: null\n"
        ),
    )
    (fixture.project_root / "CLAUDE.md").write_text(tracked_claude_md, encoding="utf-8")

    manifest_path = _write_manifest(tmp_path, _SINGLE_SLUG_BLOCKS)
    canonical_dir = _write_canonical_dir(tmp_path, {"agent-pipeline": _AGENT_PIPELINE_CURRENT_BODY})

    mod = _load_module()
    mod.CANONICAL_DIR = canonical_dir  # type: ignore[attr-defined]

    exit_code = mod.main(
        ["--apply", "--repo-root", str(fixture.project_root), "--manifest", str(manifest_path)]
    )

    assert exit_code == 0
    assert (fixture.project_root / "CLAUDE.md").read_text(encoding="utf-8") == tracked_claude_md, (
        "sidecar-placed project's tracked CLAUDE.md was mutated by --apply -- "
        "should be untouched under the manifest's `untouched` intent"
    )
    shadow_path = fixture.project_root / "CLAUDE.local.md"
    assert shadow_path.is_file(), (
        "the absent block was not appended to the shadowed CLAUDE.local.md"
    )
    assert _AGENT_PIPELINE_CURRENT_BODY in shadow_path.read_text(encoding="utf-8")


def test_apply_refuses_when_the_state_link_is_dangling_instead_of_writing_the_tracked_file(
    tmp_path: Path,
) -> None:
    """A sidecar-placed project whose mount is missing must not fall back to the
    team's tracked `CLAUDE.md`: `--apply` exits 2 by name and writes nothing."""
    from test_state_repo import _build_sidecar_owned_fixture

    tracked_claude_md = "# Team Project\n\nHand-written, tracked prose.\n"
    fixture = _build_sidecar_owned_fixture(tmp_path, origin=None)
    (fixture.project_root / "CLAUDE.md").write_text(tracked_claude_md, encoding="utf-8")
    state_link = fixture.project_root / ".ai-state"
    target = str(state_link.readlink())
    state_link.unlink()
    state_link.symlink_to(target + "-gone", True)

    manifest_path = _write_manifest(tmp_path, _SINGLE_SLUG_BLOCKS)
    canonical_dir = _write_canonical_dir(tmp_path, {"agent-pipeline": _AGENT_PIPELINE_CURRENT_BODY})
    mod = _load_module()
    mod.CANONICAL_DIR = canonical_dir  # type: ignore[attr-defined]

    with pytest.raises(SystemExit) as raised:
        mod.main(
            ["--apply", "--repo-root", str(fixture.project_root), "--manifest", str(manifest_path)]
        )

    assert raised.value.code == 2
    assert (fixture.project_root / "CLAUDE.md").read_text(encoding="utf-8") == tracked_claude_md
    assert not (fixture.project_root / "CLAUDE.local.md").exists()
