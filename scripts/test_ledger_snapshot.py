"""Tests for `ledger_snapshot.py` -- the state-snapshot reader (unjudged path).

Behavioral tests for the reader's advisory contract, its evidence classes
(location decay, decision drift, goal-link resolution, commits naming a row,
duplicates, in-place amendments, citation decay), key status and withheld
oracles.

Two fixture tiers:

- The frozen `base/` ledger snapshot (`_ledger_triage_testkit.build_fixture_repo`)
  drives the ground-truth recall assertions -- real
  rows, real notes, real ADR edges, copied byte-for-byte from `cac1ba2e`.
- Hermetic synthetic repos, built inline per test, drive the oracle-dependent
  canaries this frozen snapshot cannot safely stand in for: `citation-decay`
  positives/negatives and the withheld-oracle canaries. Reproducing the live
  ledger's exact notes-citation resolution state for the amendment's named ids
  (td-086/173/176/186/199/206/274) would require stubbing every repo path
  those rows' *notes* happen to mention -- dozens of unrelated paths the
  frozen fixture's README does not claim to stub (it stubs `location` cells
  only).

The dataclass names (`ActiveRow`, `RowDelta`, `LocationDecay`, ...) and the
signatures `gather(repo_root) -> StateSnapshot` and
`row_delta(snapshot, row) -> RowDelta` are the reader's representation
contract.
"""

from __future__ import annotations

from pathlib import Path

import ledger_snapshot
import pytest
from _ledger_triage_testkit import build_fixture_repo, git_ok

# `base_repo` / `td264_post_rebase_repo` are pytest fixtures from `conftest.py`
# (no import needed -- pytest auto-discovers them by parameter name).

# -- Helpers -------------------------------------------------------------------


def _row(snapshot, row_id: str):
    """The `ActiveRow` for `row_id`, or fail with a clear message if absent."""
    match = next((r for r in snapshot.active_rows if r.id == row_id), None)
    assert match is not None, f"{row_id} not found among {len(snapshot.active_rows)} active rows"
    return match


def _delta_for(repo_root: Path, row_id: str):
    snapshot = ledger_snapshot.gather(repo_root)
    row = _row(snapshot, row_id)
    return ledger_snapshot.row_delta(snapshot, row)


def _evidence_classes(delta) -> set[str]:
    """The distinct evidence-signal class names on one `RowDelta`.

    Each signal variant carries the class name it represents as its
    own type; `_signal_class` maps the dataclass instance to the class-name
    string the digest and `CLASS_POLICY` key on (`self-amended`,
    `location-decay`, ...), so this helper reads the *behavior* the digest
    exposes rather than asserting on Python type identity.
    """
    return {ledger_snapshot.signal_class_name(signal) for signal in delta.signals}


# -- Ground truth: recall 8/9, td-156 an asserted miss -----------------


@pytest.mark.parametrize(
    "row_id",
    ["td-064", "td-086", "td-088", "td-162", "td-186", "td-211", "td-213"],
)
def test_self_amended_rows_are_flagged_as_candidates(base_repo: Path, row_id: str) -> None:
    delta = _delta_for(base_repo, row_id)
    assert "self-amended" in _evidence_classes(delta)


def test_possible_duplicate_recovers_td270_via_resolved_peer_td095(base_repo: Path) -> None:
    delta = _delta_for(base_repo, "td-270")
    assert "possible-duplicate" in _evidence_classes(delta)
    peer_ids = {
        signal.peer_id
        for signal in delta.signals
        if ledger_snapshot.signal_class_name(signal) == "possible-duplicate"
    }
    assert "td-095" in peer_ids


def test_td156_is_a_documented_mechanical_miss_not_a_candidate(base_repo: Path) -> None:
    """A correct premise with no structural amendment -- unreachable by design.

    This is not a bug: the `self-amended` signal is structural (a
    non-stamp segment count), and td-156 was never re-amended. `--all`
    (the first real triage) is what recovers rows like this, per A5.
    """
    delta = _delta_for(base_repo, "td-156")
    assert _evidence_classes(delta) == set()


# -- Live-premise negatives ---------------------------------------------


def test_td185_has_no_evidence_despite_four_file_overlaps(base_repo: Path) -> None:
    """File overlap alone never becomes evidence -- td-185 links to
    4 ADRs in this fixture's stub corpus, all context-only."""
    delta = _delta_for(base_repo, "td-185")
    assert _evidence_classes(delta) == set()


