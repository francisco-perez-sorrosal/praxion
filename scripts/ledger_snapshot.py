"""State-snapshot reader for the tech-debt ledger: what moved since a row was filed.

A ledger row is a claim about the project as it stood on the day it was written.
This module reads the *current* project state once -- the ledger pair, the ADR
corpus, git history -- into an immutable `StateSnapshot`, then computes, per
active row, a `RowDelta`: the signals that the state has moved against the row's
premise, plus context that never counts as a signal.

Two halves, split on the effect boundary:

    gather(repo_root) -> StateSnapshot     here; the only function that reads the world
    row_delta(snapshot, row) -> RowDelta   `ledger_delta.py`; pure, every signal lives there

This module is the reader's public surface: it re-exports `row_delta` and
`signal_class_name` from its pure core, whose types callers import directly.

The reader decides nothing about candidacy -- which signals count as evidence and
how they rank is `ledger_health.py`'s policy. What the reader *does* own is which
signals it can compute honestly. Every class that depends on an oracle (git
history, the ADR corpus, the lifecycle table) is **withheld with a named reason**
when that oracle cannot answer, never defaulted: without git, a missing path is
`unclassified`, not `vanished`, because "the index did not answer" is not "the
file is gone" (the `adr_health.py` discipline, whose indexes this reuses).

File overlap between a row's location and an ADR's `affected_files` is context
only (`RelatedDecision`). Measured on the live ledger it links half the active
rows, live ones included, so it can select context but must never make a row a
candidate.

Stdlib only: the sentinel runs the probe on top of this with a bare `python3`.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from datetime import date
from pathlib import Path
from typing import assert_never

from _git_runner import GitUnavailableError, git_output, run_git
from adr_health import (
    build_deletion_index,
    build_rename_index,
    history_available,
    load_expected_absent_shapes,
)
from ledger_delta import (
    STAMP_PREFIX,
    ActiveRow,
    AdrGoal,
    Anchor,
    Anchored,
    AnchorWindow,
    Commit,
    DecisionCitation,
    DecisionFacts,
    DraftGoal,
    GitFacts,
    GoalRef,
    Judged,
    KeyFacts,
    KeyStatus,
    LocationRef,
    MalformedGoal,
    NoGoal,
    OpaqueRef,
    Oracle,
    OtherGoal,
    Outcome,
    PathRef,
    StampMalformed,
    StampState,
    StateSnapshot,
    TdId,
    TerminalPeer,
    TriageStamp,
    Unanchored,
    Unjudged,
    UnparseableRow,
    Withheld,
    cite_path,
    parse_iso_date,
    signal_class_name,
)
from ledger_delta_signals import (
    discard_recurrences,
    notes_path_citations,
    row_delta,
)
from query_adrs import (
    _FRONTMATTER_RE,
    _as_list,
    _parse_frontmatter_fallback,
    _try_import_yaml,
    discover_adr_files,
)
from state_ledger_schema import (
    LEDGERS,
    TECH_DEBT_NAMESPACE,
    DataRow,
    ParsedLedger,
    collision_blocked_ids,
    compute_dedup_key,
    dedup_rows,
    parse_ledger,
    resolve_dedup_keys,
)

# The reader's public surface: the shell's own entry points plus the pure core's.
__all__ = [
    "CLASS_ORACLES",
    "StampMalformed",
    "StateSnapshot",
    "TriageStamp",
    "discard_recurrences",
    "gather",
    "parse_rows",
    "parse_stamp",
    "row_delta",
    "signal_class_name",
    "split_segments",
    "stamp_anchors",
    "stamp_state",
    "with_stamp",
]

# -- Row grammar ---------------------------------------------------------------

_ACTIVE_STATUSES: frozenset[str] = frozenset({"open", "in-flight"})
_TERMINAL_STATUSES: frozenset[str] = frozenset({"resolved", "wontfix"})
# Legal statuses per file, in `LEDGERS` order. A terminal row may still sit in the
# active file: it migrates to the resolved file only at the next on-main commit, so
# between a triage write and that commit it is a terminal peer, not a malformed row.
_FILE_STATUSES = (_ACTIVE_STATUSES | _TERMINAL_STATUSES, _TERMINAL_STATUSES)
_OTHER_GOAL_KINDS: frozenset[str] = frozenset({"spec-req", "architecture", "claude-md"})
_TD_ID = re.compile(r"^td-\d{3,}$")
_TD_TOKEN = re.compile(r"\btd-\d{3,}\b")
_DEC_ID = re.compile(r"^dec-\d{3,}$")
_DEC_TOKEN = re.compile(r"\bdec-\d{3,}\b")
_SEGMENT_SEPARATOR = " // "

# Which oracle each withholdable class needs. A `:cause` suffix names a sub-class:
# a missing path is still reported without git, only its `vanished` verdict is not.
CLASS_ORACLES: Mapping[str, tuple[Oracle, ...]] = {
    "location-decay:vanished": ("git-history", "lifecycle-table"),
    "citation-decay:vanished": ("git-history", "lifecycle-table"),
    "cited-by-commit": ("git-history",),
    "decision-drift": ("adr-corpus",),
    "goal-link-unresolved": ("adr-corpus",),
    # Without git, a Judged row's anchor cannot be resolved at all -- this is
    # a corpus-wide withhold rather than a per-row `JudgmentUnusable` signal,
    # so a missing oracle never flags every stamped row.
    "judgment-unusable:unanchored": ("git-history",),
}

# -- Triage stamp grammar -----------------------------------------------------------
# Paired site: the grammar line in skills/software-planning/references/tech-debt-ledger.md
# § Triage. Change both together; a test parses that section's example stamps with this.
_STAMP = re.compile(
    r"^\[triage (?P<date>\d{4}-\d{2}-\d{2}) @(?P<anchor>[0-9a-f]{7,40})\] "
    r"(?P<outcome>[a-z]+)(?: from (?P<prior>[0-9a-f]{12}))?(?P<sep>:| into) (?P<text>\S.*)$"
)
_OUTCOMES: Mapping[str, Outcome] = {
    "kept": "kept",
    "realigned": "realigned",
    "discarded": "discarded",
    "merged": "merged",
}
# The extension must start with a letter, so a ratio ("3.5:1") or a version ("v1.2:3")
# is never read as a `path:line`.
_LINE_CITE = re.compile(r"(?:[\w.-]+/)*[\w-][\w.-]*\.[A-Za-z]\w*:\d+")
# A sha must carry both a digit and a hex letter: English words spelled in hex
# ("defaced") and plain numbers ("20260927", "1000000") are not commits.
_SHA = re.compile(r"\b(?=[0-9a-f]*\d)(?=[0-9a-f]*[a-f])[0-9a-f]{7,40}\b")
# What makes a discard checkable: a location, a decision, a row, or a commit.
_CHECKABLE_ANCHORS = (_LINE_CITE, _DEC_TOKEN, _TD_TOKEN, _SHA)

# -- Boundary parsing ----------------------------------------------------------------------


def stamp_anchors(text: str) -> Mapping[str, tuple[str, ...]]:
    """Every checkable anchor a stamp's text cites, by kind: path, dec, td, sha.

    The grammar only proves an anchor is *shaped* right; the apply step resolves
    each one against the repository before the stamp is written.
    """
    return {
        "path": tuple(cite_path(found) for found in _LINE_CITE.findall(text)),
        "dec": tuple(_DEC_TOKEN.findall(text)),
        "td": tuple(_TD_TOKEN.findall(text)),
        "sha": tuple(_SHA.findall(text)),
    }


def parse_stamp(segment: str, segment_index: int = 0) -> TriageStamp | StampMalformed:
    """Parse one notes segment into a stamp; anything off-grammar is `StampMalformed`.

    A `discarded` stamp must carry a checkable anchor -- a `path:line`, a decision,
    a row id or a commit sha -- so a bare "no longer relevant" can never be written
    as a verdict: that judgment belongs to the user, not to the stamp.
    """
    malformed = StampMalformed(raw=segment, segment_index=segment_index)
    found = _STAMP.match(segment.strip())
    if found is None or "|" in segment:
        return malformed
    try:
        stamped = date.fromisoformat(found["date"])
    except ValueError:
        return malformed
    outcome, prior, text = found["outcome"], found["prior"], found["text"]
    if prior is not None and outcome != "realigned":
        return malformed
    evidence_path = _path_token(text.split()[0]) if outcome == "kept" else None
    match (outcome, found["sep"]):
        case ("kept", ":"):
            valid = evidence_path is not None
        case ("realigned", ":"):
            valid = True
        case ("discarded", ":"):
            valid = any(pattern.search(text) for pattern in _CHECKABLE_ANCHORS)
        case ("merged", " into"):
            valid = _TD_ID.match(text.strip()) is not None
        case _:
            valid = False
    if not valid:
        return malformed
    return TriageStamp(stamped, found["anchor"], _OUTCOMES[outcome], text, evidence_path, prior)


def _path_token(token: str) -> str | None:
    """The path a `kept` stamp's first token names, or None when it names none."""
    path = cite_path(token)
    return path if "/" in path or "." in path else None


