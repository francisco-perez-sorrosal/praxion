#!/usr/bin/env python3
"""P07: undisposed Architecture Challenges in specialist design docs.

A specialist agent (interface-designer, agentic-transactions-architect,
discipline-consultant) can raise a load-bearing question the pipeline never
answers. Two document shapes carry that question, each with its own
disposition convention:

* `.ai-work/<slug>/INTERFACE_DESIGN.md` / `TRANSACTIONS_DESIGN.md` -- a
  non-empty `## Architecture Challenges` section is undisposed when no
  `Status:`/`Decision:`/`Resolved:` line appears in its body before the next
  `##` heading.
* `.ai-work/<slug>/CONSULT_<discipline>.md` -- the discipline-consultant's
  deliberately distinct `## Challenges` heading (never `## Architecture
  Challenges`), broken into `### CH-NN` entries. An entry is undisposed when
  its `**Disposition:**` field is absent, empty, or still the
  `<!-- convener, Round 2 -->` (or equivalent `<!-- ... -->`) placeholder.
  **Absent counts as undisposed** -- a fragment that omits the per-entry
  field entirely (substituting a trailing summary table of `<!-- convener
  -->` cells) raises the same finding as one that left the field unfilled;
  the check inspects the field beside the claim it answers, not a table that
  can be satisfied by declining to write the field.

A file with no Architecture Challenges / Challenges section at all is clean
by definition -- a specialist that raised nothing has nothing to dispose.

Golden bad-cases (content verified against this docstring's own wording):
`tests/fixtures/sentinel/challenge_no_disposition/INTERFACE_DESIGN.md` and
`tests/fixtures/sentinel/consult_no_disposition/CONSULT_statistician.md` +
`CONSULT_evidence-appraiser.md` (the two ways a disposition can be missing).
The real substrate (`.ai-work/<slug>/`) is gitignored, so the canary copies
these fixtures' *content* into a runtime `tmp_path/.ai-work/<slug>/` tree
rather than pointing this script at the committed fixture directory directly
(`rules/swe/testing-conventions.md § Fixtures Under Gitignored Paths`).

Skip conditions (exit 0, `skipped.P07` set): `.ai-work/` absent from
`repo_root`.

Invocation:

    check_specialist_dispositions.py                  # human-readable summary
    check_specialist_dispositions.py --json            # machine-readable envelope
    check_specialist_dispositions.py --check            # exit 1 on any finding
    check_specialist_dispositions.py --repo-root DIR   # operate on another checkout (tests)

Exit code: 0 by default (advisory). With --check, 1 when >=1 finding is
present. Exit code 2 when the resolved root is a plugin-cache path.
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from pathlib import Path

from _repo_root import is_plugin_cache_path, resolve_repo_root
from _script_cli import configure_logging

SCRIPT_DIR = Path(__file__).resolve().parent
SCRIPT_NAME = "check_specialist_dispositions"

AI_WORK_REL = ".ai-work"

# Keyed declaration (DS-B): even a single-check family script declares the
# tuple form -- the obligation follows the promise the row makes, not the
# current member count.
CHECK_IDS: tuple[str, ...] = ("P07",)
_CHECK_ID = CHECK_IDS[0]
_SEVERITY = "important"

_DESIGN_DOC_NAMES = ("INTERFACE_DESIGN.md", "TRANSACTIONS_DESIGN.md")
_ARCHITECTURE_CHALLENGES_HEADING = "Architecture Challenges"
_CONSULT_CHALLENGES_HEADING = "Challenges"

# A disposition line for the design-doc shape: any of the three named markers
# starting a line inside the section body.
_DESIGN_DOC_DISPOSITION = re.compile(r"^(?:Status|Decision|Resolved):", re.MULTILINE)

# `## <heading>` (not `###` or deeper) -- the section-body terminator.
_H2_HEADING = re.compile(r"^##(?!#).*$", re.MULTILINE)

_CH_ENTRY_HEADING = re.compile(r"^###\s+(CH-\d+)\b.*$", re.MULTILINE)
_DISPOSITION_FIELD = re.compile(r"\*\*Disposition:\*\*\s*(.*)")
_PLACEHOLDER_VALUE = re.compile(r"^<!--.*-->$")

logger = logging.getLogger(SCRIPT_NAME)


# -- Section parsing ------------------------------------------------------------


def _section_body(text: str, heading: str) -> str | None:
    """Return the body of the first `## <heading>` section, or None if absent.

    The body spans from immediately after the heading line to the next `##`
    (or shallower) heading, or end of file -- a `###` subsection does not end it.
    """
    marker = re.compile(rf"^##\s+{re.escape(heading)}\s*$", re.MULTILINE)
    match = marker.search(text)
    if match is None:
        return None
    start = match.end()
    next_heading = _H2_HEADING.search(text, start)
    end = next_heading.start() if next_heading else len(text)
    return text[start:end]


def _ch_entries(challenges_body: str) -> list[tuple[str, str]]:
    """Return `(ch_id, entry_text)` pairs for each `### CH-NN` subsection."""
    headings = list(_CH_ENTRY_HEADING.finditer(challenges_body))
    entries = []
    for index, heading in enumerate(headings):
        start = heading.start()
        end = headings[index + 1].start() if index + 1 < len(headings) else len(challenges_body)
        entries.append((heading.group(1), challenges_body[start:end]))
    return entries


def _is_undispositioned(entry_text: str) -> bool:
    """True when a CH-NN entry's Disposition field is absent, empty, or a placeholder."""
    match = _DISPOSITION_FIELD.search(entry_text)
    if match is None:
        return True
    value = match.group(1).strip()
    if not value:
        return True
    return bool(_PLACEHOLDER_VALUE.match(value))


# -- Per-document checks ---------------------------------------------------------


