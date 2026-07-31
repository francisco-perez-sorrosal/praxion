"""Fitness gate: the `.ai-state/CONSULT_*.md` family is append-only, and stays so.

Cites: CLAUDE.md§Context Engineering (the consult record is the durable memory of
what was challenged and how it was dispositioned -- a row rewritten or deleted
after the fact silently rewrites that memory, and every later reader inherits the
edited version as if it were the original). Per rules/swe/gate-liveness.md this is
a CODE-kind gate, so its proof is a canary that feeds a known-bad input and
asserts the gate flags it -- never a green run against the current tree.

The contract, verbatim from the three files themselves: "This file is append-only
-- no row is ever edited or deleted." All three declare it independently and none
sanctions any in-place mutation, so the gate needs no per-file exceptions.

The comparison baseline is `merge-base(origin/main, HEAD)`: the verdict is then a
function of the branch's *content* rather than of its push cadence. Two residuals
come with that choice and are accepted rather than hidden. (1) A row added in one
commit and rewritten in a later commit of the same branch shows up at the two
endpoints as a plain addition -- only walking every consecutive commit pair would
catch it. (2) On a push to `main` the merge-base collapses onto HEAD and the
comparison degrades to working-tree-vs-HEAD, which is still the shape that catches
an in-place edit before it is committed -- which is exactly how the live incident
that motivated this gate occurred.

**Deliberately NOT in scope: `.ai-state/TECH_DEBT_LEDGER.md` and
`.ai-state/TECH_DEBT_RESOLVED.md`.** They sit in the same directory and take the
same markdown-row shape, but carry the opposite contract: the ledger explicitly
sanctions in-place updates to `status` / `resolved-by` / `last-seen`, and terminal
rows migrate out of the file entirely into its sibling. Pointing this gate at them
would red every routine housekeeping commit. `consult_files()` is the single place
the file set is computed, and the exclusion is asserted mechanically below rather
than merely promised in this paragraph.

**Paired site:** `check_no_data_row_outside_table` in
`fitness/tests/test_discipline_registry_invariants.py` guards the neighbouring
defect -- a data row landing *outside* the parsed table. This gate does not depend
on it: `extract_data_rows` reads the whole file, so a row appended after the
trailing prose sections is inside this gate's comparison set either way. The two
are worth reading together whenever either one's scope changes.

**Known residual, stated rather than hidden:** because `extract_data_rows` is
whole-file by design, the pipe-delimited *documentation* grids in these files
(the `## Column Definitions` tables) are compared alongside the data rows, so
rewording a column definition reads as a mutation and trips this gate. That is the
price of the whole-file scope that closes the appended-after-prose blind spot. A
documentation edit that trips the gate is a stop-and-look, not a false alarm to be
suppressed by narrowing the scope back to a single parsed table.
"""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Scope and baseline definitions
# ---------------------------------------------------------------------------

#: The glob that defines the gate's entire file set, relative to `.ai-state/`.
CONSULT_GLOB = "CONSULT_*.md"

#: How the baseline revision is named in every operator-facing message.
BASELINE_REF_SPEC = "merge-base(origin/main, HEAD)"

#: The named reason an inert run reports. An unresolvable baseline must read as
#: "not evaluated", never as a green pass and never as a hard failure -- an
#: unanticipated history shape should cost an advisory skip, not a blocked branch.
BASELINE_SKIP_REASON = (
    f"baseline {BASELINE_REF_SPEC} is unresolvable or unreachable in this checkout "
    "(shallow clone, squash-merged branch, absent origin/main remote-tracking ref, "
    "or not a git checkout) -- the append-only comparison was SKIPPED, not passed"
)

# A markdown separator row: `|---|---|`, tolerating alignment colons and padding.
_SEPARATOR_RE = re.compile(r"^\|(?:\s*:?-{3,}:?\s*\|)+$")

# A fenced code block delimiter. These files embed shell pipelines whose
# continuation lines also begin with `|`; those are prose, not data rows.
_FENCE_RE = re.compile(r"^\s*(?:```|~~~)")

# Long rows are truncated in failure messages so the report stays readable while
# still naming the row uniquely.
_ROW_EXCERPT_LIMIT = 160


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


