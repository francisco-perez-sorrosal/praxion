"""The command artifact family is gone everywhere a reader, agent or tool would meet it."""

from __future__ import annotations

import re
import subprocess

import pytest
import yaml

from tests.acceptance.drivers.command_migration import names
from tests.acceptance.drivers.retired_surface import (
    FROZEN_HISTORY,
    LIVE_REFERENCE,
    NAMED_EXCEPTIONS,
    REPO_ROOT,
    agent_definitions,
    always_loaded_files,
    canonical_blocks,
    glob_matches,
    lines_matching,
    read_text,
)

USER_INVOKED_GUIDE = "skills/skill-crafting/references/user-invoked-skills.md"


# --- one place to learn how to author a user-invoked skill ------------------------------------


def test_the_command_authoring_skill_no_longer_exists():
    assert not (REPO_ROOT / "skills" / "command-crafting").exists()


def test_user_invoked_skill_guidance_is_reachable_from_skill_authoring():
    skill = read_text("skills/skill-crafting/SKILL.md") or ""

    assert (REPO_ROOT / USER_INVOKED_GUIDE).is_file()
    assert re.search(r"\]\((\./)?references/user-invoked-skills\.md", skill)


# Each topic the guide must cover, as patterns one paragraph of it carries together.
GUIDE_TOPICS = {
    "description-length-by-consumer": (
        r"description",
        r"user[- ]only|disable-model-invocation",
        r"model[- ]invo",
    ),
    "argument-hint-rules": (r"argument-hint", r"quot", r"omit|no arguments"),
    "whole-argument-placeholder": (r"\$ARGUMENTS\b",),
    "zero-based-indexed-arguments": (r"\$0", r"first"),
    "named-arguments-suppress-the-append": (r"arguments:", r"append"),
    "command-output-injected-before-render": (r"!`|output", r"before"),
    "skill-and-plugin-root-variables": (r"CLAUDE_SKILL_DIR", r"CLAUDE_PLUGIN_ROOT"),
    "runtime-and-permissions": (r"allowed-tools", r"permission"),
    "silent-frontmatter-parse-failure": (r"frontmatter", r"pars", r"silent"),
    "convert-a-command-file": (r"convert", r"command"),
}


@pytest.mark.parametrize("topic", sorted(GUIDE_TOPICS))
def test_the_user_invoked_skill_guide_covers_each_authoring_topic(topic):
    text = read_text(USER_INVOKED_GUIDE) or ""
    paragraphs = re.split(r"\n\s*\n", text.replace("`", ""))
    covering = [
        p for p in paragraphs if all(re.search(x, p, re.IGNORECASE) for x in GUIDE_TOPICS[topic])
    ]

    assert covering, f"no paragraph of {USER_INVOKED_GUIDE} covers {topic}"


def test_nothing_outside_frozen_history_refers_to_the_retired_authoring_skill():
    hits = lines_matching(
        re.compile(r"command-crafting"), exempt=(FROZEN_HISTORY, re.compile(r"^tests/acceptance/"))
    )

    assert not hits, "\n".join(hits[:40])


# --- no live reference to the retired directory -----------------------------------------------


def test_nothing_outside_frozen_history_and_named_exceptions_points_at_the_retired_directory():
    hits = lines_matching(LIVE_REFERENCE, exempt=(FROZEN_HISTORY, NAMED_EXCEPTIONS))

    assert not hits, f"{len(hits)} live references, first ones:\n" + "\n".join(hits[:40])


def test_the_reference_validator_is_clean_in_strict_mode():
    result = subprocess.run(
        ["python3", "skills/skill-crafting/scripts/validate_references.py", "--all", "--strict"],
        cwd=REPO_ROOT, capture_output=True, text=True, timeout=300,
    )  # fmt: skip

    assert result.returncode == 0, result.stdout[-2000:] + result.stderr[-1000:]


# --- the always-loaded set, the agents and the shipped blocks teach no command family ---------

COMMAND_VOCABULARY = re.compile(r"slash[- ]commands?|custom[- ]commands?|commands/", re.IGNORECASE)
PLATFORM_VOCABULARY = re.compile(
    r"--?disable-slash-commands|\.claude/commands/?|built-in (slash )?commands?|tests/commands/",
    re.IGNORECASE,
)
TAUGHT_SURFACES = always_loaded_files() + agent_definitions() + canonical_blocks()


@pytest.mark.parametrize("relative", TAUGHT_SURFACES)
def test_a_taught_surface_uses_command_vocabulary_only_for_the_platform(relative):
    text = read_text(relative) or ""
    offending = [
        f"{n}: {line.strip()[:160]}"
        for n, line in enumerate(text.splitlines(), 1)
        if COMMAND_VOCABULARY.search(PLATFORM_VOCABULARY.sub("", line))
    ]

    assert not offending, "\n".join(offending)


