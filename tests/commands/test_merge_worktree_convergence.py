"""Structural tests for `/merge-worktree`'s explicit-merge-back step.

`/merge-worktree` is a slash command (Markdown body executed by a live
Claude Code session) — it cannot be invoked from pytest. These tests validate
the documented contract by parsing `commands/merge-worktree.md` structurally,
matching the precedent set by `tests/commands/test_upgrade_project_command.py`.

Under `ARCH_WT_RULING.md`'s state-convergence revision, this command's
explicit `merge-back --from` call is the *preferred* — not required — path
for promoting a sidecar-placed worktree's `.ai-state/` writes: same-run
promotion, earliest visibility, conflicts surfaced while an operator is
present to resolve them. Correctness no longer depends on this step; the
project's own post-merge finalize chain and the SessionStart self-heal both
converge automatically if it is skipped, times out, or a different merge
tool is used.
"""

from __future__ import annotations

import re
from pathlib import Path

MERGE_WORKTREE_FILE = Path(__file__).parents[2] / "commands" / "merge-worktree.md"


def _body() -> str:
    """Return the full merge-worktree.md content (read lazily so collection succeeds)."""
    return MERGE_WORKTREE_FILE.read_text(encoding="utf-8")


def _frontmatter_block() -> str:
    """Return the YAML frontmatter body (between the leading '---' fences), or '' if absent."""
    match = re.match(r"^---\n(.*?)\n---\n", _body(), re.DOTALL)
    return match.group(1) if match else ""


def _numbered_steps() -> list[tuple[str, str]]:
    """Split the '## Steps' section into (number, step-text) pairs, in document order.

    Numbers are the literal leading token of each top-level list item (e.g.
    '4.5', '5') — used to assert relative ordering without depending on a
    fixed line offset that a future edit could shift.
    """
    body = _body()
    steps_section = body.split("## Steps", 1)[-1]
    return re.findall(
        r"^(\d+(?:\.\d+)?)\.\s+(.+?)(?=\n\d+(?:\.\d+)?\.\s|\Z)",
        steps_section,
        re.DOTALL | re.MULTILINE,
    )


def _convergence_step_text() -> str:
    """Return the text of the step documenting the explicit merge-back call, or '' if absent."""
    for _number, text in _numbered_steps():
        if "merge-back" in text and "--from" in text:
            return text
    return ""


def test_convergence_step_exists_and_names_the_explicit_merge_back_form() -> None:
    text = _convergence_step_text()
    assert text, (
        "commands/merge-worktree.md must document a step that calls "
        "'praxion-sidecar merge-back --from wt/<name>' before the project "
        "merge — no such step found."
    )
    assert re.search(r"praxion-sidecar merge-back --from wt/", text), (
        "The convergence step must name the exact explicit-form invocation, "
        "'praxion-sidecar merge-back --from wt/<name>'."
    )


def test_convergence_step_precedes_the_project_branch_merge_step() -> None:
    steps = _numbered_steps()
    numbers = [number for number, _text in steps]
    assert numbers, "commands/merge-worktree.md '## Steps' section must be non-empty."

    convergence_index = next(
        (i for i, (_n, text) in enumerate(steps) if "merge-back" in text and "--from" in text),
        None,
    )
    project_merge_index = next(
        (i for i, (_n, text) in enumerate(steps) if "git merge --ff-only" in text),
        None,
    )
    assert convergence_index is not None, "Convergence step not found among numbered steps."
    assert project_merge_index is not None, (
        "Project-branch merge step ('git merge --ff-only') not found."
    )
    assert convergence_index < project_merge_index, (
        "The explicit merge-back step must be sequenced before the "
        "project-branch merge step, matching the 'preferred path' contract "
        "(same-run promotion, conflicts surfaced while the operator is "
        "present)."
    )


def test_convergence_step_resolves_placement_before_deciding_to_run() -> None:
    text = _convergence_step_text()
    assert text, "Convergence step text must be present (see prior test)."
    assert re.search(r"_state_repo\.py\s+--print", text), (
        "The convergence step must resolve the worktree's '.ai-state/' "
        "placement via 'scripts/_state_repo.py --print' before deciding "
        "whether to call merge-back."
    )
    assert "placement=sidecar" in text, (
        "The convergence step must gate the merge-back call on "
        "'placement=sidecar' — a project without a sidecar mount has "
        "nothing to converge."
    )


def test_convergence_step_states_it_is_a_convenience_not_a_correctness_requirement() -> None:
    text = _convergence_step_text()
    assert text, "Convergence step text must be present (see prior test)."
    assert re.search(r"convenience", text, re.IGNORECASE), (
        "The convergence step must plainly state it is a convenience, not a "
        "correctness requirement — the ordering hazard it used to enforce "
        "no longer exists."
    )
    assert re.search(r"not a\s+(\*\*)?correctness requirement", text, re.IGNORECASE), (
        "The convergence step must explicitly rule out being a correctness "
        "requirement, so an operator does not treat a skipped/timed-out "
        "step as unsafe."
    )


def test_convergence_step_points_at_doctor_backstop_rows() -> None:
    text = _convergence_step_text()
    assert text, "Convergence step text must be present (see prior test)."
    assert "state-unmerged" in text, (
        "The convergence step must name 'state-unmerged' as a doctor row "
        "that reports anything left unconverged if this step is skipped."
    )
    assert "state-eligible" in text, (
        "The convergence step must name 'state-eligible' as a doctor row "
        "that reports anything left unconverged if this step is skipped."
    )


def test_convergence_step_proceeds_to_project_merge_regardless_of_outcome() -> None:
    text = _convergence_step_text()
    assert text, "Convergence step text must be present (see prior test)."
    assert re.search(r"proceed to (S|s)tep 5|regardless of", text), (
        "The convergence step must state that the command proceeds to the "
        "project-branch merge regardless of whether merge-back converged, "
        "found nothing to converge, or left conflict markers — the "
        "correctness backstop is the project's own post-merge convergence "
        "channel, not this command."
    )


def test_allowed_tools_grants_praxion_sidecar_for_the_merge_back_call() -> None:
    frontmatter = _frontmatter_block()
    assert frontmatter, "commands/merge-worktree.md must have a YAML frontmatter block"
    assert "Bash(praxion-sidecar:*)" in frontmatter, (
        "commands/merge-worktree.md's 'allowed-tools' frontmatter must grant "
        "'Bash(praxion-sidecar:*)' so the command can run the merge-back call."
    )
