"""Pytest plugin for the selection audit: tell the tracer which test file is running.

    PYTHONPATH=<this directory> PX_TRACE_ROOT=<repo> PX_TRACE_OUT=<dir outside repo> \\
        python -m pytest -p selection_trace_plugin ...

The audit hook in `sitecustomize.py` records every repository file opened for
reading; this plugin supplies the attribution (the test file whose collection,
setup, call or teardown is running), a heartbeat per test file that ran, the
set of test files each process collected, and every test file whose collection
failed. Heartbeats let the probe tell a test file that read nothing from one
that never ran under the tracer; a failed collection is reported by pytest's
own hook, never read back from its human-formatted summary.

Stdlib-only, and written against pytest's hook names alone so that importing it
needs nothing but the host. It also runs in xdist workers, where each worker
claims itself as the tracing process.
"""

from __future__ import annotations

import sitecustomize as tracer_module

NO_TEST = ""


class TracerNotActiveError(RuntimeError):
    """The traced run was started without a working tracer; its records would be empty."""


def _tracer() -> tracer_module.Tracer:
    tracer = getattr(tracer_module, "TRACER", None)
    if tracer is None:
        raise TracerNotActiveError(
            f"{tracer_module.ENV_ROOT} is unset, or another `sitecustomize` shadowed the tracer's"
            f" ({getattr(tracer_module, '__file__', '?')}); put the tracer directory first on PYTHONPATH"
        )
    return tracer


def pytest_configure(config: object) -> None:
    _tracer().check()


def pytest_collectstart(collector: object) -> None:
    """Attribute a module's import-time reads to that module; anything else to no test."""
    is_module = type(collector).__name__ == "Module"
    _tracer().begin(collector.nodeid if is_module else NO_TEST)  # type: ignore[attr-defined]


def pytest_collectreport(report: object) -> None:
    tracer = _tracer()
    tracer.begin(NO_TEST)
    if report.failed:  # type: ignore[attr-defined]
        tracer.emit({"uncollected": report.nodeid.partition("::")[0] or "."})  # type: ignore[attr-defined]


def pytest_collection_finish(session: object) -> None:
    files = sorted({item.nodeid.partition("::")[0] for item in session.items})  # type: ignore[attr-defined]
    if files:
        _tracer().emit({"collected": files})


def pytest_runtest_logstart(nodeid: str, location: object) -> None:
    test_file = nodeid.partition("::")[0]
    tracer = _tracer()
    tracer.begin(test_file)
    tracer.heartbeat(test_file)


def pytest_runtest_logfinish(nodeid: str, location: object) -> None:
    _tracer().begin(NO_TEST)


def pytest_sessionfinish(session: object, exitstatus: object) -> None:
    _tracer().check()
