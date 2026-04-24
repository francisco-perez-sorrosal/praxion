"""GitCollector — hard-floor git metrics (churn, entropy, coupling, ownership, truck factor).

``GitCollector`` is the only collector with ``required = True``: the runner
aborts the whole report if git is not available. Every downstream namespace
(hot-spot composition, trends, report renderer) depends on at least one
field this collector emits, so silently degrading would produce a
report that is structurally incomplete.

Metrics emitted in the ``data`` payload:

* ``churn_90d`` — dict[path -> lines_added + lines_deleted] over the window.
* ``churn_total_90d`` — scalar sum of per-file churn.
* ``change_entropy_90d`` — summed Hassan (2009) Shannon entropy across
  in-window commits. Each commit contributes ``H = -Σ p_i * log2(p_i)``
  where ``p_i`` is the fraction of lines touched in file ``i``.
* ``change_coupling`` — list of pairs co-changing in ``>= 3`` commits,
  sorted descending by ``cochange_count`` with tie-break by ``(file_a, file_b)``.
* ``ownership`` — per-file Bird (2011) major/minor breakdown. Major
  contributors are authors with ``>= 5%`` of added lines to that file.
* ``truck_factor`` — Avelino (2016) greedy author removal until fewer
  than 50% of files retain a major owner.
* ``age_days`` — dict[path -> days since first commit], relative to a
  reference clock (``PROJECT_METRICS_REFERENCE_TIME`` env var or
  ``datetime.now(UTC)``).
* ``file_count`` — number of distinct files touched in the window.
* ``churn_source`` — ``"numstat"`` when ``git log --numstat`` yields
  authoritative line counts, or ``"commit_count_fallback"`` when the
  repo is shallow-cloned and numstat is unavailable.

The collector is deterministic given the same ``CollectionContext`` and
reference time — iteration order over dicts is stable since Python 3.7,
and every sort key in the output payload is explicit.
"""

from __future__ import annotations

import math
import os
import shutil
import subprocess
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from scripts.project_metrics.collectors.base import (
    Available,
    CollectionContext,
    Collector,
    CollectorResult,
    ResolutionEnv,
    ResolutionResult,
    Unavailable,
)

__all__ = ["GitCollector"]


# ---------------------------------------------------------------------------
# Tunables — named so tests and future collectors can reference them.
# ---------------------------------------------------------------------------

_COUPLING_THRESHOLD: int = 3
_MAJOR_OWNER_MIN_PCT: float = 0.05
_TRUCK_FACTOR_COVERAGE_THRESHOLD: float = 0.5
_GIT_SUBPROCESS_TIMEOUT_SECONDS: float = 30.0
_REFERENCE_TIME_ENV_VAR: str = "PROJECT_METRICS_REFERENCE_TIME"


# ---------------------------------------------------------------------------
# Parsed-commit record — intermediate representation between `git log` output
# and the metric functions below.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _Commit:
    """One parsed commit: SHA, author, timestamp, and per-file line-change pairs.

    ``file_changes`` maps ``path -> (added, deleted)``. When numstat is
    unavailable (shallow clones), ``file_changes`` maps ``path -> (0, 0)``
    and the caller substitutes commit-count churn via ``churn_source``.
    """

    sha: str
    author: str
    author_timestamp: int
    file_changes: dict[str, tuple[int, int]]


# ---------------------------------------------------------------------------
# GitCollector — the class wired into the runner registry.
# ---------------------------------------------------------------------------


