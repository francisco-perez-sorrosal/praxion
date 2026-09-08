#!/usr/bin/env python3
"""Always-loaded token budget — measured, with the file set as code.

Three mutually inconsistent bases have coexisted in this repository, and every
historical PASS was basis-dependent. Two causes, both addressed here:

1. **The file set was prose.** "CLAUDE.md files plus every `rules/**/*.md`
   lacking `paths:`, excluding catalog READMEs" is a rule a reader can apply
   three ways -- and did. `always_loaded_files()` is that sentence as code, so
   the set stops being a judgment call.

2. **The size was a folk divisor.** Sites variously said chars/3.5, chars/3.6
   and "~3.6-4.0", which at the 2026-08-05 corpus straddled the ceiling: /3.5
   reported a breach and /3.6 reported headroom over the identical bytes. A
   divisor cannot settle that, because none of them was ever measured.

So this counts tokens with the real tokenizer when it can. Measured
2026-08-05: 88,599 bytes -> **23,341 tokens**, a true ratio of **3.796
chars/token**. Against that, /3.5 overestimates by 8.5%, /3.6 by 5.4%, and
/4.0 underestimates by 5.1%.

Without an API key it falls back to `_FALLBACK_DIVISOR`, which is retained at
3.6 -- not by inheritance, but because the measurement showed it errs ~5% high,
and a budget guardrail should overestimate. The fallback is always labelled an
estimate; only a tokenizer run is reported as measured.

Every reading and every persisted baseline sample carries its `basis`
(`"tokenizer"` or `"estimate"`) precisely because the two are not
interchangeable -- the ~20% swing between them (see `measure_listing()`'s
docstring) is large enough to read as real corpus growth on its own. That
swing is why `ratchet()`'s trailing-window trend compares **bytes**, not
tokens: the governed file set serializes to the same byte count regardless
of whether `ANTHROPIC_API_KEY` happened to be set on the day a sample was
taken, so the trend line needs no basis at all. Tokens (and `basis`) remain
only for the two absolute-ceiling checks -- the budget check in `measure()`
and the frozen listing ceiling in `ratchet()` -- where a labelled estimate
is still an honest answer to "how many tokens right now," and the listing
ceiling alone keeps its basis-mismatch guard (a mismatch there still fails
open with an INFO note rather than diffing two different rulers).

Stdlib-only, deliberately: the sentinel invokes this through the ambient
interpreter, so a third-party import would make it a finding of the
`ambient-import` gate-liveness check.

Exit 0 under budget, 1 over -- so it doubles as a gate. A missing API key is
not a failure; it downgrades the reading to an estimate and says so.

Cites: rules/CLAUDE.md#token-budget (the ceiling and the attention-share rule).
"""

from __future__ import annotations

import argparse
import functools
import json
import os
import re
import sys
import urllib.error
import urllib.request
from datetime import date, timedelta
from pathlib import Path

from _repo_root import resolve_repo_root

SCRIPT_DIR = Path(__file__).resolve().parent

BUDGET_TOKENS = 25_000

# The P1.12 directional target for the listing surface: ~1% of a 200k-token
# context window. Distinct from `ratchet()`'s baseline-pinned `listing_ceiling`
# (a no-regression-from-today floor, frozen at whatever the listing measured
# on the day that field was last written) -- this is an absolute target,
# checked ad hoc via `--listing-ceiling` and report-only by default
# (`--enforce-listing-ceiling` opts in) so the P1.12 description-diet sweep
# does not block every intermediate commit before it lands the whole corpus.
_LISTING_TARGET_CEILING_DEFAULT = 2_000

# Measured 2026-08-05 (see module docstring). Errs ~5% high, which is the
# direction a guardrail should err. Re-derive with --json after a material
# change to the corpus rather than trusting this indefinitely.
_FALLBACK_DIVISOR = 3.6
_MEASURED_RATIO = 3.796
_MEASURED_ON = "2026-08-05"

