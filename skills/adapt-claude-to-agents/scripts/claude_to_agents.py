#!/usr/bin/env python3
"""Generate a project-local AGENTS.md.tmpl from a project's CLAUDE.md."""

from __future__ import annotations

import argparse
import re
from dataclasses import dataclass
from pathlib import Path


HEADING_RE = re.compile(r"^(#{1,6})\s+(.*\S)\s*$")

EXCLUDED_HEADING_PATTERNS = (
    re.compile(r"known claude code limitations", re.IGNORECASE),
)

EXCLUDED_LINE_PATTERNS = (
    re.compile(r"claude plugin install", re.IGNORECASE),
    re.compile(r"install_claude\.sh", re.IGNORECASE),
    re.compile(r"Claude Desktop", re.IGNORECASE),
    re.compile(r"/reload-plugins"),
    re.compile(r"\.claude/plugins/cache"),
)

LINE_REPLACEMENTS = (
    (
        "The operational infrastructure for the development philosophy in "
        "`~/.claude/CLAUDE.md`.",
        "The operational infrastructure for this project's shared development "
        "philosophy.",
    ),
    (
        "1. **CLAUDE.md** (this file) — Praxion-specific agent baseline",
        "1. **CLAUDE.md** — canonical Praxion project baseline",
    ),
    (
        "- `bash install.sh` — install plugin to `~/.claude` (registers rules, hooks, settings)",
        "- `bash install.sh` — install or refresh Praxion-managed assistant surfaces",
    ),
    (
        "**Praxion-specific principles** (extend `~/.claude/CLAUDE.md`):",
        "**Praxion-specific principles** (extend the shared Praxion baseline philosophy):",
    ),
    (
        "- `/sentinel` — ecosystem coherence audit",
        "- Run the `sentinel` agent — ecosystem coherence audit",
    ),
    (
        "**Worktrees**: `.claude/worktrees/<name>/`. Pipeline worktrees via `EnterWorktree`; scratch via `/create-worktree`. ADRs created in a pipeline land as fragments under `.ai-state/decisions/drafts/` and are promoted to `dec-NNN` at merge-to-main by `scripts/finalize_adrs.py`. PR-adjacent workflow conventions live in `rules/swe/vcs/pr-conventions.md` (path-scoped).",
        "**Worktrees**: Praxion's canonical worktree home is `.claude/worktrees/<name>/`. Follow the worktree workflows in `commands/create-worktree.md` and `commands/merge-worktree.md`. ADRs created in a pipeline land as fragments under `.ai-state/decisions/drafts/` and are promoted to `dec-NNN` at merge-to-main by `scripts/finalize_adrs.py`. PR-adjacent workflow conventions live in `rules/swe/vcs/pr-conventions.md` (path-scoped).",
    ),
    (
        "**Onboarding artifacts dogfooding**: Praxion uses its own onboarding tools — Praxion's `.ai-state/`, `.gitattributes`, git hooks, and `CLAUDE.md` blocks are all results of patterns `/onboard-project` applies to user projects. When updating `/onboard-project` or `/new-project`, verify the change still produces what Praxion has on disk (or, if evolving the contract, propose what changes Praxion's own state needs).",
        "**Onboarding artifacts dogfooding**: Praxion uses its own onboarding tools — Praxion's `.ai-state/`, `.gitattributes`, git hooks, and `CLAUDE.md` blocks are all results of the patterns in `commands/onboard-project.md`. When updating `commands/onboard-project.md`, `commands/new-project.md`, or `new_project.sh`, verify the change still produces what Praxion has on disk (or, if evolving the contract, propose what changes Praxion's own state needs).",
    ),
    (
        "- **Greenfield** (empty dir): `new_project.sh` + `/new-project` — bash entry validates prereqs and scaffolds, then `exec`s a Claude Code session that runs the seed pipeline and chains to `/onboard-project`. Companion: `docs/greenfield-onboarding.md`.",
        "- **Greenfield** (empty dir): `new_project.sh` + the workflow in `commands/new-project.md` — the bash entry validates prereqs and scaffolds, then launches the seed workflow and chains to `commands/onboard-project.md`. Companion: `docs/greenfield-onboarding.md`.",
    ),
    (
        "- **Existing project** (has code): `/onboard-project` — phased, gated, idempotent (10 phases, 9 gates). Phase 8 optionally produces `.ai-state/DESIGN.md` + `docs/architecture.md`; Phase 8b installs the AaC tier; Phase 8c scaffolds ML/AI training conventions when detected. Companion: `docs/existing-project-onboarding.md`.",
        "- **Existing project** (has code): `commands/onboard-project.md` — phased, gated, idempotent (10 phases, 9 gates). Phase 8 optionally produces `.ai-state/DESIGN.md` + `docs/architecture.md`; Phase 8b installs the AaC tier; Phase 8c scaffolds ML/AI training conventions when detected. Companion: `docs/existing-project-onboarding.md`.",
    ),
    (" (or `/dashboard` from a Claude Code session)", ""),
)

