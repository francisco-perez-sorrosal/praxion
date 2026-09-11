#!/usr/bin/env python3
"""F11: `.ai-state/doc_manifest.yaml` is fresh vs. the surfaces it indexes.

Conditional on `.ai-state/doc_manifest.yaml` present -- it is *generated*,
never hand-edited, by `scripts/build_doc_manifest.py`, so its absence is a
skip, not a finding. When present, compares its `generated_at` timestamp
against the most recent commit that changed *which* surfaces exist under
`docs/` and `.ai-state/`, and WARNs (never blocks) when the manifest predates
that commit -- the builder was not re-run, so the dashboard's navigation lags
current state until `python3 scripts/build_doc_manifest.py` runs.

Two exclusions are both load-bearing, not niceties -- dropping either turns
this into a gate that WARNs on the steady state after every finalize-hook run,
which carries no signal:

1. **The manifest's own regeneration commit is excluded by sha, not by
   path.** The builder stamps `generated_at` *before* the commit that carries
   the regenerated manifest, and that same commit routinely also touches
   `docs/` (a re-rendered page, a moved doc). A comparison that does not
   exclude this specific commit WARNs on every finalize-hook run.
   `git log -1 --format=%H -- .ai-state/doc_manifest.yaml` names the commit to
   exclude; every candidate commit sharing that sha is skipped, however many
   other paths it also touched.
2. **Only a commit that changes the indexed *set* can stale the manifest.**
   The manifest indexes which surfaces exist, not their contents, so a commit
   that edits, moves rows within, or deletes text inside an
   already-indexed file leaves the manifest correct -- and `.ai-state/`
   receives such commits constantly (e.g. a tech-debt row migrating between
   `TECH_DEBT_LEDGER.md` and `TECH_DEBT_RESOLVED.md`, both already indexed).
   `--diff-filter=ADR` restricts the scan to commits that Added, Deleted, or
   Renamed a file -- never plain Modifies.

This is a faithful transcription of F11's documented procedure
(`agents/sentinel.md`), not a redesign: a strictly-better rebuild-and-compare
(re-running the builder and diffing modulo `generated_at`/`last_modified`) is
a deliberately deferred improvement, recorded in this pipeline's
`LEARNINGS.md`.

`run_f11` can land in **six** states, and they are not all the same kind of
thing. Four are genuine skips -- the check was asked to examine reality and
could not, so `--json` carries a `skipped` tagged union
(`{"reason": ..., "detail": ...}`, matching `check_adr_reciprocity.py`'s
`_skipped_report` shape) rather than an empty findings list a consumer cannot
tell apart from "ran and found nothing":

- `manifest-absent` -- the manifest is designed to be absent sometimes (it is
  *generated*, never hand-edited); this is the row's own Conditional clause.
- `manifest-unreadable` -- the manifest exists (`is_file()` is true) but its
  bytes could not be turned into a report: a non-UTF-8 encoding
  (`UnicodeDecodeError`) or an OS-level read failure such as a `0o000` mode
  (`PermissionError`). Distinct from `manifest-absent` -- "the file is not
  there" and "the file is there and I cannot read it" are different facts for
  a `--json` consumer, and collapsing them would make the second look like
  the design-expected first.
- `generated-at-unparseable` -- the manifest was read successfully but its
  one load-bearing field is corrupt; a degraded state, not an unreadable one.
- `git-unanswerable` -- git itself could not answer (no repository, no
  history for the scanned paths); an environment problem, not a manifest one.

The read that can raise `manifest-unreadable` is caught at its own call
site, inside `run_f11`, rather than left to an outer handler in `main`: this
is what makes `run_f11` **total** -- every path through it returns one of the
six well-formed states below, so `--json` can never hand a consumer an empty
stdout or a bare traceback. `main`'s own `except OSError` is a last-resort
backstop for failures outside `run_f11` (e.g. `resolve_repo_root`), not the
mechanism this envelope's well-formedness depends on.

The other two states are NOT skips -- the check ran to completion and
concluded there is nothing to flag, which is a real (if boring) answer:

- no qualifying add/delete/rename commit exists to compare the manifest
  against;
- the manifest is genuinely fresh.

Both return `skipped: None, findings: []` -- "ran and found nothing" is one
value, reused; "could not run" is a different value, never collapsed into it.

Invocation:

    check_doc_manifest_freshness.py                  # human-readable summary
    check_doc_manifest_freshness.py --json           # machine-readable JSON envelope
    check_doc_manifest_freshness.py --check          # exit 1 when any finding, else 0
    check_doc_manifest_freshness.py --repo-root DIR  # operate on another checkout (tests)

Exit code: 0 by default (advisory, WARN-only). With --check, 1 when >=1
finding is present -- a skip is never a finding, so --check exits 0 on every
skip regardless of reason. Exit code 2 when the resolved root is a
plugin-cache path.

Invoked by the sentinel's F dimension (`--json`); also runnable standalone.

Cites: SYSTEMS_PLAN.md § The Extraction Contract; CLAUDE.md § Pragmatism.
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from datetime import datetime
from pathlib import Path

from _git_runner import git_output
from _repo_root import is_plugin_cache_path, resolve_repo_root
from _script_cli import configure_logging

SCRIPT_DIR = Path(__file__).resolve().parent

CHECK_ID = "F11"
SEVERITY = "warn"

# Relative to repo_root -- the file this check is conditional on.
MANIFEST_REL = ".ai-state/doc_manifest.yaml"

# The two directories whose added/deleted/renamed files can stale the
# manifest's indexed set. Matches the manifest's own scan scope.
_SCANNED_PATHS = ("docs/", ".ai-state/")

_GENERATED_AT_RE = re.compile(r"^generated_at:\s*['\"]?([^'\"\n]+?)['\"]?\s*$", re.MULTILINE)

logger = logging.getLogger("check_doc_manifest_freshness")


# -- Parsing ------------------------------------------------------------------


def _parse_iso(value: str) -> datetime | None:
    """Parse an ISO-8601 timestamp, tolerating a trailing `Z` designator.

    `datetime.fromisoformat` accepts `Z` from Python 3.11 on; normalizing it
    to `+00:00` first keeps this correct on any 3.11+ interpreter rather than
    depending on that version-specific improvement.
    """
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _generated_at(manifest_text: str) -> datetime | None:
    """Return the manifest's `generated_at` timestamp, or None if unparseable."""
    match = _GENERATED_AT_RE.search(manifest_text)
    if match is None:
        return None
    return _parse_iso(match.group(1))


