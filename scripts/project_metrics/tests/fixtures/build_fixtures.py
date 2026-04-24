"""Re-buildable fixture generator for GitCollector tests.

Creates five deterministic git fixture repos under this directory:

* ``minimal_repo/`` — 10 commits, 4 files, 3 authors; the canonical fixture
  against which every golden value in ``FIXTURE_SPEC.md`` is pinned.
* ``empty_repo/`` — initial-commit-only baseline.
* ``single_author_repo/`` — 5 commits by one author, truck factor = 1.
* ``coupling_repo/`` — 6 commits, two files co-changing in every commit,
  exercising the change-coupling threshold.
* ``minimal_stdlib_repo/`` — 3 commits, 2 Python files, used by the
  end-to-end integration test that hides optional tools (``uvx``, ``scc``,
  ``npx``) from ``PATH`` to exercise the stdlib-only code path.

Every commit pins both ``GIT_AUTHOR_DATE`` and ``GIT_COMMITTER_DATE`` so the
SHAs are deterministic across machines. Running this script a second time
blows away the existing ``.git/`` + working-tree files and rebuilds from
scratch — the fixtures are a rebuildable artifact, not hand-crafted state.

Usage::

    python3 scripts/project_metrics/tests/fixtures/build_fixtures.py

After running, verify the golden values per ``FIXTURE_SPEC.md`` before
running pytest.
"""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

_FIXTURES_DIR = Path(__file__).resolve().parent

_ALICE = ("Alice Smith", "alice@example.test")
_BOB = ("Bob Jones", "bob@example.test")
_CAROL = ("Carol Lee", "carol@example.test")


@dataclass(frozen=True)
class _Commit:
    """A single scripted commit — author identity, UTC timestamp, message, and files.

    ``files`` maps relative paths to their full post-commit content. The
    builder rewrites each file completely for each commit, which is simpler
    than diff-based construction and produces exact, predictable numstat
    values: lines-added counts the new content's line count; lines-deleted
    counts the prior content's line count when the file existed before.
    """

    author_name: str
    author_email: str
    date_iso: str
    message: str
    files: dict[str, str]


def _git(repo: Path, *args: str, env: dict[str, str] | None = None) -> None:
    """Run ``git`` in ``repo`` with optional env overlay, abort on failure."""

    subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
        env=env,
    )


def _init_repo(repo: Path) -> None:
    """Create a fresh empty repo with main as the default branch."""

    if repo.exists():
        shutil.rmtree(repo)
    repo.mkdir(parents=True)
    _git(repo, "init", "-q", "-b", "main")
    # Local config only — never touch global git config.
    _git(repo, "config", "commit.gpgsign", "false")
    _git(repo, "config", "tag.gpgsign", "false")


def _apply_commit(repo: Path, commit: _Commit) -> None:
    """Write files, stage them, and commit with pinned author + committer dates."""

    for relpath, content in commit.files.items():
        target = repo / relpath
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        _git(repo, "add", relpath)

    import os

    env = os.environ.copy()
    env.update(
        {
            "GIT_AUTHOR_NAME": commit.author_name,
            "GIT_AUTHOR_EMAIL": commit.author_email,
            "GIT_AUTHOR_DATE": commit.date_iso,
            "GIT_COMMITTER_NAME": commit.author_name,
            "GIT_COMMITTER_EMAIL": commit.author_email,
            "GIT_COMMITTER_DATE": commit.date_iso,
        }
    )
    _git(repo, "commit", "-q", "-m", commit.message, env=env)


def _numbered_lines(prefix: str, count: int, start: int = 1) -> str:
    """Return ``count`` numbered lines starting from ``start`` as a trailing-newline-terminated string.

    Used to build file contents whose ``+X/-Y`` numstat is deterministic by
    construction — each line is unique, and rewriting the file line-by-line
    gives predictable diffs.
    """

    lines = [f"{prefix}{i}" for i in range(start, start + count)]
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# minimal_repo — 10 commits per FIXTURE_SPEC.md.
#
# Content strategy: each file is fully rewritten on every commit. Lines are
# unique ``<name><N>`` tokens so that when we rewrite from N to M lines, the
# numstat is exactly ``added = new-line-count when no overlap`` and
# ``deleted = old-line-count when no overlap``.
#
# To produce a commit like "core.py +1 line, -1 line", we rewrite exactly
# one line to a new value while keeping the others identical. Git's numstat
# counts changed lines as both added and deleted, which matches the spec.
# ---------------------------------------------------------------------------


