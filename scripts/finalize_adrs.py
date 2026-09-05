#!/usr/bin/env python3
"""Promote draft ADRs to finalized `<NNN>-<slug>.md` records at merge-to-main.

Reads `.ai-state/decisions/drafts/<YYYYMMDD-HHMM>-<user>-<branch>-<slug>.md`
fragments, assigns the next sequential `<NNN>`, renames each file, rewrites
its `id:` frontmatter, and propagates the old `dec-draft-<hash>` -> `dec-NNN`
rewrite across a bounded set of cross-reference locations.

This module owns the repo-root state, git plumbing, draft detection, NNN
assignment, promotion, locking, and the CLI. Three siblings own the pieces
that need none of that state: `finalize_adrs_fragments` (filename -> identity
fields), `finalize_adrs_crossrefs` (bounded citation rewrite + allowlist-gap
detection), and `finalize_adrs_backlinks` (`re_affirmed_by` reciprocity). All
three ship alongside this file in the plugin's `scripts/` directory and are
imported as siblings, exactly like `_repo_root` and `_script_cli`.

Invocation modes:

    finalize_adrs.py                       # --merged (default)
    finalize_adrs.py --merged              # promote drafts added in the last merge
    finalize_adrs.py --branch <name>       # promote drafts added by <name>..HEAD
    finalize_adrs.py --dry-run [mode]      # print the plan, do not write
    finalize_adrs.py --state-root <path>   # stage the promotion in <path>'s index

Exit codes:

    0 -- success, or no drafts to promote (idempotent no-op)
    1 -- manual intervention required (collision, git failure, malformed frontmatter)
"""

from __future__ import annotations

import argparse
import fcntl
import logging
import re
import subprocess
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from _git_runner import GitUnavailableError, git_output, run_git
from _repo_root import is_plugin_cache_path
from _repo_root import resolve_repo_root as _resolve_repo_root
from _script_cli import configure_logging
from _state_repo import UnwritablePlacementError, require_writable_placement
from finalize_adrs_backlinks import backfill_re_affirmed_by
from finalize_adrs_crossrefs import detect_unrewritten_ids, rewrite_cross_references
from finalize_adrs_fragments import FRAGMENT_ADR_PATTERN
from finalize_adrs_fragments import parse_fragment_filename as _parse_fragment_filename

# -- Constants ----------------------------------------------------------------

STATE_DIR_NAME = ".ai-state"

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
DECISIONS_DIR = REPO_ROOT / STATE_DIR_NAME / "decisions"
DRAFTS_DIR = DECISIONS_DIR / "drafts"
LOCK_PATH = DRAFTS_DIR / ".finalize.lock"
REGEN_SCRIPT = SCRIPT_DIR / "regenerate_adr_index.py"

# The git repository whose index carries `.ai-state/`. Equal to `REPO_ROOT`
# for an in-repo project and the sidecar mount for a sidecar-placed one --
# every `git mv`/`git add` promotion runs here, never against `REPO_ROOT`.
STATE_GIT_ROOT = REPO_ROOT

FINALIZED_ADR_PATTERN = re.compile(r"^(\d{3})-.+\.md$")
FRONTMATTER_ID_PATTERN = re.compile(r"^(id:\s*)(dec-draft-[0-9a-f]{8})\s*$", re.MULTILINE)
FRONTMATTER_STATUS_PROPOSED_PATTERN = re.compile(r"^(status:\s*)proposed\s*$", re.MULTILINE)

logger = logging.getLogger("finalize_adrs")


class GitPromotionError(RuntimeError):
    """`git` refused a promotion command, so the promotion did not happen.

    Never swallowed: a refused `git mv` under sidecar placement is the exact
    silent-misstage the mount exists to make impossible, so it aborts the run
    carrying git's own diagnostic rather than degrading to a plain rename that
    stages nothing.
    """


# -- Data classes -------------------------------------------------------------


