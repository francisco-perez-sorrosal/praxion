"""ReadinessCollector — the deterministic mechanical half of agent-readiness.

This collector wraps the stdlib-only readiness engine
(``collectors/readiness/``). It runs every **mechanical** criterion through the
check layer, scores the result with the 80%-per-level gate, and emits the
standard collector envelope with a placeholder ``llm`` sub-block
(``status: "pending"``). The non-deterministic LLM enrichment runs **outside**
the runner's collect pass — in ``cli.py``'s ``enrich_readiness`` step — so this
collector honors the byte-identical ``collect()`` determinism contract.

* ``resolve()`` always returns ``Available`` — the collector reads only the
  filesystem and needs no external tool, so its ``tool_availability`` entry is
  always ``"available"``.
* ``collect(ctx)`` is deterministic: it derives project facts once, evaluates
  the mechanical criteria, scores them, and lists every criterion (mechanical
  + LLM) with the LLM criteria left ``passed: None`` for the enrichment step.

The collector does not import :mod:`judge` and never touches the network — the
LLM dependency enters the package only at the ``cli.py`` boundary.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from scripts.project_metrics.collectors.base import (
    Available,
    CollectionContext,
    Collector,
    CollectorResult,
    ResolutionEnv,
    ResolutionResult,
)
from scripts.project_metrics.collectors.readiness import checks, config, score
from scripts.project_metrics.collectors.readiness.criteria import CRITERIA, Criterion

__all__ = ["ReadinessCollector"]

_COLLECTOR_VERSION: str = "1.0.0"
_LLM_PENDING: dict[str, Any] = {"status": "pending", "model": None, "grounded_on": None}


class ReadinessCollector(Collector):
    """Tier-0 always-available collector for the agent-readiness mechanical scan."""

    name = "readiness"
    tier = 0
    required = False
    languages: frozenset[str] = frozenset()

    def __init__(self, repo_root: Path | str | None = None) -> None:
        """Store the repo root used for the filesystem scan.

        The runner threads ``ctx.repo_root == "."`` through ``collect()``; the
        authoritative root is the constructor value, mirroring the coverage
        collector. Falls back to the current working directory when unset.
        """

        self._configured_repo_root: Path | None = Path(repo_root) if repo_root is not None else None

    def resolve(self, env: ResolutionEnv) -> ResolutionResult:
        """Always available — the collector reads only the filesystem."""

        del env
        return Available(version=_COLLECTOR_VERSION)

    def collect(self, ctx: CollectionContext) -> CollectorResult:
        """Run the mechanical criteria, score them, and emit the envelope.

        Deterministic given a fixed repository state: facts are derived once,
        each mechanical criterion is evaluated against them, and the LLM
        criteria are listed with ``passed: None`` for the enrichment step. The
        ``duration_seconds`` is left at the dataclass default ``0.0`` so the
        record is byte-identical across runs (wall-clock would break that).
        """

        repo_root = self._resolve_repo_root(ctx)
        facts = checks.derive_project_facts(repo_root)
        weights = config.load_pillar_weights(repo_root)
        criteria_verdicts = [_evaluate_criterion(crit, ctx, facts) for crit in CRITERIA]
        scored = score.score_with_weights(criteria_verdicts, weights)
        data: dict[str, Any] = {
            "level": scored["level"],
            "pass_pct": scored["pass_pct"],
            "adjusted_level": scored["adjusted_level"],
            "adjusted_pass_pct": scored["adjusted_pass_pct"],
            "pillar_weights": scored["pillar_weights"],
            "weighting_active": scored["weighting_active"],
            "note": None,
            "pillars": scored["pillars"],
            "manageability": scored["manageability"],
            "criteria": criteria_verdicts,
            "llm": dict(_LLM_PENDING),
        }
        return CollectorResult(status="ok", data=data)

    def _resolve_repo_root(self, ctx: CollectionContext) -> Path:
        """Prefer the constructor root; fall back to ctx or the cwd."""

        if self._configured_repo_root is not None:
            return self._configured_repo_root
        if ctx.repo_root and ctx.repo_root != ".":
            return Path(ctx.repo_root)
        return Path.cwd()


def _evaluate_criterion(
    criterion: Criterion, ctx: CollectionContext, facts: dict[str, object]
) -> dict[str, Any]:
    """Produce one verdict dict for ``criterion`` against the derived facts.

    LLM criteria are emitted ``passed: None`` (the enrichment step fills them).
    Non-applicable criteria are emitted ``applicable: False, passed: None``.
    Mechanical applicable criteria carry the deterministic check result.
    """

    applicable = criterion.applies(ctx, facts)
    passed: bool | None
    rationale: str | None
    if not applicable:
        passed, rationale = None, None
    elif criterion.llm:
        passed, rationale = None, None
    else:
        assert criterion.check is not None  # mechanical criteria always have a check
        passed = bool(criterion.check(ctx, facts))
        rationale = criterion.rationale if passed else None
    return {
        "id": criterion.id,
        "pillar": criterion.pillar,
        "level": criterion.level,
        "scope": criterion.scope,
        "applicable": applicable,
        "passed": passed,
        "llm": criterion.llm,
        "rationale": rationale,
        # Educational + how-to-fix content travels in the report so every
        # consumer (dashboard hover, MD report, agent) gets it without
        # reaching into the plugin. `remediation_source` starts "static"; the
        # enrichment step flips it to "llm" when a project-specific LLM
        # recommendation overrides the deterministic guidance.
        "explanation": criterion.explanation,
        "remediation": criterion.remediation,
        "remediation_source": "static",
    }