def _build_minimal_repo() -> None:
    repo = _FIXTURES_DIR / "minimal_repo"
    _init_repo(repo)

    readme_v1 = (
        "# minimal_repo\n"
        "Fixture repository for GitCollector tests.\n"
        "Do not edit directly.\n"
    )
    # core.py snapshots — each step adjusts line count or swaps lines
    # precisely to hit the target numstat. See the table in
    # FIXTURE_SPEC.md for the exact +/- per commit.
    core_c2 = _numbered_lines("core", 10)
    # C3: +2 lines (12 total, first 10 identical to C2)
    core_c3 = _numbered_lines("core", 12)
    # C4: +3, -2 → rewrite 2 lines AND add 1 (total 13 lines, 2 changed)
    core_c4_lines = [f"core{i}" for i in range(1, 13)]
    core_c4_lines[4] = "coreA4"
    core_c4_lines[5] = "coreA5"
    core_c4_lines.append("core13")
    core_c4 = "\n".join(core_c4_lines) + "\n"
    # C5: +1, -1 → rewrite exactly one line, total unchanged (13 lines)
    core_c5_lines = list(core_c4_lines)
    core_c5_lines[7] = "coreB7"
    core_c5 = "\n".join(core_c5_lines) + "\n"
    # C6: +2, -1 → rewrite 1 line AND add 1 (total 14 lines)
    core_c6_lines = list(core_c5_lines)
    core_c6_lines[9] = "coreC9"
    core_c6_lines.append("core14")
    core_c6 = "\n".join(core_c6_lines) + "\n"
    # C8: +5, -2 → rewrite 2 lines AND add 3 (total 17 lines)
    core_c8_lines = list(core_c6_lines)
    core_c8_lines[1] = "coreD1"
    core_c8_lines[2] = "coreD2"
    core_c8_lines.extend(["core15", "core16", "core17"])
    core_c8 = "\n".join(core_c8_lines) + "\n"
    # C10: +2, -1 → rewrite 1 line AND add 1 (total 18 lines)
    core_c10_lines = list(core_c8_lines)
    core_c10_lines[11] = "coreE11"
    core_c10_lines.append("core18")
    core_c10 = "\n".join(core_c10_lines) + "\n"

    # helpers.py
    helpers_c3 = _numbered_lines("help", 5)
    # C5: +4, -1 → rewrite 1 AND add 3 (total 8)
    helpers_c5_lines = [f"help{i}" for i in range(1, 6)]
    helpers_c5_lines[2] = "helpA3"
    helpers_c5_lines.extend(["help6", "help7", "help8"])
    helpers_c5 = "\n".join(helpers_c5_lines) + "\n"
    # C6: +1, -1 → rewrite exactly one line (total 8)
    helpers_c6_lines = list(helpers_c5_lines)
    helpers_c6_lines[4] = "helpB5"
    helpers_c6 = "\n".join(helpers_c6_lines) + "\n"
    # C10: +2, -1 → rewrite 1 AND add 1 (total 9)
    helpers_c10_lines = list(helpers_c6_lines)
    helpers_c10_lines[6] = "helpC7"
    helpers_c10_lines.append("help9")
    helpers_c10 = "\n".join(helpers_c10_lines) + "\n"

    # docs.md
    docs_c7 = _numbered_lines("docs", 8)
    # C9: +3, -1 → rewrite 1 AND add 2 (total 10)
    docs_c9_lines = [f"docs{i}" for i in range(1, 9)]
    docs_c9_lines[3] = "docsA4"
    docs_c9_lines.extend(["docs9", "docs10"])
    docs_c9 = "\n".join(docs_c9_lines) + "\n"

    commits: list[_Commit] = [
        _Commit(
            *_ALICE,
            "2026-02-15T10:00:00+00:00",
            "init: README",
            {"README.md": readme_v1},
        ),
        _Commit(
            *_ALICE, "2026-02-20T10:00:00+00:00", "feat: add core", {"core.py": core_c2}
        ),
        _Commit(
            *_ALICE,
            "2026-02-25T10:00:00+00:00",
            "feat: add helpers",
            {"core.py": core_c3, "helpers.py": helpers_c3},
        ),
        _Commit(
            *_BOB, "2026-03-01T10:00:00+00:00", "refactor: core", {"core.py": core_c4}
        ),
        _Commit(
            *_ALICE,
            "2026-03-05T10:00:00+00:00",
            "feat: extend helpers",
            {"core.py": core_c5, "helpers.py": helpers_c5},
        ),
        _Commit(
            *_BOB,
            "2026-03-10T10:00:00+00:00",
            "fix: core and helpers",
            {"core.py": core_c6, "helpers.py": helpers_c6},
        ),
        _Commit(
            *_ALICE,
            "2026-03-15T10:00:00+00:00",
            "docs: add user guide",
            {"docs.md": docs_c7},
        ),
        _Commit(
            *_ALICE,
            "2026-03-20T10:00:00+00:00",
            "feat: expand core",
            {"core.py": core_c8},
        ),
        _Commit(
            *_CAROL,
            "2026-03-25T10:00:00+00:00",
            "docs: polish user guide",
            {"docs.md": docs_c9},
        ),
        _Commit(
            *_ALICE,
            "2026-03-30T10:00:00+00:00",
            "chore: polish",
            {"core.py": core_c10, "helpers.py": helpers_c10},
        ),
    ]

    for commit in commits:
        _apply_commit(repo, commit)


