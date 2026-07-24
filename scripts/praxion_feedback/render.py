"""The fixed §5.2 markdown-body renderer + the issue-label invariant.

`render_candidate` projects a stored candidate dict into the eight-heading
markdown structure that both the machine reporter and a human filing manually
in the browser share -- one artifact, both entry paths. `SECTION_HEADINGS`'s
exact text and order are load-bearing: a sibling template-drift guard checks
them against the shipped `ecosystem-defect.md` issue template.

Labels are NOT part of the rendered body -- they are a `gh issue create --label`
concern. `build_issue_labels` lives here as the single source of truth for the
label set so the invariant "the managed-project reporter never emits
`ecosystem-feedback`" (P5's maintainer arming gate) is structurally enforced at
one audited home rather than string-assembled at each call site.
"""

from __future__ import annotations

#: The §5.2 body schema headings, in fixed order. Load-bearing beyond this
#: module -- the shipped issue template's body must match these verbatim.
SECTION_HEADINGS = (
    "Fingerprint",
    "Plugin / Component",
    "Capture Provenance",
    "Expected vs Observed",
    "Reproduction Command",
    "Evidence Excerpt (sanitized)",
    "Environment",
    "Regression Status",
)

# Rendered for any field that is missing or None -- never the literal "None".
_PLACEHOLDER = "_not provided_"

#: Base labels the reporter applies on every filing. `ecosystem-feedback` is
#: deliberately absent: it is the maintainer's independent arming gate (P5) and
#: must never be emitted by the managed-project reporter.
_BASE_ISSUE_LABELS = ("bug", "auto-filed", "from-managed-project")

#: The one label the managed-project reporter must never emit.
RESERVED_MAINTAINER_LABEL = "ecosystem-feedback"


def _field(fields: dict, key: str) -> str:
    value = fields.get(key)
    if value is None:
        return _PLACEHOLDER
    return str(value)


def _section(heading: str, body: str) -> str:
    return f"## {heading}\n\n{body}\n"


def render_candidate(fields: dict) -> str:
    """Render a candidate dict into the fixed eight-heading §5.2 markdown body.

    Missing optional fields render a placeholder rather than raising or emitting
    the literal string "None".
    """
    provenance = (
        f"- Detected by: {_field(fields, 'detected_by')}\n"
        f"- Detection point: {_field(fields, 'detection_point')}\n"
        f"- Confidence: {_field(fields, 'confidence')}"
    )
    plugin_component = (
        f"- Category: {_field(fields, 'category')}\n- Artifact: {_field(fields, 'artifact_path')}"
    )
    expected_observed = (
        f"- Expected: {_field(fields, 'expected')}\n- Observed: {_field(fields, 'observed')}"
    )
    evidence = f"```\n{_field(fields, 'evidence_excerpt')}\n```"

    sections = (
        _section(SECTION_HEADINGS[0], _field(fields, "fingerprint")),
        _section(SECTION_HEADINGS[1], plugin_component),
        _section(SECTION_HEADINGS[2], provenance),
        _section(SECTION_HEADINGS[3], expected_observed),
        _section(SECTION_HEADINGS[4], _field(fields, "reproduction_command")),
        _section(SECTION_HEADINGS[5], evidence),
        _section(SECTION_HEADINGS[6], _field(fields, "environment")),
        _section(SECTION_HEADINGS[7], _field(fields, "regression_status")),
    )
    return "\n".join(sections)


def build_issue_labels(category: str) -> tuple[str, ...]:
    """Return the reporter's label set for `category`, never the reserved label.

    The base labels are a frozen tuple that does not contain the reserved
    maintainer label, and the only added label is a `category:<slug>` prefix, so
    the reserved bare label is structurally impossible to emit. The explicit
    guard makes that invariant fail loudly (surviving `python -O`) rather than
    silently should a caller ever pass a category named to inject it.
    """
    labels = (*_BASE_ISSUE_LABELS, f"category:{category}")
    if RESERVED_MAINTAINER_LABEL in labels:
        raise ValueError(
            f"{RESERVED_MAINTAINER_LABEL!r} is reserved for the maintainer arming gate"
        )
    return labels
