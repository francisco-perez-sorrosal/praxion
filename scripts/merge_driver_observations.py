#!/usr/bin/env python3
"""Git custom merge driver for observations JSONL artifacts.

The "observations" name is now a slight generalization: this one driver
routes two different files depending on where `.gitattributes` points it.
Under ordinary (InRepo) placement, the raw WAL (`.ai-state/observations.jsonl`)
went gitignored-but-present under dec-377 and never reaches a git merge
again -- only the committed per-session rollup,
`.ai-state/observations_summary.jsonl`, is tracked there. Under sidecar
placement, though, `.ai-state/` moves wholesale into a separate mount and the
raw WAL stays tracked *there* (see `_sidecar_init.py`), so this driver must
still handle it. The driver key and command are kept exactly as registered
(renaming would force a fleet-wide retired-driver cleanup across every
already-onboarded project); it dispatches on **row shape** instead of on
which path it was invoked for, since a merge driver's argv (`%O %A %B`)
carries no filename. A summary row always has a `started_at` key (see
`hooks/capture_session.py`'s `build_session_summary`); a raw WAL row never
does -- so peeking at one parsed line is enough to route each merge without
tracking two separate driver names.

Usage (via git config, not called directly):
    git config merge.observations-jsonl.name "Observations JSONL merge"
    git config merge.observations-jsonl.driver "python3 scripts/merge_driver_observations.py %O %A %B"

Arguments (provided by git):
    %O — ancestor (common base)
    %A — ours (current branch) — result must be written here
    %B — theirs (merging branch)

Exit codes:
    0 — merge succeeded, result written to %A
    1 — merge failed, manual resolution needed
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# Import reconcile functions from sibling script
SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
from reconcile_ai_state import reconcile_observations, reconcile_observations_summary  # noqa: E402


def _is_summary_shaped(*texts: str) -> bool:
    """True when the input rows carry the committed-summary shape.

    Checks the first parsable line across ``texts`` for a ``started_at``
    key, which only the committed per-session rollup carries. A merge never
    straddles the two shapes (each side of a real conflict is a version of
    the same tracked file), so one line is enough to decide. Both sides
    empty defaults to the summary path -- an empty result is identical
    either way.
    """
    for text in texts:
        for line in text.strip().splitlines():
            if not line.strip():
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            return "started_at" in obj
    return True


def main() -> int:
    if len(sys.argv) != 4:
        print(f"Usage: {sys.argv[0]} <ancestor> <ours> <theirs>", file=sys.stderr)
        return 1

    _ancestor_path, ours_path, theirs_path = sys.argv[1], sys.argv[2], sys.argv[3]

    try:
        ours_text = Path(ours_path).read_text(encoding="utf-8")
        theirs_text = Path(theirs_path).read_text(encoding="utf-8")
    except OSError as e:
        print(f"Cannot read input files: {e}", file=sys.stderr)
        return 1

    try:
        reconcile = (
            reconcile_observations_summary
            if _is_summary_shaped(ours_text, theirs_text)
            else reconcile_observations
        )
        merged = reconcile(ours_text, theirs_text)
    except Exception as e:
        print(f"Observations merge failed: {e}", file=sys.stderr)
        return 1

    # Write result to ours path (git expects the result there)
    Path(ours_path).write_text(merged, encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