@dataclass(frozen=True)
class DraftPlan:
    """Promotion plan for a single draft ADR."""

    draft_path: Path
    slug: str
    nnn: int
    new_path: Path
    old_id: str  # dec-draft-<hash>
    new_id: str  # dec-NNN

    @property
    def draft_filename(self) -> str:
        return self.draft_path.name


# -- Filename parsing ---------------------------------------------------------


def parse_fragment_filename(path: Path) -> tuple[datetime, str, str, str]:
    """Extract (timestamp, user, branch, slug) from a fragment ADR filename.

    Binds `finalize_adrs_fragments.parse_fragment_filename` to this module's
    git context. The parser resolves the ambiguous `<user>-<branch>-<slug>`
    split on its own; only this module knows which checkout the identity
    hints must be read from, so it supplies them.

    Raises ValueError if the filename does not match the fragment pattern.
    """
    return _parse_fragment_filename(
        path,
        user_slug_hint=_current_git_user_slug,
        branch_slug_hint=_current_git_branch_slug,
    )


def _current_git_user_slug() -> str | None:
    """Return the user slug derived from git config, sanitized."""
    email = _git("config", "--get", "user.email")
    if email:
        return _sanitize(email.split("@", 1)[0])
    name = _git("config", "--get", "user.name")
    if name:
        return _sanitize(name)
    return None


def _current_git_branch_slug() -> str | None:
    """Return the current branch slug, sanitized."""
    branch = _git("rev-parse", "--abbrev-ref", "HEAD")
    if not branch or branch == "HEAD":
        return None
    return _sanitize(branch)


def _sanitize(raw: str, max_len: int = 40) -> str:
    """Lowercase, strip to [a-z0-9-], collapse runs, cap length."""
    lowered = raw.lower()
    kept = re.sub(r"[^a-z0-9-]+", "-", lowered).strip("-")
    return kept[:max_len]


# -- Git helpers --------------------------------------------------------------


def _git(*args: str) -> str | None:
    """Run `git <args>` and return stdout stripped; None on failure.

    Reads the module-level `REPO_ROOT` at call time, so `_apply_repo_root`'s
    rebind still takes effect. Every call this module makes runs on the
    blocking post-merge hook path, which is why the bounded `git_output` is
    load-bearing here rather than merely tidy.
    """
    return git_output(REPO_ROOT, *args)


def _is_git_worktree(root: Path | None = None) -> bool:
    """True when `root` -- the project repo by default -- is a git worktree.

    Draft detection asks about the project; promotion asks about the state git
    root, which is a different repository under sidecar placement.
    """
    target = REPO_ROOT if root is None else root
    return git_output(target, "rev-parse", "--is-inside-work-tree") == "true"


# -- Repo-root resolution -----------------------------------------------------


def resolve_repo_root(cli_repo_root: str | None) -> Path:
    """Resolve the repo root via the shared resolver, logging the fallback."""

    def _log_fallback(fallback: Path) -> None:
        logger.warning(
            "finalize_adrs: could not resolve repo root from --repo-root or git; "
            "falling back to script-relative %s",
            fallback,
        )

    return _resolve_repo_root(cli_repo_root, script_dir=SCRIPT_DIR, on_fallback=_log_fallback)


def resolve_state_git_root(cli_state_root: str | None, repo_root: Path) -> Path:
    """Resolve the git root that owns `.ai-state/`: `--state-root` > placement.

    Without an explicit flag the answer comes from the placement resolver,
    which returns `repo_root` itself for an in-repo project and the sidecar
    mount for a sidecar-placed one. `require_writable_placement` is the
    deliberate entry point: finalize mutates state, so a dangling or foreign
    shadow must raise here rather than let a caller guess a root and stage
    into the wrong index.

    An explicit root is additionally required to *be* a git worktree. The
    resolver already proves this for a mount (it reads the mount's `.git`
    pointer), and an in-repo project may legitimately not be a git repo at
    all -- but an operator who names a state root and gets no staging has
    been failed silently, which is the whole class this flag exists to close.
    """
    if cli_state_root:
        state_git_root = Path(cli_state_root).resolve()
        _require_git_worktree(state_git_root)
        return state_git_root
    return require_writable_placement(repo_root).state_git_root


