#!/usr/bin/env python3
"""Evaluate agent tool-calling quality against Phoenix trace data.

Pulls TOOL spans from a Phoenix project and evaluates them using the
arize-phoenix-evals library's tool evaluators. Results are logged back
as span annotations visible in the Phoenix UI.

Requirements: pip install arize-phoenix arize-phoenix-evals openai
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timedelta, timezone


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
            OpenAIModel,
            llm_classify,
        )
    except ImportError:
        print(
            "Error: arize-phoenix-evals not installed. Run: pip install arize-phoenix-evals",
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

    # Run evaluation
    provider, model_name = args.judge.split("/", 1)
    print(f"\nEvaluating with judge: {args.judge}")

    if provider == "openai":
        judge_model = OpenAIModel(model=model_name)
    else:
        print(f"Warning: Provider '{provider}' not directly supported. Trying OpenAI-compatible.")
        judge_model = OpenAIModel(model=model_name)

    # Tool Selection evaluation
    print("Running ToolSelection evaluation...")
    try:
        selection_results = llm_classify(
            dataframe=tool_spans,
            model=judge_model,
            template="Was the correct tool selected for the task? "
            "Tool: {name}, Input: {attributes.input.value}",
            rails=["correct", "incorrect", "unclear"],
            provide_explanation=True,
        )
        correct = (selection_results["label"] == "correct").sum()
        total = len(selection_results)
        print(f"  ToolSelection: {correct}/{total} correct ({correct / total * 100:.0f}%)")
    except Exception as exc:
        print(f"  ToolSelection evaluation failed: {exc}", file=sys.stderr)

    print("\nEvaluation complete. Results are available in the Phoenix UI.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
