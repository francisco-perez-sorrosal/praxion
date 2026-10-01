"""Tests for the selection-audit tracer.

The tracer is the audit's oracle for "which files does each test read", so its
failure mode is a silent undercount: a read that lands in no record, or under a
channel the verdict ignores. Two layers pin it. Traced pytest runs in a
throwaway repository prove the wiring through the real entry point (the plugin
and `sitecustomize` on `PYTHONPATH`), one scenario per channel. The in-process
tests then feed the tracer events directly to pin each decision it makes, which
the subprocess runs cannot show a mutation sensor.
"""

from __future__ import annotations

import builtins
import importlib
import importlib.util
import json
import os
import py_compile
import subprocess
import sys
import types
from pathlib import Path
from types import SimpleNamespace

import pytest

TRACER_DIR = Path(__file__).resolve().parent
ENV_ROOT, ENV_OUT, ENV_PID, ENV_TEST = (
    "PX_TRACE_ROOT",
    "PX_TRACE_OUT",
    "PX_TRACE_PID",
    "PX_TRACE_TEST",
)
TRACED_ENV_VARS = (ENV_ROOT, ENV_OUT, ENV_PID, ENV_TEST)

REPO_FILES = {
    "data/direct.txt": "direct\n",
    "data/child.txt": "child\n",
    "tests/lib_mod.py": "VALUE = 1\n",
    "tests/test_direct.py": (
        "from pathlib import Path\n\n\n"
        "def test_reads_a_file_directly():\n"
        "    path = Path(__file__).resolve().parent.parent / 'data' / 'direct.txt'\n"
        "    assert path.read_text() == 'direct\\n'\n"
    ),
    "tests/test_child.py": (
        "import subprocess\nimport sys\nfrom pathlib import Path\n\n"
        "REPO = Path(__file__).resolve().parent.parent\n\n\n"
        "def test_a_subprocess_reads_a_file():\n"
        "    code = f\"print(open({str(REPO / 'data' / 'child.txt')!r}).read())\"\n"
        "    run = subprocess.run(\n"
        "        [sys.executable, '-c', code], capture_output=True, text=True, check=True\n"
        "    )\n"
        "    assert run.stdout.strip() == 'child'\n"
    ),
    "tests/test_import.py": (
        "import lib_mod\n\n\ndef test_imports_a_module():\n    assert lib_mod.VALUE == 1\n"
    ),
}


def _load_sitecustomize():
    """The tracer module, loaded inert (no `PX_TRACE_ROOT`), under the name the interpreter gives it.

    A mutation run keys its mutants by module name, so a private alias would hide every hit.
    Inert is enforced, not assumed: inside a traced suite run the tracer's variables are set,
    and loading the module live would leave a second audit hook in the worker for good,
    crediting every later test's reads to this file.
    """
    spec = importlib.util.spec_from_file_location("sitecustomize", TRACER_DIR / "sitecustomize.py")
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    saved = {key: os.environ.pop(key) for key in _TRACER_ENV if key in os.environ}
    try:
        spec.loader.exec_module(module)
    finally:
        os.environ.update(saved)
    return module


_TRACER_ENV = ("PX_TRACE_ROOT", "PX_TRACE_OUT", "PX_TRACE_PID", "PX_TRACE_TEST")


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    for rel, text in REPO_FILES.items():
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
    return root


def _traced_env(repo: Path, out: Path) -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if k not in TRACED_ENV_VARS}
    env.pop("PYTEST_ADDOPTS", None)
    env.update(
        PYTHONPATH=str(TRACER_DIR),
        PYTHONDONTWRITEBYTECODE="1",
        PX_TRACE_ROOT=str(repo),
        PX_TRACE_OUT=str(out),
    )
    return env


