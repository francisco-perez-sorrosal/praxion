"""Agreement canary: seed-pipeline.md's cited bootstrap signals must be a
subset of scripts/onboard-project's actual seed-trailer keys.

`scripts/onboard-project`'s `build_seed_prompt` emits exactly four trailer
lines as the sole cross-process channel into `seed-pipeline.md` (`# Mode:`,
`# Detected state:`, `# Capabilities:`, `# Brief:`). Prior to the
`seed-prompt-contract-reanchor` rework (rw-380497ab), `seed-pipeline.md` keyed
eight decision points off bootstrap-signal lines the script never emitted
(`# Hackathon mode:`, `# AaC scaffolding:`, `# Obsidian integration:`) --
silently discarding `--hackathon` / `--without aac` / `--without obsidian` in
`new` mode. This test parses both real files (no hardcoded copies of either
key set) and asserts every `` `# <Key>:` `` signal seed-pipeline.md cites is
a member of the script's emitted trailer-key set -- the same non-vacuity bar
as `tests/onboard_project_test.sh`'s T12 state-name-agreement canary.
"""

from __future__ import annotations

import re
from pathlib import Path

SCRIPT_FILE = Path(__file__).parents[2] / "scripts" / "onboard-project"
SEED_PIPELINE_FILE = (
    Path(__file__).parents[2] / "skills" / "onboard-project" / "references" / "seed-pipeline.md"
)

# Matches `# Mode: ${mode}` / `# Detected state: ${state}` style heredoc lines.
_SCRIPT_TRAILER_KEY_RE = re.compile(r"^# ([A-Za-z ]+): \$\{", re.MULTILINE)

# Matches backtick-fenced `` `# Mode:` `` / `` `# Capabilities:` `` citations.
# Captures the key of any backticked trailer-signal citation, with or without a
# value after the colon — the original defect wrote `# Hackathon mode: true`
# (value-bearing), which a colon-then-backtick-only pattern cannot see, making
# the subset check vacuous on exactly the file it was written to catch.
_DOC_SIGNAL_KEY_RE = re.compile(r"`# ([A-Za-z ]+):[^`]*`")


def _script_body() -> str:
    return SCRIPT_FILE.read_text(encoding="utf-8")


def _seed_pipeline_body() -> str:
    return SEED_PIPELINE_FILE.read_text(encoding="utf-8")


def _script_trailer_keys() -> set[str]:
    """Return the trailer keys scripts/onboard-project actually emits."""
    return set(_SCRIPT_TRAILER_KEY_RE.findall(_script_body()))


def _doc_referenced_keys() -> set[str]:
    """Return every `# <Key>:` signal seed-pipeline.md cites.

    Excludes ALL-CAPS placeholders like `` `# TODO:` `` -- those are
    author-facing fill-in markers, not bootstrap-signal citations; every
    real trailer key (`Mode`, `Detected state`, `Capabilities`, `Brief`) is
    Title Case, never all-uppercase.
    """
    found = _DOC_SIGNAL_KEY_RE.findall(_seed_pipeline_body())
    return {key for key in found if not key.isupper()}


def test_script_emits_a_nonempty_trailer_key_set() -> None:
    keys = _script_trailer_keys()
    assert keys, "expected scripts/onboard-project's build_seed_prompt to emit trailer keys"
    assert {"Mode", "Detected state", "Capabilities", "Brief"} == keys


def test_seed_pipeline_cites_a_nonempty_signal_set() -> None:
    # Non-vacuity: a passing subset check against an empty set would be
    # meaningless -- confirm seed-pipeline.md actually cites signals.
    assert _doc_referenced_keys(), (
        "expected seed-pipeline.md to cite at least one `# <Key>:` bootstrap signal"
    )


def test_every_seed_pipeline_signal_is_a_real_trailer_key() -> None:
    doc_keys = _doc_referenced_keys()
    script_keys = _script_trailer_keys()
    missing = doc_keys - script_keys
    assert not missing, (
        f"seed-pipeline.md cites signal(s) {sorted(missing)} that "
        f"scripts/onboard-project's seed trailer never emits "
        f"(actual trailer keys: {sorted(script_keys)})"
    )


def test_seed_pipeline_no_longer_cites_the_retired_bootstrap_signal_lines() -> None:
    body = _seed_pipeline_body()
    for retired in ("Hackathon mode:", "AaC scaffolding:", "Obsidian integration:"):
        assert f"# {retired}" not in body, (
            f"seed-pipeline.md still references the retired bootstrap-signal "
            f"line `# {retired}` instead of deriving from the trailer"
        )
