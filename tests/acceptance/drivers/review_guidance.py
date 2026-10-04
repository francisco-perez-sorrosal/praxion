"""Driver that reads the review checks Praxion's diagramming guidance names.

Unbound until a binding step: where the guidance lives and how it lays out each
check (its name, the evidence that decides it, its pass condition) is a design
decision. A binding step reads the designed place and returns the checks; the
scenarios then judge them against the specification.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
CONVENTIONS_ENTRY_POINT = REPO_ROOT / "rules" / "writing" / "diagram-conventions.md"


@dataclass(frozen=True)
class ReviewCheck:
    name: str
    evidence: str
    pass_condition: str
    source: Path  # the file the check is stated in

    @property
    def text(self) -> str:
        return f"{self.name} {self.evidence} {self.pass_condition}"


def review_checks() -> list[ReviewCheck]:
    raise NotImplementedError(
        "Unbound driver: the diagramming guidance does not yet name a list of review "
        "checks, each with the evidence that decides it and its pass condition, in a "
        "place a reader reaches within one link of the diagram conventions entry point."
    )
