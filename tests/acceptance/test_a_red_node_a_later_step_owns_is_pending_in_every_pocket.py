"""A red node a later, not-done step owns reads as pending, in whichever pocket it lives.

A step that changes a value a pinned test asserts turns that test red; a later step that
names the node, by its repository-relative id, in its Read-only field owns its verdict. The
earlier step's gate counts the node as pending, names no failure for it and reads the step
verified complete -- for a root-pocket unit test, an outer-loop test and a test in a pocket
of its own alike. A node nobody else owns stays a failure.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

import pytest

from tests.acceptance.drivers.pocket_gate import gate_block
from tests.acceptance.drivers.step_loop import Step, Work, attempt, build_loop

PINNED_TEST = "{import_line}\n\n\ndef test_the_pinned_value():\n    assert VALUE == 'old'\n"


@dataclass(frozen=True)
class Pinned:
    """A value module and the test that pins it, in one pocket."""

    module: str
    test: str
    import_line: str
    extra: tuple[tuple[str, str], ...] = ()

    @property
    def node(self) -> str:
        return f"{self.test}::test_the_pinned_value"

    def base_files(self) -> dict[str, str]:
        return {
            self.module: "VALUE = 'old'\n",
            self.test: PINNED_TEST.format(import_line=self.import_line),
            **dict(self.extra),
        }


EVAL_POCKET_CONFIG = (
    '[project]\nname = "eval-pocket"\nversion = "0.0.0"\n\n'
    '[tool.pytest.ini_options]\ntestpaths = ["tests"]\npythonpath = ["."]\n'
)

POCKETS = {
    "root-unit-test": Pinned(
        "src/pinned.py", "tests/test_pinned.py", "from src.pinned import VALUE"
    ),
    "outer-loop-test": Pinned(
        "src/pinned.py", "tests/acceptance/test_pinned.py", "from src.pinned import VALUE"
    ),
    "eval-pocket": Pinned(
        "eval/pinned.py",
        "eval/tests/test_pinned.py",
        "from pinned import VALUE",
        extra=(("eval/pyproject.toml", EVAL_POCKET_CONFIG),),
    ),
}


def _gate(tmp_path, pinned: Pinned, steps: tuple[Step, ...], done: tuple[str, ...] = ()):
    """Gate the first not-done step, which changes the pinned value; return its record and block."""
    task = build_loop(tmp_path, *steps, done=done, base_files=pinned.base_files())
    recorded = attempt(task, Work(other_edits=((pinned.module, "VALUE = 'new'\n"),)))
    return recorded, gate_block(task, recorded.recorded["request"])


def _count(block: str, name: str) -> int:
    """`name`'s count summed over every Result line of the block (one per run it holds)."""
    results = [line for line in block.splitlines() if line.startswith("Result:")]
    assert results, f"the gate block has no Result line:\n{block}"
    return sum(int(n) for line in results for n in re.findall(rf"\b{name}=(\d+)", line))


def _failed_lines_naming(block: str, node: str) -> list[str]:
    return [line for line in block.splitlines() if line.startswith("Failed:") and node in line]


@pytest.mark.parametrize("pocket", list(POCKETS), ids=list(POCKETS))
def test_a_red_node_a_later_step_owns_reads_as_pending(tmp_path, pocket):
    pinned = POCKETS[pocket]
    steps = (
        Step("1", more_files=(pinned.module,)),
        Step("2", read_only=(pinned.node,), more_files=(pinned.test,)),
    )

    recorded, block = _gate(tmp_path, pinned, steps)

    assert _count(block, "pending") >= 1, block
    assert _count(block, "fail") == 0, block
    assert _failed_lines_naming(block, pinned.node) == [], block
    assert recorded.recorded["gate"]["verdict"] == "verified-complete", recorded.doc


@pytest.mark.parametrize("pocket", ["root-unit-test", "eval-pocket"])
def test_a_red_node_no_step_owns_is_a_failure(tmp_path, pocket):
    pinned = POCKETS[pocket]
    steps = (Step("1", more_files=(pinned.module,)), Step("2"))

    recorded, block = _gate(tmp_path, pinned, steps)

    assert _count(block, "fail") >= 1, block
    assert recorded.recorded["gate"]["verdict"] != "verified-complete", recorded.doc


def test_a_red_node_only_the_gated_step_owns_is_a_failure(tmp_path):
    pinned = POCKETS["eval-pocket"]
    steps = (Step("1", read_only=(pinned.node,), more_files=(pinned.module,)), Step("2"))

    recorded, block = _gate(tmp_path, pinned, steps)

    assert _count(block, "fail") >= 1, block
    assert recorded.recorded["gate"]["verdict"] != "verified-complete", recorded.doc


def test_a_red_node_only_a_done_step_owns_is_a_failure(tmp_path):
    pinned = POCKETS["eval-pocket"]
    steps = (Step("1", read_only=(pinned.node,)), Step("2", more_files=(pinned.module,)))

    recorded, block = _gate(tmp_path, pinned, steps, done=("1",))

    assert _count(block, "fail") >= 1, block
    assert recorded.recorded["gate"]["verdict"] != "verified-complete", recorded.doc