# --- the pull-request conventions load for exactly three skills -------------------------------

PR_SCOPE = {
    ".github/**/*.md",
    "rules/swe/vcs/git-conventions.md",
    "skills/review-pr/SKILL.md",
    "skills/merge-worktree/SKILL.md",
    "skills/release/SKILL.md",
}
PR_SKILLS = {"review-pr", "merge-worktree", "release"}


def _pr_rule_paths() -> list[str]:
    text = read_text("rules/swe/vcs/pr-conventions.md") or ""
    return list(yaml.safe_load(text.split("---", 2)[1]).get("paths") or [])


def test_the_pull_request_conventions_scope_names_exactly_the_decided_paths():
    assert set(_pr_rule_paths()) == PR_SCOPE


def test_the_generated_rules_manifest_records_the_same_scope():
    manifest = yaml.safe_load(read_text("rules/_manifest.yaml") or "")
    entry = next(r for r in manifest["rules"] if r["path"] == "rules/swe/vcs/pr-conventions.md")

    assert set(entry.get("paths") or []) == PR_SCOPE


def test_the_pull_request_conventions_load_for_no_other_skill():
    skills = sorted(p.parent.name for p in (REPO_ROOT / "skills").glob("*/SKILL.md"))
    loading = {
        s for s in skills if any(glob_matches(g, f"skills/{s}/SKILL.md") for g in _pr_rule_paths())
    }

    assert loading == PR_SKILLS


# --- the architecture model has no commands element -------------------------------------------


@pytest.mark.parametrize("relative", [".ai-state/DESIGN.md", "docs/architecture.md"])
def test_the_architecture_documents_carry_no_commands_element(relative):
    text = read_text(relative) or ""

    assert "knowledge.commands" not in text
    assert not re.search(
        r"^\|\s*[*`]*(slash )?commands?[*`]*\s*\|", text, re.IGNORECASE | re.MULTILINE
    ), "a table row still names a commands component"


def test_the_architecture_model_sources_carry_no_commands_element():
    sources = [
        p for p in (REPO_ROOT / "docs" / "diagrams").rglob("*.c4") if "node_modules" not in p.parts
    ]
    offending = [
        str(p.relative_to(REPO_ROOT))
        for p in sources
        if re.search(r"\bcommands\s*=", p.read_text(encoding="utf-8"))
    ]

    assert sources, "no architecture model source found under docs/diagrams"
    assert not offending, offending


def test_the_architecture_projection_check_passes():
    result = subprocess.run(
        ["python3", "scripts/check_architecture_projection.py"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=300,
    )

    assert result.returncode == 0, result.stdout[-2000:] + result.stderr[-1000:]


# --- the skills catalog and the readme counts --------------------------------------------------


def _skill_dirs() -> list[str]:
    return sorted(p.parent.name for p in (REPO_ROOT / "skills").glob("*/SKILL.md"))


@pytest.mark.parametrize("skill", sorted(set(_skill_dirs()) | set(names())))
def test_the_skills_catalog_has_a_row_for_every_skill(skill):
    catalog = read_text("skills/README.md") or ""

    assert re.search(rf"^\|.*\[{re.escape(skill)}\]\({re.escape(skill)}/?", catalog, re.MULTILINE)


def test_the_skills_catalog_has_no_row_for_the_retired_authoring_skill():
    assert "[command-crafting]" not in (read_text("skills/README.md") or "")


COUNT_STATEMENT = re.compile(
    r"\b(\d+)\s+(?:[\w-]+\s+){0,2}?(skills|agents|slash commands|commands|workflows)\b",
    re.IGNORECASE,
)


def _on_disk(noun: str) -> int:
    noun = noun.lower()
    if noun == "skills":
        return len(_skill_dirs())
    if noun == "agents":
        return len(agent_definitions())
    if noun == "workflows":
        return sum((REPO_ROOT / "skills" / n / "SKILL.md").is_file() for n in names())
    return (
        len(list((REPO_ROOT / "commands").glob("*.md"))) if (REPO_ROOT / "commands").is_dir() else 0
    )


def test_every_count_the_readme_states_matches_the_disk():
    statements = [
        (int(m.group(1)), m.group(2))
        for m in COUNT_STATEMENT.finditer(read_text("README.md") or "")
    ]
    wrong = [
        f"{count} {noun} (disk: {_on_disk(noun)})"
        for count, noun in statements
        if count != _on_disk(noun)
    ]

    assert statements, "the readme states no count"
    assert not wrong, wrong
