"""Tests for the readiness educational + recommendation surfaces.

Covers the additive 1.2.0 fields:

* every criterion carries non-empty ``explanation`` and ``remediation`` copy,
* ``PILLAR_DOCS`` covers all nine pillars,
* the collector embeds ``explanation``/``remediation``/``remediation_source``,
* the scorer attaches per-pillar (and manageability) ``explanation``,
* the judge verdict schema, prompt, and parser carry ``recommendation``.

No network calls — judge coverage exercises pure schema/prompt/parse helpers.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.project_metrics.collectors.base import CollectionContext
from scripts.project_metrics.collectors.readiness import judge, score
from scripts.project_metrics.collectors.readiness.criteria import (
    CRITERIA,
    FACTORY_PILLARS,
    MANAGEABILITY_PILLAR,
    PILLAR_DOCS,
)
from scripts.project_metrics.collectors.readiness_collector import ReadinessCollector

# ---------------------------------------------------------------------------
# Criteria content — every criterion must teach and advise.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("criterion", CRITERIA, ids=lambda c: c.id)
def test_every_criterion_has_explanation(criterion) -> None:
    assert criterion.explanation.strip(), f"{criterion.id} missing explanation"


@pytest.mark.parametrize("criterion", CRITERIA, ids=lambda c: c.id)
def test_every_criterion_has_remediation(criterion) -> None:
    assert criterion.remediation.strip(), f"{criterion.id} missing remediation"


# ---------------------------------------------------------------------------
# Pillar docs — every pillar (8 Factory + manageability) is documented.
# ---------------------------------------------------------------------------


def test_pillar_docs_cover_all_pillars() -> None:
    expected = set(FACTORY_PILLARS) | {MANAGEABILITY_PILLAR}
    assert set(PILLAR_DOCS) == expected


@pytest.mark.parametrize("pillar_id", sorted(set(FACTORY_PILLARS) | {MANAGEABILITY_PILLAR}))
def test_pillar_doc_is_non_empty(pillar_id: str) -> None:
    assert PILLAR_DOCS[pillar_id].strip()


# ---------------------------------------------------------------------------
# Collector embeds the educational + remediation fields per criterion.
# ---------------------------------------------------------------------------


def test_collector_embeds_educational_fields(tmp_path: Path) -> None:
    collector = ReadinessCollector(repo_root=tmp_path)
    ctx = CollectionContext(repo_root=str(tmp_path), window_days=90, git_sha="0" * 40)
    data = collector.collect(ctx).data

    for crit in data["criteria"]:
        assert "explanation" in crit
        assert crit["explanation"].strip()
        assert "remediation" in crit
        assert crit["remediation"].strip()
        assert crit["remediation_source"] == "static"


def test_scorer_attaches_pillar_explanation(tmp_path: Path) -> None:
    collector = ReadinessCollector(repo_root=tmp_path)
    ctx = CollectionContext(repo_root=str(tmp_path), window_days=90, git_sha="0" * 40)
    data = collector.collect(ctx).data

    for pillar in data["pillars"]:
        assert pillar["explanation"] == PILLAR_DOCS[pillar["id"]]
    assert data["manageability"]["explanation"] == PILLAR_DOCS[MANAGEABILITY_PILLAR]


def test_recompute_preserves_pillar_explanation(tmp_path: Path) -> None:
    collector = ReadinessCollector(repo_root=tmp_path)
    ctx = CollectionContext(repo_root=str(tmp_path), window_days=90, git_sha="0" * 40)
    data = collector.collect(ctx).data
    score.recompute(data)
    for pillar in data["pillars"]:
        assert pillar["explanation"] == PILLAR_DOCS[pillar["id"]]


# ---------------------------------------------------------------------------
# Judge — recommendation lives in the schema, the prompt, and the parser.
# ---------------------------------------------------------------------------


def test_verdict_schema_includes_recommendation() -> None:
    props = judge._VERDICT_SCHEMA["properties"]
    assert "recommendation" in props
    # recommendation is optional — only passed/rationale are required.
    assert "recommendation" not in judge._VERDICT_SCHEMA["required"]


def test_prompt_requests_recommendation_on_failure() -> None:
    prompt = judge._build_prompt(
        {"id": "c.docs.readme_quality", "rationale": "clear README"}, "artifact", None
    )
    assert "recommendation" in prompt.lower()


def test_parse_verdict_extracts_recommendation() -> None:
    import json as _json

    body = _json.dumps(
        {
            "content": [
                {
                    "type": "tool_use",
                    "name": "verdict",
                    "input": {
                        "passed": False,
                        "rationale": "thin",
                        "recommendation": "Add a usage example",
                    },
                }
            ]
        }
    ).encode("utf-8")
    verdict = judge._parse_verdict(body)
    assert verdict["recommendation"] == "Add a usage example"


def test_parse_verdict_recommendation_defaults_empty() -> None:
    import json as _json

    body = _json.dumps(
        {
            "content": [
                {
                    "type": "tool_use",
                    "name": "verdict",
                    "input": {"passed": True, "rationale": "good"},
                }
            ]
        }
    ).encode("utf-8")
    verdict = judge._parse_verdict(body)
    assert verdict["recommendation"] == ""