class GitCollector(Collector):
    """Hard-floor git metrics (churn, entropy, coupling, ownership, truck factor)."""

    name = "git"
    tier = 0
    required = True
    languages: frozenset[str] = frozenset()

    def __init__(self, repo_root: Path | str | None = None) -> None:
        """Store the repo root used by :meth:`resolve`.

        ``None`` defers the decision to resolve time: the repo root becomes
        ``Path.cwd()`` at that moment. This matches test conventions where
        the test ``chdir``s into a fixture before calling ``resolve()``.
        Collection-time uses :attr:`CollectionContext.repo_root`, which is
        always passed explicitly by the runner.
        """

        self._configured_repo_root: Path | None = (
            Path(repo_root) if repo_root is not None else None
        )

    # ------------------------------------------------------------------ resolve

    def resolve(self, env: ResolutionEnv) -> ResolutionResult:
        """Probe for the ``git`` binary and an enclosing work tree.

        ``env`` is accepted per the Collector protocol but unused — `shutil.which`
        is called at module scope so tests can patch it via the collector's
        import site, matching the convention established by the other
        collectors (scc, lizard, complexipy, pydeps, coverage).
        """

        del env  # unused — see docstring
        repo_root = self._configured_repo_root or Path.cwd()

        git_path = shutil.which("git")
        if git_path is None:
            return Unavailable(
                reason="git binary not found on PATH",
                install_hint="Install git from https://git-scm.com/ or your package manager.",
            )

        try:
            completed = subprocess.run(
                ["git", "rev-parse", "--is-inside-work-tree"],
                cwd=str(repo_root),
                capture_output=True,
                text=True,
                check=False,
                timeout=_GIT_SUBPROCESS_TIMEOUT_SECONDS,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
            return Unavailable(
                reason=f"git rev-parse failed: {exc!r}",
                install_hint="Ensure git is reachable and the working tree is accessible.",
            )

        if completed.returncode != 0 or completed.stdout.strip() != "true":
            return Unavailable(
                reason=f"not inside a git work tree at {repo_root}",
                install_hint="Run /project-metrics from within a git repository.",
            )

        version = _resolve_git_version()
        return Available(
            version=version,
            details={"binary": git_path, "repo_root": str(repo_root)},
        )

    # ------------------------------------------------------------------ collect

    def collect(self, ctx: CollectionContext) -> CollectorResult:
        """Run ``git log --numstat`` over the window and compute every metric."""

        repo_root = Path(ctx.repo_root)
        reference_time = _resolve_reference_time()
        issues: list[str] = []

        is_shallow = _is_shallow_repository(repo_root)
        commits = _run_git_log(repo_root, ctx.window_days)
        churn_source = "numstat"
        if is_shallow:
            churn_source = "commit_count_fallback"
            issues.append(
                "shallow clone detected; churn falls back to commit count because "
                "numstat is unavailable."
            )

        churn_per_file = _compute_churn_per_file(commits, churn_source)
        churn_total = sum(churn_per_file.values())
        change_entropy = _compute_change_entropy(commits)
        change_coupling = _compute_change_coupling(commits)
        ownership = _compute_ownership(commits)
        truck_factor = _compute_truck_factor(ownership)
        age_days = _compute_age_days(commits, reference_time)
        file_count = len(churn_per_file)

        status = "partial" if issues else "ok"
        data = {
            "churn_90d": churn_per_file,
            "churn_total_90d": churn_total,
            "change_entropy_90d": change_entropy,
            "change_coupling": change_coupling,
            "ownership": ownership,
            "truck_factor": truck_factor,
            "age_days": age_days,
            "file_count": file_count,
            "churn_source": churn_source,
        }
        return CollectorResult(status=status, data=data, issues=issues)


# ---------------------------------------------------------------------------
# Subprocess helpers.
# ---------------------------------------------------------------------------


def _resolve_git_version() -> str:
    """Return ``git --version`` stripped of its ``git version`` prefix.

    Failure here is tolerated — we still report the binary as available
    because ``rev-parse`` already succeeded.
    """

    try:
        completed = subprocess.run(
            ["git", "--version"],
            capture_output=True,
            text=True,
            check=False,
            timeout=_GIT_SUBPROCESS_TIMEOUT_SECONDS,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return ""
    raw = completed.stdout.strip()
    prefix = "git version "
    if raw.startswith(prefix):
        return raw[len(prefix) :]
    return raw


def _is_shallow_repository(repo_root: Path) -> bool:
    """Detect shallow clones via ``git rev-parse --is-shallow-repository``."""

    completed = subprocess.run(
        ["git", "rev-parse", "--is-shallow-repository"],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
        check=False,
        timeout=_GIT_SUBPROCESS_TIMEOUT_SECONDS,
    )
    return completed.stdout.strip() == "true"


def _run_git_log(repo_root: Path, window_days: int) -> list[_Commit]:
    """Run ``git log`` with pinned formatting and return parsed commits.

    Format emits one block per commit in four lines followed by numstat
    rows and a blank line separator. The parser below reconstructs the
    ``_Commit`` list from that shape.
    """

    pretty = "--pretty=format:__PM_COMMIT__%n%H%n%an%n%at%n"
    completed = subprocess.run(
        [
            "git",
            "log",
            f"--since={window_days} days ago",
            "--numstat",
            pretty,
        ],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
        check=False,
        timeout=_GIT_SUBPROCESS_TIMEOUT_SECONDS,
    )
    if completed.returncode != 0:
        raise subprocess.CalledProcessError(
            completed.returncode,
            completed.args,
            output=completed.stdout,
            stderr=completed.stderr,
        )
    return _parse_git_log(completed.stdout)


def _parse_git_log(raw: str) -> list[_Commit]:
    """Parse the custom ``git log`` output into ``_Commit`` records.

    Each commit block starts with the ``__PM_COMMIT__`` sentinel followed
    by SHA, author name, and author unix timestamp. Numstat rows are
    ``added<TAB>deleted<TAB>path``. Binary files emit ``-<TAB>-<TAB>path``
    and count as zero lines.
    """

    commits: list[_Commit] = []
    blocks = raw.split("__PM_COMMIT__\n")
    for block in blocks:
        stripped = block.strip("\n")
        if not stripped:
            continue
        lines = stripped.split("\n")
        if len(lines) < 3:
            continue
        sha = lines[0].strip()
        author = lines[1].strip()
        try:
            author_ts = int(lines[2].strip())
        except ValueError:
            continue
        file_changes: dict[str, tuple[int, int]] = {}
        for line in lines[3:]:
            parsed = _parse_numstat_line(line)
            if parsed is None:
                continue
            path, added, deleted = parsed
            file_changes[path] = (added, deleted)
        commits.append(
            _Commit(
                sha=sha,
                author=author,
                author_timestamp=author_ts,
                file_changes=file_changes,
            )
        )
    return commits


def _parse_numstat_line(line: str) -> tuple[str, int, int] | None:
    """Parse a single numstat row; return ``None`` when the line is blank/invalid."""

    stripped = line.strip()
    if not stripped:
        return None
    parts = stripped.split("\t")
    if len(parts) != 3:
        return None
    added_raw, deleted_raw, path = parts
    added = 0 if added_raw == "-" else _safe_int(added_raw)
    deleted = 0 if deleted_raw == "-" else _safe_int(deleted_raw)
    return path, added, deleted


def _safe_int(value: str) -> int:
    """Parse ``value`` as int, defaulting to 0 on malformed input."""

    try:
        return int(value)
    except ValueError:
        return 0


# ---------------------------------------------------------------------------
# Reference-clock resolution.
# ---------------------------------------------------------------------------


def _resolve_reference_time() -> datetime:
    """Parse the reference time from env or fall back to ``now(UTC)``."""

    raw = os.environ.get(_REFERENCE_TIME_ENV_VAR)
    if not raw:
        return datetime.now(timezone.utc)
    # fromisoformat since 3.11 accepts the trailing "Z".
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return datetime.now(timezone.utc)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


# ---------------------------------------------------------------------------
# Metric computations — each takes parsed ``_Commit`` records and returns a
# JSON-native value suitable for the collector ``data`` payload.
# ---------------------------------------------------------------------------


def _compute_churn_per_file(
    commits: list[_Commit], churn_source: str
) -> dict[str, int]:
    """Sum per-file churn. Under the commit-count fallback, count commits instead of lines."""

    per_file: dict[str, int] = defaultdict(int)
    if churn_source == "commit_count_fallback":
        for commit in commits:
            for path in commit.file_changes:
                per_file[path] += 1
    else:
        for commit in commits:
            for path, (added, deleted) in commit.file_changes.items():
                per_file[path] += added + deleted
    return dict(sorted(per_file.items()))


def _compute_change_entropy(commits: list[_Commit]) -> float:
    """Sum Hassan per-commit Shannon entropy.

    Each commit contributes ``-Σ p_i * log2(p_i)`` with ``p_i`` = lines
    touched in file ``i`` / total lines touched in that commit. A single
    file (or a commit with zero lines touched) contributes 0.0 bits.
    """

    total = 0.0
    for commit in commits:
        lines_per_file = [
            added + deleted for added, deleted in commit.file_changes.values()
        ]
        commit_total = sum(lines_per_file)
        if commit_total <= 0:
            continue
        for lines in lines_per_file:
            if lines <= 0:
                continue
            probability = lines / commit_total
            total -= probability * math.log2(probability)
    return total


def _compute_change_coupling(commits: list[_Commit]) -> dict[str, object]:
    """Count file pairs co-changing and emit those meeting the threshold.

    Output shape::

        {
          "pairs": [{"files": ["a.py", "b.py"], "count": 4}, ...],
          "threshold": 3,
        }

    ``pairs`` is sorted descending by ``count`` with tie-break by the
    sorted pair (ascending), so iteration order is deterministic.
    """

    pair_counts: dict[tuple[str, str], int] = defaultdict(int)
    for commit in commits:
        files = sorted(commit.file_changes)
        for i, left in enumerate(files):
            for right in files[i + 1 :]:
                pair_counts[(left, right)] += 1
    qualifying = [
        (pair, count)
        for pair, count in pair_counts.items()
        if count >= _COUPLING_THRESHOLD
    ]
    qualifying.sort(key=lambda item: (-item[1], item[0]))
    return {
        "pairs": [
            {"files": [pair[0], pair[1]], "count": count} for pair, count in qualifying
        ],
        "threshold": _COUPLING_THRESHOLD,
    }


def _compute_ownership(
    commits: list[_Commit],
) -> dict[str, dict[str, object]]:
    """Bird per-file major/minor ownership over added lines.

    Produces::

        {
          "<file>": {
            "top_author": "<name>",
            "top_author_pct": <float 0.0-1.0>,
            "major": [["<name>", <pct>], ...],
            "minor": [["<name>", <pct>], ...],
          },
          ...
        }

    ``top_author_pct`` is fractional (0.80 for 80 %, not 80). Author
    entries in ``major`` / ``minor`` are ``[name, pct]`` pairs sorted
    descending by pct with tie-break by author name. The singular
    ``major`` / ``minor`` key names mirror the Bird (2011) convention
    and match the shape referenced by the test suite.
    """

    added_per_file: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for commit in commits:
        for path, (added, _deleted) in commit.file_changes.items():
            if added <= 0:
                continue
            added_per_file[path][commit.author] += added

    ownership: dict[str, dict[str, object]] = {}
    for path in sorted(added_per_file):
        author_totals = added_per_file[path]
        total_added = sum(author_totals.values())
        if total_added <= 0:
            continue
        ranked = sorted(
            author_totals.items(),
            key=lambda item: (-item[1], item[0]),
        )
        major: list[list[object]] = []
        minor: list[list[object]] = []
        for author, lines in ranked:
            pct = lines / total_added
            entry: list[object] = [author, pct]
            if pct >= _MAJOR_OWNER_MIN_PCT:
                major.append(entry)
            else:
                minor.append(entry)
        top_author, top_lines = ranked[0]
        ownership[path] = {
            "top_author": top_author,
            "top_author_pct": top_lines / total_added,
            "major": major,
            "minor": minor,
        }
    return ownership


def _compute_truck_factor(ownership: dict[str, dict[str, object]]) -> int:
    """Avelino greedy-remove authors until fewer than 50% of files retain a major owner.

    Empty ownership (no files have contributors) returns 1 — the degenerate
    "one commit, one file" baseline matches the empty-repo golden value.
    """

    if not ownership:
        return 1

    file_majors: dict[str, set[str]] = {
        path: set(_major_names(entry.get("major", [])))
        for path, entry in ownership.items()
    }

    author_contribution: dict[str, float] = defaultdict(float)
    for entry in ownership.values():
        for name, pct in _major_pairs(entry.get("major", [])):
            author_contribution[name] += pct

    removed: set[str] = set()
    total_files = len(file_majors)
    while True:
        covered = sum(1 for majors in file_majors.values() if majors - removed)
        if covered / total_files < _TRUCK_FACTOR_COVERAGE_THRESHOLD:
            return len(removed)
        remaining_authors = [
            author for author in author_contribution if author not in removed
        ]
        if not remaining_authors:
            # No further authors to remove, but coverage still >= 50% —
            # return the count that fully uncovered the repo.
            return len(removed)
        remaining_authors.sort(
            key=lambda author: (-author_contribution[author], author)
        )
        removed.add(remaining_authors[0])


def _major_pairs(value: object) -> list[tuple[str, float]]:
    """Decode a ``major`` cell into ``(name, pct)`` tuples."""

    if not isinstance(value, list):
        return []
    pairs: list[tuple[str, float]] = []
    for item in value:
        if isinstance(item, (list, tuple)) and len(item) >= 2:
            pairs.append((str(item[0]), float(item[1])))
    return pairs


def _major_names(value: object) -> list[str]:
    """Decode the name component of each ``major`` entry."""

    return [name for name, _pct in _major_pairs(value)]


def _compute_age_days(
    commits: list[_Commit], reference_time: datetime
) -> dict[str, int]:
    """Days between each file's first commit and the reference clock.

    Both ends are floored to their UTC date so the result matches
    calendar-day arithmetic (the fixture spec's golden values use
    date-level subtraction, not timestamp-level).
    """

    first_seen: dict[str, int] = {}
    for commit in commits:
        for path in commit.file_changes:
            prior = first_seen.get(path)
            if prior is None or commit.author_timestamp < prior:
                first_seen[path] = commit.author_timestamp

    reference_date = reference_time.astimezone(timezone.utc).date()
    age: dict[str, int] = {}
    for path, ts in sorted(first_seen.items()):
        commit_date = datetime.fromtimestamp(ts, tz=timezone.utc).date()
        age[path] = (reference_date - commit_date).days
    return age
