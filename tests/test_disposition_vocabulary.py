"""Behavioral tests for skills/software-planning/references/disposition-vocabulary.md.

Tests encode the structural contract the vocabulary reference must satisfy.
Production file does not exist yet; tests are expected to FAIL until the
disposition vocabulary file is created by the implementer.

Imports are at module level (file-existence and markdown structure tests
need no Python module import; pathlib reads suffice). Tests fail with a
clear FileNotFoundError or AssertionError, not an ImportError.
"""

from __future__ import annotations

import re
from pathlib import Path

VOCAB_FILE = (
    Path(__file__).resolve().parent.parent
    / "skills/software-planning/references/disposition-vocabulary.md"
)

DISPOSITION_TERMS = ("switch-now", "defer-with-rationale", "dismiss-with-rationale")


def test_disposition_vocabulary_file_exists():
    """The canonical vocabulary reference file must exist at the declared path."""
    assert VOCAB_FILE.exists(), (
        f"Expected vocabulary file at {VOCAB_FILE}; Vocabulary file not found or the path changed."
    )


def test_all_three_terms_defined():
    """Each of the three disposition terms must be defined in the file.

    Accepts either a ## heading or a definition-list / table row containing
    the term, so the implementer can choose the most readable structure.
    """
    text = VOCAB_FILE.read_text(encoding="utf-8")
    for term in DISPOSITION_TERMS:
        pattern = re.compile(
            rf"(?:^##\s+.*{re.escape(term)}|^\*\*{re.escape(term)}\*\*|^{re.escape(term)}\s*:|\|[^|]*{re.escape(term)}[^|]*\|)",
            re.MULTILINE | re.IGNORECASE,
        )
        assert pattern.search(text), (
            f"Disposition term '{term}' not found as a heading, definition, "
            f"or table row in {VOCAB_FILE.name}"
        )


def test_consuming_surfaces_section_present():
    """A 'Consuming surfaces' section must be present and name both CIS and rework-loop."""
    text = VOCAB_FILE.read_text(encoding="utf-8")
    assert re.search(r"##\s+Consuming[- ]?[Ss]urfaces", text), (
        f"Missing '## Consuming Surfaces' section in {VOCAB_FILE.name}"
    )
    lower = text.lower()
    assert "cis" in lower or "continuous improvement" in lower, (
        "Consuming surfaces section must reference CIS (Continuous Improvement Signals)"
    )
    assert "rework" in lower, "Consuming surfaces section must reference the rework-loop surface"


def test_how_to_cite_section_present():
    """A 'How to cite' subsection must be present with usage guidance."""
    text = VOCAB_FILE.read_text(encoding="utf-8")
    assert re.search(r"##\s+How[- ]to[- ][Cc]ite", text, re.IGNORECASE), (
        f"Missing '## How to cite' section in {VOCAB_FILE.name}; "
        "the vocabulary file must include usage guidance for consuming agents"
    )
