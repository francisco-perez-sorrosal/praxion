"""Canary tests for scripts/check_shipped_artifact_isolation.py.

Cites: rules/swe/gate-liveness.md — every CODE gate ships a sibling canary proving
it fails on a known-bad input. These tests feed the detector a shipped-artifact
fixture that cites a specific .ai-state entry and assert it flags it.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

_SCRIPT_PATH = Path(__file__).resolve().parent / "check_shipped_artifact_isolation.py"


def _load_module() -> Any:
    spec = importlib.util.spec_from_file_location(
        "check_shipped_artifact_isolation", _SCRIPT_PATH
    )
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["check_shipped_artifact_isolation"] = mod
    spec.loader.exec_module(mod)
    return mod


_mod = _load_module()
scan_file = _mod.scan_file
main = _mod.main


def _write(root: Path, rel: str, body: str) -> Path:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body, encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# Canary: forbidden patterns in shipped artifacts are flagged
# ---------------------------------------------------------------------------


def test_flags_specific_adr_id_in_rules_file(tmp_path: Path) -> None:
    """A shipped rule file citing a specific dec-042 is flagged as dec-specific.

    Shipped artifacts must not embed specific .ai-state/ entries — the reference
    dangles once the plugin is installed in a different project. The gate must
    catch this before the artifact is shipped.
    """
    # dec-042 is a real Praxion ADR; citing it in a rules/ file is the exact
    # violation the gate exists to catch. The fixture body below is a synthetic
    # shipped artifact, not a reference to dec-042 in production code.
    fixture = _write(
        tmp_path,
        "rules/my_rule.md",
        "## Rationale\n\nThis was decided in dec-042.\n",
    )
    findings = scan_file(fixture)
    assert findings, "gate must flag a specific ADR ID (dec-NNN) in a shipped rule"
    names = [f[1] for f in findings]
    assert "dec-specific" in names, f"expected dec-specific finding; got: {names}"


def test_flags_decision_path_in_shipped_file(tmp_path: Path) -> None:
    """A shipped file citing .ai-state/decisions/042-slug is flagged as decision-path."""
    fixture = _write(
        tmp_path,
        "skills/my_skill/SKILL.md",
        "See `.ai-state/decisions/042-some-slug.md` for context.\n",
    )
    findings = scan_file(fixture)
    assert findings, "gate must flag a direct .ai-state/decisions/ path"
    names = [f[1] for f in findings]
    assert "decision-path" in names, f"expected decision-path finding; got: {names}"


def test_flags_spec_tied_req_id_in_shipped_file(tmp_path: Path) -> None:
    """A shipped file citing REQ-AUTH-01 (spec-tied) is flagged as req-spec-tied."""
    fixture = _write(
        tmp_path,
        "agents/my_agent.md",
        "This agent satisfies REQ-AUTH-01.\n",
    )
    findings = scan_file(fixture)
    assert findings, "gate must flag a spec-tied REQ-* identifier in a shipped artifact"
    names = [f[1] for f in findings]
    assert "req-spec-tied" in names, f"expected req-spec-tied finding; got: {names}"


def test_accepts_path_shape_placeholder(tmp_path: Path) -> None:
    """Happy path: a path shape like dec-NNN placeholder is NOT flagged."""
    fixture = _write(
        tmp_path,
        "rules/clean_rule.md",
        "Decisions follow `.ai-state/decisions/<NNN>-<slug>.md` conventions.\n",
    )
    findings = scan_file(fixture)
    assert findings == [], (
        f"path-shape placeholders must not be flagged; got: {findings}"
    )


def test_accepts_clean_shipped_artifact(tmp_path: Path) -> None:
    """Happy path: a shipped rule with no forbidden patterns produces no findings."""
    fixture = _write(
        tmp_path,
        "rules/good_rule.md",
        "## Convention\n\nAlways commit ADRs to `.ai-state/decisions/`.\n",
    )
    findings = scan_file(fixture)
    assert findings == [], f"clean rule must produce no findings; got: {findings}"


def test_ignore_marker_suppresses_finding(tmp_path: Path) -> None:
    """A line with the ignore marker is not flagged even when it contains a violation."""
    fixture = _write(
        tmp_path,
        "rules/migration_note.md",
        "Migrated from dec-042. <!-- shipped-artifact-isolation:ignore -->\n",
    )
    findings = scan_file(fixture)
    assert findings == [], (
        f"shipped-artifact-isolation:ignore must suppress the finding; got: {findings}"
    )


def test_main_exits_nonzero_on_violation(tmp_path: Path) -> None:
    """end-to-end: main() returns 1 when a shipped artifact has a violation."""
    _write(
        tmp_path,
        "rules/bad_rule.md",
        "This decision was captured in dec-099.\n",
    )
    rc = main(
        [
            "--repo-root",
            str(tmp_path),
            "--files",
            str(tmp_path / "rules" / "bad_rule.md"),
        ]
    )
    assert rc == 1, f"main() must return 1 on violations; got {rc}"


def test_main_exits_zero_when_clean(tmp_path: Path) -> None:
    """end-to-end: main() returns 0 when no violations are found."""
    _write(
        tmp_path,
        "rules/good_rule.md",
        "Follow `.ai-state/decisions/<NNN>-<slug>.md` conventions.\n",
    )
    rc = main(
        [
            "--repo-root",
            str(tmp_path),
            "--files",
            str(tmp_path / "rules" / "good_rule.md"),
        ]
    )
    assert rc == 0, f"main() must return 0 on clean input; got {rc}"
