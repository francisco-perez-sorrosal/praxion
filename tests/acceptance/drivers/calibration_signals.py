"""Driver for the tier signals the verifier's Calibration Verdict sub-step reaches.

The protocol's tier table is the `Process Calibration` section of the coordination protocol: a
row per tier, `| **<Tier>** | <Signals> | <Process> |`. The sub-step is the numbered item of
`agents/verifier.md` that opens `**Calibration Verdict**`, with its continuation lines. A file
the sub-step names is any path it writes in backticks or as a Markdown link target; a plugin
path resolves under the plugin root (leading `../` segments and `${CLAUDE_PLUGIN_ROOT}/`
dropped), whether or not the project holds the file.

A *carrier* is the sub-step itself or one file it names; it carries a tier's signals when one of
its lines holds both the tier's name and that tier's Signals cell, word for word.
"""

from __future__ import annotations

import re
from pathlib import Path

TIERS = ("Direct", "Lightweight", "Standard", "Full", "Spike")
PROTOCOL = "rules/swe/swe-agent-coordination-protocol.md"
VERIFIER = "agents/verifier.md"
_ROW = re.compile(r"^\|\s*\*\*(\w+)\*\*\s*\|\s*(.*?)\s*\|")
_ITEM = re.compile(r"^\s*\d+\.\s")
_PATHS = re.compile(r"`([^`\s]+\.[A-Za-z0-9]+)`|\]\(([^)#\s]+)")


def tier_signals(root: Path) -> dict[str, str]:
    text = (root / PROTOCOL).read_text(encoding="utf-8")
    section = text.split("### Process Calibration", 1)[1].split("\n### ", 1)[0]
    cells = {m.group(1): m.group(2) for ln in section.splitlines() if (m := _ROW.match(ln))}
    assert set(TIERS) <= set(cells), f"the protocol's tier table lacks {set(TIERS) - set(cells)}"
    return {tier: cells[tier] for tier in TIERS}


def calibration_substep(root: Path) -> str:
    lines = (root / VERIFIER).read_text(encoding="utf-8").splitlines()
    start = next(
        (i for i, ln in enumerate(lines) if _ITEM.match(ln) and "**Calibration Verdict**" in ln),
        None,
    )
    assert start is not None, f"{VERIFIER} has no numbered **Calibration Verdict** sub-step"
    end = start + 1
    while end < len(lines) and not _ITEM.match(lines[end]) and not lines[end].startswith("#"):
        end += 1
    return "\n".join(lines[start:end])


def _resolve(root: Path, written: str) -> str | None:
    rel = written.replace("${CLAUDE_PLUGIN_ROOT}/", "")
    while rel.startswith("../"):
        rel = rel[3:]
    rel = rel.removeprefix("./")
    return rel if (root / rel).is_file() else None


def carriers(root: Path) -> dict[str, str]:
    """The sub-step (as `agents/verifier.md`) and every plugin file it names, by path."""
    substep = calibration_substep(root)
    found = {VERIFIER: substep}
    for match in _PATHS.finditer(substep):
        rel = _resolve(root, match.group(1) or match.group(2))
        if rel is not None and rel != VERIFIER:
            found[rel] = (root / rel).read_text(encoding="utf-8")
    return found


def tiers_carried(text: str, signals: dict[str, str]) -> list[str]:
    lines = text.splitlines()
    return [t for t in TIERS if any(t in ln and signals[t] in ln for ln in lines)]


def signal_carrier(root: Path) -> str | None:
    """The one carrier that holds all five tiers' signals word for word; None if none does."""
    signals = tier_signals(root)
    whole = [
        rel for rel, text in carriers(root).items() if tiers_carried(text, signals) == list(TIERS)
    ]
    return whole[0] if whole else None


def drift_copy(root: Path, tier: str) -> None:
    """Change the carrier's copy of one tier's signals, leaving the protocol as it is."""
    carrier = signal_carrier(root)
    assert carrier is not None, (
        "the Calibration Verdict sub-step reaches no carrier of all five tiers"
    )
    path = root / carrier
    cell = tier_signals(root)[tier]
    text = path.read_text(encoding="utf-8")
    assert cell in text
    path.write_text(text.replace(cell, f"{cell}, or anything else", 1), encoding="utf-8")
