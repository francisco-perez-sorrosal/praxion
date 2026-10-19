#!/usr/bin/env python3
"""Real-token startup payload of a Claude Code session and of each Praxion agent.

The always-loaded budget (`measure_token_budget.py`) counts files. This
instrument counts what the model is actually billed for before it does any
work: the input tokens of the **first request** of a headless session, and of
the first request of a subagent that session spawns. Nothing is estimated and
no category table is read; the number is `input + cache_creation + cache_read`
from the first `assistant` message that `claude -p --output-format stream-json`
emits for the target, which is the method the 2026-10-11 startup-context spike
used for its ablations (`docs/independent-analysis/startup-context-diet-research.md`).

Targets:

- ``main``: the session itself, in the working directory given.
- ``agent:<name>``: a ``praxion:<name>`` agent the session is told to spawn
  with a one-word prompt; its first request is read off the stream message
  that carries ``parent_tool_use_id`` and ``subagent_type``. The session's own
  first request is recorded alongside, so one run yields both.

A reading carries a **profile**: where it ran (this repository, a managed
project with ``.ai-state/``, or an unmanaged directory), the model asked for,
and the isolation flags passed through (``--setting-sources``,
``--strict-mcp-config``, ``--plugin-dir``). Readings are comparable only within
a profile. MCP servers connecting, or not, before the first request move a
reading by about 1.7K tokens from one run to the next (measured 2026-10-11:
53.5K or 55.2K in the same empty directory), so every reading names each
server's status from the init event, and the ``--strict-mcp-config`` profile,
which three runs reproduced within 3 tokens, is the one to gate on; the
default profile reports what a user actually pays. ``--record`` writes the profile's targets into the committed
baseline (``.ai-state/startup_baseline.json``, one entry per profile, newest
wins); ``--compare`` diffs today's reading against that entry and names every
target that grew past the tolerance. A target the probe could not read (no
first request within the timeout, a session that never spawned the agent) is
**withheld with a reason**, never reported as zero and never compared.

Cost: one headless session per target, each paying its own startup (tens of
thousands of input tokens) and, for an agent target, one spawn. The run stops
each session as soon as the target's first request has been seen. Sessions in
this repository append rows to the local observation log like any other.

Exit codes: 0 read (and, with ``--fail-on-regression``, no regression) /
1 a regression past the tolerance under ``--fail-on-regression`` / 2 usage
error, a target that could not be read, or a plugin-cache root.

``--session-oauth-token-file FILE`` bills every probe session to a subscription:
the file's ``claude setup-token`` token is each session's only credential
(``CLAUDE_CODE_OAUTH_TOKEN``; no API key reaches it), and the reading's profile
names ``credential: subscription``, so it compares only with a reading taken the
same way. The token is read once, refused before any session when the file is
missing, unreadable or blank, and never printed, recorded or put in an error
message: it is redacted from every session's error output before anything keeps it.

Stdlib-only and 3.9-safe, because the ambient ``python3`` runs it.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from collections.abc import Iterable, Mapping
from dataclasses import asdict, dataclass, field
from datetime import date
from pathlib import Path

from _repo_root import is_plugin_cache_path, resolve_repo_root

SCRIPT_DIR = Path(__file__).resolve().parent
BASELINE_RELATIVE_PATH = (".ai-state", "startup_baseline.json")
BASELINE_SCHEMA = 1
READING_SCHEMA = 1

MAIN_TARGET = "main"
AGENT_TARGET_PREFIX = "agent:"
DEFAULT_NAMESPACE = "praxion"
DEFAULT_MODEL = "sonnet"
DEFAULT_TIMEOUT_SECONDS = 240
DEFAULT_TOLERANCE_PERCENT = 2.0
# The marketplace copy of the plugin would load beside a `--plugin-dir` copy
# and double every listing, so a plugin-dir run disables it for the session
# (the same overlay `scripts/praxion-claude-dev` applies).
MARKETPLACE_PLUGIN_KEY = "praxion@bit-agora"

OAUTH_VARIABLE = "CLAUDE_CODE_OAUTH_TOKEN"
# What a session billed to a subscription must not hold beside its token.
API_CREDENTIAL_VARIABLES = ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN")
SUBSCRIPTION_CREDENTIAL = "subscription"
REDACTED = "[redacted]"
STDERR_TAIL_CHARS = 600

MAIN_PROMPT = "Reply with the single word ok."
AGENT_PROMPT = (
    'Use the Agent tool exactly once, with subagent_type "{subagent}" and exactly this '
    'prompt: "Reply with the single word ok." Then reply with the single word ok.'
)

_NAME_RE = re.compile(r"^name:\s*(?P<name>[A-Za-z0-9_-]+)\s*$", re.M)


# ---------------------------------------------------------------------------
# Data shapes
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Profile:
    """Where and how a reading was taken; readings compare only within one."""

    cwd_kind: str
    model: str
    setting_sources: str | None = None
    strict_mcp_config: bool = False
    plugin_dir: str | None = None
    credential: str | None = None  # SUBSCRIPTION_CREDENTIAL, or None for the ambient route

    @property
    def key(self) -> str:
        sources = "default" if self.setting_sources is None else f"sources={self.setting_sources}"
        mcp = "no-mcp" if self.strict_mcp_config else "mcp"
        plugin = "plugin-dir" if self.plugin_dir else "installed"
        route = [self.credential] if self.credential else []
        return "|".join([self.cwd_kind, self.model, sources, mcp, plugin, *route])

    def to_json(self) -> dict:
        """The profile as a reading records it; a reading on the ambient route names no credential."""
        named = {k: v for k, v in asdict(self).items() if k != "credential" or v is not None}
        return {**named, "key": self.key}


@dataclass(frozen=True)
class FirstRequest:
    """The billed input of one first request."""

    tokens: int
    input_tokens: int
    cache_creation: int
    cache_read: int
    model: str

    @classmethod
    def from_usage(cls, usage: dict, model: str) -> FirstRequest:
        input_tokens = int(usage.get("input_tokens", 0))
        creation = int(usage.get("cache_creation_input_tokens", 0))
        read = int(usage.get("cache_read_input_tokens", 0))
        return cls(input_tokens + creation + read, input_tokens, creation, read, model)


@dataclass
class TargetReading:
    """A target's first request, or the reason it could not be read."""

    first_request: FirstRequest | None = None
    withheld: str | None = None

    def to_json(self) -> dict:
        if self.first_request is None:
            return {"withheld": self.withheld}
        return asdict(self.first_request)


