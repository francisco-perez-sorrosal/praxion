"""Tests for check_frontmatter_parses.py -- the frontmatter-loads gate.

This file is the gate's canary set (rules/swe/gate-liveness.md: a CODE gate
ships proof it *fails* on a known-bad input, not merely that it passes on the
current good state).

The known-bad input is not invented. Two shipped commands carried

    argument-hint: [<run_tag>] [--task-slug <slug>]

-- two unquoted flow sequences on one line, which no YAML parser accepts. The
entire frontmatter block failed to load, so neither command could register its
``description``, and every field-presence grep in the repo stayed green
throughout. ``test_canary_flags_the_historical_defect`` reconstructs that exact
byte sequence.

Behavioral tests:

1. The live repo scans clean (the no-op control -- without it, a gate that
   flags nothing would pass every canary below).
2. CANARY: the historical two-flow-sequence defect is flagged ``unparseable``,
   with the parser's own line/column in the detail.
3. CANARY: an unindented block-scalar continuation is flagged ``unparseable``.
4. CANARY: an unterminated frontmatter block is flagged ``no-closing-delimiter``
   rather than silently read as a body.
5. CANARY: frontmatter that loads as a scalar or list is flagged
   ``not-a-mapping`` -- field lookup on a non-mapping returns nothing rather
   than raising, so this shape reads as "no fields" to every consumer.
6. Well-formed frontmatter (including a correctly indented block scalar and a
   quoted ``argument-hint``) is NOT flagged.
7. A file with no frontmatter is counted and skipped, never flagged -- the
   documented scope boundary.
8. CANARY: the CLI exits non-zero on a defective tree and zero on a clean one --
   the exit code is what the pre-commit hook reads.
9. CANARY: with PyYAML absent the gate raises naming ``sys.executable`` and the
   CLI exits 2 -- it never degrades to a clean verdict (gate-liveness GL05).
10. The ``.pre-commit-config.yaml`` ``files:`` pattern matches every path the
    scanner actually scans (scope fidelity), and does not match the prose files
    alongside them.

Every mutating test builds its tree under ``tmp_path``; the real repo is only
ever read.
"""

from __future__ import annotations

import builtins
import functools
import importlib.util
import re
import sys
from pathlib import Path
from typing import Any

import pytest
import yaml

_SCRIPT_PATH = Path(__file__).resolve().parent / "check_frontmatter_parses.py"
_REPO_ROOT = Path(__file__).resolve().parent.parent
_PRECOMMIT_CONFIG = _REPO_ROOT / ".pre-commit-config.yaml"
_HOOK_ID = "artifact-frontmatter-parse"

# The exact frontmatter that shipped broken, byte-for-byte on the offending line.
_HISTORICAL_DEFECT = """\
---
description: >
  Poll or report on an ML training experiment. Identify the run by run_tag
  argument, or by listing recent archived runs.
argument-hint: [<run_tag>] [--task-slug <slug>]
allowed-tools: [Read, Bash, Glob]
---

Body prose.
"""

# The same file, repaired the way the two commands were.
_REPAIRED = _HISTORICAL_DEFECT.replace(
    "argument-hint: [<run_tag>] [--task-slug <slug>]",
    'argument-hint: "[<run_tag>] [--task-slug <slug>]"',
)

# A folded block scalar whose continuation lines sit at column 0: the parser is
# still inside the scalar when it meets the next key.
_UNINDENTED_BLOCK_SCALAR = """\
---
description: >
Poll or report on an ML training experiment.
allowed-tools: [Read]
---

Body prose.
"""


@functools.lru_cache(maxsize=1)
def _gate() -> Any:
    """Load the gate module under test, caching it across tests."""
    spec = importlib.util.spec_from_file_location("check_frontmatter_parses", _SCRIPT_PATH)
    assert spec is not None, f"gate module not importable at {_SCRIPT_PATH}"
    assert spec.loader is not None, f"gate module has no loader at {_SCRIPT_PATH}"
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _write_command(root: Path, name: str, body: str) -> Path:
    """Materialize one in-scope artifact under `root` and return its path."""
    path = root / "commands" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return path


def _kinds(report: dict[str, Any]) -> list[str]:
    return [finding["kind"] for finding in report["findings"]]