def _check_design_doc(slug: str, filename: str, text: str) -> list[dict]:
    body = _section_body(text, _ARCHITECTURE_CHALLENGES_HEADING)
    if body is None or not body.strip():
        return []
    if _DESIGN_DOC_DISPOSITION.search(body):
        return []
    return [
        {
            "check": _CHECK_ID,
            "severity": _SEVERITY,
            "entity": f"{slug}/{filename}",
            "message": (
                f"{slug}/{filename}: non-empty ## Architecture Challenges section "
                "carries no disposition (no Status:/Decision:/Resolved: line) -- a "
                "specialist raised a load-bearing question the pipeline never answered"
            ),
        }
    ]


def _check_consult_fragment(slug: str, filename: str, text: str) -> list[dict]:
    body = _section_body(text, _CONSULT_CHALLENGES_HEADING)
    if body is None or not body.strip():
        return []
    findings = []
    for ch_id, entry_text in _ch_entries(body):
        if not _is_undispositioned(entry_text):
            continue
        findings.append(
            {
                "check": _CHECK_ID,
                "severity": _SEVERITY,
                "entity": f"{slug}/{filename}#{ch_id}",
                "message": (
                    f"{slug}/{filename}: {ch_id} has no Disposition -- absent, empty, "
                    "or still the convener placeholder -- the convener never "
                    "adjudicated a challenge the consultant raised"
                ),
            }
        )
    return findings


def _check_slug(slug_dir: Path) -> list[dict]:
    findings: list[dict] = []
    for name in _DESIGN_DOC_NAMES:
        doc = slug_dir / name
        if doc.is_file():
            findings.extend(_check_design_doc(slug_dir.name, name, doc.read_text(encoding="utf-8")))
    for consult_path in sorted(slug_dir.glob("CONSULT_*.md")):
        findings.extend(
            _check_consult_fragment(
                slug_dir.name, consult_path.name, consult_path.read_text(encoding="utf-8")
            )
        )
    return findings


# -- Envelope (DS-A, keyed) -------------------------------------------------------


def classify(repo_root: Path) -> dict:
    """Build the P07 envelope over every `.ai-work/<slug>/` directory."""
    ai_work = repo_root / AI_WORK_REL
    if not ai_work.is_dir():
        return _skipped_report("substrate-absent", str(ai_work))

    findings: list[dict] = []
    slugs_examined = 0
    for slug_dir in sorted(p for p in ai_work.iterdir() if p.is_dir()):
        slugs_examined += 1
        findings.extend(_check_slug(slug_dir))

    return {
        "script": SCRIPT_NAME,
        "checks": list(CHECK_IDS),
        "skipped": {_CHECK_ID: None},
        "examined": {_CHECK_ID: {"slugs": slugs_examined}},
        "findings": findings,
        "info": {},
        "withheld": [],
        "bound": {
            _CHECK_ID: (
                "P07 clean means every specialist design doc's Architecture "
                "Challenges and every discipline-consultant fragment's Challenges "
                "are disposed; it does not mean no challenges were ever raised."
            )
        },
    }


def _skipped_report(reason: str, path: str) -> dict:
    return {
        "script": SCRIPT_NAME,
        "checks": list(CHECK_IDS),
        "skipped": {_CHECK_ID: {"reason": reason, "path": path}},
        "examined": {_CHECK_ID: None},
        "findings": [],
        "info": {},
        "withheld": [],
        "bound": {_CHECK_ID: "P07 did not run; no disposition conclusion can be drawn."},
    }


# -- CLI ----------------------------------------------------------------------


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog=SCRIPT_NAME,
        description=(
            "Advisory: flag undisposed ## Architecture Challenges sections and "
            "undisposed discipline-consultant CH-NN entries under .ai-work/<slug>/. "
            "Called by sentinel P07."
        ),
    )
    parser.add_argument(
        "--repo-root",
        default=None,
        metavar="DIR",
        help="Repository to operate on (default: discovered via git rev-parse).",
    )
    parser.add_argument("--json", action="store_true", help="Machine-readable JSON output.")
    parser.add_argument(
        "--check",
        action="store_true",
        help="Exit 1 when any P07 finding is present (opt-in CI gate).",
    )
    parser.add_argument("--verbose", action="store_true", help="Enable DEBUG logging.")
    return parser.parse_args(argv)


def _format_human(report: dict) -> str:
    if report["skipped"][_CHECK_ID] is not None:
        return f"{SCRIPT_NAME}: skipped ({report['skipped'][_CHECK_ID]['reason']})"
    findings = report["findings"]
    if not findings:
        slugs = report["examined"][_CHECK_ID]["slugs"]
        return f"{SCRIPT_NAME}: no P07 violations across {slugs} .ai-work/ slug(s)."
    lines = [f"P07 IMPORTANT ({len(findings)} undisposed challenge(s)):"]
    lines.extend(f"  - {f['message']}" for f in findings)
    return "\n".join(lines)


def _run(args: argparse.Namespace) -> int:
    repo_root = resolve_repo_root(args.repo_root, script_dir=SCRIPT_DIR)
    if is_plugin_cache_path(repo_root):
        logger.error("Refusing to operate on plugin-cache path: %s", repo_root)
        return 2

    report = classify(repo_root)

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        text = _format_human(report)
        print(text, file=sys.stderr if report["findings"] else sys.stdout)

    return 1 if (args.check and report["findings"]) else 0


def main(argv: list[str] | None = None) -> None:
    args = _parse_args(argv)
    configure_logging(args.verbose)
    try:
        code = _run(args)
    except OSError as exc:
        logger.error("%s: %s", SCRIPT_NAME, exc)
        sys.exit(0)
    sys.exit(code)


if __name__ == "__main__":
    main()