def extract_data_rows(text: str) -> list[str]:
    """Return every pipe-delimited data row in `text`, whitespace-normalised.

    A data row is any line whose first non-blank character is `|`, minus two
    exclusions: lines inside a fenced code block, and every markdown table header
    together with its `|---|` separator (identified positionally -- a separator
    line, plus the pipe line immediately above it).

    The unit is the whole file rather than one parsed table. That is what puts
    both of `CONSULT_PRIORS.md`'s two tables in scope without table-specific
    logic, and what keeps a row appended *after* the trailing prose sections
    inside the comparison set instead of invisible to it.
    """
    lines = text.splitlines()
    in_fence = False
    pipe_indices: list[int] = []
    for index, line in enumerate(lines):
        if _FENCE_RE.match(line):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        if line.strip().startswith("|"):
            pipe_indices.append(index)

    pipe_index_set = set(pipe_indices)
    excluded: set[int] = set()
    for index in pipe_indices:
        if not _SEPARATOR_RE.match(lines[index].strip()):
            continue
        excluded.add(index)
        if index - 1 in pipe_index_set:
            excluded.add(index - 1)

    return [lines[index].strip() for index in pipe_indices if index not in excluded]


def _excerpt(row: str) -> str:
    """Truncate a row for a failure message, keeping it identifiable."""
    if len(row) <= _ROW_EXCERPT_LIMIT:
        return row
    return row[:_ROW_EXCERPT_LIMIT] + " ..."


def check_rows_are_append_only(baseline_rows: list[str], working_rows: list[str]) -> list[str]:
    """Return one failure string per baseline row the working content lost.

    The working content honours the contract when the baseline rows all appear in
    it, byte-identical and in their original relative order -- that is, when the
    baseline is an ordered subsequence of the working rows. Anything else means a
    row was edited, deleted, or moved.

    New rows interleaved anywhere are clean: `CONSULT_PRIORS.md` carries two data
    tables, so "appended" is a per-table position, not a file-final one.
    """
    failures: list[str] = []
    cursor = 0
    for row in baseline_rows:
        try:
            position = working_rows.index(row, cursor)
        except ValueError:
            if row in working_rows:
                failures.append(f"row moved out of its baseline order: {_excerpt(row)}")
            else:
                failures.append(f"row edited or deleted since the baseline: {_excerpt(row)}")
            continue
        cursor = position + 1
    return failures


def consult_files(project_root: Path) -> list[Path]:
    """Return the `.ai-state/CONSULT_*.md` files this gate governs, sorted.

    This glob is the whole scope definition. `TECH_DEBT_LEDGER.md` and
    `TECH_DEBT_RESOLVED.md` share the directory and the row shape but carry the
    opposite contract, so they must never match -- see the module docstring.
    """
    return sorted((project_root / ".ai-state").glob(CONSULT_GLOB))


# ---------------------------------------------------------------------------
# Git-backed baseline resolution
# ---------------------------------------------------------------------------


