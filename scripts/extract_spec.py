#!/usr/bin/env python3
"""Spec extraction: derive `SPEC_EXTRACT.md`, the design-free view of a plan.

    extract_spec.py <slug> [--repo-root DIR] [--check] [--json] [--verbose]

Reads `.ai-work/<slug>/SYSTEMS_PLAN.md` (required) and
`.ai-work/<slug>/TASK_BRIEF.md` (optional; only its `## Key Signals` section)
and writes `.ai-work/<slug>/SPEC_EXTRACT.md`: the key signals, the acceptance
criteria and the behavioral specification, verbatim with HTML comments
stripped, and no other section of the plan. Whoever designs tests from the spec
alone reads this file instead of the plan, so no design text can reach them.

The extract is a derived value with one writer: this command. It carries a
digest of its own body (`sha256`, first 12 hex characters); a hand edit or a
spec change makes it stale, which `--check` detects by regenerating in memory
and comparing bytes. `--check` never writes.

The repository root is `--repo-root`, else the git toplevel of the working
directory. It is never derived from this file's location: managed projects run
the command through a `~/.local/bin` symlink, where that location is the
plugin, not the project.

Design-vocabulary lint. Design words in the spec would ride the extract to
whoever designs tests from it, so the spec is linted first: blocking findings
over `## Acceptance Criteria` and every line of `## Behavioral Specification`
except its `### Observable Surface` subsection; advisory findings over the key
signals. HTML comments are removed before linting. A token equal to a declared
name -- a backticked name on a list item of `### Observable Surface` -- is
exempt. A blocking finding writes no extract and deletes a previous one, so an
extract on disk is always lint-clean for the spec it embeds. Line numbers refer
to the file the text came from. Each finding is `{rule, severity, section, req,
line, token, message}`.

    DV01  code span: any backticked text; fenced block: one finding per block
          bad  `parse_plan`               good  a span whose text is declared
    DV02  path: a code/config file extension; a leading /, ./, ../ or ~/; a
          slash token with 2+ slashes, a trailing slash, or a segment holding
          an underscore, a dot or a number
          bad  scripts/_spec.py  src/auth/session  docs/v2  README.md
          good pass/fail  input/output  and/or  CLI/HTTP
    DV03  identifier: snake_case, CamelCase with 2+ humps, CONSTANT_CASE with
          an underscore, a dotted lowercase name whose segments have 2+
          characters, call syntax name(), a CLI flag --name
          bad  parse_plan  RefundPolicy  SPEC_MAX_LINES  auth.session
               RefundPolicy.apply()  --strict
          good e.g.  i.e.  Opus  3.11  v0.41.0  a spaced double dash

False positives are settled by declaration, not by a growing allowlist: a brand
or external name goes under `### Observable Surface`, or the text is rephrased
("read, write or delete" for a slash chain). The lint is a tripwire, not a
proof; accepted false negatives are single-word identifiers (`validate`) and a
design paraphrased in prose ("the adapter layer").

Exit codes: `0` clean (extract written, or fresh under `--check`); `1`
findings (a stale or missing extract under `--check`); `2` input error (plan
missing, `## Acceptance Criteria` or `## Behavioral Specification` absent or
empty, no requirement block, no resolvable root, bad arguments). A message on
stderr names the input. Advisory findings never change the exit status.

`--json` prints `{"schema": 1, "slug", "extract", "digest", "removed_stale",
"findings"}` on stdout; logs go to stderr. `extract` and `digest` are null
unless a current extract exists.

Stdlib-only and Python 3.9-safe (no runtime `X | Y` unions, no `match`): the
command runs under whichever bare `python3` the project has.
Tests and canaries: `scripts/test_extract_spec.py`.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import re
import sys
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import NamedTuple

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _repo_root import git_toplevel_from_cwd  # noqa: E402
from _script_cli import configure_logging  # noqa: E402

LOG = logging.getLogger("extract_spec")

EXIT_CLEAN = 0
EXIT_FINDINGS = 1
EXIT_INPUT_ERROR = 2

SCHEMA_VERSION = 1
BLOCKING = "blocking"
ADVISORY = "advisory"
RULE_STALE = "stale-extract"
RULE_SPAN, RULE_PATH, RULE_IDENTIFIER = "DV01", "DV02", "DV03"

PLAN_NAME = "SYSTEMS_PLAN.md"
BRIEF_NAME = "TASK_BRIEF.md"
EXTRACT_NAME = "SPEC_EXTRACT.md"
DIGEST_HEX_CHARS = 12

ACCEPTANCE_HEADING = "Acceptance Criteria"
BEHAVIOR_HEADING = "Behavioral Specification"
KEY_SIGNALS_HEADING = "Key Signals"
SURFACE_HEADING = "Observable Surface"

KEY_SIGNALS_ABSENT = "_None: TASK_BRIEF.md absent._"
KEY_SIGNALS_MISSING = "_None: TASK_BRIEF.md has no Key Signals section._"

_SLUG = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*$")
_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)
_H2 = re.compile(r"^## +(.+?)\s*$")
_REQ_HEADING = re.compile(r"^###\s+(REQ-\d+)\b")
_FENCE = re.compile(r"^ {0,3}(`{3,}|~{3,})(.*)$")
_H3 = re.compile(r"^###\s+(.+?)\s*$")
_LIST_ITEM = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s")
_SPAN = re.compile(r"(?<!`)(`+)(?!`)(.+?)(?<!`)\1(?!`)")
_CALL = re.compile(r"[A-Za-z_][\w.]*\(\)")
_TOKEN_SEPARATORS = re.compile(r"""[\s()\[\]{}<>"',;]+""")
_PATH_PREFIX = re.compile(r"^(?:/|\./|\.\./|~/)\S")
_SLASH_SEGMENT_MARK = re.compile(r"[_.\d]")
_SNAKE = re.compile(r"[A-Za-z0-9]_[A-Za-z0-9]")
_CAMEL = re.compile(r"^(?:[A-Z][a-z0-9]+){2,}$|^[a-z][a-z0-9]*(?:[A-Z][a-z0-9]+)+$")
_DOTTED = re.compile(r"^[a-z][a-z0-9]+(?:\.[a-z][a-z0-9]+)+$")
_FLAG = re.compile(r"^--[A-Za-z][\w-]*$")
_TRAILING_PUNCTUATION = ".,:;!?*"