def split_segments(notes: str) -> tuple[str, ...]:
    """Split a notes cell on its ` // ` separator, never inside a backtick span.

    A quoted separator (a table row, an escape example) is content, not an amendment.
    An unbalanced backtick would hide every later separator -- stamps included -- so
    such a cell falls back to the plain split.
    """
    if notes.count("`") % 2:
        return tuple(notes.split(_SEGMENT_SEPARATOR))
    segments, start, in_code = [], 0, False
    index = 0
    while index < len(notes):
        if notes[index] == "`":
            in_code = not in_code
        elif not in_code and notes.startswith(_SEGMENT_SEPARATOR, index):
            segments.append(notes[start:index])
            index += len(_SEGMENT_SEPARATOR)
            start = index
            continue
        index += 1
    segments.append(notes[start:])
    return tuple(segments)


def with_stamp(notes: str, stamp: str) -> str:
    """The notes cell once `stamp` is appended as its newest segment -- the one shape
    the triage apply step writes."""
    return f"{notes}{_SEGMENT_SEPARATOR}{stamp}" if notes.strip() else stamp


def stamp_state(segments: tuple[str, ...]) -> StampState:
    """The row's latest stamp-shaped segment wins (finalize concatenates notes)."""
    for index in range(len(segments) - 1, -1, -1):
        if segments[index].startswith(STAMP_PREFIX):
            parsed = parse_stamp(segments[index], index)
            if isinstance(parsed, StampMalformed):
                return parsed
            return Judged(stamp=parsed, segment_index=index)
    return Unjudged()


