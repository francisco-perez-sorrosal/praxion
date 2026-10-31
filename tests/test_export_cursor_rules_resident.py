"""The Cursor export carries a rule once: its resident file (a `resident_of` projection) adds no rule."""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
EXPORTER = REPO_ROOT / "cursor" / "config" / "export-cursor-rules.py"

RULE = "---\npaths:\n  - 'docs/**'\n---\n## Rule\n\nThe whole rule.\n"
RESIDENT = "---\nresident_of: rules/swe/rule.md\n---\n## Rule\n\nOne line of it.\n"


def _export(root: Path, out: Path) -> dict[str, bytes]:
    subprocess.run(
        [sys.executable, str(EXPORTER), str(root), str(out)],
        check=True,
        capture_output=True,
        text=True,
    )
    return {str(p.relative_to(out)): p.read_bytes() for p in sorted(out.rglob("*")) if p.is_file()}


def _tree(base: Path, files: dict[str, str]) -> Path:
    for rel, text in files.items():
        path = base / "rules" / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return base


def test_a_resident_beside_its_rule_yields_no_cursor_rule_and_leaves_the_rule_unchanged(
    tmp_path: Path,
) -> None:
    alone = _export(_tree(tmp_path / "alone", {"swe/rule.md": RULE}), tmp_path / "out-alone")
    both = _export(
        _tree(tmp_path / "both", {"swe/rule.md": RULE, "swe/rule-resident.md": RESIDENT}),
        tmp_path / "out-both",
    )

    assert set(both) == {"swe/rule.md"}
    assert both == alone


def test_a_rule_that_only_mentions_resident_of_in_its_body_is_still_exported(
    tmp_path: Path,
) -> None:
    mentions = (
        "---\npaths:\n  - 'docs/**'\n---\n## Rule\n\nA resident file says `resident_of: x`.\n"
    )

    exported = _export(_tree(tmp_path / "root", {"swe/mentions.md": mentions}), tmp_path / "out")

    assert set(exported) == {"swe/mentions.md"}


def _exporter_module():
    spec = importlib.util.spec_from_file_location("export_cursor_rules", EXPORTER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize(
    "text",
    [
        RESIDENT,
        RULE,
        "---\n'resident_of': \"rules/swe/rule.md\"\n---\nBody.\n",
        "---\nresident_of:\n---\nBody.\n",
        "---\n  resident_of: rules/swe/rule.md\n---\nBody.\n",
        "---\nresident_of: rules/swe/rule.md\nBody, never closed.\n",
        "No frontmatter; resident_of: rules/swe/rule.md\n",
        "---\npaths: ['docs/**']\n---\nresident_of: rules/swe/rule.md\n",
        "---\nresident_of: not-a-rule-path\n---\nBody.\n",
        "---\nresident_ofx: rules/swe/rule.md\n---\nBody.\n",
    ],
    ids=[
        "resident",
        "rule",
        "quoted",
        "empty",
        "indented",
        "unclosed",
        "none",
        "in-body",
        "non-md-value",
        "longer-key",
    ],
)
def test_the_exporters_resident_check_agrees_with_the_shared_reader(text: str) -> None:
    from scripts._resident_of import resident_parent

    assert _exporter_module().is_resident(text) is bool(resident_parent(text))
