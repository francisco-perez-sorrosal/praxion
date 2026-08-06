"""Fragment-filename identity parsing for the ADR finalize protocol.

Owns one responsibility: turning a draft ADR's filename --
`<YYYYMMDD-HHMM>-<user>-<branch>-<slug>.md` -- back into the four fields the
authoring agent encoded into it. All three text fields share one separator, so
the split is genuinely ambiguous and the parser resolves it through a cascade
of decreasing-confidence tiers (frontmatter, identity hints, sibling-prefix
discovery, first-token heuristic).

The parser knows nothing about git or repo roots: identity hints arrive as
caller-supplied callables, so `finalize_adrs.py` -- the only module that knows
which checkout is being finalized -- stays the single owner of that state.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

logger = logging.getLogger("finalize_adrs")

FRAGMENT_ADR_PATTERN = re.compile(r"^(?P<ts>\d{8}-\d{4})-(?P<rest>[a-z0-9-]+)\.md$")
# Optional `branch:` field in fragment frontmatter — when present, the value
# is the authoritative branch name written by the creating agent, immune to
# the single-fragment hyphenated-branch ambiguity the filename heuristic
# stumbles on (td-017). The value matches the same `[a-z0-9-]+` sanitize
# alphabet used to build the filename's branch slug.
FRONTMATTER_BRANCH_PATTERN = re.compile(r"""^branch:\s*["']?([a-z0-9-]+)["']?\s*$""", re.MULTILINE)
TIMESTAMP_FORMAT = "%Y%m%d-%H%M"


def parse_fragment_filename(
    path: Path,
    *,
    user_slug_hint: Callable[[], str | None],
    branch_slug_hint: Callable[[], str | None],
) -> tuple[datetime, str, str, str]:
    """Extract (timestamp, user, branch, slug) from a fragment ADR filename.

    Filename shape: `<YYYYMMDD-HHMM>-<user>-<branch>-<slug>.md` where user,
    branch, and slug are each sanitized to `[a-z0-9-]`. Because all three can
    contain hyphens, pure-filename parsing is ambiguous. The parser resolves
    the user/branch/slug boundaries in order of decreasing confidence:

    1. **Frontmatter `branch:` token-run strip (td-052 fix, extends
       td-017)**: when the fragment carries an explicit `branch:` value,
       search `rest`'s dash-delimited tokens for a contiguous run matching
       the branch's own tokens (requiring at least one token before it for
       the user, and at least one after for the slug) and strip it --
       *independent* of whether the current git user matches the filename's
       user segment. This is what makes the frontmatter branch authoritative
       even when the filename's user slug is itself hyphenated (e.g. a
       legal-name-derived slug like `francisco-perez-sorrosal` recorded at
       fragment-creation time, diverging from the git-config-derived
       `user_hint` computed at finalize time). The original td-017 fix only
       consulted the frontmatter branch *after* an exact user-hint prefix
       match, so a hyphenated-user mismatch skipped it entirely and fell
       through to the ambiguous heuristic below. Falls through to the tiers
       below when the branch value doesn't appear as a clean token run
       (e.g. stale frontmatter after a since-renamed branch) or the field
       is absent.
    2. Exact match against `git config user.*` + `git rev-parse HEAD`. The
       happy path when `finalize` runs on the branch that created the draft.
    3. Sibling-prefix discovery: scan fragments sharing `path.parent` for a
       common `<user>-<branch>-` prefix. Pipeline-authored drafts arrive in
       batches sharing user+branch, so the longest common dash-aligned
       prefix is the branch. Handles the post-merge case where git hints
       are stale (branch is `main`, not the authoring branch).
    4. Heuristic fallback: user = first token, branch = second token, slug
       = remainder. Ambiguous when user or branch themselves contain
       hyphens; logs a warning so the caller knows the parse is best-effort.

    `user_slug_hint` and `branch_slug_hint` are zero-argument callables rather
    than values so the branch hint is never fetched when the fragment's own
    frontmatter already answered -- the common post-merge case, where asking
    git would cost a subprocess to produce a discarded answer.

    Raises ValueError if the filename does not match the fragment pattern.
    """
    match = FRAGMENT_ADR_PATTERN.match(path.name)
    if not match:
        raise ValueError(f"malformed fragment filename: {path.name}")

    timestamp = datetime.strptime(match.group("ts"), TIMESTAMP_FORMAT)
    rest = match.group("rest")
    tokens = rest.split("-")
    if len(tokens) < 3:
        raise ValueError(f"fragment filename too short (need user-branch-slug): {path.name}")

    # Tier 1: authoritative branch from frontmatter, if present. Takes
    # precedence over the current-git-branch hint -- and over user-hint
    # matching (td-052) -- because it is the value the creating agent
    # recorded at fragment-write time, immune to drift when finalize runs
    # post-merge on `main` or under a different git identity.
    branch_from_frontmatter = read_draft_branch(path)

    user_hint = user_slug_hint()
    branch_hint = branch_from_frontmatter or branch_slug_hint()

    user, branch, slug = _split_user_branch_slug(
        rest,
        user_hint,
        branch_hint,
        siblings_dir=path.parent,
        self_name=path.name,
        branch_from_frontmatter=branch_from_frontmatter,
    )
    return timestamp, user, branch, slug


def read_draft_branch(path: Path) -> str | None:
    """Return the optional `branch:` value from a fragment's frontmatter.

    Returns None if the field is absent (older fragments predating td-017),
    if the file is unreadable, or if the value does not match the sanitize
    alphabet. The fall-through to filename-heuristic parsing preserves the
    pre-td-017 behavior for those cases.
    """
    try:
        content = path.read_text(encoding="utf-8")
    except OSError:
        return None
    match = FRONTMATTER_BRANCH_PATTERN.search(content)
    if match is None:
        return None
    return match.group(1)


def _split_user_branch_slug(
    rest: str,
    user_hint: str | None,
    branch_hint: str | None,
    siblings_dir: Path | None = None,
    self_name: str | None = None,
    branch_from_frontmatter: str | None = None,
) -> tuple[str, str, str]:
    """Split `<user>-<branch>-<slug>` using hints and sibling discovery.

    Priority order:
        0. Frontmatter `branch:` token-run strip (td-052) -- when present,
           strip its dash-token run from `rest` first, independent of
           user-hint matching. Immune to hyphenated user slugs that defeat
           the prefix-match tiers below.
        1. Both git hints match a prefix of `rest` -- consume exactly.
        2. Sibling-prefix discovery -- scan other fragments in
           `siblings_dir` for a common `<user>-<branch>-` prefix.
        3. Heuristic fallback -- user=first, branch=second, slug=rest
           (imperfect for multi-hyphen branches but deterministic).
    """
    if branch_from_frontmatter:
        stripped = _strip_branch_token_run(rest, branch_from_frontmatter)
        if stripped is not None:
            user, slug = stripped
            return user, branch_from_frontmatter, slug

    if user_hint and rest.startswith(user_hint + "-"):
        after_user = rest[len(user_hint) + 1 :]
        if branch_hint and after_user.startswith(branch_hint + "-"):
            slug = after_user[len(branch_hint) + 1 :]
            return user_hint, branch_hint, slug

        # User hint matched but branch hint did not. Try sibling-prefix
        # discovery before falling back to the first-token heuristic.
        discovered = _discover_branch_from_siblings(rest, user_hint, siblings_dir, self_name)
        if discovered is not None:
            branch, slug = discovered
            return user_hint, branch, slug

        # Last-resort heuristic: branch = first token after user, slug = rest.
        tokens = after_user.split("-", 1)
        if len(tokens) < 2:
            raise ValueError(f"cannot extract slug from fragment tail: {rest}")
        logger.warning(
            "finalize_adrs: parse_fragment_filename: no sibling drafts to "
            "disambiguate branch from slug in %r; assuming branch=%r. Pass "
            "--branch explicitly or populate drafts/ to resolve.",
            rest,
            tokens[0],
        )
        return user_hint, tokens[0], tokens[1]

    # Sibling-prefix discovery without git user hint -- useful when finalize
    # runs outside a git config context (e.g., CI without user.email set).
    sibling_parse = _parse_via_siblings(rest, siblings_dir, self_name)
    if sibling_parse is not None:
        return sibling_parse

    # Heuristic fallback: user=first, branch=second, slug=rest.
    tokens = rest.split("-", 2)
    if len(tokens) < 3:
        raise ValueError(f"fragment tail too short to split: {rest}")
    return tokens[0], tokens[1], tokens[2]


def _strip_branch_token_run(rest: str, branch: str) -> tuple[str, str] | None:
    """Strip the branch's dash-tokens from `rest` as a contiguous run.

    Splits both `rest` and `branch` into dash-delimited tokens and searches
    (left to right) for the first position where `branch`'s tokens appear as
    a contiguous run in `rest`'s tokens, requiring at least one token before
    the run (the user) and at least one after (the slug). Returns
    (user, slug), each rejoined with dashes, on a match; None when the
    branch value does not appear as a clean token run -- e.g. stale
    frontmatter left over after the authoring branch was renamed -- so the
    caller falls through to the heuristics below.
    """
    tokens = rest.split("-")
    branch_tokens = branch.split("-")
    run_len = len(branch_tokens)
    last_start = len(tokens) - run_len - 1
    for start in range(1, last_start + 1):
        if tokens[start : start + run_len] == branch_tokens:
            return "-".join(tokens[:start]), "-".join(tokens[start + run_len :])
    return None


def _discover_branch_from_siblings(
    rest: str,
    user_hint: str,
    siblings_dir: Path | None,
    self_name: str | None,
) -> tuple[str, str] | None:
    """Discover branch+slug via dash-aligned LCP across sibling fragments.

    Given user_hint matches `rest`, examine other fragments in `siblings_dir`
    whose names also begin with the same user prefix. The longest common
    dash-aligned prefix *after* `<user>-` across the batch is the branch.

    Returns (branch, slug) when a common prefix is discovered; None
    otherwise (no siblings, no agreement, or degenerate common prefix).
    """
    if siblings_dir is None or not siblings_dir.is_dir():
        return None

    peer_tails = _collect_peer_tails(siblings_dir, user_hint, self_name)
    if not peer_tails:
        return None

    after_user = rest[len(user_hint) + 1 :]
    common_branch = _dash_aligned_common_prefix([after_user, *peer_tails])
    if not common_branch:
        return None

    slug = after_user[len(common_branch) + 1 :]
    if not slug:
        return None
    return common_branch, slug


def _parse_via_siblings(
    rest: str, siblings_dir: Path | None, self_name: str | None
) -> tuple[str, str, str] | None:
    """Parse user+branch+slug by LCP across siblings when no user_hint is set.

    Pipeline drafts share a `<user>-<branch>-` prefix across the batch. When
    we cannot rely on git config, the LCP itself carries that prefix. We
    split the discovered prefix at the first dash boundary to recover user
    and branch: the first dash-segment is the user, the remainder is the
    branch.
    """
    if siblings_dir is None or not siblings_dir.is_dir():
        return None

    peer_rests = _collect_peer_rests(siblings_dir, self_name)
    if not peer_rests:
        return None

    common = _dash_aligned_common_prefix([rest, *peer_rests])
    if not common:
        return None
    parts = common.split("-", 1)
    if len(parts) < 2:
        return None
    user, branch = parts[0], parts[1]
    slug = rest[len(common) + 1 :]
    if not user or not branch or not slug:
        return None
    return user, branch, slug


def _collect_peer_tails(siblings_dir: Path, user_hint: str, self_name: str | None) -> list[str]:
    """Return the `<branch>-<slug>` tails of peer fragments sharing user_hint."""
    tails: list[str] = []
    prefix = user_hint + "-"
    for entry in siblings_dir.iterdir():
        if not entry.is_file():
            continue
        if self_name is not None and entry.name == self_name:
            continue
        match = FRAGMENT_ADR_PATTERN.match(entry.name)
        if match is None:
            continue
        peer_rest = match.group("rest")
        if not peer_rest.startswith(prefix):
            continue
        tails.append(peer_rest[len(prefix) :])
    return tails


def _collect_peer_rests(siblings_dir: Path, self_name: str | None) -> list[str]:
    """Return the `<user>-<branch>-<slug>` rests of peer fragments."""
    rests: list[str] = []
    for entry in siblings_dir.iterdir():
        if not entry.is_file():
            continue
        if self_name is not None and entry.name == self_name:
            continue
        match = FRAGMENT_ADR_PATTERN.match(entry.name)
        if match is None:
            continue
        rests.append(match.group("rest"))
    return rests


def _dash_aligned_common_prefix(strings: list[str]) -> str:
    """Return the longest dash-aligned common prefix across `strings`.

    Dash-aligned means the prefix must end just before a `-` in every
    input -- we never split a token mid-word. Returns an empty string
    when the inputs share no dash-aligned prefix.
    """
    if not strings:
        return ""
    shortest = min(strings, key=len)
    last_dash = -1
    for i, ch in enumerate(shortest):
        if any(i >= len(s) or s[i] != ch for s in strings):
            break
        if ch == "-":
            last_dash = i
    if last_dash < 0:
        return ""
    return shortest[:last_dash]