GENERATOR_NOTE = (
    "<!-- Generated from CLAUDE.md by Praxion Codex install. Review and refine "
    "for Codex-specific project guidance. Edit this file, not AGENTS.md. -->"
)


@dataclass(frozen=True)
class Section:
    level: int
    title: str
    heading: str
    body: list[str]


def apply_line_replacements(line: str) -> str:
    updated = line
    for old, new in LINE_REPLACEMENTS:
        updated = updated.replace(old, new)
    return updated.rstrip()


def split_sections(text: str) -> list[Section]:
    sections: list[Section] = []
    current_level: int | None = None
    current_title: str | None = None
    current_heading: str | None = None
    current_body: list[str] = []

    for raw_line in text.splitlines():
        match = HEADING_RE.match(raw_line)
        if match is not None:
            if current_level is not None and current_title is not None and current_heading is not None:
                sections.append(
                    Section(
                        level=current_level,
                        title=current_title,
                        heading=current_heading,
                        body=current_body[:],
                    )
                )
            current_level = len(match.group(1))
            current_title = match.group(2).strip()
            current_heading = raw_line.strip()
            current_body = []
            continue

        if current_level is None:
            continue
        current_body.append(raw_line)

    if current_level is not None and current_title is not None and current_heading is not None:
        sections.append(
            Section(
                level=current_level,
                title=current_title,
                heading=current_heading,
                body=current_body[:],
            )
        )
    return sections


def heading_is_excluded(title: str) -> bool:
    return any(pattern.search(title) for pattern in EXCLUDED_HEADING_PATTERNS)


def normalize_lines(lines: list[str]) -> list[str]:
    normalized: list[str] = []
    previous_blank = True

    for raw_line in lines:
        line = apply_line_replacements(raw_line)
        stripped = line.strip()
        if any(pattern.search(line) for pattern in EXCLUDED_LINE_PATTERNS):
            continue
        if not stripped:
            if previous_blank:
                continue
            normalized.append("")
            previous_blank = True
            continue
        normalized.append(line)
        previous_blank = False

    while normalized and not normalized[0].strip():
        normalized.pop(0)
    while normalized and not normalized[-1].strip():
        normalized.pop()
    return normalized


def rewrite_heading(section: Section) -> str:
    if section.level == 2 and section.title.lower() == "agent reading order":
        return "## Reading Order"
    if section.level == 2 and section.title.lower() == "claude-code-specific machinery":
        return "## Project Operations"
    return section.heading


def render_project_template(claude_text: str, project_name: str) -> str:
    sections = split_sections(claude_text)
    if not sections:
        raise RuntimeError("CLAUDE.md did not contain any Markdown headings to adapt.")

    first = sections[0]
    title = first.title if first.level == 1 else project_name
    intro_lines = normalize_lines(first.body if first.level == 1 else [])

    blocks = [GENERATOR_NOTE, f"# Agent Instructions for {title}"]
    if intro_lines:
        blocks.append("\n".join(intro_lines))

    remaining = sections[1:] if first.level == 1 else sections
    for section in remaining:
        if heading_is_excluded(section.title):
            continue
        body_lines = normalize_lines(section.body)
        if not body_lines:
            continue
        blocks.append(rewrite_heading(section))
        blocks.append("\n".join(body_lines))

    rendered = "\n\n".join(block for block in blocks if block.strip())
    return rendered.rstrip() + "\n"


def derive_project_name(project_root: Path, claude_text: str) -> str:
    sections = split_sections(claude_text)
    if sections and sections[0].level == 1:
        return sections[0].title
    return project_root.name


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", required=True, type=Path)
    parser.add_argument("--claude-md", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    project_root = args.project_root.resolve()
    claude_path = args.claude_md.resolve()
    output_path = args.output.resolve()

    if not claude_path.exists():
        raise SystemExit(f"CLAUDE.md not found: {claude_path}")

    claude_text = claude_path.read_text(encoding="utf-8")
    project_name = derive_project_name(project_root, claude_text)
    rendered = render_project_template(claude_text, project_name)
    output_path.write_text(rendered, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
