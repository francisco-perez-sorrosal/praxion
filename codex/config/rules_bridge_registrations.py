#!/usr/bin/env python3
"""Renders the Codex hook registration table (.codex/praxion/hook_registrations.json)."""

from __future__ import annotations

from pathlib import Path

HOOK_COMMAND_TEMPLATE = '/usr/bin/python3 "{hook_path}"'


def render_hook_registrations() -> dict[str, object]:
    def command(name: str, project_root: str) -> str:
        hook_path = Path(project_root) / ".codex" / "hooks" / name
        return HOOK_COMMAND_TEMPLATE.format(hook_path=hook_path.as_posix())

    project_root = "__PRAXION_PROJECT_ROOT__"
    return {
        "hooks": {
            "SessionStart": [
                {
                    "matcher": "startup|resume|clear",
                    "hooks": [
                        {
                            "type": "command",
                            "command": command("praxion-session-start.py", project_root),
                            "timeout": 30,
                            "statusMessage": "Praxion: loading always-on rules",
                        }
                    ],
                },
                {
                    "matcher": "startup|resume|clear",
                    "hooks": [
                        {
                            "type": "command",
                            "command": command("praxion-decisions-session-start.py", project_root),
                            "timeout": 30,
                            "statusMessage": "Praxion: injecting decision context",
                        }
                    ],
                },
                {
                    "matcher": "startup|resume|clear",
                    "hooks": [
                        {
                            "type": "command",
                            "command": command(
                                "praxion-observability-session-start.py", project_root
                            ),
                            "timeout": 15,
                            "statusMessage": "Praxion: capturing session start",
                        }
                    ],
                },
            ],
            "Stop": [
                {
                    "hooks": [
                        {
                            "type": "command",
                            "command": command("praxion-observability-stop.py", project_root),
                            "timeout": 15,
                            "statusMessage": "Praxion: capturing session stop",
                        }
                    ],
                },
            ],
            "UserPromptSubmit": [
                {
                    "hooks": [
                        {
                            "type": "command",
                            "command": command("praxion-user-prompt-submit.py", project_root),
                            "timeout": 30,
                            "statusMessage": "Praxion: routing prompt-scoped rules",
                        }
                    ],
                },
                {
                    "hooks": [
                        {
                            "type": "command",
                            "command": command(
                                "praxion-process-framing-user-prompt-submit.py",
                                project_root,
                            ),
                            "timeout": 15,
                            "statusMessage": "Praxion: injecting process framing",
                        }
                    ],
                },
            ],
            "PreToolUse": [
                {
                    "matcher": "Agent|Task",
                    "hooks": [
                        {
                            "type": "command",
                            "command": command("praxion-subagent-pre-tool-use.py", project_root),
                            "timeout": 15,
                            "statusMessage": "Praxion: injecting subagent contract",
                        }
                    ],
                },
                {
                    "matcher": "Bash",
                    "hooks": [
                        {
                            "type": "command",
                            "command": command(
                                "praxion-commit-quality-pre-tool-use.py", project_root
                            ),
                            "timeout": 30,
                            "statusMessage": "Praxion: checking commit quality",
                        },
                        {
                            "type": "command",
                            "command": command("praxion-commit-adr-pre-tool-use.py", project_root),
                            "timeout": 30,
                            "statusMessage": "Praxion: checking ADR reminder",
                        },
                        {
                            "type": "command",
                            "command": command(
                                "praxion-cleanup-learnings-pre-tool-use.py",
                                project_root,
                            ),
                            "timeout": 15,
                            "statusMessage": "Praxion: checking learnings cleanup",
                        },
                        {
                            "type": "command",
                            "command": command(
                                "praxion-commit-id-citation-pre-tool-use.py",
                                project_root,
                            ),
                            "timeout": 20,
                            "statusMessage": "Praxion: checking id citations",
                        },
                    ],
                },
                {
                    "matcher": "Edit|MultiEdit|NotebookEdit|Write|apply_patch|ApplyPatch",
                    "hooks": [
                        {
                            "type": "command",
                            "command": command(
                                "praxion-worktree-guard-pre-tool-use.py", project_root
                            ),
                            "timeout": 15,
                            "statusMessage": "Praxion: checking worktree boundary",
                        }
                    ],
                },
                {
                    "matcher": "Edit|MultiEdit|NotebookEdit|Write|apply_patch|ApplyPatch",
                    "hooks": [
                        {
                            "type": "command",
                            "command": command("praxion-pre-tool-use.py", project_root),
                            "timeout": 30,
                            "statusMessage": "Praxion: routing file-scoped rules",
                        }
                    ],
                },
                {
                    "hooks": [
                        {
                            "type": "command",
                            "command": command(
                                "praxion-observability-pre-tool-use.py", project_root
                            ),
                            "timeout": 15,
                            "statusMessage": "Praxion: capturing tool start",
                        }
                    ],
                },
            ],
            "PostToolUse": [
                {
                    "hooks": [
                        {
                            "type": "command",
                            "command": command(
                                "praxion-observability-post-tool-use.py", project_root
                            ),
                            "timeout": 15,
                            "statusMessage": "Praxion: capturing tool result",
                        }
                    ],
                },
                {
                    "matcher": "Write|Edit",
                    "hooks": [
                        {
                            "type": "command",
                            "command": command(
                                "praxion-format-python-post-tool-use.py", project_root
                            ),
                            "timeout": 15,
                            "statusMessage": "Praxion: formatting Python",
                        },
                        {
                            "type": "command",
                            "command": command(
                                "praxion-detect-duplication-post-tool-use.py",
                                project_root,
                            ),
                            "timeout": 15,
                            "statusMessage": "Praxion: detecting duplication",
                        },
                    ],
                },
            ],
            "SubagentStart": [
                {
                    "hooks": [
                        {
                            "type": "command",
                            "command": command(
                                "praxion-observability-subagent-start.py", project_root
                            ),
                            "timeout": 15,
                            "statusMessage": "Praxion: capturing subagent start",
                        }
                    ],
                }
            ],
            "SubagentStop": [
                {
                    "hooks": [
                        {
                            "type": "command",
                            "command": command(
                                "praxion-observability-subagent-stop.py", project_root
                            ),
                            "timeout": 15,
                            "statusMessage": "Praxion: capturing subagent stop",
                        }
                    ],
                },
            ],
            "PreCompact": [
                {
                    "hooks": [
                        {
                            "type": "command",
                            "command": command("praxion-precompact-state.py", project_root),
                            "timeout": 15,
                            "statusMessage": "Praxion: snapshotting pipeline state",
                        }
                    ],
                }
            ],
        }
    }
