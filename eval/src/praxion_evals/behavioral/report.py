"""Report dataclasses + Markdown rendering for the behavioral eval."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

Verdict = Literal["present", "missing", "stale", "skipped"]


@dataclass(frozen=True)
class ArtifactVerdict:
    """One line-item in the report: expected artifact + its filesystem verdict."""

    path: str
    verdict: Verdict
    required: bool
    description: str = ""
    detail: str = ""


@dataclass(frozen=True)
class Report:
    """Structured outcome of a behavioral eval run."""

    task_slug: str
    tier: str
    verdicts: tuple[ArtifactVerdict, ...] = field(default_factory=tuple)
    error: str | None = None

    @property
    def passed(self) -> bool:
        """True when every required artifact is ``present``."""
        if self.error is not None:
            return False
        return all(v.verdict == "present" for v in self.verdicts if v.required)

    @property
    def score(self) -> int:
        """Percentage of required artifacts that are present (0-100)."""
        required = [v for v in self.verdicts if v.required]
        if not required:
            return 100
        present = sum(1 for v in required if v.verdict == "present")
        return int(round(100 * present / len(required)))


def render_markdown(report: Report) -> str:
    """Render a Report as a Markdown summary suitable for stdout."""
    status = "PASS" if report.passed else "FAIL"
    lines: list[str] = [
        f"# Behavioral Eval — {report.task_slug}",
        "",
        f"**Tier**: {report.tier}",
        f"**Verdict**: {status}",
        f"**Score**: {report.score}%",
        "",
    ]

    if report.error:
        lines.extend(["## Error", "", report.error, ""])
        return "\n".join(lines)

    lines.extend(["## Artifacts", ""])
    for verdict in report.verdicts:
        marker = {
            "present": "[x]",
            "missing": "[ ]",
            "stale": "[~]",
            "skipped": "[-]",
        }[verdict.verdict]
        required_tag = "required" if verdict.required else "optional"
        suffix = f" — {verdict.detail}" if verdict.detail else ""
        lines.append(f"- {marker} `{verdict.path}` ({verdict.verdict}, {required_tag}){suffix}")
    lines.append("")
    return "\n".join(lines)
