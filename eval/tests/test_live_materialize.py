"""Behavioral tests for the live scenario runner's materialization layer.

Covers `praxion_evals.live.materialize`: the pure `remove_section` (canary
degradation), nonce planting (the preflight's isolation proof), and a local
integration test that builds a real user-scope install from this repo's own
HEAD — no `claude` invocation anywhere in this file: live sessions are
operator-only, never exercised from pytest.

All production imports are deferred inside each test body so pytest
collection succeeds before the `praxion_evals.live` package exists
(RED-state handshake).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]

_NONCE_SHAPE = re.compile(r"^[0-9a-f]{8}$")  # secrets.token_hex(4)


# ---------------------------------------------------------------------------
# remove_section — pure text transform, canary degradation
# ---------------------------------------------------------------------------

_DOC_WITH_A_NON_BOUNDARY_H2_IN_BETWEEN = """\
### Process Calibration

The tier table lives here.

## A Different Major Section

Prose that belongs to the removed span because only `### ` headings bound it.

### Pipeline Isolation

This heading and everything after it survives.
"""

_DOC_WHERE_THE_TARGET_HEADING_IS_LAST = """\
## Overview

### Process Calibration

The tier table lives here, and there is nothing after it.
"""


def test_remove_section_strips_from_the_heading_through_the_next_h3_heading():
    from praxion_evals.live.materialize import remove_section

    new_text, removed_bytes = remove_section(
        _DOC_WITH_A_NON_BOUNDARY_H2_IN_BETWEEN, "### Process Calibration"
    )

    assert "### Process Calibration" not in new_text
    assert "The tier table lives here." not in new_text
    assert new_text.startswith("### Pipeline Isolation")
    assert removed_bytes > 0


def test_remove_section_does_not_stop_early_at_an_intervening_h2_heading():
    """A `## ` heading between the target and the next `### ` heading is
    NOT a boundary — the whole span, including that H2 and its prose, is
    removed. Guards against a naive "stop at any heading" implementation."""
    from praxion_evals.live.materialize import remove_section

    new_text, _ = remove_section(_DOC_WITH_A_NON_BOUNDARY_H2_IN_BETWEEN, "### Process Calibration")

    assert "## A Different Major Section" not in new_text
    assert "belongs to the removed span" not in new_text


def test_remove_section_runs_to_true_eof_when_the_heading_is_the_last_one():
    """When no `### ` heading follows, removal goes all the way to EOF —
    distinct from a buggy implementation that always stops at some fixed
    point regardless of what actually follows the heading."""
    from praxion_evals.live.materialize import remove_section

    new_text, removed_bytes = remove_section(
        _DOC_WHERE_THE_TARGET_HEADING_IS_LAST, "### Process Calibration"
    )

    assert new_text == "## Overview\n\n"
    assert removed_bytes > 0


def test_remove_section_raises_when_the_heading_is_absent():
    from praxion_evals.live.materialize import remove_section

    with pytest.raises(ValueError, match="Process Calibration"):
        remove_section("### Something Else\n\nUnrelated content.\n", "### Process Calibration")


# ---------------------------------------------------------------------------
# Nonce planting — four fresh, unguessable markers per variant build
# ---------------------------------------------------------------------------


def _build_stub_copy(root: Path) -> None:
    """Minimal stand-in for a materialized copy: just the four files
    `plant_nonces` writes into, at the paths probe 1 recorded."""
    (root / "claude" / "config").mkdir(parents=True)
    (root / "claude" / "config" / "CLAUDE.md.tmpl").write_text("# {{PROJECT_NAME}}\n")
    (root / "rules" / "swe").mkdir(parents=True)
    (root / "rules" / "swe" / "agent-behavioral-contract.md").write_text("## Contract\n")
    (root / "rules" / "swe" / "agent-model-routing.md").write_text("## Agent Model Routing\n")
    (root / "agents").mkdir(parents=True)
    (root / "agents" / "researcher.md").write_text("---\nname: researcher\n---\nBody.\n")


def test_plant_nonces_writes_a_fresh_marker_into_each_of_the_four_locations(tmp_path):
    from praxion_evals.live.materialize import plant_nonces

    _build_stub_copy(tmp_path)

    plant = plant_nonces(tmp_path, rule_relpath="rules/swe/agent-behavioral-contract.md")

    global_md = (tmp_path / "claude" / "config" / "CLAUDE.md.tmpl").read_text()
    rule_md = (tmp_path / "rules" / "swe" / "agent-behavioral-contract.md").read_text()
    agent_md = (tmp_path / "agents" / "researcher.md").read_text()
    hook_rule_md = (tmp_path / "rules" / "swe" / "agent-model-routing.md").read_text()

    assert plant.global_claude_md in global_md
    assert plant.coordination_rule in rule_md
    assert plant.plugin_agent in agent_md
    assert plant.hook_delivered_rule in hook_rule_md


def test_plant_nonces_values_are_token_hex_4_shaped():
    from praxion_evals.live.materialize import plant_nonces

    tmp_root = Path(__file__).resolve().parent / "_plant_nonces_scratch"
    tmp_root.mkdir(exist_ok=True)
    try:
        _build_stub_copy(tmp_root)
        plant = plant_nonces(tmp_root, rule_relpath="rules/swe/agent-behavioral-contract.md")

        for value in (
            plant.global_claude_md,
            plant.coordination_rule,
            plant.plugin_agent,
            plant.hook_delivered_rule,
        ):
            assert _NONCE_SHAPE.match(value), f"{value!r} is not an 8-hex-char nonce"
    finally:
        import shutil

        shutil.rmtree(tmp_root, ignore_errors=True)


def test_plant_nonces_is_fresh_per_call(tmp_path):
    """Two variants of the same run (e.g. HEAD and canary) must never share
    a nonce — a shared value would let one variant's session pass the
    other's isolation proof by coincidence."""
    from praxion_evals.live.materialize import plant_nonces

    copy_a = tmp_path / "a"
    copy_b = tmp_path / "b"
    copy_a.mkdir()
    copy_b.mkdir()
    _build_stub_copy(copy_a)
    _build_stub_copy(copy_b)

    plant_a = plant_nonces(copy_a, rule_relpath="rules/swe/agent-behavioral-contract.md")
    plant_b = plant_nonces(copy_b, rule_relpath="rules/swe/agent-behavioral-contract.md")

    assert plant_a.global_claude_md != plant_b.global_claude_md
    assert plant_a.coordination_rule != plant_b.coordination_rule
    assert plant_a.plugin_agent != plant_b.plugin_agent
    assert plant_a.hook_delivered_rule != plant_b.hook_delivered_rule


