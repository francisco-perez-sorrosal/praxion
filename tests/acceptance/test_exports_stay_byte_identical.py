"""The Codex and Cursor exports are byte-identical to the base's, the checkout's location aside.

Sessions in assistants without Praxion's Claude Code hooks keep receiving exactly what they
receive today. The digests were frozen from the base's exports (`gating_readings.freeze`).
"""

from __future__ import annotations

from tests.acceptance.drivers import gating_readings as readings
from tests.acceptance.drivers import process_text_oracles as oracles


def test_every_codex_and_cursor_export_file_is_byte_identical_to_todays(tmp_path):
    exported = readings.export_digests(tmp_path)
    today = oracles.fixture_json("base_exports.json")

    differing = sorted(k for k in set(today) | set(exported) if today.get(k) != exported.get(k))

    assert differing == [], f"{len(differing)} export files differ: {differing[:10]}"
