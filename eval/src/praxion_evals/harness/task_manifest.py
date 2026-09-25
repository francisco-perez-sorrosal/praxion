"""Expected-artifact manifest for in-flight pipelines, keyed by pipeline tier.

The manifest is the source of truth for which files a completed pipeline at a
given tier must produce. Family 1's in-flight artifact-manifest check consumes
these specs (via the corpus reader) to verdict each expected deliverable.

Migrated from the retired ``praxion_evals.behavioral`` package; the corpus
reader now performs the scan once and surfaces verdicts on the Corpus, so
Family 1 stays stateless.

The Standard/Full file-decidable sets are *derived* from
``scripts/artifact_registry.py``'s per-tier floor rather than hand-maintained
here. ``scripts/`` sits outside this eval package (a separate uv project), so
it is loaded by path rather than imported as a dependency -- mirrors
``family5_token_budget_stability._load_measure_token_budget``. Only the
eval-local FULL extras (architecture-doc recency) and the LIGHTWEIGHT branch
stay hand-written here; eval-only concerns stay eval-local.
"""

from __future__ import annotations

import importlib
import sys
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

from praxion_evals.harness.schemas import TaskArtifactVerdict

# eval/src/praxion_evals/harness/task_manifest.py -> harness -> praxion_evals -> src -> eval -> repo root
_EVAL_ROOT = Path(__file__).resolve().parents[3]
_REPO_ROOT = _EVAL_ROOT.parent
_SCRIPTS_DIR = _REPO_ROOT / "scripts"


def _load_artifact_registry() -> Any:
    """Import ``scripts/artifact_registry.py`` as a sibling-safe module.

    ``scripts/`` must be on ``sys.path`` before the import -- the eval
    project's own package layout is untouched.
    """
    if str(_SCRIPTS_DIR) not in sys.path:
        sys.path.insert(0, str(_SCRIPTS_DIR))
    return importlib.import_module("artifact_registry")


class PipelineTier(StrEnum):
    """Coordination-protocol tiers that produce different artifact sets."""

    LIGHTWEIGHT = "lightweight"
    STANDARD = "standard"
    FULL = "full"


@dataclass(frozen=True)
class ArtifactSpec:
    """One expected deliverable.

    ``path`` is relative to the repo root and may contain ``{slug}`` as a
    placeholder for the task slug. ``required`` gates whether absence flips
    the verdict to ``missing`` vs informational. ``check_recency`` asks the
    scan to compare mtime against ``pipeline_start`` when one is available —
    used for living docs that must be refreshed per-pipeline.
    """

    path: str
    required: bool = True
    check_recency: bool = False
    description: str = ""
    # When set, `required` applies only if the predicate holds for the task dir
    # (`.ai-work/<slug>/`). A conditionally-produced artifact (e.g. TEST_RESULTS only
    # when tests ran) is informational — never a missing-FAIL — on runs where its
    # activation signal is absent. None = unconditionally required.
    activation: Callable[[Path], bool] | None = None


# -- Derivation from the registry's per-tier floor -----------------------------
# Only the file-decidable requirements (always / a Signal) project into the
# manifest — a 'when produced' floor entry is declarative (undecidable from
# files; see artifact_registry.signal_holds) and the manifest emits nothing
# for it, matching the registry's own floor()/signal_holds() contract.


def _activation_for(signal: Any) -> Callable[[Path], bool]:
    """Wrap a registry `Signal` into the `.ai-work/<slug>/`-relative predicate
    `ArtifactSpec.activation` expects."""

    def _holds(task_dir: Path) -> bool:
        return bool(_load_artifact_registry().signal_holds(signal, task_dir))

    return _holds


def _spec_from_floor_entry(entry: Any) -> ArtifactSpec:
    """Build one file-decidable `ArtifactSpec` from a registry `FloorEntry`."""
    artifact = _load_artifact_registry().by_name(entry.name)
    description = artifact.description if artifact is not None else ""
    path = f".ai-work/{{slug}}/{entry.name}"
    if entry.requirement == "always":
        return ArtifactSpec(path=path, description=description)
    return ArtifactSpec(
        path=path, description=description, activation=_activation_for(entry.requirement)
    )


