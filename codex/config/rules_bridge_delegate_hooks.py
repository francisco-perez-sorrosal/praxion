#!/usr/bin/env python3
"""Renders the Codex hook wrapper scripts that delegate to a canonical Praxion hook."""

from __future__ import annotations

DELEGATE_KINDS = frozenset(
    {
        "decisions-session-start",
        "observability-session-start",
        "observability-stop",
        "observability-pre-tool-use",
        "observability-post-tool-use",
        "process-framing-user-prompt-submit",
        "subagent-pre-tool-use",
        "worktree-guard-pre-tool-use",
        "commit-quality-pre-tool-use",
        "commit-adr-pre-tool-use",
        "cleanup-learnings-pre-tool-use",
        "commit-id-citation-pre-tool-use",
        "format-python-post-tool-use",
        "detect-duplication-post-tool-use",
        "observability-subagent-start",
        "observability-subagent-stop",
        "precompact-state",
    }
)


def render_delegate_hook_script(kind: str) -> str:
    if kind == "decisions-session-start":
        return """#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

HELPER_DIR = Path(__file__).resolve().parents[1] / "praxion"
sys.path.insert(0, str(HELPER_DIR))

from hook_runtime import payload_has_ai_state, run_canonical_hook


def main() -> int:
    raw = sys.stdin.read()
    if not payload_has_ai_state(raw):
        return 0
    return run_canonical_hook("hooks/inject_decisions.py", raw)


if __name__ == "__main__":
    raise SystemExit(main())
"""
    elif kind == "observability-session-start":
        return """#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

HELPER_DIR = Path(__file__).resolve().parents[1] / "praxion"
sys.path.insert(0, str(HELPER_DIR))

from hook_runtime import run_canonical_hook


def main() -> int:
    raw = sys.stdin.read()
    status = run_canonical_hook("hooks/send_event.py", raw)
    lifecycle_status = run_canonical_hook("hooks/capture_session.py", raw)
    surface_status = run_canonical_hook("hooks/measure_context_surface.py", raw)
    return surface_status or lifecycle_status or status


if __name__ == "__main__":
    raise SystemExit(main())
"""
    elif kind == "observability-stop":
        return """#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

HELPER_DIR = Path(__file__).resolve().parents[1] / "praxion"
sys.path.insert(0, str(HELPER_DIR))

from hook_runtime import run_canonical_hook


def main() -> int:
    raw = sys.stdin.read()
    status = run_canonical_hook("hooks/send_event.py", raw)
    lifecycle_status = run_canonical_hook("hooks/capture_session.py", raw)
    return lifecycle_status or status


if __name__ == "__main__":
    raise SystemExit(main())
"""
    elif kind == "observability-pre-tool-use":
        return """#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

HELPER_DIR = Path(__file__).resolve().parents[1] / "praxion"
sys.path.insert(0, str(HELPER_DIR))

from hook_runtime import run_canonical_hook


def main() -> int:
    raw = sys.stdin.read()
    return run_canonical_hook("hooks/send_event.py", raw)


if __name__ == "__main__":
    raise SystemExit(main())
"""
    elif kind == "observability-post-tool-use":
        return """#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

HELPER_DIR = Path(__file__).resolve().parents[1] / "praxion"
sys.path.insert(0, str(HELPER_DIR))

from hook_runtime import run_canonical_hook


def main() -> int:
    raw = sys.stdin.read()
    status = run_canonical_hook("hooks/send_event.py", raw)
    capture_status = run_canonical_hook("hooks/capture_memory.py", raw)
    return capture_status or status


if __name__ == "__main__":
    raise SystemExit(main())
"""
    elif kind == "process-framing-user-prompt-submit":
        return """#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

HELPER_DIR = Path(__file__).resolve().parents[1] / "praxion"
sys.path.insert(0, str(HELPER_DIR))

from hook_runtime import run_canonical_hook


def main() -> int:
    raw = sys.stdin.read()
    return run_canonical_hook("hooks/inject_process_framing.py", raw)


if __name__ == "__main__":
    raise SystemExit(main())
"""
    elif kind == "subagent-pre-tool-use":
        return """#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path

HELPER_DIR = Path(__file__).resolve().parents[1] / "praxion"
sys.path.insert(0, str(HELPER_DIR))

from hook_runtime import run_canonical_hook


def _normalize_task_payload(raw: str) -> str:
    try:
        payload = json.loads(raw or "{}")
    except json.JSONDecodeError:
        return raw
    if payload.get("tool_name") == "Task":
        payload["tool_name"] = "Agent"
        return json.dumps(payload)
    return raw


def main() -> int:
    raw = sys.stdin.read()
    return run_canonical_hook("hooks/inject_subagent_context.py", _normalize_task_payload(raw))


if __name__ == "__main__":
    raise SystemExit(main())
"""
    elif kind == "worktree-guard-pre-tool-use":
        return """#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

HELPER_DIR = Path(__file__).resolve().parents[1] / "praxion"
sys.path.insert(0, str(HELPER_DIR))

from hook_runtime import run_canonical_hook


def main() -> int:
    raw = sys.stdin.read()
    return run_canonical_hook("hooks/worktree_guard.py", raw)


if __name__ == "__main__":
    raise SystemExit(main())
"""
    elif kind == "commit-quality-pre-tool-use":
        return """#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

HELPER_DIR = Path(__file__).resolve().parents[1] / "praxion"
sys.path.insert(0, str(HELPER_DIR))

from hook_runtime import run_canonical_command


def main() -> int:
    raw = sys.stdin.read()
    return run_canonical_command(["hooks/commit_gate.sh", "hooks/check_code_quality.py"], raw)


if __name__ == "__main__":
    raise SystemExit(main())
"""
    elif kind == "commit-adr-pre-tool-use":
        return """#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

HELPER_DIR = Path(__file__).resolve().parents[1] / "praxion"
sys.path.insert(0, str(HELPER_DIR))

from hook_runtime import run_canonical_command


def main() -> int:
    raw = sys.stdin.read()
    return run_canonical_command(["hooks/commit_gate.sh", "hooks/remind_adr.py"], raw)


if __name__ == "__main__":
    raise SystemExit(main())
"""
    elif kind == "cleanup-learnings-pre-tool-use":
        return """#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

HELPER_DIR = Path(__file__).resolve().parents[1] / "praxion"
sys.path.insert(0, str(HELPER_DIR))

from hook_runtime import run_canonical_command


def main() -> int:
    raw = sys.stdin.read()
    return run_canonical_command(["hooks/cleanup_gate.sh", "hooks/promote_learnings.py"], raw)


if __name__ == "__main__":
    raise SystemExit(main())
"""
    elif kind == "commit-id-citation-pre-tool-use":
        return """#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

HELPER_DIR = Path(__file__).resolve().parents[1] / "praxion"
sys.path.insert(0, str(HELPER_DIR))

from hook_runtime import run_canonical_command


def main() -> int:
    raw = sys.stdin.read()
    return run_canonical_command(
        ["hooks/commit_gate.sh", "scripts/check_id_citation_discipline.py"],
        raw,
    )


if __name__ == "__main__":
    raise SystemExit(main())
"""
    elif kind == "format-python-post-tool-use":
        return """#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

HELPER_DIR = Path(__file__).resolve().parents[1] / "praxion"
sys.path.insert(0, str(HELPER_DIR))

from hook_runtime import run_canonical_hook


def main() -> int:
    raw = sys.stdin.read()
    return run_canonical_hook("hooks/format_python.py", raw)


if __name__ == "__main__":
    raise SystemExit(main())
"""
    elif kind == "detect-duplication-post-tool-use":
        return """#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

HELPER_DIR = Path(__file__).resolve().parents[1] / "praxion"
sys.path.insert(0, str(HELPER_DIR))

from hook_runtime import run_canonical_hook


def main() -> int:
    raw = sys.stdin.read()
    return run_canonical_hook("hooks/detect_duplication.py", raw)


if __name__ == "__main__":
    raise SystemExit(main())
"""
    elif kind == "observability-subagent-start":
        return """#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

HELPER_DIR = Path(__file__).resolve().parents[1] / "praxion"
sys.path.insert(0, str(HELPER_DIR))

from hook_runtime import run_canonical_hook


def main() -> int:
    raw = sys.stdin.read()
    status = run_canonical_hook("hooks/send_event.py", raw)
    lifecycle_status = run_canonical_hook("hooks/capture_session.py", raw)
    return lifecycle_status or status


if __name__ == "__main__":
    raise SystemExit(main())
"""
    elif kind == "observability-subagent-stop":
        return """#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

HELPER_DIR = Path(__file__).resolve().parents[1] / "praxion"
sys.path.insert(0, str(HELPER_DIR))

from hook_runtime import run_canonical_hook


def main() -> int:
    raw = sys.stdin.read()
    status = run_canonical_hook("hooks/send_event.py", raw)
    lifecycle_status = run_canonical_hook("hooks/capture_session.py", raw)
    return lifecycle_status or status


if __name__ == "__main__":
    raise SystemExit(main())
"""
    elif kind == "precompact-state":
        return """#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

HELPER_DIR = Path(__file__).resolve().parents[1] / "praxion"
sys.path.insert(0, str(HELPER_DIR))

from hook_runtime import run_canonical_hook


def main() -> int:
    raw = sys.stdin.read()
    return run_canonical_hook("hooks/precompact_state.py", raw)


if __name__ == "__main__":
    raise SystemExit(main())
"""
    else:
        raise ValueError(f"unsupported delegate hook kind: {kind}")