def _parse_locations(cell: str) -> tuple[LocationRef, ...]:
    refs: list[LocationRef] = []
    for part in (piece.strip() for piece in cell.split(",")):
        if not part:
            continue
        path = re.sub(r":\d+(?:-\d+)?$", "", part)
        refs.append(PathRef(path, part) if "/" in path or "." in path else OpaqueRef(part))
    return tuple(refs)


def _parse_goal(kind: str, value: str) -> GoalRef:
    if kind == "code-quality":
        return NoGoal() if not value else MalformedGoal(kind, value, "code-quality-with-value")
    if kind == "adr":
        if value.startswith("dec-draft-"):
            return DraftGoal(value)
        if _DEC_ID.match(value):
            return AdrGoal(value)
        return MalformedGoal(kind, value, "adr-value-not-dec-id")
    if kind in _OTHER_GOAL_KINDS:
        return OtherGoal(kind, value) if value else MalformedGoal(kind, value, "empty-value")
    return MalformedGoal(kind, value, "off-enum-kind")


def _citations(goal: GoalRef, notes: str) -> tuple[DecisionCitation, ...]:
    cited = [DecisionCitation(goal.dec_id, "goal-ref")] if isinstance(goal, AdrGoal) else []
    seen = {citation.dec_id for citation in cited}
    for dec_id in _DEC_TOKEN.findall(notes):
        if dec_id not in seen:
            seen.add(dec_id)
            cited.append(DecisionCitation(dec_id, "notes"))
    return tuple(cited)


