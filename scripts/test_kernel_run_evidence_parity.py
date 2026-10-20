"""Parity of kernel_run_evidence.py with the adherence eval, over the committed results files.

The gate restates two things the eval owns: how a lineage's complete pairs are counted, and the
name of a role's convention check. Neither may drift silently, so this file reads what the eval
wrote (the committed results directory and its run index) and the eval's own source, with `ast`
and no eval import. It reads repository files, so it stays out of the mutation run.
"""

from __future__ import annotations

import ast
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import kernel_run_evidence as kre  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent
RESULTS_DIR = REPO_ROOT / ".ai-state" / "eval_ledger" / "adherence"
EVAL_MODEL = REPO_ROOT / "eval" / "src" / "praxion_evals" / "adherence" / "model.py"
COMMITTED_FILES = kre.read_run_files(RESULTS_DIR)
INDEX = json.loads((RESULTS_DIR / "index.json").read_text(encoding="utf-8"))["runs"]
RUN_ROLES = [(run_id, role) for run_id, entry in INDEX.items() for role in entry["roles"]]


def test_every_committed_results_file_is_read_and_listed_in_the_index():
    assert sorted(file.run_id for file in COMMITTED_FILES) == sorted(INDEX)


@pytest.mark.parametrize(("run_id", "role"), RUN_ROLES)
def test_the_derived_lineage_and_pairs_equal_the_index_entry(run_id, role):
    derived = kre.derive(COMMITTED_FILES, run_id, role)

    assert derived.parts[0] == INDEX[run_id]["lineage_root"]
    assert derived.complete_pairs == INDEX[run_id]["roles"][role]["complete_pairs"]


@pytest.mark.parametrize(("run_id", "role"), RUN_ROLES)
def test_the_judged_flip_and_scored_checks_equal_the_index_entry(run_id, role):
    indexed = INDEX[run_id]["roles"][role]

    assert kre.judged_standing(COMMITTED_FILES, run_id, role) == indexed["flip"]
    recorded = kre.recorded_standing(COMMITTED_FILES, run_id, role)
    assert list(recorded.scored_checks) == indexed["scored_checks"]


def test_the_convention_check_template_equals_the_one_the_eval_names_checks_by():
    assert kre.CONVENTION_CHECK_TEMPLATE == eval_convention_template()


def eval_convention_template() -> str:
    """The f-string `convention_check_name` returns, with its one name written as `<name>`."""
    tree = ast.parse(EVAL_MODEL.read_text(encoding="utf-8"))
    function = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "convention_check_name"
    )
    returned = next(node.value for node in ast.walk(function) if isinstance(node, ast.Return))
    assert isinstance(returned, ast.JoinedStr), "the eval builds the check name as an f-string"
    return "".join(_template_part(part) for part in returned.values)


def _template_part(part: ast.expr) -> str:
    if isinstance(part, ast.Constant):
        return str(part.value)
    assert isinstance(part, ast.FormattedValue)
    assert isinstance(part.value, ast.Name), "the eval fills in one named value"
    return f"<{part.value.id}>"
