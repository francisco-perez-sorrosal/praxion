"""Behavioral tests for the label-taxonomy manifest and its drift gate + the
baseline-refresh helper (issue #52).

Covers three genuinely distinct, data-shaped concerns (workflow-YAML
structural concerns live in the sibling `test_labels_reconcile_workflow.py`):

1. **Manifest schema** — `.github/labels.yml` (does not exist yet) declares a
   two-block `baseline:`/`additional:` shape, each entry carrying exactly
   `name`, `color`, `description`; GitHub-default labels (`bug`, `duplicate`)
   are documented as intentionally absent (always provisioned by GitHub,
   never Praxion-managed).
2. **Drift gate** — every value in the two enum-driven label families
   (`_CATEGORY_CHOICES` in `scripts/praxion_feedback/cli.py`, and the
   `reviewer_family` enum documented inline in `.github/autofix-policy.yml`)
   must have a corresponding baseline label. The check is **subset, not
   exact-match**: the real manifest's baseline carries many more labels than
   just these two families (reporter, arming/triage, intake gate, ci-autofix
   entries), so asserting `required <= present` — never `required == present`
   — is what actually tolerates that over-declaration, and is what will
   continue to tolerate a project's own `additional:` growth on managed
   projects (this test only ever runs against Praxion's own manifest, but
   the assertion shape is the same one the drift gate must use everywhere).
3. **`scripts/refresh_labels_baseline.py`** (does not exist yet) as a pure
   function: given a shipped baseline template's text and a project
   manifest's text, the rewritten manifest's `baseline:` must match the
   shipped template's `baseline:` exactly (structural equality) and the
   project's `additional:` block — including its own comments — must be
   preserved byte-for-byte. A thin `main(argv)` CLI wrapper reads two file
   paths and writes the result back to the project-manifest path in place.

These interfaces (`refresh_baseline_block`, `main`) are not yet implemented;
importing `scripts.refresh_labels_baseline` is deferred into each test body
(not done at module import time) so that collection of this file succeeds
before that module exists — only the tests that exercise it fail, with a
clean `ModuleNotFoundError`, not a whole-file collection error. `.github/
labels.yml` is a data file (not a Python import), so its absence surfaces as
a `FileNotFoundError` raised from inside each test's own helper call.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]
MANIFEST_FILE = PROJECT_ROOT / ".github" / "labels.yml"
AUTOFIX_POLICY_FILE = PROJECT_ROOT / ".github" / "autofix-policy.yml"

GITHUB_DEFAULT_LABELS = ("bug", "duplicate")
REQUIRED_ENTRY_KEYS = {"name", "color", "description"}


# ---------------------------------------------------------------------------
# Manifest helpers
# ---------------------------------------------------------------------------


def _load_manifest() -> dict:
    """Parse `.github/labels.yml` as YAML (lazy — read inside each test)."""
    return yaml.safe_load(MANIFEST_FILE.read_text(encoding="utf-8"))


def _entry_names(entries: list[dict]) -> set[str]:
    return {entry["name"] for entry in entries}


def _reviewer_family_enum_values() -> list[str]:
    """Read the `reviewer_family: <value>  # gpt | gemini | composer — ...`
    inline comment from the live autofix policy and return the pipe-separated
    enum values it documents. Read from the literal enum rather than
    hardcoding the 3 current values, so this test breaks the moment a new
    `reviewer_family` value is added without a matching baseline label —
    catching *future* enum growth, not just today's fixed set."""
    raw = AUTOFIX_POLICY_FILE.read_text(encoding="utf-8")
    match = re.search(r"^\s*reviewer_family:\s*\S+\s*#\s*(.+)$", raw, re.MULTILINE)
    assert match, (
        "expected a `reviewer_family: <value>  # <enum> | <enum> | ...` line "
        "in .github/autofix-policy.yml documenting the valid values"
    )
    comment_head = match.group(1).split("—")[0]
    values = [token.strip() for token in comment_head.split("|") if token.strip()]
    assert values, "could not parse any enum values out of the reviewer_family comment"
    return values


# ---------------------------------------------------------------------------
# Manifest schema
# ---------------------------------------------------------------------------


def test_manifest_declares_baseline_and_additional_as_top_level_list_blocks() -> None:
    manifest = _load_manifest()

    assert isinstance(manifest, dict), ".github/labels.yml must parse to a YAML mapping"
    assert isinstance(
        manifest.get("baseline"), list
    ), "top-level `baseline:` key must be a list of label entries"
    assert isinstance(manifest.get("additional"), list), (
        "top-level `additional:` key must be a list of label entries "
        "(empty on a fresh install, growable per-project)"
    )


