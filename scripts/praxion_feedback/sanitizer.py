"""Mechanical capture-time sanitizer + shipped-artifact scope filter.

Both functions are pure (no I/O, no judgment) and run inside the `capture`
subcommand *before* a candidate ever reaches the git-committed `PENDING.md`
(SYSTEMS_PLAN's "sanitize-at-capture" divergence from `/report-upstream`).

`sanitize_text` is the leak-prevention contract: no absolute path, username, or
secret-shaped string may survive into committed state. It is deliberately the
mechanical first layer -- the `/report-praxion-issue` command applies a second,
judgment-based pass on top. The secret-pattern catalog mirrors
`skills/context-security-review/references/secret-patterns.md` (widened to
`{20,}` bodies so shorter real-world tokens still match).

`is_shipped_artifact_path` is the scope filter: only a path shaped like the
declared shipped Praxion artifact family is admitted, so project-local bugs
never enter the sidecar.
"""

from __future__ import annotations

import re

_REDACTION = "[REDACTED]"
_PATH_PLACEHOLDER = "<path>"
_USER_PLACEHOLDER = "<user>"

# A captured home-directory path reveals a username as its first segment; that
# same token is then redacted everywhere else in the text (a sanitizer that
# blanks only the path segment but leaks the bare username is incomplete).
_HOME_USERNAME_RE = re.compile(r"/(?:Users|home)/([^/\s]+)")
_MIN_REDACTABLE_USERNAME_LEN = 3

# Absolute-path run at a word boundary with >=2 segments. The lookbehind keeps
# it from matching inside a URL ("https://host/a/b") or a repo-relative token.
_ABSOLUTE_PATH_RE = re.compile(r"(?<![\w:~/])/[\w.\-]+(?:/[\w.\-]+)+")

# Secret-shaped strings. Assignment forms redact the whole "key=value" pair;
# prefix forms redact the whole token. Order is specific-before-general.
_SECRET_PATTERNS = (
    re.compile(r"(?i)(?:api[_-]?key|apikey)\s*[:=]\s*\S+"),
    re.compile(r"(?i)(?:secret|token|password|passwd|pwd)\s*[:=]\s*\S+"),
    re.compile(r"(?i)bearer\s+\S+"),
    re.compile(r"eyJ[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+(?:\.[A-Za-z0-9_\-]+)?"),
    re.compile(r"sk-(?:ant-)?[A-Za-z0-9]{20,}"),
    re.compile(r"sk_(?:live|test)_[A-Za-z0-9]{16,}"),
    re.compile(r"gh[pousr]_[A-Za-z0-9]{20,}"),
    re.compile(r"github_pat_[A-Za-z0-9_]{20,}"),
    re.compile(r"xox[bpaos]-[A-Za-z0-9\-]+"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
)

# category -> the repo-relative path prefix its shipped artifacts live under.
_SHIPPED_FAMILY_PREFIXES = {
    "hooks": "hooks/",
    "blocks": "claude/canonical-blocks/",
    "agents": "agents/",
    "scripts": "scripts/",
    "skills": "skills/",
}


def _extract_usernames(text: str) -> set[str]:
    """Collect usernames revealed by home-directory paths in the text.

    A minimum length guards against redacting a short, common token (e.g. a
    one-off single-letter home) as if it were a username everywhere it appears.
    """
    usernames: set[str] = set()
    for match in _HOME_USERNAME_RE.finditer(text):
        username = match.group(1)
        if len(username) >= _MIN_REDACTABLE_USERNAME_LEN:
            usernames.add(username)
    return usernames


def _redact_secrets(text: str) -> str:
    for pattern in _SECRET_PATTERNS:
        text = pattern.sub(_REDACTION, text)
    return text


def sanitize_text(text: str) -> str:
    """Return `text` with absolute paths, usernames, and secrets removed.

    Benign content is preserved verbatim: a string carrying none of the above
    passes through unchanged (the negative-space contract).
    """
    usernames = _extract_usernames(text)
    text = _redact_secrets(text)
    text = _ABSOLUTE_PATH_RE.sub(_PATH_PLACEHOLDER, text)
    for username in usernames:
        text = re.sub(rf"\b{re.escape(username)}\b", _USER_PLACEHOLDER, text)
    return text


def is_shipped_artifact_path(artifact_path: str, category: str) -> bool:
    """True only if `artifact_path` matches the shape of `category`'s family.

    A path must match the declared category's own prefix -- a hooks-shaped path
    declared under "scripts" is still a scope-filter rejection, and a
    project-local path (e.g. "src/app.py") is rejected outright.
    """
    prefix = _SHIPPED_FAMILY_PREFIXES.get(category)
    if prefix is None:
        return False
    return artifact_path.startswith(prefix)
