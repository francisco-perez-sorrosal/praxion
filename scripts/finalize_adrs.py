#!/usr/bin/env python3
"""Promote draft ADRs to finalized `<NNN>-<slug>.md` records at merge-to-main.

Reads `.ai-state/decisions/drafts/<YYYYMMDD-HHMM>-<user>-<branch>-<slug>.md`
fragments, assigns the next sequential `<NNN>`, renames each file, rewrites
its `id:` frontmatter, and propagates the old `dec-draft-<hash>` -> `dec-NNN`
rewrite across a bounded set of cross-reference locations.

Invocation modes:

    finalize_adrs.py                       # --merged (default)
    finalize_adrs.py --merged              # promote drafts added in the last merge
    finalize_adrs.py --branch <name>       # promote drafts added by <name>..HEAD
    finalize_adrs.py --dry-run [mode]      # print the plan, do not write

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

# -- Constants ----------------------------------------------------------------

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
DECISIONS_DIR = REPO_ROOT / ".ai-state" / "decisions"
DRAFTS_DIR = DECISIONS_DIR / "drafts"
LOCK_PATH = DRAFTS_DIR / ".finalize.lock"
REGEN_SCRIPT = SCRIPT_DIR / "regenerate_adr_index.py"

FINALIZED_ADR_PATTERN = re.compile(r"^(\d{3})-.+\.md$")
FRAGMENT_ADR_PATTERN = re.compile(r"^(?P<ts>\d{8}-\d{4})-(?P<rest>[a-z0-9-]+)\.md$")
FRONTMATTER_ID_PATTERN = re.compile(
    r"^(id:\s*)(dec-draft-[0-9a-f]{8})\s*$", re.MULTILINE
)
TIMESTAMP_FORMAT = "%Y%m%d-%H%M"

logger = logging.getLogger("finalize_adrs")


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

    Filename shape: `<YYYYMMDD-HHMM>-<user>-<branch>-<slug>.md` where user,
    branch, and slug are each sanitized to `[a-z0-9-]`. Because all three can
    contain hyphens, pure-filename parsing is ambiguous. We resolve by
    probing the current git identity and branch to recover the user/branch
    prefix lengths. When git is unavailable, we fall back to a heuristic:
    user = first segment, branch = second segment, slug = remainder.

    Raises ValueError if the filename does not match the fragment pattern.
    """
    match = FRAGMENT_ADR_PATTERN.match(path.name)
    if not match:
        raise ValueError(f"malformed fragment filename: {path.name}")

    timestamp = datetime.strptime(match.group("ts"), TIMESTAMP_FORMAT)
    rest = match.group("rest")
    tokens = rest.split("-")
    if len(tokens) < 3:
        raise ValueError(
            f"fragment filename too short (need user-branch-slug): {path.name}"
        )

    user_slug_hint = _current_git_user_slug()
    branch_slug_hint = _current_git_branch_slug()
    user, branch, slug = _split_user_branch_slug(rest, user_slug_hint, branch_slug_hint)
    return timestamp, user, branch, slug


def _split_user_branch_slug(
    rest: str, user_hint: str | None, branch_hint: str | None
) -> tuple[str, str, str]:
    """Split `<user>-<branch>-<slug>` using hints from git config when possible.

    When both hints match a prefix of `rest`, we consume them exactly.
    Otherwise we fall back to: user = first token, branch = second token,
    slug = remainder. The heuristic fallback is imperfect but deterministic.
    """
    if user_hint and rest.startswith(user_hint + "-"):
        after_user = rest[len(user_hint) + 1 :]
        if branch_hint and after_user.startswith(branch_hint + "-"):
            slug = after_user[len(branch_hint) + 1 :]
            return user_hint, branch_hint, slug
        # Branch hint did not match; second segment is branch.
        tokens = after_user.split("-", 1)
        if len(tokens) < 2:
            raise ValueError(f"cannot extract slug from fragment tail: {rest}")
        return user_hint, tokens[0], tokens[1]

    # Heuristic fallback: user=first, branch=second, slug=rest.
    tokens = rest.split("-", 2)
    if len(tokens) < 3:
        raise ValueError(f"fragment tail too short to split: {rest}")
    return tokens[0], tokens[1], tokens[2]


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
    """Run `git <args>` and return stdout stripped; None on failure."""
    try:
        result = subprocess.run(
            ["git", *args],
            capture_output=True,
            text=True,
            cwd=REPO_ROOT,
            check=False,
        )
    except FileNotFoundError:
        return None
    if result.returncode != 0:
        return None
    return result.stdout.strip() or None


