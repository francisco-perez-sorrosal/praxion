"""Structural tests for the healing-sidecar §Phase 2 onboarding sub-step.

`/onboard-project` (now `skills/onboard-project/SKILL.md` + its phase-body
references) is executed by a live Claude Code session — it cannot be invoked
from pytest. These tests validate the documented contract by parsing
`skills/onboard-project/references/phases-core.md` structurally, matching the
precedent set by `tests/commands/test_onboard_ci_autofix_install.py`.

Unlike the ci-autofix sub-step (its own `### Sub-step 8e.8` heading), the
healing-sidecar install is a new bullet inside the existing `## §Phase 2` list
(mirroring the `.ai-state/metrics_reports/index.html` bullet already there) —
so assertions scope to the §Phase 2 section body, not to a dedicated heading.
"""

from __future__ import annotations

import re
from pathlib import Path

ONBOARD_FILE = (
    Path(__file__).parents[2] / "skills" / "onboard-project" / "references" / "phases-core.md"
)

PENDING_PATH = ".ai-state/praxion_feedback/PENDING.md"


def _onboard_body() -> str:
    """Return the full phases-core.md content (read lazily so collection succeeds)."""
    return ONBOARD_FILE.read_text(encoding="utf-8")


def _phase_2_section() -> str:
    """Return the '## §Phase 2' section body, up to the next '## ' heading.

    A fixed heading-to-heading window keeps assertions scoped to this phase's
    own text and unable to pass vacuously against a neighboring phase.
    """
    match = re.search(r"##\s+§Phase 2 .*?(?=\n## |\Z)", _onboard_body(), re.DOTALL)
    return match.group(0) if match else ""


def _manifest_artifacts_snippet() -> str:
    """Return the text following the '"artifacts"' key in the §Phase 9 manifest example.

    A fixed-size window (not brace-matching) is intentional: the manifest JSON
    example is illustrative Markdown, not parseable JSON, so a generous
    character window is more robust than exact brace nesting.
    """
    body = _onboard_body()
    idx = body.find('"artifacts"')
    assert idx != -1, "commands/onboard-project.md must document an 'artifacts' manifest key"
    return body[idx : idx + 700]


def test_phase_2_documents_the_pending_ledger_skeleton() -> None:
    section = _phase_2_section()
    assert section, "§Phase 2 section not found in commands/onboard-project.md"
    assert PENDING_PATH in section, (
        f"§Phase 2 must document creating '{PENDING_PATH}' as a header-only "
        "skeleton — not found. The implementer must add it."
    )


def test_skips_without_overwriting_when_pending_already_exists() -> None:
    section = _phase_2_section()
    assert PENDING_PATH in section, "PENDING.md sub-step not documented yet"
    # Scope to the text following the PENDING.md bullet, up to the next top-level bullet.
    idx = section.find(PENDING_PATH)
    following = section[idx : idx + 700]
    predicate_match = re.search(r"\*\*Predicate.*?\*\*.*?(?=\n\*\*Action|\Z)", following, re.DOTALL)
    assert predicate_match, "PENDING.md sub-step must document a Predicate (skip-if-exists guard)"
    predicate = predicate_match.group(0)
    assert PENDING_PATH in predicate, "Predicate must check for an existing PENDING.md"
    assert re.search(r"skip", predicate, re.IGNORECASE), (
        "Predicate must document skipping (never overwriting) when PENDING.md already exists"
    )


def test_writes_header_only_skeleton_content() -> None:
    section = _phase_2_section()
    assert PENDING_PATH in section, "PENDING.md sub-step not documented yet"
    idx = section.find(PENDING_PATH)
    following = section[idx : idx + 1000]
    assert re.search(r"\bAction\b", following), "PENDING.md sub-step must document an Action"
    assert "Pending Praxion Feedback" in following, (
        "Action must write the header-only skeleton content "
        "(the '# Pending Praxion Feedback' heading)"
    )
    assert "/report-praxion-issue" in following, (
        "Skeleton content must reference /report-praxion-issue"
    )


def test_records_install_in_onboard_manifest() -> None:
    snippet = _manifest_artifacts_snippet()
    assert re.search(r'"[a-z_]*praxion_feedback[a-z_]*"\s*:', snippet, re.IGNORECASE), (
        "The §Phase 9 onboard-manifest 'artifacts' example must gain a new key "
        "recording the installed praxion_feedback ledger — not found near the "
        "'artifacts' block."
    )


def test_reporter_and_command_documented_as_plugin_global_not_per_project() -> None:
    section = _phase_2_section()
    assert PENDING_PATH in section, "PENDING.md sub-step not documented yet"
    idx = section.find(PENDING_PATH)
    preceding_and_following = section[max(0, idx - 200) : idx + 700]
    assert re.search(r"plugin-global", preceding_and_following, re.IGNORECASE), (
        "Sub-step must document that the reporter script and command are "
        "plugin-global (no per-project copy needed)"
    )
    assert re.search(
        r"no.{0,40}per-project (copy|wiring)", preceding_and_following, re.IGNORECASE
    ), (
        "Sub-step must explicitly rule out any additional per-project asset "
        "install beyond the PENDING.md skeleton (reporter/command/hook ship "
        "plugin-wide via hooks/hooks.json)"
    )
