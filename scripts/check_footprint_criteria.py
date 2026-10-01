#!/usr/bin/env python3
"""Footprint criteria check: does a change that moves a footprint carry a measured bound?

    check_footprint_criteria.py <slug> [--stage spec|plan|verify] [--paths PATH ...]
            [--base-ref REF] [--repo-root DIR] [--json]

The grammars of the spec tables, the registry and the measurement log, the
finding table and the stages are specified once, in the docstring of
`_footprint_grammar.py`, which also holds the parsers. This docstring specifies
the command that runs them.

CLI. `--stage` defaults to `verify`. `--paths` is required for `plan` and
rejected for the other stages. `--base-ref` is used only by `verify`; its default
is `git merge-base HEAD main`, and when that cannot be resolved the command exits
2 and asks for `--base-ref`. The repository root is `--repo-root`, else the git
toplevel of the working directory; it is never derived from this file's
location, because managed projects run the command through a `~/.local/bin`
symlink where that location is the plugin. The command reads
`.ai-work/<slug>/SYSTEMS_PLAN.md` (required), `.ai-state/FOOTPRINTS.md` and
`.ai-work/<slug>/MEASUREMENTS.md` (both if present). It runs only `git diff`,
`git ls-files`, `git rev-parse` and `git merge-base`, and never executes a
command named in a table or the registry.

Exit codes: `0` no `fail` finding (including the inactive case); `1` at least one
`fail` finding; `2` input error (bad arguments, the plan missing or without
`## Acceptance Criteria`, the base unresolvable); stderr names the input.

`--json` prints on stdout
`{"schema": 1, "slug", "stage", "active", "registry", "base_ref", "moved":
[{"footprint", "paths"}], "criteria", "not_measured", "measurements", "findings":
[{"code", "severity", "footprint", "criterion", "reason", "message"}]}`.
`active` is false exactly when there is no registry and the spec has neither
table.

Stdlib-only and Python 3.9-safe, like its private siblings. Tests:
`scripts/test_check_footprint_criteria.py`.
"""

from __future__ import annotations

import sys


def main() -> int:
    """Refuse until the stages exist: an executable `check_*` that exits 0 is a false all-clear."""
    print("check_footprint_criteria.py: stages not implemented", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
