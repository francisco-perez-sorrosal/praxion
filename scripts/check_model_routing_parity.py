#!/usr/bin/env python3
"""Hold every agent definition's ``model:`` equal to its row in the model-routing tier table.

The tier table in ``rules/swe/agent-model-routing.md`` says which model each agent runs at, and
each definition's ``model:`` frontmatter is what the harness applies when a spawn passes no
``model`` of its own. When the two agree, a spawn reaches its tier whatever the orchestrator
remembers; when they drift, the table describes routing that no longer happens. Nothing checked
them against each other, so this does.

One difference is deliberate and declared here, never inferred: the discipline-consultant's
frontmatter floor is ``sonnet`` while its row is ``opus``, so a routine consult can route down
(one of the rule's two sanctioned downgrades; the other, the verifier's light review, is per spawn
and declares no floor). A declared floor that no longer differs from the row, or that the
definition no longer carries, is reported too, so the exception cannot outlive its reason.

Findings: ``mismatch`` (a definition's model is not its row's alias), ``no-row`` (an agent the
table does not list), ``no-agent`` (a row naming no definition), ``stale-floor`` (a declared floor
the files no longer show), ``no-table`` (the rule has no readable tier table).

Usage: python3 scripts/check_model_routing_parity.py [--repo-root PATH]
Exit codes: 0 in parity, 1 findings, 2 input error (the rule cannot be read).
Stdlib-only, since it runs under the ambient interpreter.
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from _repo_root import resolve_repo_root  # noqa: E402

ROUTING_RULE = Path("rules/swe/agent-model-routing.md")
AGENTS_DIR = Path("agents")
TABLE_HEADING = "### Tier Table"
# The one sanctioned difference between a row and its definition: agent -> frontmatter floor.
DECLARED_FLOORS = {"discipline-consultant": "sonnet"}
_ROW = re.compile(r"^\|\s*`(?P<agent>[^`]+)`\s*\|\s*[^|]*\|\s*`(?P<alias>[^`]+)`\s*\|")
# A frontmatter value may carry a trailing YAML comment (`model: x  # why`).
_FIELD = re.compile(r"^(?P<key>name|model):\s*(?P<value>[^\s#]+)\s*(?:#.*)?$", re.MULTILINE)


@dataclass(frozen=True)
class Finding:
    kind: str
    agent: str
    detail: str

    def render(self) -> str:
        return f"{self.kind}: {self.agent}: {self.detail}"


def table_aliases(rule_text: str) -> dict[str, str] | None:
    """The tier table's agent -> alias rows, or None when the rule carries no table."""
    if TABLE_HEADING not in rule_text:
        return None
    section = rule_text.split(TABLE_HEADING, 1)[1].split("\n#", 1)[0]
    rows = (_ROW.match(line) for line in section.splitlines())
    aliases = {row["agent"]: row["alias"] for row in rows if row}
    return aliases or None


def frontmatter_model(definition_text: str) -> tuple[str, str] | None:
    """A definition's (name, model), or None when its frontmatter declares no agent name."""
    if not definition_text.startswith("---\n"):
        return None
    header = definition_text.split("\n---", 1)[0]
    fields = {m["key"]: m["value"] for m in _FIELD.finditer(header)}
    return (fields["name"], fields.get("model", "")) if "name" in fields else None


def judge(aliases: dict[str, str], models: dict[str, str]) -> list[Finding]:
    """Every way the table and the definitions disagree, the declared floors aside."""
    findings = [
        Finding("no-agent", agent, "the tier table lists it, no definition declares it")
        for agent in sorted(aliases.keys() - models.keys())
    ]
    for agent in sorted(models):
        model, alias = models[agent], aliases.get(agent)
        floor = DECLARED_FLOORS.get(agent)
        if alias is None:
            findings.append(
                Finding("no-row", agent, f"model {model or '(none)'}, no tier-table row")
            )
        elif floor is not None and (model != floor or floor == alias):
            detail = f"declared floor {floor}, definition {model or '(none)'}, row {alias}"
            findings.append(Finding("stale-floor", agent, detail))
        elif floor is None and model != alias:
            detail = f"definition model {model or '(none)'}, tier-table alias {alias}"
            findings.append(Finding("mismatch", agent, detail))
    return findings


def gather(repo_root: Path) -> tuple[dict[str, str] | None, dict[str, str]]:
    """The table's rows and every definition's model, read from the checkout."""
    aliases = table_aliases((repo_root / ROUTING_RULE).read_text(encoding="utf-8"))
    models: dict[str, str] = {}
    for path in sorted((repo_root / AGENTS_DIR).glob("*.md")):
        declared = frontmatter_model(path.read_text(encoding="utf-8"))
        if declared is not None:
            models[declared[0]] = declared[1]
    return aliases, models


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--repo-root")
    repo_root = resolve_repo_root(parser.parse_args(argv).repo_root, script_dir=SCRIPT_DIR)
    try:
        aliases, models = gather(repo_root)
    except OSError as exc:
        print(f"model routing parity: cannot read the checkout: {exc}", file=sys.stderr)
        return 2
    if aliases is None:
        print(f"no-table: {ROUTING_RULE} has no readable '{TABLE_HEADING}'")
        return 1
    findings = judge(aliases, models)
    for finding in findings:
        print(finding.render())
    print(f"model routing parity: {len(models)} agents, {len(findings)} finding(s)")
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