def _row_scope_withheld(
    row_id: str, goal: GoalRef, first_seen: date | None, refs: tuple[LocationRef, ...]
) -> tuple[Withheld, ...]:
    """Classes this one row cannot be judged on, and why."""
    withheld: list[Withheld] = []
    match goal:
        case OtherGoal(kind=kind):
            withheld.append(
                _row_withheld("goal-link-unresolved", f"goal-oracle-unsupported:{kind}", row_id)
            )
        case MalformedGoal(reason=reason):
            withheld.append(
                _row_withheld("goal-link-unresolved", f"goal-ref-malformed:{reason}", row_id)
            )
        case NoGoal() | AdrGoal() | DraftGoal():
            pass
        case _:
            assert_never(goal)
    if first_seen is None:
        withheld.append(_row_withheld("cited-by-commit", "first-seen-malformed", row_id))
    for ref in refs:
        if isinstance(ref, OpaqueRef):
            withheld.append(_row_withheld("location-decay", f"opaque-location:{ref.raw}", row_id))
    return tuple(withheld)


def _row_withheld(class_name: str, reason: str, row_id: str) -> Withheld:
    return Withheld(class_name, reason, "row", (row_id,))


def _key_facts(row: DataRow, resolved: Mapping[str, str], blocked: Mapping[str, str]) -> KeyFacts:
    written, base = row.value("dedup_key"), compute_dedup_key(row)
    correct = resolved.get(row.row_id, base)
    status: KeyStatus
    if row.row_id in blocked:
        status = "collision-blocked"
    elif written != correct:
        status = "nonconforming"
    elif correct != base:
        status = "discriminated"
    else:
        status = "plain"
    return KeyFacts(written=written, base=base, resolved=correct, status=status)


def _parse_active(row: DataRow, key: KeyFacts) -> ActiveRow:
    row_id = TdId(row.row_id)
    notes = row.value("notes")
    segments = split_segments(notes)
    goal = _parse_goal(row.value("goal-ref-type"), row.value("goal-ref-value"))
    first_seen = parse_iso_date(row.value("first-seen"))
    refs = _parse_locations(row.value("location"))
    return ActiveRow(
        id=row_id,
        status="open" if row.value("status") == "open" else "in-flight",
        klass=row.value("class"),
        severity=row.value("severity"),
        owner_role=row.value("owner-role"),
        direction=row.value("direction"),
        source=row.value("source"),
        locations=refs,
        goal=goal,
        first_seen=first_seen,
        last_seen=parse_iso_date(row.value("last-seen")),
        notes=notes,
        segments=segments,
        stamp=stamp_state(segments),
        cited_decisions=_citations(goal, notes),
        key=key,
        row_withheld=_row_scope_withheld(row_id, goal, first_seen, refs),
        line_no=row.line_no,
    )


def _parse_terminal(row: DataRow, key: KeyFacts) -> TerminalPeer:
    return TerminalPeer(
        id=TdId(row.row_id),
        status="resolved" if row.value("status") == "resolved" else "wontfix",
        klass=row.value("class"),
        base_key=key.base,
        locations=_parse_locations(row.value("location")),
        first_seen=parse_iso_date(row.value("first-seen")),
        last_seen=parse_iso_date(row.value("last-seen")),
        stamp=stamp_state(split_segments(row.value("notes"))),
    )


def _unparseable_reason(row: DataRow, legal: frozenset[str]) -> str | None:
    if row.table is None:
        return "outside-table"
    if len(row.cells) != len(row.table.columns):
        return f"field-count:{len(row.cells)}"
    if not _TD_ID.match(row.row_id):
        return "malformed-id"
    if row.value("status") not in legal:
        return f"status:{row.value('status')}"
    return None