@dataclass
class StreamObservation:
    """What one stream yields: the session's and the spawned agent's first requests."""

    claude_code_version: str | None = None
    mcp_servers: dict = field(default_factory=dict)  # name -> status, from the init event
    main: FirstRequest | None = None
    agents: dict = field(default_factory=dict)  # subagent_type -> FirstRequest


# ---------------------------------------------------------------------------
# Pure core: the stream, target selection, comparison
# ---------------------------------------------------------------------------


def parse_stream(lines: Iterable[str]) -> StreamObservation:
    """Fold a stream-json transcript into first requests. Malformed lines are skipped.

    The first `assistant` message without `parent_tool_use_id` is the session's
    first request; the first one carrying `parent_tool_use_id` is the first
    request of the subagent named by `subagent_type`. Later messages of either
    are ignored: the instrument reads startup, not the run.
    """
    seen = StreamObservation()
    for line in lines:
        try:
            event = json.loads(line)
        except (ValueError, TypeError):
            continue
        if not isinstance(event, dict):
            continue
        if event.get("type") == "system" and event.get("subtype") == "init":
            seen.claude_code_version = event.get("claude_code_version")
            seen.mcp_servers = {
                str(s.get("name")): str(s.get("status"))
                for s in event.get("mcp_servers") or []
                if isinstance(s, dict)
            }
            continue
        if event.get("type") != "assistant":
            continue
        message = event.get("message") or {}
        usage = message.get("usage")
        if not isinstance(usage, dict):
            continue
        request = FirstRequest.from_usage(usage, str(message.get("model", "")))
        if event.get("parent_tool_use_id"):
            subagent = str(event.get("subagent_type") or "")
            seen.agents.setdefault(subagent, request)
        elif seen.main is None:
            seen.main = request
    return seen