def test_td264_pre_rebase_candidate_class_is_possible_duplicate_only(base_repo: Path) -> None:
    """td-264's only evidence is its base-key twin td-257 -- never file overlap
    with dec-394 (which appears only in `context.related_decisions`)."""
    delta = _delta_for(base_repo, "td-264")
    assert _evidence_classes(delta) == {"possible-duplicate"}
    related_ids = {rel.dec_id for rel in delta.context.related_decisions}
    assert "dec-394" in related_ids


# -- Decision drift --------------------------------------------


def test_td084_flags_decision_drift_on_partially_superseded_dec310(base_repo: Path) -> None:
    delta = _delta_for(base_repo, "td-084")
    assert "decision-drift" in _evidence_classes(delta)
    drift = next(
        s
        for s in delta.signals
        if ledger_snapshot.signal_class_name(s) == "decision-drift" and s.dec_id == "dec-310"
    )
    assert drift.by == ("dec-375",)


def test_td172_flags_decision_drift_on_partially_superseded_dec364(base_repo: Path) -> None:
    delta = _delta_for(base_repo, "td-172")
    drift = next(
        s
        for s in delta.signals
        if ledger_snapshot.signal_class_name(s) == "decision-drift" and s.dec_id == "dec-364"
    )
    assert drift.by == ("dec-366",)


def test_td173_flags_decision_drift_on_superseded_dec160(base_repo: Path) -> None:
    delta = _delta_for(base_repo, "td-173")
    drift = next(
        s
        for s in delta.signals
        if ledger_snapshot.signal_class_name(s) == "decision-drift" and s.dec_id == "dec-160"
    )
    assert drift.change == "superseded"
    assert drift.by == ("dec-374",)


# -- Key facts -----------------------------------------------------------


@pytest.mark.parametrize("row_id", ["td-257", "td-264", "td-270", "td-281"])
def test_discriminated_rows_report_discriminated_key_status(base_repo: Path, row_id: str) -> None:
    snapshot = ledger_snapshot.gather(base_repo)
    row = _row(snapshot, row_id)
    assert row.key.status == "discriminated"


def test_a_plain_key_row_reports_plain_key_status(base_repo: Path) -> None:
    snapshot = ledger_snapshot.gather(base_repo)
    row = _row(snapshot, "td-156")
    assert row.key.status == "plain"


# -- td-264 post-rebase: notes-amended-in-place + re-key --------------------------


def test_td264_post_rebase_row_is_self_amended(td264_post_rebase_repo: Path) -> None:
    """The rebased row carries an appended `Part fixed by 4b9e8462` segment --
    a real notes-amended-in-place case, distinct from the `base/` snapshot."""
    delta = _delta_for(td264_post_rebase_repo, "td-264")
    assert "self-amended" in _evidence_classes(delta)


def test_td264_post_rebase_key_is_discriminated_at_the_new_hash(
    td264_post_rebase_repo: Path,
) -> None:
    snapshot = ledger_snapshot.gather(td264_post_rebase_repo)
    row = _row(snapshot, "td-264")
    assert row.key.status == "discriminated"
    assert row.key.resolved == "898240af0a2e"


# -- Advisory contract: gather never writes -----------------------


def test_gather_leaves_ledger_files_byte_identical(base_repo: Path) -> None:
    ledger_path = base_repo / ".ai-state" / "TECH_DEBT_LEDGER.md"
    resolved_path = base_repo / ".ai-state" / "TECH_DEBT_RESOLVED.md"
    before = (ledger_path.read_bytes(), resolved_path.read_bytes())
    ledger_snapshot.gather(base_repo)
    after = (ledger_path.read_bytes(), resolved_path.read_bytes())
    assert before == after


# -- Withheld canaries, one per oracle -----------------------------------


def test_no_git_history_withholds_vanished_cause_and_cited_by_commit(tmp_path: Path) -> None:
    """Without `.git`, `vanished` (needs both git indexes) and `cited-by-commit`
    (needs the commit index) must never be reported -- silently defaulting them
    would misread "the oracle didn't answer" as "the file is gone"."""
    repo_root = build_fixture_repo(tmp_path, "base")
    import shutil

    shutil.rmtree(repo_root / ".git")

    snapshot = ledger_snapshot.gather(repo_root)
    withheld_classes = {w.class_name for w in snapshot.withheld}
    assert "cited-by-commit" in withheld_classes

    for row in snapshot.active_rows:
        delta = ledger_snapshot.row_delta(snapshot, row)
        for signal in delta.signals:
            if ledger_snapshot.signal_class_name(signal) == "location-decay":
                assert signal.cause != "vanished"