def parse_rows(
    parsed: list[ParsedLedger],
) -> tuple[tuple[ActiveRow, ...], tuple[TerminalPeer, ...], tuple[UnparseableRow, ...]]:
    """Ledger pair -> typed rows, once, routed by each row's own status."""
    rows = dedup_rows(parsed)
    resolved, blocked = resolve_dedup_keys(rows), collision_blocked_ids(parsed)
    active: list[ActiveRow] = []
    terminal: list[TerminalPeer] = []
    unparseable: list[UnparseableRow] = []
    for ledger, legal in zip(parsed, _FILE_STATUSES, strict=True):
        for row in ledger.rows:
            reason = _unparseable_reason(row, legal)
            if reason is not None:
                unparseable.append(UnparseableRow(row.row_id, row.line_no, reason))
                continue
            key = _key_facts(row, resolved, blocked)
            if row.value("status") in _ACTIVE_STATUSES:
                active.append(_parse_active(row, key))
            else:
                terminal.append(_parse_terminal(row, key))
    return tuple(active), tuple(terminal), tuple(unparseable)


# -- Gather: the only reads of the world ------------------------------------------------

_EDGE_FIELDS = (
    "superseded_by",
    "retired_by",
    "superseded_in_part_by",
    "supersedes",
    "supersedes_in_part",
)
_RECORD_SEPARATOR, _FIELD_SEPARATOR = "\x1e", "\x1f"
_COMMIT_FORMAT = f"--format={_RECORD_SEPARATOR}%H{_FIELD_SEPARATOR}%as{_FIELD_SEPARATOR}%B{_FIELD_SEPARATOR}"  # author date: a rebase or merge moves the committer date past a row's filing day


def gather(repo_root: Path, today: date | None = None) -> StateSnapshot:
    """Read the ledger pair, the ADR corpus and git history once; never write.

    Raises `OSError` / `UnicodeDecodeError` when a ledger or ADR file exists but cannot be
    read -- the probe's one script error. Every other gap is an oracle withheld.
    """
    specs = [spec for spec in LEDGERS if spec.dedup_namespace == TECH_DEBT_NAMESPACE]
    active, terminal, unparseable = parse_rows([parse_ledger(repo_root, spec) for spec in specs])
    decisions = _load_decisions(repo_root)
    windows = [row.first_seen for row in active if row.first_seen is not None]
    stamp_shas = frozenset(
        row.stamp.stamp.anchor for row in active if isinstance(row.stamp, Judged)
    )
    git, history_gap = _gather_history(repo_root, min(windows) if windows else None, stamp_shas)
    has_history = git is not None
    lazy_shapes = load_expected_absent_shapes(repo_root)
    oracles: dict[Oracle, str | None] = {
        "git-history": history_gap,
        "adr-corpus": None if decisions else "no parseable ADR under .ai-state/decisions/",
        "lifecycle-table": None if lazy_shapes is not None else "artifact-inventory.md unreadable",
    }
    head = git_output(repo_root, "rev-parse", "HEAD") if has_history else None
    return StateSnapshot(
        repo_root=repo_root,
        today=today or date.today(),
        head=head,
        anchor=(git.merge_base if git else None) or head,
        active_rows=active,
        terminal_peers=terminal,
        unparseable=unparseable,
        decisions=decisions,
        git=git,
        lazy_shapes=tuple(lazy_shapes) if lazy_shapes is not None else None,
        present_paths=_present_paths(repo_root, active),
        oracles=oracles,
        withheld=_corpus_withheld(oracles),
    )


def _present_paths(repo_root: Path, rows: tuple[ActiveRow, ...]) -> frozenset[str]:
    """Which of the rows' location and notes-cited paths exist on disk right now."""
    referenced = {ref.path for row in rows for ref in row.locations if isinstance(ref, PathRef)}
    referenced |= {path for row in rows for _, path in notes_path_citations(row.notes)}
    return frozenset(path for path in referenced if (repo_root / path).exists())


