"""Behavioral tests for `_sidecar_render.py` -- render regressions.

Narrow by design: `_sidecar_render.py` has no prior test file, and this
fixer's scope is the two findings below, not a full-coverage suite for the
module. Import strategy matches the sibling `_sidecar_checks.py` suite: plain
sibling import via pytest's prepend import mode.
"""

from __future__ import annotations

from pathlib import Path

import _sidecar_render as render


def _healthy_multi_checkout_status() -> render.SidecarStatus:
    """A `SidecarStatus` at more than one checkout -- the exact shape that
    used to trigger the deleted "no branch isolation" tail."""
    return render.SidecarStatus(
        project_root=Path("/project"),
        origin="https://github.com/acme/billing",
        project_id="github.com--acme--billing",
        checkout=render.Checkout(root=Path("/project"), kind="main", index=1, total=3),
        sidecar=render.SidecarFacts(
            root=Path("/sidecar"),
            branch="main",
            dirty_files=0,
            unpushed_commits=0,
            last_commit_at=None,
        ),
        remote=None,
        autocommit="manual",
        paths=(),
        healthy=True,
        failed_checks=(),
        counts={"pass": 1, "warn": 0, "fail": 0},
    )


def test_healthy_multi_checkout_status_never_claims_no_branch_isolation() -> None:
    """The pre-ruling model line must never render -- state is NOT
    shared live across checkouts under sidecar placement (per-checkout
    mounts + branch isolation)."""
    text = render.status_text(_healthy_multi_checkout_status())

    assert "no branch isolation" not in text
    assert "shared live" not in text
    assert "Healthy." in text


def test_short_usage_names_merge_back() -> None:
    """`SHORT_USAGE` must not omit a real subcommand."""
    assert "merge-back" in render.SHORT_USAGE