def test_every_baseline_entry_has_exactly_name_color_description_string_keys() -> None:
    manifest = _load_manifest()

    for entry in manifest["baseline"]:
        assert set(entry.keys()) == REQUIRED_ENTRY_KEYS, (
            f"baseline entry {entry!r} must declare exactly "
            f"{REQUIRED_ENTRY_KEYS} — no more, no fewer"
        )
        for key in REQUIRED_ENTRY_KEYS:
            assert isinstance(
                entry[key], str
            ), f"baseline entry {entry!r}'s {key!r} must be a string"


def test_every_additional_entry_has_exactly_name_color_description_string_keys() -> None:
    manifest = _load_manifest()

    for entry in manifest["additional"]:
        assert set(entry.keys()) == REQUIRED_ENTRY_KEYS, (
            f"additional entry {entry!r} must declare exactly "
            f"{REQUIRED_ENTRY_KEYS} — no more, no fewer"
        )
        for key in REQUIRED_ENTRY_KEYS:
            assert isinstance(
                entry[key], str
            ), f"additional entry {entry!r}'s {key!r} must be a string"


def test_github_default_labels_are_absent_from_baseline_and_additional() -> None:
    """`bug` and `duplicate` are always provisioned by GitHub itself — managing
    them here would risk overwriting a project's own colors for no benefit.
    Documentary exclusion only; never reconciled."""
    manifest = _load_manifest()
    all_names = _entry_names(manifest["baseline"]) | _entry_names(manifest["additional"])

    for default_label in GITHUB_DEFAULT_LABELS:
        assert default_label not in all_names, (
            f"GitHub-default label {default_label!r} must never appear in the "
            "manifest — it is always provisioned by GitHub and intentionally "
            "out of scope for this taxonomy"
        )


# ---------------------------------------------------------------------------
# Drift gate: enum-driven label families must be a subset of baseline
# ---------------------------------------------------------------------------


def test_every_category_choice_has_a_corresponding_baseline_label() -> None:
    """Every `_CATEGORY_CHOICES` value (the reporter's `--category` argparse
    enum) must have a `category:<slug>` baseline label — read from the live
    enum, not a hardcoded copy, so this test catches a *future* category
    added to the reporter without a matching manifest entry."""
    from scripts.praxion_feedback.cli import _CATEGORY_CHOICES  # noqa: PLC0415

    manifest = _load_manifest()
    baseline_names = _entry_names(manifest["baseline"])
    required = {f"category:{choice}" for choice in _CATEGORY_CHOICES}

    missing = required - baseline_names
    assert not missing, (
        f"every _CATEGORY_CHOICES value must have a corresponding "
        f"'category:<slug>' baseline label; missing: {sorted(missing)}"
    )


def test_every_reviewer_family_value_has_a_corresponding_baseline_label() -> None:
    """Every `reviewer_family` enum value documented in `.github/
    autofix-policy.yml` must have a `reviewed-by:<family>` baseline label —
    including `gemini` and `composer`, today's live gaps this feature closes."""
    manifest = _load_manifest()
    baseline_names = _entry_names(manifest["baseline"])
    required = {f"reviewed-by:{family}" for family in _reviewer_family_enum_values()}

    missing = required - baseline_names
    assert not missing, (
        f"every reviewer_family enum value must have a corresponding "
        f"'reviewed-by:<family>' baseline label; missing: {sorted(missing)}"
    )


# ---------------------------------------------------------------------------
# scripts/refresh_labels_baseline.py: pure-function fixtures
# ---------------------------------------------------------------------------

_SHIPPED_TEMPLATE_TEXT = (
    "# baseline: Praxion-owned. Refreshed by /upgrade-project. Do not hand-edit.\n"
    "baseline:\n"
    '  - { name: auto-filed, color: "5319e7", description: "Auto-filed" }\n'
    '  - { name: needs-adr, color: "fbca04", description: "Needs ADR" }\n'
    "# additional: project-owned. Never touched by Praxion.\n"
    "additional: []\n"
)

# A stale project manifest: missing the shipped template's second baseline
# entry (needs-adr), and carrying a hand-edited additional: block with its
# own project-specific label and a maintainer's own comment.
_STALE_PROJECT_MANIFEST_TEXT = (
    "# baseline: Praxion-owned. Refreshed by /upgrade-project. Do not hand-edit.\n"
    "baseline:\n"
    '  - { name: auto-filed, color: "5319e7", description: "Auto-filed" }\n'
    "# additional: project-owned. Never touched by Praxion.\n"
    "additional:\n"
    '  - { name: "triage:urgent", color: "b60205", description: "Project-specific urgent triage label" }\n'
    "  # a maintainer's own hand-written note about this label\n"
)