def _require_git_worktree(state_git_root: Path) -> None:
    """Refuse a `--state-root` that no `git mv` could ever stage into."""
    if not _is_git_worktree(state_git_root):
        raise UnwritablePlacementError(
            f"{state_git_root} is not a git worktree, so a promotion staged there "
            "would be recorded in no index at all: --state-root must name a git "
            "repository (the sidecar mount realpath for a sidecar-placed checkout)"
        )


def require_state_root_owns_state(state_git_root: Path, repo_root: Path) -> None:
    """Refuse a `--state-root` that is not the repository holding `.ai-state/`.

    The mistake this catches is passing the *project* root for a
    sidecar-placed checkout: its `.ai-state/` resolves into the mount, a
    nested repository, so every promotion command would run against a repo
    that does not track the files. Checked once, up front, before any
    frontmatter is rewritten -- git's own diagnostic for the same mistake
    ("not under version control") arrives only after the first write and
    points at the wrong remedy.
    """
    owned = (repo_root / STATE_DIR_NAME).resolve()
    expected = state_git_root / STATE_DIR_NAME
    if owned != expected:
        raise UnwritablePlacementError(
            f"{owned} is outside repository at {state_git_root}: --state-root must "
            f"name the git root whose own {STATE_DIR_NAME}/ holds the decisions "
            "(the sidecar mount realpath, never the project that shadows it)"
        )


def _apply_repo_root(root: Path, state_git_root: Path | None = None) -> None:
    """Rebind the module-level path constants to a resolved repo root.

    `state_git_root` defaults to `root`, which is exactly the in-repo
    placement: a project with a real `.ai-state/` directory owns its own
    state. `REGEN_SCRIPT` deliberately stays `SCRIPT_DIR`-relative: it is a
    plugin sibling, not a per-repo artifact.
    """
    global REPO_ROOT, DECISIONS_DIR, DRAFTS_DIR, LOCK_PATH, STATE_GIT_ROOT
    REPO_ROOT = root
    DECISIONS_DIR = root / STATE_DIR_NAME / "decisions"
    DRAFTS_DIR = DECISIONS_DIR / "drafts"
    LOCK_PATH = DRAFTS_DIR / ".finalize.lock"
    STATE_GIT_ROOT = root if state_git_root is None else state_git_root


# -- Draft detection ----------------------------------------------------------


def detect_drafts_to_promote(mode: str, branch: str | None) -> list[Path]:
    """Return draft paths to promote based on invocation mode.

    Modes:
    - "merged": drafts added in the just-merged commit range (merge-base..HEAD).
    - "branch": drafts added by `<branch>..HEAD`.
    - "all": every file currently in drafts/ that looks like a fragment.
    """
    if not DRAFTS_DIR.is_dir():
        return []

    all_md = {p for p in DRAFTS_DIR.iterdir() if p.is_file() and p.suffix == ".md"}
    existing = {p for p in all_md if FRAGMENT_ADR_PATTERN.match(p.name)}

    # Defense in depth: a draft whose filename does not match the fragment
    # schema is filtered out of `existing` and would otherwise be silently
    # stranded forever (e.g. a dot or colon left in the slug at creation
    # time). A valid, human-authored decision should never disappear without
    # a trace -- warn loudly so it can be renamed to a valid slug.
    for unmatched in sorted(all_md - existing):
        logger.warning(
            "finalize_adrs: %s is in drafts/ but does not match the fragment "
            "schema [a-z0-9-]+; it will NOT be promoted -- rename it to a "
            "valid slug.",
            unmatched.name,
        )

    if not existing:
        return []

    if mode == "all":
        return sorted(existing)

    if mode == "merged":
        added = _drafts_added_in_last_merge()
    elif mode == "branch":
        if branch is None:
            raise ValueError("mode='branch' requires a branch name")
        added = _drafts_added_by_branch(branch)
    else:
        raise ValueError(f"unknown mode: {mode}")

    if added is None:
        # Git lookup failed; do not guess. Log and return empty.
        logger.warning(
            "finalize_adrs: could not detect drafts via git (mode=%s); "
            "pass --branch or use `--all` explicitly if you want to "
            "promote every file currently in drafts/",
            mode,
        )
        return []

    # Intersect git-detected paths with existing files (ignore renamed-away).
    added_paths = {(DRAFTS_DIR / name).resolve() for name in added}
    return sorted(p for p in existing if p.resolve() in added_paths)