CODE_EXTENSIONS = (
    "py pyi ts tsx js mjs cjs rs go java kt rb sh toml yaml yml json md c4 sql ini cfg"
).split()
_FILE_EXTENSION = re.compile(r"[^/\s]\.(?:" + "|".join(CODE_EXTENSIONS) + r")$", re.IGNORECASE)
_DIGEST_LINE = re.compile(r"\*\*Spec digest:\*\* (sha256:[0-9a-f]+)")

TEXT, FENCE_OPEN, FENCE_BODY, FENCE_CLOSE = "text", "open", "body", "close"


# -- Data ------------------------------------------------------------------


class InputError(Exception):
    """A broken input: reported on stderr, exit status 2, never a finding."""


@dataclass(frozen=True)
class Finding:
    rule: str
    severity: str
    section: str
    req: str | None
    line: int
    token: str
    message: str

    def as_dict(self) -> dict[str, object]:
        return {
            "rule": self.rule,
            "severity": self.severity,
            "section": self.section,
            "req": self.req,
            "line": self.line,
            "token": self.token,
            "message": self.message,
        }


@dataclass(frozen=True)
class Section:
    """The lines of one `##` section: (source line number, cleaned text)."""

    lines: tuple[tuple[int, str], ...]

    @property
    def body(self) -> str:
        return "\n".join(text for _, text in self.lines).strip("\n")

    @property
    def substantive(self) -> bool:
        return any(text.strip() for _, text in self.lines)


@dataclass(frozen=True)
class Spec:
    acceptance: Section
    behavior: Section
    key_signals: Section | None
    brief_present: bool


@dataclass(frozen=True)
class Outcome:
    exit_code: int
    summary: str
    extract: str | None
    digest: str | None
    removed_stale: bool
    findings: tuple[Finding, ...]


# -- Entry point -------------------------------------------------------------


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    configure_logging(args.verbose)
    try:
        root = _resolve_root(args.repo_root)
        outcome = run(args.slug, root, check=args.check)
    except InputError as error:
        print(f"extract_spec: {error}", file=sys.stderr)
        return EXIT_INPUT_ERROR
    _report(args.slug, outcome, as_json=args.json)
    return outcome.exit_code


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Write or verify SPEC_EXTRACT.md, the design-free view of a plan."
    )
    parser.add_argument("slug", type=_slug, help="task slug under .ai-work/")
    parser.add_argument(
        "--repo-root", metavar="DIR", help="repository root (default: git toplevel)"
    )
    parser.add_argument(
        "--check", action="store_true", help="verify the extract on disk; never write"
    )
    parser.add_argument("--json", action="store_true", help="machine-readable output on stdout")
    parser.add_argument("--verbose", action="store_true", help="debug logging on stderr")
    return parser


