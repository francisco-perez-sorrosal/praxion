"""Canary tests for scripts/check_paths_syntax.py.

Cites: rules/swe/gate-liveness.md — every CODE gate ships a sibling canary proving
it fails on a known-bad input. These tests feed the detector a rule file with a
multi-entry YAML block-list paths: declaration and assert it flags it AT_RISK.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

_SCRIPT_PATH = Path(__file__).resolve().parent / "check_paths_syntax.py"


def _load_module() -> Any:
    spec = importlib.util.spec_from_file_location("check_paths_syntax", _SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["check_paths_syntax"] = mod
    spec.loader.exec_module(mod)
    return mod


_mod = _load_module()
classify = _mod.classify
SyntaxForm = _mod.SyntaxForm


def _write_rule(root: Path, name: str, frontmatter: str) -> Path:
    """Write a synthetic rule file with the given frontmatter under root/rules/."""
    rules_dir = root / "rules"
    rules_dir.mkdir(parents=True, exist_ok=True)
    p = rules_dir / name
    p.write_text(
        f"---\n{frontmatter}\n---\n\n## Body\n\nSome content.\n", encoding="utf-8"
    )
    return p


# ---------------------------------------------------------------------------
# Canary: multi-entry YAML block-list is flagged AT_RISK
# ---------------------------------------------------------------------------


def test_flags_multi_entry_block_list_as_at_risk(tmp_path: Path) -> None:
    """A rule using a multi-entry YAML block-list paths: is classified AT_RISK.

    Per upstream anthropics/claude-code#16853, multi-entry block-list paths:
    declarations fail silently in production. The gate must flag them.
    """
    rule = _write_rule(
        tmp_path,
        "test_rule.md",
        'paths:\n  - "**/*.py"\n  - "**/*.pyi"\n',
    )
    decl = classify(rule)
    assert decl is not None, "classify() must return a PathsDecl for this rule"
    assert decl.form == SyntaxForm.BLOCK_LIST_MULTI, (
        f"expected BLOCK_LIST_MULTI; got {decl.form}"
    )
    assert decl.at_risk, "multi-entry block-list must be flagged at_risk"


def test_flags_three_entry_block_list_as_at_risk(tmp_path: Path) -> None:
    """A rule with three block-list entries is also AT_RISK."""
    rule = _write_rule(
        tmp_path,
        "three_entry.md",
        'paths:\n  - "**/*.py"\n  - "**/*.ts"\n  - "**/*.js"\n',
    )
    decl = classify(rule)
    assert decl is not None
    assert decl.at_risk, "three-entry block-list must be at_risk"
    assert decl.suggested_inline is not None, (
        "AT_RISK rule must have a suggested inline rewrite"
    )


# ---------------------------------------------------------------------------
# Happy path: safe forms are not flagged
# ---------------------------------------------------------------------------


def test_accepts_inline_array_form(tmp_path: Path) -> None:
    """An inline-array paths: is NOT at_risk."""
    rule = _write_rule(
        tmp_path,
        "inline.md",
        'paths: ["**/*.py", "**/*.pyi"]\n',
    )
    decl = classify(rule)
    assert decl is not None
    assert decl.form == SyntaxForm.INLINE_ARRAY
    assert not decl.at_risk


def test_accepts_single_block_list_entry(tmp_path: Path) -> None:
    """A single-entry block-list paths: is NOT at_risk."""
    rule = _write_rule(
        tmp_path,
        "single_block.md",
        'paths:\n  - "**/*.py"\n',
    )
    decl = classify(rule)
    assert decl is not None
    assert decl.form == SyntaxForm.BLOCK_LIST_SINGLE
    assert not decl.at_risk


def test_accepts_single_string_form(tmp_path: Path) -> None:
    """A single-string paths: is NOT at_risk."""
    rule = _write_rule(
        tmp_path,
        "single_string.md",
        'paths: "**/*.py"\n',
    )
    decl = classify(rule)
    assert decl is not None
    assert decl.form == SyntaxForm.SINGLE_STRING
    assert not decl.at_risk


def test_at_risk_rule_includes_suggested_inline_rewrite(tmp_path: Path) -> None:
    """An AT_RISK rule provides a suggested inline-array rewrite."""
    rule = _write_rule(
        tmp_path,
        "needs_fix.md",
        'paths:\n  - "tests/**"\n  - "test_*"\n',
    )
    decl = classify(rule)
    assert decl is not None and decl.at_risk
    suggestion = decl.suggested_inline
    assert suggestion is not None
    assert suggestion.startswith("paths: [")
    assert '"tests/**"' in suggestion
    assert '"test_*"' in suggestion
