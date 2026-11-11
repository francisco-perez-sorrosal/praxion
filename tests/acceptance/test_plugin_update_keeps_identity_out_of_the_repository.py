"""The change adds no personal value to the repository.

No line the change adds since its base revision, in any tracked or new file, holds the operator's
email address or a copy of the identity values the installer falls back to. The values are
derived at run time, never written down here: the operator's from their git configuration, the
fallbacks from what a clone relink renders in a home that has no identity at all.
"""

from __future__ import annotations

import subprocess
import uuid

import pytest

from tests.acceptance.drivers import plugin_update as pu

BASE_COMMIT = "4cf729a533f2b1a856fd9d50af27edd41d84a1cb"
MIN_VALUE_LENGTH = 6  # shorter strings occur by chance in any diff


def _git(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], cwd=pu.REPO_ROOT, capture_output=True, text=True)


def _added_lines() -> list[tuple[str, str]]:
    """Every line added since the base: diffed tracked files, then whole new files."""
    diff = _git("diff", "--no-color", "--no-ext-diff", "--unified=0", BASE_COMMIT, "--").stdout
    added, path = [], ""
    for line in diff.splitlines():
        if line.startswith("+++ "):
            path = line[6:] if line.startswith("+++ b/") else ""
        elif line.startswith("+") and path:
            added.append((path, line[1:]))
    for new in _git("ls-files", "-o", "--exclude-standard").stdout.splitlines():
        text = (pu.REPO_ROOT / new).read_text(encoding="utf-8", errors="replace")
        added.extend((new, line) for line in text.splitlines())
    return added


@pytest.fixture(scope="module")
def identity_values(tmp_path_factory) -> set[str]:
    scratch = tmp_path_factory.mktemp("identity")
    clone = pu.as_git_repository(pu.shipped_tree(scratch / "clone"))
    machine = pu.Machine(scratch / "machine")
    token = uuid.uuid4().hex[:10]  # an identity no repository line can hold
    machine.set_identity(pu.Identity(f"Probe {token}", f"probe{token}@example.invalid"))
    result = pu.relink(clone, machine, answers="Y\nY\nY\n")  # accept the defaults
    assert (clone / pu.RENDER).exists(), result.stdout[-1500:] + result.stderr[-1500:]
    template = (clone / pu.TEMPLATE).read_text(encoding="utf-8")
    fallbacks = pu.values_in((clone / pu.RENDER).read_text(encoding="utf-8"), template)
    operator = _git("config", "user.email").stdout.strip()
    values = {*fallbacks.values(), operator, operator.split("@")[0]}
    values |= {v.lstrip("@") for v in fallbacks.values()}
    return {v for v in values if len(v) >= MIN_VALUE_LENGTH and token not in v}


def test_no_line_the_change_adds_holds_a_personal_value(identity_values):
    if _git("cat-file", "-e", f"{BASE_COMMIT}^{{commit}}").returncode != 0:
        pytest.skip(f"the base commit {BASE_COMMIT[:12]} is absent from this clone")
    hits = sorted(
        {path for path, line in _added_lines() if any(v in line for v in identity_values)}
    )
    assert not hits, f"added lines holding a personal value, in: {hits}"
