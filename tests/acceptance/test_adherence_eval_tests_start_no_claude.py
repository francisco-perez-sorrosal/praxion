"""The evaluation project's own tests never start a real `claude` process.

The whole `eval/` suite runs with a stand-in `claude` first on PATH that records
every start and refuses to run; the suite stays green and the stand-in is never
started.
"""

from __future__ import annotations

from tests.acceptance.drivers.adherence_eval import run_eval_suite_under_tripwire


def test_the_eval_suite_passes_without_ever_starting_claude(tmp_path):
    run = run_eval_suite_under_tripwire(tmp_path)

    assert run.claude_starts == [], f"the eval suite started claude: {run.claude_starts[:5]}"
    assert run.exit_code == 0, f"the eval suite failed:\n{run.tail}"