def test_no_adr_corpus_withholds_decision_drift_and_goal_link_unresolved(tmp_path: Path) -> None:
    repo_root = build_fixture_repo(tmp_path, "base")
    import shutil

    shutil.rmtree(repo_root / ".ai-state" / "decisions")
    git_ok(repo_root, "add", "-A")
    git_ok(repo_root, "commit", "-q", "-m", "remove ADR corpus")

    snapshot = ledger_snapshot.gather(repo_root)
    withheld_classes = {w.class_name for w in snapshot.withheld}
    assert "decision-drift" in withheld_classes
    assert "goal-link-unresolved" in withheld_classes


def test_architecture_goal_ref_withholds_goal_link_class_for_that_row(base_repo: Path) -> None:
    """td-064's goal-ref-type is `architecture` (not `adr`) -- the reader withholds
    the class rather than reporting a false "goal gone"."""
    snapshot = ledger_snapshot.gather(base_repo)
    row = _row(snapshot, "td-064")
    withheld_reasons = {w.reason for w in row.row_withheld}
    assert any(reason.startswith("goal-oracle-unsupported:") for reason in withheld_reasons)


# -- `citation-decay` (amendment; strong tier, location-decay oracles) ----------


def test_unresolved_notes_citation_fires_citation_decay(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    git_ok(repo_root, "init", "-q", "-b", "main")
    git_ok(repo_root, "config", "user.email", "t@t.t")
    git_ok(repo_root, "config", "user.name", "t")
    state = repo_root / ".ai-state"
    state.mkdir()
    header = (
        "# Technical Debt Ledger\n\n**Schema**: 14 row fields + 1 structural "
        "`dedup_key`.\n\n"
        "| id | severity | class | direction | location | goal-ref-type | "
        "goal-ref-value | source | first-seen | last-seen | owner-role | "
        "status | resolved-by | notes | dedup_key |\n"
        "|----|----------|-------|-----------|----------|---------------|"
        "----------------|--------|------------|-----------|-----------|"
        "--------|-------------|-------|-----------|\n"
    )
    row = (
        "| td-900 | suggested | other | code-to-goals | scripts/x.py | "
        "code-quality |  | verifier | 2026-01-01 | 2026-01-01 | implementer | "
        "open |  | See `scripts/vanished_module.py` for the prior "
        "implementation. | 000000000000 |\n"
    )
    (state / "TECH_DEBT_LEDGER.md").write_text(header + row, encoding="utf-8")
    (state / "TECH_DEBT_RESOLVED.md").write_text(header, encoding="utf-8")
    (repo_root / "scripts").mkdir()
    (repo_root / "scripts" / "x.py").write_text("stub\n", encoding="utf-8")
    git_ok(repo_root, "add", "-A")
    git_ok(
        repo_root, *("-c", "user.email=t@t.t", "-c", "user.name=t"), "commit", "-q", "-m", "seed"
    )

    snapshot = ledger_snapshot.gather(repo_root)
    row_obj = _row(snapshot, "td-900")
    delta = ledger_snapshot.row_delta(snapshot, row_obj)
    assert "citation-decay" in _evidence_classes(delta)


@pytest.mark.parametrize(
    "cite",
    [
        "See `.ai-work/some-slug/NOTES.md` for context.",
        "Tracked in `.claude/worktrees/feature-x/scratch.md`.",
        "Written to `tmp/scratch.py` during debugging.",
        "Documented at `~/.claude/CLAUDE.md`.",
        "See https://example.com/some/repo/path.py for background.",
    ],
)
def test_lazy_or_ephemeral_shaped_citations_never_fire_citation_decay(
    tmp_path: Path, cite: str
) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    git_ok(repo_root, "init", "-q", "-b", "main")
    git_ok(repo_root, "config", "user.email", "t@t.t")
    git_ok(repo_root, "config", "user.name", "t")
    state = repo_root / ".ai-state"
    state.mkdir()
    header = (
        "# Technical Debt Ledger\n\n**Schema**: 14 row fields + 1 structural "
        "`dedup_key`.\n\n"
        "| id | severity | class | direction | location | goal-ref-type | "
        "goal-ref-value | source | first-seen | last-seen | owner-role | "
        "status | resolved-by | notes | dedup_key |\n"
        "|----|----------|-------|-----------|----------|---------------|"
        "----------------|--------|------------|-----------|-----------|"
        "--------|-------------|-------|-----------|\n"
    )
    row = (
        f"| td-901 | suggested | other | code-to-goals | scripts/x.py | "
        f"code-quality |  | verifier | 2026-01-01 | 2026-01-01 | implementer | "
        f"open |  | {cite} | 000000000000 |\n"
    )
    (state / "TECH_DEBT_LEDGER.md").write_text(header + row, encoding="utf-8")
    (state / "TECH_DEBT_RESOLVED.md").write_text(header, encoding="utf-8")
    (repo_root / "scripts").mkdir()
    (repo_root / "scripts" / "x.py").write_text("stub\n", encoding="utf-8")
    git_ok(repo_root, "add", "-A")
    git_ok(
        repo_root, *("-c", "user.email=t@t.t", "-c", "user.name=t"), "commit", "-q", "-m", "seed"
    )

    snapshot = ledger_snapshot.gather(repo_root)
    row_obj = _row(snapshot, "td-901")
    delta = ledger_snapshot.row_delta(snapshot, row_obj)
    assert "citation-decay" not in _evidence_classes(delta)


# -- stamp grammar: the paired-site test ------------------------------------


def test_documented_stamp_examples_parse_under_the_stamp_grammar() -> None:
    """Paired-site test (gate-liveness two-site rule): the example stamps in
    `tech-debt-ledger.md § Triage` must parse under `ledger_snapshot`'s stamp
    regex. Until that section exists the test skips, so a missing section
    never masquerades as a grammar failure.
    """
    doc_path = (
        Path(__file__).resolve().parent.parent
        / "skills"
        / "software-planning"
        / "references"
        / "tech-debt-ledger.md"
    )
    text = doc_path.read_text(encoding="utf-8") if doc_path.is_file() else ""
    section_marker = "## Triage"
    if section_marker not in text:
        pytest.skip("tech-debt-ledger.md § Triage not written yet (the /triage-debt protocol)")

    section = text.split(section_marker, 1)[1]
    import re

    examples = re.findall(r"`(\[triage \d{4}-\d{2}-\d{2} @[0-9a-f]{7,40}\][^`]*)`", section)
    assert examples, "no example stamps found in tech-debt-ledger.md § Triage"
    for example in examples:
        result = ledger_snapshot.parse_stamp(example)
        assert not isinstance(result, ledger_snapshot.StampMalformed), (
            f"documented example failed to parse: {example!r}"
        )


# -- outcomes: `realigned` and the discard anchor gate ----------------------


@pytest.mark.parametrize(
    "segment",
    [
        "[triage 2026-09-27 @9ad0e205] kept: scripts/foo.py:12 premise still holds",
        "[triage 2026-09-27 @9ad0e205] realigned from 0123456789ab: old premise named bar.py",
        "[triage 2026-09-27 @9ad0e205] realigned: citations moved to scripts/foo.py:40",
        "[triage 2026-09-27 @9ad0e205] discarded: premise refuted at scripts/foo.py:40",
        "[triage 2026-09-27 @9ad0e205] discarded: made moot by dec-401",
        "[triage 2026-09-27 @9ad0e205] discarded: fixed by c95a9e96",
        "[triage 2026-09-27 @9ad0e205] merged into td-257",
    ],
)
def test_well_formed_stamps_parse(segment: str) -> None:
    result = ledger_snapshot.parse_stamp(segment)
    assert not isinstance(result, ledger_snapshot.StampMalformed), segment


def test_realigned_is_a_first_class_outcome() -> None:
    result = ledger_snapshot.parse_stamp(
        "[triage 2026-09-27 @9ad0e205] realigned from 0123456789ab: old premise"
    )
    assert result.outcome == "realigned"


@pytest.mark.parametrize(
    "segment",
    [
        "[triage 2026-09-27 @9ad0e205] discarded: no longer relevant",
        "[triage 2026-09-27 @9ad0e205] discarded: superseded by later work",
        "[triage 2026-09-27 @9ad0e205] repurposed from 0123456789ab: old premise",
    ],
)
def test_stamps_without_a_checkable_anchor_or_legal_outcome_are_malformed(segment: str) -> None:
    """a discard must cite a path:line, dec-NNN, td-NNN or commit sha;
    `repurposed` is not an outcome after the north-star amendment."""
    assert isinstance(ledger_snapshot.parse_stamp(segment), ledger_snapshot.StampMalformed)
