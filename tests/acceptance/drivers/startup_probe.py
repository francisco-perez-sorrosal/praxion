"""Driver for the real-token startup probe, `scripts/measure_startup_payload.py`, run against a stand-in.

A stand-in `claude` sits first on the probe's PATH. It records each start (its arguments
and environment) and answers with a minimal `stream-json` session whose first request
the probe can read. When asked to, it echoes every credential its environment holds on
its error output and in its reply, and, when asked to fail, exits non-zero after that,
so a scenario can see whether a credential that reached a session ever surfaces in what
the probe prints, records or reports.

Bound here, because the specification or the base commit fixes them: the probe's
`main` target, `--empty-dir`, `--json`, `--record` and `--baseline PATH`, its JSON
reading (`profile`, `targets`), and `--session-oauth-token-file`, the option name the
adherence entry already takes. No real `claude` starts: before any run the stand-in is
checked to shadow every other `claude` on the probe's PATH.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
PROBE = REPO_ROOT / "scripts" / "measure_startup_payload.py"
PLANTED_TOKEN = "sk-ant-oat01-acceptance-planted-subscription-token-4b9e21"
OPERATOR_API_KEY = "sk-ant-api03-acceptance-operator-key-8c1d77"
CREDENTIAL_VARIABLES = ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "CLAUDE_CODE_OAUTH_TOKEN")
_SYSTEM_PATH = ("/usr/bin", "/bin", "/usr/sbin", "/sbin")
_STRIPPED = ("CLAUDE", "ANTHROPIC", "PRAXION", "GIT_")

# Today's profile of a reading taken in an empty directory with no isolation flag.
TODAYS_EMPTY_DIR_PROFILE = {
    "cwd_kind": "unmanaged",
    "model": "sonnet",
    "setting_sources": None,
    "strict_mcp_config": False,
    "plugin_dir": None,
    "key": "unmanaged|sonnet|default|mcp|installed",
}

_STAND_IN = r"""#!{python}
import json, os, sys, time
from pathlib import Path

CONFIG = json.loads(Path({config!r}).read_text())
LOG = Path(CONFIG["log_dir"])
LOG.mkdir(parents=True, exist_ok=True)
(LOG / f"start-{{os.getpid()}}-{{time.time_ns()}}.json").write_text(
    json.dumps({{"argv": sys.argv[1:], "env": dict(os.environ)}})
)
if "--version" in sys.argv[1:]:
    print("9.9.9 (Claude Code)")
    sys.exit(0)
held = " ".join(f"{{n}}={{os.environ[n]}}" for n in {credentials!r} if n in os.environ)
if CONFIG["echo"]:
    sys.stderr.write(f"stand-in session credentials: {{held}}\n")
    sys.stderr.flush()
if CONFIG["fail"]:
    print(json.dumps({{"type": "result", "subtype": "error_during_execution", "is_error": True,
                      "result": f"refused: {{held}}"}}), flush=True)
    sys.exit(1)
reply = f"ok {{held}}" if CONFIG["echo"] else "ok"
events = [
    {{"type": "system", "subtype": "init", "cwd": os.getcwd(), "session_id": "probe", "tools": [],
      "mcp_servers": [], "model": "claude-sonnet", "apiKeySource": "none",
      "claude_code_version": "9.9.9", "agents": [], "plugins": []}},
    {{"type": "assistant", "parent_tool_use_id": None, "session_id": "probe",
      "message": {{"model": "claude-sonnet", "id": "msg_probe", "type": "message",
                  "role": "assistant", "content": [{{"type": "text", "text": reply}}],
                  "usage": {{"input_tokens": 2, "cache_creation_input_tokens": 100,
                            "cache_read_input_tokens": 0, "output_tokens": 3}}}}}},
    {{"type": "result", "subtype": "success", "is_error": False, "result": reply,
      "session_id": "probe", "num_turns": 1, "duration_ms": 5, "total_cost_usd": 0.0}},
]
for event in events:
    print(json.dumps(event), flush=True)
"""


@dataclass(frozen=True)
class StandIn:
    root: Path

    @property
    def bin_dir(self) -> Path:
        return self.root / "bin"

    def sessions(self) -> list[dict]:
        """Every start that was not a version query: its argv and its environment."""
        log = self.root / "log"
        starts = [json.loads(p.read_text()) for p in sorted(log.glob("start-*.json"))]
        return [s for s in starts if "--version" not in s["argv"]] if log.is_dir() else []


def install_stand_in(workspace: Path, *, echo: bool = False, fail: bool = False) -> StandIn:
    stand_in = StandIn(workspace / "stand-in")
    stand_in.bin_dir.mkdir(parents=True, exist_ok=True)
    config = stand_in.root / "config.json"
    config.write_text(
        json.dumps({"log_dir": str(stand_in.root / "log"), "echo": echo, "fail": fail})
    )
    script = stand_in.bin_dir / "claude"
    script.write_text(
        _STAND_IN.format(
            python=sys.executable, config=str(config), credentials=CREDENTIAL_VARIABLES
        )
    )
    script.chmod(0o755)
    return stand_in


def token_file(workspace: Path, content: str | None = PLANTED_TOKEN + "\n") -> Path:
    """A `claude setup-token` file holding `content`; None leaves the path absent."""
    path = workspace / "session-token"
    if content is not None:
        path.write_text(content, encoding="utf-8")
    return path


@dataclass(frozen=True)
class ProbeRun:
    exit_code: int
    stdout: str
    stderr: str
    sessions: list[dict]

    @property
    def reading(self) -> dict:
        return json.loads(self.stdout)

    def everything_printed(self) -> str:
        return self.stdout + self.stderr


def probe(
    workspace: Path,
    stand_in: StandIn,
    *,
    session_token_file: Path | None = None,
    baseline: Path | None = None,
) -> ProbeRun:
    """`measure_startup_payload.py main --empty-dir --json`, the operator's API key in its env."""
    path = os.pathsep.join([str(stand_in.bin_dir), *_SYSTEM_PATH])
    resolved = shutil.which("claude", path=path)
    assert resolved == str(stand_in.bin_dir / "claude"), f"claude resolves to {resolved}"
    home = workspace / "home"
    home.mkdir(exist_ok=True)
    env = {k: v for k, v in os.environ.items() if not k.startswith(_STRIPPED)}
    env.update({"PATH": path, "HOME": str(home), "ANTHROPIC_API_KEY": OPERATOR_API_KEY})
    argv = [sys.executable, str(PROBE), "main", "--empty-dir", "--json", "--timeout", "60"]
    argv += ["--repo-root", str(REPO_ROOT)]
    if session_token_file is not None:
        argv += ["--session-oauth-token-file", str(session_token_file)]
    if baseline is not None:
        argv += ["--record", "--baseline", str(baseline)]
    proc = subprocess.run(argv, env=env, cwd=workspace, capture_output=True, text=True, timeout=180)
    return ProbeRun(proc.returncode, proc.stdout, proc.stderr, stand_in.sessions())


def credentials_held(session: dict) -> dict[str, str]:
    """Every credential variable a session's environment holds, by name."""
    return {name: session["env"][name] for name in CREDENTIAL_VARIABLES if name in session["env"]}


def make_unreadable(path: Path) -> None:
    path.chmod(0o000)


def running_as_root() -> bool:
    return hasattr(os, "geteuid") and os.geteuid() == 0
