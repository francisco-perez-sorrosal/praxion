"""The Codex and Cursor exports are byte-identical to the base's, the checkout's location aside,
save the two hand-path skills', which match what their exporters regenerate today.

Sessions in assistants without Praxion's Claude Code hooks keep receiving exactly what they
receive today. The digests were frozen from the base's exports (`gating_readings.freeze`).
"""

from __future__ import annotations

from tests.acceptance.drivers import gating_readings as readings
from tests.acceptance.drivers import process_text_oracles as oracles

# The hand-path skills' exports may change, but only to what their exporters regenerate from
# the head sources; every other export keeps the base's digest.
REGENERATED = (
    "codex-skills/praxion-complete-install/SKILL.md",
    "codex-skills/praxion-complete-uninstall/SKILL.md",
)


def test_every_codex_and_cursor_export_file_is_byte_identical_to_todays(tmp_path):
    exported = readings.export_digests(tmp_path)
    today = oracles.fixture_json("base_exports.json")
    missing = [k for k in REGENERATED if k not in exported]
    assert missing == [], f"the exporters no longer write {missing}"
    today.update({k: exported[k] for k in REGENERATED})

    differing = sorted(k for k in set(today) | set(exported) if today.get(k) != exported.get(k))

    assert differing == [], f"{len(differing)} export files differ: {differing[:10]}"