def _file_decidable_floor(tier: str) -> tuple[Any, ...]:
    """The registry's floor projection at `tier`, excluding undecidable PRODUCED entries."""
    registry = _load_artifact_registry()
    return tuple(e for e in registry.floor(tier) if e.requirement is not registry.Signal.PRODUCED)


_FULL_EXTRA: tuple[ArtifactSpec, ...] = (
    ArtifactSpec(
        path=".ai-state/DESIGN.md",
        required=False,
        check_recency=True,
        description="Architect-facing design target; should be touched for structural changes.",
    ),
    ArtifactSpec(
        path="docs/architecture.md",
        required=False,
        check_recency=True,
        description="Developer-facing navigation guide derived from DESIGN.md.",
    ),
)


def expected_artifacts(tier: PipelineTier = PipelineTier.STANDARD) -> tuple[ArtifactSpec, ...]:
    """Return the ordered artifact specs for the given pipeline tier."""
    if tier is PipelineTier.LIGHTWEIGHT:
        # Lightweight tier requires only WIP.md; other docs are optional. Lightweight has no
        # registry floor entry (the floor is Standard/Full-only) -- stays eval-local.
        return (
            ArtifactSpec(
                path=".ai-work/{slug}/WIP.md",
                description="Live execution state (lightweight pipelines).",
            ),
        )
    registry_tier = "full" if tier is PipelineTier.FULL else "standard"
    specs = tuple(_spec_from_floor_entry(e) for e in _file_decidable_floor(registry_tier))
    if tier is PipelineTier.FULL:
        # FULL extends the registry's Full floor with the architecture-doc recency checks
        # (eval-local: recency has no registry representation).
        return specs + _FULL_EXTRA
    return specs


def scan_task_manifest(
    repo_root: Path,
    task_slug: str,
    tier: PipelineTier,
    pipeline_start: datetime | None = None,
) -> tuple[TaskArtifactVerdict, ...]:
    """Walk the per-tier manifest under *repo_root* and return verdicts.

    Pure filesystem read; never invokes subprocesses or imports judging code.

    Args:
        repo_root: Filesystem root to scan (a working tree, a worktree, or any
            checkout-like directory).
        task_slug: The pipeline's task slug (``.ai-work/<slug>/`` directory).
        tier: Pipeline tier governing which artifacts are expected.
        pipeline_start: Optional timestamp gating recency checks for FULL tier.

    Returns:
        Tuple of ``TaskArtifactVerdict`` in manifest order.
    """
    specs = expected_artifacts(tier)
    verdicts: list[TaskArtifactVerdict] = []
    for spec in specs:
        verdicts.append(_verdict_for(spec, task_slug, repo_root, pipeline_start))
    return tuple(verdicts)


def _verdict_for(
    spec: ArtifactSpec,
    task_slug: str,
    repo_root: Path,
    pipeline_start: datetime | None,
) -> TaskArtifactVerdict:
    relative = spec.path.format(slug=task_slug)
    path = repo_root / relative
    # A conditional spec is required only when its activation signal holds; on a run
    # where the producing step did not fire, an absent artifact is informational.
    task_dir = repo_root / ".ai-work" / task_slug
    effective_required = spec.required and (spec.activation is None or spec.activation(task_dir))
    if not path.exists():
        return TaskArtifactVerdict(
            path=relative,
            verdict="missing",
            required=effective_required,
            description=spec.description,
        )
    if spec.check_recency and pipeline_start is not None:
        mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=pipeline_start.tzinfo)
        if mtime < pipeline_start:
            return TaskArtifactVerdict(
                path=relative,
                verdict="stale",
                required=effective_required,
                description=spec.description,
                detail=(
                    f"mtime {mtime.isoformat()} precedes pipeline start "
                    f"{pipeline_start.isoformat()}"
                ),
            )
    return TaskArtifactVerdict(
        path=relative,
        verdict="present",
        required=effective_required,
        description=spec.description,
    )
