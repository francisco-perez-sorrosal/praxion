"""YAML-subset and markdown-fence parsing for `TEST_TOPOLOGY.md`.

Split out of `resolve_test_scope.py` on cohesion: "turn topology text into
dicts" and "decide which tests to run" are two jobs with one narrow seam
(`parse_yaml_subset` / `iter_yaml_blocks` in, `TopologyError` out). The sibling
precedent is `check_state_ledgers.py` + `state_ledger_schema.py` -- the format
description lives beside the reader that consumes it, private and unexported.

PyYAML is deliberately not used. The resolver is invoked through a bare
`python3`, which is whatever the shell resolves and routinely holds none of the
project's declared dependencies; a third-party import in this module would
propagate to the resolver (the ambient-import check follows sibling imports
transitively) and kill it on load at exactly the call sites that cannot report
why. Hand-parsing is acceptable only because the schema is closed and documented
(`skills/testing-strategy/references/test-topology.md` §"Test Group Schema").

The parser's governing rule follows from that: **it is a closed subset, and
anything outside it raises with a file and a line.** Never skip. A silently
dropped group is a group whose `file_dependencies` never match, whose tests
therefore never run, and whose absence leaves no trace anywhere -- the exact
under-selection the resolver exists to prevent.

Sibling-imported (not executed), so it resolves through the `install_claude.sh`
symlink without needing a link of its own, and is non-executable so the
installer's `-f && -x` filter leaves it off `PATH`.
"""

from __future__ import annotations

import re


class TopologyError(Exception):
    """A topology construct the parser will not silently accept."""

    def __init__(self, source: str, lineno: int, message: str) -> None:
        super().__init__(f"{source}:{lineno}: {message}")
        self.source = source
        self.lineno = lineno


# --- YAML subset parser ------------------------------------------------------
#
# PyYAML is unavailable under the ambient interpreter (see the module docstring),
# so the closed, documented subset the topology schema uses is hand-parsed. The
# whole point is that it is *closed*: anything outside it raises with a file and
# a line rather than being skipped, because a silently dropped group makes the
# resolver under-select and the omission leaves no trace.

_KEY = re.compile(r"^([A-Za-z_][A-Za-z0-9_-]*):(?:[ \t]+(.*))?$")
_PLACEHOLDER = re.compile(r"^<.*>$")
_YAML_INDICATORS = ("&", "*", "!", "|", ">", "%", "`", "@", "{", "}")
_UNSUPPORTED_LINES = ("---", "...", "<<:")


