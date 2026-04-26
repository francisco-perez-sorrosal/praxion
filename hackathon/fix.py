"""Fixer script — generates a patch and regression test after Round 2 catch.

Reads a FindingsOutput (findings.json from the Reviewer) plus the PR diff that was
reviewed, then calls the LLM once to produce:

  proposed_fix.patch  — smallest unified-diff fix for the highest-severity finding
  missing_test.py     — a single pytest case that would have caught the defect

Both are written to --out-dir (defaults to hackathon/artifacts/).

Exit codes:
  0  — success or no fix needed (no FAIL-equivalent findings)
  1  — missing required input file
  2  — LLM call failed
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

try:
    from hackathon.models import Finding, FindingsOutput, FixOutput
except ModuleNotFoundError:
    from models import Finding, FindingsOutput, FixOutput  # type: ignore[no-redef]

MODEL = "claude-sonnet-4-6"
MAX_TOKENS = 2048

# Severities that warrant a fix — anything FAIL-equivalent.
FIX_SEVERITIES = {"FAIL", "critical", "high"}

SYSTEM_PROMPT = (
    "You are an expert Python engineer tasked with fixing a code defect found "
    "during code review. Produce two artifacts only — no prose explanations:\n\n"
    "1. A minimal unified diff (git format) that fixes exactly the defect described "
    "in the finding. The patch must be the smallest correct change: a mutable default "
    "argument is fixed by changing the signature to `param=None` and adding "
    "`if param is None: param = <type>()` at the function top. Four lines maximum.\n\n"
    "2. A single pytest function named `test_<defect_class>_not_shared_across_calls` "
    "that would fail on the original code and pass after applying the patch. "
    "The test must call the fixed function twice with no explicit argument and assert "
    "that the second call's result does not contain data from the first."
)


def _load_findings(findings_path: Path) -> FindingsOutput:
    """Read and parse findings.json as FindingsOutput. Exits with code 1 if missing."""
    if not findings_path.exists():
        print(f"Error: findings file not found: {findings_path}", file=sys.stderr)
        sys.exit(1)
    return FindingsOutput.model_validate_json(findings_path.read_text(encoding="utf-8"))


def _read_text_file(path: Path, label: str) -> str:
    """Read a required text file. Exits with code 1 on missing file."""
    if not path.exists():
        print(f"Error: required {label} file not found: {path}", file=sys.stderr)
        sys.exit(1)
    return path.read_text(encoding="utf-8")


def _pick_primary_finding(findings: list[Finding]) -> Finding | None:
    """Return the first FAIL-equivalent finding, or None if none exist.

    FAIL severity takes precedence; within the same tier, first occurrence wins.
    """
    fail_findings = [f for f in findings if f.severity in FIX_SEVERITIES]
    if not fail_findings:
        return None
    for finding in fail_findings:
        if finding.severity == "FAIL":
            return finding
    return fail_findings[0]


def _build_user_message(finding: Finding, diff_text: str, rule_excerpt: str) -> str:
    return (
        "## Finding to Fix\n\n"
        f"- **File**: {finding.file}:{finding.line}\n"
        f"- **Rule**: {finding.rule}\n"
        f"- **Evidence**: {finding.evidence}\n\n"
        "## PR Diff (the code being fixed)\n\n"
        f"```diff\n{diff_text}\n```\n\n"
        "## Relevant Rule Excerpt\n\n"
        f"{rule_excerpt}"
    )


def _call_llm(client: object, user_message: str) -> FixOutput:
    """Call the LLM with structured output.

    Prefers messages.parse() (SDK >=0.97.0). Falls back to messages.create()
    + JSON extraction for older host installs — matching the run_review.py pattern.
    """
    if hasattr(client, "messages") and hasattr(client.messages, "parse"):  # type: ignore[union-attr]
        response = client.messages.parse(  # type: ignore[union-attr]
            model=MODEL,
            max_tokens=MAX_TOKENS,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_message}],
            output_format=FixOutput,
        )
        return response.parsed_output  # type: ignore[return-value]

    json_instruction = (
        "\n\nRespond with ONLY a JSON object matching this schema, no markdown:\n"
        '{"patch_text": "unified diff string", "test_text": "pytest function string"}'
    )
    response = client.messages.create(  # type: ignore[union-attr]
        model=MODEL,
        max_tokens=MAX_TOKENS,
        system=SYSTEM_PROMPT + json_instruction,
        messages=[{"role": "user", "content": user_message}],
    )
    raw = response.content[0].text.strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1].rsplit("```", 1)[0].strip()
    return FixOutput.model_validate_json(raw)


def propose_fix(findings: list[dict], pr_diff: str, rule: str) -> tuple[str, str]:
    """Generate a patch + regression test for the highest-severity FAIL finding.

    Returns ("", "") when there are no FAIL-equivalent findings — callers should
    check for empty strings before writing artifacts.

    Args:
        findings: Plain-dict list (keys: severity, file, line, rule, evidence).
        pr_diff:  The unified diff text that was reviewed.
        rule:     The coding-style rule text (used as LLM context).
    """
    finding_objects = [Finding(**f) for f in findings]
    primary = _pick_primary_finding(finding_objects)
    if primary is None:
        return ("", "")

    from anthropic import Anthropic  # noqa: PLC0415

    client = Anthropic()
    user_message = _build_user_message(primary, pr_diff, rule[:2000])

    try:
        fix_output = _call_llm(client, user_message)
    except Exception as exc:
        print(f"Error: LLM call failed: {exc}", file=sys.stderr)
        sys.exit(2)

    return (fix_output.patch_text, fix_output.test_text)


def _write_artifacts(out_dir: Path, patch_text: str, test_text: str) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "proposed_fix.patch").write_text(patch_text, encoding="utf-8")
    (out_dir / "missing_test.py").write_text(test_text, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate a patch + regression test for a FAIL finding."
    )
    parser.add_argument(
        "--findings",
        type=Path,
        default=Path("hackathon/artifacts/findings_r2.json"),
        metavar="PATH",
        help="Path to findings.json (FindingsOutput) from the Reviewer",
    )
    parser.add_argument(
        "--diff",
        type=Path,
        default=Path("hackathon/fixtures/pr_B.patch"),
        metavar="PATH",
        help="Path to the PR unified diff that was reviewed",
    )
    parser.add_argument(
        "--rule",
        type=Path,
        default=Path("rules/swe/coding-style.md"),
        metavar="PATH",
        help="Path to the coding-style rule for LLM context",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=Path("hackathon/artifacts"),
        metavar="PATH",
        help="Directory to write proposed_fix.patch and missing_test.py",
    )
    args = parser.parse_args()

    findings_output = _load_findings(args.findings)
    primary = _pick_primary_finding(findings_output.findings)
    if primary is None:
        print("No fix proposed: no FAIL-equivalent findings in input.")
        return 0

    diff_text = _read_text_file(args.diff, "PR diff")
    rule_text = _read_text_file(args.rule, "coding-style rule")

    findings_dicts = [f.model_dump() for f in findings_output.findings]
    patch_text, test_text = propose_fix(findings_dicts, diff_text, rule_text)

    if not patch_text and not test_text:
        print("No fix proposed: no FAIL-equivalent findings in input.")
        return 0

    _write_artifacts(args.out_dir, patch_text, test_text)
    print(f"Fixer: wrote proposed_fix.patch and missing_test.py to {args.out_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