# ---------------------------------------------------------------------------
# empty_repo — one commit, one file, one line.
# ---------------------------------------------------------------------------


def _build_empty_repo() -> None:
    repo = _FIXTURES_DIR / "empty_repo"
    _init_repo(repo)
    _apply_commit(
        repo,
        _Commit(
            *_ALICE,
            "2026-02-15T10:00:00+00:00",
            "initial commit",
            {"README.md": "baseline\n"},
        ),
    )


# ---------------------------------------------------------------------------
# single_author_repo — 5 commits by Alice; 3 touch a.py, 2 touch b.py; no
# commit touches both.
# ---------------------------------------------------------------------------


def _build_single_author_repo() -> None:
    repo = _FIXTURES_DIR / "single_author_repo"
    _init_repo(repo)

    a_v1 = _numbered_lines("a", 3)
    a_v2 = _numbered_lines("a", 5)
    a_v3 = _numbered_lines("a", 7)
    b_v1 = _numbered_lines("b", 3)
    b_v2 = _numbered_lines("b", 5)

    commits = [
        _Commit(*_ALICE, "2026-03-01T10:00:00+00:00", "add a v1", {"a.py": a_v1}),
        _Commit(*_ALICE, "2026-03-02T10:00:00+00:00", "add b v1", {"b.py": b_v1}),
        _Commit(*_ALICE, "2026-03-03T10:00:00+00:00", "a v2", {"a.py": a_v2}),
        _Commit(*_ALICE, "2026-03-04T10:00:00+00:00", "b v2", {"b.py": b_v2}),
        _Commit(*_ALICE, "2026-03-05T10:00:00+00:00", "a v3", {"a.py": a_v3}),
    ]
    for commit in commits:
        _apply_commit(repo, commit)


# ---------------------------------------------------------------------------
# coupling_repo — 6 commits by Alice, alpha.py + beta.py co-change in every
# commit so the pair surfaces with count=6.
# ---------------------------------------------------------------------------


def _build_coupling_repo() -> None:
    repo = _FIXTURES_DIR / "coupling_repo"
    _init_repo(repo)

    for i in range(1, 7):
        alpha = _numbered_lines("alpha", 2 + i)
        beta = _numbered_lines("beta", 2 + i)
        date = f"2026-03-{i:02d}T10:00:00+00:00"
        _apply_commit(
            repo,
            _Commit(
                *_ALICE,
                date,
                f"co-change commit {i}",
                {"alpha.py": alpha, "beta.py": beta},
            ),
        )


# ---------------------------------------------------------------------------
# minimal_stdlib_repo — 3 commits by Alice, two Python files. Exists so the
# end-to-end integration test has a tiny, deterministic target for the
# stdlib-only code path: the Git hard-floor resolves, all optional
# collectors (scc/lizard/complexipy/pydeps/coverage) skip via the
# PATH-manipulation harness in the test, and the MD renderer's
# ``_not computed — install <tool>_`` markers can be asserted byte-for-byte.
# ---------------------------------------------------------------------------


def _build_minimal_stdlib_repo() -> None:
    repo = _FIXTURES_DIR / "minimal_stdlib_repo"
    _init_repo(repo)

    main_v1 = _numbered_lines("main", 4)
    main_v2 = _numbered_lines("main", 6)
    utils_v1 = _numbered_lines("util", 3)

    commits = [
        _Commit(
            *_ALICE,
            "2026-04-01T10:00:00+00:00",
            "init: main module",
            {"main.py": main_v1},
        ),
        _Commit(
            *_ALICE,
            "2026-04-05T10:00:00+00:00",
            "feat: add utils",
            {"utils.py": utils_v1},
        ),
        _Commit(
            *_ALICE,
            "2026-04-10T10:00:00+00:00",
            "feat: extend main",
            {"main.py": main_v2},
        ),
    ]
    for commit in commits:
        _apply_commit(repo, commit)


def build_all() -> None:
    """Build every fixture. Idempotent: blows away any prior ``.git/`` + working tree."""

    _build_minimal_repo()
    _build_empty_repo()
    _build_single_author_repo()
    _build_coupling_repo()
    _build_minimal_stdlib_repo()


if __name__ == "__main__":
    build_all()
    print("fixtures built under", _FIXTURES_DIR)