def target_satisfied(seen: StreamObservation, target: str, namespace: str) -> bool:
    """True once the stream holds everything `target` needs; the session can stop."""
    if target == MAIN_TARGET:
        return seen.main is not None
    return subagent_type_for(target, namespace) in seen.agents


def subagent_type_for(target: str, namespace: str) -> str:
    return f"{namespace}:{target[len(AGENT_TARGET_PREFIX) :]}"


def readings_for(seen: StreamObservation, target: str, namespace: str, timeout: int) -> dict:
    """The target readings one stream contributes: the target and, for an agent, `main` too."""
    out = {}
    if seen.main is not None:
        out[MAIN_TARGET] = TargetReading(first_request=seen.main)
    elif target == MAIN_TARGET:
        out[MAIN_TARGET] = TargetReading(withheld=f"no first request within {timeout}s")
    if target != MAIN_TARGET:
        subagent = subagent_type_for(target, namespace)
        if subagent in seen.agents:
            out[target] = TargetReading(first_request=seen.agents[subagent])
        else:
            out[target] = TargetReading(
                withheld=f"the session spawned no {subagent} within {timeout}s"
            )
    return out


def compare(baseline_targets: dict, today_targets: dict, tolerance_percent: float) -> list:
    """Per-target delta against the baseline entry of the same profile.

    A target missing on either side, or withheld on either side, is reported
    as `skipped` with the reason; it is never a regression and never a saving.
    """
    rows = []
    for name in sorted(set(baseline_targets) | set(today_targets)):
        before = baseline_targets.get(name)
        now = today_targets.get(name)
        row = {"target": name}
        if before is None or "tokens" not in before:
            row.update(verdict="skipped", reason="no baseline reading")
        elif now is None or "tokens" not in now:
            row.update(verdict="skipped", reason=(now or {}).get("withheld", "no reading today"))
        else:
            delta = int(now["tokens"]) - int(before["tokens"])
            allowed = int(before["tokens"]) * tolerance_percent / 100.0
            verdict = (
                "regression" if delta > allowed else ("saving" if delta < -allowed else "stable")
            )
            row.update(
                before=int(before["tokens"]), now=int(now["tokens"]), delta=delta, verdict=verdict
            )
        rows.append(row)
    return rows


def classify_cwd(cwd: Path) -> str:
    """`praxion-repo`, `managed` (carries `.ai-state/`) or `unmanaged`."""
    manifest = cwd / ".claude-plugin" / "plugin.json"
    if manifest.is_file():
        try:
            if json.loads(manifest.read_text(encoding="utf-8")).get("name") == DEFAULT_NAMESPACE:
                return "praxion-repo"
        except (ValueError, OSError):
            pass
    if (cwd / ".ai-state").is_dir():
        return "managed"
    return "unmanaged"


def build_invocation(target: str, profile: Profile, namespace: str, max_turns: int = 4) -> list:
    """The `claude` argv for one target. Pure; executed only by `run_target`."""
    prompt = (
        MAIN_PROMPT
        if target == MAIN_TARGET
        else AGENT_PROMPT.format(subagent=subagent_type_for(target, namespace))
    )
    argv = [
        "claude",
        "-p",
        prompt,
        "--output-format",
        "stream-json",
        "--verbose",
        "--model",
        profile.model,
        "--max-turns",
        str(max_turns),
    ]
    if profile.setting_sources is not None:
        argv += ["--setting-sources", profile.setting_sources]
    if profile.strict_mcp_config:
        argv.append("--strict-mcp-config")
    if profile.plugin_dir:
        overlay = json.dumps({"enabledPlugins": {MARKETPLACE_PLUGIN_KEY: False}})
        argv += ["--plugin-dir", profile.plugin_dir, "--settings", overlay]
    return argv


