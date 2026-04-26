"""Editor script — rewrites the code-review SKILL.md Gotchas section on the host.

Queries Cognee for a missed-bug record, calls the LLM to generate one Gotcha
bullet, validates the proposed change with is_safe_rewrite(), and (if safe)
writes the new SKILL.md to disk.

The 4-condition sanity check is the architectural contract (inline-sanity-check-replaces-critic).
If you feel the urge to add a 5th condition, surface the objection to the architect instead.

SDK imports (cognee, anthropic) are deferred to the functions that use them so
that `is_safe_rewrite` is importable without those packages being installed.
"""

from __future__ import annotations

import argparse
import asyncio
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

DEFAULT_SKILL_PATH = Path("hackathon/SKILL_DEMO.md")
DEFAULT_BACKUP_DIR = Path("hackathon/artifacts")
DEFAULT_REWRITE_LOG = Path("hackathon/artifacts/rewrite_log.md")
MODEL = "claude-sonnet-4-6"
MAX_TOKENS = 1024
GOTCHA_INSERTION_MARKER = "## Relationship to coding-style Rule"


# ---------------------------------------------------------------------------
# Pure sanity-check — no external dependencies, always importable.
# ---------------------------------------------------------------------------


def is_safe_rewrite(old: str, new: str) -> tuple[bool, str | None]:
    """Return (passed, failure_reason) for the 4-condition sanity check.

    Conditions (all must be true for a safe rewrite):
    1. Body delta < 400 chars (strict less-than).
    2. Frontmatter unchanged (text between the first and second '---').
    3. Section count unchanged (number of '## ' occurrences).
    4. No fenced python block longer than 8 lines (inclusive boundary).
    """
    if len(new) - len(old) >= 400:
        return (False, "size delta >= 400 chars")

    old_parts = old.split("---")
    new_parts = new.split("---")
    if len(old_parts) < 3 or len(new_parts) < 3:
        return (False, "frontmatter delimiter missing")
    if new_parts[1] != old_parts[1]:
        return (False, "frontmatter changed")

    if new.count("## ") != old.count("## "):
        return (False, "section count changed")

    # Check every fenced python block in new — none may exceed 8 code lines.
    # Strip leading/trailing whitespace before counting so the surrounding
    # newlines (the \n after ```python and before ```) don't inflate the count.
    segments = new.split("```python")
    for block in segments[1:]:  # first segment is before any python block
        code = block.split("```")[0].strip()
        line_count = len(code.splitlines())
        if line_count > 8:
            return (False, "fenced python block > 8 lines")

    return (True, None)


# ---------------------------------------------------------------------------
# Text-manipulation helpers — stdlib only.
# ---------------------------------------------------------------------------


def _extract_gotchas_section(skill_text: str) -> str:
    """Return the current content of the ## Gotchas section."""
    start = skill_text.find("## Gotchas")
    if start == -1:
        return ""
    end = skill_text.find("## ", start + len("## Gotchas"))
    if end == -1:
        return skill_text[start:]
    return skill_text[start:end]


def _insert_bullet(skill_text: str, bullet: str) -> str:
    """Append bullet immediately before the '## Relationship to coding-style Rule' heading."""
    marker_pos = skill_text.find(GOTCHA_INSERTION_MARKER)
    if marker_pos == -1:
        # Fallback: append at end of file if marker not found.
        return skill_text.rstrip() + "\n" + bullet + "\n"
    return skill_text[:marker_pos] + bullet + "\n\n" + skill_text[marker_pos:]


def _append_log(log_path: Path, message: str) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as f:
        f.write(message + "\n")


def _backup_skill(skill_path: Path, backup_dir: Path) -> None:
    """Write SKILL_v1.md.bak only if it does not already exist (idempotent)."""
    backup_dir.mkdir(parents=True, exist_ok=True)
    backup_path = backup_dir / "SKILL_v1.md.bak"
    if not backup_path.exists():
        backup_path.write_text(skill_path.read_text(encoding="utf-8"), encoding="utf-8")


# ---------------------------------------------------------------------------
# SDK-dependent functions — imports deferred until call time.
# ---------------------------------------------------------------------------


