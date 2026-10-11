"""Driver for the sentinel's skill-frontmatter key check, observed from outside.

The artifact-conformance family runs as `check_artifact_conformance.py --json --repo-root <root>`
on a scratch repository holding one skill. The contract assumed of its JSON output: a `findings`
list whose frontmatter-key entries carry `check: "N03"`, an `entity` naming the skill's
`SKILL.md`, and a `message` quoting the unrecognized key in backticks. A key is accepted when no
such finding names it.

Nothing here imports the system under test.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
CONFORMANCE = REPO_ROOT / "scripts" / "check_artifact_conformance.py"


def frontmatter_key_findings(sandbox: Path, skill: str, skill_text: str) -> list[dict]:
    """The frontmatter-key findings the check reports for one skill in a scratch repository."""
    skill_dir = sandbox / "skills" / skill
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(skill_text, encoding="utf-8")
    env = {k: v for k, v in os.environ.items() if not k.startswith(("CLAUDE", "PRAXION_"))}
    result = subprocess.run(
        [sys.executable, str(CONFORMANCE), "--json", "--repo-root", str(sandbox)],
        cwd=sandbox, env=env, capture_output=True, text=True, timeout=300,
    )  # fmt: skip
    if result.returncode != 0:
        raise AssertionError(
            f"the conformance family exited {result.returncode}: {result.stderr[-1500:]}"
        )
    return [
        f
        for f in json.loads(result.stdout).get("findings", [])
        if f.get("check") == "N03" and f"skills/{skill}/" in str(f.get("entity", ""))
    ]


def accepts(findings: list[dict], key: str) -> bool:
    return not [f for f in findings if f"`{key}`" in str(f.get("message", ""))]
