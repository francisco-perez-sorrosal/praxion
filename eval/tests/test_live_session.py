"""Behavioral tests for the live scenario runner's session-invocation layer.

Covers the pure functions in `praxion_evals.live.session`: building the
`claude -p` argv and environment for one session, parsing a verbatim
stream-json envelope into a typed `SessionEnvelope`, classifying
infrastructure failures, and checking per-session isolation from harness
telemetry (never from the model's own self-report).

`build_argv`/`build_env` fix the contract the implementer's `SessionSpec`
must satisfy (test-engineer-designed interface, per the paired RED/GREEN
step ordering): a session is built from an explicit, allowlisted set of
inputs — nothing ambient leaks in silently.

Fixtures under `fixtures/live_scenarios/*.stream.jsonl` are verbatim
`claude -p --output-format stream-json --verbose` captures (see that
directory's README.md for provenance and the one substitution applied).
`parse_stream`/`classify`/`check_isolation` are exercised against them
directly — never against hand-written JSON shaped like what an envelope
"should" look like.

All production imports are deferred inside each test body so pytest
collection succeeds before the `praxion_evals.live` package exists
(RED-state handshake).
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures" / "live_scenarios"

# The preflight and ambient-control envelopes were both recorded against the
# same planted `--plugin-dir` copy — this is the copy_root every isolation
# check in this file is measured against.
_PREFLIGHT_COPY_ROOT = Path(
    "/private/tmp/claude-501/-Users-operator-dev-praxion/"
    "ecca6863-b00e-4005-a781-2c1ba6e8cd2f/scratchpad/probe1/target"
)


def _fixture_text(name: str) -> str:
    return (FIXTURES_DIR / f"{name}.stream.jsonl").read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# build_argv — pure, one govern per-scenario session invocation shape
# ---------------------------------------------------------------------------


def test_build_argv_produces_the_documented_claude_invocation_shape():
    """The real call shape a session invocation must produce: `-p`,
    stream-json output, strict empty MCP config, no permission prompts."""
    from praxion_evals.live.session import SessionSpec, build_argv

    spec = SessionSpec(
        prompt="do the thing",
        model="opus",
        effort="medium",
        plugin_dir=Path("/tmp/materialization"),
        cwd=Path("/tmp/session/fixture"),
        permission_mode="default",
        max_budget_usd=1.0,
    )

    argv = build_argv(spec)

    assert argv[0] == "claude"
    assert argv[1:3] == ["-p", "do the thing"]
    assert "--model" in argv
    assert argv[argv.index("--model") + 1] == "opus"
    assert "--effort" in argv
    assert argv[argv.index("--effort") + 1] == "medium"
    assert "--output-format" in argv
    assert argv[argv.index("--output-format") + 1] == "stream-json"
    assert "--verbose" in argv
    assert "--plugin-dir" in argv
    assert argv[argv.index("--plugin-dir") + 1] == str(spec.plugin_dir)
    assert "--strict-mcp-config" in argv
    assert "--mcp-config" in argv
    assert argv[argv.index("--mcp-config") + 1] == '{"mcpServers":{}}'
    assert "--permission-prompts" in argv
    assert argv[argv.index("--permission-prompts") + 1] == "none"
    assert "--permission-mode" in argv
    assert argv[argv.index("--permission-mode") + 1] == "default"
    assert "--max-budget-usd" in argv
    assert argv[argv.index("--max-budget-usd") + 1] == "1.0"


def test_build_argv_omits_optional_flags_when_unset():
    """A minimal spec (no allowed tools, no json schema, no subagent
    forwarding) never emits those flags — an absent optional stays absent,
    never a flag paired with an empty value."""
    from praxion_evals.live.session import SessionSpec, build_argv

    spec = SessionSpec(
        prompt="p",
        model="sonnet",
        effort="medium",
        plugin_dir=Path("/tmp/m"),
        cwd=Path("/tmp/s/fixture"),
        permission_mode="default",
        max_budget_usd=1.0,
    )

    argv = build_argv(spec)

    assert "--allowedTools" not in argv
    assert "--json-schema" not in argv
    assert "--forward-subagent-text" not in argv
    assert "--add-dir" not in argv


def test_build_argv_includes_add_dir_when_set_so_the_plugin_copy_is_readable():
    """Without `--add-dir`, a session cannot Read files under the plugin copy
    (it lies outside the session's cwd) — skill references become denied."""
    from praxion_evals.live.session import SessionSpec, build_argv

    spec = SessionSpec(
        prompt="p",
        model="sonnet",
        effort="medium",
        plugin_dir=Path("/tmp/copy"),
        cwd=Path("/tmp/s/fixture"),
        permission_mode="default",
        max_budget_usd=1.0,
        add_dir=Path("/tmp/copy"),
    )

    argv = build_argv(spec)

    assert "--add-dir" in argv
    assert argv[argv.index("--add-dir") + 1] == "/tmp/copy"


def test_build_argv_includes_allowed_tools_json_schema_and_subagent_forwarding_when_set():
    """The spawn-selection and subagent-carrying scenarios set every optional
    flag; each must reach argv exactly once, in a form `claude` accepts."""
    from praxion_evals.live.session import SessionSpec, build_argv

    spec = SessionSpec(
        prompt="p",
        model="opus",
        effort="medium",
        plugin_dir=Path("/tmp/m"),
        cwd=Path("/tmp/s/fixture"),
        permission_mode="acceptEdits",
        max_budget_usd=3.0,
        allowed_tools=("Bash(git status *)", "Bash(git diff *)"),
        json_schema={"tier": "string", "agents": ["string"]},
        forward_subagent_text=True,
    )

    argv = build_argv(spec)

    tools_index = argv.index("--allowedTools")
    assert argv[tools_index + 1 : tools_index + 3] == [
        "Bash(git status *)",
        "Bash(git diff *)",
    ]
    schema_index = argv.index("--json-schema")
    assert json.loads(argv[schema_index + 1]) == {"tier": "string", "agents": ["string"]}
    assert "--forward-subagent-text" in argv


# ---------------------------------------------------------------------------
# build_env — allowlist only; nothing ambient leaks in silently
# ---------------------------------------------------------------------------


def test_build_env_sets_sandbox_home_config_dir_and_tmpdir():
    """The three per-session overrides always point inside the sandbox root,
    never at the ambient values (even if the ambient mapping supplies them)."""
    from praxion_evals.live.session import build_env

    sandbox = Path("/tmp/run-abc/session-1")
    ambient = {"HOME": "/Users/operator", "PATH": "/usr/bin"}

    env = build_env(sandbox, ambient)

    assert env["HOME"] == str(sandbox / "home")
    assert env["CLAUDE_CONFIG_DIR"] == str(sandbox / "home" / ".claude")
    assert env["TMPDIR"] == str(sandbox / "tmp")


def test_build_env_drops_claude_plugin_root_and_claudecode_even_when_ambient_sets_them():
    """`CLAUDE_PLUGIN_ROOT`/`CLAUDECODE` are the two ambient leaks probe 3
    identified (the ambient control's ground truth for what NOT to inherit)
    — present in `ambient`, must never reach the built env."""
    from praxion_evals.live.session import build_env

    ambient = {
        "PATH": "/usr/bin",
        "CLAUDE_PLUGIN_ROOT": "/Users/operator/dev/praxion",
        "CLAUDECODE": "1",
    }

    env = build_env(Path("/tmp/run/session-1"), ambient)

    assert "CLAUDE_PLUGIN_ROOT" not in env
    assert "CLAUDECODE" not in env


def test_build_env_drops_unlisted_ambient_keys():
    """The allowlist is closed — a variable not on it (however innocuous)
    does not pass through, even when present in the ambient mapping."""
    from praxion_evals.live.session import build_env

    ambient = {"PATH": "/usr/bin", "SOME_UNRELATED_TOOL_VAR": "value"}

    env = build_env(Path("/tmp/run/session-1"), ambient)

    assert "SOME_UNRELATED_TOOL_VAR" not in env


def test_build_env_passes_through_the_allowlisted_credential_and_locale_keys():
    """Auth and locale/terminal keys are the documented pass-through set."""
    from praxion_evals.live.session import build_env

    ambient = {
        "PATH": "/usr/bin",
        "ANTHROPIC_API_KEY": "test-value-not-a-real-key",
        "LANG": "en_US.UTF-8",
        "TERM": "xterm-256color",
        "USER": "operator",
    }

    env = build_env(Path("/tmp/run/session-1"), ambient)

    assert env["ANTHROPIC_API_KEY"] == "test-value-not-a-real-key"
    assert env["LANG"] == "en_US.UTF-8"
    assert env["TERM"] == "xterm-256color"
    assert env["USER"] == "operator"


def test_build_env_prepends_the_interpreter_parent_directory_to_path():
    """Orchestrator amendment: the sandbox `PATH` is built with
    `Path(sys.executable).parent` prepended — hook-delivered rules must
    reach the measured layer, so hooks run under an interpreter that has
    PyYAML, not whatever ambient `python3` the operator's shell resolves."""
    from praxion_evals.live.session import build_env

    ambient = {"PATH": "/usr/bin:/bin"}

    env = build_env(Path("/tmp/run/session-1"), ambient)

    interpreter_dir = str(Path(sys.executable).parent)
    path_entries = env["PATH"].split(os.pathsep)
    assert path_entries[0] == interpreter_dir
    assert "/usr/bin" in path_entries
    assert "/bin" in path_entries


def test_build_env_sets_the_side_effect_kill_switches_and_harness_noise_flags():
    """The documented fixed switches — side-effect hooks off, harness noise
    off — are present on every built env regardless of ambient content."""
    from praxion_evals.live.session import build_env

    env = build_env(Path("/tmp/run/session-1"), {"PATH": "/usr/bin"})

    for key in (
        "PRAXION_DISABLE_AUTO_COMPLETE",
        "PRAXION_DISABLE_OBSERVABILITY",
        "PRAXION_DISABLE_HOOK_CHAIN_HEAL",
        "PRAXION_DISABLE_SIDECAR_AUTOCOMMIT",
        "CLAUDE_CODE_DISABLE_AUTO_MEMORY",
        "DISABLE_AUTOUPDATER",
        "PYTHONDONTWRITEBYTECODE",
    ):
        assert env[key] == "1", f"{key} must be set to '1'"


# ---------------------------------------------------------------------------
# parse_stream — boundary parsing of verbatim envelopes
# ---------------------------------------------------------------------------


def test_parse_stream_preflight_envelope_carries_all_three_legacy_nonces():
    """The isolated-marker preflight fixture's final result text is the
    isolation proof: three unguessable nonces the model could not produce
    unless it loaded the planted copy. This fixture predates the fourth
    (hook-delivered-rule) nonce — asserting a fourth here would assert
    something the recording never captured."""
    from praxion_evals.live.session import parse_stream

    envelope = parse_stream(_fixture_text("isolated_marker_preflight_sonnet"))

    assert envelope.final_result is not None
    text = envelope.final_result.result_text
    assert text is not None
    assert "PRXPROBE-GLOBAL-f5323cbc" in text
    assert "PRXPROBE-RULE-c47ffd71" in text
    assert "PRXPROBE-AGENT-f0bf7511" in text


def test_parse_stream_preflight_envelope_init_reports_only_the_target_copy():
    from praxion_evals.live.session import parse_stream

    envelope = parse_stream(_fixture_text("isolated_marker_preflight_sonnet"))

    assert envelope.init is not None
    assert envelope.init.mcp_servers == ()
    non_builtin = [p for p in envelope.init.plugins if p.get("source") != "telemetry@builtin"]
    assert len(non_builtin) == 2  # praxion@inline (target copy) + agents-md@builtin


def test_parse_stream_ambient_control_envelope_reports_marketplace_plugins_and_mcp_servers():
    """Ground truth for what an isolation breach looks like: 5 MCP servers
    connect and the plugin list carries 9 plugins beyond the target copy and
    the one builtin the preflight fixture also carries."""
    from praxion_evals.live.session import parse_stream

    envelope = parse_stream(_fixture_text("ambient_control_sonnet"))

    assert envelope.init is not None
    assert len(envelope.init.mcp_servers) == 5
    assert len(envelope.init.plugins) == 11


def test_parse_stream_spawn_selection_envelope_captures_structured_output():
    from praxion_evals.live.session import parse_stream

    envelope = parse_stream(_fixture_text("spawn_selection_standard_opus"))

    assert envelope.final_result is not None
    assert envelope.final_result.structured_output == {
        "tier": "Standard",
        "agents": [
            "praxion:researcher",
            "praxion:systems-architect",
            "praxion:interface-designer",
            "praxion:implementation-planner",
            "praxion:implementer",
            "praxion:test-engineer",
            "praxion:verifier",
        ],
    }
    tool_use_names = [t.name for t in envelope.tool_uses]
    assert "StructuredOutput" in tool_use_names


def test_parse_stream_subagent_envelope_final_result_is_the_last_of_two_result_events():
    """Probe 4's discovery: a background-subagent session emits two `result`
    events (the async-stub relay message, then the actual relayed text).
    `final_result` must be the second one, not the first."""
    from praxion_evals.live.session import parse_stream

    envelope = parse_stream(_fixture_text("subagent_implementer_background_sonnet"))

    assert envelope.result_count == 2
    assert envelope.final_result is not None
    assert envelope.final_result.result_text == (
        "PRXPROBE-AGENTBODY-8e968ced\n"
        "PRXPROBE-GLOBAL-703112aa\n"
        "PRXPROBE-RULE-4e736369\n"
        "PRXPROBE-PRELOADSKILL-db0ad889"
    )


def test_parse_stream_subagent_envelope_captures_forwarded_subagent_text_and_task_notification():
    """Ground-truth capture for the subagent scenario: the forwarded
    assistant event whose `parent_tool_use_id` is the Agent call, and the
    `task_notification` summary as fallback — both must be reachable from
    the parsed envelope, not just the top-level orchestrator's relay."""
    from praxion_evals.live.session import parse_stream

    envelope = parse_stream(_fixture_text("subagent_implementer_background_sonnet"))

    assert len(envelope.subagent_texts) >= 1
    parent_id, subagent_type, text = envelope.subagent_texts[-1]
    assert parent_id == "toolu_019Na3M1JsL25rwD8kcakVxH"
    assert subagent_type == "praxion:implementer"
    assert text  # non-empty ground-truth text, not the orchestrator's relay

    assert len(envelope.task_notifications) == 1
    tool_use_id, status, summary = envelope.task_notifications[0]
    assert tool_use_id == "toolu_019Na3M1JsL25rwD8kcakVxH"
    assert status == "completed"
    assert "PRXPROBE-AGENTBODY-8e968ced" in summary


def test_parse_stream_marks_envelope_unparseable_on_a_non_json_line():
    """A stream with one malformed line is unparseable as a whole — not
    partially parsed with the bad line silently dropped."""
    from praxion_evals.live.session import parse_stream

    corrupted = _fixture_text("isolated_marker_preflight_sonnet") + "not-a-json-line{{{\n"

    envelope = parse_stream(corrupted)

    assert envelope.unparseable is True


def test_parse_stream_well_formed_envelope_is_not_marked_unparseable():
    from praxion_evals.live.session import parse_stream

    envelope = parse_stream(_fixture_text("isolated_marker_preflight_sonnet"))

    assert envelope.unparseable is False


# ---------------------------------------------------------------------------
# classify — infrastructure failures never masquerade as behavioral ones
# ---------------------------------------------------------------------------


def test_classify_returns_none_for_a_clean_successful_session():
    from praxion_evals.live.session import classify, parse_stream

    envelope = parse_stream(_fixture_text("isolated_marker_preflight_sonnet"))

    assert classify(envelope, exit_code=0, timed_out=False) is None


def test_classify_returns_timeout_when_the_session_timed_out():
    from praxion_evals.live.session import classify, parse_stream

    envelope = parse_stream(_fixture_text("isolated_marker_preflight_sonnet"))

    assert classify(envelope, exit_code=0, timed_out=True) == "timeout"


def test_classify_returns_exit_nonzero_for_a_nonzero_exit_code():
    from praxion_evals.live.session import classify, parse_stream

    envelope = parse_stream(_fixture_text("isolated_marker_preflight_sonnet"))

    assert classify(envelope, exit_code=1, timed_out=False) == "exit_nonzero"


def test_classify_returns_envelope_unparseable_for_a_corrupted_stream():
    from praxion_evals.live.session import classify, parse_stream

    corrupted = _fixture_text("isolated_marker_preflight_sonnet") + "not-a-json-line{{{\n"
    envelope = parse_stream(corrupted)

    assert classify(envelope, exit_code=0, timed_out=False) == "envelope_unparseable"


def test_classify_returns_no_result_event_when_the_stream_never_emits_a_result():
    """Drop the trailing `result` line from a real envelope — infrastructure
    failure, not a behavioral one, so it must classify distinctly from
    `result_error`."""
    from praxion_evals.live.session import classify, parse_stream

    lines = _fixture_text("isolated_marker_preflight_sonnet").splitlines()
    without_result = "\n".join(line for line in lines if '"type":"result"' not in line) + "\n"
    envelope = parse_stream(without_result)

    assert envelope.final_result is None
    assert classify(envelope, exit_code=0, timed_out=False) == "no_result_event"


def test_classify_returns_result_error_when_the_final_result_reports_an_error():
    """Budget-cap and max-turns stops surface as an error `result` event —
    classify must read that from the envelope, not assume success from a
    zero exit code."""
    from praxion_evals.live.session import ResultInfo, SessionEnvelope, classify

    envelope = SessionEnvelope(
        init=None,
        tool_uses=(),
        subagent_texts=(),
        task_notifications=(),
        hook_outputs=(),
        final_result=ResultInfo(
            result_text=None,
            structured_output=None,
            is_error=True,
            subtype="error_max_budget",
            total_cost_usd=1.0,
            session_id="s1",
        ),
        result_count=1,
        unparseable=False,
    )

    assert classify(envelope, exit_code=0, timed_out=False) == "result_error"


# ---------------------------------------------------------------------------
# check_isolation — from harness telemetry, never from model self-report
# ---------------------------------------------------------------------------


def test_check_isolation_passes_for_the_preflight_fixture():
    """Only the target copy plugin (plus builtins) and no MCP servers —
    isolation holds."""
    from praxion_evals.live.session import check_isolation, parse_stream

    envelope = parse_stream(_fixture_text("isolated_marker_preflight_sonnet"))

    assert check_isolation(envelope, _PREFLIGHT_COPY_ROOT) is True


def test_check_isolation_breaches_for_the_ambient_control_fixture():
    """Same target copy, but the ambient environment leaked 9 extra plugins
    and 5 live MCP servers — the exact negative control this checker exists
    to catch, using the identical copy_root as the passing case above."""
    from praxion_evals.live.session import check_isolation, parse_stream

    envelope = parse_stream(_fixture_text("ambient_control_sonnet"))

    assert check_isolation(envelope, _PREFLIGHT_COPY_ROOT) is False


# ---------------------------------------------------------------------------
# Isolation breaches judged one clause at a time
# ---------------------------------------------------------------------------


def _preflight_with_init(**changes):
    """The passing preflight envelope with its `init` telemetry altered."""
    import dataclasses

    from praxion_evals.live.session import parse_stream

    envelope = parse_stream(_fixture_text("isolated_marker_preflight_sonnet"))
    assert envelope.init is not None
    return dataclasses.replace(envelope, init=dataclasses.replace(envelope.init, **changes))


def _preflight_without_init() -> str:
    lines = _fixture_text("isolated_marker_preflight_sonnet").splitlines()
    return "\n".join(line for line in lines if '"subtype":"init"' not in line) + "\n"


def test_check_isolation_breaches_when_only_an_mcp_server_leaked():
    """Plugins are exactly the target copy plus builtins, but one user MCP
    server started — that alone is a breach."""
    from praxion_evals.live.session import check_isolation

    envelope = _preflight_with_init(mcp_servers=({"name": "chub", "source": "user"},))

    assert check_isolation(envelope, _PREFLIGHT_COPY_ROOT) is False


def test_check_isolation_breaches_when_the_stream_has_no_init_event():
    """Without `init` telemetry isolation cannot be proven — never assumed."""
    from praxion_evals.live.session import check_isolation, parse_stream

    envelope = parse_stream(_preflight_without_init())

    assert envelope.init is None
    assert check_isolation(envelope, _PREFLIGHT_COPY_ROOT) is False


def test_check_isolation_exempts_a_builtin_only_when_it_is_really_builtin():
    """A plugin whose source merely ends in `@builtin` but loads from a real
    directory is a foreign plugin, not a builtin."""
    from praxion_evals.live.session import check_isolation

    impostor = {
        "name": "evil",
        "path": "/Users/operator/.claude/plugins/cache/evil",
        "source": "evil@builtin",
    }
    clean = _preflight_with_init()
    assert clean.init is not None
    leaked = _preflight_with_init(plugins=(*clean.init.plugins, impostor))

    assert check_isolation(clean, _PREFLIGHT_COPY_ROOT) is True
    assert check_isolation(leaked, _PREFLIGHT_COPY_ROOT) is False


def test_session_error_turns_a_stream_without_init_into_a_typed_isolation_error():
    """A stream that completed but never reported `init` is an infrastructure
    error of kind `isolation_breach` — never a gradeable session."""
    from praxion_evals.live.results import Errored
    from praxion_evals.live.session import SessionRun, parse_stream, session_error

    run = SessionRun(stdout=_preflight_without_init(), stderr="", exit_code=0)

    error = session_error(parse_stream(run.stdout), run, _PREFLIGHT_COPY_ROOT)

    assert isinstance(error, Errored)
    assert error.kind == "isolation_breach"
    assert "init" in error.detail


def test_session_error_names_the_leaked_mcp_server():
    from praxion_evals.live.session import SessionRun, session_error

    envelope = _preflight_with_init(mcp_servers=({"name": "chub", "source": "user"},))
    run = SessionRun(stdout="", stderr="", exit_code=0)

    error = session_error(envelope, run, _PREFLIGHT_COPY_ROOT)

    assert error is not None
    assert error.kind == "isolation_breach"
    assert "chub" in error.detail


def test_session_error_is_none_for_a_clean_isolated_session():
    from praxion_evals.live.session import SessionRun, parse_stream, session_error

    run = SessionRun(
        stdout=_fixture_text("isolated_marker_preflight_sonnet"), stderr="", exit_code=0
    )

    assert session_error(parse_stream(run.stdout), run, _PREFLIGHT_COPY_ROOT) is None


def test_session_error_reports_infrastructure_failure_before_isolation():
    """Classification runs first: a timed-out ambient session is a timeout."""
    from praxion_evals.live.session import SessionRun, parse_stream, session_error

    run = SessionRun(stdout=_fixture_text("ambient_control_sonnet"), stderr="", exit_code=None)

    error = session_error(parse_stream(run.stdout), run, _PREFLIGHT_COPY_ROOT)

    assert error is not None
    assert error.kind == "timeout"


# ---------------------------------------------------------------------------
# Spend telemetry — the one value the run-level cap sums
# ---------------------------------------------------------------------------


def test_parse_stream_reads_the_exact_session_cost_from_the_final_result():
    import pytest

    from praxion_evals.live.session import parse_stream

    envelope = parse_stream(_fixture_text("spawn_selection_standard_opus"))

    assert envelope.final_result is not None
    assert envelope.final_result.total_cost_usd == pytest.approx(0.243873, abs=5e-7)


# ---------------------------------------------------------------------------
# run_argv / run_session — against a stand-in `claude` on a temporary PATH
# ---------------------------------------------------------------------------

_STAND_IN = """\
import json, os, sys, time
print(json.dumps({"argv": sys.argv[1:], "cwd": os.getcwd(),
                  "home": os.environ.get("HOME"),
                  "claudecode": os.environ.get("CLAUDECODE"),
                  "stdin": sys.stdin.read()}), flush=True)
if os.environ.get("STAND_IN_SLEEP"):
    time.sleep(float(os.environ["STAND_IN_SLEEP"]))
print("stand-in stderr", file=sys.stderr)
sys.exit(int(os.environ.get("STAND_IN_EXIT", "0")))
"""


def _stand_in_env(tmp_path, **extra):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    claude = bin_dir / "claude"
    claude.write_text(f"#!{sys.executable}\n{_STAND_IN}", encoding="utf-8")
    claude.chmod(0o755)
    return {"PATH": str(bin_dir), "HOME": str(tmp_path / "home"), **extra}


def _stand_in_spec(tmp_path, timeout_s=30):
    from praxion_evals.live.session import SessionSpec

    cwd = tmp_path / "fixture"
    cwd.mkdir()
    return SessionSpec(
        prompt="p",
        model="sonnet",
        effort="medium",
        plugin_dir=tmp_path / "copy",
        cwd=cwd,
        permission_mode="default",
        max_budget_usd=1.0,
        timeout_s=timeout_s,
    )


def test_run_session_launches_claude_from_the_given_env_in_the_spec_cwd(tmp_path):
    """The stand-in proves argv, cwd and env reach the child, an ambient
    `CLAUDECODE` does not, and stdin is closed (never the runner's terminal)."""
    from praxion_evals.live.session import build_argv, run_session

    spec = _stand_in_spec(tmp_path)
    env = _stand_in_env(tmp_path, STAND_IN_EXIT="3")

    run = run_session(spec, env)

    seen = json.loads(run.stdout.splitlines()[0])
    assert seen["argv"] == build_argv(spec)[1:]
    assert Path(seen["cwd"]).resolve() == spec.cwd.resolve()
    assert seen["home"] == str(tmp_path / "home")
    assert seen["claudecode"] is None
    assert seen["stdin"] == ""
    assert run.stderr.strip() == "stand-in stderr"
    assert run.exit_code == 3
    assert run.timed_out is False


def test_run_argv_timeout_returns_the_decoded_partial_stdout_and_no_exit_code(tmp_path):
    from praxion_evals.live.session import classify, parse_stream, run_argv

    env = _stand_in_env(tmp_path, STAND_IN_SLEEP="30")
    cwd = tmp_path / "fixture"
    cwd.mkdir()

    run = run_argv(["claude", "-p", "x"], cwd=cwd, env=env, timeout_s=1)

    assert run.exit_code is None
    assert run.timed_out is True
    assert isinstance(run.stdout, str)
    assert json.loads(run.stdout.splitlines()[0])["argv"] == ["-p", "x"]
    assert classify(parse_stream(run.stdout), run.exit_code, run.timed_out) == "timeout"
