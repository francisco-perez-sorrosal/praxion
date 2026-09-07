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

Stdlib-only, deliberately: the sentinel invokes this through the ambient
interpreter, so a third-party import would make it a finding of the
`ambient-import` gate-liveness check.

Exit 0 under budget, 1 over -- so it doubles as a gate. A missing API key is
not a failure; it downgrades the reading to an estimate and says so.

Cites: rules/CLAUDE.md#token-budget (the ceiling and the attention-share rule).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import date, timedelta
from pathlib import Path

from _repo_root import resolve_repo_root

SCRIPT_DIR = Path(__file__).resolve().parent

BUDGET_TOKENS = 25_000

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


def always_loaded_files(repo_root: Path, *, include_global: bool = True) -> list[Path]:
    """The always-loaded surface, as the loader actually resolves it.

    Catalog `README.md` files are excluded. This is not a convenience: a
    `rules/README.md` carries no `paths:` and so reads as always-loaded under a
    naive "no frontmatter means always loaded" test, but it is a catalog rather
    than a rule and a live session does not inject it. Counting them in swings
    the total by roughly 4,500 tokens -- enough on its own to flip the verdict.
    """
    files = [
        path
        for path in sorted(repo_root.glob("rules/**/*.md"))
        if path.name != "README.md" and not _is_path_scoped(path)
    ]
    files.append(repo_root / "CLAUDE.md")
    if include_global:
        files.append(Path.home() / ".claude" / "CLAUDE.md")
    return [f for f in files if f.is_file()]


def count_tokens(text: str, api_key: str) -> int | None:
    """Real token count, or None when the API is unreachable."""
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


def measure_listing(repo_root: Path, *, api_key: str | None = None) -> dict:
    """Measure the listing surface: only `description:` frontmatter, never body text."""
    files = listing_files(repo_root)
    descriptions = []
    for f in files:
        frontmatter = _frontmatter_block(f.read_text(encoding="utf-8"))
        if frontmatter is None:
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
        "file_count": len(files),
    }


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
    """
    path = baseline_path or repo_root.joinpath(*_BASELINE_RELATIVE_PATH)
    today = today or date.today()

    governed = measure(repo_root, api_key=api_key)
    if not governed["files"]:
        return _ratchet_skip("the governed file set is empty")

    baseline = _load_baseline(path)
    if baseline is None:
        return _ratchet_skip(f"no baseline file at {path}")

    listing = measure_listing(repo_root, api_key=api_key)
    updated = _append_sample(baseline, today=today, governed_tokens=governed["tokens"])
    _write_baseline(path, updated)

    today_str = today.isoformat()
    prior_samples = sorted(
        (s for s in updated["samples"] if s["date"] != today_str), key=lambda s: s["date"]
    )
    oldest_prior = prior_samples[0] if prior_samples else None
    tracked_days = (today - date.fromisoformat(oldest_prior["date"])).days if oldest_prior else 0

    # The comparison point is the oldest surviving prior sample, never today's
    # own just-appended entry -- comparing today against itself would always
    # read as zero delta and mask real growth whenever the daily cadence has a
    # gap. The 35-day prune bound (`_append_sample`) already caps how far back
    # "oldest" can reach, so this stays a trailing-window comparison without
    # needing a second, narrower window filter that can end up with nothing
    # but today's entry left inside it.
    governed_delta = (
        governed["tokens"] - oldest_prior["governed_tokens"]
        if tracked_days >= _RATCHET_WINDOW_DAYS
        else None
    )

    listing_ceiling = baseline.get("listing_ceiling")
    listing_over_ceiling = listing_ceiling is not None and listing["tokens"] > listing_ceiling

    return {
        "skipped": False,
        "reason": None,
        "ratchet_ok": not listing_over_ceiling and (governed_delta is None or governed_delta <= 0),
        "governed_delta": governed_delta,
        "listing_over_ceiling": listing_over_ceiling,
        "governed_tokens": governed["tokens"],
        "listing_tokens": listing["tokens"],
        "listing_ceiling": listing_ceiling,
    }


def _ratchet_skip(reason: str) -> dict:
    return {
        "skipped": True,
        "reason": reason,
        "ratchet_ok": True,
        "governed_delta": None,
        "listing_over_ceiling": False,
    }


def _load_baseline(path: Path) -> dict | None:
    """The baseline, or None on absence/corruption -- both fail open the same way."""
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _append_sample(baseline: dict, *, today: date, governed_tokens: int) -> dict:
    """A new baseline dict with today's sample appended and old samples pruned."""
    today_str = today.isoformat()
    samples = [s for s in baseline.get("samples", []) if s["date"] != today_str]
    samples.append({"date": today_str, "governed_tokens": governed_tokens})
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
    args = parser.parse_args(argv)

    repo_root = resolve_repo_root(args.repo_root, script_dir=SCRIPT_DIR)
    api_key = os.environ.get("ANTHROPIC_API_KEY")

    if args.ratchet:
        result = ratchet(repo_root, api_key=api_key)
        if args.json:
            print(json.dumps(result, indent=2))
        elif result["skipped"]:
            print(f"ratchet: SKIPPED -- {result['reason']}")
        else:
            verdict = "OK" if result["ratchet_ok"] else "BLOCKED"
            print(
                f"ratchet: {verdict} -- governed_delta={result['governed_delta']}, "
                f"listing={result['listing_tokens']}/{result['listing_ceiling']}"
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
