"""Driver for the texts a reader follows: skills, agent prompts, rules, commands, docs.

These texts are the system's surface for a reader (human or agent), so the scenarios read
them the way a reader does: by file, by section heading, and by sentence. A *sentence* here
is a stretch of text bounded by a line end, a semicolon, or a full stop followed by a
space, so a table row is one sentence; a *clause* is also bounded by parentheses. Before
matching, emphasis and code marks (`*` and backticks) are dropped and runs of spaces fold
to one, so `**review**: force` and `review: force` read alike.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]

COORDINATION_PROTOCOL = "rules/swe/swe-agent-coordination-protocol.md"
COORDINATION_DETAILS = "skills/software-planning/references/coordination-details.md"
PIPELINE_DETAILS = "skills/software-planning/references/agent-pipeline-details.md"
DOCUMENT_TEMPLATES = "skills/software-planning/references/document-templates.md"
INTRA_STEP_REVIEW = "skills/software-planning/references/intra-step-review.md"
SOFTWARE_PLANNING_SKILL = "skills/software-planning/SKILL.md"
PLANNER_PROMPT = "agents/implementation-planner.md"
IMPLEMENTER_PROMPT = "agents/implementer.md"
RESUME_PIPELINE = "commands/resume-pipeline.md"
STEP_LOOP_SKILL = "skills/step-loop/SKILL.md"

SENTENCE_BREAK = r"\n|;|\.\s"
CLAUSE_BREAK = SENTENCE_BREAK + r"|\(|\)"
_HEADING = re.compile(r"^(#{1,6})\s+(.*)$")


def path_of(relative: str) -> Path:
    return REPO_ROOT / relative


def read(relative: str) -> str:
    path = path_of(relative)
    if not path.is_file():
        raise AssertionError(f"{relative} does not exist")
    return path.read_text(encoding="utf-8")


def normalize(text: str) -> str:
    text = text.replace("`", "").replace("*", "")
    return re.sub(r"[ \t]+", " ", text)


def sentences(text: str, breaks: str = SENTENCE_BREAK) -> list[str]:
    return [s.strip() for s in re.split(breaks, normalize(text)) if s.strip()]


def sentences_matching(text: str, *patterns: str, breaks: str = SENTENCE_BREAK) -> list[str]:
    """Sentences (or clauses, with `breaks=CLAUSE_BREAK`) in which every pattern
    (case-insensitive regex) is found."""
    return [
        s for s in sentences(text, breaks) if all(re.search(p, s, re.IGNORECASE) for p in patterns)
    ]


def section(text: str, heading_pattern: str) -> str:
    """The body under the first heading matching `heading_pattern`, to the next heading
    of the same or a higher level."""
    lines = text.splitlines()
    for index, line in enumerate(lines):
        match = _HEADING.match(line)
        if match and re.search(heading_pattern, match.group(2), re.IGNORECASE):
            level = len(match.group(1))
            body = []
            for later in lines[index + 1 :]:
                deeper = _HEADING.match(later)
                if deeper and len(deeper.group(1)) <= level:
                    break
                body.append(later)
            return "\n".join(body)
    raise AssertionError(f"no heading matches {heading_pattern!r}")


def frontmatter(text: str) -> dict:
    if not text.startswith("---"):
        raise AssertionError("the file opens with no frontmatter block")
    block = text.split("---", 2)[1]
    loaded = yaml.safe_load(block)
    return loaded if isinstance(loaded, dict) else {}


def body(text: str) -> str:
    return text.split("---", 2)[2] if text.startswith("---") else text


def paragraphs(text: str) -> list[str]:
    return [p for p in re.split(r"\n\s*\n", text) if p.strip()]


def lines_containing(text: str, pattern: str) -> list[str]:
    return [line for line in text.splitlines() if re.search(pattern, line, re.IGNORECASE)]
