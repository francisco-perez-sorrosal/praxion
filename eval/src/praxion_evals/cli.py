"""Praxion evals CLI — thin argparse dispatch to tier entrypoints.

Subcommands:
    list          Default — print the tier registry status table.
    behavioral    Run Tier 1 behavioral eval against a task slug.
    regression    Run Tier 1 regression eval against a baseline JSON.
    judge         Run a specific LLM judge (openai is Tier 1, anthropic is stub).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from praxion_evals import tiers as tier_registry
from praxion_evals.behavioral import PipelineTier, render_markdown, run_behavioral
from praxion_evals.regression import run_regression


def _cmd_list(_: argparse.Namespace) -> int:
    print("Praxion evals — available tiers")
    print()
    print(tier_registry.format_status_table())
    return 0


def _cmd_behavioral(args: argparse.Namespace) -> int:
    tier_value = args.tier
    try:
        tier = PipelineTier(tier_value)
    except ValueError:
        print(f"Unknown tier '{tier_value}'. Choose: lightweight|standard|full", file=sys.stderr)
        return 2

    repo_root = Path(args.repo_root) if args.repo_root else Path.cwd()
    report = run_behavioral(task_slug=args.task_slug, repo_root=repo_root, tier=tier)
    print(render_markdown(report))
    return 0 if report.passed else 1


def _cmd_regression(args: argparse.Namespace) -> int:
    baseline_path = Path(args.baseline)
    if not baseline_path.exists():
        print(f"Baseline not found: {baseline_path}", file=sys.stderr)
        return 2

    result = run_regression(baseline_path)
    if not result.has_drift:
        print(f"No drift detected for task_slug={result.task_slug}.")
        return 0

    print(f"Drift findings for task_slug={result.task_slug}:")
    for finding in result.findings:
        print(f"- {finding}")
    return 1


def _cmd_judge(args: argparse.Namespace) -> int:
    if args.provider == "anthropic":
        from praxion_evals.judges import anthropic

        return anthropic.main()
    from praxion_evals.judges import openai

    return openai.main()


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="praxion-evals",
        description="Out-of-band quality evals (Tier 1: behavioral + regression).",
    )
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("list", help="Show tier registry and status")

    p_behavioral = sub.add_parser("behavioral", help="Run Tier 1 behavioral eval")
    p_behavioral.add_argument("--task-slug", required=True)
    p_behavioral.add_argument(
        "--tier",
        default="standard",
        choices=[t.value for t in PipelineTier],
        help="Pipeline tier governing expected artifacts.",
    )
    p_behavioral.add_argument(
        "--repo-root",
        default=None,
        help="Repository root (defaults to CWD).",
    )

    p_regression = sub.add_parser("regression", help="Run Tier 1 regression eval")
    p_regression.add_argument("--baseline", required=True, help="Path to baseline JSON.")

    p_judge = sub.add_parser("judge", help="Invoke an LLM judge over Phoenix traces")
    p_judge.add_argument(
        "--provider",
        default="openai",
        choices=("openai", "anthropic"),
        help="Judge provider (anthropic is a Tier 2 stub).",
    )

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    dispatch = {
        None: _cmd_list,
        "list": _cmd_list,
        "behavioral": _cmd_behavioral,
        "regression": _cmd_regression,
        "judge": _cmd_judge,
    }
    handler = dispatch.get(args.command)
    if handler is None:
        parser.print_help()
        return 2
    return handler(args)


if __name__ == "__main__":
    sys.exit(main())