def _drafts_added_in_last_merge() -> set[str] | None:
    """Detect drafts added by the most recent HEAD advance (merge or FF).

    Uses the reflog ``HEAD@{1}`` reference as the primary detection point
    so the diff range captures every commit landed by the most recent
    HEAD update — including fast-forward merges that span multiple
    commits, where the parent-pointer alone (``HEAD^1``) only sees the
    most recent commit and misses drafts added in earlier ones (td-011).

    Falls back to first-parent detection when reflog lookup fails (e.g.,
    shallow clones or freshly initialized repos with no prior HEAD).
    """
    if not _is_git_worktree():
        return None

    # Primary: reflog. ``HEAD@{1}`` is the position of HEAD before its
    # most recent update. Whether the advance was a true merge commit or
    # a fast-forward of N commits, the diff prev_head..HEAD captures
    # every newly-landed file.
    prev_head = _git("rev-parse", "HEAD@{1}")
    if prev_head is not None:
        added = _diff_added_names(prev_head, "HEAD")
        if added is not None:
            return added

    # Fallback: first-parent. Correct for true merge commits; under-
    # detects on FF-merges that span multiple commits but is the safe
    # last resort when reflog is unavailable.
    parents = _git("rev-list", "--parents", "-n", "1", "HEAD")
    if parents is None:
        return None
    parts = parents.split()
    if len(parts) < 2:
        # Root commit; nothing was merged.
        return set()
    merge_base = parts[1]
    return _diff_added_names(merge_base, "HEAD")


def _drafts_added_by_branch(branch: str) -> set[str] | None:
    """Detect drafts added by commits unique to <branch> relative to HEAD."""
    if not _is_git_worktree():
        return None
    merge_base = _git("merge-base", branch, "HEAD")
    if merge_base is None:
        # Branch unknown or no common ancestor; return empty set.
        return set()
    return _diff_added_names(merge_base, branch)


def _diff_added_names(base: str, tip: str) -> set[str] | None:
    """Return filenames added under drafts/ in the given commit range."""
    out = _git(
        "log",
        "--diff-filter=A",
        "--name-only",
        "--pretty=format:",
        f"{base}..{tip}",
        "--",
        ".ai-state/decisions/drafts/",
    )
    if out is None:
        return None
    names: set[str] = set()
    for line in out.splitlines():
        line = line.strip()
        if not line:
            continue
        # The path is repo-relative; take the filename.
        names.add(Path(line).name)
    return names


# -- NNN assignment -----------------------------------------------------------


def next_adr_number(decisions_dir: Path) -> int:
    """Return the next sequential NNN, scanning only finalized ADRs.

    Ignores `drafts/` subdirectory entirely. Returns 1 when no finalized
    ADRs exist yet.
    """
    if not decisions_dir.is_dir():
        return 1
    highest = 0
    for entry in decisions_dir.iterdir():
        if not entry.is_file():
            continue
        match = FINALIZED_ADR_PATTERN.match(entry.name)
        if match is None:
            continue
        highest = max(highest, int(match.group(1)))
    return highest + 1