def _is_git_worktree() -> bool:
    return _git("rev-parse", "--is-inside-work-tree") == "true"


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

    existing = {p for p in DRAFTS_DIR.iterdir() if FRAGMENT_ADR_PATTERN.match(p.name)}
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
    """Detect drafts added by the most recent merge.

    Uses `HEAD^1..HEAD` when HEAD has two parents (a merge commit), falling
    back to `HEAD~1..HEAD` for linear history.
    """
    if not _is_git_worktree():
        return None
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
    for offset, draft_path in enumerate(sorted_drafts):
        _, _, _, slug = parse_fragment_filename(draft_path)
        if not slug:
            raise ValueError(
                f"fragment {draft_path.name} produced empty slug after parse"
            )
        old_id = _read_draft_id(draft_path)
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
    return plans


def _read_draft_id(draft_path: Path) -> str:
    """Extract the `id: dec-draft-<hash>` value from a draft's frontmatter.

    Raises ValueError if the id field is absent or malformed.
    """
    content = draft_path.read_text(encoding="utf-8")
    match = FRONTMATTER_ID_PATTERN.search(content)
    if match is None:
        raise ValueError(
            f"draft {draft_path.name} has no `id: dec-draft-<hash>` in frontmatter"
        )
    return match.group(2)


def promote_draft(draft_path: Path, nnn: int, repo_root: Path) -> tuple[Path, str]:
    """Promote a single draft to a finalized ADR.

    Performs rename + frontmatter `id:` rewrite only. Cross-reference
    rewrite is the caller's responsibility (see `rewrite_cross_references`).

    Returns `(new_path, old_draft_id)` where `old_draft_id` is the
    `dec-draft-<hash>` value extracted before the rewrite.
    """
    _, _, _, slug = parse_fragment_filename(draft_path)
    new_name = f"{nnn:03d}-{slug}.md"
    new_path = DECISIONS_DIR / new_name
    new_id = f"dec-{nnn:03d}"

    if new_path.exists():
        raise FileExistsError(
            f"target exists: {new_path}; manual intervention required"
        )

    old_id = _read_draft_id(draft_path)

    # Rewrite frontmatter `id:` in-place, then rename.
    content = draft_path.read_text(encoding="utf-8")
    rewritten = FRONTMATTER_ID_PATTERN.sub(rf"\g<1>{new_id}", content, count=1)
    draft_path.write_text(rewritten, encoding="utf-8")

    _rename(draft_path, new_path, repo_root)
    return new_path, old_id


def _rename(src: Path, dst: Path, repo_root: Path) -> None:
    """Rename src -> dst, preferring `git mv` when inside a git worktree."""
    if _is_git_worktree():
        result = subprocess.run(
            ["git", "mv", str(src), str(dst)],
            capture_output=True,
            text=True,
            cwd=repo_root,
            check=False,
        )
        if result.returncode == 0:
            return
        logger.debug(
            "git mv failed (%s); falling back to Path.rename",
            result.stderr.strip(),
        )
    src.rename(dst)


# -- Cross-reference rewrite --------------------------------------------------


