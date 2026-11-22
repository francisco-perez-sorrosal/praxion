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

    {"t": <test file>, "p": <repo path>, "c": "direct" | "child" | "import" | "copy"}
    {"heartbeat": <test file>}
    {"collected": [<test file>, ...]}
    {"uncollected": <test file whose collection failed>}

Channels: `child` is every read in a process other than the one running the
tests; `import` is an in-process read made while the import machinery
(`_find_and_load`) is on the stack, which credits whichever test imported a
module first; `direct` is every other in-process read, explicit path loads
(`spec_from_file_location`, `runpy`) included; `copy` is the source-side read of
a `shutil.copyfile` that copies a file of a checkout the running test has just
listed with `git ls-files` at the repository root, to a destination that keeps
the file's repository path (see `Tracer._copied_source`). A bytecode-cache read
is recorded as the `.py` source it stands for, so a module's first load looks
the same whether it compiled or read a cached `.pyc`.

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

DIRECT, CHILD, IMPORT, COPY = "direct", "child", "import", "copy"

_WRITE_FLAGS = os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_APPEND | os.O_TRUNC
_WRITE_MODE_CHARS = frozenset("wax+")
_UNTRACKED_PREFIXES = (".git/", ".venv/")
_IMPORT_MODULE = "importlib._bootstrap"
_IMPORT_FUNCTION = "_find_and_load"
_COPYTREE_MODULE = "shutil"
_COPYTREE_FUNCTION = "copytree"
_AUDITED_EVENTS = frozenset({"open", "shutil.copyfile", "subprocess.Popen"})
_GIT_LISTING = "ls-files"
_GIT_OPTION_WITH_ARGUMENT = {"-c": False, "-C": True}  # True: the argument moves the directory


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


def _copytree_on_stack() -> bool:
    frame = sys._getframe(1)
    while frame is not None:
        if (
            frame.f_code.co_name == _COPYTREE_FUNCTION
            and frame.f_globals.get("__name__") == _COPYTREE_MODULE
        ):
            return True
        frame = frame.f_back
    return False


def _listed_directory(argv: object, directory: object) -> str | None:
    """The directory a `git ls-files` command lists, or None for any other command.

    `directory` is where the command starts; `-C <path>` moves it. A shape not
    understood reads as "not a listing", which leaves a later copy audited.
    """
    if not isinstance(argv, (list, tuple)) or not argv:
        return None
    try:
        words = [os.fsdecode(word) for word in argv]
        current = os.fsdecode(directory)  # type: ignore[arg-type]
    except TypeError:
        return None
    if os.path.basename(words[0]) != "git":
        return None
    remaining = iter(words[1:])
    for word in remaining:
        if word in _GIT_OPTION_WITH_ARGUMENT:
            argument = next(remaining, "")
            if _GIT_OPTION_WITH_ARGUMENT[word]:
                current = os.path.join(current, argument)
        elif not word.startswith("-"):
            return os.path.abspath(current) if word == _GIT_LISTING else None
    return None


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
        self.listed_checkout = False  # this process, in this test, listed the repository root
        self._copied = threading.local()  # `.source`: the file the copy under way is about to read

    def on_audit(self, event: str, args: tuple) -> None:
        if event not in _AUDITED_EVENTS or not self.test or getattr(self._busy, "on", False):
            return
        self._busy.on = True
        try:
            if event == "open":
                self._record_open(*args)
            elif event == "subprocess.Popen":
                self._note_command(*args)
            else:
                self._note_copy(*args)
        except Exception as exc:  # an audit hook that raises would break the code it watches
            self.write_error = repr(exc)  # surfaced loudly by `check`
        finally:
            self._busy.on = False

    def begin(self, test: str) -> None:
        """Attribute reads from here on to `test` ("" for none); claim this process as the tracer."""
        self.test = test
        self.listed_checkout = False
        self._copied = threading.local()
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
        copied = self._take_copied_source() == source
        if source.endswith(".pyc"):
            source = source_of_bytecode(source) or source
        rel = self._repo_relative(source)
        if rel is None or rel.endswith(".pyc") or rel.startswith(_UNTRACKED_PREFIXES):
            return
        channel = COPY if copied else self._read_channel()
        self._emit_once(("read", self.test, rel, channel), {"t": self.test, "p": rel, "c": channel})

    def _read_channel(self) -> str:
        if os.getpid() != self.tracing_pid:
            return CHILD
        return IMPORT if _import_machinery_on_stack() else DIRECT

    def _note_command(self, _executable: object, argv: object, cwd: object, *_rest: object) -> None:
        """Remember that this test listed the checkout: its copies of listed files are checkout copies."""
        if os.getpid() != self.tracing_pid:  # a forked child never inherits the listing
            return
        listed = _listed_directory(argv, os.getcwd() if cwd is None else cwd)
        if listed is not None and any(c in self.roots for c in (listed, os.path.realpath(listed))):
            self.listed_checkout = True

    def _note_copy(self, source: object, destination: object, *_rest: object) -> None:
        """Arm the read this copy is about to make; a copy that does not qualify disarms it."""
        self._copied.source = self._copied_source(source, destination)

    def _take_copied_source(self) -> str | None:
        """The armed copy source, consumed by the next read in this thread whatever it opens."""
        armed = getattr(self._copied, "source", None)
        self._copied.source = None
        return armed

    def _copied_source(self, source: object, destination: object) -> str | None:
        """The source of a copy of a listed checkout file to a path that keeps its repository path.

        A copy made while `copytree` runs is a different shape with its own rule. A copy to
        another path, or one made without listing the checkout first, is an ordinary read.
        """
        if not self.listed_checkout or os.getpid() != self.tracing_pid or _copytree_on_stack():
            return None
        absolute = os.path.abspath(os.fsdecode(source))  # type: ignore[arg-type]
        relative = self._repo_relative(absolute)
        if relative is None or relative.startswith(_UNTRACKED_PREFIXES):
            return None
        kept = os.path.abspath(os.fsdecode(destination)).endswith(os.sep + relative)  # type: ignore[arg-type]
        return absolute if kept else None

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
