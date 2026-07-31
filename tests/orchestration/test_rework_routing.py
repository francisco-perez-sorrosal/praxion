"""Tests for the architect-always-first routing invariant.

These tests validate that commands/resume-rework.md documents the routing
contract: ALL rework rows — regardless of class (architecture or implementation)
— dispatch to systems-architect first. The implementation-planner is only
invoked downstream after the architect has produced SYSTEMS_PLAN.md.

All tests are expected to FAIL until commands/resume-rework.md is created by
the implementer.
"""

from __future__ import annotations

import re
from pathlib import Path

COMMAND_FILE = Path(__file__).parents[2] / "commands" / "resume-rework.md"


def _body() -> str:
    """Return the full command file content (imported lazily so collection succeeds)."""
    return COMMAND_FILE.read_text(encoding="utf-8")


def test_architecture_class_routes_to_architect() -> None:
    body = _body()
    # The command must document that architecture-class rows dispatch to systems-architect.
    assert (
        "systems-architect" in body
    ), "commands/resume-rework.md must document dispatch to 'systems-architect'"
    assert re.search(
        r"(architecture.{0,80}systems.architect|systems.architect.{0,80}architecture)",
        body,
        re.IGNORECASE | re.DOTALL,
    ), (
        "Dispatch section must document that architecture-class rows route to "
        "systems-architect (the architect-always-first routing invariant)"
    )


def test_implementation_class_routes_through_architect_first() -> None:
    body = _body()
    # The command must document that even implementation-class rows go to architect first.
    # The planner is only downstream after SYSTEMS_PLAN.md exists.
    assert re.search(
        r"(implementation.{0,120}systems.architect|architect.{0,120}first)",
        body,
        re.IGNORECASE | re.DOTALL,
    ), (
        "Dispatch section must document that implementation-class rows ALSO route to "
        "systems-architect first — the planner is only invoked after the architect "
        "produces SYSTEMS_PLAN.md (architect-always-first invariant applies to all classes)"
    )


def test_no_direct_planner_dispatch() -> None:
    body = _body()
    # The command body must not contain a code path that dispatches
    # implementation-planner directly from /resume-rework.
    # The architect-always-first routing invariant is statically verifiable:
    # every dispatch arm names systems-architect, never implementation-planner alone.
    direct_planner_dispatch = re.search(
        r"dispatch.{0,60}implementation.planner|spawn.{0,60}implementation.planner",
        body,
        re.IGNORECASE | re.DOTALL,
    )
    assert not direct_planner_dispatch, (
        "commands/resume-rework.md must NOT dispatch implementation-planner directly. "
        "The architect-always-first invariant means every dispatch arm names "
        "systems-architect. The planner is invoked downstream, not by this command. "
        f"Found: {direct_planner_dispatch.group() if direct_planner_dispatch else ''}"
    )


def test_routing_decision_cites_architect_always_first_rationale() -> None:
    body = _body()
    # The command body or its dispatch section must contain rationale for routing
    # all classes through the architect first. The specific ADR dec-178
    # was the decision vehicle; the shipped command should carry inline rationale
    # or a reference to preserve the decision intent for readers.
    assert re.search(
        r"(architect.always.first|always.{0,40}architect|SYSTEMS_PLAN.{0,60}planner)",
        body,
        re.IGNORECASE | re.DOTALL,
    ), (
        "Dispatch section must carry the architect-always-first rationale inline "
        "(e.g., 'always routes through systems-architect first' or reference to "
        "the routing decision). This preserves the decision intent for command readers "
        "without requiring access to the ADR."
    )