def _hook_files_pattern() -> str:
    """The `files:` regex the pre-commit hook filters staged paths with."""
    config = yaml.safe_load(_PRECOMMIT_CONFIG.read_text(encoding="utf-8"))
    for repo in config["repos"]:
        for hook in repo.get("hooks", []):
            if hook.get("id") == _HOOK_ID:
                return hook["files"]
    raise AssertionError(f"hook id {_HOOK_ID!r} is not registered in {_PRECOMMIT_CONFIG}")


# --- 1. Control: the live repository ----------------------------------------


def test_real_repo_frontmatter_all_loads() -> None:
    """Every artifact in the live tree that declares frontmatter parses as a mapping."""
    report = _gate().check_frontmatter_parses(_REPO_ROOT)

    assert report["findings"] == [], (
        f"shipped artifacts carry frontmatter no YAML parser can load: {report['findings']}"
    )
    assert report["with_frontmatter"] > 100, (
        "scan collapsed to a near-empty set -- a gate examining nothing reports "
        f"clean forever (with_frontmatter={report['with_frontmatter']})"
    )


# --- 2-5. Canaries: each finding kind bites ---------------------------------


def test_canary_flags_the_historical_defect(tmp_path: Path) -> None:
    """The two-unquoted-flow-sequences line that actually shipped is flagged."""
    _write_command(tmp_path, "check-experiment.md", _HISTORICAL_DEFECT)

    report = _gate().check_frontmatter_parses(tmp_path)

    assert _kinds(report) == ["unparseable"]
    finding = report["findings"][0]
    assert finding["file"] == "commands/check-experiment.md"
    # The parser's own problem mark must survive into the finding: without the
    # line/column a reader cannot locate the defect in a 15-line block.
    assert "argument-hint" in finding["detail"] or "line 4" in finding["detail"]


def test_canary_flags_unindented_block_scalar(tmp_path: Path) -> None:
    """A folded scalar whose continuation sits at column 0 is flagged."""
    _write_command(tmp_path, "run-experiment.md", _UNINDENTED_BLOCK_SCALAR)

    report = _gate().check_frontmatter_parses(tmp_path)

    assert _kinds(report) == ["unparseable"]


def test_canary_flags_missing_closing_delimiter(tmp_path: Path) -> None:
    """An unterminated block is named, not silently treated as body prose."""
    _write_command(tmp_path, "unterminated.md", "---\ndescription: hello\n\nBody prose.\n")

    report = _gate().check_frontmatter_parses(tmp_path)

    assert _kinds(report) == ["no-closing-delimiter"]


@pytest.mark.parametrize(
    ("block", "expected_kind"),
    [
        ("- just\n- a list", "list"),
        ("just a bare scalar", "str"),
        ("# only a comment", "empty"),
    ],
)
def test_canary_flags_non_mapping_frontmatter(
    tmp_path: Path, block: str, expected_kind: str
) -> None:
    """Frontmatter that loads as anything but a mapping is flagged.

    Field lookup on a non-mapping returns nothing rather than raising, so this
    shape is indistinguishable from "declares no fields" to every consumer.
    """
    _write_command(tmp_path, "shape.md", f"---\n{block}\n---\n\nBody.\n")

    report = _gate().check_frontmatter_parses(tmp_path)

    assert _kinds(report) == ["not-a-mapping"]
    assert expected_kind in report["findings"][0]["detail"]


def test_canary_flags_bracket_form_argument_hint(tmp_path: Path) -> None:
    """CANARY: a one-element bracket hint is a YAML list, and must be flagged.

    ``argument-hint: [--init]`` parses cleanly, so every check that greps for
    field presence -- and both the Cursor and Codex line-regex exporters, which
    coerce whatever they read to ``str`` -- report it healthy.  Only a real YAML
    loader sees a ``list``, which is why the divergence survived across 15 files
    unnoticed.  It is also one edit from ``unparseable``: add a second group and
    the line becomes two flow sequences, the historical defect above.
    """
    _write_command(tmp_path, "bracket.md", "---\nargument-hint: [--init]\n---\n\nBody.\n")

    report = _gate().check_frontmatter_parses(tmp_path)

    assert _kinds(report) == ["argument-hint-not-a-string"]
    assert "list" in report["findings"][0]["detail"]


