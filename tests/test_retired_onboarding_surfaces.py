"""The unified onboarding skill replaced the two commands, the root script, and its test.

The cut must be atomic: shipping the skill and a same-named command together would
register duplicate `/praxion:onboard-project` surfaces, and a surviving root script
would resurrect the retired `new-project` entry point.
"""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

RETIRED = (
    "commands/onboard-project.md",
    "commands/new-project.md",
    "new_project.sh",
    "tests/new_project_test.sh",
)

REPLACEMENTS = (
    "skills/onboard-project/SKILL.md",
    "scripts/onboard-project",
    "tests/onboard_project_test.sh",
)


def test_retired_surfaces_do_not_exist():
    survivors = [p for p in RETIRED if (REPO_ROOT / p).exists()]
    assert not survivors, f"retired onboarding surfaces still on disk: {survivors}"


def test_replacement_surfaces_exist():
    missing = [p for p in REPLACEMENTS if not (REPO_ROOT / p).exists()]
    assert not missing, f"replacement onboarding surfaces missing: {missing}"
