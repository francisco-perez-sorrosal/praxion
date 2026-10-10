"""Driver for the live evaluation's file-change check.

The live evaluation compares a sandbox's files before and after a scenario and
drops hook byproducts before judging what changed. This driver hands a set of
created files to the `lightweight-fix` scenario's capture, exactly as the live
run does, and reports what the scenario judged. It runs in a subprocess under the
evaluation project's own `uv` environment (the package needs Python 3.13 and is
not installed in this repository's environment), replaying the recorded session
envelope the evaluation's own tests use.
"""

from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
EVAL_PROJECT = REPO_ROOT / "eval"
EVAL_SRC = EVAL_PROJECT / "src"
EVAL_PYTHON = "3.13"  # the evaluation's floor; pinned so uv never builds its env on a newer, wheel-less Python
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
    # The evaluation package requires Python 3.13 and its own dependencies, while this suite
    # runs on the repository's floor (3.11 on CI): the capture runs through the evaluation
    # project's own `uv` environment, not this interpreter. The outer run's environment
    # variables are dropped so `uv` resolves the evaluation project, not this one.
    env = {
        k: v
        for k, v in os.environ.items()
        if not k.startswith(("CLAUDE", "PRAXION_", "ANTHROPIC_", "VIRTUAL_ENV", "UV_"))
    }
    env["PYTHONPATH"] = str(EVAL_SRC)
    result = subprocess.run(
        [
            "uv",
            "run",
            "--quiet",
            "--python",
            EVAL_PYTHON,
            "--project",
            str(EVAL_PROJECT),
            "python",
            "-c",
            _CAPTURE,
        ],
        input=json.dumps({"envelope": str(ENVELOPE), "created": created}),
        capture_output=True,
        text=True,
        env=env,
        timeout=300,
    )
    assert result.returncode == 0, f"the live evaluation's capture failed: {result.stderr[-1500:]}"
    answer = json.loads(result.stdout)
    return Judgement(answer["kind"], answer["value"])
