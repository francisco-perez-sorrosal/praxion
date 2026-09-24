"""Guard: the security-review permission baseline must match the agents' real tool grants.

`skills/context-security-review/references/permission-baseline.md` is the
reference a security review diffs a PR against to spot tool escalation. When an
agent's `tools:` frontmatter changes and the baseline does not, the baseline
either flags a deliberate grant as an escalation or, worse, hides a real one.
This guard keeps the two in lockstep: every agent row's Tools column must name
exactly the tools that agent declares, and every declared agent must have a row.

Test strategy: static analysis (YAML frontmatter + markdown table parse). No mocks.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
AGENTS_DIR = REPO_ROOT / "agents"
BASELINE = (
    REPO_ROOT / "skills" / "context-security-review" / "references" / "permission-baseline.md"
)

# Guards against a broken glob or table parse producing a vacuous pass.
MIN_EXPECTED_AGENT_COUNT = 17


def _split_tools(raw: str) -> frozenset[str]:
    """Split a comma-separated tool list, keeping scoped entries like `Bash(git:*)` whole."""
    unescaped = raw.replace("\\*", "*")
    return frozenset(
        part.strip() for part in re.split(r",\s*(?![^()]*\))", unescaped) if part.strip()
    )


def _agent_tools() -> dict[str, frozenset[str]]:
    tools_by_agent = {}
    for path in sorted(AGENTS_DIR.glob("*.md")):
        text = path.read_text(encoding="utf-8")
        if not text.startswith("---"):
            continue
        frontmatter = yaml.safe_load(text.split("---", 2)[1]) or {}
        if "tools" in frontmatter:
            tools_by_agent[frontmatter["name"]] = _split_tools(str(frontmatter["tools"]))
    return tools_by_agent


def _baseline_tools() -> dict[str, frozenset[str]]:
    rows = {}
    for line in BASELINE.read_text(encoding="utf-8").splitlines():
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) < 2 or cells[0] in {"Agent", ""} or set(cells[0]) <= {"-"}:
            continue
        rows[cells[0]] = _split_tools(cells[1])
    return rows


def test_parse_is_not_vacuous():
    assert len(_agent_tools()) >= MIN_EXPECTED_AGENT_COUNT
    assert len(_baseline_tools()) >= MIN_EXPECTED_AGENT_COUNT


def test_every_agent_has_a_baseline_row():
    missing = sorted(set(_agent_tools()) - set(_baseline_tools()))
    assert not missing, f"agents with no permission-baseline row: {missing}"


def test_baseline_tools_match_agent_frontmatter():
    baseline = _baseline_tools()
    drift = {
        name: {"frontmatter": sorted(declared), "baseline": sorted(baseline[name])}
        for name, declared in _agent_tools().items()
        if name in baseline and baseline[name] != declared
    }
    assert not drift, f"permission-baseline Tools column drifted from agent frontmatter: {drift}"