def _call_llm(
    client: object, entry: object, rule_excerpt: str, gotchas_section: str
) -> object:
    """Generate one Gotcha bullet via LLM.

    Uses messages.parse() when available (SDK >=0.97.0), falls back to
    messages.create() + JSON extraction for older host installs (0.71.x).
    Accepts typed objects as `object` to avoid importing SDK types at module level.
    """
    # Import models here so the module is importable without them installed.
    try:
        from hackathon.models import RewriteOutput  # noqa: PLC0415
    except ModuleNotFoundError:
        from models import RewriteOutput  # type: ignore[no-redef]  # noqa: PLC0415

    system_prompt = (
        "You are improving a code-review skill's Gotchas section based on a real missed bug. "
        "Produce exactly one new Gotcha bullet in Markdown format: "
        '"- **<Title>**: <one-sentence description of what to watch for and why>". '
        "The bullet must address the specific defect class that was missed. "
        "Do not reproduce existing bullets verbatim."
    )
    user_message = (
        f"## Failed Review Summary\n\n{entry.result_summary}\n\n"  # type: ignore[attr-defined]
        f"## Error Message\n\n{entry.error_message}\n\n"  # type: ignore[attr-defined]
        f"## Relevant Rule Excerpt\n\n{rule_excerpt}\n\n"
        f"## Existing Gotchas (do not duplicate)\n\n{gotchas_section}"
    )

    if hasattr(client, "messages") and hasattr(client.messages, "parse"):  # type: ignore[union-attr]
        response = client.messages.parse(  # type: ignore[union-attr]
            model=MODEL,
            max_tokens=MAX_TOKENS,
            system=system_prompt,
            messages=[{"role": "user", "content": user_message}],
            output_format=RewriteOutput,
        )
        return response.parsed_output

    json_instruction = '\n\nRespond with ONLY a JSON object: {"gotcha_bullet": "- **Title**: description"}'
    response = client.messages.create(  # type: ignore[union-attr]
        model=MODEL,
        max_tokens=MAX_TOKENS,
        system=system_prompt + json_instruction,
        messages=[{"role": "user", "content": user_message}],
    )
    raw = response.content[0].text.strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1].rsplit("```", 1)[0].strip()
    return RewriteOutput.model_validate_json(raw)


def _load_run_record(record_path: Path) -> object | None:
    """Load SkillRunEntry from a local JSON file (avoids Cognee search dependency)."""
    try:
        from hackathon.models import SkillRunEntry  # noqa: PLC0415
    except ModuleNotFoundError:
        from models import SkillRunEntry  # type: ignore[no-redef]  # noqa: PLC0415

    if not record_path.exists():
        return None
    try:
        return SkillRunEntry.model_validate_json(
            record_path.read_text(encoding="utf-8")
        )
    except Exception:
        return None


async def _main_async(
    skill_path: Path,
    backup_dir: Path,
    rewrite_log: Path,
    rule_path: Path,
    dry_run: bool,
    run_record_path: Path | None,
) -> int:
    from anthropic import Anthropic  # noqa: PLC0415

    _backup_skill(skill_path, backup_dir)

    entry = _load_run_record(run_record_path) if run_record_path is not None else None
    if entry is None:
        msg = "SKIP: no run record provided — Round 1 may have succeeded"
        _append_log(rewrite_log, msg)
        print(msg)
        return 0

    old_text = skill_path.read_text(encoding="utf-8")
    rule_text = rule_path.read_text(encoding="utf-8") if rule_path.exists() else ""
    rule_excerpt = rule_text[:2000]
    gotchas_section = _extract_gotchas_section(old_text)

    client = Anthropic()
    rewrite_output = _call_llm(client, entry, rule_excerpt, gotchas_section)
    bullet = rewrite_output.gotcha_bullet.strip()  # type: ignore[attr-defined]

    new_text = _insert_bullet(old_text, bullet)
    safe, reason = is_safe_rewrite(old_text, new_text)

    if dry_run:
        print(f"DRY RUN — proposed bullet:\n{bullet}")
        print(f"is_safe_rewrite: {safe}" + (f" (reason: {reason})" if reason else ""))
        return 0

    if not safe:
        msg = f"REWRITE REJECTED: {reason}\nBullet: {bullet}"
        _append_log(rewrite_log, msg)
        print(msg, file=sys.stderr)
        return 1

    skill_path.write_text(new_text, encoding="utf-8")
    msg = f"REWRITE ACCEPTED\nBullet: {bullet}"
    _append_log(rewrite_log, msg)
    print(msg)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Rewrite the code-review SKILL.md Gotchas section from Cognee feedback."
    )
    parser.add_argument(
        "--skill-path",
        type=Path,
        default=DEFAULT_SKILL_PATH,
        metavar="PATH",
        help="Path to the skill being self-improved (default: hackathon/SKILL_DEMO.md)",
    )
    parser.add_argument(
        "--backup-dir",
        type=Path,
        default=DEFAULT_BACKUP_DIR,
        metavar="PATH",
        help="Directory to store SKILL_v1.md.bak",
    )
    parser.add_argument(
        "--rewrite-log",
        type=Path,
        default=DEFAULT_REWRITE_LOG,
        metavar="PATH",
        help="Append-only log of rewrite outcomes",
    )
    parser.add_argument(
        "--rule",
        type=Path,
        default=Path("rules/swe/coding-style.md"),
        metavar="PATH",
        help="Path to coding-style rule for LLM context",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print proposed bullet but do not write to disk",
    )
    parser.add_argument(
        "--run-record-json",
        type=Path,
        default=None,
        metavar="PATH",
        help="Path to a SkillRunEntry JSON file (bypasses Cognee search)",
    )
    args = parser.parse_args()

    return asyncio.run(
        _main_async(
            skill_path=args.skill_path,
            backup_dir=args.backup_dir,
            rewrite_log=args.rewrite_log,
            rule_path=args.rule,
            dry_run=args.dry_run,
            run_record_path=args.run_record_json,
        )
    )


if __name__ == "__main__":
    sys.exit(main())