_COUNT_TOKENS_URL = "https://api.anthropic.com/v1/messages/count_tokens"
_MODEL = "claude-sonnet-4-5"
_TIMEOUT = 60

_BASELINE_SCHEMA = 1
_BASELINE_RELATIVE_PATH = (".ai-state", "token_budget_baseline.json")
_RATCHET_WINDOW_DAYS = 30  # the net-delta comparison window
_BASELINE_PRUNE_DAYS = 35  # kept slightly wider than the window so the window
# always has an in-range sample to compare against, even the day before a prune


def _is_path_scoped(path: Path) -> bool:
    """True when a rule declares `paths:` frontmatter, so it loads conditionally."""
    head = path.read_text(encoding="utf-8").splitlines()[:8]
    return any(line.strip().startswith("paths:") for line in head)


def _unscoped_rule_files(base: Path) -> list[Path]:
    """Unscoped (no `paths:`) `.md` rule files under `base`, catalog `README.md`
    excluded -- a `README.md` carries no `paths:` and so reads as always-loaded
    under a naive "no frontmatter means always loaded" test, but it is a
    catalog rather than a rule and a live session does not inject it. Counting
    it in swings the total by roughly 4,500 tokens -- enough on its own to flip
    the verdict. Absent `base` is not an error: most managed projects carry no
    project-scoped `.claude/rules/`, relying on the global one instead.
    """
    if not base.is_dir():
        return []
    return [
        path
        for path in sorted(base.glob("**/*.md"))
        if path.name != "README.md" and not _is_path_scoped(path)
    ]


