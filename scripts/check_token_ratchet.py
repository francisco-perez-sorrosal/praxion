#!/usr/bin/env python3
"""Commit-gate wrapper over `measure_token_budget.ratchet()`.

Thin by design, matching the existing `check_*.py` commit-gate convention
(`hooks/commit_gate.sh` passes each registered check exactly one positional
script path, no forwarded CLI args): this script's only job is translating
`ratchet()`'s structured result into the 0-clean/1-findings exit convention
`--blocking` maps onto PreToolUse's block code. The ratchet's own definition
-- the trailing-30-day governed-*byte* delta, the frozen listing ceiling, and
the fail-open conditions -- lives in `measure_token_budget.py`; this file
restates none of it.

Stdlib-only, for the reason `measure_token_budget.py`'s own module docstring
already gives: it is ambient-invoked, so a third-party import would make it a
finding of `check_gate_liveness.py`'s own `ambient-import` check. This script
imports only that stdlib-only sibling, `_repo_root`, and `hooks/_hook_utils`
(also stdlib-only) for `record_gate_fire`.

Exit codes: 0 clean or fail-open skip, 1 the ratchet breached, 3 script
error -- an unhandled exception here must never resolve to 1 (findings) or
2. Exit 2 is not merely "the code `--blocking` maps onto a block" -- it is
the code `hooks/commit_gate.sh` passes straight through *unchanged* for
every value other than 1 (only rc==1 is translated to 2; a literal 2
returned by this script reaches PreToolUse as 2 regardless), so a script
error returning 2 blocks every commit fleet-wide exactly like a breach
would. 3 is unambiguously non-blocking on both sides of that translation.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import measure_token_budget as mtb
from _repo_root import resolve_repo_root

# hooks/_hook_utils.py is a sibling package to this file's own scripts/
# directory, not on sys.path by default -- add it, mirroring the reverse
# direction hooks/remind_calibration.py already uses for scripts/.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "hooks"))
from _hook_utils import record_gate_fire  # noqa: E402

SCRIPT_DIR = Path(__file__).resolve().parent
_SCRIPT_ERROR = 3

# rc -> gate_fire decision. A script error (rc == _SCRIPT_ERROR) is neither a
# clean pass nor an enforced block -- it fails open by design (see the exit
# code table above) but is still worth flagging, so it records as "warn".
_DECISION_BY_RC = {0: "pass", 1: "block"}


def _format_reasons(result: dict) -> str:
    reasons = []
    delta_bytes = result["governed_delta_bytes"]
    if delta_bytes is not None and delta_bytes > 0:
        reasons.append(
            f"governed always-loaded bytes grew by {delta_bytes} over the trailing 30 days"
        )
    if result["listing_over_ceiling"]:
        reasons.append(
            f"listing tokens ({result['listing_tokens']}) exceed the frozen "
            f"ceiling ({result['listing_ceiling']})"
        )
    return "; ".join(reasons)


def main() -> int:
    try:
        repo_root = resolve_repo_root(None, script_dir=SCRIPT_DIR)
        result = mtb.ratchet(repo_root, api_key=os.environ.get("ANTHROPIC_API_KEY"))
    except Exception as exc:  # noqa: BLE001 - see module docstring on exit codes
        print(f"token ratchet: SCRIPT ERROR -- {exc}", file=sys.stderr)
        return _SCRIPT_ERROR

    for note in result.get("notes", []):
        print(f"token ratchet: INFO -- {note}")

    if result["skipped"]:
        print(f"token ratchet: SKIPPED -- {result['reason']}")
        return 0
    if result["ratchet_ok"]:
        return 0

    print(f"token ratchet: BLOCKED -- {_format_reasons(result)}")
    return 1


if __name__ == "__main__":
    _rc = main()
    try:
        # No parsed payload is in scope here (main() never reads stdin), so
        # this row lands without a session_id -- still in the raw WAL, just
        # outside the Stop-time per-session rollup.
        record_gate_fire("check_token_ratchet", _DECISION_BY_RC.get(_rc, "warn"))
    except Exception:
        pass
    sys.exit(_rc)