def _corpus_withheld(oracles: Mapping[Oracle, str | None]) -> tuple[Withheld, ...]:
    """Every class whose oracle cannot answer, derived from `CLASS_ORACLES`."""
    withheld = []
    for class_name, needs in CLASS_ORACLES.items():
        reasons = [f"{oracle}: {oracles[oracle]}" for oracle in needs if oracles[oracle]]
        if reasons:
            withheld.append(Withheld(class_name, "; ".join(reasons), "corpus", ()))
    return tuple(withheld)


def _load_decisions(repo_root: Path) -> Mapping[str, DecisionFacts]:
    yaml_module = _try_import_yaml()
    facts: dict[str, DecisionFacts] = {}
    for path in discover_adr_files(repo_root):
        data = _frontmatter(path, yaml_module)
        dec_id = str(data.get("id", "")).strip() if data else ""
        if not data or not dec_id:
            continue
        facts[dec_id] = DecisionFacts(
            dec_id=dec_id,
            status=str(data.get("status", "")).strip(),
            date=str(data.get("date", "")).strip(),
            title=str(data.get("title", "")).strip(),
            summary=str(data.get("summary", "")).strip(),
            affected_files=tuple(_as_list(data.get("affected_files"))),
            edges={field: tuple(_as_list(data.get(field))) for field in _EDGE_FIELDS},
            path=path.relative_to(repo_root).as_posix(),
        )
    return facts


def _frontmatter(path: Path, yaml_module) -> dict | None:
    """One ADR's frontmatter mapping through `query_adrs`'s parse dispatch, or None."""
    found = _FRONTMATTER_RE.match(path.read_text(encoding="utf-8"))
    if not found:
        return None
    if yaml_module is None:
        data = _parse_frontmatter_fallback(found.group(1), path)
    else:
        try:
            data = yaml_module.safe_load(found.group(1))
        except yaml_module.YAMLError:
            data = None
    return data if isinstance(data, dict) else None


def _gather_history(
    repo_root: Path, since: date | None, stamp_shas: frozenset[str]
) -> tuple[GitFacts | None, str | None]:
    """Four whole-repository history reads plus the anchor machinery; never one per row.

    Returns the facts, or None plus the reason when any of the four core reads fails:
    a failed read is an unanswered oracle, never an empty history (a failed rename
    index would turn every move into a deletion, a failed log would read every row
    as untouched). The merge-base and per-anchor reads are additive on top of an
    already-successful core read, so their own failure degrades only the anchors
    that depend on them (see `_resolve_stamp_anchors`), never the whole snapshot.
    """
    if not history_available(repo_root):
        return None, "no git history, or a shallow clone"
    tree = git_output(repo_root, "ls-tree", "-r", "--name-only", "HEAD")
    renames = build_rename_index(repo_root, strict=True)
    deletions = build_deletion_index(repo_root, strict=True)
    commits = _commit_index(repo_root, since) if since is not None else ()
    if tree is None or renames is None or deletions is None or commits is None:
        reads = {"tree": tree, "renames": renames, "deletions": deletions, "commits": commits}
        failed = ", ".join(name for name, value in reads.items() if value is None)
        return None, f"git history read failed: {failed}"
    merge_base = _resolve_merge_base(repo_root)
    anchors, anchor_windows = _resolve_stamp_anchors(repo_root, stamp_shas)
    facts = GitFacts(
        frozenset(tree.splitlines()),
        renames,
        deletions,
        commits,
        merge_base,
        anchors,
        anchor_windows,
    )
    return facts, None


def _parse_commit_records(stdout: str) -> tuple[Commit, ...]:
    commits = []
    for record in stdout.split(_RECORD_SEPARATOR):
        fields = record.split(_FIELD_SEPARATOR)
        if len(fields) != 4:
            continue
        sha, day, body, paths = fields
        commits.append(
            Commit(
                sha=sha.strip(),
                date=date.fromisoformat(day.strip()),
                subject=body.strip().splitlines()[0] if body.strip() else "",
                td_ids=frozenset(_TD_TOKEN.findall(body)),
                paths=tuple(line for line in paths.splitlines() if line.strip()),
            )
        )
    return tuple(commits)


