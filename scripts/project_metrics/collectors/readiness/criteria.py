"""Criteria-as-data: the 8 Factory pillars + Pillar 9 Manageability rubric.

The readiness rubric is expressed as a flat tuple of :class:`Criterion`
records rather than a YAML file, keeping the engine stdlib-only and the
predicates first-class Python callables. Each criterion belongs to one of
eight Factory pillars (industry-aligned, externally benchmarkable) or the
Praxion-native ninth pillar (``manageability``), carries a maturity level
(1-5), a ``scope`` (``repo`` for whole-repo signals, ``app`` for per-app
signals in a monorepo), and a flag distinguishing **mechanical** criteria
(deterministic ``check`` functions) from **LLM-judged** criteria
(``llm=True``, ``check=None``, scored out-of-band by the enrichment step).

The eight Factory pillars (consolidated product framing):

* ``style_validation`` — Style & Validation
* ``build_system`` — Build System
* ``testing`` — Testing
* ``documentation`` — Documentation
* ``dev_environment`` — Dev Environment
* ``observability`` — Debugging & Observability
* ``security`` — Security & Governance
* ``code_quality`` — Code Quality

The ninth pillar (``manageability``) is Praxion-native and is **never folded
into the 8-pillar level** — it is reported as a separate sub-score so the
Factory number stays comparable across tools.

The four LLM criteria mirror the kodus ``--ai`` split:
``naming_conventions``, ``test_quality``, ``readme_quality``,
``docs_agent_friendliness``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from scripts.project_metrics.collectors.base import CollectionContext
from scripts.project_metrics.collectors.readiness import checks

__all__ = [
    "Criterion",
    "CRITERIA",
    "FACTORY_PILLARS",
    "INFO_NOT_FAIL_CRITERIA",
    "MANAGEABILITY_PILLAR",
    "PILLAR_NAMES",
    "ProjectFacts",
    "always_applies",
]


# ---------------------------------------------------------------------------
# Pillar identity — the 8 Factory pillars (externally benchmarkable) plus the
# Praxion-native ninth pillar. Order is the canonical display order.
# ---------------------------------------------------------------------------

FACTORY_PILLARS: tuple[str, ...] = (
    "style_validation",
    "build_system",
    "testing",
    "documentation",
    "dev_environment",
    "observability",
    "security",
    "code_quality",
)

MANAGEABILITY_PILLAR: str = "manageability"

PILLAR_NAMES: dict[str, str] = {
    "style_validation": "Style & Validation",
    "build_system": "Build System",
    "testing": "Testing",
    "documentation": "Documentation",
    "dev_environment": "Dev Environment",
    "observability": "Debugging & Observability",
    "security": "Security & Governance",
    "code_quality": "Code Quality",
    "manageability": "Praxion Manageability",
}

# Maturity levels span 1-5; the 80%-per-level gate unlocks each in turn.
_MIN_LEVEL: int = 1
_MAX_LEVEL: int = 5


# ---------------------------------------------------------------------------
# ProjectFacts — cheap, deterministic facts derived once per collect pass and
# threaded into every applicability/check predicate so they need not re-walk
# the filesystem. Built by `checks.derive_project_facts(repo_root)`.
# ---------------------------------------------------------------------------

ProjectFacts = dict[str, object]


def always_applies(ctx: CollectionContext, facts: ProjectFacts) -> bool:
    """Applicability predicate for criteria that apply to every repository."""

    del ctx, facts
    return True


# ---------------------------------------------------------------------------
# Criterion record.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Criterion:
    """One pass/fail readiness criterion.

    ``id`` is a stable dotted identifier (``c.<pillar-short>.<slug>``).
    ``pillar`` is one of :data:`FACTORY_PILLARS` or :data:`MANAGEABILITY_PILLAR`.
    ``level`` is the maturity level (1-5) at which the criterion is gated.
    ``scope`` is ``"repo"`` or ``"app"``.
    ``llm`` is ``True`` for LLM-judged criteria (``check`` must be ``None``).
    ``applies`` is a predicate gating applicability against the project facts.
    ``check`` is the deterministic mechanical predicate (``None`` for LLM
    criteria). ``rationale`` is a short static description used when no
    dynamic rationale is produced.
    """

    id: str
    pillar: str
    level: int
    scope: str
    llm: bool
    applies: Callable[[CollectionContext, ProjectFacts], bool] = always_applies
    check: Callable[[CollectionContext, ProjectFacts], bool] | None = None
    rationale: str = ""

    def __post_init__(self) -> None:
        if not (_MIN_LEVEL <= self.level <= _MAX_LEVEL):
            raise ValueError(
                f"Criterion {self.id!r} level {self.level} out of range "
                f"[{_MIN_LEVEL}, {_MAX_LEVEL}]"
            )
        if self.scope not in ("repo", "app"):
            raise ValueError(
                f"Criterion {self.id!r} scope {self.scope!r} must be 'repo' or 'app'"
            )
        if self.llm and self.check is not None:
            raise ValueError(
                f"LLM criterion {self.id!r} must not declare a mechanical check"
            )
        if not self.llm and self.check is None:
            raise ValueError(
                f"Mechanical criterion {self.id!r} must declare a check function"
            )


def _mechanical(
    crit_id: str,
    pillar: str,
    level: int,
    check: Callable[[CollectionContext, ProjectFacts], bool],
    *,
    scope: str = "repo",
    applies: Callable[[CollectionContext, ProjectFacts], bool] = always_applies,
    rationale: str = "",
) -> Criterion:
    """Build a mechanical (deterministic) criterion with concise keyword wiring."""

    return Criterion(
        id=crit_id,
        pillar=pillar,
        level=level,
        scope=scope,
        llm=False,
        applies=applies,
        check=check,
        rationale=rationale,
    )


def _llm(
    crit_id: str,
    pillar: str,
    level: int,
    *,
    scope: str = "repo",
    applies: Callable[[CollectionContext, ProjectFacts], bool] = always_applies,
    rationale: str = "",
) -> Criterion:
    """Build an LLM-judged criterion (no mechanical check; scored out-of-band)."""

    return Criterion(
        id=crit_id,
        pillar=pillar,
        level=level,
        scope=scope,
        llm=True,
        applies=applies,
        check=None,
        rationale=rationale,
    )


# ---------------------------------------------------------------------------
# The rubric — seeded from the kodus 39-check MIT list, mapped onto the eight
# Factory pillars + Pillar 9 Manageability. Mechanical criteria reference pure
# predicates in `checks.py`; the four LLM criteria carry `llm=True`.
# ---------------------------------------------------------------------------

CRITERIA: tuple[Criterion, ...] = (
    # --- Pillar 1: Style & Validation -------------------------------------
    _mechanical(
        "c.style.linter_config",
        "style_validation",
        1,
        checks.has_linter_config,
        rationale="a linter configuration is present",
    ),
    _mechanical(
        "c.style.formatter_config",
        "style_validation",
        2,
        checks.has_formatter_config,
        rationale="a formatter configuration is present",
    ),
    _mechanical(
        "c.style.editorconfig",
        "style_validation",
        2,
        checks.has_editorconfig,
        rationale="an .editorconfig is present",
    ),
    _mechanical(
        "c.style.precommit_config",
        "style_validation",
        3,
        checks.has_precommit_config,
        rationale="a pre-commit configuration is present",
    ),
    _llm(
        "c.style.naming_conventions",
        "style_validation",
        3,
        rationale="naming conventions are consistent and intention-revealing",
    ),
    # --- Pillar 2: Build System -------------------------------------------
    _mechanical(
        "c.build.manifest",
        "build_system",
        1,
        checks.has_build_manifest,
        rationale="a build/dependency manifest is present",
    ),
    _mechanical(
        "c.build.lockfile",
        "build_system",
        2,
        checks.has_lockfile,
        rationale="a dependency lockfile pins versions",
    ),
    _mechanical(
        "c.build.ci_pipeline",
        "build_system",
        3,
        checks.has_ci_pipeline,
        rationale="a CI pipeline configuration is present",
    ),
    # --- Pillar 3: Testing -------------------------------------------------
    _mechanical(
        "c.testing.test_directory",
        "testing",
        1,
        checks.has_test_directory,
        rationale="a test directory or test files are present",
    ),
    _mechanical(
        "c.testing.ci_runs_tests",
        "testing",
        3,
        checks.ci_runs_tests,
        rationale="CI configuration invokes the test suite",
    ),
    _llm(
        "c.testing.test_quality",
        "testing",
        4,
        rationale="tests are behavior-focused and meaningfully cover the code",
    ),
    # --- Pillar 4: Documentation ------------------------------------------
    _mechanical(
        "c.docs.readme",
        "documentation",
        1,
        checks.has_readme,
        rationale="a README is present",
    ),
    _mechanical(
        "c.docs.contributing",
        "documentation",
        3,
        checks.has_contributing_guide,
        rationale="a contributing guide is present",
    ),
    _llm(
        "c.docs.readme_quality",
        "documentation",
        2,
        rationale="the README explains setup, usage, and architecture clearly",
    ),
    _llm(
        "c.docs.agent_friendliness",
        "documentation",
        4,
        rationale="documentation is structured for agent consumption",
    ),
    # --- Pillar 5: Dev Environment ----------------------------------------
    _mechanical(
        "c.devenv.gitignore",
        "dev_environment",
        1,
        checks.has_gitignore,
        rationale="a .gitignore is present",
    ),
    _mechanical(
        "c.devenv.containerized",
        "dev_environment",
        3,
        checks.has_container_config,
        rationale="a container or devcontainer configuration is present",
    ),
    _mechanical(
        "c.devenv.env_example",
        "dev_environment",
        2,
        checks.has_env_example,
        rationale="an environment-variable example file is present",
    ),
    # --- Pillar 6: Debugging & Observability ------------------------------
    _mechanical(
        "c.observability.logging_config",
        "observability",
        3,
        checks.has_logging_config,
        rationale="logging or observability configuration is present",
    ),
    _mechanical(
        "c.observability.healthcheck",
        "observability",
        4,
        checks.has_healthcheck,
        rationale="a health-check or monitoring surface is present",
    ),
    # --- Pillar 7: Security & Governance ----------------------------------
    _mechanical(
        "c.security.dependency_scanning",
        "security",
        3,
        checks.has_dependency_scanning,
        rationale="automated dependency scanning is configured",
    ),
    _mechanical(
        "c.security.secrets_policy",
        "security",
        2,
        checks.has_secrets_policy,
        rationale="a secrets-management policy or scanner is present",
    ),
    _mechanical(
        "c.security.license",
        "security",
        1,
        checks.has_license,
        rationale="a LICENSE file is present",
    ),
    # --- Pillar 8: Code Quality -------------------------------------------
    _mechanical(
        "c.codequality.typecheck_config",
        "code_quality",
        3,
        checks.has_typecheck_config,
        rationale="a static type-checker configuration is present",
    ),
    _mechanical(
        "c.codequality.complexity_gate",
        "code_quality",
        4,
        checks.has_complexity_gate,
        rationale="a complexity or quality gate is configured",
    ),
    # --- Pillar 9: Praxion Manageability (separate sub-score) -------------
    _mechanical(
        "c.manage.claudemd",
        "manageability",
        1,
        checks.has_claude_md,
        rationale="a CLAUDE.md project block is present",
    ),
    _mechanical(
        "c.manage.agents_md",
        "manageability",
        2,
        checks.has_agents_md,
        rationale="an AGENTS.md surface is present (info, not failure)",
    ),
    _mechanical(
        "c.manage.git_hooks",
        "manageability",
        3,
        checks.has_git_hooks,
        rationale="project git hooks are installed",
    ),
    _mechanical(
        "c.manage.ai_state",
        "manageability",
        3,
        checks.has_ai_state,
        rationale="an .ai-state/ intelligence directory is present",
    ),
)


# Criteria whose failure is informational, not a hard fail (the AGENTS.md
# manageability criterion). The scorer consults this set to exclude such
# criteria from their pillar's denominator rather than counting them failed.
INFO_NOT_FAIL_CRITERIA: frozenset[str] = frozenset({"c.manage.agents_md"})