# -- Promotion ----------------------------------------------------------------


def build_promotion_plan(draft_paths: list[Path]) -> list[DraftPlan]:
    """Build a deterministic per-draft promotion plan from the detected set.

    Assigns NNN in filename-sort order for reproducibility across runs.
    """
    sorted_drafts = sorted(draft_paths, key=lambda p: p.name)
    start = next_adr_number(DECISIONS_DIR)

    plans: list[DraftPlan] = []
    offset = 0
    for draft_path in sorted_drafts:
        # Validate each draft independently: a single malformed fragment (bad
        # filename, empty slug, or non-conforming `id:`) is skipped with a
        # warning rather than aborting the batch. Otherwise one bad ADR would
        # strand an entire release's worth of valid decision history. The
        # offset only advances for drafts that enter the plan, so skipped
        # fragments leave no gap in the assigned NNN sequence.
        try:
            _, _, _, slug = parse_fragment_filename(draft_path)
            if not slug:
                raise ValueError(f"fragment {draft_path.name} produced empty slug after parse")
            old_id = _read_draft_id(draft_path)
        except ValueError as exc:
            logger.warning("finalize_adrs: skipping malformed draft: %s", exc)
            continue
        nnn = start + offset
        new_name = f"{nnn:03d}-{slug}.md"
        new_path = DECISIONS_DIR / new_name
        new_id = f"dec-{nnn:03d}"
        plans.append(
            DraftPlan(
                draft_path=draft_path,
                slug=slug,
                nnn=nnn,
                new_path=new_path,
                old_id=old_id,
                new_id=new_id,
            )
        )
        offset += 1
    return plans


def _read_draft_id(draft_path: Path) -> str:
    """Extract the `id: dec-draft-<hash>` value from a draft's frontmatter.

    Raises ValueError if the id field is absent or malformed.
    """
    content = draft_path.read_text(encoding="utf-8")
    match = FRONTMATTER_ID_PATTERN.search(content)
    if match is None:
        raise ValueError(f"draft {draft_path.name} has no `id: dec-draft-<hash>` in frontmatter")
    return match.group(2)


def promote_draft(draft_path: Path, nnn: int, state_git_root: Path) -> tuple[Path, str]:
    """Promote a single draft to a finalized ADR.

    Performs rename + frontmatter `id:` rewrite only. Cross-reference
    rewrite is the caller's responsibility (see `rewrite_cross_references`).

    `state_git_root` is the repository whose index records the rename -- the
    project root for an in-repo project, the sidecar mount for a
    sidecar-placed one.

    Returns `(new_path, old_draft_id)` where `old_draft_id` is the
    `dec-draft-<hash>` value extracted before the rewrite.

    **Move first, rewrite second.** The reverse order -- rewrite the draft in
    place, then move it -- is not atomic: a refused move leaves a file at the
    `drafts/` path already carrying `id: dec-NNN` and `status: accepted`, which
    every later run then skips as malformed ("no `id: dec-draft-<hash>`") while
    its `dec-NNN` collides with the ADR that legitimately takes that number.
    The draft is stranded permanently and silently. Moving first means every
    refusal path raises with the draft byte-unchanged, so the next run retries
    cleanly.
    """
    _, _, _, slug = parse_fragment_filename(draft_path)
    new_name = f"{nnn:03d}-{slug}.md"
    new_path = DECISIONS_DIR / new_name
    new_id = f"dec-{nnn:03d}"

    if new_path.exists():
        raise FileExistsError(f"target exists: {new_path}; manual intervention required")

    old_id = _read_draft_id(draft_path)

    staged = _rename(draft_path, new_path, state_git_root)

    # The status flip from `proposed` to `accepted` matches the lifecycle
    # transition that finalize represents; without it, finalized ADRs stay
    # flagged as proposals indefinitely.
    content = new_path.read_text(encoding="utf-8")
    rewritten = FRONTMATTER_ID_PATTERN.sub(rf"\g<1>{new_id}", content, count=1)
    rewritten = FRONTMATTER_STATUS_PROPOSED_PATTERN.sub(r"\g<1>accepted", rewritten, count=1)
    new_path.write_text(rewritten, encoding="utf-8")

    # `git mv` stages the rename from the *index* blob, so the rewrite above
    # is an unstaged modification against the new path until it is re-staged
    # -- the `RM` shape that once shipped a finalized ADR still carrying its
    # draft `id:` and `status: proposed`.
    if staged:
        _stage_path(new_path, state_git_root)
    return new_path, old_id


