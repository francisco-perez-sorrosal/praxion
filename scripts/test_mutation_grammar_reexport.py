"""The `_step_schema` facade over the mutation-line leaf keeps every old name.

The `Mutation:` line and `mutation:` tag grammar moved out of `_step_schema` into
`_mutation_grammar`. Importers and tests reach those names through the old module
(`from _step_schema import render_mutation_line`, `schema.parse_mutation_tag`), so
the move is behaviour-preserving only while each name stays reachable there and is
the very object the leaf defines. The grammar's own cases stay in
`test_step_schema.py`, unedited; this file pins the seam.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import _mutation_grammar as leaf  # noqa: E402
import _step_schema as schema  # noqa: E402

# Every public name `_step_schema` defined before the split, read once from the
# module as it stood at the pipeline base. A literal on purpose: computing it from
# git here would make the test depend on history instead of on the contract.
BASE_PUBLIC_NAMES = (
    "GREEN",
    "RED",
    "STEP_ID_RE",
    "Counts",
    "NoRun",
    "Malformed",
    "ResultLine",
    "StepBlock",
    "step_id_from_heading",
    "step_sort_key",
    "parse_result_line",
    "split_step_blocks",
    "non_step_headings",
    "Claim",
    "parse_wip_claims",
    "checklist_step_id",
    "RecordedRun",
    "recorded_runs",
    "step_test_status",
    "MutationRan",
    "MutationRefused",
    "MutationMalformed",
    "MutationReading",
    "DECLARED_LIMIT_REASONS",
    "parse_mutation_line",
    "render_mutation_line",
    "step_mutation_reading",
    "mutation_block_reason",
    "parse_mutation_tag",
    "mutation_tagged_steps",
    "mutation_block_reasons",
)

# The subset that now lives in the leaf and is only re-exported by `_step_schema`.
MOVED_NAMES = (
    "MutationRan",
    "MutationRefused",
    "MutationMalformed",
    "MutationReading",
    "DECLARED_LIMIT_REASONS",
    "parse_mutation_line",
    "render_mutation_line",
    "mutation_block_reason",
    "parse_mutation_tag",
)


@pytest.mark.parametrize("name", BASE_PUBLIC_NAMES)
def test_every_name_the_schema_module_exported_before_the_split_is_still_reachable(
    name: str,
) -> None:
    assert hasattr(schema, name)


@pytest.mark.parametrize("name", MOVED_NAMES)
def test_a_moved_name_is_the_same_object_in_the_schema_module_and_the_leaf(name: str) -> None:
    assert getattr(schema, name) is getattr(leaf, name)


def test_the_schema_module_declares_its_whole_public_surface_in_all() -> None:
    assert set(BASE_PUBLIC_NAMES) <= set(schema.__all__)


def test_the_leaf_imports_nothing_but_the_standard_library() -> None:
    tree = ast.parse(Path(leaf.__file__).read_text())
    plain = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    # A relative import has no module name; "." is no stdlib module, so it fails the check.
    sourced = {node.module or "." for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)}
    assert {name.split(".")[0] for name in plain | sourced} <= set(sys.stdlib_module_names)


STEP_ID = 1  # a plan step label built from a constant, as the id-citation rule asks


def test_a_step_block_reads_its_mutation_line_through_the_leaf_grammar() -> None:
    line = "Mutation: survivors=0 mutants=5 targets=[a.py] ()"
    (block,) = schema.split_step_blocks(f"## Step {STEP_ID}\n{line}\n")
    assert block.mutation == leaf.parse_mutation_line(line)
    assert isinstance(block.mutation, leaf.MutationRan)
