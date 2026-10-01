"""Dead gates: changes to one gate inside a scratch copy, so a liveness check can be
shown to fail when its gate no longer does its job.

A dead gate still runs and reports, but reports a pass, a refusal, or nothing,
whatever its input. Each helper here changes only the gate, in the copy, through
the same path production reaches it: a script at its own path, or a command in
the hook registration (`hooks/hooks.json`). Nothing here knows how a liveness
check works; the scenarios commit the change and run the check.

Two kinds per gate, as the specification asks: one that does nothing and reports
success, and one that reproduces the failure that silenced the gate in
September 2026.
"""

from __future__ import annotations

import json

from tests.acceptance.drivers.gate_liveness import RepoCopy

MUTATION_SENSOR = "scripts/mutation_sensor.py"
SPAWN_COUNT = "scripts/spawn_count.py"
RESOLVER = "scripts/resolve_test_scope.py"
HOOK_REGISTRATION = "hooks/hooks.json"

# Import-safe: a dead gate is still importable (a real one does nothing, it does not
# crash its importers), so the copy's suite can still be collected and traced (SQ-03).
_STUB = '''#!/usr/bin/env python3
"""A dead gate standing in for {name}, written by a liveness acceptance scenario."""
import sys

if __name__ == "__main__":
    sys.stdout.write({stdout!r})
    sys.exit({exit_code})
'''


def replace_with_stub(copy: RepoCopy, script: str, *, stdout: str, exit_code: int) -> None:
    """Replace a gate's script with one that ignores its input and always says `stdout`."""
    copy.write(script, _STUB.format(name=script, stdout=stdout, exit_code=exit_code))


# -- The mutation sensor --------------------------------------------------------


def mutation_sensor_refuses(copy: RepoCopy, reason: str, detail: str) -> str:
    """The sensor reports itself unavailable on every run; returns the line it prints."""
    line = f"Mutation: unavailable reason={reason} ({detail})"
    replace_with_stub(copy, MUTATION_SENSOR, stdout=line + "\n", exit_code=2)
    return line


def mutation_sensor_parallel_inheritance_failure(copy: RepoCopy) -> str:
    """September 2026: every mutant run inherited `-n auto` and failed, so the sensor refused."""
    return mutation_sensor_refuses(
        copy,
        "run-failed",
        "every mutant's test run failed: pytest inherited the project's parallel default options",
    )


def mutation_sensor_reports_success_without_running(copy: RepoCopy) -> str:
    line = "Mutation: survivors=0 mutants=12 targets=[module.py]"
    replace_with_stub(copy, MUTATION_SENSOR, stdout=line + "\n", exit_code=0)
    return line


def mutation_sensor_reports_survivor_in_unforeseen_code(copy: RepoCopy) -> str:
    line = (
        "Mutation: survivors=1 mutants=12 targets=[module.py] "
        "(liveness_canary_unforeseen_function: 1)"
    )
    replace_with_stub(copy, MUTATION_SENSOR, stdout=line + "\n", exit_code=0)
    return line


def mutation_sensor_says_nothing(copy: RepoCopy) -> None:
    replace_with_stub(copy, MUTATION_SENSOR, stdout="", exit_code=0)


# -- The spawn counter ----------------------------------------------------------


def spawn_counter_says_nothing(copy: RepoCopy) -> None:
    """Does nothing and reports success: exit 0, no tally at all."""
    replace_with_stub(copy, SPAWN_COUNT, stdout="", exit_code=0)


_SPAWN_COUNT_WRAPPER = '''#!/usr/bin/env python3
"""A dead spawn counter wrapping the real one, written by a liveness acceptance scenario."""
import json
import subprocess
import sys
from pathlib import Path

REAL = Path(__file__).with_name("liveness_canary_real_spawn_count.py")
MODE = {mode!r}


def checkout_root(argv):
    if "--repo-root" in argv:
        return Path(argv[argv.index("--repo-root") + 1]).resolve()
    top = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True
    ).stdout.strip()
    return Path(top or ".").resolve()


argv = sys.argv[1:]
if MODE == "by-checkout-name" and "--slug" in argv:
    argv[argv.index("--slug") + 1] = checkout_root(argv).name
result = subprocess.run([sys.executable, str(REAL), *argv], capture_output=True, text=True)
if MODE == "unseen-as-zero" and result.returncode == 2:
    slug = argv[argv.index("--slug") + 1] if "--slug" in argv else ""
    if "--json" in argv:
        sys.stdout.write(json.dumps(
            {{"slug": slug, "spawns": 0, "resumes": 0, "charged": 0, "agents": [], "verdict": "ok"}}
        ) + "\\n")
    else:
        sys.stdout.write(f"{{slug}}: 0 spawns, 0 resumes\\n")
    sys.exit(0)
sys.stdout.write(result.stdout)
sys.stderr.write(result.stderr)
sys.exit(result.returncode)
'''