# -- Git queries ----------------------------------------------------------------


def _self_commit_sha(repo_root: Path) -> str | None:
    """Return the sha of the commit that last touched the manifest itself."""
    return git_output(repo_root, "log", "-1", "--format=%H", "--", MANIFEST_REL, logger=logger)


def _commit_log(repo_root: Path) -> str | None:
    """Return the raw `git log` text for adds/deletes/renames under the scanned
    paths, or None if git could not answer at all (no repository, or any other
    failure `git_output` swallows).

    Kept separate from `_newest_indexed_set_change` so "git could not answer"
    (a skip) and "git answered, no qualifying commit in the answer" (a clean
    result) are two distinct return values instead of one `None` standing for
    both -- exactly the collapse this envelope exists to avoid.
    """
    return git_output(
        repo_root,
        "log",
        "--diff-filter=ADR",
        "--format=%H %cI",
        "--",
        *_SCANNED_PATHS,
        logger=logger,
    )


def _newest_indexed_set_change(log: str, self_sha: str | None) -> tuple[str, datetime] | None:
    """Return `(sha, committer_date)` of the newest add/delete/rename in `log`,
    excluding `self_sha`, or None if none exists.

    `self_sha` is excluded by direct sha comparison (exclusion 1 above), never
    by narrowing the scanned paths -- the manifest's own regeneration commit
    can legitimately also add or rename a `docs/` page in the same commit, and
    a path-based exclusion would not catch that case.
    """
    for line in log.splitlines():
        sha, _, date_str = line.partition(" ")
        if not sha or sha == self_sha:
            continue
        committer_date = _parse_iso(date_str)
        if committer_date is not None:
            return sha, committer_date
    return None


# -- Envelope -------------------------------------------------------------------


def _skipped_report(reason: str, detail: str) -> dict:
    """The tagged-union skip envelope -- shape matches
    `check_adr_reciprocity.py::_skipped_report`, generalized to `detail` since
    F11's three skip reasons don't all name a filesystem path.
    """
    return {"check": CHECK_ID, "skipped": {"reason": reason, "detail": detail}, "findings": []}


