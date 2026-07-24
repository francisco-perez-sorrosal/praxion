#!/usr/bin/env python3
"""Thin entry point for the managed-project -> Praxion feedback reporter CLI.

All orchestration lives in `scripts.praxion_feedback.cli`; this module exists so
the reporter is invocable as a plain file from an installed-plugin cache
location (`python3 report_praxion_issue.py <subcommand> ...`) while `main` stays
importable for unit tests. The repo root is resolved at runtime by the CLI via
git / `--repo-root`, never from this file's `__file__` location.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Bootstrap the PLUGIN root onto sys.path so the absolute `from scripts...`
# import below resolves when this file is executed directly -- PATH-installed as
# `report_praxion_issue.py`, or `python3 scripts/report_praxion_issue.py`. Run
# as a plain script only `scripts/` is on the path, not its parent, so
# `import scripts` fails. This `__file__` use locates the plugin's OWN package
# to import; it is distinct from the CONSUMER repo root (where PENDING.md
# lives), which the CLI resolves via git / --repo-root, never from `__file__`.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.praxion_feedback.cli import main  # noqa: E402  (after sys.path bootstrap)

__all__ = ["main"]


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
