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
    "PILLAR_DOCS",
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
    dynamic rationale is produced. ``explanation`` is the educational
    "what this measures and why it matters" surfaced in dashboard hovers and
    embedded in every report. ``remediation`` is the deterministic
    "how to fix it" guidance surfaced when the criterion fails (an LLM
    criterion may override it with a project-specific recommendation at
    enrichment time).
    """

    id: str
    pillar: str
    level: int
    scope: str
    llm: bool
    applies: Callable[[CollectionContext, ProjectFacts], bool] = always_applies
    check: Callable[[CollectionContext, ProjectFacts], bool] | None = None
    rationale: str = ""
    explanation: str = ""
    remediation: str = ""

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
    explanation: str = "",
    remediation: str = "",
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
        explanation=explanation,
        remediation=remediation,
    )


def _llm(
    crit_id: str,
    pillar: str,
    level: int,
    *,
    scope: str = "repo",
    applies: Callable[[CollectionContext, ProjectFacts], bool] = always_applies,
    rationale: str = "",
    explanation: str = "",
    remediation: str = "",
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
        explanation=explanation,
        remediation=remediation,
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
        explanation=(
            "Checks for a linter config (ruff, eslint, etc.). A linter catches "
            "bugs and anti-patterns mechanically, so an agent gets consistent, "
            "automated feedback instead of guessing the project's standards."
        ),
        remediation=(
            "Add a linter config for your stack — a `[tool.ruff]` block in "
            "`pyproject.toml` for Python, or `biome.json` / `eslint.config.mjs` "
            "for JS/TS — and commit it. Praxion's `/onboard-project` scaffolds "
            "this automatically (Phase 8e)."
        ),
    ),
    _mechanical(
        "c.style.formatter_config",
        "style_validation",
        2,
        checks.has_formatter_config,
        rationale="a formatter configuration is present",
        explanation=(
            "Checks for an auto-formatter config (ruff format, black, prettier). "
            "A formatter removes style debate and keeps diffs minimal, so agent "
            "edits stay consistent with the codebase automatically."
        ),
        remediation=(
            "Configure a formatter — `[tool.ruff.format]` / black for Python or "
            "Biome / Prettier for JS/TS — and pin its settings in the project "
            "config. Praxion's `/onboard-project` scaffolds this (Phase 8e)."
        ),
    ),
    _mechanical(
        "c.style.editorconfig",
        "style_validation",
        2,
        checks.has_editorconfig,
        rationale="an .editorconfig is present",
        explanation=(
            "Checks for an `.editorconfig`. It encodes indentation, charset, and "
            "newline rules every editor honors, so contributors and agents emit "
            "byte-consistent files regardless of local settings."
        ),
        remediation=(
            "Add an `.editorconfig` at the repo root declaring `indent_style`, "
            "`indent_size`, `end_of_line`, and `charset` for your file types. "
            "Praxion's `/onboard-project` installs a universal one (Phase 8e)."
        ),
    ),
    _mechanical(
        "c.style.precommit_config",
        "style_validation",
        3,
        checks.has_precommit_config,
        rationale="a pre-commit configuration is present",
        explanation=(
            "Checks for a pre-commit hook config. Running lint/format/secret "
            "checks before each commit shifts quality enforcement left, so bad "
            "changes are blocked at authoring time rather than in review."
        ),
        remediation=(
            "Add a `.pre-commit-config.yaml` wiring your linter, formatter, and "
            "secret scanner, then run `pre-commit install`."
        ),
    ),
    _llm(
        "c.style.naming_conventions",
        "style_validation",
        3,
        rationale="naming conventions are consistent and intention-revealing",
        explanation=(
            "An LLM judges whether names are consistent and intention-revealing "
            "across the codebase. Predictable naming lets an agent locate and "
            "extend code without re-reading everything."
        ),
        remediation=(
            "Adopt one casing convention per identifier kind (files, dirs, "
            "symbols), document it in CLAUDE.md, and rename outliers toward it."
        ),
    ),
    # --- Pillar 2: Build System -------------------------------------------
    _mechanical(
        "c.build.manifest",
        "build_system",
        1,
        checks.has_build_manifest,
        rationale="a build/dependency manifest is present",
        explanation=(
            "Checks for a dependency/build manifest (`pyproject.toml`, "
            "`package.json`, `Cargo.toml`, …). It declares how to install and "
            "build the project — the entry point any agent needs to act safely."
        ),
        remediation=(
            "Add the manifest for your ecosystem and declare dependencies and "
            "build/run entry points in it."
        ),
    ),
    _mechanical(
        "c.build.lockfile",
        "build_system",
        2,
        checks.has_lockfile,
        rationale="a dependency lockfile pins versions",
        explanation=(
            "Checks for a lockfile (`uv.lock`, `package-lock.json`, …). Pinned "
            "transitive versions make installs reproducible, so an agent's local "
            "build matches CI and teammates."
        ),
        remediation=(
            "Generate and commit a lockfile — e.g. `uv lock`, `npm install`, or "
            "`poetry lock` — alongside the manifest."
        ),
    ),
    _mechanical(
        "c.build.ci_pipeline",
        "build_system",
        3,
        checks.has_ci_pipeline,
        rationale="a CI pipeline configuration is present",
        explanation=(
            "Checks for a CI config (GitHub Actions, GitLab CI, …). Automated "
            "build/test on every push gives an agent a trusted signal that a "
            "change is safe before it merges."
        ),
        remediation=(
            "Add a CI workflow (e.g. `.github/workflows/test.yml`) that installs "
            "dependencies and runs the build and test suite on push/PR."
        ),
    ),
    # --- Pillar 3: Testing -------------------------------------------------
    _mechanical(
        "c.testing.test_directory",
        "testing",
        1,
        checks.has_test_directory,
        rationale="a test directory or test files are present",
        explanation=(
            "Checks for tests on disk (a `tests/` dir or `*_test`/`test_*` "
            "files). Tests are the safety net that lets an agent change code "
            "and verify it still works."
        ),
        remediation=(
            "Create a `tests/` directory and add at least one test that exercises "
            "a core behavior, runnable with your test runner."
        ),
    ),
    _mechanical(
        "c.testing.ci_runs_tests",
        "testing",
        3,
        checks.ci_runs_tests,
        rationale="CI configuration invokes the test suite",
        explanation=(
            "Checks that CI actually invokes the test suite. Tests that don't run "
            "automatically rot; wiring them into CI keeps the safety net live on "
            "every change."
        ),
        remediation=(
            "Add a test-run step to your CI workflow (e.g. `pytest -q` or "
            "`npm test`) so every push and PR executes the suite."
        ),
    ),
    _llm(
        "c.testing.test_quality",
        "testing",
        4,
        rationale="tests are behavior-focused and meaningfully cover the code",
        explanation=(
            "An LLM judges whether tests verify behavior (not implementation "
            "details) and meaningfully cover the code. High-quality tests give "
            "an agent confidence that green means correct."
        ),
        remediation=(
            "Refactor tests toward behavior-focused assertions, cover error and "
            "edge paths, and remove tests that only restate the implementation."
        ),
    ),
    # --- Pillar 4: Documentation ------------------------------------------
    _mechanical(
        "c.docs.readme",
        "documentation",
        1,
        checks.has_readme,
        rationale="a README is present",
        explanation=(
            "Checks for a README. It is the first artifact a human or agent "
            "reads to orient — what the project is, how to run it, where things "
            "live."
        ),
        remediation=(
            "Add a `README.md` covering what the project does, how to install "
            "and run it, and how to run the tests."
        ),
    ),
    _mechanical(
        "c.docs.contributing",
        "documentation",
        3,
        checks.has_contributing_guide,
        rationale="a contributing guide is present",
        explanation=(
            "Checks for a contributing guide. It encodes the dev workflow — "
            "branching, commits, review, release — so a contributor or agent "
            "follows the project's process instead of inventing one."
        ),
        remediation=(
            "Add a `CONTRIBUTING.md` describing the branch/commit conventions, "
            "how to run checks locally, and the PR/review flow."
        ),
    ),
    _llm(
        "c.docs.readme_quality",
        "documentation",
        2,
        rationale="the README explains setup, usage, and architecture clearly",
        explanation=(
            "An LLM judges whether the README clearly explains setup, usage, and "
            "architecture. A present-but-thin README still leaves an agent "
            "guessing; this measures whether it actually informs."
        ),
        remediation=(
            "Expand the README with concrete setup steps, a usage example, and a "
            "short architecture overview pointing to key directories."
        ),
    ),
    _llm(
        "c.docs.agent_friendliness",
        "documentation",
        4,
        rationale="documentation is structured for agent consumption",
        explanation=(
            "An LLM judges whether docs are structured for agent consumption — "
            "explicit commands, file-path references, and conventions an agent "
            "can act on directly rather than prose it must interpret."
        ),
        remediation=(
            "Add agent-facing structure: a CLAUDE.md/AGENTS.md with exact build "
            "and test commands, repo-layout table, and pointers to conventions."
        ),
    ),
    # --- Pillar 5: Dev Environment ----------------------------------------
    _mechanical(
        "c.devenv.gitignore",
        "dev_environment",
        1,
        checks.has_gitignore,
        rationale="a .gitignore is present",
        explanation=(
            "Checks for a `.gitignore`. It keeps build output, caches, and "
            "secrets out of version control, so an agent's commits stay clean "
            "and don't leak local artifacts."
        ),
        remediation=(
            "Add a `.gitignore` (start from a GitHub template for your stack) "
            "covering build output, caches, virtualenvs, and `.env` files."
        ),
    ),
    _mechanical(
        "c.devenv.containerized",
        "dev_environment",
        3,
        checks.has_container_config,
        rationale="a container or devcontainer configuration is present",
        explanation=(
            "Checks for a container/devcontainer config (`Dockerfile`, "
            "`devcontainer.json`, `compose.yaml`). A reproducible environment "
            "removes 'works on my machine' for humans and agents alike."
        ),
        remediation=(
            "Add a `Dockerfile` or `.devcontainer/devcontainer.json` that "
            "provisions the toolchain and dependencies the project needs."
        ),
    ),
    _mechanical(
        "c.devenv.env_example",
        "dev_environment",
        2,
        checks.has_env_example,
        rationale="an environment-variable example file is present",
        explanation=(
            "Checks for an env-var example (`.env.example`). It documents which "
            "configuration the project expects without committing secrets, so "
            "setup is self-describing."
        ),
        remediation=(
            "Add a `.env.example` listing every required variable with safe "
            "placeholder values, and reference it from the README."
        ),
    ),
    # --- Pillar 6: Debugging & Observability ------------------------------
    _mechanical(
        "c.observability.logging_config",
        "observability",
        3,
        checks.has_logging_config,
        rationale="logging or observability configuration is present",
        explanation=(
            "Checks for logging/observability configuration. Structured logging "
            "gives an agent runtime evidence to diagnose failures instead of "
            "reasoning blind."
        ),
        remediation=(
            "Add a logging configuration (level, format, handlers) or an "
            "observability setup (OpenTelemetry, structured logger) to the app."
        ),
    ),
    _mechanical(
        "c.observability.healthcheck",
        "observability",
        4,
        checks.has_healthcheck,
        rationale="a health-check or monitoring surface is present",
        explanation=(
            "Checks for a health-check or monitoring surface (a `/health` "
            "endpoint, a healthcheck script). It lets automation confirm the "
            "service is actually up, not just deployed."
        ),
        remediation=(
            "Expose a health endpoint or check (e.g. `/healthz`) and wire it into "
            "your container/deploy config or monitoring."
        ),
    ),
    # --- Pillar 7: Security & Governance ----------------------------------
    _mechanical(
        "c.security.dependency_scanning",
        "security",
        3,
        checks.has_dependency_scanning,
        rationale="automated dependency scanning is configured",
        explanation=(
            "Checks for automated dependency vulnerability scanning (Dependabot, "
            "renovate, audit in CI). It surfaces known CVEs in dependencies "
            "before they ship."
        ),
        remediation=(
            "Enable `.github/dependabot.yml` or add an audit step "
            "(`pip-audit`, `npm audit`) to CI."
        ),
    ),
    _mechanical(
        "c.security.secrets_policy",
        "security",
        2,
        checks.has_secrets_policy,
        rationale="a secrets-management policy or scanner is present",
        explanation=(
            "Checks for secrets hygiene (a secret scanner config, or a documented "
            "secrets policy). It guards against committing credentials — a "
            "failure mode agents are especially prone to."
        ),
        remediation=(
            "Add a secret scanner (gitleaks/trufflehog) to pre-commit or CI, and "
            "document where real secrets belong."
        ),
    ),
    _mechanical(
        "c.security.license",
        "security",
        1,
        checks.has_license,
        rationale="a LICENSE file is present",
        explanation=(
            "Checks for a LICENSE file. It defines how the code may be used and "
            "is a baseline governance signal for any shared project."
        ),
        remediation=(
            "Add a `LICENSE` file with an SPDX-recognized license appropriate to "
            "the project."
        ),
    ),
    # --- Pillar 8: Code Quality -------------------------------------------
    _mechanical(
        "c.codequality.typecheck_config",
        "code_quality",
        3,
        checks.has_typecheck_config,
        rationale="a static type-checker configuration is present",
        explanation=(
            "Checks for a static type-checker config (mypy, pyright, tsconfig "
            "strict). Types catch a class of errors before runtime and document "
            "interfaces an agent must respect."
        ),
        remediation=(
            "Configure a type checker — a `[tool.mypy]`/`pyrightconfig.json` for "
            "Python or `strict` in `tsconfig.json` for TS — and run it in CI."
        ),
    ),
    _mechanical(
        "c.codequality.complexity_gate",
        "code_quality",
        4,
        checks.has_complexity_gate,
        rationale="a complexity or quality gate is configured",
        explanation=(
            "Checks for a complexity/quality gate (a configured complexity limit "
            "or a coverage threshold). Mechanical gates keep cognitive load and "
            "risk from drifting upward as the code grows."
        ),
        remediation=(
            "Configure a gate — e.g. a max-complexity rule in your linter or a "
            "coverage threshold in CI — and enforce it on PRs."
        ),
    ),
    # --- Pillar 9: Praxion Manageability (separate sub-score) -------------
    _mechanical(
        "c.manage.claudemd",
        "manageability",
        1,
        checks.has_claude_md,
        rationale="a CLAUDE.md project block is present",
        explanation=(
            "Checks for a `CLAUDE.md` project block. It is the agent's baseline "
            "briefing — build/test commands, conventions, repo layout — read at "
            "the start of every session."
        ),
        remediation=(
            "Add a `CLAUDE.md` at the repo root, or run `/onboard-project` to "
            "scaffold the Praxion baseline blocks."
        ),
    ),
    _mechanical(
        "c.manage.agents_md",
        "manageability",
        2,
        checks.has_agents_md,
        rationale="an AGENTS.md surface is present (info, not failure)",
        explanation=(
            "Checks for an `AGENTS.md` surface (informational — its absence does "
            "not lower the score). It provides assistant-agnostic agent "
            "instructions for non-Claude tooling."
        ),
        remediation=(
            "Optionally add an `AGENTS.md` (often generated from CLAUDE.md) for "
            "assistant-agnostic agent guidance."
        ),
    ),
    _mechanical(
        "c.manage.git_hooks",
        "manageability",
        3,
        checks.has_git_hooks,
        rationale="project git hooks are installed",
        explanation=(
            "Checks for installed project git hooks. Hooks enforce gates "
            "(finalize, isolation checks, commit policy) automatically at the "
            "git boundary rather than relying on memory."
        ),
        remediation=(
            "Install the project's git hooks — for Praxion-managed repos, run "
            "`/onboard-project` Phase 4 to symlink them."
        ),
    ),
    _mechanical(
        "c.manage.ai_state",
        "manageability",
        3,
        checks.has_ai_state,
        rationale="an .ai-state/ intelligence directory is present",
        explanation=(
            "Checks for an `.ai-state/` directory. It is the project's persistent "
            "intelligence — ADRs, decisions, metrics, tech-debt — that accrues "
            "value across agent sessions."
        ),
        remediation=(
            "Create `.ai-state/` (and commit it) — `/onboard-project` scaffolds "
            "the skeleton, or add `decisions/` and a first ADR to seed it."
        ),
    ),
)


# ---------------------------------------------------------------------------
# Pillar-level educational docs — the "what this pillar measures and why" copy
# surfaced in dashboard hovers and embedded in each report's pillar records.
# Keyed by pillar id; covers the 8 Factory pillars plus Pillar 9.
# ---------------------------------------------------------------------------

PILLAR_DOCS: dict[str, str] = {
    "style_validation": (
        "Mechanical style and validation tooling — linter, formatter, "
        "editorconfig, pre-commit, and consistent naming. Measures whether the "
        "project enforces consistency automatically so agent edits match house "
        "style without guesswork."
    ),
    "build_system": (
        "How the project declares, pins, and builds its dependencies — manifest, "
        "lockfile, and CI build. Measures whether an agent can reproducibly "
        "install and build the code."
    ),
    "testing": (
        "The automated safety net — tests on disk, run by CI, and of meaningful "
        "behavioral quality. Measures whether an agent can change code and trust "
        "a green suite to mean correct."
    ),
    "documentation": (
        "Human- and agent-facing docs — README, contributing guide, and "
        "agent-structured guidance. Measures whether the project explains itself "
        "well enough to act on."
    ),
    "dev_environment": (
        "Reproducible local setup — gitignore, env-var examples, and "
        "containerization. Measures whether a contributor or agent can stand up "
        "the project the same way every time."
    ),
    "observability": (
        "Runtime visibility — logging/observability configuration and health "
        "surfaces. Measures whether an agent has evidence to diagnose failures "
        "instead of reasoning blind."
    ),
    "security": (
        "Security and governance baselines — license, secrets hygiene, and "
        "dependency scanning. Measures whether the project guards against the "
        "failure modes agents are most prone to."
    ),
    "code_quality": (
        "Mechanical quality gates beyond style — static typing and "
        "complexity/coverage thresholds. Measures whether risk and cognitive "
        "load are held in check as the code grows."
    ),
    "manageability": (
        "Praxion-native agent-manageability surfaces — CLAUDE.md, AGENTS.md, git "
        "hooks, and .ai-state/. Reported as a separate sub-score and never folded "
        "into the 8-pillar Factory level."
    ),
}


# Criteria whose failure is informational, not a hard fail (the AGENTS.md
# manageability criterion). The scorer consults this set to exclude such
# criteria from their pillar's denominator rather than counting them failed.
INFO_NOT_FAIL_CRITERIA: frozenset[str] = frozenset({"c.manage.agents_md"})