def _report(findings: list[dict]) -> dict:
    """The clean envelope: the check ran to completion, `findings` is the answer."""
    return {"check": CHECK_ID, "skipped": None, "findings": findings}


# -- Core detection -------------------------------------------------------------

_SKIP_MANIFEST_ABSENT = "manifest-absent"
_SKIP_MANIFEST_UNREADABLE = "manifest-unreadable"
_SKIP_GENERATED_AT_UNPARSEABLE = "generated-at-unparseable"
_SKIP_GIT_UNANSWERABLE = "git-unanswerable"


def run_f11(repo_root: Path) -> dict:
    """Return F11's envelope: `skipped` when the check could not examine
    reality, else `findings` -- a single WARN when the manifest predates the
    newest add/delete/rename under `docs/` or `.ai-state/`, else `[]`.

    Total over its input: every return statement below produces a
    well-formed envelope, so no exception raised while examining the
    manifest or the repository ever escapes to a caller. See the module
    docstring for the six-state partition this implements.
    """
    manifest_path = repo_root / MANIFEST_REL
    if not manifest_path.is_file():
        return _skipped_report(_SKIP_MANIFEST_ABSENT, MANIFEST_REL)

    try:
        manifest_text = manifest_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        return _skipped_report(_SKIP_MANIFEST_UNREADABLE, f"{MANIFEST_REL}: {exc}")

    generated_at = _generated_at(manifest_text)
    if generated_at is None:
        return _skipped_report(_SKIP_GENERATED_AT_UNPARSEABLE, MANIFEST_REL)

    self_sha = _self_commit_sha(repo_root)
    log = _commit_log(repo_root)
    if log is None:
        return _skipped_report(_SKIP_GIT_UNANSWERABLE, " ".join(_SCANNED_PATHS))

    candidate = _newest_indexed_set_change(log, self_sha)
    if candidate is None:
        return _report([])

    sha, committer_date = candidate
    if generated_at >= committer_date:
        return _report([])

    return _report(
        [
            {
                "check": CHECK_ID,
                "severity": SEVERITY,
                "entity": MANIFEST_REL,
                "message": (
                    f"{MANIFEST_REL}: generated_at={generated_at.isoformat()} predates "
                    f"{sha[:12]} ({committer_date.isoformat()}), which added, deleted, or "
                    "renamed a docs/ or .ai-state/ surface -- run "
                    "`python3 scripts/build_doc_manifest.py` to refresh"
                ),
            }
        ]
    )


# -- CLI --------------------------------------------------------------------------


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="check_doc_manifest_freshness",
        description=(
            "Advisory: flag .ai-state/doc_manifest.yaml when its generated_at "
            "predates the newest commit that added, deleted, or renamed a docs/ "
            "or .ai-state/ surface. Called by sentinel F11."
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
        help="Exit 1 when any F11 finding is present (opt-in CI gate).",
    )
    parser.add_argument("--verbose", action="store_true", help="Enable DEBUG logging.")
    return parser.parse_args(argv)


def _format_human(report: dict) -> str:
    if report["skipped"] is not None:
        return f"check_doc_manifest_freshness: skipped ({report['skipped']['reason']})"
    findings = report["findings"]
    if not findings:
        return "check_doc_manifest_freshness: no F11 violations found."
    lines = [f"F11 ({len(findings)} finding(s)):"]
    for f in findings:
        lines.append(f"  - {f['message']}")
    return "\n".join(lines)


def _run(args: argparse.Namespace) -> int:
    repo_root = resolve_repo_root(args.repo_root, script_dir=SCRIPT_DIR)
    if is_plugin_cache_path(repo_root):
        logger.error("Refusing to operate on plugin-cache path: %s", repo_root)
        return 2

    report = run_f11(repo_root)
    findings = report["findings"]

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        text = _format_human(report)
        if findings:
            print(text, file=sys.stderr)
        else:
            print(text)

    return 1 if (args.check and findings) else 0


def main(argv: list[str] | None = None) -> None:
    args = _parse_args(argv)
    configure_logging(args.verbose)
    try:
        code = _run(args)
    except OSError as exc:
        logger.error("check_doc_manifest_freshness: %s", exc)
        sys.exit(0)
    sys.exit(code)


if __name__ == "__main__":
    main()
