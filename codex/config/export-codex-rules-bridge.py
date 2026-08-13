#!/usr/bin/env python3
"""Export a Praxion rules bridge for Codex project-local hooks."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_MODULE_DIR = Path(__file__).resolve().parent
if str(_MODULE_DIR) not in sys.path:
    sys.path.insert(0, str(_MODULE_DIR))

from rules_bridge_delegate_hooks import (  # noqa: E402
    DELEGATE_KINDS,
    render_delegate_hook_script,
)
from rules_bridge_parsing import build_manifest  # noqa: E402
from rules_bridge_registrations import render_hook_registrations  # noqa: E402
from rules_bridge_routing_hooks import ROUTING_KINDS, render_routing_hook_script  # noqa: E402
from rules_bridge_static_modules import (  # noqa: E402
    render_hook_runtime_module,
    render_lookup_module,
)


def render_hook_script(kind: str) -> str:
    if kind in ROUTING_KINDS:
        return render_routing_hook_script(kind)
    if kind in DELEGATE_KINDS:
        return render_delegate_hook_script(kind)
    raise ValueError(f"unsupported hook kind: {kind}")


def export_rules_bridge(repo_root: Path, out_dir: Path) -> list[Path]:
    codex_dir = out_dir
    praxion_dir = codex_dir / "praxion"
    hooks_dir = codex_dir / "hooks"
    praxion_dir.mkdir(parents=True, exist_ok=True)
    hooks_dir.mkdir(parents=True, exist_ok=True)

    manifest = build_manifest(repo_root)
    written: list[Path] = []

    manifest_path = praxion_dir / "rules_manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    written.append(manifest_path)

    lookup_path = praxion_dir / "rules_lookup.py"
    lookup_path.write_text(render_lookup_module(), encoding="utf-8")
    written.append(lookup_path)

    runtime_path = praxion_dir / "hook_runtime.py"
    runtime_path.write_text(render_hook_runtime_module(repo_root), encoding="utf-8")
    written.append(runtime_path)

    for hook_name, kind in [
        ("praxion-session-start.py", "session-start"),
        ("praxion-decisions-session-start.py", "decisions-session-start"),
        ("praxion-observability-session-start.py", "observability-session-start"),
        ("praxion-observability-stop.py", "observability-stop"),
        ("praxion-user-prompt-submit.py", "user-prompt-submit"),
        (
            "praxion-process-framing-user-prompt-submit.py",
            "process-framing-user-prompt-submit",
        ),
        ("praxion-subagent-pre-tool-use.py", "subagent-pre-tool-use"),
        ("praxion-commit-quality-pre-tool-use.py", "commit-quality-pre-tool-use"),
        ("praxion-commit-adr-pre-tool-use.py", "commit-adr-pre-tool-use"),
        ("praxion-cleanup-learnings-pre-tool-use.py", "cleanup-learnings-pre-tool-use"),
        (
            "praxion-commit-id-citation-pre-tool-use.py",
            "commit-id-citation-pre-tool-use",
        ),
        ("praxion-worktree-guard-pre-tool-use.py", "worktree-guard-pre-tool-use"),
        ("praxion-pre-tool-use.py", "pre-tool-use"),
        ("praxion-observability-pre-tool-use.py", "observability-pre-tool-use"),
        ("praxion-observability-post-tool-use.py", "observability-post-tool-use"),
        ("praxion-format-python-post-tool-use.py", "format-python-post-tool-use"),
        (
            "praxion-detect-duplication-post-tool-use.py",
            "detect-duplication-post-tool-use",
        ),
        ("praxion-observability-subagent-start.py", "observability-subagent-start"),
        ("praxion-observability-subagent-stop.py", "observability-subagent-stop"),
        ("praxion-precompact-state.py", "precompact-state"),
    ]:
        hook_path = hooks_dir / hook_name
        hook_path.write_text(render_hook_script(kind), encoding="utf-8")
        written.append(hook_path)

    registrations_path = praxion_dir / "hook_registrations.json"
    registrations_path.write_text(
        json.dumps(render_hook_registrations(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    written.append(registrations_path)
    return written


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=".", type=Path)
    parser.add_argument("--out-dir", required=True, type=Path)
    args = parser.parse_args()

    written = export_rules_bridge(args.repo_root.resolve(), args.out_dir.resolve())
    for path in written:
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
