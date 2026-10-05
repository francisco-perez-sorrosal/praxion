"""The turn-budget driver runs the hook script the plugin ships, found beside its manifest."""

from __future__ import annotations

from tests.acceptance.drivers.turn_budget_reminder import HOOKS_MANIFEST, reminder_script


def test_the_reminder_resolves_to_the_plugins_turn_budget_hook_script():
    script = reminder_script()

    assert script.name == "remind_turn_budget.py"
    assert script.parent == HOOKS_MANIFEST.parent
    assert script.parent.name == "hooks"
