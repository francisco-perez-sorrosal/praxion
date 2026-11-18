"""Driver for the startup instrument reading an agent target whose spawn the harness refuses.

A stand-in `claude` sits first on the instrument's PATH and plays one of four sessions for an
`agent:<name>` target: the main session calls the `Agent` tool and the harness refuses the call
(`refused`, and `refused_at_length` with a refusal text of several thousand characters); the
session ends at once without spawning (`ended`); or it runs on without spawning until something
stops it (`runs_on`). A refused call is written the way the harness writes a denial, as the
adherence driver binds it: an error tool result answering the `Agent` call, and an entry in the
final result's `permission_denials`.

Bound here, because the specification or the base commit fixes them: the target form
`agent:<name>`, `--empty-dir`, `--json`, `--timeout`, the JSON reading's `targets` with a
`withheld` reason for a target it could not read, and the stand-in recording each start.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from tests.acceptance.drivers import startup_probe

REPO_ROOT = startup_probe.REPO_ROOT
PROBE = startup_probe.PROBE
AGENT = "implementer"
TARGET = f"agent:{AGENT}"
TIMEOUT_SECONDS = 6
REFUSAL = "The server-side auto mode classifier gave no verdict (error)"
LONG_REFUSAL = REFUSAL + " " + "detail " * 900
BASE_ARGV_FIXTURE = (
    REPO_ROOT / "tests" / "acceptance" / "fixtures" / "refused_spawn" / "base_agent_argv.json"
)

_STAND_IN = r"""#!{python}
import json, os, sys, time
from pathlib import Path

CONFIG = json.loads(Path({config!r}).read_text())
LOG = Path(CONFIG["log_dir"])
LOG.mkdir(parents=True, exist_ok=True)
(LOG / f"start-{{os.getpid()}}-{{time.time_ns()}}.json").write_text(
    json.dumps({{"argv": sys.argv[1:]}})
)
if "--version" in sys.argv[1:]:
    print("9.9.9 (Claude Code)")
    sys.exit(0)
mode = CONFIG["mode"]
usage = {{"input_tokens": 2, "cache_creation_input_tokens": 100, "cache_read_input_tokens": 0,
          "output_tokens": 3}}
def emit(event):
    print(json.dumps(event), flush=True)
emit({{"type": "system", "subtype": "init", "cwd": os.getcwd(), "session_id": "probe",
      "tools": ["Agent"], "mcp_servers": [], "model": "claude-sonnet", "apiKeySource": "none",
      "claude_code_version": "9.9.9", "agents": [], "plugins": []}})
denials = []
if mode in ("refused", "refused_at_length"):
    call = {{"type": "tool_use", "id": "toolu_probe_agent", "name": "Agent",
             "input": {{"subagent_type": CONFIG["subagent"], "prompt": "Reply with the single word ok.",
                        "description": "probe"}}}}
    emit({{"type": "assistant", "parent_tool_use_id": None, "session_id": "probe",
          "message": {{"model": "claude-sonnet", "id": "msg_probe", "type": "message",
                      "role": "assistant", "content": [call], "usage": usage}}}})
    emit({{"type": "user", "parent_tool_use_id": None, "session_id": "probe",
          "message": {{"role": "user", "content": [{{"type": "tool_result",
                      "tool_use_id": "toolu_probe_agent", "is_error": True,
                      "content": CONFIG["refusal"]}}]}}}})
    denials = [{{"tool_name": "Agent", "tool_use_id": "toolu_probe_agent", "tool_input": call["input"]}}]
else:
    emit({{"type": "assistant", "parent_tool_use_id": None, "session_id": "probe",
          "message": {{"model": "claude-sonnet", "id": "msg_probe", "type": "message",
                      "role": "assistant", "content": [{{"type": "text", "text": "thinking"}}],
                      "usage": usage}}}})
if mode == "runs_on":
    time.sleep(120)
emit({{"type": "result", "subtype": "success", "is_error": False, "result": "ok",
      "session_id": "probe", "num_turns": 1, "duration_ms": 5, "total_cost_usd": 0.0,
      "permission_denials": denials}})
"""


@dataclass(frozen=True)
class AgentReading:
    exit_code: int
    stdout: str
    stderr: str
    session_argvs: tuple[tuple[str, ...], ...]

    def withheld(self) -> str | None:
        try:
            targets = json.loads(self.stdout)["targets"]
        except (json.JSONDecodeError, KeyError) as missing:
            raise AssertionError(
                f"no JSON reading ({missing}):\n{self.stdout}\n{self.stderr}"
            ) from missing
        entry = targets.get(TARGET)
        assert entry is not None, f"the reading has no {TARGET} entry: {targets}"
        return entry.get("withheld")


def read_agent_target(workspace: Path, mode: str) -> AgentReading:
    root = workspace / f"stand-in-{mode}"
    bin_dir = root / "bin"
    bin_dir.mkdir(parents=True)
    refusal = LONG_REFUSAL if mode == "refused_at_length" else REFUSAL
    config = root / "config.json"
    config.write_text(
        json.dumps(
            {
                "log_dir": str(root / "log"),
                "mode": mode,
                "subagent": f"praxion:{AGENT}",
                "refusal": refusal,
            }
        )
    )
    script = bin_dir / "claude"
    script.write_text(_STAND_IN.format(python=sys.executable, config=str(config)))
    script.chmod(0o755)
    path = os.pathsep.join([str(bin_dir), *startup_probe._SYSTEM_PATH])
    assert shutil.which("claude", path=path) == str(script), "the stand-in does not shadow claude"
    home = workspace / f"home-{mode}"
    home.mkdir()
    env = {k: v for k, v in os.environ.items() if not k.startswith(startup_probe._STRIPPED)}
    env.update(
        {"PATH": path, "HOME": str(home), "ANTHROPIC_API_KEY": startup_probe.OPERATOR_API_KEY}
    )
    argv = [sys.executable, str(PROBE), TARGET, "--empty-dir", "--json"]
    argv += ["--timeout", str(TIMEOUT_SECONDS), "--repo-root", str(REPO_ROOT)]
    done = subprocess.run(argv, env=env, cwd=workspace, capture_output=True, text=True, timeout=300)
    starts = sorted((root / "log").glob("start-*.json")) if (root / "log").is_dir() else []
    argvs = [tuple(json.loads(p.read_text())["argv"]) for p in starts]
    return AgentReading(
        done.returncode,
        done.stdout,
        done.stderr,
        tuple(a for a in argvs if "--version" not in a),
    )


def base_agent_argv() -> tuple[str, ...]:
    return tuple(json.loads(BASE_ARGV_FIXTURE.read_text(encoding="utf-8"))["argv"])
