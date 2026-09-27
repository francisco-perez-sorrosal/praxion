"""Shared fixture builders for the `ledger_triage` test suites.

Not a test module: no `test_` prefix, so pytest never collects it, and plain
sibling import (`scripts/` has no `__init__.py`, so pytest's prepend import
mode puts it on `sys.path[0]`) is what `test_ledger_snapshot.py` and
`test_ledger_health.py` use -- same pattern as `_sidecar_testkit.py`. The
`base_repo`/`td264_post_rebase_repo` pytest fixtures built on top of
`build_fixture_repo` live in the sibling `conftest.py`, not here -- a plain
`from _ledger_triage_testkit import base_repo` in two test modules collides
with each test function's own `base_repo` parameter (ruff F811); `conftest.py`
is pytest's own mechanism for sharing a fixture across modules with no import
statement at all.

Every builder drives a *real* `git init`/`commit` under a `tmp_path`; nothing
about git is mocked, because the classes under test (`location-decay`,
`cited-by-commit`, `citation-decay`) are oracle-dependent on real git history.

The frozen `base/` and `td264_post_rebase/` fixtures under
`scripts/test_fixtures/ledger_triage/` are copied byte-for-byte from a
specific historical commit (`cac1ba2e`) -- see that directory's `README.md`.
This module's job is only to turn that frozen snapshot into a real,
committed git repository a reader (`ledger_snapshot.gather`) can run
against, stubbing every `location` cell as a real file so `location-decay`
never fires spuriously on a fixture-only path.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from state_ledger_schema import LEDGERS, parse_ledger

FIXTURES_ROOT = Path(__file__).resolve().parent / "test_fixtures" / "ledger_triage"

IDENTITY = ("-c", "user.email=test@example.com", "-c", "user.name=Test")


def git(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=False)


def git_ok(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    result = git(cwd, *args)
    if result.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} in {cwd} failed: {result.stderr}")
    return result


def _fixture_locations(repo_root: Path) -> set[str]:
    """Every raw `location` cell (comma-split, line-range stripped) in the
    parsed ledger pair plus every `affected_files` entry in the ADR stubs.

    Reuses `state_ledger_schema.parse_ledger` rather than hand-rolling a
    second table parser, and reads ADR `affected_files` with a small local
    regex rather than pulling in `query_adrs` -- these are fixture-side stub
    files, not real ADR records the reader will classify in this pass.
    """
    paths: set[str] = set()
    for spec in LEDGERS[:2]:  # TECH_DEBT_LEDGER.md, TECH_DEBT_RESOLVED.md
        parsed = parse_ledger(repo_root, spec)
        for row in parsed.rows:
            if row.table is None:
                continue
            cell = row.value("location")
            for part in cell.split(","):
                part = part.strip()
                if part:
                    paths.add(part)
    decisions_dir = repo_root / ".ai-state" / "decisions"
    if decisions_dir.is_dir():
        for adr_file in sorted(decisions_dir.glob("*.md")):
            in_block = False
            for line in adr_file.read_text(encoding="utf-8").splitlines():
                if line.startswith("affected_files:"):
                    in_block = True
                    continue
                if in_block:
                    stripped = line.strip()
                    if stripped.startswith("- "):
                        paths.add(stripped[2:].strip())
                    else:
                        in_block = False
    return paths


def _strip_line_range(path: str) -> str:
    """Drop a trailing `:N` or `:N-M` line-range suffix, if present."""
    head, sep, tail = path.rpartition(":")
    if sep and tail.replace("-", "").isdigit():
        return head
    return path


def stub_locations(repo_root: Path) -> None:
    """Create every cited location as a real file (or directory) on disk.

    Skips shapes that are not real repo paths: bare backtick expressions
    with no extension and no slash never appear as `location` cells (they
    are notes-only), but this stays defensive against a directory-shaped ref
    (trailing `/`) by creating a directory instead of a file.
    """
    for raw in _fixture_locations(repo_root):
        cleaned = _strip_line_range(raw)
        if not cleaned or cleaned.startswith("~") or cleaned.startswith("http"):
            continue
        target = repo_root / cleaned
        if cleaned.endswith("/"):
            target.mkdir(parents=True, exist_ok=True)
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists():
            target.write_text("stub\n", encoding="utf-8")


def build_fixture_repo(tmp_path: Path, variant: str = "base") -> Path:
    """A real, committed git repo seeded from the frozen `variant/` fixture.

    Every `location` cell across both ledger files (and every ADR stub's
    `affected_files` entry) is stubbed as a real file first, so
    `location-decay` cannot fire on a path this fixture merely *mentions*.
    """
    src = FIXTURES_ROOT / variant
    if not src.is_dir():
        raise FileNotFoundError(f"no such fixture variant: {src}")

    repo_root = tmp_path / f"repo-{variant}"
    repo_root.mkdir(parents=True)
    git_ok(repo_root, "init", "-q", "-b", "main")
    git_ok(repo_root, "config", "user.email", "test@example.com")
    git_ok(repo_root, "config", "user.name", "Test")

    state_src = src / ".ai-state"
    state_dst = repo_root / ".ai-state"
    state_dst.mkdir(parents=True)
    for path in state_src.rglob("*"):
        if path.is_file():
            rel = path.relative_to(state_src)
            dest = state_dst / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(path.read_bytes())

    stub_locations(repo_root)
    git_ok(repo_root, "add", "-A")
    git_ok(repo_root, *IDENTITY, "commit", "-q", "-m", "seed ledger-triage fixture")
    return repo_root


_LEDGER_HEADER = (
    "# Technical Debt Ledger\n\n**Schema**: 14 row fields + 1 structural `dedup_key`.\n\n"
    "| id | severity | class | direction | location | goal-ref-type | goal-ref-value | "
    "source | first-seen | last-seen | owner-role | status | resolved-by | notes | dedup_key |\n"
    "|----|----------|-------|-----------|----------|---------------|----------------|"
    "--------|------------|-----------|-----------|--------|-------------|-------|-----------|\n"
)


def one_row_repo(tmp_path: Path, notes: str, files: tuple[str, ...]) -> Path:
    """A committed repo holding `files` and one open row `td-902` with `notes`."""
    repo_root = tmp_path / "repo"
    (repo_root / ".ai-state").mkdir(parents=True)
    git_ok(repo_root, "init", "-q", "-b", "main")
    row = (
        "| td-902 | suggested | other | code-to-goals | scripts/x.py | code-quality |  | "
        f"verifier | 2026-01-01 | 2026-01-01 | implementer | open |  | {notes} | 000000000000 |\n"
    )
    (repo_root / ".ai-state" / "TECH_DEBT_LEDGER.md").write_text(_LEDGER_HEADER + row)
    (repo_root / ".ai-state" / "TECH_DEBT_RESOLVED.md").write_text(_LEDGER_HEADER)
    for rel in ("scripts/x.py", *files):
        (repo_root / rel).parent.mkdir(parents=True, exist_ok=True)
        (repo_root / rel).write_text("stub\n")
    git_ok(repo_root, "add", "-A")
    git_ok(repo_root, *IDENTITY, "commit", "-q", "-m", "seed")
    return repo_root


def tombstone_row(repo_root: Path, row_id: str, stamp: str) -> None:
    """Apply a merge or discard the way `/triage-debt` does, before finalize migrates it:
    `status: wontfix` in place in the active file, the stamp appended to `notes`."""
    ledger = repo_root / ".ai-state" / "TECH_DEBT_LEDGER.md"
    lines = ledger.read_text().splitlines(keepends=True)
    (index,) = [i for i, line in enumerate(lines) if line.startswith(f"| {row_id} |")]
    cells = lines[index].split("|")
    cells[12] = " wontfix "
    cells[14] = f" {cells[14].strip()} // {stamp} "
    lines[index] = "|".join(cells)
    ledger.write_text("".join(lines))
