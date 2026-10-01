"""Spec texts the extract command handled before are handled exactly as before.

Making room for footprint criteria must not move the design-vocabulary lint or
the extract for any spec text that existed before it: the same exit status and
the same findings (rule, severity, section, requirement, line, token, message),
and -- for a change that moves no footprint -- the same extract, byte for byte.

The "before" is a frozen corpus (`fixtures/spec_lint_before.jsonl`): the rule
table's own examples in every linted section, declared-name exemptions, fenced
blocks, comments, brief variants, input errors, criterion-shaped text written
the way specs wrote it before any convention for it, and the acceptance and
requirement text of every archived spec. Each case carries what the command
reported on it at the base commit, recorded by running the command.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.acceptance.drivers.spec_extract import run_extract

CORPUS = Path(__file__).resolve().parent / "fixtures" / "spec_lint_before.jsonl"


def _cases() -> list[dict]:
    lines = CORPUS.read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines[1:] if line.strip()]


CASES = _cases()
EXTRACTED_FOOTPRINT_FREE = [
    case for case in CASES if case["footprint_free"] and case["extract_sha256"] is not None
]


def test_the_corpus_covers_every_lint_outcome() -> None:
    rules = {finding["rule"] for case in CASES for finding in case["findings"]}
    exit_codes = {case["exit_code"] for case in CASES}

    assert {"DV01", "DV02", "DV03", "key-signals-missing"} <= rules
    assert {0, 1, 2} <= exit_codes
    assert any(case["name"].startswith("archived-") for case in CASES)


@pytest.mark.parametrize("case", CASES, ids=[case["name"] for case in CASES])
def test_a_prior_spec_text_gets_the_same_lint_findings(tmp_path: Path, case: dict) -> None:
    run = run_extract(tmp_path, case["plan"], case["brief"])

    assert run.exit_code == case["exit_code"], (
        f"exit status moved: before {case['exit_code']}, now {run.exit_code}; {run.stderr}"
    )
    assert run.findings == case["findings"], _findings_diff(case["findings"], run.findings)


@pytest.mark.parametrize(
    "case", EXTRACTED_FOOTPRINT_FREE, ids=[case["name"] for case in EXTRACTED_FOOTPRINT_FREE]
)
def test_a_footprint_free_spec_yields_the_same_extract(tmp_path: Path, case: dict) -> None:
    run = run_extract(tmp_path, case["plan"], case["brief"])

    assert run.extract is not None, f"no extract written; findings: {run.findings}"
    assert run.extract_sha256() == case["extract_sha256"], (
        "the extract of a footprint-free spec changed; it now reads:\n" + run.extract
    )


def _findings_diff(before: list[dict], now: list[dict]) -> str:
    def key(finding: dict) -> str:
        return json.dumps(finding, sort_keys=True)

    gone = [f for f in before if key(f) not in {key(n) for n in now}]
    new = [f for f in now if key(f) not in {key(b) for b in before}]
    return f"findings moved -- no longer reported: {gone}; newly reported: {new}"