def _load_claude_md_excludes(settings_path: Path) -> list[str]:
    """`claudeMdExcludes` glob patterns from a `.claude/settings.json`, or `[]`.

    Absence or malformation fails open (empty list) -- most managed projects
    carry no excludes at all, so a missing file is the common case, not an
    error.
    """
    if not settings_path.is_file():
        return []
    try:
        data = json.loads(settings_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    excludes = data.get("claudeMdExcludes", [])
    if not isinstance(excludes, list):
        return []
    return [pattern for pattern in excludes if isinstance(pattern, str)]


def _exclude_glob_to_regex(pattern: str) -> re.Pattern[str]:
    """A `claudeMdExcludes`-style glob to regex -- `**` crosses `/`, `*` does not.

    Not `fnmatch`: `fnmatch.fnmatch("x/y.md", "**/x/y.md")` is `False` because
    `fnmatch` translates `*` to `.*` with no path-segment awareness, so a
    leading `**/` (meant to match "at any depth, including zero") never
    matches the zero-depth case. This translates each glob primitive by hand
    instead, precisely to keep that zero-depth case matching.
    """
    escaped = re.escape(pattern)
    escaped = escaped.replace(r"\*\*/", "(?:.*/)?")
    escaped = escaped.replace(r"\*\*", ".*")
    escaped = escaped.replace(r"\*", "[^/]*")
    escaped = escaped.replace(r"\?", ".")
    return re.compile(f"^{escaped}$")


def _is_excluded(path: Path, repo_root: Path, patterns: list[str]) -> bool:
    """True when `path` matches any `claudeMdExcludes` glob.

    Tried against both the path relative to `repo_root` and relative to the
    user's home directory (a pattern may target either root), plus the
    absolute posix string as a last resort -- so a pattern anchored at
    whichever root wrote it still matches.
    """
    if not patterns:
        return False
    candidates = {path.as_posix()}
    for root in (repo_root, Path.home()):
        try:
            candidates.add(path.relative_to(root).as_posix())
        except ValueError:
            pass
    return any(
        _exclude_glob_to_regex(pattern).match(candidate)
        for pattern in patterns
        for candidate in candidates
    )


def _discover_rules_manifest(repo_root: Path) -> Path | None:
    """`rules/_manifest.yaml`, checked at the project root first, then the
    live plugin install (`CLAUDE_PLUGIN_ROOT`) -- a managed project's own
    checkout rarely carries the manifest (it ships with the plugin, not the
    project), so the plugin-root fallback is the common case there."""
    candidate = repo_root / "rules" / "_manifest.yaml"
    if candidate.is_file():
        return candidate
    plugin_root = os.environ.get("CLAUDE_PLUGIN_ROOT")
    if plugin_root:
        candidate = Path(plugin_root) / "rules" / "_manifest.yaml"
        if candidate.is_file():
            return candidate
    return None


def _hook_deliver_rule_paths(manifest_text: str) -> list[str]:
    """`path:` values of manifest entries whose `install:` is `hook-deliver`.

    Deliberately not a YAML parse -- this module is stdlib-only by
    construction (see the module docstring) -- and `rules/_manifest.yaml` is
    machine-generated by `regenerate_rules_manifest.py` with one guaranteed
    shape: a flat list of `- id: ...` entries, each a run of unindented-once
    `key: value` scalar lines with no nesting. A line-scan over that one
    shape is exact; it would not be for arbitrary YAML.
    """
    current_path: str | None = None
    current_install: str | None = None
    results: list[str] = []

    def _flush() -> None:
        if current_path and current_install == "hook-deliver":
            results.append(current_path)

    for line in manifest_text.splitlines():
        stripped = line.strip()
        if stripped.startswith("- id:"):
            _flush()
            current_path, current_install = None, None
        elif stripped.startswith("path:"):
            current_path = stripped[len("path:") :].strip().strip("'\"")
        elif stripped.startswith("install:"):
            current_install = stripped[len("install:") :].strip().strip("'\"")
    _flush()
    return results


def _hook_delivered_files(repo_root: Path) -> list[tuple[Path, str]]:
    """Rules delivered into a session by `inject_rules.py` rather than
    symlinked -- the manifest's `install: hook-deliver` rows -- resolved
    against the manifest's own repo root (`<root>/rules/_manifest.yaml` ->
    `<root>`), since a plugin-cache manifest and a checkout manifest
    describe two different physical trees. Returns `(path, name)` pairs so
    the caller can dedup by `name` against whatever other channel already
    delivered the same rule (see `always_loaded_files`)."""
    manifest_path = _discover_rules_manifest(repo_root)
    if manifest_path is None:
        return []
    manifest_root = manifest_path.parent.parent
    relative_paths = _hook_deliver_rule_paths(manifest_path.read_text(encoding="utf-8"))
    return [
        (manifest_root / rel, rel.removeprefix("rules/"))
        for rel in relative_paths
        if rel.startswith("rules/")
    ]


def _rule_name(path: Path, root: Path) -> str:
    """`path`'s identity within a rules tree -- its path relative to `root`,
    POSIX-style. The dedup key across every channel that can deliver the same
    rule (see `always_loaded_files`)."""
    return path.relative_to(root).as_posix()


def always_loaded_files(repo_root: Path, *, include_global: bool = True) -> list[Path]:
    """The always-loaded surface, as the Claude Code loader actually resolves it
    for a session in `repo_root`.

    Four sources: the project's own `CLAUDE.md` and its unscoped
    `.claude/rules/**`; the global `~/.claude/CLAUDE.md` and its unscoped
    `~/.claude/rules/**`; `claudeMdExcludes` glob subtraction from either
    `settings.json`; and the rules a project's own onboarding never symlinks
    at all because `inject_rules.py` delivers them per-session instead
    (`install: hook-deliver` in `rules/_manifest.yaml`). For Praxion's own
    tree, the project-root `rules/**` is *also* included unscoped -- this
    repository is the source the global symlinks point at, not a
    `.claude/rules/`-shaped consumer of it.

    Deduplication is by **rule name** (path relative to whichever rules-tree
    root delivered it), not realpath and not content: a self-hosted checkout
    running from a worktree has its own `rules/**` diverge byte-for-byte from
    whatever `~/.claude/rules/**` symlinks to (a different physical checkout
    entirely, mid-edit relative to it) -- realpath dedup never collapses that
    divergence (two different files), and content-hash dedup only collapses
    it for rules that happen to be byte-identical at measurement time, which
    an in-flight edit to exactly one rule defeats. Name-based dedup collapses
    all of them, and processing project-scoped sources before global ones
    means the project's own (freshest) copy always wins -- exactly the
    "prefer the repo path when present" rule a self-hosted checkout needs.
    The two `CLAUDE.md` singletons (project root, global) are never part of
    a rules-tree name collision and are deduped on their own literal path.
    """
    excludes = _load_claude_md_excludes(repo_root / ".claude" / "settings.json")
    if include_global:
        excludes = excludes + _load_claude_md_excludes(Path.home() / ".claude" / "settings.json")

    files: list[Path] = []
    seen_names: set[str] = set()
    seen_paths: set[Path] = set()

    def _add(path: Path, name: str | None = None) -> None:
        if not path.is_file() or _is_excluded(path, repo_root, excludes):
            return
        if name is None:
            if path in seen_paths:
                return
            seen_paths.add(path)
        else:
            if name in seen_names:
                return
            seen_names.add(name)
        files.append(path)

    _add(repo_root / "CLAUDE.md")
    project_rules = repo_root / ".claude" / "rules"
    for rule_path in _unscoped_rule_files(project_rules):
        _add(rule_path, name=_rule_name(rule_path, project_rules))
    dogfood_rules = repo_root / "rules"
    for rule_path in _unscoped_rule_files(dogfood_rules):
        _add(rule_path, name=_rule_name(rule_path, dogfood_rules))
    if include_global:
        _add(Path.home() / ".claude" / "CLAUDE.md")
        global_rules = Path.home() / ".claude" / "rules"
        for rule_path in _unscoped_rule_files(global_rules):
            _add(rule_path, name=_rule_name(rule_path, global_rules))
        # Hook-delivered rules ride the same "consult ambient session state"
        # channel as the global scan above (`CLAUDE_PLUGIN_ROOT`, a live
        # plugin install) -- gated the same way so `include_global=False`
        # stays what its callers rely on it for: a hermetic, project-only
        # reading with no ambient environment lookups at all.
        for rule_path, name in _hook_delivered_files(repo_root):
            _add(rule_path, name=name)
    return files


@functools.lru_cache(maxsize=32)
def count_tokens(text: str, api_key: str) -> int | None:
    """Real token count, or None when the API is unreachable.

    Memoized per `(text, api_key)`: a process that ends up asking for the
    same corpus twice -- tests, or a future caller re-deriving an
    already-measured reading -- pays the network round-trip once, not twice.
    Use `count_tokens.cache_clear()` between tests that need a fresh call.

    This does NOT collapse `ratchet()`'s two round-trips per commit into
    one: the governed-rules corpus (`measure()`) and the listing-description
    corpus (`measure_listing()`) are disjoint text, so each still needs its
    own call -- there is no shared substring to memoize across them. Both
    share this module's 60s socket `_TIMEOUT` and both run inside
    `check_token_ratchet.py`'s 20s PreToolUse hook timeout
    (`hooks/hooks.json`); a slow or degraded endpoint can still exceed that
    20s budget across the two sequential calls. This cache guards against
    redundant re-tokenization of identical text, not against API latency --
    if endpoint latency becomes an operational problem, shorten `_TIMEOUT`
    for that call site instead.
    """
    request = urllib.request.Request(  # noqa: S310 - fixed https endpoint
        _COUNT_TOKENS_URL,
        data=json.dumps(
            {"model": _MODEL, "messages": [{"role": "user", "content": text}]}
        ).encode(),
        headers={
            "content-type": "application/json",
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=_TIMEOUT) as response:  # noqa: S310
            return int(json.loads(response.read())["input_tokens"])
    except (urllib.error.URLError, OSError, KeyError, ValueError, TimeoutError):
        return None


def measure(repo_root: Path, *, api_key: str | None = None) -> dict:
    """Measure the always-loaded surface. Never raises on a missing key."""
    files = always_loaded_files(repo_root)
    blob = "\n".join(f.read_text(encoding="utf-8") for f in files)
    chars = len(blob.encode("utf-8"))

    tokens = count_tokens(blob, api_key) if api_key else None
    measured = tokens is not None
    if not measured:
        tokens = round(chars / _FALLBACK_DIVISOR)

    return {
        "files": [str(f) for f in files],
        "bytes": chars,
        "tokens": tokens,
        "budget": BUDGET_TOKENS,
        "over_by": max(0, tokens - BUDGET_TOKENS),
        "headroom": max(0, BUDGET_TOKENS - tokens),
        "utilisation": round(tokens / BUDGET_TOKENS, 4),
        "basis": "tokenizer" if measured else f"estimate (bytes / {_FALLBACK_DIVISOR})",
        "measured": measured,
        "chars_per_token": round(chars / tokens, 3) if measured else None,
        "reference_ratio": {"chars_per_token": _MEASURED_RATIO, "measured_on": _MEASURED_ON},
    }


_LISTING_GLOBS = ("skills/*/SKILL.md", "commands/*.md", "agents/*.md")


def listing_files(repo_root: Path) -> list[Path]:
    """Skill/command/agent files whose `description:` frontmatter Claude Code loads
    into every session's tool/skill listing -- a second always-loaded surface,
    disjoint from the rule/CLAUDE.md set `always_loaded_files()` measures."""
    files: list[Path] = []
    for pattern in _LISTING_GLOBS:
        files.extend(sorted(repo_root.glob(pattern)))
    return [f for f in files if f.is_file()]


def _frontmatter_block(text: str) -> str | None:
    """The YAML frontmatter body between the first two `---` fences, or None."""
    if not text.startswith("---"):
        return None
    end = text.find("\n---", 3)
    return None if end == -1 else text[3:end]


def _extract_description(frontmatter: str) -> str:
    """The `description:` value only -- a single-line scalar or a `>`/`|` block.

    Deliberately not a YAML parse (this module is stdlib-only by construction,
    see the module docstring): frontmatter across skills/commands/agents uses
    only these two shapes in practice, and a body line can never look like a
    `description:` key because this only ever scans the fenced frontmatter.
    """
    lines = frontmatter.splitlines()
    for index, line in enumerate(lines):
        stripped = line.strip()
        if not stripped.startswith("description:"):
            continue
        value = stripped[len("description:") :].strip()
        if not value:
            return ""
        if value[0] not in ">|":
            return value.strip("\"'")
        block = []
        for cont in lines[index + 1 :]:
            if cont.strip() == "" or cont.startswith((" ", "\t")):
                block.append(cont.strip())
                continue
            break
        return " ".join(block)
    return ""


_DISABLE_MODEL_INVOCATION_RE = re.compile(r"^disable-model-invocation:\s*true\s*$", re.M)


def name_only_overrides(repo_root: Path) -> set[str]:
    """Skill names the project settings list under `skillOverrides` as `name-only`.

    Claude Code shows only the name for these -- their description leaves the
    model-facing listing. Keys may carry the plugin namespace (`praxion:x`);
    both forms are accepted. Read from `.claude/settings.json` and
    `.claude/settings.local.json` (local wins on conflict, as in the harness).
    """
    names: set[str] = set()
    for rel in (".claude/settings.json", ".claude/settings.local.json"):
        path = repo_root / rel
        if not path.is_file():
            continue
        try:
            overrides = json.loads(path.read_text(encoding="utf-8")).get("skillOverrides", {})
        except (OSError, ValueError):
            continue
        for key, mode in overrides.items():
            if mode == "name-only":
                names.add(key.split(":", 1)[-1])
    return names


def measure_listing(
    repo_root: Path, *, api_key: str | None = None, honor_overrides: bool = True
) -> dict:
    """Measure the listing surface as the model sees it: `description:` frontmatter only,
    minus entries `disable-model-invocation: true` removes outright, and with
    `skillOverrides` name-only skills contributing their name instead of a description."""
    files = listing_files(repo_root)
    # `honor_overrides=False` measures what the model sees if Claude Code ignores the
    # `skillOverrides` key form written to settings -- the ratchet uses that reading
    # until the baseline records `listing_overrides_verified: true` (checked live).
    name_only = name_only_overrides(repo_root) if honor_overrides else set()
    descriptions = []
    for f in files:
        frontmatter = _frontmatter_block(f.read_text(encoding="utf-8"))
        if frontmatter is None:
            continue
        if _DISABLE_MODEL_INVOCATION_RE.search(frontmatter):
            continue
        if f.name == "SKILL.md" and f.parent.name in name_only:
            descriptions.append(f.parent.name)
            continue
        description = _extract_description(frontmatter)
        if description:
            descriptions.append(description)
    blob = "\n".join(descriptions)
    chars = len(blob.encode("utf-8"))

    tokens = count_tokens(blob, api_key) if api_key else None
    measured = tokens is not None
    if not measured:
        tokens = round(chars / _FALLBACK_DIVISOR)

    return {
        "tokens": tokens,
        "bytes": chars,
        "basis": "tokenizer" if measured else f"estimate (bytes / {_FALLBACK_DIVISOR})",
        "measured": measured,
        "file_count": len(files),
    }


def _basis_label(reading: dict) -> str:
    """The short comparison basis for a `measure()`/`measure_listing()` reading.

    Defaults to `"tokenizer"` when `measured` is absent -- the shape every
    `ratchet()` test double and every pre-migration baseline sample used
    before this field existed, and in this repo's dev environment (API key
    always set) that default was also always the true value.
    """
    return "tokenizer" if reading.get("measured", True) else "estimate"


def ratchet(
    repo_root: Path,
    *,
    api_key: str | None = None,
    baseline_path: Path | None = None,
    today: date | None = None,
) -> dict:
    """Today's token-budget ratchet reading against the committed baseline.

    Fails open -- `skipped: True` with a `reason`, never a false `ratchet_ok:
    False` -- whenever the mechanism cannot answer honestly: a governed file
    set found empty (a misconfigured `always_loaded_files()` glob would
    otherwise silently pass every commit), or an absent/unreadable baseline
    file. The second case is deliberately the single detector for two distinct
    situations this gate ships into (a fleet plugin, not just this repo): a
    project that has never seeded a baseline, and a project that is not
    Praxion-managed at all -- neither carries this file, so one check answers
    both without a second, redundant "is this project managed" predicate.

    Records today's sample into the baseline on disk (idempotent -- at most
    one entry per calendar date; a same-day rerun overwrites with the same
    value) before computing the trailing-window delta, so the committed file
    grows by ordinary use rather than a separate bookkeeping step.

    The trailing-window trend compares **bytes**, not tokens (td-180): a
    project whose `ANTHROPIC_API_KEY` availability flips day to day (CI vs.
    local commits) would otherwise see its governed-token history alternate
    between a tokenizer count and the `bytes / 3.6` fallback estimate, and
    the ~20% swing between those two rulers on identical text dwarfs any
    real growth the ratchet exists to catch. Bytes need no such basis --
    the same file set always serializes to the same byte count regardless
    of which measurement path produced today's *token* reading -- so the
    byte-delta check never skips on that account. The frozen listing
    ceiling is a separate, still token-based tripwire and keeps its own
    basis-mismatch guard below, since a labelled token estimate is still
    the right answer to "how many tokens right now."
    """
    path = baseline_path or repo_root.joinpath(*_BASELINE_RELATIVE_PATH)
    today = today or date.today()

    governed = measure(repo_root, api_key=api_key)
    if not governed["files"]:
        return _ratchet_skip("the governed file set is empty")

    baseline = _load_baseline(path)
    if baseline is None:
        return _ratchet_skip(f"no baseline file at {path}")

    overrides_verified = bool(baseline.get("listing_overrides_verified", False))

    listing = measure_listing(repo_root, api_key=api_key, honor_overrides=overrides_verified)
    updated = _append_sample(
        baseline,
        today=today,
        governed_tokens=governed["tokens"],
        governed_bytes=governed["bytes"],
        basis=_basis_label(governed),
    )
    _write_baseline(path, updated)

    today_str = today.isoformat()
    prior_samples = sorted(
        (s for s in updated["samples"] if s["date"] != today_str), key=lambda s: s["date"]
    )
    governed_delta_bytes, notes = _governed_byte_delta(prior_samples, governed, today)

    listing_basis = _basis_label(listing)
    listing_ceiling = baseline.get("listing_ceiling")
    listing_ceiling_basis = baseline.get("listing_ceiling_basis", "tokenizer")
    listing_over_ceiling = False
    if listing_ceiling is not None:
        if listing_ceiling_basis == listing_basis:
            listing_over_ceiling = listing["tokens"] > listing_ceiling
        else:
            notes.append(
                f"listing ceiling was frozen on basis '{listing_ceiling_basis}' but today's "
                f"listing reading is basis '{listing_basis}' -- skipping the listing-ceiling check"
            )

    return {
        "skipped": False,
        "reason": None,
        "ratchet_ok": not listing_over_ceiling
        and (governed_delta_bytes is None or governed_delta_bytes <= 0),
        "governed_delta_bytes": governed_delta_bytes,
        "listing_over_ceiling": listing_over_ceiling,
        "governed_tokens": governed["tokens"],
        "governed_bytes": governed["bytes"],
        "listing_tokens": listing["tokens"],
        "listing_ceiling": listing_ceiling,
        "listing_overrides_verified": overrides_verified,
        "notes": notes,
    }


def _governed_byte_delta(
    prior_samples: list[dict], governed: dict, today: date
) -> tuple[int | None, list[str]]:
    """The trailing-window byte delta against the oldest byte-tracked prior sample.

    The comparison point is the oldest surviving prior sample that carries
    `governed_bytes`, never today's own just-appended entry (comparing today
    against itself would always read as zero delta). Legacy samples recorded
    before this field existed carry only `governed_tokens` -- skipped here,
    not `KeyError`'d, so an old baseline degrades to "no comparison yet"
    rather than crashing the gate. The 35-day prune bound (`_append_sample`)
    already caps how far back "oldest" can reach, so this stays a
    trailing-window comparison without needing a second, narrower window
    filter.
    """
    byte_tracked_priors = [s for s in prior_samples if "governed_bytes" in s]
    if not byte_tracked_priors:
        if prior_samples:
            return None, [
                "no byte-tracked prior sample in the tracked window -- skipping "
                "the governed-byte delta check"
            ]
        return None, []

    oldest_prior = byte_tracked_priors[0]
    tracked_days = (today - date.fromisoformat(oldest_prior["date"])).days
    if tracked_days < _RATCHET_WINDOW_DAYS:
        return None, []
    return governed["bytes"] - oldest_prior["governed_bytes"], []


def _ratchet_skip(reason: str) -> dict:
    return {
        "skipped": True,
        "reason": reason,
        "ratchet_ok": True,
        "governed_delta_bytes": None,
        "listing_over_ceiling": False,
        "notes": [],
    }


def _load_baseline(path: Path) -> dict | None:
    """The baseline, or None on absence/corruption -- both fail open the same way."""
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _append_sample(
    baseline: dict, *, today: date, governed_tokens: int, governed_bytes: int, basis: str
) -> dict:
    """A new baseline dict with today's sample appended and old samples pruned.

    `governed_tokens`/`basis` are kept for reporting (the absolute reading on
    the day the sample was taken); `governed_bytes` is what `ratchet()`'s
    trailing-window trend actually compares (td-180).
    """
    today_str = today.isoformat()
    samples = [s for s in baseline.get("samples", []) if s["date"] != today_str]
    samples.append(
        {
            "date": today_str,
            "governed_tokens": governed_tokens,
            "governed_bytes": governed_bytes,
            "basis": basis,
        }
    )
    cutoff = today - timedelta(days=_BASELINE_PRUNE_DAYS)
    samples = [s for s in samples if date.fromisoformat(s["date"]) >= cutoff]
    samples.sort(key=lambda s: s["date"])
    return {**baseline, "samples": samples}


def _write_baseline(path: Path, baseline: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(baseline, indent=2) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Always-loaded token budget (measured).")
    parser.add_argument("--json", action="store_true", help="emit the reading as JSON")
    parser.add_argument("--repo-root", help="repository root (defaults to git discovery)")
    parser.add_argument(
        "--ratchet",
        action="store_true",
        help="report the trailing-30-day governed-token delta and listing ceiling instead",
    )
    parser.add_argument(
        "--listing-ceiling",
        type=int,
        default=_LISTING_TARGET_CEILING_DEFAULT,
        help=(
            "absolute token ceiling for the skill/command/agent description listing, "
            f"checked alongside --ratchet (default {_LISTING_TARGET_CEILING_DEFAULT}, "
            "~1%% of a 200k window); reported only unless --enforce-listing-ceiling is "
            "also passed"
        ),
    )
    parser.add_argument(
        "--enforce-listing-ceiling",
        action="store_true",
        help="fail --ratchet when --listing-ceiling is exceeded (default: report only)",
    )
    args = parser.parse_args(argv)

    repo_root = resolve_repo_root(args.repo_root, script_dir=SCRIPT_DIR)
    api_key = os.environ.get("ANTHROPIC_API_KEY")

    if args.ratchet:
        result = ratchet(repo_root, api_key=api_key)
        target_over = None
        if not result["skipped"]:
            target_over = result["listing_tokens"] > args.listing_ceiling
            result["listing_target_ceiling"] = args.listing_ceiling
            result["listing_over_target"] = target_over
            if args.enforce_listing_ceiling and target_over:
                result["ratchet_ok"] = False
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            for note in result.get("notes", []):
                print(f"ratchet: INFO -- {note}")
            if result["skipped"]:
                print(f"ratchet: SKIPPED -- {result['reason']}")
            else:
                verdict = "OK" if result["ratchet_ok"] else "BLOCKED"
                print(
                    f"ratchet: {verdict} -- governed_delta_bytes={result['governed_delta_bytes']}, "
                    f"listing={result['listing_tokens']}/{result['listing_ceiling']}"
                )
                target_verdict = "OVER" if target_over else "OK"
                enforced = "enforced" if args.enforce_listing_ceiling else "report-only"
                print(
                    f"ratchet: listing-target {target_verdict} ({enforced}) -- "
                    f"{result['listing_tokens']}/{args.listing_ceiling}"
                )
        return 0 if result["ratchet_ok"] else 1

    report = measure(repo_root, api_key=api_key)
    report["listing"] = measure_listing(repo_root, api_key=api_key)

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        verdict = f"OVER by {report['over_by']:,}" if report["over_by"] else "under budget"
        print(
            f"{report['tokens']:,} / {report['budget']:,} tokens "
            f"({report['utilisation']:.1%}) — {verdict}"
        )
        print(
            f"  basis: {report['basis']} over {len(report['files'])} files, {report['bytes']:,} bytes"
        )
        if not report["measured"]:
            print(
                "  NOTE: no ANTHROPIC_API_KEY — this is an estimate that errs high, not a measurement"
            )
        listing = report["listing"]
        print(
            f"  listing: {listing['tokens']:,} tokens ({listing['basis']}) over "
            f"{listing['file_count']} files, {listing['bytes']:,} bytes"
        )
    return 1 if report["over_by"] else 0


if __name__ == "__main__":
    sys.exit(main())
