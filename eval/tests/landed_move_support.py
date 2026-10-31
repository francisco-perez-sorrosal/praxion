"""The checkout as it stood before the adr-conventions move landed, for tests that build its arms.

The move instrument measures a move that has not landed: it refuses to build the lean arm over a
tree that already holds what the arm adds. Tests that build arms from a copy of the live tree put
that copy back in the pre-move state first.
"""

from __future__ import annotations

from pathlib import Path

import yaml

ADR_KERNEL = "rules/swe/adr-conventions-resident.md"
ADR_KERNEL_ID = "swe/adr-conventions-resident"
MANIFEST = "rules/_manifest.yaml"


def before_the_adr_move(root: Path) -> None:
    """Drop the shipped resident file and its manifest row from a copy of the tree."""
    (root / ADR_KERNEL).unlink(missing_ok=True)
    manifest = root / MANIFEST
    doc = yaml.safe_load(manifest.read_text(encoding="utf-8"))
    doc["rules"] = [row for row in doc["rules"] if row["id"] != ADR_KERNEL_ID]
    manifest.write_text(yaml.safe_dump(doc, sort_keys=False), encoding="utf-8")