def _traced_pytest(
    repo: Path, out: Path, *extra: str, env: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    # No `cwd=repo`: a process that inherits this one's directory keeps whatever
    # configuration a mutation run placed there, and every path below is absolute.
    command = [
        sys.executable,
        "-m",
        "pytest",
        "-p",
        "selection_trace_plugin",
        "-p",
        "no:cacheprovider",
    ]
    return subprocess.run(
        [*command, "--rootdir", str(repo), *extra, str(repo)],
        env=env or _traced_env(repo, out),
        capture_output=True,
        text=True,
        check=False,
    )


def _records(out: Path) -> list[dict]:
    lines = [line for f in sorted(out.glob("trace-*.jsonl")) for line in f.read_text().splitlines()]
    return [json.loads(line) for line in lines]


def _reads(out: Path) -> set[tuple[str, str, str]]:
    return {(r["t"], r["p"], r["c"]) for r in _records(out) if "p" in r}


def _traced_run(repo: Path, out: Path, *extra: str) -> set[tuple[str, str, str]]:
    out.mkdir(exist_ok=True)
    run = _traced_pytest(repo, out, *extra)
    assert run.returncode == 0, run.stdout + run.stderr
    return _reads(out)


def test_a_direct_read_lands_in_the_direct_channel(repo: Path, tmp_path: Path) -> None:
    reads = _traced_run(repo, tmp_path / "out")

    assert ("tests/test_direct.py", "data/direct.txt", "direct") in reads


def test_a_read_in_a_subprocess_lands_in_the_child_channel(repo: Path, tmp_path: Path) -> None:
    reads = _traced_run(repo, tmp_path / "out")

    assert ("tests/test_child.py", "data/child.txt", "child") in reads
    assert ("tests/test_child.py", "data/child.txt", "direct") not in reads


def test_an_import_lands_in_the_import_channel_with_the_py_source_path(
    repo: Path, tmp_path: Path
) -> None:
    reads = _traced_run(repo, tmp_path / "out")  # bytecode writing is off: the source is compiled

    assert ("tests/test_import.py", "tests/lib_mod.py", "import") in reads
    assert not any(path.endswith(".pyc") for _, path, _ in reads)


def test_a_cached_bytecode_import_maps_back_to_the_py_source_path(
    repo: Path, tmp_path: Path
) -> None:
    py_compile.compile(str(repo / "tests" / "lib_mod.py"), doraise=True)  # a valid cache to load
    assert list((repo / "tests" / "__pycache__").glob("lib_mod.*.pyc"))

    reads = _traced_run(repo, tmp_path / "out")

    assert ("tests/test_import.py", "tests/lib_mod.py", "import") in reads
    assert not any(path.endswith(".pyc") for _, path, _ in reads)


def test_every_collected_test_file_has_a_heartbeat(repo: Path, tmp_path: Path) -> None:
    out = tmp_path / "out"
    _traced_run(repo, out)

    records = _records(out)
    collected = {f for r in records if "collected" in r for f in r["collected"]}
    heartbeats = {r["heartbeat"] for r in records if "heartbeat" in r}
    assert collected == {"tests/test_child.py", "tests/test_direct.py", "tests/test_import.py"}
    assert heartbeats == collected


def test_repeat_runs_give_identical_records_after_channel_filtering(
    repo: Path, tmp_path: Path
) -> None:
    def verdict_bearing(reads: set[tuple[str, str, str]]) -> set[tuple[str, str, str]]:
        return {read for read in reads if read[2] != "import"}

    first = verdict_bearing(_traced_run(repo, tmp_path / "first"))
    second = verdict_bearing(_traced_run(repo, tmp_path / "second"))

    assert first == second
    assert first  # an empty comparison would pass for any tracer


def test_the_traced_run_adds_no_file_to_the_repository(repo: Path, tmp_path: Path) -> None:
    def listing() -> set[str]:
        return {p.relative_to(repo).as_posix() for p in repo.rglob("*")}

    before = listing()

    _traced_run(repo, tmp_path / "out")

    assert listing() == before
    assert list((tmp_path / "out").glob("trace-*.jsonl"))


def test_an_unwritable_output_directory_fails_the_run_loudly(repo: Path, tmp_path: Path) -> None:
    run = _traced_pytest(repo, tmp_path / "does-not-exist")

    assert run.returncode != 0
    assert "PX_TRACE_OUT" in run.stdout + run.stderr


def test_an_output_directory_inside_the_repository_fails_the_run_loudly(repo: Path) -> None:
    inside = repo / "trace-out"
    inside.mkdir()

    run = _traced_pytest(repo, inside)

    assert run.returncode != 0
    assert "outside the repository" in run.stdout + run.stderr


def test_the_plugin_without_a_tracer_fails_the_run_loudly(repo: Path, tmp_path: Path) -> None:
    env = _traced_env(repo, tmp_path)
    del env["PX_TRACE_ROOT"]

    run = _traced_pytest(repo, tmp_path, env=env)

    assert run.returncode != 0
    assert "PX_TRACE_ROOT" in run.stdout + run.stderr


def test_xdist_workers_trace_their_own_reads_as_direct(repo: Path, tmp_path: Path) -> None:
    pytest.importorskip("xdist")
    out = tmp_path / "out"
    out.mkdir()

    run = _traced_pytest(repo, out, "-p", "xdist", "-n", "2")

    assert run.returncode == 0, run.stdout + run.stderr
    reads = _reads(out)
    assert ("tests/test_direct.py", "data/direct.txt", "direct") in reads
    assert ("tests/test_child.py", "data/child.txt", "child") in reads


@pytest.mark.parametrize(
    ("cache_file", "source"),
    [
        (f"pkg/__pycache__/mod.{sys.implementation.cache_tag}.pyc", "pkg/mod.py"),
        ("pkg/__pycache__/test_x.cpython-311-pytest-8.3.4.pyc", "pkg/test_x.py"),
        ("pkg/__pycache__/conftest.cpython-311-pytest-9.0.0.pyc", "pkg/conftest.py"),
    ],
)
def test_bytecode_cache_names_map_back_to_their_source(cache_file: str, source: str) -> None:
    tracer = _load_sitecustomize()

    assert tracer.source_of_bytecode("/r/" + cache_file) == "/r/" + source


@pytest.mark.parametrize("path", ["/r/pkg/mod.pyc", "/r/pkg/__pycache__/mod", "/r/mod.py"])
def test_a_path_that_is_not_a_bytecode_cache_has_no_source(path: str) -> None:
    tracer = _load_sitecustomize()

    assert tracer.source_of_bytecode(path) is None


def test_without_a_trace_root_the_module_installs_nothing() -> None:
    tracer = _load_sitecustomize()

    assert tracer.TRACER is None


# -- The tracer's own logic, fed events in process -------------------------------
# The scenarios above prove the wiring; these pin each decision the hook makes.


@pytest.fixture
def traced(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    """A `Tracer` over a throwaway root, attributing to one test file, with no hook installed."""
    root = tmp_path / "root"
    out = tmp_path / "out"
    root.mkdir()
    out.mkdir()
    for name in (ENV_PID, ENV_TEST):
        monkeypatch.setenv(name, "")  # registered, so `begin` cannot leak them
    monkeypatch.setenv(ENV_PID, str(os.getpid()))
    module = _load_sitecustomize()
    tracer = module.Tracer(str(root), str(out))
    tracer.begin("tests/test_a.py")
    return SimpleNamespace(tracer=tracer, root=root, out=out, module=module)


def _open_event(path: Path | str, mode: object = "r", flags: object = os.O_RDONLY) -> tuple:
    return (str(path), mode, flags)


def test_a_read_of_a_repository_file_is_recorded_once(traced: SimpleNamespace) -> None:
    event = _open_event(traced.root / "data" / "x.txt")

    traced.tracer.on_audit("open", event)
    traced.tracer.on_audit("open", event)

    assert _records(traced.out) == [{"t": "tests/test_a.py", "p": "data/x.txt", "c": "direct"}]


def test_an_event_other_than_open_is_ignored(traced: SimpleNamespace) -> None:
    traced.tracer.on_audit("os.listdir", _open_event(traced.root / "data"))

    assert _records(traced.out) == []


@pytest.mark.parametrize(
    "flags",
    [os.O_WRONLY, os.O_RDWR, os.O_CREAT, os.O_APPEND, os.O_TRUNC],
    ids=["wronly", "rdwr", "creat", "append", "trunc"],
)
def test_a_read_that_could_write_is_not_a_read(traced: SimpleNamespace, flags: int) -> None:
    traced.tracer.on_audit("open", _open_event(traced.root / "x.txt", "w", flags))

    assert _records(traced.out) == []


@pytest.mark.parametrize(
    ("mode", "recorded"),
    [("r", True), ("rb", True), ("w", False), ("a", False), ("x", False), ("r+", False)],
)
def test_without_integer_flags_the_mode_decides_whether_it_is_a_read(
    traced: SimpleNamespace, mode: str, recorded: bool
) -> None:
    traced.tracer.on_audit("open", _open_event(traced.root / "x.txt", mode, None))

    assert bool(_records(traced.out)) is recorded


@pytest.mark.parametrize("relative", ["../elsewhere.txt", ".git/config", ".venv/lib/site.py"])
def test_a_file_that_is_not_a_tracked_candidate_is_not_recorded(
    traced: SimpleNamespace, relative: str
) -> None:
    traced.tracer.on_audit("open", _open_event(traced.root / relative))

    assert _records(traced.out) == []


def test_an_open_by_descriptor_is_ignored(traced: SimpleNamespace) -> None:
    traced.tracer.on_audit("open", (3, "r", os.O_RDONLY))

    assert _records(traced.out) == []


def test_a_read_with_no_current_test_is_not_attributed(traced: SimpleNamespace) -> None:
    traced.tracer.begin("")

    traced.tracer.on_audit("open", _open_event(traced.root / "x.txt"))

    assert _records(traced.out) == []


def test_a_read_in_another_process_is_a_child_read(traced: SimpleNamespace) -> None:
    traced.tracer.tracing_pid = os.getpid() + 1

    traced.tracer.on_audit("open", _open_event(traced.root / "x.txt"))

    assert [r["c"] for r in _records(traced.out)] == ["child"]


def test_a_read_made_while_a_module_is_imported_is_an_import_read(
    traced: SimpleNamespace, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    modules = tmp_path / "modules"
    modules.mkdir()
    (modules / "reads_on_import.py").write_text("import builtins\nbuiltins.feed_the_tracer()\n")
    event = _open_event(traced.root / "data" / "x.txt")
    monkeypatch.setattr(
        builtins, "feed_the_tracer", lambda: traced.tracer.on_audit("open", event), raising=False
    )
    monkeypatch.syspath_prepend(str(modules))
    monkeypatch.delitem(sys.modules, "reads_on_import", raising=False)

    importlib.import_module("reads_on_import")

    assert [r["c"] for r in _records(traced.out)] == ["import"]


def test_a_bytecode_read_is_recorded_as_its_source(traced: SimpleNamespace) -> None:
    cache = traced.root / "pkg" / "__pycache__" / f"mod.{sys.implementation.cache_tag}.pyc"

    traced.tracer.on_audit("open", _open_event(cache, "rb"))

    assert [r["p"] for r in _records(traced.out)] == ["pkg/mod.py"]


def test_one_heartbeat_is_written_per_test_file(traced: SimpleNamespace) -> None:
    traced.tracer.heartbeat("tests/test_a.py")
    traced.tracer.heartbeat("tests/test_a.py")
    traced.tracer.heartbeat("tests/test_b.py")

    assert _records(traced.out) == [
        {"heartbeat": "tests/test_a.py"},
        {"heartbeat": "tests/test_b.py"},
    ]


def test_beginning_a_test_claims_the_process_and_names_the_test_for_children(
    traced: SimpleNamespace,
) -> None:
    traced.tracer.begin("tests/test_b.py")

    assert traced.tracer.test == "tests/test_b.py"
    assert traced.tracer.tracing_pid == os.getpid()
    assert os.environ[ENV_TEST] == "tests/test_b.py"
    assert os.environ[ENV_PID] == str(os.getpid())


def test_a_read_made_while_recording_is_not_recorded_again(traced: SimpleNamespace) -> None:
    other = _open_event(traced.root / "other.txt")
    emit = traced.tracer.emit

    def emit_after_a_nested_read(record: dict) -> None:
        traced.tracer.on_audit("open", other)  # what opening the output file does
        emit(record)

    traced.tracer.emit = emit_after_a_nested_read

    traced.tracer.on_audit("open", _open_event(traced.root / "x.txt"))

    assert [r["p"] for r in _records(traced.out)] == ["x.txt"]


def test_a_failure_to_record_is_reported_by_the_next_check(traced: SimpleNamespace) -> None:
    def failing_emit(record: dict) -> None:
        raise OSError("disk full")

    traced.tracer.emit = failing_emit

    traced.tracer.on_audit("open", _open_event(traced.root / "x.txt"))

    with pytest.raises(RuntimeError, match="failed to record a read: .*disk full"):
        traced.tracer.check()


def test_check_passes_for_a_writable_directory_outside_the_root(traced: SimpleNamespace) -> None:
    traced.tracer.check()


def test_check_rejects_a_missing_output_directory(traced: SimpleNamespace) -> None:
    traced.tracer.out_dir = str(traced.out / "missing")

    with pytest.raises(RuntimeError, match="PX_TRACE_OUT is not a writable directory"):
        traced.tracer.check()


def test_check_rejects_an_output_directory_inside_the_root(traced: SimpleNamespace) -> None:
    inside = traced.root / "trace"
    inside.mkdir()
    traced.tracer.out_dir = str(inside)

    with pytest.raises(RuntimeError, match="outside the repository"):
        traced.tracer.check()


def test_the_environment_names_the_root_and_output_directory(
    traced: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(ENV_ROOT, str(traced.root))
    monkeypatch.setenv(ENV_OUT, str(traced.out))

    tracer = traced.module._from_environment()

    assert tracer.out_dir == str(traced.out)
    assert os.path.abspath(str(traced.root)) in tracer.roots


# -- The plugin's hooks, against a recording tracer ---------------------------------


class RecordingTracer:
    def __init__(self) -> None:
        self.calls: list[tuple] = []

    def begin(self, test: str) -> None:
        self.calls.append(("begin", test))

    def heartbeat(self, test: str) -> None:
        self.calls.append(("heartbeat", test))

    def emit(self, record: dict) -> None:
        self.calls.append(("emit", record))

    def check(self) -> None:
        self.calls.append(("check",))


class Module:
    nodeid = "tests/test_x.py"


class Package:
    nodeid = "tests"


@pytest.fixture
def plugin(monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    """The plugin module, wired to a recording tracer instead of the real `sitecustomize`."""
    recording = RecordingTracer()
    fake = types.ModuleType("sitecustomize")
    fake.TRACER = recording
    fake.ENV_ROOT = "PX_TRACE_ROOT"
    monkeypatch.setitem(sys.modules, "sitecustomize", fake)
    spec = importlib.util.spec_from_file_location(
        "selection_trace_plugin", TRACER_DIR / "selection_trace_plugin.py"
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return SimpleNamespace(module=module, calls=recording.calls, fake=fake)


def test_a_module_is_collected_under_its_own_name(plugin: SimpleNamespace) -> None:
    plugin.module.pytest_collectstart(Module())

    assert plugin.calls == [("begin", "tests/test_x.py")]


def test_any_other_collector_is_collected_under_no_test(plugin: SimpleNamespace) -> None:
    plugin.module.pytest_collectstart(Package())

    assert plugin.calls == [("begin", "")]


def test_a_finished_collection_report_clears_the_current_test(plugin: SimpleNamespace) -> None:
    plugin.module.pytest_collectreport(object())

    assert plugin.calls == [("begin", "")]


def test_the_collected_test_files_are_emitted_sorted_and_unique(plugin: SimpleNamespace) -> None:
    items = [SimpleNamespace(nodeid=n) for n in ("b.py::t1", "a.py::t1", "a.py::t2")]

    plugin.module.pytest_collection_finish(SimpleNamespace(items=items))

    assert plugin.calls == [("emit", {"collected": ["a.py", "b.py"]})]


def test_an_empty_collection_emits_nothing(plugin: SimpleNamespace) -> None:
    plugin.module.pytest_collection_finish(SimpleNamespace(items=[]))

    assert plugin.calls == []


def test_a_starting_test_is_attributed_and_given_a_heartbeat(plugin: SimpleNamespace) -> None:
    plugin.module.pytest_runtest_logstart(
        "tests/test_x.py::test_a", ("tests/test_x.py", 3, "test_a")
    )

    assert plugin.calls == [("begin", "tests/test_x.py"), ("heartbeat", "tests/test_x.py")]


def test_a_finished_test_clears_the_current_test(plugin: SimpleNamespace) -> None:
    plugin.module.pytest_runtest_logfinish(
        "tests/test_x.py::test_a", ("tests/test_x.py", 3, "test_a")
    )

    assert plugin.calls == [("begin", "")]


def test_the_tracer_is_checked_at_configure_and_at_session_finish(plugin: SimpleNamespace) -> None:
    plugin.module.pytest_configure(object())
    plugin.module.pytest_sessionfinish(object(), 0)

    assert plugin.calls == [("check",), ("check",)]


def test_a_plugin_without_a_tracer_names_the_missing_root(plugin: SimpleNamespace) -> None:
    plugin.fake.TRACER = None

    with pytest.raises(plugin.module.TracerNotActiveError, match="PX_TRACE_ROOT"):
        plugin.module.pytest_configure(object())
