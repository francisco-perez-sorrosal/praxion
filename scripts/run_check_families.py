#!/usr/bin/env python3
"""One Bash call for the sentinel's Family dispatch table, not eleven.

Measured over the last two sweeps, the sentinel's Phase 3 (Pass 1) spent
roughly 7 Bash calls invoking the ~11 family scripts in `agents/sentinel.md`'s
"Family dispatch (auto)" table, ~12 more calls parsing each script's JSON
envelope, and ~13 more triaging the ~124 WARN entries that came back --
*more* calls than the table's own row-by-row dispatch it replaced. This
script collapses all three phases into one call: it parses the dispatch
table itself (never a hard-coded family list, so a new table row is picked
up automatically), runs every listed invocation, and emits a single
pre-formatted digest the sentinel can copy straight into its report.

Table shape (see agents/sentinel.md, "Family dispatch (auto)"):

    | Substrate (skip when absent) | Invocation | Rows |
    |---|---|---|
    | ... | `python3 scripts/check_foo.py --json` | F01 F02 |

Golden bad-cases this script defends against:

* A family script prints something that is not JSON on stdout (a traceback,
  a stray log line ahead of the payload). Its result becomes a `runner-error`
  entry for that family -- the aggregate for every *other* family is still
  produced, and the runner itself never raises.
* A table row names a script that does not exist (a rename that forgot to
  update the row, a typo). Same treatment: a `runner-error`, not a crash.

Declared limits:

* JSON is parsed regardless of exit code. Most family scripts exit 0 always
  under plain `--json` (no `--check`), but `regenerate_adr_index.py --json
  --check` (the DL03 row) intentionally exits 1 when findings exist -- and
  still prints valid JSON first. Gating on exit code would misreport a real
  DL03 finding as a runner error, so exit code is only ever used to enrich
  the error message when the JSON itself fails to parse.
* Each family script's own envelope shape (`checks`/`skipped`/`examined`/
  `bound`, keyed by check id -- except DL03, whose envelope uses the
  singular `check`/`skipped`/`examined`/`bound` fields directly, flat) is
  read as-is; this script does not validate that shape beyond what it needs
  to aggregate.
* Not registered in `.pre-commit-config.yaml`: this is a sentinel-dispatched
  reporting aggregator, not a commit gate -- nothing here blocks a commit,
  and its own exit code is always 0 (see below).

Invocation:

    run_check_families.py --repo-root DIR             # Markdown digest (default)
    run_check_families.py --repo-root DIR --json       # machine-readable envelope
    run_check_families.py --repo-root DIR --max-entities N

Exit code: always 0. This is an advisory aggregator over scripts that already
carry their own `--check` gating semantics; it changes nothing about them.
"""

from __future__ import annotations

import argparse
import json
import shlex
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

from _repo_root import resolve_repo_root

SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_TIMEOUT = 120.0
DEFAULT_MAX_ENTITIES = 5

_TABLE_HEADER = "| Substrate (skip when absent) | Invocation | Rows |"


@dataclass(frozen=True)
class DispatchRow:
    """One row of the Family dispatch table: what to run and which checks it covers."""

    substrate: str
    invocation: str
    check_ids: tuple[str, ...]

    @property
    def family(self) -> str:
        """The dispatched script's module stem, e.g. `check_behavioral_contract`."""
        parts = shlex.split(self.invocation)
        for part in parts[1:]:
            if part.endswith(".py"):
                return Path(part).stem
        return self.invocation


@dataclass
class CheckAggregate:
    """Accumulated severity counts and sample findings for one check id."""

    family: str
    fail: int = 0
    warn: int = 0
    info: int = 0
    skipped: object = None
    examined: object = None
    bound: object = None
    entities: list[tuple[str, str]] = field(default_factory=list)

    def bump(self, severity: str) -> None:
        if severity == "fail":
            self.fail += 1
        elif severity == "warn":
            self.warn += 1
        elif severity == "info":
            self.info += 1


@dataclass
class RunnerError:
    """A family invocation that produced no usable JSON."""

    family: str
    invocation: str
    reason: str