def _git(project_root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    """Run a read-only git command inside `project_root`, never raising."""
    return subprocess.run(
        ["git", *args],
        cwd=project_root,
        capture_output=True,
        text=True,
        check=False,
    )


def resolve_baseline_revision(project_root: Path) -> str | None:
    """Return the baseline commit sha, or None when it cannot be relied on.

    None is returned both when `merge-base(origin/main, HEAD)` does not resolve
    (no git checkout, no origin/main remote-tracking ref, an orphan branch) and
    when the resolved sha is not a reachable commit (a shallow clone, or a
    squash-merged branch). Callers must treat None as "not evaluated" -- the
    reachability idiom mirrors the sealed-prior witness check already shipped in
    `fitness/tests/test_discipline_registry_invariants.py`.
    """
    merge_base = _git(project_root, "merge-base", "origin/main", "HEAD")
    if merge_base.returncode != 0:
        return None
    revision = merge_base.stdout.strip()
    if not revision:
        return None
    reachable = _git(project_root, "cat-file", "-e", f"{revision}^{{commit}}")
    if reachable.returncode != 0:
        return None
    return revision


def baseline_file_text(project_root: Path, revision: str, relative_path: str) -> str | None:
    """Return a file's content at `revision`, or None if it did not exist there.

    `revision` must already have been validated by `resolve_baseline_revision`;
    with a reachable commit in hand, a `git show` failure means one thing only --
    the path was not present at that commit, so every row in the working file is
    an addition.
    """
    show = _git(project_root, "show", f"{revision}:{relative_path}")
    if show.returncode != 0:
        return None
    return show.stdout


def check_consult_files_are_append_only(project_root: Path) -> list[str] | None:
    """Return one failure per lost row across the governed files, or None.

    None means the baseline could not be established, and is deliberately a
    *different* value from `[]` (clean): an unreachable baseline must never be
    indistinguishable from a verified-clean tree. Callers skip on None.
    """
    revision = resolve_baseline_revision(project_root)
    if revision is None:
        return None

    failures: list[str] = []
    for path in consult_files(project_root):
        relative_path = path.relative_to(project_root).as_posix()
        baseline_text = baseline_file_text(project_root, revision, relative_path)
        if baseline_text is None:
            continue  # the file is new since the baseline; every row is an addition
        lost_rows = check_rows_are_append_only(
            extract_data_rows(baseline_text),
            extract_data_rows(path.read_text(encoding="utf-8")),
        )
        failures.extend(f"{relative_path}: {failure}" for failure in lost_rows)
    return failures


# ---------------------------------------------------------------------------
# The real-repo gate
# ---------------------------------------------------------------------------


def test_the_real_consult_files_are_append_only_since_the_baseline(project_root: Path) -> None:
    """No row present in a real CONSULT_*.md at the baseline has been edited,
    deleted, or reordered in the working tree."""
    failures = check_consult_files_are_append_only(project_root)
    if failures is None:
        pytest.skip(BASELINE_SKIP_REASON)
    assert not failures, (
        f"append-only violations against {BASELINE_REF_SPEC} "
        "(rules/swe/gate-liveness.md; these files are append-only -- append a new "
        "row referencing the old one instead of rewriting it):\n  " + "\n  ".join(failures)
    )


def test_the_real_file_set_is_exactly_the_three_consult_files(project_root: Path) -> None:
    """The governed set is the three CONSULT_*.md files and nothing else.

    A fourth `.ai-state/CONSULT_*.md` file is automatically governed by the glob;
    this assertion exists so that adding one is a conscious act with a visible
    review checkpoint rather than a silent scope change.
    """
    names = [path.name for path in consult_files(project_root)]
    assert names == [
        "CONSULT_COSTS.md",
        "CONSULT_LEDGER.md",
        "CONSULT_PRIORS.md",
    ], f"unexpected governed file set: {names}"


def test_no_real_consult_file_compares_an_empty_row_set(project_root: Path) -> None:
    """Every governed file contributes at least one row to the comparison.

    Without this, an extraction that silently stopped matching rows would leave
    the gate permanently green: comparing nothing against nothing never fails.
    """
    empty = [
        path.name
        for path in consult_files(project_root)
        if not extract_data_rows(path.read_text(encoding="utf-8"))
    ]
    assert not empty, (
        "these governed files yielded zero comparable rows, so the append-only "
        f"comparison over them is vacuous: {empty}"
    )


def test_both_priors_tables_contribute_rows_to_the_comparison(project_root: Path) -> None:
    """CONSULT_PRIORS.md's two data tables are both inside the comparison set.

    The Sealed Priors table uses `P-NN` prior ids and the Challenge
    Classification table uses `CH-NN` challenge ids; seeing both in the extracted
    rows proves the whole-file rule reaches the second table, which a
    one-table-per-file parser would silently leave unchecked.
    """
    priors_path = project_root / ".ai-state" / "CONSULT_PRIORS.md"
    if not priors_path.is_file():
        pytest.skip("CONSULT_PRIORS.md does not exist yet")
    rows = extract_data_rows(priors_path.read_text(encoding="utf-8"))
    sealed_prior_rows = [row for row in rows if "| P-0" in row]
    classification_rows = [row for row in rows if "| CH-0" in row]
    assert sealed_prior_rows, "no Sealed Priors row reached the comparison set"
    assert classification_rows, "no Challenge Classification row reached the comparison set"


# ---------------------------------------------------------------------------
# Fixtures: real git repositories built in tmp_path
# ---------------------------------------------------------------------------

_LEDGER_HEADER = "| timestamp | task-slug | discipline | stage | challenge-id | disposition |"
_LEDGER_SEPARATOR = "|---|---|---|---|---|---|"

_ROW_A = "| 2026-07-30T17:05:00Z | task-a | statistician | architecture | CH-01 | switch-now |"
_ROW_B = (
    "| 2026-07-30T17:06:00Z | task-a | statistician | architecture | CH-02 | defer-with-rationale |"
)
_ROW_B_EDITED = (
    "| 2026-07-30T17:06:00Z | task-a | statistician | architecture | CH-02 | switch-now |"
)
_ROW_C = (
    "| 2026-07-31T09:00:00Z | task-b | evidence-appraiser | research | CH-01 | "
    "dismiss-with-rationale |"
)


def _ledger_document(*rows: str) -> str:
    """Build a minimal CONSULT_LEDGER.md-shaped document around `rows`."""
    body = "\n".join([_LEDGER_HEADER, _LEDGER_SEPARATOR, *rows])
    return f"# Consultation Disposition Ledger\n\nThis file is append-only.\n\n{body}\n"


def _git_env() -> dict[str, str]:
    """Environment for fixture git calls: no global/system config, fixed identity."""
    return os.environ | {
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_CONFIG_SYSTEM": os.devnull,
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_AUTHOR_NAME": "Fixture",
        "GIT_AUTHOR_EMAIL": "fixture@example.invalid",
        "GIT_COMMITTER_NAME": "Fixture",
        "GIT_COMMITTER_EMAIL": "fixture@example.invalid",
    }


def _run_git(repo: Path, *args: str) -> None:
    """Run a git command in the fixture repo, asserting it succeeded."""
    result = subprocess.run(
        ["git", *args],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
        env=_git_env(),
    )
    assert result.returncode == 0, f"fixture `git {' '.join(args)}` failed: {result.stderr}"


def _write_ledger(repo: Path, text: str) -> None:
    (repo / ".ai-state" / "CONSULT_LEDGER.md").write_text(text, encoding="utf-8")


def _make_repo_with_baseline(tmp_path: Path, ledger_text: str) -> Path:
    """Create a git repo whose merge-base(origin/main, HEAD) holds `ledger_text`.

    `origin/main` is planted as a local remote-tracking ref, so the fixture
    exercises the real baseline resolution path without any network.
    """
    repo = tmp_path / "repo"
    (repo / ".ai-state").mkdir(parents=True)
    _run_git(repo, "init", "--quiet")
    _run_git(repo, "symbolic-ref", "HEAD", "refs/heads/main")
    _write_ledger(repo, ledger_text)
    _run_git(repo, "add", "-A")
    _run_git(repo, "commit", "--quiet", "-m", "baseline consult ledger")
    _run_git(repo, "update-ref", "refs/remotes/origin/main", "HEAD")
    _run_git(repo, "checkout", "--quiet", "-b", "feature")
    return repo


def _commit_ledger(repo: Path, ledger_text: str, message: str) -> None:
    _write_ledger(repo, ledger_text)
    _run_git(repo, "commit", "--quiet", "-a", "-m", message)


# ---------------------------------------------------------------------------
# Canaries: the gate bites on each known-bad shape
# ---------------------------------------------------------------------------


def test_flags_a_row_edited_in_place_mid_branch(tmp_path: Path) -> None:
    """Canary: a row rewritten in the middle commit of a three-commit branch is
    flagged, even though the final commit leaves it untouched.

    This is the shape a previous-commit baseline misses and the merge-base
    baseline catches: at HEAD~1 the row already carries its rewritten value.
    """
    repo = _make_repo_with_baseline(tmp_path, _ledger_document(_ROW_A, _ROW_B))
    _commit_ledger(repo, _ledger_document(_ROW_A, _ROW_B_EDITED), "rewrite CH-02's disposition")
    _commit_ledger(repo, _ledger_document(_ROW_A, _ROW_B_EDITED, _ROW_C), "append a new row")

    failures = check_consult_files_are_append_only(repo)

    assert failures, "an in-place row edit must be flagged; got no failures (the gate is inert)"
    assert any(
        "CH-02" in failure for failure in failures
    ), f"the failure must name the rewritten row; got: {failures}"


def test_flags_a_row_deleted_since_the_baseline(tmp_path: Path) -> None:
    """Canary: a row present at the baseline and dropped from the working tree is
    flagged -- deletion is the second violation shape, distinct from an edit."""
    repo = _make_repo_with_baseline(tmp_path, _ledger_document(_ROW_A, _ROW_B))
    _commit_ledger(repo, _ledger_document(_ROW_A), "drop CH-02")

    failures = check_consult_files_are_append_only(repo)

    assert failures, "a deleted row must be flagged; got no failures (the gate is inert)"
    assert any(
        "CH-02" in failure for failure in failures
    ), f"the failure must name the deleted row; got: {failures}"


def test_flags_an_uncommitted_in_place_edit_in_the_working_tree(tmp_path: Path) -> None:
    """Canary: the gate reads the working tree, so a mutation is flagged before it
    is ever committed -- which is how the live incident would have been caught."""
    repo = _make_repo_with_baseline(tmp_path, _ledger_document(_ROW_A, _ROW_B))
    _write_ledger(repo, _ledger_document(_ROW_A, _ROW_B_EDITED))

    failures = check_consult_files_are_append_only(repo)

    assert failures, "an uncommitted in-place edit must be flagged; got no failures"


def test_flags_rows_reordered_since_the_baseline() -> None:
    """Canary: two baseline rows swapped, none lost, is still a violation -- the
    ledger's order is part of the record, not an incidental detail."""
    failures = check_rows_are_append_only([_ROW_A, _ROW_B], [_ROW_B, _ROW_A])

    assert failures, "reordered baseline rows must be flagged; got no failures"
    assert any(
        "moved out of its baseline order" in failure for failure in failures
    ), f"the failure must name reordering as the cause; got: {failures}"


def test_flags_an_edit_to_a_row_that_sits_after_the_trailing_prose() -> None:
    """Canary: a row that landed after the trailing prose sections -- outside any
    parsed table -- is still inside the comparison set, so editing it is flagged.

    This is the previously-demonstrated blind spot: an end-of-file row is
    invisible to every table-scoped counting recipe. Whole-file extraction is
    what closes it.
    """
    stray_row = (
        "| 2026-08-01T09:00:00Z | task-c | statistician | architecture | CH-99 | switch-now |"
    )
    stray_row_edited = (
        "| 2026-08-01T09:00:00Z | task-c | statistician | architecture | CH-99 | "
        "dismiss-with-rationale |"
    )
    prose = "\n## Column Definitions\n\nSome trailing prose.\n\n## Single Writer\n\nMore prose.\n\n"
    baseline_text = _ledger_document(_ROW_A) + prose + stray_row + "\n"
    working_text = _ledger_document(_ROW_A) + prose + stray_row_edited + "\n"

    failures = check_rows_are_append_only(
        extract_data_rows(baseline_text),
        extract_data_rows(working_text),
    )

    assert failures, (
        "editing a row that sits after the trailing prose must be flagged; got no "
        "failures (the whole-file scope is not reaching it)"
    )


def test_flags_an_edit_in_the_second_of_two_tables() -> None:
    """Canary: a file with two data tables has both compared -- an edit confined
    to the second table is flagged, not silently unchecked."""
    second_header = "| timestamp | task-slug | prior-id | concern |"
    second_row = "| 2026-07-31T05:25:00Z | task-a | P-01 | no minimum detectable effect |"
    second_row_edited = "| 2026-07-31T05:25:00Z | task-a | P-01 | a rewritten concern |"
    second_table = f"\n## Sealed Priors\n\n{second_header}\n|---|---|---|---|\n"
    baseline_text = _ledger_document(_ROW_A) + second_table + second_row + "\n"
    working_text = _ledger_document(_ROW_A) + second_table + second_row_edited + "\n"

    failures = check_rows_are_append_only(
        extract_data_rows(baseline_text),
        extract_data_rows(working_text),
    )

    assert failures, "an edit in the second table must be flagged; got no failures"


def test_an_unresolvable_baseline_never_reads_as_a_clean_pass(tmp_path: Path) -> None:
    """Canary: outside a git checkout the gate reports "not evaluated" (None), a
    value the caller cannot mistake for the empty failure list of a clean tree."""
    result = check_consult_files_are_append_only(tmp_path)

    assert result is None, (
        "an unresolvable baseline must return None, distinguishable from [] (clean); "
        f"got: {result!r}"
    )
    assert resolve_baseline_revision(tmp_path) is None


def test_a_repo_without_origin_main_reports_a_missing_baseline(tmp_path: Path) -> None:
    """Canary: a real git repo that has no `origin/main` remote-tracking ref
    resolves no baseline -- the shape a fresh clone of a fork takes."""
    repo = tmp_path / "repo"
    (repo / ".ai-state").mkdir(parents=True)
    _run_git(repo, "init", "--quiet")
    _write_ledger(repo, _ledger_document(_ROW_A))
    _run_git(repo, "add", "-A")
    _run_git(repo, "commit", "--quiet", "-m", "initial")

    assert resolve_baseline_revision(repo) is None


def test_the_computed_file_set_excludes_the_tech_debt_ledger_pair(tmp_path: Path) -> None:
    """The tech-debt ledger pair is never governed by this gate.

    Both files sit in `.ai-state/` and take the same row shape, but they sanction
    in-place `status` / `resolved-by` / `last-seen` updates and migrate terminal
    rows out of the file -- routine housekeeping this gate would otherwise red on
    every commit.
    """
    state = tmp_path / ".ai-state"
    state.mkdir()
    for name in (
        "CONSULT_LEDGER.md",
        "CONSULT_COSTS.md",
        "CONSULT_PRIORS.md",
        "TECH_DEBT_LEDGER.md",
        "TECH_DEBT_RESOLVED.md",
    ):
        (state / name).write_text(_ledger_document(_ROW_A), encoding="utf-8")

    names = [path.name for path in consult_files(tmp_path)]

    assert names == [
        "CONSULT_COSTS.md",
        "CONSULT_LEDGER.md",
        "CONSULT_PRIORS.md",
    ], f"consult_files() must return exactly the CONSULT_*.md files; got: {names}"
    assert "TECH_DEBT_LEDGER.md" not in names, (
        "TECH_DEBT_LEDGER.md sanctions in-place status/resolved-by/last-seen edits -- "
        "governing it with the append-only contract would red routine housekeeping"
    )
    assert "TECH_DEBT_RESOLVED.md" not in names, (
        "TECH_DEBT_RESOLVED.md receives rows migrated out of the active ledger -- "
        "its row set legitimately grows by relocation, not by append-only writes"
    )


# ---------------------------------------------------------------------------
# No-op controls: the sanctioned write path stays frictionless
# ---------------------------------------------------------------------------


def test_appending_rows_only_is_accepted(tmp_path: Path) -> None:
    """No-op control: a branch that only appends rows produces no failures."""
    repo = _make_repo_with_baseline(tmp_path, _ledger_document(_ROW_A, _ROW_B))
    _commit_ledger(repo, _ledger_document(_ROW_A, _ROW_B, _ROW_C), "append a new disposition")

    failures = check_consult_files_are_append_only(repo)

    assert failures == [], f"a pure append must produce no failures; got: {failures}"


def test_an_untouched_branch_is_accepted(tmp_path: Path) -> None:
    """No-op control: a branch that changes nothing produces no failures."""
    repo = _make_repo_with_baseline(tmp_path, _ledger_document(_ROW_A, _ROW_B))

    failures = check_consult_files_are_append_only(repo)

    assert failures == [], f"an untouched branch must produce no failures; got: {failures}"


def test_a_row_inserted_into_an_earlier_table_is_accepted() -> None:
    """No-op control: with two tables, appending to the first one inserts a row
    mid-file -- ordered-subsequence matching accepts it, as it must."""
    later_row = "| 2026-07-31T05:25:00Z | task-a | P-01 | a sealed concern |"
    baseline_rows = [_ROW_A, later_row]
    working_rows = [_ROW_A, _ROW_B, later_row]

    failures = check_rows_are_append_only(baseline_rows, working_rows)

    assert failures == [], f"a mid-file insertion must be accepted; got: {failures}"


# ---------------------------------------------------------------------------
# Row extraction: what counts as a data row
# ---------------------------------------------------------------------------


def test_extraction_drops_table_headers_and_separators() -> None:
    """Headers and their `|---|` separators are structure, not data."""
    rows = extract_data_rows(_ledger_document(_ROW_A, _ROW_B))

    assert rows == [_ROW_A, _ROW_B], f"only the data rows must survive extraction; got: {rows}"


def test_extraction_ignores_pipe_lines_inside_fenced_code_blocks() -> None:
    """Shell-pipeline continuation lines inside a fence are prose, not rows.

    All three files embed `grep`/`cut`/`awk` recipes whose continuation lines
    begin with `|`; sweeping them in would red the gate whenever a recipe is
    revised, which the append-only contract says nothing about.
    """
    document = (
        _ledger_document(_ROW_A) + "\n## Falsifier\n\n```bash\ngrep '^|' file.md \\\n"
        "  | cut -d'|' -f6 \\\n  | sort -u\n```\n"
    )

    rows = extract_data_rows(document)

    assert rows == [_ROW_A], f"fenced pipe lines must not be treated as rows; got: {rows}"
