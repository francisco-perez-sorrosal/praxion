"""Fleet-wide guard: plugin-distributed agents must not declare ignored frontmatter fields.

Claude Code ignores the `permissionMode`, `hooks`, and `mcpServers` frontmatter
fields for plugin-distributed subagents (vendor-documented at
code.claude.com/docs/en/sub-agents, verified 2026-07-30). Praxion ships all 17
of its agents exclusively via `.claude-plugin/plugin.json`, so any declaration
of these fields is inert and misleading to future agent authors.

Test strategy: static analysis (YAML frontmatter parse). No fixtures, no mocks.
Rationale is documented in ADR dec-307 (td-072).
"""

from __future__ import annotations

import json
from pathlib import Path

import yaml

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parent.parent
PLUGIN_MANIFEST = REPO_ROOT / ".claude-plugin" / "plugin.json"
VIOLATION_FIXTURE = REPO_ROOT / "tests" / "fixtures" / "agent_frontmatter_violation.md"

# Minimum number of plugin-registered agent files expected. Guards against a
# broken glob or manifest parse silently producing a vacuous pass.
MIN_EXPECTED_AGENT_COUNT = 17

# The single place the ignored-field list is written.
IGNORED_FIELDS: frozenset[str] = frozenset({"permissionMode", "hooks", "mcpServers"})


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_frontmatter(text: str) -> dict[str, object]:
    """Extract and parse YAML frontmatter from a Markdown file.

    Returns a dict; raises ValueError if frontmatter delimiters are missing.
    """
    if not text.startswith("---"):
        raise ValueError("File does not start with YAML frontmatter delimiter '---'")
    end = text.index("---", 3)
    fm_text = text[3:end].strip()
    return yaml.safe_load(fm_text) or {}


def detect_ignored_fields(path: Path) -> set[str]:
    """Return the ignored frontmatter fields declared at the top level of `path`.

    The single shared detector used by both the fleet invariant test and the
    negative-fixture test — a fixture exercising a parallel code path would
    prove nothing about the fleet assertion.
    """
    text = path.read_text(encoding="utf-8")
    fm = _parse_frontmatter(text)
    return set(fm.keys()) & IGNORED_FIELDS


def _plugin_registered_agent_files() -> list[Path]:
    """Resolve every agent file listed in `.claude-plugin/plugin.json`'s `agents` array.

    Derived from plugin.json, not from `glob("agents/*.md")` — the invariant is
    "registered as a plugin subagent", and a future non-plugin agent under
    `agents/` (or a non-agent file like `agents/CLAUDE.md`) must not be caught.
    """
    manifest = json.loads(PLUGIN_MANIFEST.read_text(encoding="utf-8"))
    entries = manifest.get("agents", [])
    # Entries (e.g. "./agents/researcher.md") are relative to the plugin root,
    # which is the repo root — not to .claude-plugin/, where the manifest lives.
    plugin_root = PLUGIN_MANIFEST.parent.parent
    return [(plugin_root / entry).resolve() for entry in entries]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_no_plugin_agent_declares_ignored_fields() -> None:
    """No plugin-registered agent frontmatter may declare an ignored field.

    Accumulates violations across the whole fleet and asserts once, naming
    every offending file and field, so a single run surfaces the full extent
    of the problem rather than stopping at the first failure.
    """
    files = _plugin_registered_agent_files()
    assert len(files) >= MIN_EXPECTED_AGENT_COUNT, (
        f"Expected at least {MIN_EXPECTED_AGENT_COUNT} plugin-registered agent files, "
        f"found {len(files)}. A broken glob or plugin.json parse must not produce a "
        "vacuous pass."
    )

    violations = {path: found for path in files if (found := detect_ignored_fields(path))}
    assert not violations, (
        "Plugin-registered agents must not declare fields Claude Code ignores for "
        "plugin subagents (permissionMode, hooks, mcpServers). Violations:\n"
        + "\n".join(f"  {path}: {sorted(fields)}" for path, fields in violations.items())
    )


def test_detector_flags_a_violating_fixture() -> None:
    """The shared detector must report all three ignored fields on a known-bad fixture.

    Proves the detector actually bites on the real defect shape, not on an
    invented one.
    """
    assert detect_ignored_fields(VIOLATION_FIXTURE) == set(IGNORED_FIELDS)


def test_fixture_is_not_plugin_registered() -> None:
    """The negative fixture must never be a plugin-registered agent.

    If it were, it would make the fleet test red permanently — the fixture
    exists to prove the detector works, not to be part of the fleet.
    """
    assert VIOLATION_FIXTURE.resolve() not in _plugin_registered_agent_files()
