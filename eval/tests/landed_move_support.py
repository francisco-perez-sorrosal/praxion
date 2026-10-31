"""The checkout as it stood before the adr-conventions move landed, for tests that build its arms.

The move instrument measures a move that has not landed: it refuses to build the lean arm over a
tree that already holds what the arm adds or has already swapped the rule. Tests that build arms
from a copy of the live tree put that copy back in the pre-move state first.
"""

from __future__ import annotations

from pathlib import Path

import yaml

ADR_KERNEL = "rules/swe/adr-conventions-resident.md"
ADR_KERNEL_ID = "swe/adr-conventions-resident"
ADR_RULE = "rules/swe/adr-conventions.md"
ADR_RULE_ID = "swe/adr-conventions"
MANIFEST = "rules/_manifest.yaml"
PRE_MOVE_ADR_RULE = Path(__file__).parent / "fixtures" / "pre_move_adr_conventions.md"


def before_the_adr_move(root: Path) -> None:
    """Put a copy of the tree back before the move: no resident file, the always-loaded rule."""
    (root / ADR_KERNEL).unlink(missing_ok=True)
    rule = PRE_MOVE_ADR_RULE.read_text(encoding="utf-8")
    (root / ADR_RULE).write_text(rule, encoding="utf-8")
    manifest = root / MANIFEST
    doc = yaml.safe_load(manifest.read_text(encoding="utf-8"))
    doc["rules"] = [row for row in doc["rules"] if row["id"] != ADR_KERNEL_ID]
    for row in doc["rules"]:
        if row["id"] == ADR_RULE_ID:
            row.pop("paths", None)
            row.update(load="always_on", chars=len(rule))
    manifest.write_text(yaml.safe_dump(doc, sort_keys=False), encoding="utf-8")
