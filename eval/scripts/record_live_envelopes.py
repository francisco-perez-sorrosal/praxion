#!/usr/bin/env python3
"""Record verbatim ``claude -p`` stream-json envelopes for the live runner's tests.

Runs one real, sandboxed headless session per shape and writes its stdout
byte-for-byte to ``<output-dir>/<shape>.stream.jsonl``. The shapes are the four
single-case seeded scenarios plus three infrastructure-error shapes (a budget
stop, a rejected credential, an unknown CLI flag), so the parser and capture
functions are tested against what the CLI really emits, not hand-written JSON.

**Every non-dry run spends API money** (roughly $4-6 for all seven shapes).
Never invoked by pytest, hooks or CI. Run it deliberately, from the package:

    cd eval && uv run python scripts/record_live_envelopes.py --output-dir DIR
    cd eval && uv run python scripts/record_live_envelopes.py --dry-run

Sessions use the same isolation as the runner: a copy of the target's HEAD
passed via ``--plugin-dir``, a per-session sandbox HOME populated by the copy's
own installer, and an allowlisted environment. Before any file is written its
content is scanned for ``sk-ant-``-shaped secrets; a hit refuses that write.
Fixture repos here are minimal stand-ins for the runner's own fixture trees —
they only need to elicit each shape once.
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

if TYPE_CHECKING:
    from praxion_evals.live.results import ErrorKind
    from praxion_evals.live.session import PermissionMode, SessionEnvelope, SessionRun, SessionSpec

CREDENTIAL_KEYS = ("ANTHROPIC_API_KEY", "CLAUDE_CODE_OAUTH_TOKEN", "ANTHROPIC_AUTH_TOKEN")
SECRET_SHAPE = re.compile(r"sk-ant-[A-Za-z0-9_\-]*")
SCENARIO_FIXTURES = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "scenarios"
EFFORT = "medium"
ERROR_SHAPE_MODEL = "sonnet"
BUDGET_STOP_USD = 0.01
# Shapes that fail before any API call still reserve a budget; keep it nominal.
NO_SPEND_BUDGET_USD = 0.01
REJECTED_CREDENTIAL = "rejected-credential-for-envelope-recording"
UNKNOWN_FLAG = "--no-such-flag-for-envelope-recording"
FIXTURE_USER_NAME = "scenario"
FIXTURE_USER_EMAIL = "scenario@example.invalid"

ModelRole = Literal["scenario", "error"]
Seeded = Mapping[str, Any]
CLEAN: frozenset[ErrorKind | None] = frozenset({None})


@dataclass(frozen=True)
class Shape:
    name: str
    seeded_file: str | None
    build_fixture: Callable[[Path, Seeded], None]
    prompt: Callable[[Seeded], str]
    permission_mode: PermissionMode
    max_budget_usd: float
    model_role: ModelRole
    allowed_tools: tuple[str, ...] = ()
    forward_subagent_text: bool = False
    extra_argv: tuple[str, ...] = ()
    env_overrides: Mapping[str, str | None] = field(default_factory=dict)
    # The outcome that makes this shape's envelope worth keeping: a clean
    # session for scenarios, the named infrastructure error for error shapes.
    expected_errors: frozenset[ErrorKind | None] = CLEAN


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    shapes = [SHAPES[name] for name in args.shapes]
    if not args.dry_run and not any(os.environ.get(key) for key in CREDENTIAL_KEYS):
        print(f"No credential in the environment; set one of {', '.join(CREDENTIAL_KEYS)}.")
        return 2
    target = Path(_git(Path(args.target), "rev-parse", "--show-toplevel").strip())
    if args.dry_run:
        _print_plan(shapes, target, args.model)
        return 0
    return _record(shapes, target, args)


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Record verbatim claude -p envelopes (spends money unless --dry-run).",
        epilog=f"Shapes: {', '.join(SHAPES)}.",
    )
    parser.add_argument("--output-dir", type=Path, help="Where the .stream.jsonl files go.")
    parser.add_argument("--target", default=".", help="Checkout whose HEAD is the context layer.")
    parser.add_argument("--model", default="opus", help="Model for scenario shapes.")
    parser.add_argument(
        "--shapes", nargs="+", choices=list(SHAPES), default=list(SHAPES), metavar="SHAPE"
    )
    parser.add_argument("--keep-sandbox", action="store_true", help="Keep the run directory.")
    parser.add_argument(
        "--max-total-usd",
        type=float,
        default=None,
        help="Run-level spend cap; a shape whose budget would cross it is not run (default: 10).",
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Print argv + env keys; spawn nothing."
    )
    args = parser.parse_args(argv)
    if not args.dry_run and args.output_dir is None:
        parser.error("--output-dir is required unless --dry-run")
    if args.max_total_usd is None:
        # Imported after parsing so `--help` works without the package installed.
        from praxion_evals.live.spend import RECORDER_SPEND_CAP_USD

        args.max_total_usd = RECORDER_SPEND_CAP_USD
    return args


# ---------------------------------------------------------------------------
# Recording (the only paid path)
# ---------------------------------------------------------------------------


def _record(shapes: list[Shape], target: Path, args: argparse.Namespace) -> int:
    from praxion_evals.live.materialize import materialize_head
    from praxion_evals.live.results import Errored
    from praxion_evals.live.spend import SpendLedger

    args.output_dir.mkdir(parents=True, exist_ok=True)
    credentials = _credential_values(os.environ)
    ledger = SpendLedger(cap_usd=args.max_total_usd)
    run_root = Path(tempfile.mkdtemp(prefix="praxion-live-record-"))
    failures = 0
    try:
        copy = materialize_head(target, run_root / "copy")
        for shape in shapes:
            destination = args.output_dir / f"{shape.name}.stream.jsonl"
            if destination.exists():
                print(f"[{shape.name}] refused: {destination} exists (delete it to re-record)")
                failures += 1
                continue
            admitted = ledger.reserve(shape.max_budget_usd)
            if isinstance(admitted, Errored):
                print(f"[{shape.name}] not run: {admitted.detail}")
                failures += 1
                continue
            cost, written = _record_one(shape, copy.root, run_root / shape.name, args, credentials)
            ledger = admitted.settle(shape.max_budget_usd, cost)
            failures += not written
            print(f"spent so far: ${ledger.spent_usd:.4f} of ${ledger.cap_usd:.2f}", flush=True)
    finally:
        if args.keep_sandbox:
            print(f"sandbox kept: {run_root}")
        else:
            shutil.rmtree(run_root, ignore_errors=True)
    return 1 if failures else 0


def _record_one(
    shape: Shape,
    copy_root: Path,
    session_root: Path,
    args: argparse.Namespace,
    credentials: Mapping[str, str],
) -> tuple[float | None, bool]:
    """Run one shape; return its reported cost and whether its envelope was written."""
    from praxion_evals.live.materialize import install_user_scope
    from praxion_evals.live.session import build_argv, parse_stream, run_argv

    seeded = _load_seeded(shape)
    install_user_scope(copy_root, session_root)
    fixture = session_root / "fixture"
    shape.build_fixture(fixture, seeded)
    spec = _spec(shape, seeded, copy_root, fixture, args.model)
    print(f"[{shape.name}] running ({spec.model}, budget ${spec.max_budget_usd})", flush=True)
    run = run_argv(
        [*build_argv(spec), *shape.extra_argv],
        cwd=fixture,
        env=_session_env(shape, session_root),
        timeout_s=spec.timeout_s,
    )
    envelope = parse_stream(run.stdout)
    result = envelope.final_result
    cost = result.total_cost_usd if result else None
    stderr = _redact(run.stderr.strip()[:300], credentials)
    print(
        f"[{shape.name}] exit={run.exit_code} results={envelope.result_count} "
        f"subtype={result.subtype if result else None} cost={cost} stderr={stderr!r}"
    )
    refusal = _write_refusal(shape, envelope, run, copy_root) or _leaked_secret(
        run.stdout, credentials
    )
    if refusal is not None:
        print(f"[{shape.name}] refused, nothing written: {refusal}")
        return cost, False
    destination = args.output_dir / f"{shape.name}.stream.jsonl"
    destination.write_text(run.stdout, encoding="utf-8")
    print(f"[{shape.name}] wrote {destination}")
    return cost, True


def _write_refusal(
    shape: Shape, envelope: SessionEnvelope, run: SessionRun, copy_root: Path
) -> str | None:
    """Why this session's envelope must not become a fixture, or ``None``.

    A fixture is kept only when the session ended the way its shape exists to
    capture, and — whenever the session reached ``init`` or ended cleanly —
    only when isolation is proven. A leaked session must never be pinned as
    an isolated one.
    """
    from praxion_evals.live.session import classify, isolation_breach

    kind = classify(envelope, run.exit_code, run.timed_out)
    if kind not in shape.expected_errors:
        expected = sorted(str(k) for k in shape.expected_errors)
        return f"session ended as {kind or 'clean'}, this shape keeps only {expected}"
    if envelope.init is None and kind is not None:
        return None  # failed before the session started: there is no layer to isolate
    breach = isolation_breach(envelope, copy_root)
    return None if breach is None else f"isolation_breach: {breach}"


def _credential_values(environ: Mapping[str, str]) -> dict[str, str]:
    return {key: environ[key] for key in CREDENTIAL_KEYS if environ.get(key)}


def _leaked_secret(text: str, credentials: Mapping[str, str]) -> str | None:
    """Name (never quote) the secret a would-be fixture contains, or ``None``."""
    if SECRET_SHAPE.search(text):
        return "output contains an sk-ant- shaped substring"
    for name, value in credentials.items():
        if value and value in text:
            return f"output contains the value of {name}"
    return None


def _redact(text: str, credentials: Mapping[str, str]) -> str:
    for name, value in credentials.items():
        if value:
            text = text.replace(value, f"<{name}>")
    return SECRET_SHAPE.sub("<sk-ant-redacted>", text)


def _spec(shape: Shape, seeded: Seeded, copy_root: Path, cwd: Path, model: str) -> SessionSpec:
    from praxion_evals.live.session import SessionSpec

    return SessionSpec(
        prompt=shape.prompt(seeded),
        model=model if shape.model_role == "scenario" else ERROR_SHAPE_MODEL,
        effort=EFFORT,
        plugin_dir=copy_root,
        cwd=cwd,
        permission_mode=shape.permission_mode,
        max_budget_usd=shape.max_budget_usd,
        allowed_tools=shape.allowed_tools,
        forward_subagent_text=shape.forward_subagent_text,
    )


def _session_env(shape: Shape, session_root: Path) -> dict[str, str]:
    from praxion_evals.live.session import build_env

    env = build_env(session_root, os.environ)
    for key, value in shape.env_overrides.items():
        if value is None:
            env.pop(key, None)
        else:
            env[key] = value
    return env


def _print_plan(shapes: list[Shape], target: Path, model: str) -> None:
    from praxion_evals.live.session import build_argv, build_env

    run_root = Path(tempfile.gettempdir()) / "praxion-live-record-<run>"
    copy_root = run_root / "copy"
    print(f"target: {target} (HEAD, materialized into {copy_root})")
    for shape in shapes:
        session_root = run_root / shape.name
        spec = _spec(shape, _load_seeded(shape), copy_root, session_root / "fixture", model)
        argv = [*build_argv(spec), *shape.extra_argv]
        env_keys = sorted(
            {*build_env(session_root, os.environ), *shape.env_overrides}
            - {k for k, v in shape.env_overrides.items() if v is None}
        )
        print(f"\n[{shape.name}]\n  argv: {argv}\n  env keys: {env_keys}")


def _load_seeded(shape: Shape) -> Seeded:
    if shape.seeded_file is None:
        return {}
    import yaml

    return yaml.safe_load((SCENARIO_FIXTURES / shape.seeded_file).read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Fixture repos (minimal stand-ins that elicit each shape)
# ---------------------------------------------------------------------------


def _write_tree(root: Path, files: Mapping[str, str]) -> None:
    for relpath, content in files.items():
        path = root / relpath
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")


def _init_repo(root: Path, files: Mapping[str, str]) -> None:
    """A fixture repo whose own config carries the identity.

    The session's sandbox HOME has no git identity, and the session must be
    able to commit the way an operator's session can — so the identity lives
    in the repo, never in HOME.
    """
    root.mkdir(parents=True)
    _git(root, "init", "-q", "-b", "main")
    _git(root, "config", "user.name", FIXTURE_USER_NAME)
    _git(root, "config", "user.email", FIXTURE_USER_EMAIL)
    _write_tree(root, {"README.md": "# fixture\n", **files})
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "baseline")


def _ui_step_fixture(root: Path, seeded: Seeded) -> None:
    _init_repo(
        root,
        {
            ".gitignore": ".ai-work/\n",
            "dashboard_app/src/styles/tokens.css": ":root {\n  --space-2: 8px;\n  --radius-1: 4px;\n}\n",
            "dashboard_app/src/components/AdrList.tsx": (
                "export function AdrList({ adrs }: { adrs: { id: string; title: string }[] }) {\n"
                "  return <ul>{adrs.map((a) => <li key={a.id}>{a.title}</li>)}</ul>;\n}\n"
            ),
        },
    )
    step = f"## Current step\n\n{seeded['seeded_step']}"
    _write_tree(
        root,
        {
            ".ai-work/ui-step/IMPLEMENTATION_PLAN.md": f"# Plan: ADR list loading state\n\n{step}",
            ".ai-work/ui-step/WIP.md": f"# WIP\n\n{step}\nStatus: TODO\n",
        },
    )


def _adr_fixture(root: Path, seeded: Seeded) -> None:
    _init_repo(
        root,
        {
            ".ai-state/decisions/drafts/.gitkeep": "",
            "hooks/capture_memory.py": '"""Capture memory writes and filter them."""\n',
        },
    )


def _commit_staging_fixture(root: Path, seeded: Seeded) -> None:
    _init_repo(root, {"scripts/foo.py": '"""Retrun the answer."""\n\nANSWER = 42\n'})
    _write_tree(
        root,
        {
            "scripts/foo.py": '"""Return the answer."""\n\nANSWER = 42\n',
            "scripts/test_foo.py": (
                "from foo import __doc__ as doc\n\n\ndef test_docstring():\n"
                '    assert doc == "Return the answer."\n'
            ),
            ".ai-state/observations.jsonl": '{"event": "session_start"}\n',
        },
    )


def _lightweight_fix_fixture(root: Path, seeded: Seeded) -> None:
    _init_repo(
        root,
        {
            "scripts/paginate.py": (
                "def page(items, number, size):\n"
                '    """Return the 1-based page ``number`` of ``items``."""\n'
                "    start = number * size\n"
                "    return items[start : start + size]\n"
            ),
            "scripts/test_paginate.py": (
                "from paginate import page\n\n\ndef test_first_page():\n"
                "    assert page(list(range(10)), 1, 3) == [0, 1, 2]\n"
            ),
            ".ai-state/calibration_log.md": "# Calibration Log\n\n| Date | Task | Tier |\n|---|---|---|\n",
        },
    )


def _minimal_fixture(root: Path, seeded: Seeded) -> None:
    _init_repo(root, {})


# ---------------------------------------------------------------------------
# Shapes
# ---------------------------------------------------------------------------

_SPAWN_IMPLEMENTER = (
    "Spawn exactly one `praxion:implementer` subagent with the prompt "
    "`Task slug: ui-step. Implement the current step in WIP.md.` "
    "When it finishes, stop."
)
_RECORD_ADR = (
    "Record the following decision as an ADR according to the conventions in your "
    "context. Do not spawn agents.\n\n"
)
_NO_TOOLS = "Do not use any tools. Reply with the single word READY."

# Narrow per-command Bash patterns: each lets the seeded task complete and
# nothing broader. `git diff` is granted only in exact forms because
# `git diff --output=<path>` writes anywhere.
_GIT_INSPECT = ("Bash(git status)", "Bash(git status *)", "Bash(git diff)")
_GIT_STAGE_AND_COMMIT = ("Bash(git add *)", "Bash(git commit *)")
_GIT_IDENTITY_READS = (
    "Bash(git config --get *)",
    "Bash(git config user.name)",
    "Bash(git config user.email)",
    "Bash(git rev-parse *)",
    "Bash(git branch --show-current)",
)
_RUN_TESTS = ("Bash(python3 -m pytest)", "Bash(python3 -m pytest *)")

SHAPES: dict[str, Shape] = {
    shape.name: shape
    for shape in (
        Shape(
            name="ui_step_conformance",
            seeded_file="02_ui_step_conformance.yaml",
            build_fixture=_ui_step_fixture,
            prompt=lambda _: _SPAWN_IMPLEMENTER,
            permission_mode="acceptEdits",
            max_budget_usd=3.0,
            model_role="scenario",
            allowed_tools=_GIT_INSPECT,
            forward_subagent_text=True,
        ),
        Shape(
            name="adr_authoring",
            seeded_file="03_adr_authoring.yaml",
            build_fixture=_adr_fixture,
            prompt=lambda seeded: _RECORD_ADR + seeded["seeded_decision"],
            permission_mode="acceptEdits",
            max_budget_usd=3.0,
            model_role="scenario",
            allowed_tools=(*_GIT_IDENTITY_READS, "Bash(date *)", "Bash(shasum *)"),
        ),
        Shape(
            name="commit_staging",
            seeded_file="04_commit_staging.yaml",
            build_fixture=_commit_staging_fixture,
            prompt=lambda seeded: f"{seeded['seeded_change'].strip()} Commit it.",
            permission_mode="default",
            max_budget_usd=2.0,
            model_role="scenario",
            allowed_tools=(*_GIT_INSPECT, "Bash(git diff --cached)", *_GIT_STAGE_AND_COMMIT),
        ),
        Shape(
            name="lightweight_fix",
            seeded_file="05_lightweight_fix.yaml",
            build_fixture=_lightweight_fix_fixture,
            prompt=lambda seeded: seeded["seeded_fix"],
            permission_mode="acceptEdits",
            max_budget_usd=3.0,
            model_role="scenario",
            allowed_tools=(*_RUN_TESTS, *_GIT_INSPECT, *_GIT_STAGE_AND_COMMIT),
        ),
        Shape(
            name="error_budget_stop",
            seeded_file=None,
            build_fixture=_minimal_fixture,
            prompt=lambda _: _NO_TOOLS,
            permission_mode="default",
            max_budget_usd=BUDGET_STOP_USD,
            model_role="error",
            expected_errors=frozenset({"result_error"}),
        ),
        Shape(
            name="error_invalid_credential",
            seeded_file=None,
            build_fixture=_minimal_fixture,
            prompt=lambda _: _NO_TOOLS,
            permission_mode="default",
            max_budget_usd=NO_SPEND_BUDGET_USD,
            model_role="error",
            env_overrides={
                "ANTHROPIC_API_KEY": REJECTED_CREDENTIAL,
                "CLAUDE_CODE_OAUTH_TOKEN": None,
                "ANTHROPIC_AUTH_TOKEN": None,
            },
            expected_errors=frozenset({"result_error", "exit_nonzero"}),
        ),
        Shape(
            name="error_invalid_flag",
            seeded_file=None,
            build_fixture=_minimal_fixture,
            prompt=lambda _: _NO_TOOLS,
            permission_mode="default",
            max_budget_usd=NO_SPEND_BUDGET_USD,
            model_role="error",
            extra_argv=(UNKNOWN_FLAG,),
            expected_errors=frozenset({"exit_nonzero"}),
        ),
    )
}


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True, check=True
    ).stdout


if __name__ == "__main__":
    sys.exit(main())
