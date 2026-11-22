"""A change to a file a test reads, only through a process it starts or a copy it makes, selects it.

The selection audit found root-pocket tests that read a file the resolver did not route to them:
the eval pocket's project file through `uv run --project`, the kernel adoption ledger through the
spawn hook, the committed adherence results through the kernel-manifest tests, hook helpers and
every hook module through the hook processes a test starts, the testing-conventions rule through
its pinned export, and every rule file through the kernel tools. For each, a change to that file
alone answers, in the root pocket, with the full suite or a list that holds the reading test.
"""

from __future__ import annotations

import pytest

from tests.acceptance.drivers.gate_liveness import make_copy
from tests.acceptance.drivers.selection_answers import (
    answers_for,
    describe_root_answer,
    selects,
    tracked_files,
)

HOOK_DELIVERY_TEST = "hooks/test_inject_subagent_context_delivery.py"
KERNEL_MANIFEST_TEST = "scripts/test_check_kernel_manifest.py"
RESULTS_PARITY_TEST = "scripts/test_kernel_run_evidence_parity.py"

NAMED_PAIRS = (
    ("eval/pyproject.toml", "scripts/test_pocket_gate_declarations.py"),
    (".ai-state/kernel_adoption.yaml", "tests/acceptance/test_spawn_kernel_injection.py"),
    ("hooks/_commit_command.py", HOOK_DELIVERY_TEST),
    ("hooks/_hook_utils.py", HOOK_DELIVERY_TEST),
    ("hooks/_hook_utils.py", "tests/acceptance/test_adherence_eval_stays_out_of_band.py"),
    ("hooks/_hook_utils.py", "tests/acceptance/test_live_eval_treats_archives_as_byproducts.py"),
    ("hooks/_hook_utils.py", "tests/acceptance/test_log_archives_stay_out_of_version_control.py"),
    ("hooks/_hook_utils.py", "tests/acceptance/test_log_health_checks.py"),
    (
        "rules/swe/testing-conventions.md",
        "tests/acceptance/test_other_channels_carry_the_kernel.py",
    ),
    ("rules/swe/vcs/git-conventions.md", KERNEL_MANIFEST_TEST),
    ("rules/_manifest.yaml", KERNEL_MANIFEST_TEST),
    ("hooks/inject_rules.py", HOOK_DELIVERY_TEST),
)

RESULTS_DIRECTORY = ".ai-state/eval_ledger/adherence/"
RUN_INDEX = RESULTS_DIRECTORY + "index.json"
RULES_DIRECTORY = "rules/"
RULE_DIRECTORY_PROSE = ("rules/README.md", "rules/CLAUDE.md")
HOOKS_DIRECTORY = "hooks/"


@pytest.fixture(scope="module")
def copy(tmp_path_factory):
    return make_copy(tmp_path_factory.mktemp("named-gaps"))


@pytest.mark.parametrize(("changed", "reader"), NAMED_PAIRS)
def test_a_change_to_the_file_alone_selects_the_test_that_reads_it(copy, changed, reader):
    answer = answers_for(copy, [changed])[changed]

    assert selects(answer, reader), (
        f"{reader} reads {changed}, yet a change to it alone does not select it; "
        f"{describe_root_answer(answer)}"
    )


def _unselected(copy, files, reader) -> list[str]:
    answers = answers_for(copy, files)
    return sorted(path for path in files if not selects(answers[path], reader))


def test_a_change_to_any_committed_results_file_selects_the_parity_test_that_reads_them_all(copy):
    results = [
        path
        for path in tracked_files(copy)
        if path.startswith(RESULTS_DIRECTORY)
        and "/" not in path[len(RESULTS_DIRECTORY) :]
        and path.endswith(".json")
        and path != RUN_INDEX
    ]

    assert results, f"no committed results file under {RESULTS_DIRECTORY}"
    assert _unselected(copy, results, RESULTS_PARITY_TEST) == [], (
        f"these results files do not select {RESULTS_PARITY_TEST}, which reads every one"
    )


def test_a_change_to_any_rule_file_selects_the_kernel_test_that_reads_every_rule(copy):
    rule_files = [
        path
        for path in tracked_files(copy)
        if path.startswith(RULES_DIRECTORY) and path not in RULE_DIRECTORY_PROSE
    ]

    assert rule_files, f"no rule file under {RULES_DIRECTORY}"
    assert _unselected(copy, rule_files, KERNEL_MANIFEST_TEST) == [], (
        f"these rule files do not select {KERNEL_MANIFEST_TEST}, whose kernel tools read every rule"
    )


def test_a_change_to_any_hook_module_selects_the_test_that_delivers_through_every_hook(copy):
    hook_modules = [
        path
        for path in tracked_files(copy)
        if path.startswith(HOOKS_DIRECTORY)
        and "/" not in path[len(HOOKS_DIRECTORY) :]
        and path.endswith(".py")
        and not path[len(HOOKS_DIRECTORY) :].startswith("test_")
    ]

    assert hook_modules, f"no hook module under {HOOKS_DIRECTORY}"
    assert _unselected(copy, hook_modules, HOOK_DELIVERY_TEST) == [], (
        f"these hook modules do not select {HOOK_DELIVERY_TEST}, which reads every hook"
    )
