"""Structural tests for `/upgrade-project`'s hub-SHA resolution + forwarding.

`/upgrade-project` is a slash command (Markdown body executed by a live
Claude Code session) — it cannot be invoked from pytest. These tests validate
the documented contract by parsing `commands/upgrade-project.md` structurally,
matching the precedent set by `tests/commands/test_onboard_ci_autofix_install.py`.

The command currently wraps `scripts/upgrade_project_pins.sh` for the four
pre-existing version-pinned surfaces only — it does not yet resolve a hub SHA,
forward `--hub-sha`, degrade gracefully when `gh` is unavailable, or surface
the `CURSOR_API_KEY` setup print. All tests below are expected to FAIL until
the implementer wires this in, per the command-layer SHA-resolution design
(see the ADR `upgrade-caller-sha-rewrite` and `SYSTEMS_PLAN.md` REQ-11/REQ-14).
"""

from __future__ import annotations

import re
from pathlib import Path

UPGRADE_FILE = Path(__file__).parents[2] / "commands" / "upgrade-project.md"


def _upgrade_body() -> str:
    """Return the full upgrade-project.md content (read lazily so collection succeeds)."""
    return UPGRADE_FILE.read_text(encoding="utf-8")


def _frontmatter_block() -> str:
    """Return the YAML frontmatter body (between the leading '---' fences), or '' if absent."""
    match = re.match(r"^---\n(.*?)\n---\n", _upgrade_body(), re.DOTALL)
    return match.group(1) if match else ""


def _hub_sha_context() -> str:
    """Return a window of text around the first 'hub SHA'/'HUB_SHA' mention, or '' if absent.

    Scoping to this window (rather than the whole file) keeps the resolution-
    mechanism, 40-hex-validation, and never-a-placeholder assertions anchored
    to the actual SHA-resolution prose once it exists, instead of matching
    unrelated words ("current", "actual") that already appear elsewhere in
    this short command file.
    """
    body = _upgrade_body()
    match = re.search(r"hub[\s_-]?sha", body, re.IGNORECASE)
    if not match:
        return ""
    start = max(0, match.start() - 200)
    end = min(len(body), match.end() + 500)
    return body[start:end]


def _gh_absence_context() -> str:
    """Return a window of text around a 'gh unavailable/absent/missing' mention, or '' if absent."""
    body = _upgrade_body()
    match = re.search(
        r"\bgh\b.{0,80}(unavailable|absent|missing|not (installed|authenticated|found))",
        body,
        re.IGNORECASE | re.DOTALL,
    )
    if not match:
        return ""
    start = max(0, match.start() - 100)
    end = min(len(body), match.end() + 500)
    return body[start:end]


def test_resolves_current_hub_sha_via_gh_api_commits_endpoint() -> None:
    context = _hub_sha_context()
    assert context, (
        "commands/upgrade-project.md must document resolving a hub SHA — no "
        "'hub SHA'/'HUB_SHA' mention found yet. The implementer must add it."
    )
    assert re.search(r"gh api\s+repos/[\w./-]+/commits/main", context), (
        "The hub-SHA resolution must use `gh api repos/<owner>/<repo>/commits/main`, "
        "mirroring onboard sub-step 8e.8's resolution mechanism"
    )
    assert re.search(r"--jq\s+\.sha", context), (
        "The hub-SHA resolution must extract the commit SHA via `--jq .sha`, "
        "matching onboard's resolution command shape"
    )


def test_validates_resolved_sha_is_forty_hex_before_forwarding() -> None:
    context = _hub_sha_context()
    assert context, "commands/upgrade-project.md must document resolving a hub SHA"
    assert re.search(r"40.?hex", context, re.IGNORECASE), (
        "commands/upgrade-project.md must document validating the resolved "
        "hub SHA is a 40-hex commit before forwarding it to the reconciler"
    )


def test_documents_hub_sha_is_never_a_placeholder_or_mutable_ref() -> None:
    context = _hub_sha_context()
    assert context, "commands/upgrade-project.md must document resolving a hub SHA"
    assert re.search(r"real|actual|resolved|current", context, re.IGNORECASE), (
        "commands/upgrade-project.md must document resolving the hub SHA to a "
        "real, current commit SHA — not found near the hub-SHA mention"
    )
    assert re.search(r"never.{0,60}(placeholder|mutable|tag|branch)", context, re.IGNORECASE), (
        "commands/upgrade-project.md must explicitly rule out a placeholder or "
        "mutable tag/branch for the hub SHA, mirroring onboard sub-step 8e.8's "
        "resolution discipline (the SHA-rewrite script requires a real 40-hex "
        "value — a moving ref would break its determinism contract)"
    )


def test_forwards_resolved_sha_to_reconciler_via_hub_sha_flag() -> None:
    body = _upgrade_body()
    assert re.search(r"upgrade_project_pins\.sh[^\n]*--hub-sha", body), (
        "commands/upgrade-project.md must forward the resolved SHA to "
        "scripts/upgrade_project_pins.sh via a '--hub-sha <SHA>' argument on "
        "the script invocation line"
    )


def test_degrades_gracefully_when_gh_is_unavailable_but_core_surfaces_still_reconcile() -> None:
    context = _gh_absence_context()
    assert context, (
        "commands/upgrade-project.md must document what happens when `gh` is "
        "unavailable/unauthenticated — no such mention found yet"
    )
    assert re.search(r"skip", context, re.IGNORECASE), (
        "The gh-unavailable path must document SKIPPING the caller surfaces "
        "(ci-autofix SHA re-point + cross-model-review add), never a hard failure"
    )
    assert re.search(r"advis", context, re.IGNORECASE), (
        "The gh-unavailable path must surface an advisory to the operator, "
        "not fail silently and not abort the whole upgrade"
    )
    assert re.search(
        r"(core|four|pre-existing|existing) surfaces?.{0,80}(still|continue|reconcile)"
        r"|reconcile.{0,80}(core|four|pre-existing|existing) surfaces?",
        context,
        re.IGNORECASE | re.DOTALL,
    ), (
        "The gh-unavailable path must state that the four pre-existing "
        "surfaces still reconcile — a missing `gh` must never block the "
        "whole upgrade"
    )


def test_prints_cursor_api_key_setup_without_auto_running_it_when_cross_model_caller_is_added() -> (
    None
):
    body = _upgrade_body()
    assert "gh secret set CURSOR_API_KEY" in body, (
        "commands/upgrade-project.md must document the exact 'gh secret set "
        "CURSOR_API_KEY' command, surfaced when the cross-model-review.yml "
        "caller is added"
    )
    assert re.search(r"\bprint\b", body, re.IGNORECASE), (
        "The CURSOR_API_KEY setup must be PRINTED, matching the print-not-inject "
        "convention already used by onboard sub-step 8e.8 for the same secret"
    )
    assert not re.search(r"\brun\s+gh secret set", body, re.IGNORECASE), (
        "commands/upgrade-project.md must never auto-run 'gh secret set' on "
        "the operator's behalf — only print it as a one-time manual step"
    )


def test_allowed_tools_grants_gh_for_sha_resolution() -> None:
    frontmatter = _frontmatter_block()
    assert frontmatter, "commands/upgrade-project.md must have a YAML frontmatter block"
    assert "Bash(gh:*)" in frontmatter, (
        "commands/upgrade-project.md's 'allowed-tools' frontmatter must grant "
        "'Bash(gh:*)' so the command can resolve the hub SHA via `gh api`"
    )