def parse_dispatch_table(sentinel_md: Path) -> list[DispatchRow]:
    """Parse the Family dispatch table out of `agents/sentinel.md`.

    Reads only the rows between the header line and the first line that is
    not a table row -- the table is followed by prose, never more rows past
    a blank line, so a `not line.startswith("|")` stop condition is exact.
    """
    lines = sentinel_md.read_text(encoding="utf-8").splitlines()
    try:
        header_index = next(i for i, line in enumerate(lines) if line.strip() == _TABLE_HEADER)
    except StopIteration:
        raise ValueError(f"Family dispatch header not found in {sentinel_md}") from None

    rows: list[DispatchRow] = []
    # header_index + 1 is the `|---|---|---|` separator; data rows start after it.
    for line in lines[header_index + 2 :]:
        if not line.strip().startswith("|"):
            break
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) < 3:
            continue
        substrate, invocation_cell, rows_cell = cells[0], cells[1], cells[2]
        invocation = _extract_backticked(invocation_cell)
        if invocation is None:
            continue
        rows.append(
            DispatchRow(
                substrate=substrate,
                invocation=invocation,
                check_ids=tuple(rows_cell.split()),
            )
        )
    return rows


def _extract_backticked(cell: str) -> str | None:
    """Return the text inside the first `` `...` `` span in `cell`, or None."""
    start = cell.find("`")
    if start == -1:
        return None
    end = cell.find("`", start + 1)
    if end == -1:
        return None
    return cell[start + 1 : end]


def _build_command(invocation: str) -> list[str]:
    """Turn an invocation string into an argv, swapping `python3`/`python` for `sys.executable`."""
    parts = shlex.split(invocation)
    if parts and parts[0] in ("python3", "python"):
        parts[0] = sys.executable
    return parts


def run_family(row: DispatchRow, repo_root: Path, timeout: float) -> tuple[dict | None, str | None]:
    """Run one dispatch row's invocation, returning (payload, error) -- exactly one is None.

    JSON is parsed from stdout regardless of exit code (see module docstring's
    "Declared limits"). Only a launch failure, a timeout, or unparseable stdout
    produces an error.
    """
    command = _build_command(row.invocation)
    script = command[1] if len(command) > 1 else None
    if script is not None and not (repo_root / script).exists():
        return None, f"script not found: {script}"

    try:
        result = subprocess.run(
            command, cwd=repo_root, capture_output=True, text=True, timeout=timeout
        )
    except subprocess.TimeoutExpired:
        return None, f"timed out after {timeout:g}s"
    except OSError as exc:
        return None, f"failed to launch: {exc}"

    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError:
        stderr_tail = result.stderr.strip().splitlines()[-1:] or [""]
        detail = f": {stderr_tail[0]}" if stderr_tail[0] else ""
        return None, f"exit {result.returncode}, unparseable stdout{detail}"

    return payload, None


def _declared_checks(payload: dict) -> tuple[list[str], bool]:
    """Return (check ids, is_flat) from a family payload's own `checks`/`check` field."""
    if "checks" in payload:
        return list(payload["checks"]), False
    if "check" in payload:
        return [payload["check"]], True
    return [], False


def _field_for(payload: dict, field_name: str, check_id: str, flat: bool) -> object:
    """Read `field_name` for `check_id`, honoring the flat (DL03) vs. keyed envelope shape."""
    value = payload.get(field_name)
    if flat:
        return value
    if isinstance(value, dict):
        return value.get(check_id)
    return value


def aggregate_family(
    row: DispatchRow, payload: dict, max_entities: int
) -> dict[str, CheckAggregate]:
    """Fold one family's JSON payload into a per-check-id aggregate."""
    declared, flat = _declared_checks(payload)
    check_ids = declared or list(row.check_ids)

    aggregates = {
        check_id: CheckAggregate(
            family=row.family,
            skipped=_field_for(payload, "skipped", check_id, flat),
            examined=_field_for(payload, "examined", check_id, flat),
            bound=_field_for(payload, "bound", check_id, flat),
        )
        for check_id in check_ids
    }

    for finding in payload.get("findings", []):
        check_id = finding.get("check")
        agg = aggregates.setdefault(check_id, CheckAggregate(family=row.family))
        agg.bump(str(finding.get("severity", "")).lower())
        if len(agg.entities) < max_entities:
            agg.entities.append((str(finding.get("entity", "")), str(finding.get("message", ""))))

    return aggregates


def build_aggregate(
    rows: list[DispatchRow], repo_root: Path, timeout: float, max_entities: int
) -> dict:
    """Run every dispatch row and fold the results into one aggregate envelope."""
    families: list[dict] = []
    checks: dict[str, CheckAggregate] = {}
    runner_errors: list[RunnerError] = []

    for row in rows:
        payload, error = run_family(row, repo_root, timeout)
        if error is not None:
            families.append(
                {
                    "name": row.family,
                    "invocation": row.invocation,
                    "check_ids": list(row.check_ids),
                    "status": "runner-error",
                }
            )
            runner_errors.append(
                RunnerError(family=row.family, invocation=row.invocation, reason=error)
            )
            continue

        families.append(
            {
                "name": row.family,
                "invocation": row.invocation,
                "check_ids": list(row.check_ids),
                "status": "ok",
            }
        )
        checks.update(aggregate_family(row, payload, max_entities))

    totals = {
        "families": len(rows),
        "checks": len(checks),
        "fail": sum(agg.fail for agg in checks.values()),
        "warn": sum(agg.warn for agg in checks.values()),
        "info": sum(agg.info for agg in checks.values()),
    }

    return {
        "families": families,
        "checks": checks,
        "totals": totals,
        "runner_errors": runner_errors,
    }


