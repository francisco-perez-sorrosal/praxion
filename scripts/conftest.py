"""Shared pytest fixtures for `scripts/` test modules.

Currently carries only the `ledger_triage` fixture pair (`base_repo`,
`td264_post_rebase_repo`), consumed by `test_ledger_snapshot.py` and
`test_ledger_health.py`. Defined here rather than imported by name from
`_ledger_triage_testkit.py` into each test module: pytest resolves a fixture
by its parameter name, so `from _ledger_triage_testkit import base_repo` and
a same-named test parameter collide (ruff F811) the moment two test modules
both use it. `conftest.py` is pytest's own answer to sharing a fixture across
modules -- no import statement, no name collision.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest
from _ledger_triage_testkit import build_fixture_repo


def pytest_configure(config: pytest.Config) -> None:
    """Put the test interpreter's own `bin/` first on `PATH` for the session.

    Many tests here run shell entry points and `#!/usr/bin/env python3` CLIs as
    subprocesses (onboarding, the sidecar CLI, the finalize chain). Without this,
    `python3` is whatever the developer's ambient interpreter happens to be, and
    one that lacks the project's declared dependencies (PyYAML) fails them with a
    message about the machine rather than the code. With it, they run under the
    interpreter running the suite, as on CI.
    """
    interpreter_bin = str(Path(sys.executable).parent)
    os.environ["PATH"] = f"{interpreter_bin}{os.pathsep}{os.environ.get('PATH', '')}"


@pytest.fixture
def base_repo(tmp_path: Path) -> Path:
    """The 17-row `base/` ledger-triage fixture (frozen at `cac1ba2e`) as a
    real, committed git repo."""
    return build_fixture_repo(tmp_path, "base")


@pytest.fixture
def td264_post_rebase_repo(tmp_path: Path) -> Path:
    """The td-264 re-key case, isolated from `base/`'s pre-rebase td-264 row."""
    return build_fixture_repo(tmp_path, "td264_post_rebase")