class TokenFileError(Exception):
    """The session token file cannot be used; the message never carries its content."""


def read_session_token(path: Path) -> str:
    """The token in a `claude setup-token` file, or a TokenFileError naming the file and why not."""
    try:
        text = path.read_bytes().decode()
    except FileNotFoundError:
        raise TokenFileError(f"{path}: the token file does not exist") from None
    except OSError as error:
        raise TokenFileError(f"{path}: the token file cannot be read ({error.strerror})") from None
    except UnicodeDecodeError:  # its message quotes the bytes it could not decode
        raise TokenFileError(f"{path}: the token file is not text") from None
    token = text.strip()
    if not token:
        raise TokenFileError(f"{path}: the token file is blank")
    return token


def session_environment(inherited: Mapping[str, str], token: str | None) -> dict:
    """The environment a probe session starts with.

    With a token it is the session's only credential. Without one the environment is
    inherited as is, except an empty oauth variable, which the CLI would read as a token.
    """
    if token is None:
        return {k: v for k, v in inherited.items() if k != OAUTH_VARIABLE or v}
    held_elsewhere = (OAUTH_VARIABLE, *API_CREDENTIAL_VARIABLES)
    return {
        **{k: v for k, v in inherited.items() if k not in held_elsewhere},
        OAUTH_VARIABLE: token,
    }


def redact(text: str, token: str | None) -> str:
    return text if token is None else text.replace(token, REDACTED)


def agent_names(repo_root: Path) -> list:
    """Every agent the repository defines: `agents/*.md` whose frontmatter declares `name:`."""
    names = []
    for path in sorted((repo_root / "agents").glob("*.md")):
        head = path.read_text(encoding="utf-8")[:2000]
        match = _NAME_RE.search(head)
        if match:
            names.append(match.group("name"))
    return names


# ---------------------------------------------------------------------------
# Baseline file
# ---------------------------------------------------------------------------


def load_baseline(path: Path) -> dict:
    if not path.is_file():
        return {"schema": BASELINE_SCHEMA, "profiles": {}}
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schema") != BASELINE_SCHEMA or not isinstance(data.get("profiles"), dict):
        raise ValueError(f"{path}: not a schema-{BASELINE_SCHEMA} startup baseline")
    return data


def record_reading(baseline: dict, reading: dict) -> dict:
    """The baseline with this reading's targets replacing its profile entry (withheld ones kept out)."""
    kept = {name: value for name, value in reading["targets"].items() if "tokens" in value}
    entry = baseline["profiles"].get(reading["profile"]["key"], {})
    merged_targets = dict(entry.get("targets", {}))
    merged_targets.update(kept)
    baseline["profiles"][reading["profile"]["key"]] = {
        "recorded": reading["date"],
        "claude_code_version": reading["claude_code_version"],
        "profile": reading["profile"],
        "targets": merged_targets,
    }
    return baseline


def write_baseline(path: Path, baseline: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(baseline, indent=2, sort_keys=True) + "\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# Impure shell: one headless session per target
# ---------------------------------------------------------------------------


def run_target(
    target: str,
    profile: Profile,
    cwd: Path,
    namespace: str,
    timeout: int,
    token: str | None = None,
) -> tuple:
    """Run one session, stop it once the target's first request is seen; returns (observation, stderr tail).

    The stderr tail has the session's token redacted before it is cut, so no part of it survives.
    """
    argv = build_invocation(target, profile, namespace)
    env = session_environment(os.environ, token)
    process = subprocess.Popen(
        argv,
        cwd=str(cwd),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env,
    )
    seen = StreamObservation()
    deadline = time.monotonic() + timeout
    lines = []
    try:
        assert process.stdout is not None
        for line in process.stdout:
            lines.append(line)
            seen = parse_stream(lines)
            if target_satisfied(seen, target, namespace) or time.monotonic() > deadline:
                break
    finally:
        _stop(process)
    stderr_tail = ""
    if process.stderr is not None:
        try:
            stderr_tail = redact(process.stderr.read(), token)[-STDERR_TAIL_CHARS:]
        except (OSError, ValueError):
            stderr_tail = ""
    return seen, stderr_tail


def _stop(process: subprocess.Popen) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=10)


