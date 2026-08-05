"""Every finalized ADR's frontmatter must parse with a real YAML parser.

Cites: rules/swe/gate-liveness.md — a CODE gate ships a canary proving it bites.

This lives here, as a test, rather than inside
``scripts/check_adr_frontmatter_promotion.py``, and the reason is the finding
itself. That script is deliberately stdlib-only (it runs as a pre-commit hook),
so a check added there could only *approximate* what a YAML parser rejects —
and a first attempt at that approximation flagged 418 false positives on
``tags: [a, b]``, a perfectly valid flow sequence. Approximating an oracle that
already exists is the wrong tool. Tests run under the project interpreter, where
the real parser is importable, so the oracle is the parser itself.

The defect this guards was **latent, not harmless**. Thirteen finalized records
carried frontmatter ``yaml.safe_load`` rejected — values opening with a backtick
(a YAML indicator) or containing ``": "`` in prose. Every in-repo consumer
(``adr_health``, ``finalize_adrs``, the promotion checker) parses tolerantly
line-by-line and never noticed, while the documented Discovery Protocol invites
a real parser. Any consumer that used one would have silently dropped those
thirteen records — and silence is the whole problem: a dropped decision does not
announce itself.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

DECISIONS = Path(__file__).parents[1] / ".ai-state" / "decisions"
FRONTMATTER_DELIMITER = "---"


def _frontmatter(text: str) -> str | None:
    """The raw frontmatter block, or None when the file carries none."""
    if not text.startswith(FRONTMATTER_DELIMITER):
        return None
    parts = text.split(FRONTMATTER_DELIMITER, 2)
    return parts[1] if len(parts) >= 3 else None


def _finalized_adrs() -> list[Path]:
    return sorted(DECISIONS.glob("[0-9]*.md"))


def test_every_finalized_adr_frontmatter_parses() -> None:
    """The invariant. A record a real parser cannot read is a record that vanishes."""
    unparseable: list[str] = []
    for path in _finalized_adrs():
        block = _frontmatter(path.read_text(encoding="utf-8"))
        if block is None:
            continue
        try:
            yaml.safe_load(block)
        except yaml.YAMLError as exc:
            unparseable.append(f"{path.name}: {type(exc).__name__}")

    assert not unparseable, (
        "finalized ADRs whose frontmatter a real YAML parser rejects "
        f"({len(unparseable)}): {unparseable}"
    )


def test_the_corpus_is_actually_being_scanned() -> None:
    """A positive control: an empty glob would make the invariant vacuously true.

    Without this, deleting the corpus — or renaming the directory — turns the
    test above green, which is the failure mode it exists to detect.
    """
    assert len(_finalized_adrs()) > 100, "the finalized-ADR corpus should not be near-empty"


@pytest.mark.parametrize(
    ("label", "value"),
    [
        ("opens with a backtick indicator", "`ROADMAP.md` at project root"),
        ("contains a colon-space in prose", "Adopt <!-- last-verified: YYYY-MM-DD --> markers"),
    ],
)
def test_canary_the_shapes_that_actually_shipped_are_rejected(label: str, value: str) -> None:
    """Both real-world shapes must fail the parser, so the invariant can catch them.

    Parameterised on the two forms found in the corpus rather than one invented
    example: the backtick opener accounted for most of the thirteen, and the
    bare ``": "`` for the rest, and they fail for different reasons.
    """
    with pytest.raises(yaml.YAMLError):
        yaml.safe_load(f"id: dec-001\ntitle: {value}\n")

    # ...and quoting is the fix the repair applied, so it must round-trip exactly.
    quoted = "'" + value.replace("'", "''") + "'"
    assert yaml.safe_load(f"id: dec-001\ntitle: {quoted}\n")["title"] == value
