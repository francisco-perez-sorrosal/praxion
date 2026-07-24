"""The fingerprint / dedup contract.

`compute_fingerprint` is `sha256(category + normalized_artifact_path +
normalized_error)`. `normalize_error` is the load-bearing half: it strips
run-specific noise so the *same* logical defect, captured on different machines
or runs, hashes identically -- while genuinely different defects stay distinct.

Design bias (SYSTEMS_PLAN Risk Assessment): prefer *under*-normalization. Each
stripped token targets a specific, provably-volatile noise category (line
numbers, hex addresses, timestamps, PIDs, temp-dir / UUID tokens, absolute-path
prefixes) rather than a blanket digit/word wipe -- the latter would collapse
distinct defects that differ only by a number.
"""

from __future__ import annotations

import hashlib
import re

# Field separator for the fingerprint pre-image. A NUL byte cannot occur in any
# of the three text fields, so it prevents boundary collisions (e.g. category
# "a" + path "bc" hashing the same as category "ab" + path "c").
_FIELD_SEPARATOR = "\0"

# Repo-root directory segments used to canonicalize an absolute path in error
# text down to its repo-relative shape, so /Users/<user>/dev/praxion/scripts/x.py
# and /home/ci/work/praxion/scripts/x.py both normalize to scripts/x.py.
_KNOWN_ROOT_SEGMENTS = frozenset(
    {
        "hooks",
        "scripts",
        "agents",
        "skills",
        "blocks",
        "commands",
        "rules",
        "claude",
        "tests",
        "docs",
        ".github",
        ".ai-state",
        ".ai-work",
    }
)

# An absolute-path run: a leading "/" at a word boundary followed by >=2
# path segments. The lookbehind keeps it from matching a "/" mid-token (a
# repo-relative "scripts/foo.py" has no leading slash) or inside a URL scheme.
_ABSOLUTE_PATH_RE = re.compile(r"(?<![\w:~/])/[\w.\-]+(?:/[\w.\-]+)+")

_UUID_RE = re.compile(
    r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
)
_HEX_ADDRESS_RE = re.compile(r"0x[0-9a-fA-F]+")
_ISO_TIMESTAMP_RE = re.compile(
    r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})?"
)
# tempfile.mkdtemp / mkstemp names are "tmp" + >=6 random chars.
_TEMP_NAME_RE = re.compile(r"\btmp[A-Za-z0-9]{6,}\b")
_PID_RE = re.compile(r"(?i)\bpid\s+\d+")
_LINE_NUMBER_RE = re.compile(r"(?i)\bline\s+\d+")
_WHITESPACE_RUN_RE = re.compile(r"\s+")

_ADDRESS_PLACEHOLDER = "0x<addr>"
_TIMESTAMP_PLACEHOLDER = "<ts>"
_UUID_PLACEHOLDER = "<uuid>"
_TEMP_NAME_PLACEHOLDER = "<tmpname>"
_PID_PLACEHOLDER = "pid <n>"
_LINE_PLACEHOLDER = "line <n>"


def _canonicalize_absolute_path(match: re.Match[str]) -> str:
    """Truncate an absolute path down to its first known repo-root segment.

    Returns the original token unchanged when no known root is present (e.g. a
    ``/tmp/...`` scratch path, which the temp-name / UUID rules handle instead).
    """
    token = match.group(0)
    segments = token.split("/")
    for index, segment in enumerate(segments):
        if segment in _KNOWN_ROOT_SEGMENTS:
            return "/".join(segments[index:])
    return token


def normalize_error(error: str) -> str:
    """Collapse run-specific noise so the same recurring defect matches itself.

    The order is intentional: absolute paths are canonicalized first (on the raw
    text), then per-token volatile noise is stripped, then whitespace is
    collapsed last so structurally identical captures with different indentation
    or line breaks converge.
    """
    text = _ABSOLUTE_PATH_RE.sub(_canonicalize_absolute_path, error)
    text = _HEX_ADDRESS_RE.sub(_ADDRESS_PLACEHOLDER, text)
    text = _ISO_TIMESTAMP_RE.sub(_TIMESTAMP_PLACEHOLDER, text)
    text = _UUID_RE.sub(_UUID_PLACEHOLDER, text)
    text = _TEMP_NAME_RE.sub(_TEMP_NAME_PLACEHOLDER, text)
    text = _PID_RE.sub(_PID_PLACEHOLDER, text)
    text = _LINE_NUMBER_RE.sub(_LINE_PLACEHOLDER, text)
    return _WHITESPACE_RUN_RE.sub(" ", text).strip()


def normalize_artifact_path(artifact_path: str) -> str:
    """Canonicalize an artifact path to its repo-relative shape and trim it."""
    text = _ABSOLUTE_PATH_RE.sub(_canonicalize_absolute_path, artifact_path)
    return text.strip()


def compute_fingerprint(category: str, artifact_path: str, error: str) -> str:
    """Return the 64-char hex sha256 of the normalized (category, path, error).

    Same logical defect -> identical digest; a change in any of the three
    normalized components -> a different digest. This is the managed-side dedup
    key against both PENDING.md and UPSTREAM_ISSUES.md.
    """
    pre_image = _FIELD_SEPARATOR.join(
        (category, normalize_artifact_path(artifact_path), normalize_error(error))
    )
    return hashlib.sha256(pre_image.encode("utf-8")).hexdigest()
