from __future__ import annotations

import importlib.util
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = REPO_ROOT / "codex" / "config" / "rules_bridge_parsing.py"


def load_rules_bridge_parsing():
    spec = importlib.util.spec_from_file_location("rules_bridge_parsing", MODULE_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_extract_summary_pins_to_intro_sentence_for_behavioral_contract_rule():
    """AC-10: `parse_rule()` on the behavioral-contract rule returns its intro paragraph
    verbatim, with no HTML-comment leakage — the property Decision 2 relies on."""
    parser = load_rules_bridge_parsing()
    rule_path = REPO_ROOT / "rules" / "swe" / "agent-behavioral-contract.md"

    parsed = parser.parse_rule(rule_path, REPO_ROOT)

    assert parsed["summary"] == (
        "The Methodology defines the flow; the contract defines the stance. "
        "Four non-negotiable behaviors for every agent that writes, plans, or reviews code:"
    )
    assert "<!--" not in parsed["summary"]


def test_extract_summary_rejects_html_comment_fence_as_summary(tmp_path: Path):
    """Pins the case Decision 2 relies on, not just today's rule file: a rule whose
    body STARTS with an HTML-comment line or block must not leak it into the
    Codex-facing manifest summary. Declared limits of the fix (not covered here):
    a comment trailing real text on the same line is kept verbatim, and an
    unterminated `<!--` or text after a same-line `-->` yields an empty summary."""
    parser = load_rules_bridge_parsing()
    rule_path = tmp_path / "fenced-rule.md"
    rule_path.write_text(
        "## Fenced Rule\n"
        "\n"
        "<!-- internal note: do not surface this in the Codex manifest -->\n"
        "\n"
        "Real summary text should appear here instead.\n",
        encoding="utf-8",
    )

    parsed = parser.parse_rule(rule_path, tmp_path)

    assert parsed["summary"] == "Real summary text should appear here instead."
    assert "<!--" not in parsed["summary"]


def test_extract_summary_rejects_multiline_html_comment_block(tmp_path: Path):
    """The single-line case above doesn't exercise a comment spanning multiple lines --
    a fence opened on one line and closed several lines later must be skipped in full."""
    parser = load_rules_bridge_parsing()
    rule_path = tmp_path / "fenced-rule.md"
    rule_path.write_text(
        "## Fenced Rule\n"
        "\n"
        "<!--\n"
        "internal note: do not surface this in the Codex manifest\n"
        "spanning several lines\n"
        "-->\n"
        "\n"
        "Real summary text should appear here instead.\n",
        encoding="utf-8",
    )

    parsed = parser.parse_rule(rule_path, tmp_path)

    assert parsed["summary"] == "Real summary text should appear here instead."
    assert "<!--" not in parsed["summary"]