# ---------------------------------------------------------------------------
# Local-HEAD materialization integration test — no `claude` invocation
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_materialize_head_installs_a_rendered_claude_md_and_excludes_hook_delivered_rules(
    tmp_path,
):
    """Builds a real copy of this repo's own HEAD, installs user scope into
    a sandbox with the copy's own `render_claude_md.py` + `link_rules`, and
    checks the two behaviors that matter for sandbox fidelity: the global
    CLAUDE.md actually renders, and a hook-deliver rule is present in the
    copy (so the hook can deliver it) but is never symlinked into
    `.claude/rules` — that would double-deliver it and defeat the
    per-project blacklist."""
    from praxion_evals.live.materialize import install_user_scope, materialize_head

    dest = tmp_path / "copy"
    materialization = materialize_head(_REPO_ROOT, dest)

    sandbox = tmp_path / "sandbox"
    install_user_scope(materialization.root, sandbox)

    rendered_claude_md = sandbox / "home" / ".claude" / "CLAUDE.md"
    assert rendered_claude_md.exists()
    assert rendered_claude_md.read_text(encoding="utf-8").strip() != ""

    hook_delivered_rule_in_copy = materialization.root / "rules" / "swe" / "agent-model-routing.md"
    assert hook_delivered_rule_in_copy.exists()

    linked_hook_rule = sandbox / "home" / ".claude" / "rules" / "swe" / "agent-model-routing.md"
    assert not linked_hook_rule.exists()

    linked_regular_rule = sandbox / "home" / ".claude" / "rules" / "swe" / "coding-style.md"
    assert linked_regular_rule.is_symlink()


@pytest.mark.integration
def test_materialize_head_tree_digest_is_stable_across_two_builds(tmp_path):
    """Two independent builds of the same HEAD produce the same digest —
    the digest is a content hash, not something order- or timestamp-
    sensitive that would make every canary comparison spuriously differ."""
    from praxion_evals.live.materialize import materialize_head

    first = materialize_head(_REPO_ROOT, tmp_path / "copy-1")
    second = materialize_head(_REPO_ROOT, tmp_path / "copy-2")

    assert first.tree_digest == second.tree_digest
    assert first.tree_digest != ""