def _slug(value: str) -> str:
    if not _SLUG.match(value):
        raise argparse.ArgumentTypeError(
            f"{value!r} is not a task slug (letters, digits, '-' and '_'; no path separators)"
        )
    return value


def _resolve_root(cli_root: str | None) -> Path:
    if cli_root:
        root = Path(cli_root).resolve()
        if not root.is_dir():
            raise InputError(f"--repo-root is not a directory: {cli_root}")
        return root
    toplevel = git_toplevel_from_cwd()
    if toplevel is None:
        raise InputError(
            "cannot resolve the repository root: the working directory is not inside "
            "a git repository; pass --repo-root DIR"
        )
    return toplevel.resolve()


# -- Orchestration (the I/O edge) ----------------------------------------------


def run(slug: str, root: Path, *, check: bool) -> Outcome:
    task_dir = root / ".ai-work" / slug
    plan = _read_text(task_dir / PLAN_NAME, required=True)
    brief = _read_text(task_dir / BRIEF_NAME, required=False)
    spec = parse_spec(plan or "", brief)
    LOG.debug("parsed spec for %s (brief present: %s)", slug, spec.brief_present)

    findings = tuple(lint_spec(spec))
    target = task_dir / EXTRACT_NAME
    relative = f".ai-work/{slug}/{EXTRACT_NAME}"
    if any(finding.severity == BLOCKING for finding in findings):
        return _blocked(target, findings, check=check)
    text, digest = render_extract(slug, spec)
    if check:
        return _check(target, relative, text, digest, findings)
    target.write_bytes(text.encode("utf-8"))
    summary = f"extract written: {relative} (sha256:{digest})"
    return Outcome(EXIT_CLEAN, summary, relative, digest, False, findings)


def _blocked(target: Path, findings: tuple[Finding, ...], *, check: bool) -> Outcome:
    """Blocking findings: no extract may exist, so a previous one is deleted."""
    removed = target.is_file() and not check
    if removed:
        target.unlink()
    summary = "blocking findings: no extract written" + (
        " (removed the stale one)" if removed else ""
    )
    return Outcome(EXIT_FINDINGS, summary, None, None, removed, findings)


def _check(
    target: Path, relative: str, text: str, digest: str, findings: tuple[Finding, ...]
) -> Outcome:
    on_disk = target.read_bytes() if target.is_file() else None
    if on_disk == text.encode("utf-8"):
        summary = f"extract fresh: {relative} (sha256:{digest})"
        return Outcome(EXIT_CLEAN, summary, relative, digest, False, findings)
    stale = _stale_finding(relative, digest, on_disk)
    return Outcome(
        EXIT_FINDINGS, f"extract stale: {relative}", None, None, False, (*findings, stale)
    )


def _stale_finding(relative: str, expected: str, on_disk: bytes | None) -> Finding:
    if on_disk is None:
        message = "the extract is missing; run extract_spec.py to write it"
    else:
        found = _DIGEST_LINE.search(on_disk.decode("utf-8", errors="replace"))
        message = (
            f"the extract differs from the current spec (expected sha256:{expected}, "
            f"found {found.group(1) if found else 'no digest'}); run extract_spec.py to rewrite it"
        )
    return Finding(RULE_STALE, BLOCKING, "Spec Extract", None, 0, relative, message)


def _read_text(path: Path, *, required: bool) -> str | None:
    if not path.is_file():
        if required:
            raise InputError(f"{PLAN_NAME} not found: {path}")
        return None
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as error:
        raise InputError(f"cannot read {path}: {error}") from error


def _report(slug: str, outcome: Outcome, *, as_json: bool) -> None:
    if as_json:
        payload = {
            "schema": SCHEMA_VERSION,
            "slug": slug,
            "extract": outcome.extract,
            "digest": f"sha256:{outcome.digest}" if outcome.digest else None,
            "removed_stale": outcome.removed_stale,
            "findings": [finding.as_dict() for finding in outcome.findings],
        }
        print(json.dumps(payload, indent=2))
        return
    print(outcome.summary)
    for finding in outcome.findings:
        print(_finding_line(finding))


def _finding_line(finding: Finding) -> str:
    where = finding.section + (f" {finding.req}" if finding.req else "")
    return f"{finding.severity} {finding.rule} [{where}] line {finding.line}: {finding.token} -- {finding.message}"


# -- Pure core: parse -----------------------------------------------------------


