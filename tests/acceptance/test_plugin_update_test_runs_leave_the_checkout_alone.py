"""Test runs never write a checkout's configuration; an operator's own relink still does.

A checkout's rendered `claude/config/CLAUDE.md` is what its operator's global instructions link
to, and `claude/config/.personal_info.env` holds their saved values. Running the checkout's tests
that drive an installer or the first-session completion leaves both byte-identical with
unchanged modification times, or absent if they were absent. An operator's
`bash install.sh --relink` from their clone still renders into that clone with its saved values.

The test run happens in a stand-in checkout (a committed copy of this working tree), so a failing
run can never rewrite the operator's real configuration.
"""

from __future__ import annotations

import hashlib
import os

import pytest

from tests.acceptance.drivers import plugin_update as pu

SAVED = {"USERNAME": "@quill-standin", "EMAIL": "quill.standin@example.invalid",
         "GITHUB_URL": "https://example.invalid/quill-standin"}  # fmt: skip
RENDERED = b"# An operator's rendered instructions, as their own relink left them\n"
LONG_AGO = 1_000_000_000  # 2001: any write by the run moves the time


def _digest(path) -> str:
    """A file's content digest: the run's state is compared without printing what it holds."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _configuration(checkout) -> dict[str, tuple[str, int] | None]:
    state = {}
    for rel in (pu.RENDER, pu.SAVED_VALUES):
        path = checkout / rel
        state[rel] = (_digest(path), path.stat().st_mtime_ns) if path.exists() else None
    return state


@pytest.mark.parametrize("configuration", ["present", "absent"])
def test_running_the_installer_tests_leaves_the_checkout_configuration_unchanged(
    tmp_path, configuration
):
    checkout = pu.stand_in_checkout(tmp_path / "checkout")
    for rel, data in (
        (pu.RENDER, RENDERED),
        (pu.SAVED_VALUES, pu.saved_values_file(SAVED).encode()),
    ):
        (checkout / rel).unlink(missing_ok=True)
        if configuration == "present":
            (checkout / rel).write_bytes(data)
            os.utime(checkout / rel, (LONG_AGO, LONG_AGO))
    before = _configuration(checkout)
    selected = pu.installer_tests(checkout)
    result = pu.run_tests(checkout, tmp_path / "home", selected)
    assert selected, "no test drives an installer"
    assert result.returncode in (0, 1), result.stdout[-1500:] + result.stderr[-1500:]
    assert _configuration(checkout) == before, "the test run wrote the checkout's configuration"


def test_an_operators_relink_from_a_clone_renders_into_that_clone_with_its_saved_values(tmp_path):
    clone = pu.as_git_repository(pu.shipped_tree(tmp_path / "clone"))
    (clone / pu.SAVED_VALUES).write_text(pu.saved_values_file(SAVED), encoding="utf-8")
    machine = pu.Machine(tmp_path / "machine")
    machine.set_identity(pu.LATER)
    result = pu.relink(clone, machine)
    template = (clone / pu.TEMPLATE).read_text(encoding="utf-8")
    assert result.returncode == 0, result.stdout[-1500:] + result.stderr[-1500:]
    assert (clone / pu.RENDER).read_text(encoding="utf-8") == pu.render(template, SAVED)
    assert os.path.realpath(machine.instructions) == os.path.realpath(clone / pu.RENDER)
