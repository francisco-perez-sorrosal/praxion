"""Structural tests for `/upgrade-project`'s label-taxonomy baseline refresh + re-point.

`/upgrade-project` is a slash command (Markdown body executed by a live
Claude Code session) — it cannot be invoked from pytest. These tests validate
the documented contract by parsing `commands/upgrade-project.md`
structurally, matching the precedent set by
`tests/commands/test_upgrade_project_command.py`.

The command currently documents re-pointing the `ci-autofix.yml` caller and
adding the `cross-model-review.yml` caller (surface 5) — it does not yet
mention `refresh_labels_baseline.py` or the `labels-reconcile.yml` caller.
All tests below are expected to FAIL until the implementer wires the labels
surface in.
"""

from __future__ import annotations

import re
from pathlib import Path

UPGRADE_FILE = Path(__file__).parents[2] / "commands" / "upgrade-project.md"

# The exact phrase anchoring surface 5's existing ci-autofix.yml re-point
# description (see commands/upgrade-project.md's numbered surface list).
CI_AUTOFIX_REPOINT_ANCHOR = "ci-autofix.yml` caller's pinned hub commit reference"


def _upgrade_body() -> str:
    """Return the full upgrade-project.md content (read lazily so collection succeeds)."""
    return UPGRADE_FILE.read_text(encoding="utf-8")


def _ci_autofix_repoint_description() -> str:
    """Return a window of text around surface 5's existing ci-autofix.yml
    re-point description, or '' if not found.

    Scoping to this window (rather than the whole file) keeps the
    "labels-reconcile mentioned alongside it" assertion anchored to the
    actual re-point prose, instead of matching an unrelated
    'labels-reconcile' mention elsewhere in the file.
    """
    body = _upgrade_body()
    idx = body.find(CI_AUTOFIX_REPOINT_ANCHOR)
    if idx == -1:
        return ""
    start = max(0, idx - 50)
    end = min(len(body), idx + 500)
    return body[start:end]


def test_documents_invoking_refresh_labels_baseline_script() -> None:
    body = _upgrade_body()
    assert re.search(r"refresh_labels_baseline\.py", body), (
        "commands/upgrade-project.md must document invoking "
        "'scripts/refresh_labels_baseline.py' (or reference the script by "
        "name) to refresh the project's labels.yml baseline block — not "
        "found. The implementer must add it."
    )


def test_refresh_description_preserves_additional_block() -> None:
    body = _upgrade_body()
    idx = body.find("refresh_labels_baseline.py")
    assert idx != -1, (
        "commands/upgrade-project.md must document the labels baseline "
        "refresh before its preservation guarantee can be checked"
    )
    window = body[max(0, idx - 200) : idx + 600]
    assert re.search(r"additional", window, re.IGNORECASE), (
        "The labels baseline refresh description must document that the "
        "project's `additional:` block is preserved untouched by the refresh"
    )


def test_hub_sha_repoint_description_also_mentions_labels_reconcile_caller() -> None:
    context = _ci_autofix_repoint_description()
    assert context, (
        "commands/upgrade-project.md's existing ci-autofix caller re-point "
        "description (surface 5) was not found — cannot verify the "
        "labels-reconcile caller is documented alongside it"
    )
    assert re.search(r"labels-reconcile\.yml", context), (
        "commands/upgrade-project.md must document that the "
        "'labels-reconcile.yml' caller is ALSO re-pointed by the hub-SHA "
        "resolution, alongside the existing ci-autofix.yml caller re-point "
        "description"
    )


def test_upgrade_project_pins_script_hub_sha_flag_reconciles_labels_caller() -> None:
    body = _upgrade_body()
    assert re.search(r"upgrade_project_pins\.sh[^\n]*--hub-sha", body), (
        "commands/upgrade-project.md must forward the resolved hub SHA to "
        "scripts/upgrade_project_pins.sh via '--hub-sha' (pre-existing "
        "contract; this test pins that the invocation line still exists as "
        "the anchor the labels-reconcile re-point rides on)"
    )
    assert re.search(r"labels-reconcile\.yml", body), (
        "commands/upgrade-project.md must mention 'labels-reconcile.yml' "
        "somewhere, documenting that scripts/upgrade_project_pins.sh "
        "--hub-sha also re-points this third caller"
    )
