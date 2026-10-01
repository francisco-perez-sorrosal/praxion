"""Audit-hook tracer: which repository files does each test file open for reading?

The selection-audit probe puts this directory on `PYTHONPATH` for one traced
pytest run. The interpreter then imports this module at startup, in the test
process and in every child process the tests start, so a read made by a
subprocess is seen too. Without `PX_TRACE_ROOT` in the environment the module
installs nothing. Stdlib-only; the directory deliberately has no `__init__.py`.

Environment: `PX_TRACE_ROOT` (the repository), `PX_TRACE_OUT` (a directory
outside it that receives one `trace-<pid>.jsonl` per traced process), and two
variables the tracer maintains for its children, `PX_TRACE_PID` and
`PX_TRACE_TEST`.

Records (JSON Lines), each written the moment it is first seen:

    {"t": <test file>, "p": <repo path>, "c": "direct" | "child" | "import"}
    {"heartbeat": <test file>}
    {"collected": [<test file>, ...]}
    {"uncollected": <test file whose collection failed>}

Channels: `child` is every read in a process other than the one running the
tests; `import` is an in-process read made while the import machinery
(`_find_and_load`) is on the stack, which credits whichever test imported a
module first; `direct` is every other in-process read, explicit path loads
(`spec_from_file_location`, `runpy`) included. A bytecode-cache read is
recorded as the `.py` source it stands for, so a module's first load looks the
same whether it compiled or read a cached `.pyc`.

The plugin (`selection_trace_plugin.py`) drives the module through `begin`,
`heartbeat`, `emit` and `check`.
"""

from __future__ import annotations

import json
import os
import sys
import threading
from importlib.util import source_from_cache

ENV_ROOT = "PX_TRACE_ROOT"
ENV_OUT = "PX_TRACE_OUT"
ENV_PID = "PX_TRACE_PID"
ENV_TEST = "PX_TRACE_TEST"

DIRECT, CHILD, IMPORT = "direct", "child", "import"

_WRITE_FLAGS = os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_APPEND | os.O_TRUNC
_WRITE_MODE_CHARS = frozenset("wax+")
_UNTRACKED_PREFIXES = (".git/", ".venv/")
_IMPORT_MODULE = "importlib._bootstrap"
_IMPORT_FUNCTION = "_find_and_load"


def source_of_bytecode(path: str) -> str | None:
    """The `.py` source a bytecode-cache file was compiled from, or None.

    `source_from_cache` reads the interpreter's own naming; pytest's assertion
    rewriting adds a `-pytest-<version>` tag it does not parse, so those names
    fall back to the module stem in front of the first dot.
    """
    try:
        return source_from_cache(path)
    except (ValueError, NotImplementedError):
        directory, name = os.path.split(path)
        if os.path.basename(directory) != "__pycache__" or not name.endswith(".pyc"):
            return None
        return os.path.join(os.path.dirname(directory), name.split(".")[0] + ".py")


def _opens_for_reading(mode: object, flags: object) -> bool:
    if isinstance(flags, int):
        return not flags & _WRITE_FLAGS
    return isinstance(mode, str) and not _WRITE_MODE_CHARS & set(mode)


def _import_machinery_on_stack() -> bool:
    frame = sys._getframe(1)
    while frame is not None:
        if (
            frame.f_code.co_name == _IMPORT_FUNCTION
            and frame.f_globals.get("__name__") == _IMPORT_MODULE
        ):
            return True
        frame = frame.f_back
    return False


class Tracer:
    """Records the repository reads of the current test, one JSON line per new fact."""

    def __init__(self, root: str, out_dir: str) -> None:
        self.roots = tuple(dict.fromkeys((os.path.abspath(root), os.path.realpath(root))))
        self.out_dir = out_dir
        self.tracing_pid = int(os.environ.setdefault(ENV_PID, str(os.getpid())))
        self.test = os.environ.get(ENV_TEST, "")
        self.write_error = ""
        self._seen: set[tuple[str, ...]] = set()
        self._busy = threading.local()

    def on_audit(self, event: str, args: tuple) -> None:
        if event != "open" or not self.test or getattr(self._busy, "on", False):
            return
        self._busy.on = True
        try:
            self._record_open(*args)
        except Exception as exc:  # an audit hook that raises would break the code it watches
            self.write_error = repr(exc)  # surfaced loudly by `check`
        finally:
            self._busy.on = False

    def begin(self, test: str) -> None:
        """Attribute reads from here on to `test` ("" for none); claim this process as the tracer."""
        self.test = test
        self.tracing_pid = os.getpid()
        os.environ[ENV_PID] = str(self.tracing_pid)
        os.environ[ENV_TEST] = test

    def heartbeat(self, test: str) -> None:
        self._emit_once(("heartbeat", test), {"heartbeat": test})

    def emit(self, record: dict) -> None:
        line = json.dumps(record, sort_keys=True)
        with open(os.path.join(self.out_dir, f"trace-{os.getpid()}.jsonl"), "a") as out:
            out.write(line + "\n")

    def check(self) -> None:
        """Raise unless this process can trace and has recorded everything it saw."""
        if not os.path.isdir(self.out_dir) or not os.access(self.out_dir, os.W_OK):
            raise RuntimeError(f"{ENV_OUT} is not a writable directory: {self.out_dir!r}")
        if any(_under(os.path.realpath(self.out_dir), root) for root in self.roots):
            raise RuntimeError(f"{ENV_OUT} must lie outside the repository: {self.out_dir!r}")
        if self.write_error:
            raise RuntimeError(f"the tracer failed to record a read: {self.write_error}")

    def _record_open(self, path: object, mode: object, flags: object) -> None:
        if not isinstance(path, (str, bytes, os.PathLike)) or not _opens_for_reading(mode, flags):
            return
        source = os.path.abspath(os.fsdecode(path))
        if source.endswith(".pyc"):
            source = source_of_bytecode(source) or source
        rel = self._repo_relative(source)
        if rel is None or rel.endswith(".pyc") or rel.startswith(_UNTRACKED_PREFIXES):
            return
        channel = CHILD if os.getpid() != self.tracing_pid else self._in_process_channel()
        self._emit_once(("read", self.test, rel, channel), {"t": self.test, "p": rel, "c": channel})

    def _in_process_channel(self) -> str:
        return IMPORT if _import_machinery_on_stack() else DIRECT

    def _repo_relative(self, absolute: str) -> str | None:
        for root in self.roots:
            if _under(absolute, root):
                return absolute[len(root) + 1 :]
        return None

    def _emit_once(self, key: tuple[str, ...], record: dict) -> None:
        if key not in self._seen:
            self._seen.add(key)
            self.emit(record)


def _under(path: str, root: str) -> bool:
    return path.startswith(root + os.sep)


def _from_environment() -> Tracer | None:
    root = os.environ.get(ENV_ROOT)
    if not root:
        return None
    return Tracer(root, os.environ.get(ENV_OUT, ""))


TRACER = _from_environment()
if TRACER is not None:
    sys.addaudithook(TRACER.on_audit)