def _state_relative(path: Path, state_git_root: Path) -> str:
    """`path` as a realpath relative to `state_git_root`, for a git argument.

    `.ai-state/` is a symlink under sidecar placement, and git refuses any
    path reaching it through the shadow (`is outside repository at <mount>`).
    Resolving here -- the single site that hands a state path to git -- keeps
    that resolution out of every call site and yields an argument that is
    already relative to the `-C` root, so no absolute-path prefix logic is
    involved at all.
    """
    return str(path.resolve().relative_to(state_git_root))


def _rename(src: Path, dst: Path, state_git_root: Path) -> bool:
    """Rename src -> dst, preferring `git mv` when inside a git worktree.

    Returns True when the move was recorded in an index (so the caller must
    re-stage anything it writes to `dst` afterwards), False when the plain
    filesystem fallback ran and no index is involved at all.

    A refused `git mv` raises rather than falling back to `Path.rename`: the
    fallback moved the file with nothing staged anywhere and logged only at
    DEBUG, which under sidecar placement turned every promotion into a silent
    misstage. `Path.rename` survives for the one case where it is honest --
    an in-repo project that is not a git repository at all, where staging has
    no meaning. That case is reachable only by default resolution: an explicit
    `--state-root` is proven a worktree before any promotion starts. It still
    warns, naming the file, so "renamed but unstaged" is never silent.
    """
    if not _is_git_worktree(state_git_root):
        logger.warning(
            "%s is not a git worktree; %s is renamed but staged in no index",
            state_git_root,
            src.name,
        )
        src.rename(dst)
        return False
    _require_tracked(src, state_git_root)
    result = run_git(
        state_git_root,
        "mv",
        _state_relative(src, state_git_root),
        _state_relative(dst, state_git_root),
    )
    if result.returncode != 0:
        raise GitPromotionError(
            f"git mv refused to promote {src.name} in {state_git_root}: {result.stderr.strip()}"
        )
    return True


def _require_tracked(src: Path, state_git_root: Path) -> None:
    """Put `src` in the index, since `git mv` moves the *index* blob.

    Drafts are meant to be tracked, but under sidecar placement the state
    mount's commit is made by the finalize chain itself, so a draft written
    since the last one is legitimately still untracked when promotion runs --
    and `git mv` refuses an untracked source. Staging it here is the same
    thing the operator's own commit would have done a moment later, and the
    file's content is unaffected either way.

    Raises so the refusal happens before `promote_draft` writes anything: an
    unstageable draft is left byte-identical for the next run to retry.
    """
    rel = _state_relative(src, state_git_root)
    result = run_git(state_git_root, "add", "--", rel)
    if result.returncode != 0:
        raise GitPromotionError(
            f"git add refused to track {src.name} in {state_git_root}: {result.stderr.strip()}"
        )


def _stage_path(path: Path, state_git_root: Path) -> None:
    """Stage `path` so the index carries its current working-tree content.

    Best-effort by design: the rename has already succeeded by the time this
    runs, and this function executes inside the post-merge/post-commit hook
    chain, where raising would abort the promotion mid-flight with no recovery
    path. A failure is logged at warning level so the resulting stale-index
    state is visible rather than silent.
    """
    try:
        result = run_git(state_git_root, "add", "--", _state_relative(path, state_git_root))
    except GitUnavailableError as exc:
        detail = str(exc)
    else:
        if result.returncode == 0:
            return
        detail = result.stderr.strip()
    logger.warning(
        "git add failed for %s (%s); the promoted ADR is renamed but its "
        "frontmatter rewrite is left unstaged",
        path,
        detail,
    )


