"""Mechanical check functions and the project-facts derivation pass.

Every mechanical criterion in :mod:`criteria` resolves to a pure predicate in
this module. The predicates do **not** re-walk the filesystem on each call —
instead, :func:`derive_project_facts` performs one deterministic scan of the
repository root and records a flat ``dict`` of boolean/string facts, which the
predicates read. This keeps the collect pass cheap (one filesystem scan, not
one per criterion) and byte-identical across runs for the same repository.

Stdlib-only: file-existence probes, ``tomllib`` config parses, and substring
scans of well-known config files. No external tools, no network, no clocks,
no randomness — the determinism contract requires byte-identical output for a
fixed ``CollectionContext``.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

from scripts.project_metrics.collectors.base import CollectionContext

__all__ = [
    "derive_project_facts",
    "has_agents_md",
    "has_ai_state",
    "has_build_manifest",
    "has_ci_pipeline",
    "has_claude_md",
    "has_complexity_gate",
    "has_container_config",
    "has_contributing_guide",
    "has_dependency_scanning",
    "has_editorconfig",
    "has_env_example",
    "has_formatter_config",
    "has_git_hooks",
    "has_gitignore",
    "has_healthcheck",
    "has_license",
    "has_linter_config",
    "has_lockfile",
    "has_logging_config",
    "has_precommit_config",
    "has_readme",
    "has_secrets_policy",
    "has_test_directory",
    "has_typecheck_config",
    "ci_runs_tests",
]


# ---------------------------------------------------------------------------
# Fact keys — one stable string per derived fact. Centralized so the deriver
# and the predicates cannot drift apart on a typo'd key.
# ---------------------------------------------------------------------------

_F = {
    "linter_config": "has_linter_config",
    "formatter_config": "has_formatter_config",
    "editorconfig": "has_editorconfig",
    "precommit_config": "has_precommit_config",
    "build_manifest": "has_build_manifest",
    "lockfile": "has_lockfile",
    "ci_pipeline": "has_ci_pipeline",
    "ci_runs_tests": "ci_runs_tests",
    "test_directory": "has_test_directory",
    "readme": "has_readme",
    "contributing": "has_contributing_guide",
    "gitignore": "has_gitignore",
    "container_config": "has_container_config",
    "env_example": "has_env_example",
    "logging_config": "has_logging_config",
    "healthcheck": "has_healthcheck",
    "dependency_scanning": "has_dependency_scanning",
    "secrets_policy": "has_secrets_policy",
    "license": "has_license",
    "typecheck_config": "has_typecheck_config",
    "complexity_gate": "has_complexity_gate",
    "claude_md": "has_claude_md",
    "agents_md": "has_agents_md",
    "git_hooks": "has_git_hooks",
    "ai_state": "has_ai_state",
}


# ---------------------------------------------------------------------------
# Candidate filename / glob tables — the well-known signals each fact probes.
# Tuples (not sets) so iteration order is stable and the scan is deterministic.
# ---------------------------------------------------------------------------

_LINTER_CONFIGS: tuple[str, ...] = (
    ".eslintrc",
    ".eslintrc.json",
    ".eslintrc.js",
    ".eslintrc.cjs",
    ".eslintrc.yml",
    ".eslintrc.yaml",
    "eslint.config.js",
    "eslint.config.mjs",
    "eslint.config.cjs",
    "eslint.config.ts",
    # Biome lints and formats in one tool — mainstream JS/TS choice.
    "biome.json",
    "biome.jsonc",
    ".flake8",
    ".pylintrc",
    "ruff.toml",
    ".ruff.toml",
)
_FORMATTER_CONFIGS: tuple[str, ...] = (
    ".prettierrc",
    ".prettierrc.json",
    ".prettierrc.yml",
    ".prettierrc.yaml",
    ".prettierrc.js",
    ".prettierrc.cjs",
    ".prettierrc.mjs",
    "prettier.config.js",
    "prettier.config.mjs",
    "prettier.config.cjs",
    # Biome is also a formatter (see _LINTER_CONFIGS).
    "biome.json",
    "biome.jsonc",
    ".rustfmt.toml",
    "rustfmt.toml",
    ".clang-format",
)
_BUILD_MANIFESTS: tuple[str, ...] = (
    "pyproject.toml",
    "setup.py",
    "setup.cfg",
    "package.json",
    "Cargo.toml",
    "go.mod",
    "pom.xml",
    "build.gradle",
    "build.gradle.kts",
    "Gemfile",
)
_LOCKFILES: tuple[str, ...] = (
    "uv.lock",
    "poetry.lock",
    "package-lock.json",
    "yarn.lock",
    "pnpm-lock.yaml",
    "Cargo.lock",
    "go.sum",
    "Gemfile.lock",
    "requirements.txt",
)
_CONTAINER_CONFIGS: tuple[str, ...] = (
    "Dockerfile",
    "docker-compose.yml",
    "docker-compose.yaml",
    "compose.yaml",
    "compose.yml",
)
_ENV_EXAMPLES: tuple[str, ...] = (
    ".env.example",
    ".env.sample",
    ".env.template",
    ".env.dist",
)
_CONTRIBUTING_FILES: tuple[str, ...] = (
    "CONTRIBUTING.md",
    "CONTRIBUTING.rst",
    "CONTRIBUTING",
    "docs/CONTRIBUTING.md",
    ".github/CONTRIBUTING.md",
)
_LICENSE_FILES: tuple[str, ...] = (
    "LICENSE",
    "LICENSE.md",
    "LICENSE.txt",
    "COPYING",
)
_README_FILES: tuple[str, ...] = (
    "README.md",
    "README.rst",
    "README.txt",
    "README",
)
_SECRETS_POLICY_FILES: tuple[str, ...] = (
    ".gitleaks.toml",
    ".secrets.baseline",
    ".env.example",
    ".env.sample",
    "SECURITY.md",
    ".github/SECURITY.md",
)
_DEPENDENCY_SCANNING_FILES: tuple[str, ...] = (
    ".github/dependabot.yml",
    ".github/dependabot.yaml",
    "renovate.json",
    ".renovaterc",
    ".renovaterc.json",
    ".snyk",
)
_TEST_DIRS: tuple[str, ...] = (
    "tests",
    "test",
    "spec",
    "__tests__",
)
_CI_DIRS: tuple[str, ...] = (
    ".github/workflows",
    ".gitlab-ci.yml",
    ".circleci",
    ".travis.yml",
    "azure-pipelines.yml",
    "Jenkinsfile",
)


# ---------------------------------------------------------------------------
# Project-facts derivation — one scan, recorded as a flat dict.
# ---------------------------------------------------------------------------


def derive_project_facts(repo_root: Path) -> dict[str, object]:
    """Scan ``repo_root`` once and return the flat fact dict the checks read.

    Deterministic: the scan visits a fixed set of well-known paths and config
    files in a fixed order, producing identical output for identical repo
    state. No clocks, randomness, or external tools.
    """

    pyproject_text = _read_text(repo_root / "pyproject.toml")
    package_json_text = _read_text(repo_root / "package.json")
    pyproject_data = _parse_toml(pyproject_text)

    facts: dict[str, object] = {
        _F["linter_config"]: (
            _any_exists(repo_root, _LINTER_CONFIGS)
            or _pyproject_has_section(pyproject_data, "tool", "ruff")
            or _pyproject_has_section(pyproject_data, "tool", "flake8")
        ),
        _F["formatter_config"]: (
            _any_exists(repo_root, _FORMATTER_CONFIGS)
            or _pyproject_has_section(pyproject_data, "tool", "black")
            or _pyproject_has_section(pyproject_data, "tool", "ruff", "format")
        ),
        _F["editorconfig"]: _exists(repo_root, ".editorconfig"),
        _F["precommit_config"]: _exists(repo_root, ".pre-commit-config.yaml")
        or _exists(repo_root, ".pre-commit-config.yml"),
        _F["build_manifest"]: _any_exists(repo_root, _BUILD_MANIFESTS),
        _F["lockfile"]: _any_exists(repo_root, _LOCKFILES),
        _F["ci_pipeline"]: _any_exists(repo_root, _CI_DIRS),
        _F["ci_runs_tests"]: _ci_invokes_tests(repo_root),
        _F["test_directory"]: _any_exists(repo_root, _TEST_DIRS),
        _F["readme"]: _any_exists(repo_root, _README_FILES),
        _F["contributing"]: _any_exists(repo_root, _CONTRIBUTING_FILES),
        _F["gitignore"]: _exists(repo_root, ".gitignore"),
        _F["container_config"]: _any_exists(repo_root, _CONTAINER_CONFIGS)
        or _exists(repo_root, ".devcontainer"),
        _F["env_example"]: _any_exists(repo_root, _ENV_EXAMPLES),
        _F["logging_config"]: _detect_logging(pyproject_text, package_json_text),
        _F["healthcheck"]: _detect_healthcheck(repo_root, package_json_text),
        _F["dependency_scanning"]: _any_exists(repo_root, _DEPENDENCY_SCANNING_FILES),
        _F["secrets_policy"]: _any_exists(repo_root, _SECRETS_POLICY_FILES),
        _F["license"]: _any_exists(repo_root, _LICENSE_FILES),
        _F["typecheck_config"]: _detect_typecheck(repo_root, pyproject_data),
        _F["complexity_gate"]: _detect_complexity_gate(repo_root, pyproject_data),
        _F["claude_md"]: _exists(repo_root, "CLAUDE.md"),
        _F["agents_md"]: _exists(repo_root, "AGENTS.md"),
        _F["git_hooks"]: _has_installed_git_hooks(repo_root),
        _F["ai_state"]: _exists(repo_root, ".ai-state"),
    }
    return facts


# ---------------------------------------------------------------------------
# Mechanical predicates — read pre-derived facts; never re-scan the filesystem.
# Each takes (ctx, facts) per the criterion contract; ctx is unused (the facts
# already encode the repo state) but kept for signature uniformity.
# ---------------------------------------------------------------------------


def _fact(facts: dict[str, object], key: str) -> bool:
    return bool(facts.get(key, False))


def has_linter_config(ctx: CollectionContext, facts: dict[str, object]) -> bool:
    del ctx
    return _fact(facts, _F["linter_config"])


def has_formatter_config(ctx: CollectionContext, facts: dict[str, object]) -> bool:
    del ctx
    return _fact(facts, _F["formatter_config"])


def has_editorconfig(ctx: CollectionContext, facts: dict[str, object]) -> bool:
    del ctx
    return _fact(facts, _F["editorconfig"])


def has_precommit_config(ctx: CollectionContext, facts: dict[str, object]) -> bool:
    del ctx
    return _fact(facts, _F["precommit_config"])


def has_build_manifest(ctx: CollectionContext, facts: dict[str, object]) -> bool:
    del ctx
    return _fact(facts, _F["build_manifest"])


def has_lockfile(ctx: CollectionContext, facts: dict[str, object]) -> bool:
    del ctx
    return _fact(facts, _F["lockfile"])


def has_ci_pipeline(ctx: CollectionContext, facts: dict[str, object]) -> bool:
    del ctx
    return _fact(facts, _F["ci_pipeline"])


def ci_runs_tests(ctx: CollectionContext, facts: dict[str, object]) -> bool:
    del ctx
    return _fact(facts, _F["ci_runs_tests"])


def has_test_directory(ctx: CollectionContext, facts: dict[str, object]) -> bool:
    del ctx
    return _fact(facts, _F["test_directory"])


def has_readme(ctx: CollectionContext, facts: dict[str, object]) -> bool:
    del ctx
    return _fact(facts, _F["readme"])


def has_contributing_guide(ctx: CollectionContext, facts: dict[str, object]) -> bool:
    del ctx
    return _fact(facts, _F["contributing"])


def has_gitignore(ctx: CollectionContext, facts: dict[str, object]) -> bool:
    del ctx
    return _fact(facts, _F["gitignore"])


def has_container_config(ctx: CollectionContext, facts: dict[str, object]) -> bool:
    del ctx
    return _fact(facts, _F["container_config"])


def has_env_example(ctx: CollectionContext, facts: dict[str, object]) -> bool:
    del ctx
    return _fact(facts, _F["env_example"])


def has_logging_config(ctx: CollectionContext, facts: dict[str, object]) -> bool:
    del ctx
    return _fact(facts, _F["logging_config"])


def has_healthcheck(ctx: CollectionContext, facts: dict[str, object]) -> bool:
    del ctx
    return _fact(facts, _F["healthcheck"])


def has_dependency_scanning(ctx: CollectionContext, facts: dict[str, object]) -> bool:
    del ctx
    return _fact(facts, _F["dependency_scanning"])


def has_secrets_policy(ctx: CollectionContext, facts: dict[str, object]) -> bool:
    del ctx
    return _fact(facts, _F["secrets_policy"])


def has_license(ctx: CollectionContext, facts: dict[str, object]) -> bool:
    del ctx
    return _fact(facts, _F["license"])


def has_typecheck_config(ctx: CollectionContext, facts: dict[str, object]) -> bool:
    del ctx
    return _fact(facts, _F["typecheck_config"])


def has_complexity_gate(ctx: CollectionContext, facts: dict[str, object]) -> bool:
    del ctx
    return _fact(facts, _F["complexity_gate"])


def has_claude_md(ctx: CollectionContext, facts: dict[str, object]) -> bool:
    del ctx
    return _fact(facts, _F["claude_md"])


def has_agents_md(ctx: CollectionContext, facts: dict[str, object]) -> bool:
    del ctx
    return _fact(facts, _F["agents_md"])


def has_git_hooks(ctx: CollectionContext, facts: dict[str, object]) -> bool:
    del ctx
    return _fact(facts, _F["git_hooks"])


def has_ai_state(ctx: CollectionContext, facts: dict[str, object]) -> bool:
    del ctx
    return _fact(facts, _F["ai_state"])


# ---------------------------------------------------------------------------
# Filesystem + config probes — pure helpers used only by derive_project_facts.
# ---------------------------------------------------------------------------


def _exists(repo_root: Path, relative: str) -> bool:
    """Return True when ``repo_root / relative`` exists (file or directory)."""

    return (repo_root / relative).exists()


def _any_exists(repo_root: Path, candidates: tuple[str, ...]) -> bool:
    """Return True when any candidate relative path exists under ``repo_root``."""

    return any(_exists(repo_root, candidate) for candidate in candidates)


def _read_text(path: Path) -> str:
    """Return the file text, or empty string on any read failure."""

    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


def _parse_toml(text: str) -> dict[str, object]:
    """Parse TOML text into a dict; empty dict on parse failure or empty text."""

    if not text:
        return {}
    try:
        return tomllib.loads(text)
    except tomllib.TOMLDecodeError:
        return {}


def _pyproject_has_section(data: dict[str, object], *keys: str) -> bool:
    """Return True when the nested table path ``keys`` exists in ``data``."""

    node: object = data
    for key in keys:
        if not isinstance(node, dict) or key not in node:
            return False
        node = node[key]
    return True


def _ci_invokes_tests(repo_root: Path) -> bool:
    """Return True when a CI workflow file references a test invocation.

    Scans GitHub Actions workflow files plus the common single-file CI
    configs for ``pytest`` / ``npm test`` / ``go test`` / ``cargo test`` /
    a bare ``test`` token, which is a reliable signal that CI runs tests.
    """

    workflows_dir = repo_root / ".github" / "workflows"
    texts: list[str] = []
    if workflows_dir.is_dir():
        for child in sorted(workflows_dir.iterdir()):
            if child.suffix in (".yml", ".yaml"):
                texts.append(_read_text(child))
    for single in (".gitlab-ci.yml", ".travis.yml", "azure-pipelines.yml"):
        candidate = repo_root / single
        if candidate.is_file():
            texts.append(_read_text(candidate))

    test_tokens = ("pytest", "npm test", "go test", "cargo test", "run: make test")
    return any(token in text for text in texts for token in test_tokens)


def _detect_logging(pyproject_text: str, package_json_text: str) -> bool:
    """Return True when a logging/observability library is declared."""

    tokens = (
        "opentelemetry",
        "structlog",
        "loguru",
        "sentry",
        "winston",
        "pino",
        "prometheus",
    )
    haystack = pyproject_text + "\n" + package_json_text
    return any(token in haystack for token in tokens)


def _detect_healthcheck(repo_root: Path, package_json_text: str) -> bool:
    """Return True for a health-check signal (Docker HEALTHCHECK or a route)."""

    dockerfile = _read_text(repo_root / "Dockerfile")
    if "HEALTHCHECK" in dockerfile:
        return True
    return "healthz" in package_json_text or "/health" in package_json_text


def _detect_typecheck(repo_root: Path, pyproject_data: dict[str, object]) -> bool:
    """Return True when a static type-checker is configured."""

    if _pyproject_has_section(pyproject_data, "tool", "mypy") or _pyproject_has_section(
        pyproject_data, "tool", "pyright"
    ):
        return True
    return _any_exists(
        repo_root,
        ("mypy.ini", ".mypy.ini", "pyrightconfig.json", "tsconfig.json"),
    )


def _detect_complexity_gate(repo_root: Path, pyproject_data: dict[str, object]) -> bool:
    """Return True when a complexity / coverage quality gate is configured."""

    if _pyproject_has_section(
        pyproject_data, "tool", "coverage"
    ) or _pyproject_has_section(pyproject_data, "tool", "radon"):
        return True
    return _any_exists(repo_root, ("sonar-project.properties", ".coveragerc"))


def _has_installed_git_hooks(repo_root: Path) -> bool:
    """Return True when project-managed git hooks are installed.

    Looks for a tracked ``.githooks`` directory or installed hook scripts in
    ``.git/hooks`` that are not the default ``.sample`` files git ships.
    """

    if (repo_root / ".githooks").is_dir():
        return True
    hooks_dir = repo_root / ".git" / "hooks"
    if not hooks_dir.is_dir():
        return False
    return any(
        child.is_file() and not child.name.endswith(".sample")
        for child in hooks_dir.iterdir()
    )
