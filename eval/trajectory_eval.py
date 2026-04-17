#!/usr/bin/env python3
"""Evaluate agent tool-calling quality against Phoenix trace data.

Pulls TOOL spans from a Phoenix project and evaluates them using the
arize-phoenix-evals library's tool evaluators. Results are logged back
as span annotations visible in the Phoenix UI.

Requirements: pip install arize-phoenix arize-phoenix-evals openai
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from typing import Any


def _count_label(results: Any, score_column: str, label: str) -> int:
    """Count rows in an evaluate_dataframe result whose Score column has the given label.

    evaluate_dataframe adds a `{score.name}_score` column holding JSON-serialized Score
    objects (per the 3.x docstring). This parses each cell defensively — handling dicts,
    JSON strings, and Score-like objects with a .label attribute — and tallies matches.
    """
    if score_column not in results.columns:
        return 0
    count = 0
    for cell in results[score_column]:
        if cell is None:
            continue
        if isinstance(cell, str):
            try:
                cell = json.loads(cell)
            except (ValueError, TypeError):
                continue
        if isinstance(cell, dict):
            if cell.get("label") == label:
                count += 1
        elif getattr(cell, "label", None) == label:
            count += 1
    return count


def _parse_since(since: str) -> datetime:
    """Parse a relative duration like '24h', '7d', '30m' into a UTC datetime."""
    unit = since[-1]
    amount = int(since[:-1])
    match unit:
        case "h":
            delta = timedelta(hours=amount)
        case "d":
            delta = timedelta(days=amount)
        case "m":
            delta = timedelta(minutes=amount)
        case _:
            raise ValueError(
                f"Unknown time unit '{unit}'. Use h (hours), d (days), or m (minutes)."
            )
    return datetime.now(timezone.utc) - delta


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Evaluate agent tool-calling quality against Phoenix traces.",
        epilog="Example: python trajectory_eval.py --project my-api --judge openai/gpt-4o --since 24h",
    )
    parser.add_argument(
        "--project", required=True, help="Phoenix project name (e.g., 'my-api', 'praxion')"
    )
    parser.add_argument(
        "--judge", default="openai/gpt-4o", help="LLM judge model (default: openai/gpt-4o)"
    )
    parser.add_argument("--trace-id", help="Evaluate a specific trace ID only")
    parser.add_argument(
        "--since", help="Evaluate traces from the last N hours/days (e.g., '24h', '7d')"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Show what would be evaluated without running"
    )
    args = parser.parse_args()

    # Lazy imports — these are heavy deps
    try:
        import phoenix as px
    except ImportError:
        print("Error: arize-phoenix not installed. Run: pip install arize-phoenix", file=sys.stderr)
        return 1

    try:
        from phoenix.evals import (
            LLM,
            bind_evaluator,
            create_classifier,
            evaluate_dataframe,
        )
    except ImportError:
        print(
            "Error: arize-phoenix-evals>=3.0 not installed. "
            "Run: pip install 'arize-phoenix-evals>=3.0'",
            file=sys.stderr,
        )
        return 1

    # Connect to Phoenix
    client = px.Client()

    # Pull spans
    print(f"Fetching TOOL spans from project '{args.project}'...")
    try:
        spans_df = client.get_spans_dataframe(project_name=args.project)
    except Exception as exc:
        print(f"Error fetching spans: {exc}", file=sys.stderr)
        print("Is Phoenix running? Check: phoenix-ctl status", file=sys.stderr)
        return 1

    if spans_df is None or spans_df.empty:
        print("No spans found for this project.")
        return 0

    # Filter to TOOL spans
    if "span_kind" in spans_df.columns:
        tool_spans = spans_df[spans_df["span_kind"] == "TOOL"]
    elif "attributes.openinference.span.kind" in spans_df.columns:
        tool_spans = spans_df[spans_df["attributes.openinference.span.kind"] == "TOOL"]
    else:
        print("Warning: Could not identify TOOL spans by kind. Using all spans.")
        tool_spans = spans_df

    # Filter by trace ID if specified
    if args.trace_id and "context.trace_id" in tool_spans.columns:
        tool_spans = tool_spans[tool_spans["context.trace_id"] == args.trace_id]

    # Filter by time if specified
    if args.since and "start_time" in tool_spans.columns:
        cutoff = _parse_since(args.since)
        tool_spans = tool_spans[tool_spans["start_time"] >= cutoff]

    print(f"Found {len(tool_spans)} TOOL spans.")

    if tool_spans.empty:
        print("No TOOL spans to evaluate.")
        return 0

    if args.dry_run:
        print("\n[DRY RUN] Would evaluate these spans:")
        for _, span in tool_spans.head(10).iterrows():
            name = span.get("name", "?")
            trace_id = span.get("context.trace_id", "?")
            print(f"  - {name} (trace: {trace_id})")
        if len(tool_spans) > 10:
            print(f"  ... and {len(tool_spans) - 10} more")
        return 0

    # Run evaluation — 3.x uses a unified LLM wrapper with first-class multi-provider support
    provider, model_name = args.judge.split("/", 1)
    print(f"\nEvaluating with judge: {args.judge}")

    try:
        judge_llm = LLM(provider=provider, model=model_name)
    except Exception as exc:
        print(
            f"Error: Could not initialize LLM({provider=}, {model_name=}): {exc}", file=sys.stderr
        )
        return 1

    # ClassificationEvaluator infers template variables from the prompt string, so dotted
    # DataFrame columns need input_mapping to translate to flat placeholder names.
    tool_selection = create_classifier(
        name="tool_selection",
        llm=judge_llm,
        prompt_template=(
            "Was the correct tool selected for the task? Tool: {tool_name}, Input: {tool_input}"
        ),
        choices=["correct", "incorrect", "unclear"],
    )
    tool_selection = bind_evaluator(
        evaluator=tool_selection,
        input_mapping={"tool_name": "name", "tool_input": "attributes.input.value"},
    )

    print("Running ToolSelection evaluation...")
    try:
        results = evaluate_dataframe(dataframe=tool_spans, evaluators=[tool_selection])
    except Exception as exc:
        print(f"  ToolSelection evaluation failed: {exc}", file=sys.stderr)
        return 1

    correct = _count_label(results, score_column="tool_selection_score", label="correct")
    total = len(results)
    if total:
        print(f"  ToolSelection: {correct}/{total} correct ({correct / total * 100:.0f}%)")

    print("\nEvaluation complete. Results are available in the Phoenix UI.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
