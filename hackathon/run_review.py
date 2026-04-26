"""Reviewer script — runs inside a Daytona sandbox or on the host.

Calls Anthropic messages.parse(output_format=FindingsOutput) and writes:
  <out>/findings.json  — serialized FindingsOutput (always on success)
  <out-dir>/report.md  — human-readable markdown rendering of findings

Decision record: dec-draft-145b6ce7 mandates messages.parse() at all call sites.
ANTHROPIC_API_KEY is injected via Daytona env_vars inside the sandbox; on the host,
load_dotenv() reads it from .env if present (no-op when absent).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Ensure repo root is on sys.path so `hackathon.models` resolves whether this
# script runs via `python hackathon/run_review.py` (standalone) or inside a
# Daytona sandbox where only the script + models.py are uploaded flat.
_REPO_ROOT = Path(__file__).parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

# Also support flat-upload layout: models.py uploaded alongside run_review.py.
_SCRIPT_DIR = Path(__file__).parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    # python-dotenv not installed in all sandbox images — ANTHROPIC_API_KEY
    # arrives via env_vars injection; dotenv is optional inside the sandbox.
    pass

from anthropic import Anthropic  # noqa: E402

# Dual-layout import: package form (host) or flat form (sandbox root upload).
try:
    from hackathon.models import FindingsOutput  # noqa: E402
except ModuleNotFoundError:
    from models import FindingsOutput  # type: ignore[no-redef]  # noqa: E402

SYSTEM_PROMPT = (
    "You are reviewing a Python pull request against the project's coding-style rule. "
    "Use the methodology in the SKILL.md to identify defects. "
    "Return structured findings only — no prose."
)
MAX_TOKENS = 2048
MODEL = "claude-sonnet-4-6"


def _build_user_message(skill_text: str, rule_text: str, diff_text: str) -> str:
    return (
        "## SKILL.md\n\n"
        f"{skill_text}\n\n"
        "## coding-style.md\n\n"
        f"{rule_text}\n\n"
        "## PR Diff\n\n"
        f"```diff\n{diff_text}\n```"
    )


def _render_report(findings_output: FindingsOutput) -> str:
    if not findings_output.findings:
        return "# Review Report\n\nNo findings.\n"
    lines = ["# Review Report\n"]
    for f in findings_output.findings:
        lines.append(f"## [{f.severity}] {f.file}:{f.line}\n")
        lines.append(f"- **Rule**: {f.rule}")
        lines.append(f"- **Evidence**: {f.evidence}")
        lines.append("")
    return "\n".join(lines)


def _read_input_files(
    skill_path: Path, rule_path: Path, diff_path: Path
) -> tuple[str, str, str]:
    """Read all three input files, exiting non-zero on any missing file."""
    missing = [p for p in (skill_path, rule_path, diff_path) if not p.exists()]
    if missing:
        for p in missing:
            print(f"Error: required input file not found: {p}", file=sys.stderr)
        sys.exit(1)
    return (
        skill_path.read_text(encoding="utf-8"),
        rule_path.read_text(encoding="utf-8"),
        diff_path.read_text(encoding="utf-8"),
    )


def _write_outputs(out_path: Path, findings_output: FindingsOutput) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(findings_output.model_dump_json(indent=2), encoding="utf-8")
    report_path = out_path.parent / "report.md"
    report_path.write_text(_render_report(findings_output), encoding="utf-8")


def _call_llm(client: Anthropic, user_message: str) -> FindingsOutput:
    """Call the LLM with structured output.

    Prefers messages.parse() (SDK >=0.97.0 with native structured output).
    Falls back to messages.create() + JSON extraction for older SDK installs.
    The fallback uses a JSON-schema instruction in the system prompt to coerce
    structured output — functionally equivalent, slightly less type-safe.
    """
    if hasattr(client.messages, "parse"):
        response = client.messages.parse(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_message}],
            output_format=FindingsOutput,
        )
        return response.parsed_output  # type: ignore[return-value]

    # Fallback: instruct the model to return raw JSON matching FindingsOutput.
    json_instruction = (
        "\n\nRespond with ONLY a JSON object matching this schema, no markdown:\n"
        '{"findings": [{"severity": "FAIL|WARN|PASS", "file": "str", '
        '"line": 123, "rule": "str", "evidence": "str"}]}'
    )
    response = client.messages.create(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        system=SYSTEM_PROMPT + json_instruction,
        messages=[{"role": "user", "content": user_message}],
    )
    raw_text = response.content[0].text
    # Strip markdown fences if the model wrapped its output.
    stripped = raw_text.strip()
    if stripped.startswith("```"):
        stripped = stripped.split("\n", 1)[1].rsplit("```", 1)[0].strip()
    return FindingsOutput.model_validate_json(stripped)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Review a PR diff against a skill methodology and coding-style rule."
    )
    parser.add_argument(
        "--skill", required=True, metavar="PATH", help="Path to SKILL.md"
    )
    parser.add_argument(
        "--rule", required=True, metavar="PATH", help="Path to coding-style rule file"
    )
    parser.add_argument(
        "--diff", required=True, metavar="PATH", help="Path to PR unified diff"
    )
    parser.add_argument(
        "--out", required=True, metavar="PATH", help="Output path for findings.json"
    )
    args = parser.parse_args()

    skill_path = Path(args.skill)
    rule_path = Path(args.rule)
    diff_path = Path(args.diff)
    out_path = Path(args.out)

    skill_text, rule_text, diff_text = _read_input_files(
        skill_path, rule_path, diff_path
    )

    # Empty diff — nothing to review; short-circuit before any API call.
    if not diff_text.strip():
        empty_output = FindingsOutput(findings=[])
        _write_outputs(out_path, empty_output)
        return 0

    client = Anthropic()
    user_message = _build_user_message(skill_text, rule_text, diff_text)
    findings_output = _call_llm(client, user_message)

    _write_outputs(out_path, findings_output)
    return 0


if __name__ == "__main__":
    sys.exit(main())
