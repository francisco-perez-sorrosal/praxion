"""Healing-sidecar reporter core for the managed-project -> Praxion feedback channel.

Stdlib-only building blocks shared by the `report_praxion_issue.py` CLI and the
`/report-praxion-issue` command: the fingerprint/dedup contract, the mechanical
capture-time sanitizer, the shipped-artifact scope filter, the PENDING.md
candidate store, and the fixed §5.2 markdown-body renderer.
"""

from __future__ import annotations

__all__: list[str] = []
