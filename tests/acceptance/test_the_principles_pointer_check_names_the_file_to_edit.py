"""The principles-pointer check names each missing principle and the file to edit.

When the check in the kernel-texts test that holds the principles pointer to the user
template's principles fails because a principle is missing from the pointer, its
failure names each missing principle and `claude/kernels/src/principles-pointer.md`.
"""

from __future__ import annotations

from pathlib import Path

from tests.acceptance.drivers.refusal_messages import (
    POINTER_SOURCE,
    drop_from_pointer,
    kernel_texts_sandbox,
    run_kernel_texts_test,
)

DROPPED = ("Structural Beauty", "Balanced Coupling")


def test_a_pointer_missing_principles_fails_naming_each_one_and_the_pointer_file(
    tmp_path: Path,
) -> None:
    sandbox = kernel_texts_sandbox(tmp_path / "checkout")
    drop_from_pointer(sandbox, *DROPPED)

    run = run_kernel_texts_test(sandbox)

    report = run.stdout + run.stderr
    assert run.exit_code == 1, report
    assert "1 failed" in report, report
    assert [name for name in DROPPED if name not in report] == [], report
    assert POINTER_SOURCE in report, f"the failure does not name the file to edit:\n{report}"


def test_a_pointer_naming_every_principle_passes_the_check(tmp_path: Path) -> None:
    sandbox = kernel_texts_sandbox(tmp_path / "checkout")

    run = run_kernel_texts_test(sandbox)

    assert run.exit_code == 0, run.stdout + run.stderr
