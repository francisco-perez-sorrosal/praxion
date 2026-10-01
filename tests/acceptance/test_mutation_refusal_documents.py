"""No project document still says a missing mutation reading is only recorded or warned.

Once a tagged step without a reading is blocked, a document that tells a reader
the refusal is "recorded, no finding", or that a missing line is a `WARN`,
trains the reader to let the step through. A statement about a refusal or a
missing `Mutation:` line may still describe a non-blocking disposition, but
only for the `not-flat-layout` refusal, or alongside the block itself.

The documents read are the ones that describe the mutation tag, the sensor's
line, or the verifier's disposition of it.
"""

from __future__ import annotations

import re

import pytest

from tests.acceptance.drivers.gate_liveness import REPO_ROOT

MUTATION_DOCUMENTS = (
    "agents/verifier.md",
    "agents/implementer.md",
    "agents/test-engineer.md",
    "agents/implementation-planner.md",
    "docs/architecture.md",
    "scripts/CLAUDE.md",
    ".ai-state/DESIGN.md",
    "skills/software-planning/references/agent-pipeline-details.md",
    "skills/software-planning/references/decomposition-guide.md",
    "skills/software-planning/references/document-templates.md",
    "skills/testing-strategy/references/python-testing.md",
)
OTHER_REFUSAL_REASONS = (
    "path-missing",
    "pyproject-present",
    "mutants-dir-present",
    "toolchain-missing",
    "run-timeout",
    "run-failed",
)

_ABOUT_A_MISSING_READING = re.compile(
    r"unavailable|refusal|\bno\b[\s*`]*Mutation:?[`*]*\s+line|absence", re.IGNORECASE
)
_MISSING_LINE = re.compile(r"\bno\b[\s*`]*Mutation:?[`*]*\s+line|absence", re.IGNORECASE)
_NON_BLOCKING = re.compile(r"\brecorded\b|\bWARN\b|\badvisory\b")
_BLOCKS = re.compile(r"(?<!non-)\b(?:blocks|blocked|blocking)\b", re.IGNORECASE)


def _only_about_the_layout_refusal(statement: str) -> bool:
    return (
        "not-flat-layout" in statement
        and not any(reason in statement for reason in OTHER_REFUSAL_REASONS)
        and not _MISSING_LINE.search(statement)
    )


def _lets_a_missing_reading_through(statement: str) -> bool:
    return (
        "Mutation" in statement
        and bool(_ABOUT_A_MISSING_READING.search(statement))
        and bool(_NON_BLOCKING.search(statement))
        and not _BLOCKS.search(statement)
        and not _only_about_the_layout_refusal(statement)
    )


@pytest.mark.parametrize("relpath", MUTATION_DOCUMENTS)
def test_document_states_no_non_blocking_disposition_for_a_missing_reading(relpath):
    text = (REPO_ROOT / relpath).read_text(encoding="utf-8")

    offending = [
        f"{relpath}:{number}: {line.strip()[:200]}"
        for number, line in enumerate(text.splitlines(), start=1)
        if _lets_a_missing_reading_through(line)
    ]

    assert not offending, (
        "these statements still say a refusal or a missing mutation line is only recorded "
        "or warned about:\n" + "\n".join(offending)
    )