def _to_json_safe(aggregate: dict) -> dict:
    """Render the aggregate's dataclass values into plain JSON-serializable structures."""
    checks_json = {
        check_id: {
            "family": agg.family,
            "fail": agg.fail,
            "warn": agg.warn,
            "info": agg.info,
            "skipped": agg.skipped,
            "examined": agg.examined,
            "bound": agg.bound,
            "entities": [{"entity": e, "message": m} for e, m in agg.entities],
        }
        for check_id, agg in sorted(aggregate["checks"].items())
    }
    runner_errors_json = [
        {"family": e.family, "invocation": e.invocation, "reason": e.reason}
        for e in aggregate["runner_errors"]
    ]
    return {
        "families": aggregate["families"],
        "checks": checks_json,
        "totals": aggregate["totals"],
        "runner_errors": runner_errors_json,
    }


def render_table(aggregate: dict, max_entities: int) -> str:
    """Render the Markdown digest: summary table, per-check entity detail, footer."""
    checks: dict[str, CheckAggregate] = aggregate["checks"]
    lines = [
        "| Check | Family | FAIL | WARN | INFO | Skipped | Examined | Sample entity |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for check_id in sorted(checks):
        agg = checks[check_id]
        sample = agg.entities[0][0] if agg.entities else "-"
        lines.append(
            f"| {check_id} | {agg.family} | {agg.fail} | {agg.warn} | {agg.info} | "
            f"{_compact(agg.skipped)} | {_compact(agg.examined)} | {sample} |"
        )

    detail_lines = []
    for check_id in sorted(checks):
        agg = checks[check_id]
        if agg.fail + agg.warn + agg.info == 0 or not agg.entities:
            continue
        entries = "; ".join(f"{e} — {m}" for e, m in agg.entities[:max_entities])
        detail_lines.append(f"- **{check_id}** ({agg.family}): {entries}")

    if detail_lines:
        lines.append("")
        lines.extend(detail_lines)

    runner_errors = aggregate["runner_errors"]
    if runner_errors:
        lines.append("")
        lines.append("### Runner errors")
        lines.extend(f"- **{e.family}** (`{e.invocation}`): {e.reason}" for e in runner_errors)

    totals = aggregate["totals"]
    lines.append("")
    lines.append(
        f"families: {totals['families']} · checks: {totals['checks']} · "
        f"fail: {totals['fail']} · warn: {totals['warn']} · "
        f"calls saved: {totals['families']} → 1"
    )
    return "\n".join(lines)


def _compact(value: object) -> str:
    """Render a skipped/examined value compactly for a table cell."""
    if value is None:
        return "-"
    if isinstance(value, dict):
        return ", ".join(f"{k}={v}" for k, v in value.items()) or "-"
    return str(value)


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="run_check_families",
        description=(
            "Run every family script in agents/sentinel.md's Family dispatch table in one "
            "call and emit a pre-formatted digest."
        ),
    )
    parser.add_argument(
        "--repo-root", default=None, metavar="DIR", help="Repository to operate on."
    )
    output = parser.add_mutually_exclusive_group()
    output.add_argument("--json", action="store_true", help="Machine-readable JSON envelope.")
    output.add_argument("--table", action="store_true", help="Markdown digest table (default).")
    parser.add_argument(
        "--max-entities",
        type=int,
        default=DEFAULT_MAX_ENTITIES,
        metavar="N",
        help=f"Sample entities per check (default: {DEFAULT_MAX_ENTITIES}).",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=DEFAULT_TIMEOUT,
        metavar="SECONDS",
        help=f"Per-family timeout (default: {DEFAULT_TIMEOUT:g}s).",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = _parse_args(argv)
    repo_root = resolve_repo_root(args.repo_root, script_dir=SCRIPT_DIR)
    rows = parse_dispatch_table(repo_root / "agents" / "sentinel.md")
    aggregate = build_aggregate(rows, repo_root, args.timeout, args.max_entities)

    if args.json:
        print(json.dumps(_to_json_safe(aggregate), indent=2))
    else:
        print(render_table(aggregate, args.max_entities))

    sys.exit(0)


if __name__ == "__main__":
    main()
