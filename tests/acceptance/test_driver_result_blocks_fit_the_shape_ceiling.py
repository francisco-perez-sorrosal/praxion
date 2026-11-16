"""Every green result block the driver writes passes its own shape checker's ceiling.

A step with a long declared file list, a derived scope over three pockets and well over a
hundred test files, and a Check command of several hundred characters, is gated green; the
block the driver writes for it passes `check_test_results_shape.py` and still lets a reader
find the exact Check command that ran, in the block or in a file the block names.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

from tests.acceptance.drivers.loop_repairs import set_check
from tests.acceptance.drivers.pocket_gate import gate_block, shape_check
from tests.acceptance.drivers.step_loop import Step, Work, attempt, build_loop

PATH_LENGTH = 60
POCKETS = ("pocket_a", "pocket_b")
TESTS_PER_SCOPE = 40
POCKET_CONFIG = (
    '[project]\nname = "{name}"\nversion = "0.0.0"\n\n'
    '[tool.pytest.ini_options]\ntestpaths = ["tests"]\npythonpath = ["."]\n'
)


def _padded(prefix: str, index: int, suffix: str = ".py") -> str:
    """A path of exactly PATH_LENGTH characters: `prefix`, filler, a two-digit index, `suffix`."""
    tail = f"_{index:02d}{suffix}"
    filler = "x" * (PATH_LENGTH - len(prefix) - len(tail))
    assert filler, prefix
    return f"{prefix}{filler}{tail}"


ROOT_MODULE = _padded("src/changed_root_widget_", 0)
POCKET_MODULES = {pocket: _padded(f"{pocket}/changed_{pocket}_widget_", 0) for pocket in POCKETS}
DECLARED_TESTS = tuple(_padded("tests/test_declared_widget_behaviour_", i) for i in range(20))
DECLARED_SOURCES = tuple(_padded("src/declared_helper_module_", i) for i in range(5))
EXTRA_FILES = (ROOT_MODULE, *POCKET_MODULES.values(), *DECLARED_TESTS, *DECLARED_SOURCES)


def _module_name(path: str) -> str:
    return Path(path).stem


def _scope_test(import_line: str) -> str:
    """A test in the changed module's scope; it reads the module's source, importing nothing."""
    module = import_line.split()[1].replace(".", "/")
    return (
        "from pathlib import Path\n\n\n"
        "def test_the_value_is_known():\n"
        f"    source = Path(__file__).resolve().parents[1] / '{module}.py'\n"
        "    assert 'VALUE' in source.read_text()\n"
    )


def _base_files() -> dict[str, str]:
    files = {ROOT_MODULE: "VALUE = 1\n"}
    root_import = f"from src.{_module_name(ROOT_MODULE)} import VALUE"
    for i in range(TESTS_PER_SCOPE):
        files[f"tests/test_root_scope_{i:02d}.py"] = _scope_test(root_import)
    for pocket, module in POCKET_MODULES.items():
        files[f"{pocket}/pyproject.toml"] = POCKET_CONFIG.format(name=pocket)
        files[module] = "VALUE = 1\n"
        for i in range(TESTS_PER_SCOPE):
            files[f"{pocket}/tests/test_{pocket}_scope_{i:02d}.py"] = _scope_test(
                f"from {_module_name(module)} import VALUE"
            )
    return files


def _edits() -> tuple[tuple[str, str], ...]:
    changed = [(m, "VALUE = 2\n") for m in (ROOT_MODULE, *POCKET_MODULES.values())]
    tests = [(t, "def test_declared_behaviour():\n    assert True\n") for t in DECLARED_TESTS]
    sources = [(s, "HELPER = True\n") for s in DECLARED_SOURCES]
    return tuple(changed + tests + sources)


CHECK = f"{sys.executable} -m pytest {' '.join(DECLARED_TESTS)} -q -p no:cacheprovider"


def _gated_green(tmp_path):
    assert len(CHECK) >= 760, len(CHECK)
    assert len(EXTRA_FILES) + 2 == 30
    task = build_loop(tmp_path, Step("1", more_files=EXTRA_FILES), base_files=_base_files())
    set_check(task, "1", CHECK, "pass=20 fail=0 skip=0")
    recorded = attempt(task, Work(other_edits=_edits()))
    assert recorded.recorded["gate"]["verdict"] == "verified-complete", recorded.doc
    return task, gate_block(task, recorded.recorded["request"])


def _files_named(task, block: str) -> list[Path]:
    """Files a block names by an absolute or a repository- or task-relative path."""
    named = []
    for word in re.findall(r"[\w./-]+\.\w+", block):
        for candidate in (Path(word), task.root / word, task.task_dir / word):
            if candidate.is_file():
                named.append(candidate)
    return named


def test_the_drivers_green_block_passes_the_shape_checker(tmp_path):
    _, block = _gated_green(tmp_path)

    checked = shape_check(tmp_path, block)

    assert checked.returncode == 0, (
        f"{checked.stdout}{checked.stderr}\n{len(block.encode())} bytes:\n{block}"
    )


def test_the_exact_check_command_is_found_from_the_block(tmp_path):
    task, block = _gated_green(tmp_path)

    holders = [p for p in _files_named(task, block) if CHECK in p.read_text(encoding="utf-8")]

    assert CHECK in block or holders, (
        f"the Check command is neither in the block nor in a file it names:\n{block}"
    )