def _indent_of(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


def _is_blank(line: str) -> bool:
    stripped = line.strip()
    return not stripped or stripped.startswith("#")


def _next_content(lines: list[str], index: int) -> int | None:
    while index < len(lines):
        if not _is_blank(lines[index]):
            return index
        index += 1
    return None


def _strip_comment(text: str) -> str:
    """Drop a trailing `# ...` comment, respecting a quoted scalar."""
    if text[:1] in ("'", '"'):
        quote = text[0]
        end = text.find(quote, 1)
        if end != -1:
            return text[: end + 1]
    cut = text.find(" #")
    return text[:cut] if cut != -1 else text


def _scalar(text: str, source: str, lineno: int) -> object:
    """One plain, quoted, or typed scalar. Rejects every YAML feature beyond that."""
    text = _strip_comment(text).strip()
    if not text:
        return None
    if text[0] in ("'", '"'):
        if len(text) < 2 or text[-1] != text[0]:
            raise TopologyError(source, lineno, f"unterminated quoted scalar: {text!r}")
        return text[1:-1]
    if _PLACEHOLDER.match(text):
        raise TopologyError(
            source, lineno, f"schema placeholder {text!r} is not a value -- fill it in"
        )
    if text[0] in _YAML_INDICATORS:
        raise TopologyError(
            source, lineno, f"unsupported YAML construct {text!r} (anchor, alias, tag, or block)"
        )
    lowered = text.lower()
    if lowered in ("true", "false"):
        return lowered == "true"
    if lowered in ("null", "~"):
        return None
    try:
        return int(text)
    except ValueError:
        pass
    try:
        return float(text)
    except ValueError:
        return text


def _flow_sequence(text: str, source: str, lineno: int) -> list[object]:
    """`[a, "b", c]` -- one level only; a nested flow collection raises."""
    body = text[1:-1].strip()
    if not body:
        raise TopologyError(source, lineno, "empty flow sequence is not a valid selector argument")
    items: list[object] = []
    for chunk in _split_flow(body, source, lineno):
        chunk = chunk.strip()
        if not chunk:
            raise TopologyError(source, lineno, f"empty entry in flow sequence {text!r}")
        if chunk[0] in ("[", "{"):
            raise TopologyError(source, lineno, "nested flow collections are not supported")
        items.append(_scalar(chunk, source, lineno))
    return items


def _split_flow(body: str, source: str, lineno: int) -> list[str]:
    """Split on top-level commas, honouring quotes."""
    parts: list[str] = []
    current: list[str] = []
    quote: str | None = None
    for char in body:
        if quote:
            current.append(char)
            if char == quote:
                quote = None
            continue
        if char in ("'", '"'):
            quote = char
            current.append(char)
        elif char == ",":
            parts.append("".join(current))
            current = []
        else:
            current.append(char)
    if quote:
        raise TopologyError(source, lineno, f"unterminated quote in flow sequence: {body!r}")
    parts.append("".join(current))
    return parts


def _value(text: str, source: str, lineno: int) -> object:
    text = _strip_comment(text).strip()
    if text.startswith("[") and text.endswith("]"):
        return _flow_sequence(text, source, lineno)
    if text.startswith("{"):
        raise TopologyError(source, lineno, "flow mappings are not supported")
    return _scalar(text, source, lineno)


def _guard_line(stripped: str, source: str, lineno: int) -> None:
    for token in _UNSUPPORTED_LINES:
        if stripped.startswith(token):
            raise TopologyError(source, lineno, f"unsupported YAML construct {token!r}")


def _parse_mapping(
    lines: list[str], index: int, indent: int, source: str, offset: int
) -> tuple[dict[str, object], int]:
    result: dict[str, object] = {}
    while index < len(lines):
        raw = lines[index]
        if _is_blank(raw):
            index += 1
            continue
        current = _indent_of(raw)
        if current < indent:
            break
        stripped = raw.strip()
        lineno = offset + index
        if current > indent:
            raise TopologyError(source, lineno, f"unexpected indentation in mapping: {stripped!r}")
        if stripped.startswith("- "):
            break
        _guard_line(stripped, source, lineno)
        match = _KEY.match(stripped)
        if not match:
            raise TopologyError(source, lineno, f"unrecognized line: {stripped!r}")
        key, inline = match.group(1), match.group(2)
        if key in result:
            raise TopologyError(source, lineno, f"duplicate key {key!r}")
        if inline is not None and _strip_comment(inline).strip():
            result[key] = _value(inline, source, lineno)
            index += 1
        else:
            result[key], index = _parse_child(lines, index, indent, source, offset)
    return result, index


def _parse_child(
    lines: list[str], index: int, indent: int, source: str, offset: int
) -> tuple[object, int]:
    """The block value of a `key:` with nothing after the colon."""
    follower = _next_content(lines, index + 1)
    if follower is None:
        return None, index + 1
    child_indent = _indent_of(lines[follower])
    is_item = lines[follower].strip().startswith("- ")
    if is_item and child_indent >= indent:
        return _parse_sequence(lines, follower, child_indent, source, offset)
    if not is_item and child_indent > indent:
        return _parse_mapping(lines, follower, child_indent, source, offset)
    return None, index + 1


def _parse_sequence(
    lines: list[str], index: int, indent: int, source: str, offset: int
) -> tuple[list[object], int]:
    items: list[object] = []
    while index < len(lines):
        raw = lines[index]
        if _is_blank(raw):
            index += 1
            continue
        current = _indent_of(raw)
        if current < indent or not raw.strip().startswith("-"):
            break
        lineno = offset + index
        if current > indent:
            raise TopologyError(
                source, lineno, f"unexpected indentation in sequence: {raw.strip()!r}"
            )
        rest = raw.strip()[1:]
        if not rest.strip():
            raise TopologyError(source, lineno, "empty sequence item")
        if not rest.startswith((" ", "\t")):
            raise TopologyError(source, lineno, f"unrecognized sequence item: {raw.strip()!r}")
        item_indent = current + 1 + (len(rest) - len(rest.lstrip()))
        rest = rest.strip()
        if _KEY.match(rest):
            # Re-indent the item's first key so the mapping parser sees a normal
            # block starting on this same line; line numbering is preserved.
            lines[index] = " " * item_indent + rest
            item, index = _parse_mapping(lines, index, item_indent, source, offset)
            items.append(item)
        else:
            items.append(_value(rest, source, lineno))
            index += 1
    return items, index


def parse_yaml_subset(text: str, source: str, offset: int = 1) -> dict[str, object]:
    """Parse the closed YAML subset the topology schema uses.

    `offset` is the 1-based file line number of `text`'s first line, so errors
    point at the real location inside the enclosing markdown file.
    """
    lines = text.splitlines()
    first = _next_content(lines, 0)
    if first is None:
        raise TopologyError(source, offset, "empty yaml block")
    mapping, index = _parse_mapping(lines, first, _indent_of(lines[first]), source, offset)
    trailing = _next_content(lines, index)
    if trailing is not None:
        raise TopologyError(source, offset + trailing, f"trailing content: {lines[trailing]!r}")
    return mapping


_FENCE_OPEN = re.compile(r"^\s*```+\s*ya?ml\s*$", re.IGNORECASE)
_FENCE_CLOSE = re.compile(r"^\s*```+\s*$")


def iter_yaml_blocks(text: str, source: str) -> list[tuple[str, int]]:
    """Every ```yaml fence in the markdown, as (body, 1-based first-line-number)."""
    blocks: list[tuple[str, int]] = []
    lines = text.splitlines()
    index = 0
    while index < len(lines):
        if not _FENCE_OPEN.match(lines[index]):
            index += 1
            continue
        start = index + 1
        end = start
        while end < len(lines) and not _FENCE_CLOSE.match(lines[end]):
            end += 1
        if end >= len(lines):
            raise TopologyError(source, index + 1, "unterminated ```yaml fence")
        blocks.append(("\n".join(lines[start:end]), start + 1))
        index = end + 1
    return blocks
