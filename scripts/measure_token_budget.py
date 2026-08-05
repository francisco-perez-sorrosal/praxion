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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Always-loaded token budget (measured).")
    parser.add_argument("--json", action="store_true", help="emit the reading as JSON")
    parser.add_argument("--repo-root", help="repository root (defaults to git discovery)")
    args = parser.parse_args(argv)

    report = measure(
        resolve_repo_root(args.repo_root, script_dir=SCRIPT_DIR),
        api_key=os.environ.get("ANTHROPIC_API_KEY"),
    )

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
    return 1 if report["over_by"] else 0


if __name__ == "__main__":
    sys.exit(main())
