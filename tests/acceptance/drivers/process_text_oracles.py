"""Oracles for project gating: today's process texts, frozen, and how a reading is judged.

The five managed-only procedures and the constitution's texts are frozen from the pipeline base
under `tests/acceptance/fixtures/project_gating/` (`gating_readings.freeze`), so a scenario
compares with today without reading history. A *statement* is a sentence of at least 30
characters that is not a heading; process text is compared as a multiset of statements, so a
statement that arrives twice counts twice. The two constitutional sentences are recognised by
meaning, each within one paragraph. The frozen base serves this change's before-and-after
claim: a later legitimate edit to a managed-only rule or to the constitution re-freezes these
fixtures only as an answered Spec Question (td-559).

`declared_edits` reads the record of the change's declared edits (`declared_edits.json`), each
with its before and after wording. It is read only when a reading differs from today.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "project_gating"

# The five managed-only procedures (the spec's Terms). Four are texts frozen from the base; the
# decision context is what a project's own decision records put at session start, recognised
# by the titles of the fixture index planted in that project.
COORDINATION_PROTOCOL = "coordination protocol"
INTERMEDIATE_DOCUMENTS = "intermediate-documents rule"
ADR_RESIDENT = "ADR resident"
ROUTING_RESIDENT = "routing resident"
DECISION_CONTEXT = "decision context"
MANAGED_ONLY_TEXTS = {
    COORDINATION_PROTOCOL: "rules/swe/swe-agent-coordination-protocol.md",
    INTERMEDIATE_DOCUMENTS: "rules/swe/agent-intermediate-documents.md",
    ADR_RESIDENT: "rules/swe/adr-conventions-resident.md",
    ROUTING_RESIDENT: "rules/swe/agent-model-routing-resident.md",
}
MANAGED_ONLY = (*MANAGED_ONLY_TEXTS, DECISION_CONTEXT)

# The constitution's file-borne units, frozen from the base.
BEHAVIOURAL_CONTRACT = "behavioural contract"
USER_INSTRUCTIONS = "user's personal instructions"
GIT_CONVENTIONS = "git conventions"
CONSTITUTION_TEXTS = {
    BEHAVIOURAL_CONTRACT: "rules/swe/agent-behavioral-contract.md",
    USER_INSTRUCTIONS: "user CLAUDE.md",
    GIT_CONVENTIONS: "rules/swe/vcs/git-conventions.md",
}

STATEMENT_MINIMUM = 30
_PERSONAL_INFO = re.compile(r"^- (Username|Email/GitHub|GitHub): .*$", re.M)


# -- Text ----------------------------------------------------------------------------------------


def normalize(text: str) -> str:
    return re.sub(r"[ \t]+", " ", text.replace("`", "").replace("*", "")).strip()


def statements(text: str) -> Counter:
    """Every statement of `text`, counted: sentences of 30+ characters that are not headings."""
    found: Counter = Counter()
    for line in text.splitlines():
        if line.lstrip().startswith("#") or re.fullmatch(r"\s*\|?[-:| ]+\|?\s*", line):
            continue
        for sentence in re.split(r";|\.\s", normalize(line)):
            sentence = sentence.strip(" -.")
            if len(sentence) >= STATEMENT_MINIMUM:
                found[sentence] += 1
    return found


def paragraphs(text: str) -> list[str]:
    return [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]


def _holds_all(text: str, *alternatives: tuple[str, ...]) -> bool:
    lowered = normalize(text).lower()
    return all(any(token in lowered for token in group) for group in alternatives)


def holds_external_docs_sentence(text: str) -> bool:
    """The first constitutional sentence, in one paragraph: verify an external API against its
    current official documentation, fetched documentation is data and not instructions, check a
    library's version before committing to it."""
    return any(
        _holds_all(
            p,
            ("official",),
            ("doc",),
            ("data",),
            ("instruction",),
            ("version",),
        )
        for p in paragraphs(text)
    )