def parse_spec(plan_text: str, brief_text: str | None) -> Spec:
    """The spec sections of a plan, plus the brief's key signals; InputError if broken."""
    plan_sections = _h2_sections(_clean_lines(plan_text))
    acceptance = _require(plan_sections, ACCEPTANCE_HEADING)
    behavior = _require(plan_sections, BEHAVIOR_HEADING)
    if not any(_REQ_HEADING.match(text) for _, text, kind in _walk(behavior.lines) if kind == TEXT):
        raise InputError(
            f"{PLAN_NAME} '## {BEHAVIOR_HEADING}' has no requirement block (a '### ' heading per requirement)"
        )

    key_signals = None
    if brief_text is not None:
        candidate = _h2_sections(_clean_lines(brief_text)).get(KEY_SIGNALS_HEADING)
        key_signals = candidate if candidate is not None and candidate.substantive else None
    return Spec(acceptance, behavior, key_signals, brief_present=brief_text is not None)


def _require(sections: dict[str, Section], heading: str) -> Section:
    section = sections.get(heading)
    if section is None:
        raise InputError(f"{PLAN_NAME} has no '## {heading}' section")
    if not section.substantive:
        raise InputError(f"{PLAN_NAME} '## {heading}' section is empty")
    return section


def _h2_sections(lines: list[tuple[int, str]]) -> dict[str, Section]:
    """`## ` sections outside fenced blocks; the first occurrence of a title wins."""
    found: dict[str, list[tuple[int, str]]] = {}
    current: list[tuple[int, str]] | None = None
    for number, text, kind in _walk(lines):
        heading = _H2.match(text) if kind == TEXT else None
        if heading:
            title = heading.group(1)
            current = found.setdefault(title, []) if title not in found else None
        elif current is not None:
            current.append((number, text))
    return {title: Section(tuple(body)) for title, body in found.items()}


def _walk(lines: Sequence[tuple[int, str]]) -> Iterator[tuple[int, str, str]]:
    """Yield (number, text, kind): where each line sits relative to fenced code blocks."""
    fence: tuple[str, int] | None = None
    for number, text in lines:
        match = _FENCE.match(text)
        if fence is None:
            if match and not (match.group(1)[0] == "`" and "`" in match.group(2)):
                fence = (match.group(1)[0], len(match.group(1)))
                yield number, text, FENCE_OPEN
            else:
                yield number, text, TEXT
        elif match and _closes(match, fence):
            fence = None
            yield number, text, FENCE_CLOSE
        else:
            yield number, text, FENCE_BODY


def _closes(match: re.Match[str], fence: tuple[str, int]) -> bool:
    marker = match.group(1)
    return marker[0] == fence[0] and len(marker) >= fence[1] and not match.group(2).strip()


def _clean_lines(text: str) -> list[tuple[int, str]]:
    """(source line number, text) with HTML comments removed.

    Comments vanish without shifting later line numbers; a line that held only
    a comment is dropped so it leaves no blank line in the extract.
    """
    original = text.replace("\r\n", "\n").split("\n")
    stripped = _COMMENT.sub(lambda m: "\n" * m.group().count("\n"), "\n".join(original))
    cleaned = stripped.split("\n")
    return [
        (number, cleaned[number - 1].rstrip())
        for number, before in enumerate(original, start=1)
        if not (before.strip() and not cleaned[number - 1].strip())
    ]


# -- Pure core: render -------------------------------------------------------------


def render_extract(slug: str, spec: Spec) -> tuple[str, str]:
    """The extract text and its digest; the digest covers the body below the header."""
    body = (
        f"## {KEY_SIGNALS_HEADING}\n\n{_key_signals_text(spec)}\n\n"
        f"## {ACCEPTANCE_HEADING}\n\n{spec.acceptance.body}\n\n"
        f"## {BEHAVIOR_HEADING}\n\n{spec.behavior.body}\n"
    )
    digest = hashlib.sha256(body.encode("utf-8")).hexdigest()[:DIGEST_HEX_CHARS]
    sources = f"{PLAN_NAME}; {BRIEF_NAME} § {KEY_SIGNALS_HEADING}"
    if not spec.brief_present:
        sources = f"{PLAN_NAME}; {BRIEF_NAME} absent"
    header = (
        f"# Spec Extract — {slug}\n\n"
        "<!-- Generated by extract_spec.py; do not edit. Regenerate after any spec change. -->\n"
        f"**Spec digest:** sha256:{digest}\n"
        f"**Sources:** {sources}\n\n"
    )
    return header + body, digest


def _key_signals_text(spec: Spec) -> str:
    if spec.key_signals is not None:
        return spec.key_signals.body
    return KEY_SIGNALS_MISSING if spec.brief_present else KEY_SIGNALS_ABSENT


