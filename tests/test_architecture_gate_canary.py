"""Canary for the architecture workflow's merge-blocking verdict gate.

`.github/workflows/architecture.yml` job `dsl-validate` ends in a step that reads
the architect-validator's `structured_output`, renders it into the job summary,
and turns a `FAIL` verdict into a red check. That step is the only thing in the
job that can block a merge -- the agent has no shell and cannot set an exit code
-- so if its shell logic is wrong, the whole structural gate is advisory in
practice however the validator votes. It shipped without an executable proof
that it bites, and this module is that proof.

## Why the script is parsed out of the workflow rather than pasted in here

A canary holding its own transcription of the gate is not a canary. It proves a
copy behaves; the shipped expression is then free to drift away from the copy
with every test still green -- the "convention lives at two textual sites with
no sync check" anti-pattern in `rules/swe/gate-liveness.md`, which this repo has
had to close repeatedly. Writing that defect into the test that certifies a gate
would be a uniquely thorough way to lose the plot.

So `shipped_gate_script()` loads the workflow YAML, finds the step by name, and
returns its literal `run:` body. `test_gate_script_is_parsed_not_transcribed`
holds that honest: it asserts the verdict expression is present in the raw
workflow bytes and *absent* from this module's own source, so the expression
under test cannot have been copied here.

## Fidelity to the runner

GitHub Actions executes a `run:` block with no explicit `shell:` as
`bash -e {0}` -- errexit on, pipefail off. Every case below runs the extracted
body through `bash -e <file>` with `VALIDATOR_OUTPUT` and `GITHUB_STEP_SUMMARY`
bound exactly as the workflow binds them, in a scratch cwd (the step writes a
JSON file next to itself).

Covered: `FAIL` blocks, `PASS` passes, `PASS_WITH_WARNINGS` passes, unparseable
JSON fails closed, empty output passes *with* the warning annotation -- a spent
API quota must not redden an unrelated PR, but it must also not look like a
pass. A final mutation case proves the FAIL assertion is not vacuous: with the
gate's `exit 1` neutered, the same input sails through.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_PATH = REPO_ROOT / ".github" / "workflows" / "architecture.yml"

GATE_JOB = "dsl-validate"
GATE_STEP_NAME = "Render verdict and gate on structural drift"

# The 9-test tests/consumer_layout/ suite carries the same guard; the `test-root`
# CI job asserts `command -v jq` so neither can silently stop running there.
needs_jq = pytest.mark.skipif(shutil.which("jq") is None, reason="jq is not installed")


# --------------------------------------------------------------------------
# Extraction
# --------------------------------------------------------------------------


def shipped_gate_script() -> str:
    """Return the literal `run:` body of the shipped gate step.

    Fails loudly rather than falling back to a default if the step is renamed or
    the job restructured: a canary that silently starts testing nothing is worse
    than a red one.
    """

    document = yaml.safe_load(WORKFLOW_PATH.read_text(encoding="utf-8"))
    steps = document["jobs"][GATE_JOB]["steps"]
    matches = [step for step in steps if step.get("name") == GATE_STEP_NAME]

    assert len(matches) == 1, (
        f"expected exactly one {GATE_STEP_NAME!r} step in job {GATE_JOB!r} of "
        f"{WORKFLOW_PATH.name}, found {len(matches)}; the gate was renamed or "
        f"removed and this canary is no longer pointed at it"
    )

    script = matches[0].get("run")
    assert script, f"the {GATE_STEP_NAME!r} step carries no `run:` body to execute"
    return script


def run_gate(script: str, validator_output: str, workdir: Path) -> tuple[int, str, str]:
    """Execute `script` the way the runner would; return (exit code, summary, stderr)."""

    script_path = workdir / "gate.sh"
    script_path.write_text(script, encoding="utf-8")
    summary_path = workdir / "step_summary.md"
    summary_path.touch()

    env = dict(os.environ)
    env["VALIDATOR_OUTPUT"] = validator_output
    env["GITHUB_STEP_SUMMARY"] = str(summary_path)

    completed = subprocess.run(
        ["bash", "-e", str(script_path)],
        cwd=str(workdir),
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    return completed.returncode, summary_path.read_text(encoding="utf-8"), completed.stdout


def verdict_payload(verdict: str) -> str:
    return json.dumps(
        {
            "verdict": verdict,
            "summary": "canary payload",
            "findings": [
                {
                    "severity": "FAIL",
                    "section": "model-to-code",
                    "code": "M2C-01",
                    "location": "docs/architecture.md",
                    "detail": "canary finding",
                    "suggested_action": "canary action",
                }
            ],
        }
    )


# --------------------------------------------------------------------------
# The gate under test
# --------------------------------------------------------------------------


@needs_jq
def test_fail_verdict_blocks_the_merge(tmp_path: Path) -> None:
    """The whole point of the gate: a FAIL verdict must redden the check."""

    code, summary, _ = run_gate(shipped_gate_script(), verdict_payload("FAIL"), tmp_path)

    assert code != 0, "a FAIL verdict left the job green -- the gate does not bite"
    assert "Architecture Validation Report" in summary
    assert "**Verdict:** FAIL" in summary


@needs_jq
def test_pass_verdict_does_not_block(tmp_path: Path) -> None:
    code, summary, _ = run_gate(shipped_gate_script(), verdict_payload("PASS"), tmp_path)

    assert code == 0, "a PASS verdict reddened the job -- the gate over-blocks"
    assert "**Verdict:** PASS" in summary


@needs_jq
def test_pass_with_warnings_does_not_block(tmp_path: Path) -> None:
    """Warnings are reported, never blocking -- the distinction the enum exists for."""

    code, summary, _ = run_gate(
        shipped_gate_script(), verdict_payload("PASS_WITH_WARNINGS"), tmp_path
    )

    assert code == 0, "PASS_WITH_WARNINGS blocked the merge -- warnings are not failures"
    assert "**Verdict:** PASS_WITH_WARNINGS" in summary


@needs_jq
def test_unparseable_output_fails_closed(tmp_path: Path) -> None:
    """Garbage is not a pass. A gate that cannot read its input must block."""

    code, _, _ = run_gate(shipped_gate_script(), "this is not json {{{", tmp_path)

    assert code != 0, "unparseable validator output left the job green -- the gate fails OPEN"


@needs_jq
def test_empty_output_passes_but_annotates(tmp_path: Path) -> None:
    """No verdict means the check never ran, not that it passed.

    An exhausted API quota is infrastructure failure, not structural drift, so it
    must not redden an unrelated PR -- but it must say so out loud, or a skipped
    structural check is indistinguishable from a clean one.
    """

    code, summary, stdout = run_gate(shipped_gate_script(), "", tmp_path)

    assert code == 0, "an empty validator output reddened the PR on infrastructure failure"
    assert "::warning::" in stdout, "the skipped-validation case emitted no warning annotation"
    assert "did not run" in summary


# --------------------------------------------------------------------------
# Proofs about the canary itself
# --------------------------------------------------------------------------


def test_gate_script_is_parsed_not_transcribed() -> None:
    """The expression under test comes from the workflow, and exists nowhere here.

    Two halves, both needed. The first proves the extracted body really is the
    shipped text. The second proves this module holds no copy of it -- so the
    cases above cannot keep passing against a stale duplicate while the shipped
    gate drifts.
    """

    script = shipped_gate_script()
    # Assembled at runtime so the literal never appears in this file's source.
    verdict_expression = ".verdict != " + '"FAIL"'

    assert verdict_expression in script, (
        "the extracted step body no longer contains the verdict expression; "
        "the gate's logic moved and this canary is testing something else"
    )
    assert verdict_expression in WORKFLOW_PATH.read_text(encoding="utf-8"), (
        "the verdict expression is absent from the raw workflow file"
    )
    assert verdict_expression not in Path(__file__).read_text(encoding="utf-8"), (
        "this module contains a literal copy of the shipped gate expression -- "
        "the two-sites-with-no-sync-check defect the parsing exists to avoid"
    )


@needs_jq
def test_canary_bites_when_the_gate_logic_is_broken(tmp_path: Path) -> None:
    """Mutation proof: neuter the gate's teeth and the FAIL case stops blocking.

    Without this, `test_fail_verdict_blocks_the_merge` could be passing for a
    reason unrelated to the gate -- the classic canary that never saw its own
    bad input. Replacing the terminal `exit 1` with `exit 0` is the smallest
    mutation that removes the blocking behaviour and nothing else.
    """

    script = shipped_gate_script()
    mutated = script.replace("exit 1", "exit 0")

    assert mutated != script, (
        "the gate body no longer contains the `exit 1` this mutation targets; "
        "the blocking mechanism changed shape and this proof needs rewriting"
    )

    code, _, _ = run_gate(mutated, verdict_payload("FAIL"), tmp_path)

    assert code == 0, (
        "neutering the gate's exit did not change the outcome, so the FAIL case "
        "above passes for some reason other than the gate blocking"
    )
