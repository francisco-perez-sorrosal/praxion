"""A `wrong-command` finding states the rule its command was held to.

The message says the logged command must repeat the criterion's command token by
token, in order, and may add only options and their values after them, and that a
placeholder in the criterion stands for one whole token, so a placeholder joined to
other text inside one token is compared as literal text. The finding's code, severity
and stage, and the matching itself, are unchanged.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from tests.acceptance.drivers.refusal_messages import verify_footprints, wrong_command_findings

ADDS_A_POSITIONAL = (
    "python3 scripts/check_agent_prompt_size.py",
    "python3 scripts/check_agent_prompt_size.py agents/verifier.md",
)
JOINS_A_PLACEHOLDER_TO_AN_OPTION = (
    "python3 scripts/measure_selection_size.py --compare-ref=<sha>",
    "python3 scripts/measure_selection_size.py --compare-ref=f3988742",
)

TOKEN_ORDER_RULE = (r"\btoken", r"\border\b|in sequence|same sequence", r"\bonly\b", r"\boption")
PLACEHOLDER_RULE = (r"placeholder", r"(one|a single|whole|entire|single) token", r"literal")

SCENARIOS = [
    pytest.param(ADDS_A_POSITIONAL, id="log-adds-a-positional"),
    pytest.param(JOINS_A_PLACEHOLDER_TO_AN_OPTION, id="criterion-joins-a-placeholder-to-an-option"),
]


def _missing(message: str, patterns: tuple[str, ...]) -> list[str]:
    return [p for p in patterns if re.search(p, message, re.IGNORECASE) is None]


@pytest.mark.parametrize(
    "rule",
    [
        pytest.param(TOKEN_ORDER_RULE, id="token-by-token-then-options"),
        pytest.param(PLACEHOLDER_RULE, id="placeholder-is-one-token"),
    ],
)
@pytest.mark.parametrize("commands", SCENARIOS)
def test_the_wrong_command_message_states_the_matching_rule(
    tmp_path: Path, commands: tuple[str, str], rule: tuple[str, ...]
) -> None:
    criterion, logged = commands

    findings = wrong_command_findings(
        verify_footprints(tmp_path, criterion_command=criterion, logged_command=logged)
    )

    assert len(findings) == 1, findings
    missing = _missing(findings[0]["message"], rule)
    assert missing == [], f"the message lacks {missing}: {findings[0]['message']}"


@pytest.mark.parametrize("commands", SCENARIOS)
def test_the_wrong_command_finding_keeps_its_code_and_severity(
    tmp_path: Path, commands: tuple[str, str]
) -> None:
    criterion, logged = commands

    findings = wrong_command_findings(
        verify_footprints(tmp_path, criterion_command=criterion, logged_command=logged)
    )

    assert [(f["code"], f["severity"], f["criterion"]) for f in findings] == [
        ("FP03", "fail", "FC-01")
    ]


@pytest.mark.parametrize(
    ("criterion", "logged"),
    [
        pytest.param(
            "python3 scripts/check_agent_prompt_size.py",
            "python3 scripts/check_agent_prompt_size.py --json",
            id="an-added-option",
        ),
        pytest.param(
            "python3 scripts/measure_selection_size.py --compare-ref <sha>",
            "python3 scripts/measure_selection_size.py --compare-ref f3988742",
            id="a-placeholder-filled-as-one-token",
        ),
    ],
)
def test_a_command_the_rule_admits_is_not_a_wrong_command(
    tmp_path: Path, criterion: str, logged: str
) -> None:
    findings = verify_footprints(tmp_path, criterion_command=criterion, logged_command=logged)

    assert wrong_command_findings(findings) == []