def measure(
    targets: list,
    profile: Profile,
    cwd: Path,
    namespace: str,
    timeout: int,
    today: date,
    token: str | None = None,
) -> dict:
    """A reading over `targets`: one session each, `main` folded in from any agent run."""
    collected = {}
    version = None
    stderr_by_target = {}
    mcp_by_target = {}
    for target in targets:
        seen, stderr_tail = run_target(target, profile, cwd, namespace, timeout, token)
        version = version or seen.claude_code_version
        mcp_by_target[target] = seen.mcp_servers
        for name, reading in readings_for(seen, target, namespace, timeout).items():
            if name in collected and collected[name].first_request is not None:
                continue
            collected[name] = reading
            if reading.withheld:
                stderr_by_target[name] = stderr_tail
    return {
        "schema": READING_SCHEMA,
        "date": today.isoformat(),
        "claude_code_version": version,
        "cwd": str(cwd),
        "profile": profile.to_json(),
        "targets": {name: reading.to_json() for name, reading in collected.items()},
        "mcp_servers": mcp_by_target,
        "stderr": stderr_by_target,
    }


# ---------------------------------------------------------------------------
# Command line
# ---------------------------------------------------------------------------


def _parse_args(argv: list | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "targets",
        nargs="*",
        help=f"`{MAIN_TARGET}` and/or `{AGENT_TARGET_PREFIX}<name>` entries (default: main)",
    )
    parser.add_argument("--all-agents", action="store_true", help="add every agent in agents/*.md")
    parser.add_argument("--cwd", help="directory to start the session in (default: the repo root)")
    parser.add_argument(
        "--empty-dir",
        action="store_true",
        help="start in a fresh empty directory instead: the unmanaged-project reading",
    )
    parser.add_argument(
        "--model", default=DEFAULT_MODEL, help=f"session model (default {DEFAULT_MODEL})"
    )
    parser.add_argument("--setting-sources", help="passed through to claude (isolation)")
    parser.add_argument("--strict-mcp-config", action="store_true", help="passed through to claude")
    parser.add_argument(
        "--plugin-dir", help="measure this plugin checkout; the marketplace copy is disabled"
    )
    parser.add_argument(
        "--session-oauth-token-file",
        type=Path,
        help="a `claude setup-token` file: every session bills its subscription, with no API key",
    )
    parser.add_argument(
        "--namespace", default=DEFAULT_NAMESPACE, help="agent namespace (default praxion)"
    )
    parser.add_argument(
        "--timeout", type=int, default=DEFAULT_TIMEOUT_SECONDS, help="seconds per target"
    )
    parser.add_argument("--record", action="store_true", help="write the reading into the baseline")
    parser.add_argument(
        "--compare", action="store_true", help="diff against the baseline's same profile"
    )
    parser.add_argument(
        "--tolerance", type=float, default=DEFAULT_TOLERANCE_PERCENT, help="percent"
    )
    parser.add_argument("--fail-on-regression", action="store_true", help="exit 1 on a regression")
    parser.add_argument(
        "--baseline", help="baseline path (default .ai-state/startup_baseline.json)"
    )
    parser.add_argument(
        "--json", action="store_true", help="emit the reading (and comparison) as JSON"
    )
    parser.add_argument("--repo-root", help="repository root (default: git discovery)")
    return parser.parse_args(argv)


