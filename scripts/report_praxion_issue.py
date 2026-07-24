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

from scripts.praxion_feedback.cli import main

__all__ = ["main"]


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
