"""Tests for the Phoenix trace reader — monkey-patch Phoenix to keep tests offline."""

from __future__ import annotations

import sys

import pandas as pd
import pytest

from praxion_evals.regression.trace_reader import (
    read_current_summary,
    summarize_dataframe,
)


def test_summarize_empty_dataframe_notes_no_spans():
    summary = summarize_dataframe("demo", pd.DataFrame())
    assert summary.span_count == 0
    assert "no-spans-found" in summary.notes


def test_summarize_counts_spans_and_tool_calls():
    df = pd.DataFrame(
        [
            {"span_kind": "CHAIN", "name": "root"},
            {"span_kind": "TOOL", "name": "Read"},
            {"span_kind": "TOOL", "name": "Grep"},
            {"span_kind": "AGENT", "name": "researcher"},
        ]
    )
    summary = summarize_dataframe("demo", df)
    assert summary.span_count == 4
    assert summary.tool_call_count == 2
    assert summary.agent_count == 1


def test_read_current_summary_no_phoenix_installed(monkeypatch: pytest.MonkeyPatch):
    """When phoenix is unimportable, the reader returns a clean TraceSummary."""
    import importlib

    monkeypatch.delitem(sys.modules, "phoenix", raising=False)

    real_import_module = importlib.import_module

    def _fake_import_module(name: str, *args: object, **kwargs: object):
        if name == "phoenix":
            raise ImportError("phoenix not installed in this test env")
        return real_import_module(name, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(importlib, "import_module", _fake_import_module)

    summary = read_current_summary("demo")
    assert summary.span_count == 0
    assert any("phoenix-not-installed" in n for n in summary.notes)
