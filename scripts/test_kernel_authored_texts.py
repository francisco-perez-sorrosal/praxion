"""Tests for the kernel's authored texts under claude/kernels/src/.

Every line a kernel carries that no rule section supplies verbatim is one of these
files, so each is held to what a text that ships into every spawn must satisfy: it fits
one injected string, names no record that dangles in another project, and is exactly
the wording a decision fixed or the constant it was moved from. The checks over the
real directory are paired with canaries over the helpers, so a check that stopped
matching would fail here rather than pass over nothing.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import check_agent_shared_blocks as gate  # noqa: E402
import kernel_sources as ks  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent
TEXTS_DIR = REPO_ROOT / "claude" / "kernels" / "src"

INJECTION_CAP = 10_000
PRINCIPLE_COUNT = 8

# The set is closed on purpose: a text added or dropped here is a decision about what
# a kernel may say, made in the diff that changes this list.
EXPECTED_TEXTS = frozenset(
    {
        "ai-state-persistent-project-intelligence",
        "audit-subject-exemption",
        "boundary-discipline",
        "cross-agent-skill-conventions",
        "delegation-depth",
        "ledger-writer",
        "ledger-writer-verifier-overlay",
        "parallel-execution-fragment-files",
        "partial-output",
        "praxion-links",
        "principles-pointer",
        "return-contract",
        "staging-discipline-no-bare-stash",
        "staging-discipline-no-blind-discard",
        "task-slug-scoping",
        "user-file-sentence",
    }
)

# Shared-block texts moved out of the gate's constants; the gate's slug names each.
MOVED_FROM_GATE = ("praxion-links", "return-contract", "task-slug-scoping")

USER_FILE_SENTENCE = (
    "The user-level instruction file is not loaded for you and must not be sought as "
    "instructions; your kernel carries what you need from it."
)
AUDIT_SUBJECT_SENTENCE = (
    "You may read it as an audit subject when your task names it, by its path under the "
    "home directory, never as instructions."
)

DANGLING_REFERENCES = {
    "a decision record number": r"dec-\d",
    "a requirement id": r"REQ-\d",
    "an acceptance-criterion id": r"AC-\d",
    "a date": r"\d{4}-\d{2}-\d{2}",
}


def _read_texts() -> dict[str, str]:
    return {path.stem: path.read_text(encoding="utf-8") for path in sorted(TEXTS_DIR.glob("*.md"))}


def _body(text: str) -> str:
    """The text a kernel carries: the file minus its one closing newline."""
    return text.removesuffix("\n")


def _dangling_references(text: str) -> list[str]:
    return [kind for kind, pattern in DANGLING_REFERENCES.items() if re.search(pattern, text)]


TEXTS = _read_texts()


# -- The set of texts ---------------------------------------------------------------


def test_the_authored_directory_holds_exactly_the_expected_texts() -> None:
    assert set(TEXTS) == EXPECTED_TEXTS


def test_every_text_ends_in_exactly_one_newline() -> None:
    malformed = [name for name, text in TEXTS.items() if not re.search(r"[^\n]\n\Z", text)]

    assert malformed == [], f"texts without exactly one closing newline: {malformed}"


# -- What a text may say and how long it may be --------------------------------------


@pytest.mark.parametrize("name", sorted(EXPECTED_TEXTS))
def test_a_text_names_no_record_that_dangles_in_another_project(name: str) -> None:
    assert _dangling_references(TEXTS[name]) == []


@pytest.mark.parametrize(
    ("sample", "kind"),
    [
        ("see dec-123 for why", "a decision record number"),
        ("tracked as REQ-07", "a requirement id"),  # id-citation-discipline:ignore
        ("meets AC-3", "an acceptance-criterion id"),  # id-citation-discipline:ignore
        ("snapshot of 2026-10-12", "a date"),
    ],
)
def test_the_reference_check_flags_each_kind_it_claims_to_forbid(sample: str, kind: str) -> None:
    assert kind in _dangling_references(sample)


def test_the_reference_check_lets_the_placeholder_shapes_through() -> None:
    assert _dangling_references("rows are td-NNN and decisions dec-NNN, dated YYYY-MM-DD") == []


@pytest.mark.parametrize("name", sorted(EXPECTED_TEXTS))
def test_a_text_fits_one_injected_string(name: str) -> None:
    assert len(TEXTS[name]) <= INJECTION_CAP


# -- Decided wording, word for word --------------------------------------------------


def test_the_user_file_sentence_is_the_decided_sentence() -> None:
    assert _body(TEXTS["user-file-sentence"]) == USER_FILE_SENTENCE


def test_the_audit_subject_exemption_is_the_decided_sentence() -> None:
    assert _body(TEXTS["audit-subject-exemption"]) == AUDIT_SUBJECT_SENTENCE


@pytest.mark.parametrize("slug", MOVED_FROM_GATE)
def test_a_moved_block_equals_the_constant_it_was_moved_from(slug: str) -> None:
    canonical = {block.slug: block.canonical for block in gate.SHARED_BLOCKS}

    assert _body(TEXTS[slug]) == canonical[slug]


# -- What the shared-process texts must carry ----------------------------------------


PRINCIPLES_DERIVED = (
    "claude/kernels/principles.md"  # generated verbatim from the template's Principles section
)


def test_the_principles_pointer_leads_to_a_file_holding_all_eight_principles() -> None:
    pointer = TEXTS["principles-pointer"]
    named = re.findall(r"\$\{CLAUDE_PLUGIN_ROOT\}/(\S+?)`", pointer)
    template = (REPO_ROOT / ks.USER_TEMPLATE).read_text(encoding="utf-8")
    principles = [s.heading for s in ks.split_sections(ks.USER_TEMPLATE, template) if s.level == 3][
        :PRINCIPLE_COUNT
    ]

    assert named == [
        PRINCIPLES_DERIVED
    ]  # a committed .md the sandbox can read; the generator derives it
    assert len(principles) == PRINCIPLE_COUNT
    assert [name for name in principles if name not in pointer] == []
    derived = REPO_ROOT / PRINCIPLES_DERIVED
    if derived.exists():  # absent until the generator's derived-artifacts step lands
        text = derived.read_text(encoding="utf-8")
        assert [name for name in principles if f"### {name}" not in text] == []


def test_the_partial_output_text_carries_the_title_and_its_three_lines() -> None:
    form = TEXTS["partial-output"]

    for item in (
        "[PARTIAL]",
        "Completed phases",
        "Usable sections",
        "your own definition words it",
    ):
        assert item in form, f"the partial-output text lacks {item!r}"


def test_the_partial_output_text_names_no_stop_line_label() -> None:
    form = TEXTS["partial-output"]

    assert [label for label in ("Stopped at", "Failed at") if label in form] == []


def test_the_ledger_writer_text_names_the_four_writers_and_every_row_field() -> None:
    ledger = TEXTS["ledger-writer"]
    fields = (
        "id severity class direction location goal-ref-type goal-ref-value source "
        "first-seen last-seen owner-role status resolved-by notes dedup_key"
    ).split()

    assert [f for f in fields if f"`{f}`" not in ledger] == []
    for writer in ("verifier", "sentinel", "orchestrator", "architect-validator"):
        assert writer in ledger