_PROJECT_ADDITIONAL_BLOCK_TEXT = (
    "additional:\n"
    '  - { name: "triage:urgent", color: "b60205", description: "Project-specific urgent triage label" }\n'
    "  # a maintainer's own hand-written note about this label\n"
)


def _refresh_baseline_block():
    """Import lazily so collection succeeds before the module exists."""
    from scripts.refresh_labels_baseline import refresh_baseline_block  # noqa: PLC0415

    return refresh_baseline_block


# ---------------------------------------------------------------------------
# scripts/refresh_labels_baseline.py: refresh_baseline_block (pure function)
# ---------------------------------------------------------------------------


def test_refresh_baseline_block_replaces_baseline_with_shipped_template_exactly() -> None:
    refresh_baseline_block = _refresh_baseline_block()

    result_text = refresh_baseline_block(_SHIPPED_TEMPLATE_TEXT, _STALE_PROJECT_MANIFEST_TEXT)
    result = yaml.safe_load(result_text)
    shipped = yaml.safe_load(_SHIPPED_TEMPLATE_TEXT)

    assert result["baseline"] == shipped["baseline"], (
        "the refreshed manifest's baseline: must match the shipped "
        "template's baseline: exactly, closing the missing needs-adr gap"
    )


def test_refresh_baseline_block_preserves_additional_block_byte_for_byte() -> None:
    refresh_baseline_block = _refresh_baseline_block()

    result_text = refresh_baseline_block(_SHIPPED_TEMPLATE_TEXT, _STALE_PROJECT_MANIFEST_TEXT)

    assert _PROJECT_ADDITIONAL_BLOCK_TEXT in result_text, (
        "the project's additional: block — including its own hand-written "
        "comment — must survive a baseline refresh byte-for-byte, never "
        "reformatted or dropped. Got:\n" + result_text
    )


def test_refresh_baseline_block_is_idempotent_when_run_twice() -> None:
    refresh_baseline_block = _refresh_baseline_block()

    once = refresh_baseline_block(_SHIPPED_TEMPLATE_TEXT, _STALE_PROJECT_MANIFEST_TEXT)
    twice = refresh_baseline_block(_SHIPPED_TEMPLATE_TEXT, once)

    assert twice == once, (
        "refreshing an already-current manifest a second time must be a "
        "no-op — the output must be identical to the first refresh's output"
    )


def test_refresh_baseline_block_never_touches_the_additional_header_comment() -> None:
    """The `# additional: project-owned...` header comment sits immediately
    above the additional: key — a splice that touches lines outside the
    baseline: key would risk swallowing or duplicating this comment."""
    refresh_baseline_block = _refresh_baseline_block()

    result_text = refresh_baseline_block(_SHIPPED_TEMPLATE_TEXT, _STALE_PROJECT_MANIFEST_TEXT)

    assert result_text.count("# additional: project-owned. Never touched by Praxion.") == 1, (
        "the additional: header comment must appear exactly once, untouched, "
        "in the refreshed manifest. Got:\n" + result_text
    )


# ---------------------------------------------------------------------------
# scripts/refresh_labels_baseline.py: main() CLI wrapper
# ---------------------------------------------------------------------------


def test_main_writes_the_refreshed_manifest_back_to_the_project_manifest_path(
    tmp_path: Path,
) -> None:
    from scripts.refresh_labels_baseline import main  # noqa: PLC0415

    shipped_path = tmp_path / "labels.yml.tmpl"
    shipped_path.write_text(_SHIPPED_TEMPLATE_TEXT, encoding="utf-8")
    project_path = tmp_path / "labels.yml"
    project_path.write_text(_STALE_PROJECT_MANIFEST_TEXT, encoding="utf-8")

    exit_code = main([str(shipped_path), str(project_path)])

    after = project_path.read_text(encoding="utf-8")
    after_parsed = yaml.safe_load(after)
    shipped = yaml.safe_load(_SHIPPED_TEMPLATE_TEXT)
    assert exit_code == 0, "main() must exit 0 on a successful refresh"
    assert (
        after_parsed["baseline"] == shipped["baseline"]
    ), "main() must write the refreshed baseline: back to the project manifest path in place"
    assert _PROJECT_ADDITIONAL_BLOCK_TEXT in after, (
        "main() must preserve the project's additional: block byte-for-byte "
        "when writing the refreshed manifest back to disk"
    )
