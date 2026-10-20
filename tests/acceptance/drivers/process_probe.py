"""Driver for watching what a hook process reads and starts, from outside it.

A hook is a Python interpreter started by the harness. This driver puts a
`sitecustomize` module on the interpreter's `PYTHONPATH` that installs an audit hook
(PEP 578) before the hook's own code runs, and appends one JSON line per event to a log
outside every sandbox a scenario builds:

- `start`: the interpreter came up with the probe loaded (one per interpreter,
  children included, since they inherit the environment);
- `open`: a file was opened, with its absolute path and mode;
- `process`: a process was started (`subprocess.Popen`, `os.system`, `os.exec*`,
  `os.posix_spawn`, `os.spawn*`, `os.fork`).

Bound here, because the specification fixes it: a hook is a Python interpreter that
honours `PYTHONPATH` (it is not started with `-I`, `-E` or `-S`). A run whose log holds
no `start` line saw nothing, and every reading of it fails rather than report an
interpreter that read nothing.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

LOG_VARIABLE = "ACCEPTANCE_PROCESS_PROBE_LOG"

_SITECUSTOMIZE = """
import json, os, sys

_log = os.environ.get("ACCEPTANCE_PROCESS_PROBE_LOG")
if _log:
    _out = open(_log, "a", buffering=1, encoding="utf-8")
    _out.write(json.dumps({"event": "start", "pid": os.getpid()}) + "\\n")
    _PROCESS_EVENTS = {
        "subprocess.Popen", "os.system", "os.exec", "os.posix_spawn", "os.spawn",
        "os.fork", "os.forkpty", "pty.spawn",
    }

    def _probe(event, args):
        try:
            if event == "open":
                path, mode = args[0], args[1]
                if isinstance(path, int) or path is None:
                    return
                where = os.path.realpath(os.path.abspath(os.fsdecode(path)))
                _out.write(json.dumps({"event": "open", "path": where, "mode": str(mode)}) + "\\n")
            elif event in _PROCESS_EVENTS:
                _out.write(json.dumps({"event": "process", "call": event, "args": repr(args)[:400]}) + "\\n")
        except Exception:
            pass

    sys.addaudithook(_probe)
"""


@dataclass(frozen=True)
class Probe:
    """A probe installed under `directory`, logging to `log`."""

    directory: Path
    log: Path

    def env(self) -> dict[str, str]:
        """The variables that load the probe into every interpreter started with them."""
        return {"PYTHONPATH": str(self.directory), LOG_VARIABLE: str(self.log)}

    def forget(self) -> None:
        self.log.unlink(missing_ok=True)

    def events(self) -> list[dict]:
        if not self.log.is_file():
            return []
        return [json.loads(line) for line in self.log.read_text(encoding="utf-8").splitlines()]

    def saw_an_interpreter(self) -> bool:
        return any(e["event"] == "start" for e in self.events())

    def _checked_events(self) -> list[dict]:
        events = self.events()
        assert any(e["event"] == "start" for e in events), (
            "the process probe saw no interpreter start: the hook did not load the probe "
            "(it is not a Python interpreter honouring PYTHONPATH), so nothing it read or "
            "started can be observed"
        )
        return events

    def opened_under(self, *roots: Path) -> list[Path]:
        """Every file the watched interpreters opened under any of `roots`, in order."""
        resolved = [Path(os.path.realpath(r)) for r in roots]
        opened = []
        for event in self._checked_events():
            if event["event"] != "open":
                continue
            path = Path(event["path"])
            if any(path == r or r in path.parents for r in resolved):
                opened.append(path)
        return opened

    def processes_started(self) -> list[str]:
        """Every process the watched interpreters started, as the audit event named it."""
        return [
            f"{e['call']} {e['args']}" for e in self._checked_events() if e["event"] == "process"
        ]


def install(workspace: Path) -> Probe:
    """A probe whose module and log live in `workspace`, apart from any sandbox."""
    directory = workspace / "process-probe"
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "sitecustomize.py").write_text(_SITECUSTOMIZE, encoding="utf-8")
    return Probe(directory, workspace / "process-probe.log")
