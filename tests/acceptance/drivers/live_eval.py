"""Driver for the live evaluation's file-change check.

The live evaluation compares a sandbox's files before and after a scenario and
drops hook byproducts before judging what changed. This driver hands a set of
created files to the `lightweight-fix` scenario's capture, exactly as the live
run does, and reports what the scenario judged. It runs in a subprocess with the
evaluation package on `PYTHONPATH` (the package is not installed in this
repository's environment), replaying the recorded session envelope the
evaluation's own tests use.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
EVAL_SRC = REPO_ROOT / "eval" / "src"
ENVELOPE = (
    REPO_ROOT / "eval" / "tests" / "fixtures" / "live_scenarios" / "lightweight_fix.stream.jsonl"
)

_CAPTURE = """
import json, sys
from pathlib import Path
from praxion_evals.live.scenarios import SCENARIOS, FsDelta
from praxion_evals.live.session import parse_stream

request = json.load(sys.stdin)
envelope = parse_stream(Path(request["envelope"]).read_text(encoding="utf-8"))
delta = FsDelta(created=request["created"], modified={})
result = SCENARIOS["lightweight-fix"].capture(envelope, delta, {})
print(json.dumps({"kind": type(result).__name__, "value": getattr(result, "value", None)}))
"""


@dataclass(frozen=True)
class Judgement:
    kind: str  # "Captured" or "NotElicited"
    value: object


def lightweight_fix_judgement(created: dict[str, str]) -> Judgement:
    """What the scenario judged when exactly `created` (relpath -> content) appeared."""
    env = {
        k: v
        for k, v in os.environ.items()
        if not k.startswith(("CLAUDE", "PRAXION_", "ANTHROPIC_"))
    }
    env["PYTHONPATH"] = str(EVAL_SRC)
    result = subprocess.run(
        [sys.executable, "-c", _CAPTURE],
        input=json.dumps({"envelope": str(ENVELOPE), "created": created}),
        capture_output=True,
        text=True,
        env=env,
        timeout=60,
    )
    assert result.returncode == 0, f"the live evaluation's capture failed: {result.stderr[-1500:]}"
    answer = json.loads(result.stdout)
    return Judgement(answer["kind"], answer["value"])