def test_quoted_argument_hint_is_not_flagged(tmp_path: Path) -> None:
    """Inverse guard: the canonical quoted form scans clean.

    Including the multi-group shape the bracket form cannot express at all.
    """
    _write_command(
        tmp_path,
        "quoted.md",
        '---\nargument-hint: "[<tag>] [--slug <s>]"\n---\n\nBody.\n',
    )

    report = _gate().check_frontmatter_parses(tmp_path)

    assert report["findings"] == []


# --- 6-7. Inverse guards: no false positives --------------------------------


def test_well_formed_frontmatter_is_not_flagged(tmp_path: Path) -> None:
    """The repaired form of the historical defect scans clean."""
    _write_command(tmp_path, "check-experiment.md", _REPAIRED)

    report = _gate().check_frontmatter_parses(tmp_path)

    assert report["findings"] == []
    assert report["with_frontmatter"] == 1


def test_file_without_frontmatter_is_skipped_not_flagged(tmp_path: Path) -> None:
    """Absent frontmatter is counted and skipped -- it is another gate's question."""
    _write_command(tmp_path, "README.md", "# Commands\n\nA catalog, no frontmatter.\n")

    report = _gate().check_frontmatter_parses(tmp_path)

    assert report["findings"] == []
    assert report["scanned"] == 1
    assert report["with_frontmatter"] == 0
    assert report["skipped_no_frontmatter"] == 1


# --- 8. Canary: the CLI exit code the hook reads ----------------------------


def test_canary_cli_exits_nonzero_on_defective_tree(tmp_path: Path, capsys) -> None:
    """The exit code -- the only thing pre-commit reads -- distinguishes the trees."""
    _write_command(tmp_path, "broken.md", _HISTORICAL_DEFECT)
    assert _gate().main(["--repo-root", str(tmp_path)]) == 1
    assert "unparseable" in capsys.readouterr().out

    _write_command(tmp_path, "broken.md", _REPAIRED)
    assert _gate().main(["--repo-root", str(tmp_path)]) == 0


# --- 9. Canary: the GL05 dependency disposition -----------------------------


def test_canary_missing_pyyaml_raises_naming_the_interpreter(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    """Without a parser the gate refuses a verdict; it never reports clean.

    A gate that dies on import, or degrades to an empty result, is
    indistinguishable from no gate (gate-liveness GL05). The remedy must name
    `sys.executable`, because the cause is almost always the wrong interpreter
    rather than an uninstalled package.
    """
    gate = _gate()
    _write_command(tmp_path, "fine.md", _REPAIRED)
    real_import = builtins.__import__

    def _no_yaml(name: str, *args: Any, **kwargs: Any) -> Any:
        if name == "yaml":
            raise ModuleNotFoundError("No module named 'yaml'")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _no_yaml)
    monkeypatch.delitem(sys.modules, "yaml", raising=False)

    with pytest.raises(gate.MissingParserError) as excinfo:
        gate.check_frontmatter_parses(tmp_path)
    assert sys.executable in str(excinfo.value)

    assert gate.main(["--repo-root", str(tmp_path)]) == 2
    assert "PyYAML is required" in capsys.readouterr().err


# --- 10. Scope fidelity: the hook's filter vs. the scanner's real input -----


def test_precommit_pattern_matches_every_scanned_path() -> None:
    """The hook's `files:` filter must cover every path the scanner examines.

    A narrower filter means the gate never fires on the artifacts it is
    documented to guard -- the scope-fidelity failure that returns a false
    all-clear for everything outside the computed set.
    """
    pattern = re.compile(_hook_files_pattern())
    scanned = [path.relative_to(_REPO_ROOT).as_posix() for path in _gate().scan_targets(_REPO_ROOT)]
    assert scanned, "scanner found nothing -- the coverage assertion would be vacuous"

    unmatched = [rel for rel in scanned if not pattern.search(rel)]
    assert unmatched == [], (
        "the pre-commit `files:` pattern does not fire on these scanned artifacts, "
        f"so edits to them never invoke the gate: {unmatched}"
    )


@pytest.mark.parametrize(
    "unrelated",
    [
        "docs/architecture.md",
        "skills/refactoring/references/patterns.md",
        ".ai-state/DESIGN.md",
        "README.md",
    ],
)
def test_precommit_pattern_does_not_match_unrelated_prose(unrelated: str) -> None:
    """An over-broad filter runs the gate on files it has no claim over."""
    assert not re.compile(_hook_files_pattern()).search(unrelated)
