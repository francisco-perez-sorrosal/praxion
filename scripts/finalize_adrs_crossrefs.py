"""Cross-reference propagation for the ADR finalize protocol.

Owns one responsibility: once a draft's `dec-draft-<hash>` becomes a stable
`dec-NNN`, every *other* file that cited the draft id must be rewritten to
match. That means owning the bounded allowlist of citation locations, the
rewrite itself, and the detector that catches a citation the allowlist
missed.

Deliberately repo-root-parameterized and free of module-level path state:
`finalize_adrs.py` resolves the consumer repo root at startup and passes it
in, so this module never guesses which checkout it is operating on.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from pathlib import Path

logger = logging.getLogger("finalize_adrs")


def rewrite_cross_references(repo_root: Path, old_id: str, new_id: str) -> int:
    """Rewrite every occurrence of `old_id` to `new_id` in bounded locations.

    Bounded scope:
    - All files under `.ai-state/decisions/` (both drafts/ and finalized).
    - `.ai-state/DESIGN.md`, `.ai-state/TECH_DEBT_LEDGER.md`,
      `.ai-state/TECH_DEBT_RESOLVED.md`, `.ai-state/CONSULT_LEDGER.md`,
      `.ai-state/CONSULT_COSTS.md`, `.ai-state/CONSULT_PRIORS.md`,
      `.ai-state/SYSTEM_DEPLOYMENT.md`, and a project-root `ROADMAP.md` --
      named persistent files that cite the ADR a decision/debt/disposition
      row resolved.
    - Every markdown file under `docs/` (subsumes `docs/architecture.md`):
      design notes and integration docs cite ADR ids outside `.ai-state/`.
    - `.ai-state/idea_ledgers/*.md`: idea entries ground their clusters in the
      ADRs that motivated them, cited as draft ids while the pipeline that
      authored those drafts is still in flight.
    - All `.ai-work/*/LEARNINGS.md`.
    - All `.ai-work/*/SYSTEMS_PLAN.md` and `.ai-work/*/IMPLEMENTATION_PLAN.md`.
    - `.ai-state/specs/SPEC_*.md` files matching any active pipeline task slug.
      Matching is separator-insensitive: spec filenames conventionally use
      underscores (`SPEC_auth_flow_YYYY-MM-DD.md`) while task slugs are
      kebab-case (`auth-flow`), so a literal substring test never matches.

    `scripts/` is deliberately excluded: id-citation-discipline forbids
    `dec-draft-<hash>` in committed code, so the only scripts carrying a
    concrete draft id are test fixtures that must not be rewritten.

    The scope is still an explicit allowlist of named files and bounded
    subtrees -- never an arbitrary whole-repo sweep.

    Returns the number of files modified.
    """
    modified = 0
    for target in _cross_reference_targets(repo_root):
        if _rewrite_in_file(target, old_id, new_id):
            modified += 1
    return modified


def detect_unrewritten_ids(repo_root: Path, promoted_ids: list[str]) -> list[tuple[Path, str]]:
    """Find promoted draft ids that survived the rewrite, outside the allowlist.

    `rewrite_cross_references` walks a bounded allowlist, and a file outside it
    is indistinguishable from a file with no matches -- the allowlist fails
    silently by construction, so a citation in an unlisted file dangles while
    the run still reports success. This detector closes that failure class
    rather than its instances: it re-scans a deliberately wider net (every
    markdown file under `.ai-state/` and `docs/`) for the concrete ids just
    promoted. Matching concrete ids rather than the `dec-draft-<hash>` shape
    keeps teaching placeholders and test fixtures from registering as findings.

    Read-only. Returns (path, surviving_id) pairs for the caller to report.
    """
    if not promoted_ids:
        return []
    survivors: list[tuple[Path, str]] = []
    for scan_root in (repo_root / ".ai-state", repo_root / "docs"):
        if not scan_root.is_dir():
            continue
        for entry in sorted(scan_root.rglob("*.md")):
            if not entry.is_file():
                continue
            try:
                text = entry.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            survivors.extend((entry, i) for i in promoted_ids if i in text)
    return survivors


def _cross_reference_targets(repo_root: Path) -> Iterator[Path]:
    """Yield every file whose `dec-draft-<hash>` references must be rewritten."""
    decisions = repo_root / ".ai-state" / "decisions"
    if decisions.is_dir():
        for entry in decisions.rglob("*.md"):
            if entry.is_file():
                yield entry

    # Named persistent files that legitimately cite ADR ids: the design target,
    # both tech-debt ledgers (rows reference the ADR that resolved them), the
    # consult disposition ledger (its `rationale-ref` column is documented to
    # hold `dec-NNN` or, pre-finalize, `dec-draft-<hash>`), the calibration log
    # (every tier's completion row may name the decisions the task executed,
    # and rows written mid-pipeline can only know the draft id), plus a
    # project-root ROADMAP.md when present.
    for persistent_doc in (
        repo_root / ".ai-state" / "DESIGN.md",
        repo_root / ".ai-state" / "TECH_DEBT_LEDGER.md",
        repo_root / ".ai-state" / "TECH_DEBT_RESOLVED.md",
        repo_root / ".ai-state" / "CONSULT_LEDGER.md",
        repo_root / ".ai-state" / "CONSULT_COSTS.md",
        repo_root / ".ai-state" / "CONSULT_PRIORS.md",
        repo_root / ".ai-state" / "SYSTEM_DEPLOYMENT.md",
        repo_root / ".ai-state" / "calibration_log.md",
        repo_root / "ROADMAP.md",
    ):
        if persistent_doc.is_file():
            yield persistent_doc

    # Bounded docs/ sweep: every markdown file under docs/ (subsumes the
    # developer architecture guide). Consumer projects cite ADR ids from
    # design notes and integration docs that live outside .ai-state/; without
    # this sweep those references dangle the moment finalize runs.
    docs_dir = repo_root / "docs"
    if docs_dir.is_dir():
        for entry in docs_dir.rglob("*.md"):
            if entry.is_file():
                yield entry

    # Idea ledgers cite the ADRs that motivated a cluster, and the citation is
    # authored mid-pipeline when only the draft id exists -- the case
    # adr-conventions explicitly sanctions. The allowlist-gap detector already
    # scans this subtree; without the sweep the rewriter disagrees with the
    # detector and every finalize strands those citations.
    idea_ledgers = repo_root / ".ai-state" / "idea_ledgers"
    if idea_ledgers.is_dir():
        for entry in idea_ledgers.glob("*.md"):
            if entry.is_file():
                yield entry

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

    # NOTE: scripts/ is intentionally NOT swept. id-citation-discipline forbids
    # `dec-draft-<hash>` in committed code, so no production script legitimately
    # carries a draft id to rewrite; the only `scripts/` files that contain a
    # concrete draft id are test fixtures that use it as data (and must be left
    # untouched). Sweeping scripts/ was all-risk (corrupting a fixture on a hash
    # collision), no-benefit, and contradicted the documented bounded scope,
    # which never listed scripts/.

    specs = repo_root / ".ai-state" / "specs"
    task_slugs = _active_task_slugs(repo_root)
    if specs.is_dir() and task_slugs:
        # Spec filenames conventionally use underscores while task slugs are
        # kebab-case, so compare with both separators normalized to `-`.
        normalized_slugs = {slug.replace("_", "-") for slug in task_slugs}
        for entry in specs.glob("SPEC_*.md"):
            normalized_name = entry.name.replace("_", "-")
            if any(slug in normalized_name for slug in normalized_slugs):
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
