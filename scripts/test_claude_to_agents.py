from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = (
    REPO_ROOT
    / "skills"
    / "adapt-claude-to-agents"
    / "scripts"
    / "claude_to_agents.py"
)


def load_module():
    spec = importlib.util.spec_from_file_location("claude_to_agents", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_render_project_template_filters_claude_only_sections() -> None:
    module = load_module()
    claude_text = """# Sample Project

The operational infrastructure for the development philosophy in `~/.claude/CLAUDE.md`. This repo provides the shared artifacts.

## Agent reading order

1. **CLAUDE.md** (this file) — Praxion-specific agent baseline

## Build / test / lint

- `bash install.sh` — install plugin to `~/.claude` (registers rules, hooks, settings)
- `streamlit run app.py` (or `/dashboard` from a Claude Code session)

## How to verify your work

- `/sentinel` — ecosystem coherence audit

## Claude-Code-specific machinery

**Worktrees**: `.claude/worktrees/<name>/`. Pipeline worktrees via `EnterWorktree`; scratch via `/create-worktree`. ADRs created in a pipeline land as fragments under `.ai-state/decisions/drafts/` and are promoted to `dec-NNN` at merge-to-main by `scripts/finalize_adrs.py`. PR-adjacent workflow conventions live in `rules/swe/vcs/pr-conventions.md` (path-scoped).

## Critical conventions

- Never modify `~/.claude/plugins/cache/`
- **Praxion-specific principles** (extend `~/.claude/CLAUDE.md`): token budget first-class.
- Keep `tmp/` for temporary files.

## Known Claude Code Limitations

This whole section should disappear too.
"""

    rendered = module.render_project_template(claude_text, "sample-project")

    assert rendered.startswith("<!-- Generated from CLAUDE.md")
    assert "# Agent Instructions for Sample Project" in rendered
    assert "shared development philosophy" in rendered
    assert "## Reading Order" in rendered
    assert "## Project Operations" in rendered
    assert "Claude-Code-specific machinery" not in rendered
    assert "Known Claude Code Limitations" not in rendered
    assert "~/.claude/plugins/cache/" not in rendered
    assert "/dashboard" not in rendered
    assert "canonical Praxion project baseline" in rendered
    assert "install or refresh Praxion-managed assistant surfaces" in rendered
    assert "Run the `sentinel` agent" in rendered
    assert "commands/create-worktree.md" in rendered
    assert "shared Praxion baseline philosophy" in rendered
    assert "Keep `tmp/` for temporary files." in rendered


def test_render_project_template_uses_project_name_without_h1() -> None:
    module = load_module()
    claude_text = """## Build / test / lint

- `pytest`
"""

    rendered = module.render_project_template(claude_text, "demo-project")

    assert "# Agent Instructions for demo-project" in rendered
    assert "## Build / test / lint" in rendered


def test_praxion_root_agents_template_matches_generator() -> None:
    module = load_module()
    claude_text = (REPO_ROOT / "CLAUDE.md").read_text(encoding="utf-8")

    rendered = module.render_project_template(claude_text, REPO_ROOT.name)
    expected = (REPO_ROOT / "AGENTS.md.tmpl").read_text(encoding="utf-8")

    assert rendered == expected