def _wrap_spawn_counter(copy: RepoCopy, mode: str) -> None:
    real = copy.path(SPAWN_COUNT)
    real.rename(real.with_name("liveness_canary_real_spawn_count.py"))
    copy.write(SPAWN_COUNT, _SPAWN_COUNT_WRAPPER.format(mode=mode))


def spawn_counter_attributes_by_checkout_name(copy: RepoCopy) -> None:
    """September 2026: spawns charged by the checkout's directory name, not the prompt's slug."""
    _wrap_spawn_counter(copy, "by-checkout-name")


def spawn_counter_counts_unseen_slug_as_zero(copy: RepoCopy) -> None:
    """A slug no row names is answered with a tally of zero instead of being withheld."""
    _wrap_spawn_counter(copy, "unseen-as-zero")


# -- The observation-log hooks ----------------------------------------------------

_HOOK_SHIM_NAME = "liveness_canary_hook_shim.py"
_HOOK_ORIGINALS_NAME = "liveness_canary_hook_commands.json"

_HOOK_SHIM = '''#!/usr/bin/env python3
"""Runs one original hook command under a dead-gate condition (liveness acceptance)."""
import json
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
MODE = sys.argv[1]
COMMAND = json.loads((HERE / {originals!r}).read_text())[int(sys.argv[2])]

raw = sys.stdin.read()
try:
    payload = json.loads(raw)
except ValueError:
    payload = None
cwd = payload.get("cwd") if isinstance(payload, dict) else None
session_dir = Path(cwd) if isinstance(cwd, str) and Path(cwd).is_dir() else None
below_root = session_dir is not None and not (session_dir / ".git").exists()

env = dict(os.environ)
run_cwd = os.getcwd()
if MODE == "beside-cwd" and below_root:
    # Every way a hook can find "the project" now answers with the session's own
    # directory, so the log lands beside the working directory, as in September 2026.
    subprocess.run(["git", "init", "-q"], cwd=session_dir, capture_output=True)
    (session_dir / ".ai-state").mkdir(exist_ok=True)
    env["CLAUDE_PROJECT_DIR"] = str(session_dir)
    run_cwd = str(session_dir)

result = subprocess.run(["/bin/sh", "-c", COMMAND], input=raw, text=True, cwd=run_cwd, env=env)

sys.exit(result.returncode)
'''


def _rewrite_hook_commands(copy: RepoCopy, replacement) -> None:
    registration = json.loads(copy.read(HOOK_REGISTRATION))
    originals: list[str] = []
    for groups in registration["hooks"].values():
        for group in groups:
            for hook in group["hooks"]:
                originals.append(hook["command"])
                hook["command"] = replacement(len(originals) - 1)
    copy.write(HOOK_REGISTRATION, json.dumps(registration, indent=2) + "\n")
    copy.write(f"hooks/{_HOOK_ORIGINALS_NAME}", json.dumps(originals, indent=2) + "\n")


def hooks_do_nothing(copy: RepoCopy) -> None:
    """Every registered hook command reads its payload and exits 0, writing nothing."""
    _rewrite_hook_commands(copy, lambda _index: "cat >/dev/null")


def _shim_hooks(copy: RepoCopy, mode: str) -> None:
    copy.write(f"hooks/{_HOOK_SHIM_NAME}", _HOOK_SHIM.format(originals=_HOOK_ORIGINALS_NAME))
    _rewrite_hook_commands(
        copy,
        lambda index: f"python3 ${{CLAUDE_PLUGIN_ROOT}}/hooks/{_HOOK_SHIM_NAME} {mode} {index}",
    )


def hooks_log_beside_session_directory(copy: RepoCopy) -> None:
    """September 2026: a session in a subdirectory writes its rows beside that directory."""
    _shim_hooks(copy, "beside-cwd")
