"""Every reader of the reconciler's verdict vocabulary names every verdict.

The reconciler decides which verdict words exist (`VERDICT_WORDS`); three
readers explain them to someone who acts on them: the `/resume-pipeline`
command, the Mechanism paragraph of the completion handshake, and the
reconciler's own `--help` text. A verdict added to the vocabulary but missing
from one of them leaves that reader unable to say what to do with it -- worst
for a verdict that must never be resumed automatically. Each site is pinned
here, and a canary proves the check bites when a word is removed.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import reconcile_pipeline_state  # noqa: E402
from _step_verdict import VERDICT_WORDS  # noqa: E402

RESUME_COMMAND = REPO_ROOT / "commands" / "resume-pipeline.md"
HANDSHAKE_DOC = (
    REPO_ROOT / "skills" / "software-planning" / "references" / "agent-pipeline-details.md"
)
MECHANISM_MARKER = "**Mechanism.**"
# The key every reader must explain beside the words: what decided the verdict.
DECIDING_KEY = "decided_by"


def missing_words(text: str, words: tuple[str, ...] = (*VERDICT_WORDS, DECIDING_KEY)) -> list[str]:
    """The words `text` never uses as a whole token (`in-flight` is not `flight`)."""
    return [w for w in words if not re.search(rf"(?<![\w-]){re.escape(w)}(?![\w-])", text)]


def mechanism_paragraph() -> str:
    lines = HANDSHAKE_DOC.read_text(encoding="utf-8").splitlines()
    return next(line for line in lines if line.startswith(MECHANISM_MARKER))


def help_text() -> str:
    return " ".join(reconcile_pipeline_state._build_parser().format_help().split())


SITES = {
    "resume-pipeline command": lambda: RESUME_COMMAND.read_text(encoding="utf-8"),
    "handshake mechanism paragraph": mechanism_paragraph,
    "reconciler --help": help_text,
}


@pytest.mark.parametrize("site", SITES)
def test_every_verdict_word_and_the_deciding_key_appear_at_each_reader(site: str) -> None:
    assert missing_words(SITES[site]()) == []


def test_the_vocabulary_includes_the_verdict_that_is_never_resumed_automatically() -> None:
    assert "attempts-exhausted" in VERDICT_WORDS


@pytest.mark.parametrize("word", VERDICT_WORDS)
def test_canary_a_word_removed_from_a_prose_fixture_is_reported_missing(word: str) -> None:
    fixture = " ".join((*VERDICT_WORDS, DECIDING_KEY))
    assert missing_words(fixture) == []

    pruned = re.sub(rf"(?<![\w-]){re.escape(word)}(?![\w-])", "", fixture)

    assert missing_words(pruned) == [word]


def test_canary_a_longer_word_does_not_stand_in_for_a_verdict_word() -> None:
    assert missing_words("in-flighty unknown-ish", ("in-flight", "unknown")) == [
        "in-flight",
        "unknown",
    ]
