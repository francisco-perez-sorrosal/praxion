"""Cross-reference propagation for the ADR finalize protocol.

Owns one responsibility: once a draft's `dec-draft-<hash>` becomes a stable
`dec-NNN`, every *other* file that cited the draft id must be rewritten to
match. That means owning the one definition of where such a citation may
live -- the citation net -- the rewrite itself, and the post-condition check
that proves the rewrite left nothing behind.

The net is a single generator shared by the rewriter and the detector, and
that sharing is the point. They used to disagree: the rewriter walked an
enumerated allowlist of named files while the detector re-scanned every
markdown file under `.ai-state/` and `docs/`, so each file the allowlist had
not learned yet -- the idea ledgers, then the calibration log, then every
archived spec of a worktree pipeline -- dangled through a finalize before it
was listed. One definition, two consumers: a citation the detector can see is
one the rewriter has already visited, so a survivor is a rewrite failure to
inspect, never a scope gap to widen.

Deliberately repo-root-parameterized and free of module-level path state:
`finalize_adrs.py` resolves the consumer repo root at startup and passes it
in, so this module never guesses which checkout it is operating on.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from pathlib import Path

logger = logging.getLogger("finalize_adrs")

# Frozen historical reports: never regenerated, no downstream automated
# reader, and (verified) carry zero `dec-draft-<hash>` ids -- so excluding
# them from the sweep can never strand a dangling draft reference.
_FROZEN_DOCS_SUBTREE = Path("docs") / "independent-analysis"

# The pipeline documents that cite drafts while the pipeline authoring them is
# still in flight. `.ai-work/` is gitignored and local to the checkout finalize
# runs in, so a worktree pipeline's copies are invisible from the canonical
# checkout -- which is why nothing *persistent* may be scoped through them
# (the archived-spec slug derivation once was, and every worktree pipeline's
# spec kept its draft ids after promotion).
_IN_FLIGHT_DOCUMENTS = ("LEARNINGS.md", "SYSTEMS_PLAN.md", "IMPLEMENTATION_PLAN.md")


def rewrite_cross_references(repo_root: Path, old_id: str, new_id: str) -> int:
    """Rewrite every occurrence of `old_id` to `new_id` across the citation net.

    `old_id` is a concrete `dec-draft-<8-hex>` id, never the shape, so the
    rewrite alters nothing but the citation it is looking for. Returns the
    number of files modified.
    """
    modified = 0
    for target in citation_net(repo_root):
        if _rewrite_in_file(target, old_id, new_id):
            modified += 1
    return modified


def detect_unrewritten_ids(repo_root: Path, promoted_ids: list[str]) -> list[tuple[Path, str]]:
    """Post-condition: promoted draft ids that survived the rewrite, anywhere in the net.

    Walks exactly the files `rewrite_cross_references` walked, so a finding
    can only mean the rewrite of that file failed -- unreadable, unwritable,
    changed underneath the run -- and the caller reports it for a human to
    inspect. Matching concrete ids rather than the `dec-draft-<hash>` shape
    keeps teaching placeholders from registering as findings. Read-only.
    """
    if not promoted_ids:
        return []
    survivors: list[tuple[Path, str]] = []
    for entry in citation_net(repo_root):
        text = _read(entry)
        if text is None:
            continue
        survivors.extend((entry, i) for i in promoted_ids if i in text)
    return survivors


def citation_net(repo_root: Path) -> Iterator[Path]:
    """Every file a `dec-draft-<hash>` citation may legitimately live in.

    Bounded subtrees and named files -- never an arbitrary repo sweep, and
    never code:

    - Every markdown file under `.ai-state/`: sibling decisions (drafts and
      finalized), `DESIGN.md` and its changelog, both tech-debt ledgers, the
      three `CONSULT_*` files, `calibration_log.md`, `SYSTEM_DEPLOYMENT.md`,
      the idea ledgers, every archived spec, and the timestamped report
      families. Any of them may be written mid-pipeline, when the draft id is
      the only id there is -- the citation `rules/swe/adr-conventions.md`
      § Linking to ADRs sanctions.
    - Every markdown file under `docs/` except `docs/independent-analysis/`
      (frozen historical analysis; see `_FROZEN_DOCS_SUBTREE`).
    - The in-flight `.ai-work/*/` pipeline documents named in
      `_IN_FLIGHT_DOCUMENTS`.
    - A project-root `ROADMAP.md`.

    `scripts/` is deliberately outside the net: id-citation-discipline forbids
    `dec-draft-<hash>` in committed code, so the only scripts carrying a
    concrete draft id are test fixtures that must stay literal.
    """
    yield from _markdown_under(repo_root / ".ai-state")
    yield from _markdown_under(repo_root / "docs", excluding=repo_root / _FROZEN_DOCS_SUBTREE)

    ai_work = repo_root / ".ai-work"
    if ai_work.is_dir():
        for subdir in sorted(ai_work.iterdir()):
            if not subdir.is_dir():
                continue
            for filename in _IN_FLIGHT_DOCUMENTS:
                candidate = subdir / filename
                if candidate.is_file():
                    yield candidate

    roadmap = repo_root / "ROADMAP.md"
    if roadmap.is_file():
        yield roadmap


def _markdown_under(root: Path, *, excluding: Path | None = None) -> Iterator[Path]:
    if not root.is_dir():
        return
    for entry in sorted(root.rglob("*.md")):
        if entry.is_file() and (excluding is None or excluding not in entry.parents):
            yield entry


def _read(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        logger.warning("cannot read %s: %s", path, exc)
        return None


def _rewrite_in_file(path: Path, old_id: str, new_id: str) -> bool:
    """Rewrite `old_id` -> `new_id` in `path`; return True if the file changed."""
    content = _read(path)
    if content is None or old_id not in content:
        return False
    try:
        path.write_text(content.replace(old_id, new_id), encoding="utf-8")
    except OSError as exc:
        # Left in place for `detect_unrewritten_ids` to report: the id is still there.
        logger.warning("cannot rewrite %s: %s", path, exc)
        return False
    logger.debug("rewrote %s -> %s in %s", old_id, new_id, path)
    return True
