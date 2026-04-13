"""OpenAI judge — Tier 1 shim preserving `trajectory_eval.py` behaviour.

This module is intentionally thin — it re-exports the existing CLI entrypoint
so `/eval judge --provider openai/gpt-4o` can delegate to the proven
`trajectory_eval.py` flow without duplicating logic. Phoenix + OpenAI imports
remain lazy inside ``main()``.
"""

from __future__ import annotations

from pathlib import Path


def main() -> int:
    """Delegate to the canonical trajectory_eval.py entrypoint (back-compat).

    Preferred: import the module by path so we do not require repo-root layout
    assumptions when invoked from a checkout. Returns the delegate's exit code.
    """
    import importlib.util
    import sys

    candidates = [
        Path(__file__).resolve().parents[4] / "trajectory_eval.py",
        Path.cwd() / "eval" / "trajectory_eval.py",
        Path.cwd() / "trajectory_eval.py",
    ]

    for script in candidates:
        if script.exists():
            spec = importlib.util.spec_from_file_location("trajectory_eval", script)
            if spec is None or spec.loader is None:
                continue
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            delegate = getattr(module, "main", None)
            if callable(delegate):
                result = delegate()
                return int(result) if isinstance(result, int) else 0

    print("trajectory_eval.py not found on disk", file=sys.stderr)
    return 1
