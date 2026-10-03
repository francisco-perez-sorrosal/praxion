"""Driver that records the file work a hook process does, from outside its code.

Every Python hook the harness starts imports `sitecustomize` from the probe
directory put first on `PYTHONPATH`; it installs a CPython audit hook that
appends one JSON line per file open, directory listing and process start to a
log the scenario reads afterwards. Each line names the hook script that did it
(its `argv[0]` basename, as `hooks/hooks.json` registers it). Nothing in the
hook's code is touched or imported.

Declared limit: only Python processes are observed; a shell hook's own work is
not.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

from tests.acceptance.drivers.observation_harness import HookHarness

_LOG_VARIABLE = "ACCEPTANCE_FILE_WORK_LOG"

_SITECUSTOMIZE = """
import os
import sys

_LOG = os.environ.get("ACCEPTANCE_FILE_WORK_LOG")
_WATCHED = frozenset(
    {"open", "os.listdir", "os.scandir", "subprocess.Popen", "os.posix_spawn",
     "os.exec", "os.fork", "os.forkpty", "os.system", "os.spawn", "os.startfile"}
)
if _LOG:
    import json as _json

    _fd = os.open(_LOG, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o644)
    _busy = [False]

    def _text(value):
        if isinstance(value, (str, bytes, os.PathLike)):
            return os.fsdecode(value)
        return repr(value)

    def _record(event, args):
        if event not in _WATCHED or _busy[0]:
            return
        _busy[0] = True
        try:
            entry = {
                "script": os.path.basename(sys.argv[0]) if sys.argv else "",
                "event": event,
                "path": _text(args[0]) if args else None,
                "mode": args[1] if event == "open" and len(args) > 1 else None,
                "flags": args[2] if event == "open" and len(args) > 2 else None,
            }
            os.write(_fd, (_json.dumps(entry, default=str) + "\\n").encode())
        finally:
            _busy[0] = False

    sys.addaudithook(_record)
"""

_PROCESS_EVENTS = frozenset(
    {
        "subprocess.Popen",
        "os.posix_spawn",
        "os.exec",
        "os.fork",
        "os.forkpty",
        "os.system",
        "os.spawn",
    }
)
_LISTING_EVENTS = frozenset({"os.listdir", "os.scandir"})


@dataclass(frozen=True)
class FileWork:
    events: tuple[dict, ...]

    def by(self, script: str) -> FileWork:
        return FileWork(tuple(e for e in self.events if e["script"] == script))

    def opened(self, paths: set[Path]) -> list[dict]:
        names = {str(p) for p in paths} | {os.path.realpath(p) for p in paths}
        return [e for e in self.events if e["event"] == "open" and e["path"] in names]

    def opened_for_reading(self, paths: set[Path]) -> list[dict]:
        return [e for e in self.opened(paths) if _reads(e)]

    def listed(self, directory: Path) -> list[dict]:
        names = {str(directory), os.path.realpath(directory)}
        return [e for e in self.events if e["event"] in _LISTING_EVENTS and e["path"] in names]

    def processes_started(self) -> list[dict]:
        return [e for e in self.events if e["event"] in _PROCESS_EVENTS]


def _reads(event: dict) -> bool:
    mode = event.get("mode")
    if isinstance(mode, str):
        return "r" in mode or "+" in mode
    flags = event.get("flags")
    if isinstance(flags, int):
        return flags & os.O_ACCMODE in (os.O_RDONLY, os.O_RDWR)
    return True


@dataclass(frozen=True)
class Probe:
    harness: HookHarness
    log: Path

    def work(self) -> FileWork:
        if not self.log.exists():
            return FileWork(())
        lines = self.log.read_text(encoding="utf-8").splitlines()
        return FileWork(tuple(json.loads(line) for line in lines if line.strip()))

    def reset(self) -> None:
        self.log.write_text("", encoding="utf-8")


def probing_harness(scratch: Path, mode: str | None = None) -> Probe:
    probe_dir = scratch / "probe"
    probe_dir.mkdir(parents=True, exist_ok=True)
    (probe_dir / "sitecustomize.py").write_text(_SITECUSTOMIZE, encoding="utf-8")
    log = scratch / "file-work.jsonl"
    harness = HookHarness(
        scratch / "harness",
        mode,
        extra_env={"PYTHONPATH": str(probe_dir), _LOG_VARIABLE: str(log)},
    )
    return Probe(harness, log)