def _commit_index(repo_root: Path, since: date) -> tuple[Commit, ...] | None:
    try:
        result = run_git(
            repo_root, "log", f"--since={since.isoformat()}", _COMMIT_FORMAT, "--name-only", "HEAD"
        )
    except GitUnavailableError:
        return None
    if result.returncode != 0:
        return None
    return _parse_commit_records(result.stdout)


def _range_commit_index(repo_root: Path, since_sha: str) -> tuple[Commit, ...] | None:
    """`rev-list`-equivalent commit log for `since_sha..HEAD`: one read per distinct anchor."""
    try:
        result = run_git(
            repo_root, "log", f"{since_sha}..HEAD", _COMMIT_FORMAT, "--name-only", "HEAD"
        )
    except GitUnavailableError:
        return None
    if result.returncode != 0:
        return None
    return _parse_commit_records(result.stdout)


# -- Anchors: the stamp-with sha and every distinct row-stamp anchor ----------------------


def _default_branch(repo_root: Path) -> str | None:
    """The local default branch when it exists, else its remote-tracking ref.

    Local first: unpushed commits on the default branch are still the state a triage
    on that branch judges against, so the merge-base there must be HEAD itself.
    """
    ref = git_output(repo_root, "symbolic-ref", "refs/remotes/origin/HEAD")
    candidates = [ref.removeprefix("refs/remotes/origin/")] if ref else []
    for name in [*candidates, "main", "master"]:
        if git_output(repo_root, "rev-parse", "--verify", f"refs/heads/{name}") is not None:
            return name
    return ref


def _resolve_merge_base(repo_root: Path) -> str | None:
    """`git merge-base HEAD <default-branch>`: on the default branch this is HEAD.

    On a triage branch it is the branch point, a sha that survives a squash
    or rebase of that branch, so a stamp anchored to it stays resolvable.
    """
    branch = _default_branch(repo_root)
    return git_output(repo_root, "merge-base", "HEAD", branch) if branch else None


def _reachability(repo_root: Path, sha: str) -> Anchor:
    """Is `sha` an ancestor of HEAD? One `merge-base --is-ancestor` call, then its date."""
    try:
        check = run_git(repo_root, "merge-base", "--is-ancestor", sha, "HEAD")
    except GitUnavailableError:
        return Unanchored(sha, "unknown-object")
    if check.returncode == 1:
        return Unanchored(sha, "not-ancestor")
    if check.returncode != 0:
        return Unanchored(sha, "unknown-object")
    commit_date = git_output(repo_root, "show", "-s", "--format=%as", sha)
    parsed = parse_iso_date(commit_date) if commit_date else None
    return Anchored(sha, parsed) if parsed else Unanchored(sha, "unknown-object")


def _resolve_stamp_anchors(
    repo_root: Path, shas: frozenset[str]
) -> tuple[dict[str, Anchor], dict[str, AnchorWindow]]:
    """Per distinct stamp anchor: one reachability check, then (when reachable) one
    `ls-tree` and one `rev-list anchor..HEAD` -- never per row.

    A failed tree or commit read downgrades an otherwise-reachable anchor to
    `Unanchored` rather than silently building a window from partial data --
    the same "withhold, never read empty" discipline `_gather_history` already
    applies to the four corpus-wide indexes.
    """
    anchors: dict[str, Anchor] = {}
    windows: dict[str, AnchorWindow] = {}
    for sha in sorted(shas):
        anchor = _reachability(repo_root, sha)
        if isinstance(anchor, Anchored):
            tree = git_output(repo_root, "ls-tree", "-r", "--name-only", sha)
            range_commits = _range_commit_index(repo_root, sha)
            if tree is None or range_commits is None:
                anchor = Unanchored(sha, "unknown-object")
            else:
                windows[sha] = AnchorWindow(anchor, frozenset(tree.splitlines()), range_commits)
        anchors[sha] = anchor
    return anchors, windows
