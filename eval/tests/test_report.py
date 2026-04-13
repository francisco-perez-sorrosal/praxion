"""Tests for Markdown report rendering."""

from __future__ import annotations

from praxion_evals.behavioral.report import (
    ArtifactVerdict,
    Report,
    render_markdown,
)


def _mk_verdict(path: str, verdict: str, required: bool = True) -> ArtifactVerdict:
    return ArtifactVerdict(path=path, verdict=verdict, required=required)  # type: ignore[arg-type]


def test_render_markdown_contains_heading_and_bullets():
    report = Report(
        task_slug="demo",
        tier="standard",
        verdicts=(
            _mk_verdict(".ai-work/demo/WIP.md", "present"),
            _mk_verdict(".ai-work/demo/VERIFICATION_REPORT.md", "missing"),
        ),
    )
    output = render_markdown(report)
    assert "# Behavioral Eval — demo" in output
    assert "**Tier**: standard" in output
    assert "[x] `.ai-work/demo/WIP.md`" in output
    assert "[ ] `.ai-work/demo/VERIFICATION_REPORT.md`" in output


def test_render_markdown_passes_when_all_required_present():
    report = Report(
        task_slug="demo",
        tier="standard",
        verdicts=(_mk_verdict("x.md", "present"),),
    )
    assert "Verdict**: PASS" in render_markdown(report)
    assert report.score == 100


def test_render_markdown_error_short_circuits():
    report = Report(task_slug="demo", tier="standard", error="Task dir missing")
    output = render_markdown(report)
    assert "## Error" in output
    assert "Task dir missing" in output