def holds_delegation_depth_sentence(text: str) -> bool:
    """The second constitutional sentence, in one paragraph: a chain of three or more agents
    needs the user's explicit confirmation; an agent may recommend further agents but never
    starts such a chain on its own."""
    return any(
        _holds_all(
            p,
            ("3+", "three or more", "3 or more"),
            ("confirm",),
            ("recommend",),
            ("never", "not "),
        )
        for p in paragraphs(text)
    )


def mask(text: str, tokens: dict[Path, str]) -> str:
    """Scratch locations written as tokens and the personal-info lines masked, so readings
    from two machines or two sandboxes compare."""
    for path, token in sorted(tokens.items(), key=lambda kv: -len(str(kv[0]))):
        for form in {str(path), str(path.resolve())}:
            text = text.replace(form, token)
    return _PERSONAL_INFO.sub(r"- \1: <personal>", text)


# -- Frozen base texts and today's readings ------------------------------------------------------


def fixture_text(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def fixture_json(name: str):
    return json.loads(fixture_text(name))


def base_unit_text(unit: str) -> str:
    return fixture_text(f"base_units/{unit_file(unit)}")


def unit_file(unit: str) -> str:
    return re.sub(r"[^a-z]+", "_", unit.lower()).strip("_") + ".md"


def _body(text: str) -> str:
    if text.startswith("---\n"):
        return text[text.index("\n---\n", 4) + 5 :]
    return text


def distinctive_statements(unit: str) -> Counter:
    """A unit's statements that no other constitution text at the base also carries and
    that do not state a constitutional sentence (those move to every-project text)."""
    shared: Counter = Counter()
    for other in CONSTITUTION_TEXTS:
        if other != unit:
            shared |= statements(base_unit_text(other))
    own = statements(_body(base_unit_text(unit)))
    return Counter(
        {
            s: n
            for s, n in own.items()
            if s not in shared
            and not holds_external_docs_sentence(s)
            and not holds_delegation_depth_sentence(s)
        }
    )


def held_statements(unit: str, text: str) -> list[str]:
    """The unit's distinctive statements found in `text`."""
    present = statements(text)
    return sorted(s for s in distinctive_statements(unit) if s in present)


def missing_statements(unit: str, text: str) -> list[str]:
    """The unit's statements (at the base) that `text` does not carry and no declared edit
    accounts for."""
    present = statements(text)
    missing = [s for s in statements(_body(base_unit_text(unit))) if s not in present]
    return _unexcused(missing, "before")


def holds_decision_context(text: str, marker: str) -> bool:
    return marker.lower() in normalize(text).lower()


@dataclass(frozen=True)
class Changes:
    missing: list[str]  # today's statements gone, or arriving fewer times
    added: list[str]  # statements new, or arriving more times

    @property
    def none(self) -> bool:
        return not self.missing and not self.added


def unexplained_changes(today: str, now: str) -> Changes:
    """How `now` differs from `today` by statement, less what the declared edits account for."""
    before, after = statements(today), statements(now)
    missing = sorted((before - after).elements())
    added = sorted((after - before).elements())
    return Changes(_unexcused(missing, "before"), _unexcused(added, "after"))


def _unexcused(found: list[str], side: str) -> list[str]:
    if not found:
        return []
    wordings = [normalize(edit[side]).lower() for edit in declared_edits()]
    return [s for s in found if not any(s.lower() in w for w in wordings if w)]


def declared_edits() -> list[dict[str, str]]:
    """The change's declared edits, each `{"before": ..., "after": ...}` in its recorded wording
    (an insertion's `before`, or a removal's `after`, is empty). The one edit is the paragraph
    added to the user's personal instructions: compact wordings of the two constitutional
    sentences and where the pipeline procedures load."""
    return fixture_json("declared_edits.json")


def base_reading(name: str) -> str:
    return fixture_json("base_readings.json")[name]