# -- Concurrency --------------------------------------------------------------


@contextmanager
def acquire_lock(lock_path: Path) -> Iterator[None]:
    """Acquire an exclusive advisory lock for the duration of the context.

    Creates `lock_path` if missing. Releases automatically on exit.
    """
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_file = lock_path.open("a+")
    try:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        yield
    finally:
        try:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
        finally:
            lock_file.close()


# -- Orchestration ------------------------------------------------------------


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="finalize_adrs",
        description=(
            "Promote draft ADRs under .ai-state/decisions/drafts/ to "
            "finalized <NNN>-<slug>.md records."
        ),
    )
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument(
        "--merged",
        action="store_true",
        help="Detect drafts added in the last merge (default mode).",
    )
    mode_group.add_argument(
        "--branch",
        metavar="NAME",
        help="Promote drafts added by commits unique to NAME (relative to HEAD).",
    )
    mode_group.add_argument(
        "--all",
        action="store_true",
        help=(
            "Promote every fragment currently in drafts/, ignoring git "
            "detection. Use when detection is impossible (e.g., no git)."
        ),
    )
    parser.add_argument(
        "--repo-root",
        metavar="PATH",
        help=(
            "Repo root whose .ai-state/decisions/ to finalize. When omitted, "
            "resolved from `git rev-parse --show-toplevel` in the current "
            "directory. Required when the script runs from a symlinked plugin "
            "cache, where the script location does not identify the consumer repo."
        ),
    )
    parser.add_argument(
        "--state-root",
        metavar="PATH",
        help=(
            "Git root whose index carries .ai-state/ -- the sidecar mount for a "
            "sidecar-placed checkout. When omitted, resolved from the project's "
            "placement, which answers with the repo root itself for an ordinary "
            "in-repo .ai-state/ directory."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the promotion plan without writing any files.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable debug logging.",
    )
    return parser.parse_args(argv)


def _resolve_mode(args: argparse.Namespace) -> tuple[str, str | None]:
    if args.branch is not None:
        return "branch", args.branch
    if args.all:
        return "all", None
    # Default behaviour is --merged.
    return "merged", None


def _run_regenerate_index() -> bool:
    """Invoke regenerate_adr_index.py via subprocess. Return True on success."""
    if not REGEN_SCRIPT.is_file():
        logger.warning("regenerate_adr_index.py not found; skipping index regen")
        return False
    try:
        result = subprocess.run(
            [sys.executable, str(REGEN_SCRIPT), "--repo-root", str(REPO_ROOT)],
            capture_output=True,
            text=True,
            cwd=REPO_ROOT,
            check=False,
        )
    except OSError as exc:
        logger.error("failed to invoke regenerate_adr_index.py: %s", exc)
        return False
    if result.returncode != 0:
        logger.error(
            "regenerate_adr_index.py failed (rc=%s): %s",
            result.returncode,
            result.stderr.strip(),
        )
        return False
    if result.stdout:
        logger.info("%s", result.stdout.strip())
    return True


def _describe_plan(plans: list[DraftPlan]) -> str:
    lines = [f"finalize_adrs: {len(plans)} draft(s) to promote"]
    for plan in plans:
        lines.append(
            f"  {plan.draft_filename} -> {plan.new_path.name} ({plan.old_id} -> {plan.new_id})"
        )
    return "\n".join(lines)


def _run(mode: str, branch: str | None, dry_run: bool) -> int:
    """Core promotion workflow. Returns an exit code (0 or 1)."""
    if not DRAFTS_DIR.is_dir():
        logger.info("finalize_adrs: nothing to do (drafts/ missing)")
        return 0

    draft_paths = detect_drafts_to_promote(mode, branch)
    if not draft_paths:
        logger.info("finalize_adrs: nothing to do")
        return 0

    plans = build_promotion_plan(draft_paths)
    logger.info(_describe_plan(plans))

    if dry_run:
        logger.info("finalize_adrs: --dry-run; no changes written")
        return 0

    # Promote each draft (rename + id rewrite) before cross-reference rewrite
    # so the old fragment file does not still carry the old id when other
    # files are updated. Order within the batch is deterministic (sort).
    for plan in plans:
        _, old_id = promote_draft(plan.draft_path, plan.nnn, STATE_GIT_ROOT)
        if old_id != plan.old_id:
            logger.error(
                "id mismatch for %s: plan=%s observed=%s",
                plan.draft_filename,
                plan.old_id,
                old_id,
            )
            return 1
        logger.info(
            "promoted %s -> %s (%s -> %s)",
            plan.draft_filename,
            plan.new_path.name,
            plan.old_id,
            plan.new_id,
        )

    # Cross-reference rewrite across bounded scope, one id at a time.
    total_rewrites = 0
    for plan in plans:
        count = rewrite_cross_references(REPO_ROOT, plan.old_id, plan.new_id)
        if count:
            logger.info(
                "rewrote %s -> %s across %d file(s)",
                plan.old_id,
                plan.new_id,
                count,
            )
        total_rewrites += count
    logger.info("finalize_adrs: %d cross-reference file(s) rewritten", total_rewrites)

    # Post-condition over the same citation net the rewrite walked. A survivor
    # means the rewrite of that one file failed (its warning is above), never
    # that the net is missing a location -- the two share one definition.
    for path, old_id in detect_unrewritten_ids(REPO_ROOT, [p.old_id for p in plans]):
        logger.warning(
            "finalize_adrs: %s still cites %s after the rewrite -- its rewrite "
            "failed; inspect the file and rerun finalize",
            path.relative_to(REPO_ROOT),
            old_id,
        )

    # Self-heal re_affirms/re_affirmed_by reciprocity (dec-070/DL06).
    backfilled = backfill_re_affirmed_by(DECISIONS_DIR, plans)
    if backfilled:
        logger.info("finalize_adrs: %d re_affirmed_by back-link(s) backfilled", backfilled)

    # Regenerate the index last.
    if not _run_regenerate_index():
        return 1

    return 0


def main(argv: list[str] | None = None) -> None:
    """CLI entry point. Never raises; logs errors and exits with a code."""
    args = _parse_args(argv)
    configure_logging(args.verbose)
    mode, branch = _resolve_mode(args)
    root = resolve_repo_root(args.repo_root)
    if is_plugin_cache_path(root):
        logger.error(
            "finalize_adrs: refusing to run against a plugin-cache path (%s); "
            "pass --repo-root or run from the consumer worktree",
            root,
        )
        sys.exit(1)
    try:
        state_git_root = resolve_state_git_root(args.state_root, root)
        require_state_root_owns_state(state_git_root, root)
    except UnwritablePlacementError as exc:
        logger.error("finalize_adrs: %s", exc)
        sys.exit(1)
    _apply_repo_root(root, state_git_root)

    try:
        with acquire_lock(LOCK_PATH):
            code = _run(mode, branch, args.dry_run)
    except (FileExistsError, ValueError, GitPromotionError) as exc:
        logger.error("finalize_adrs: %s", exc)
        sys.exit(1)
    except subprocess.CalledProcessError as exc:
        logger.error("finalize_adrs: git command failed: %s", exc)
        sys.exit(1)
    except OSError as exc:
        logger.error("finalize_adrs: %s", exc)
        sys.exit(1)
    sys.exit(code)


if __name__ == "__main__":
    main()