def main(argv: list | None = None) -> int:
    args = _parse_args(argv)
    repo_root = resolve_repo_root(args.repo_root, script_dir=SCRIPT_DIR)
    if repo_root is None or is_plugin_cache_path(repo_root):
        print(
            "measure_startup_payload: no usable repository root (a plugin-cache root is refused)",
            file=sys.stderr,
        )
        return 2
    if shutil.which("claude") is None:
        print("measure_startup_payload: the `claude` CLI is not on PATH", file=sys.stderr)
        return 2

    token = None
    if args.session_oauth_token_file is not None:
        try:
            token = read_session_token(args.session_oauth_token_file)
        except TokenFileError as error:
            print(f"measure_startup_payload: {error}", file=sys.stderr)
            return 2

    targets = list(args.targets) or ([] if args.all_agents else [MAIN_TARGET])
    if args.all_agents:
        targets += [AGENT_TARGET_PREFIX + name for name in agent_names(repo_root)]
    bad = [t for t in targets if t != MAIN_TARGET and not t.startswith(AGENT_TARGET_PREFIX)]
    if bad:
        print(f"measure_startup_payload: unknown target(s) {bad}", file=sys.stderr)
        return 2

    scratch = None
    if args.empty_dir:
        scratch = tempfile.mkdtemp(prefix="startup-probe-")
        cwd = Path(scratch)
    else:
        cwd = Path(args.cwd).resolve() if args.cwd else repo_root
    profile = Profile(
        cwd_kind=classify_cwd(cwd),
        model=args.model,
        setting_sources=args.setting_sources,
        strict_mcp_config=args.strict_mcp_config,
        plugin_dir=str(Path(args.plugin_dir).resolve()) if args.plugin_dir else None,
        credential=SUBSCRIPTION_CREDENTIAL if token else None,
    )
    try:
        reading = measure(targets, profile, cwd, args.namespace, args.timeout, date.today(), token)
    finally:
        if scratch:
            shutil.rmtree(scratch, ignore_errors=True)

    baseline_path = (
        Path(args.baseline) if args.baseline else repo_root.joinpath(*BASELINE_RELATIVE_PATH)
    )
    comparison = None
    if args.compare:
        entry = load_baseline(baseline_path)["profiles"].get(profile.key, {})
        comparison = compare(entry.get("targets", {}), reading["targets"], args.tolerance)
    if args.record:
        write_baseline(baseline_path, record_reading(load_baseline(baseline_path), reading))

    withheld = [name for name, value in reading["targets"].items() if "withheld" in value]
    if args.json:
        payload = dict(reading)
        if comparison is not None:
            payload["comparison"] = comparison
        print(json.dumps(payload, indent=2))
    else:
        _print_text(reading, comparison, profile)

    if withheld:
        return 2
    if (
        args.fail_on_regression
        and comparison
        and any(r["verdict"] == "regression" for r in comparison)
    ):
        return 1
    return 0


def _print_text(reading: dict, comparison: list | None, profile: Profile) -> None:
    print(f"profile: {profile.key}  (claude {reading['claude_code_version']}, {reading['date']})")
    for name, value in reading["targets"].items():
        if "withheld" in value:
            print(f"  {name:<40} withheld: {value['withheld']}")
        else:
            print(f"  {name:<40} {value['tokens']:>8,} tokens  ({value['model']})")
    for name, tail in reading.get("stderr", {}).items():
        if tail.strip():
            print(f"  stderr[{name}]: {tail.strip()[-200:]}")
    if comparison is not None:
        print("comparison against the baseline:")
        for row in comparison:
            if row["verdict"] == "skipped":
                print(f"  {row['target']:<40} skipped: {row['reason']}")
            else:
                print(
                    f"  {row['target']:<40} {row['before']:>8,} -> {row['now']:>8,}  "
                    f"({row['delta']:+,})  {row['verdict']}"
                )


if __name__ == "__main__":
    sys.exit(main())