# -- Pure core: lint ----------------------------------------------------------------


class Row(NamedTuple):
    """One spec line with the context the lint needs."""

    number: int
    text: str
    kind: str
    req: str | None
    in_surface: bool


def lint_spec(spec: Spec) -> list[Finding]:
    """Design-vocabulary findings: blocking in criteria and requirements, advisory in key signals."""
    declared = _declared_names(spec.behavior)
    findings = _lint_section(ACCEPTANCE_HEADING, spec.acceptance, BLOCKING, declared)
    findings += _lint_section(BEHAVIOR_HEADING, spec.behavior, BLOCKING, declared)
    if spec.key_signals is not None:
        findings += _lint_section(KEY_SIGNALS_HEADING, spec.key_signals, ADVISORY, declared)
    return findings


def _annotate(section: Section) -> Iterator[Row]:
    """Rows tagged with the requirement they sit in and whether they are Observable Surface."""
    req: str | None = None
    in_surface = False
    for number, text, kind in _walk(section.lines):
        heading = _H3.match(text) if kind == TEXT else None
        if heading:
            in_surface = heading.group(1) == SURFACE_HEADING
            found = _REQ_HEADING.match(text)
            req = found.group(1) if found else None
        yield Row(number, text, kind, req, in_surface)


def _declared_names(behavior: Section) -> frozenset[str]:
    """Backticked names on list items of `### Observable Surface`; the only way to whitelist."""
    names: set[str] = set()
    for row in _annotate(behavior):
        if row.in_surface and row.kind == TEXT and _LIST_ITEM.match(row.text):
            for match in _SPAN.finditer(row.text):
                name = match.group(2).strip()
                names.update((name, name.rstrip(_TRAILING_PUNCTUATION)))
    return frozenset(names)


def _lint_section(
    title: str, section: Section, severity: str, declared: frozenset[str]
) -> list[Finding]:
    found: list[Finding] = []
    for row in _annotate(section):
        if row.in_surface and title == BEHAVIOR_HEADING:
            continue
        if row.kind == FENCE_OPEN:
            message = "fenced block: describe the behavior in words, or declare the names it shows"
            token = row.text.strip()
            found.append(Finding(RULE_SPAN, severity, title, row.req, row.number, token, message))
        elif row.kind == TEXT:
            found.extend(_lint_text(row, title, severity, declared))
    return sorted(found, key=lambda finding: finding.line)


def _lint_text(row: Row, title: str, severity: str, declared: frozenset[str]) -> list[Finding]:
    def finding(rule: str, token: str, what: str) -> Finding:
        message = f"{what} '{token}' is not declared under Observable Surface: use plain words or declare it"
        return Finding(rule, severity, title, row.req, row.number, token, message)

    found = []
    for match in _SPAN.finditer(row.text):
        token = match.group(2).strip()
        if token not in declared:
            found.append(finding(RULE_SPAN, token, "code span"))
    rest = _SPAN.sub(" ", row.text)
    for match in _CALL.finditer(rest):
        if match.group() not in declared:
            found.append(finding(RULE_IDENTIFIER, match.group(), "call"))
    rest = _CALL.sub(" ", rest)
    for raw in _TOKEN_SEPARATORS.split(rest):
        token = raw.lstrip("*").rstrip(_TRAILING_PUNCTUATION)
        if not token or token in declared:
            continue
        classified = _classify(token)
        if classified is not None:
            rule, what = classified
            found.append(finding(rule, token, what))
    return found


def _classify(token: str) -> tuple[str, str] | None:
    """(rule, description) for a plain-text token that looks like design vocabulary."""
    if _is_path(token):
        return RULE_PATH, "path"
    kind = _identifier_kind(token)
    return (RULE_IDENTIFIER, kind) if kind else None


def _is_path(token: str) -> bool:
    if _PATH_PREFIX.match(token) or _FILE_EXTENSION.search(token):
        return True
    if "/" not in token or not token.strip("/"):
        return False
    marked = any(_SLASH_SEGMENT_MARK.search(segment) for segment in token.split("/"))
    return token.count("/") >= 2 or token.endswith("/") or marked


def _identifier_kind(token: str) -> str | None:
    if _SNAKE.search(token):
        return "snake_case or CONSTANT_CASE identifier"
    if _CAMEL.match(token):
        return "CamelCase identifier"
    if _DOTTED.match(token):
        return "dotted name"
    if _FLAG.match(token):
        return "CLI flag"
    return None


if __name__ == "__main__":
    sys.exit(main())
