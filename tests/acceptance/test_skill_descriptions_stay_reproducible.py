"""Every skill description stays reproducible from its row in the description diet table."""

from __future__ import annotations

import subprocess
import sys

from tests.acceptance.drivers.skill_pages import REPO_ROOT


def test_the_description_diet_check_reports_no_drift():
    result = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / "apply_skill_description_diet.py"), "--check"],
        cwd=REPO_ROOT, capture_output=True, text=True, timeout=300,
    )  # fmt: skip

    assert result.returncode == 0, result.stdout[-2000:] + result.stderr[-2000:]