def rewrite_cross_references(repo_root: Path, old_id: str, new_id: str) -> int:
    """Rewrite every occurrence of `old_id` to `new_id` in bounded locations.

    Bounded scope:
    - All files under `.ai-state/decisions/` (both drafts/ and finalized).
    - `.ai-state/ARCHITECTURE.md` and `docs/architecture.md` (Section 8 ADR
      references land here during pipelines).
    - All `.ai-work/*/LEARNINGS.md`.
    - All `.ai-work/*/SYSTEMS_PLAN.md` and `.ai-work/*/IMPLEMENTATION_PLAN.md`.
    - All `scripts/*.py` and `scripts/*.sh` (pipeline-authored test files and
      migration scripts can carry draft-id references in docstrings/comments).
    - `.ai-state/specs/SPEC_*.md` files matching any active pipeline task slug.

    Returns the number of files modified.
    """
    modified = 0
    for target in _cross_reference_targets(repo_root):
        if _rewrite_in_file(target, old_id, new_id):
            modified += 1
    return modified


def _cross_reference_targets(repo_root: Path) -> Iterator[Path]:
    """Yield every file whose `dec-draft-<hash>` references must be rewritten."""
    decisions = repo_root / ".ai-state" / "decisions"
    if decisions.is_dir():
        for entry in decisions.rglob("*.md"):
            if entry.is_file():
                yield entry

    for architecture_doc in (
        repo_root / ".ai-state" / "ARCHITECTURE.md",
        repo_root / "docs" / "architecture.md",
    ):
        if architecture_doc.is_file():
            yield architecture_doc

    ai_work = repo_root / ".ai-work"
    if ai_work.is_dir():
        for subdir in ai_work.iterdir():
            if not subdir.is_dir():
                continue
            for filename in (
                "LEARNINGS.md",
                "SYSTEMS_PLAN.md",
                "IMPLEMENTATION_PLAN.md",
            ):
                candidate = subdir / filename
                if candidate.is_file():
                    yield candidate

    scripts_dir = repo_root / "scripts"
    if scripts_dir.is_dir():
        for pattern in ("*.py", "*.sh"):
            for entry in scripts_dir.glob(pattern):
                if entry.is_file():
                    yield entry

    specs = repo_root / ".ai-state" / "specs"
    task_slugs = _active_task_slugs(repo_root)
    if specs.is_dir() and task_slugs:
        for entry in specs.glob("SPEC_*.md"):
            if any(slug in entry.name for slug in task_slugs):
                yield entry


def _active_task_slugs(repo_root: Path) -> set[str]:
    """Return task slugs derived from `.ai-work/` subdirectory names."""
    ai_work = repo_root / ".ai-work"
    if not ai_work.is_dir():
        return set()
    return {child.name for child in ai_work.iterdir() if child.is_dir()}


def _rewrite_in_file(path: Path, old_id: str, new_id: str) -> bool:
    """Rewrite `old_id` -> `new_id` in `path`; return True if the file changed."""
    try:
        content = path.read_text(encoding="utf-8")
    except OSError as exc:
        logger.warning("cannot read %s: %s", path, exc)
        return False
    if old_id not in content:
        return False
    rewritten = content.replace(old_id, new_id)
    path.write_text(rewritten, encoding="utf-8")
    logger.debug("rewrote %s -> %s in %s", old_id, new_id, path)
    return True


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


def _configure_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(levelname)s: %(message)s",
        stream=sys.stderr,
    )


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
            [sys.executable, str(REGEN_SCRIPT)],
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
            f"  {plan.draft_filename} -> {plan.new_path.name} "
            f"({plan.old_id} -> {plan.new_id})"
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
        _, old_id = promote_draft(plan.draft_path, plan.nnn, REPO_ROOT)
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

    # Regenerate the index last.
    if not _run_regenerate_index():
        return 1

    return 0


def main(argv: list[str] | None = None) -> None:
    """CLI entry point. Never raises; logs errors and exits with a code."""
    args = _parse_args(argv)
    _configure_logging(args.verbose)
    mode, branch = _resolve_mode(args)

    try:
        with acquire_lock(LOCK_PATH):
            code = _run(mode, branch, args.dry_run)
    except (FileExistsError, ValueError) as exc:
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
