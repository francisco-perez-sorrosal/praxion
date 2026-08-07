"""Tests for hooks/send_event.py -- the Chronograph relay hook.

Scope note: `task-chronograph-mcp/tests/test_hook_script.py` owns the
`_build_events` event-shape contract (that suite is the relay consumer's, and
it runs in its own CI job). These tests deliberately do *not* re-derive it.
What lives here is the surface that suite does not reach -- port derivation and
worktree resolution, git context capture, the POST failure path, `main()`'s
end-to-end wiring, secret redaction, and the agent-provenance metadata -- plus
the pieces of event assembly that carry that provenance.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Import the hook script via importlib (it lives outside any package)
# ---------------------------------------------------------------------------

HOOK_SCRIPT_PATH = Path(__file__).resolve().parent / "send_event.py"


def _load_hook_module():
    """Load send_event.py as a module. Returns the module or None if loading fails."""
    if not HOOK_SCRIPT_PATH.exists():
        return None
    spec = importlib.util.spec_from_file_location("send_event", HOOK_SCRIPT_PATH)
    if spec is None or spec.loader is None:
        return None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_module = _load_hook_module()

# Guard: if send_event.py does not yet expose _redact_secrets, skip all tests
# gracefully so the test file remains importable during incremental development.
_has_redaction = _module is not None and hasattr(_module, "_redact_secrets")

requires_redaction = pytest.mark.skipif(
    not _has_redaction,
    reason="_redact_secrets not available in send_event.py",
)


@pytest.fixture
def redact_secrets():
    """Provide the _redact_secrets function from the hook module."""
    assert _module is not None
    return _module._redact_secrets


@pytest.fixture
def summarize_tool_input():
    """Provide _summarize_tool_input if available, else skip."""
    if _module is None or not hasattr(_module, "_summarize_tool_input"):
        pytest.skip("_summarize_tool_input not available")
    return _module._summarize_tool_input


@pytest.fixture
def summarize_tool_output():
    """Provide _summarize_tool_output if available, else skip."""
    if _module is None or not hasattr(_module, "_summarize_tool_output"):
        pytest.skip("_summarize_tool_output not available")
    return _module._summarize_tool_output


@pytest.fixture
def classify_mcp_tool():
    """Provide _classify_mcp_tool if available, else skip."""
    if _module is None or not hasattr(_module, "_classify_mcp_tool"):
        pytest.skip("_classify_mcp_tool not available")
    return _module._classify_mcp_tool


# ---------------------------------------------------------------------------
# MCP classification -- Claude plugin and Codex MCP tool names are recognized
# ---------------------------------------------------------------------------


class TestMcpToolClassification:
    """Praxion MCP tool names are classified across supported adapter shapes.

    `task-chronograph` is the only Praxion MCP server that exists. The in-house
    `memory` server was removed by dec-225, so it is exercised below strictly as
    a *historical* name: the classifier still recognizes it because replayed and
    archived event streams predating that removal carry it, and an unclassified
    row there would silently lose its server attribution. Nothing live emits it.
    """

    @pytest.mark.parametrize(
        ("tool_name", "expected"),
        [
            (
                "mcp__plugin_i-am_task-chronograph__report_interaction",
                ("task-chronograph", "report_interaction"),
            ),
            (
                "mcp__task_chronograph__report_interaction",
                ("task_chronograph", "report_interaction"),
            ),
            (
                "mcp__task-chronograph__report_interaction",
                ("task-chronograph", "report_interaction"),
            ),
        ],
        ids=[
            "claude_plugin_chronograph",
            "codex_chronograph_underscore",
            "codex_chronograph_hyphen",
        ],
    )
    def test_praxion_mcp_tool_names_classify(self, classify_mcp_tool, tool_name, expected):
        """Praxion MCP tools return their server and tool components."""
        assert classify_mcp_tool(tool_name) == expected

    def test_retired_memory_server_name_still_classifies_for_historical_streams(
        self, classify_mcp_tool
    ):
        """dec-225 removed the memory server; archived streams still name it."""
        assert classify_mcp_tool("mcp__plugin_i-am_memory__remember") == ("memory", "remember")

    def test_plugin_prefixed_name_without_a_tool_segment_yields_an_empty_tool(
        self, classify_mcp_tool
    ):
        assert classify_mcp_tool("mcp__plugin_i-am_task-chronograph") == ("task-chronograph", "")

    def test_non_praxion_mcp_tool_is_ignored(self, classify_mcp_tool):
        """Non-Praxion MCP tools do not get classified as Praxion events."""
        assert classify_mcp_tool("mcp__github__get_pull_request") is None

    def test_plain_tool_name_is_not_mcp(self, classify_mcp_tool):
        assert classify_mcp_tool("Write") is None

    def test_malformed_mcp_name_without_a_tool_segment_is_ignored(self, classify_mcp_tool):
        assert classify_mcp_tool("mcp__task-chronograph") is None


# ---------------------------------------------------------------------------
# Pattern coverage -- each secret type is redacted
# ---------------------------------------------------------------------------


@requires_redaction
class TestPatternCoverage:
    """Each secret pattern type defined in SECRET_PATTERNS must be redacted."""

    @pytest.mark.parametrize(
        ("secret_input", "description"),
        [
            ("api_key=sk-abc123xyz", "key-value api_key"),
            ("API-KEY: some-secret-value", "header-style API-KEY"),
            ("token=my-secret-token", "key-value token"),
            ("password: hunter2", "key-value password"),
            ("Bearer eyJhbGciOiJIUz.payload.signature", "Bearer token"),
            (
                "sk-TAbCdEfGhIjKlMnOpQrStUvWxYz1234567890ab",
                "OpenAI API key (sk- prefix with 20+ alnum)",
            ),
            (
                "sk-ant-ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefgh",
                "Anthropic API key (sk-ant- prefix with 20+ alnum)",
            ),
            (
                "ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghij",
                "GitHub Personal Access Token",
            ),
            (
                "gho_ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghij",
                "GitHub OAuth token",
            ),
            ("xoxb-1234-5678-abcdef", "Slack bot token"),
            ("AKIAIOSFODNN7EXAMPLE", "AWS access key ID"),
        ],
        ids=[
            "api_key_kv",
            "api_key_header",
            "token_kv",
            "password_kv",
            "bearer",
            "openai_key",
            "anthropic_key",
            "github_pat",
            "github_oauth",
            "slack_token",
            "aws_key",
        ],
    )
    def test_secret_pattern_redacted(self, redact_secrets, secret_input, description):
        """Each known secret pattern is replaced with [REDACTED]."""
        result = redact_secrets(secret_input)
        assert "[REDACTED]" in result, (
            f"Expected secret pattern ({description}) to be redacted, but got: {result!r}"
        )
        # The original secret value should not survive redaction.
        # Extract a distinctive substring from each secret to verify removal.
        # For key=value patterns, the value after the separator should be gone.
        # For prefix patterns, the full match should be replaced.

    def test_openai_key_fully_replaced(self, redact_secrets):
        """An OpenAI-style key is fully replaced, not partially masked."""
        key = "sk-TAbCdEfGhIjKlMnOpQrStUvWxYz1234567890ab"
        result = redact_secrets(f"key is {key} here")
        assert key not in result
        assert "[REDACTED]" in result

    def test_anthropic_key_fully_replaced(self, redact_secrets):
        """An Anthropic-style key is fully replaced, not partially masked."""
        key = "sk-ant-ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefgh"
        result = redact_secrets(f"using {key} for auth")
        assert key not in result
        assert "[REDACTED]" in result

    def test_github_pat_fully_replaced(self, redact_secrets):
        """A GitHub PAT is fully replaced."""
        pat = "ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghij"
        result = redact_secrets(f"token: {pat}")
        assert pat not in result
        assert "[REDACTED]" in result

    def test_github_fine_grained_pat_fully_replaced(self, redact_secrets):
        """A GitHub fine-grained PAT (github_pat_ prefix) is fully replaced."""
        pat = "github_pat_11ABCDEFGH0123456789_abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXY"
        result = redact_secrets(f"token: {pat}")
        assert pat not in result
        assert "[REDACTED]" in result

    def test_aws_key_fully_replaced(self, redact_secrets):
        """An AWS access key ID is fully replaced."""
        result = redact_secrets("AWS_ACCESS_KEY_ID=AKIAIOSFODNN7EXAMPLE")
        assert "AKIAIOSFODNN7EXAMPLE" not in result
        assert "[REDACTED]" in result

    def test_slack_token_fully_replaced(self, redact_secrets):
        """A Slack token is fully replaced."""
        result = redact_secrets("SLACK_TOKEN=xoxb-1234-5678-abcdef")
        assert "xoxb-1234-5678-abcdef" not in result
        assert "[REDACTED]" in result


# ---------------------------------------------------------------------------
# Passthrough -- text without secrets is unchanged
# ---------------------------------------------------------------------------


@requires_redaction
class TestPassthrough:
    """Text without any secret patterns passes through unchanged."""

    def test_plain_text_unchanged(self, redact_secrets):
        text = "This is a normal log message with no secrets."
        assert redact_secrets(text) == text

    def test_empty_string_unchanged(self, redact_secrets):
        assert redact_secrets("") == ""

    def test_code_snippet_unchanged(self, redact_secrets):
        code = "def calculate_total(items): return sum(i.price for i in items)"
        assert redact_secrets(code) == code

    def test_url_without_credentials_unchanged(self, redact_secrets):
        url = "https://example.com/api/v1/users?page=1&limit=10"
        assert redact_secrets(url) == url

    def test_json_without_secrets_unchanged(self, redact_secrets):
        data = json.dumps({"name": "test", "count": 42, "active": True})
        assert redact_secrets(data) == data


# ---------------------------------------------------------------------------
# Multiple secrets -- all are redacted in a single string
# ---------------------------------------------------------------------------


@requires_redaction
class TestMultipleSecrets:
    """When a string contains multiple secrets, all must be redacted."""

    def test_two_different_secret_types_both_redacted(self, redact_secrets):
        text = "api_key=sk-abc123xyz and password: hunter2"
        result = redact_secrets(text)
        assert "sk-abc123xyz" not in result
        assert "hunter2" not in result
        assert result.count("[REDACTED]") >= 2

    def test_three_secrets_all_redacted(self, redact_secrets):
        text = "Config: token=secret123, Bearer eyJhbGciOiJIUz.payload, AKIAIOSFODNN7EXAMPLE"
        result = redact_secrets(text)
        assert "secret123" not in result
        assert "eyJhbGciOiJIUz" not in result
        assert "AKIAIOSFODNN7EXAMPLE" not in result

    def test_same_pattern_repeated(self, redact_secrets):
        text = "password: first and password: second"
        result = redact_secrets(text)
        assert "first" not in result
        assert "second" not in result


# ---------------------------------------------------------------------------
# Case insensitivity -- key-value patterns match any casing
# ---------------------------------------------------------------------------


@requires_redaction
class TestCaseInsensitivity:
    """Key-value patterns (api_key, token, password) must match case-insensitively."""

    @pytest.mark.parametrize(
        "text",
        [
            "API_KEY=secret123",
            "api_key=secret123",
            "Api_Key=secret123",
            "API_key=secret123",
        ],
        ids=["UPPER", "lower", "Title", "Mixed"],
    )
    def test_api_key_case_variants_redacted(self, redact_secrets, text):
        result = redact_secrets(text)
        assert "[REDACTED]" in result
        assert "secret123" not in result

    @pytest.mark.parametrize(
        "text",
        [
            "TOKEN=mytoken",
            "token=mytoken",
            "Token=mytoken",
        ],
        ids=["UPPER", "lower", "Title"],
    )
    def test_token_case_variants_redacted(self, redact_secrets, text):
        result = redact_secrets(text)
        assert "[REDACTED]" in result
        assert "mytoken" not in result

    @pytest.mark.parametrize(
        "text",
        [
            "PASSWORD: hunter2",
            "password: hunter2",
            "Password: hunter2",
        ],
        ids=["UPPER", "lower", "Title"],
    )
    def test_password_case_variants_redacted(self, redact_secrets, text):
        result = redact_secrets(text)
        assert "[REDACTED]" in result
        assert "hunter2" not in result

    def test_bearer_case_insensitive(self, redact_secrets):
        result = redact_secrets("BEARER eyJhbGciOiJIUz.payload")
        assert "[REDACTED]" in result
        assert "eyJhbGciOiJIUz" not in result


# ---------------------------------------------------------------------------
# Integration -- _summarize_tool_input and _summarize_tool_output
#        redact secrets in their output
# ---------------------------------------------------------------------------


@requires_redaction
class TestSummarizeIntegration:
    """Summarize functions must produce output with secrets redacted."""

    def test_summarize_tool_input_redacts_string_input(self, summarize_tool_input):
        """When tool_input is a raw string containing a secret, it is redacted."""
        data = {"tool_input": "api_key=sk-abc123xyz in the command"}
        result = summarize_tool_input(data)
        assert "[REDACTED]" in result
        assert "sk-abc123xyz" not in result

    def test_summarize_tool_input_redacts_command_field(self, summarize_tool_input):
        """When tool_input has a command field with a secret, it is redacted."""
        data = {
            "tool_input": {
                "command": "curl -H 'Authorization: Bearer eyJhbGciOiJIUz' https://api.example.com"
            }
        }
        result = summarize_tool_input(data)
        assert "[REDACTED]" in result
        assert "eyJhbGciOiJIUz" not in result

    def test_summarize_tool_input_redacts_json_fallback(self, summarize_tool_input):
        """When tool_input dict has no known keys, the JSON dump is redacted."""
        data = {"tool_input": {"credentials": "password: hunter2"}}
        result = summarize_tool_input(data)
        assert "hunter2" not in result

    def test_summarize_tool_output_redacts_secrets(self, summarize_tool_output):
        """When tool output contains a secret, it is redacted."""
        data = {"tool_response": "Response includes token=abc123secret"}
        result = summarize_tool_output(data)
        assert "[REDACTED]" in result
        assert "abc123secret" not in result

    def test_summarize_tool_output_no_secrets_unchanged(self, summarize_tool_output):
        """When tool output has no secrets, it passes through."""
        data = {"tool_response": "File written successfully"}
        result = summarize_tool_output(data)
        assert result == "File written successfully"

    def test_summarize_tool_input_no_secrets_unchanged(self, summarize_tool_input):
        """When tool_input has no secrets, it passes through."""
        data = {"tool_input": {"file_path": "/project/src/main.py"}}
        result = summarize_tool_input(data)
        assert "file_path=/project/src/main.py" in result


# ---------------------------------------------------------------------------
# Fixtures for the process-level surfaces (port, git context, main)
# ---------------------------------------------------------------------------


@pytest.fixture
def hook():
    """The loaded send_event module."""
    assert _module is not None
    return _module


@pytest.fixture
def main_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "main"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.email", "t@example.com"], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.name", "test"], check=True)
    (repo / "README.md").write_text("seed\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-q", "-m", "init"], check=True)
    return repo


@pytest.fixture
def linked_worktree(main_repo: Path, tmp_path: Path) -> Path:
    wt = tmp_path / "linked"
    subprocess.run(
        ["git", "-C", str(main_repo), "worktree", "add", "-q", str(wt), "-b", "feature"],
        check=True,
    )
    return wt


# ---------------------------------------------------------------------------
# Port derivation -- must agree with the server, and be worktree-stable
# ---------------------------------------------------------------------------


class TestPortDerivation:
    def test_same_project_dir_always_derives_the_same_port(self, hook):
        assert hook._derive_port("/a/b/c") == hook._derive_port("/a/b/c")

    def test_different_project_dirs_derive_different_ports(self, hook):
        assert hook._derive_port("/a/b/c") != hook._derive_port("/a/b/d")

    def test_derived_port_stays_inside_the_declared_range(self, hook):
        port = hook._derive_port("/some/project")
        assert hook.DEFAULT_PORT <= port < hook.DEFAULT_PORT + hook.PORT_RANGE_SIZE

    def test_empty_project_dir_uses_the_default_port(self, hook):
        assert hook._derive_port("") == hook.DEFAULT_PORT

    def test_relative_and_absolute_forms_of_one_path_agree(self, hook, monkeypatch, tmp_path):
        monkeypatch.chdir(tmp_path)
        assert hook._derive_port(".") == hook._derive_port(str(tmp_path))


class TestProjectRootResolution:
    def test_regular_checkout_resolves_to_itself(self, hook, main_repo: Path):
        assert Path(hook._resolve_project_root(str(main_repo))).resolve() == main_repo.resolve()

    def test_worktree_resolves_to_the_main_repo_so_the_port_matches(
        self, hook, main_repo: Path, linked_worktree: Path
    ):
        """A worktree session must POST to the same chronograph instance as the
        canonical checkout -- otherwise its spans land in a second server."""
        resolved = Path(hook._resolve_project_root(str(linked_worktree))).resolve()
        assert resolved == main_repo.resolve()
        assert hook._derive_port(str(resolved)) == hook._derive_port(str(main_repo))

    def test_non_git_directory_falls_back_to_the_given_path(self, hook, tmp_path: Path):
        plain = tmp_path / "plain"
        plain.mkdir()
        assert hook._resolve_project_root(str(plain)) == str(plain)

    def test_empty_cwd_is_returned_unchanged(self, hook):
        assert hook._resolve_project_root("") == ""

    def test_missing_git_binary_falls_back_to_the_given_path(self, hook, monkeypatch, tmp_path):
        def _missing(*_a, **_k):
            raise FileNotFoundError("git")

        monkeypatch.setattr(hook.subprocess, "check_output", _missing)
        assert hook._resolve_project_root(str(tmp_path)) == str(tmp_path)


# ---------------------------------------------------------------------------
# Git context capture -- fail-open, worktree-aware
# ---------------------------------------------------------------------------


class TestGitContext:
    def test_main_checkout_reports_branch_toplevel_and_not_a_worktree(self, hook, main_repo: Path):
        context = hook._git_context(str(main_repo))
        assert context["git_branch"]
        assert Path(context["git_toplevel"]).resolve() == main_repo.resolve()
        assert context["is_worktree"] is False
        assert "worktree_name" not in context

    def test_linked_worktree_is_flagged_and_named(self, hook, linked_worktree: Path):
        context = hook._git_context(str(linked_worktree))
        assert context["is_worktree"] is True
        assert context["worktree_name"] == linked_worktree.name

    def test_non_git_directory_yields_an_empty_context(self, hook, tmp_path: Path):
        plain = tmp_path / "plain"
        plain.mkdir()
        assert hook._git_context(str(plain)) == {}

    def test_empty_cwd_yields_an_empty_context(self, hook):
        assert hook._git_context("") == {}


# ---------------------------------------------------------------------------
# Agent provenance -- a relay consumer must be able to tell a real agent_type
# from a fallback label wearing the same field
# ---------------------------------------------------------------------------


class TestAgentProvenance:
    def test_supplied_agent_type_is_marked_as_coming_from_the_payload(self, hook):
        assert hook._agent_type_source({"agent_type": "i-am:researcher"}) == hook.SOURCE_PAYLOAD

    def test_description_fallback_is_named_as_such(self, hook):
        assert (
            hook._agent_type_source({"agent_type": "", "description": "Audit hooks"})
            == hook.SOURCE_DESCRIPTION_FALLBACK
        )

    def test_agent_id_fallback_is_named_as_such(self, hook):
        assert hook._agent_type_source({"agent_id": "abc123"}) == hook.SOURCE_AGENT_ID_FALLBACK

    def test_nothing_available_is_reported_as_unresolved(self, hook):
        assert hook._agent_type_source({}) == hook.SOURCE_UNRESOLVED

    def test_whitespace_only_agent_type_is_not_treated_as_supplied(self, hook):
        assert hook._agent_type_source({"agent_type": "   "}) != hook.SOURCE_PAYLOAD

    def test_subagent_stop_carries_the_provenance_marker(self, hook):
        events, _ = hook._build_events(
            {
                "hook_event_name": "SubagentStop",
                "session_id": "s1",
                "agent_id": "a1",
                "agent_type": "",
            }
        )
        assert events[0]["metadata"]["agent_type_source"] == hook.SOURCE_AGENT_ID_FALLBACK

    def test_subagent_stop_keeps_the_transcript_path_alongside_the_provenance(self, hook):
        events, _ = hook._build_events(
            {
                "hook_event_name": "SubagentStop",
                "session_id": "s1",
                "agent_id": "a1",
                "agent_type": "i-am:verifier",
                "agent_transcript_path": "/tmp/t.md",
            }
        )
        metadata = events[0]["metadata"]
        assert metadata["agent_transcript_path"] == "/tmp/t.md"
        assert metadata["agent_type_source"] == hook.SOURCE_PAYLOAD

    def test_subagent_start_carries_the_provenance_marker(self, hook):
        events, _ = hook._build_events(
            {"hook_event_name": "SubagentStart", "session_id": "s1", "agent_type": "i-am:sentinel"}
        )
        assert events[0]["metadata"]["agent_type_source"] == hook.SOURCE_PAYLOAD

    @pytest.mark.parametrize("hook_event", ["SubagentStart", "SubagentStop"])
    def test_lifecycle_events_never_carry_an_empty_agent_id(self, hook, hook_event):
        """A lifecycle span keyed on "" cannot be correlated with anything."""
        events, _ = hook._build_events({"hook_event_name": hook_event, "session_id": "s1"})
        assert events[0]["agent_id"] == "s1"

    @pytest.mark.parametrize("hook_event", ["SubagentStart", "SubagentStop"])
    def test_lifecycle_events_with_no_identifier_at_all_use_the_sentinel(self, hook, hook_event):
        events, _ = hook._build_events({"hook_event_name": hook_event})
        assert events[0]["agent_id"] == hook.UNKNOWN_AGENT_ID


class TestAgentLabel:
    def test_agent_type_wins(self, hook):
        assert hook._agent_label({"agent_type": "i-am:researcher"}) == "i-am:researcher"

    def test_description_is_preferred_over_the_uuid_like_agent_id(self, hook):
        assert hook._agent_label({"description": "Audit", "agent_id": "abc"}) == "Audit"

    def test_long_description_is_truncated_to_fifty_characters(self, hook):
        assert len(hook._agent_label({"description": "x" * 200})) == 50

    def test_agent_id_is_the_last_real_option(self, hook):
        assert hook._agent_label({"agent_id": "abc123"}) == "abc123"

    def test_empty_payload_yields_the_sentinel(self, hook):
        assert hook._agent_label({}) == hook.UNKNOWN_AGENT_ID


# ---------------------------------------------------------------------------
# PROGRESS.md parsing
# ---------------------------------------------------------------------------


class TestProgressLineParsing:
    def test_full_phase_line_is_parsed_into_its_components(self, hook):
        content = "[2026-08-06T12:00:00Z] [implementer] Phase 3/8: build -- wired the emitter #x"
        parsed = hook._parse_last_progress_line(content)
        assert parsed == {
            "agent_type": "implementer",
            "phase": 3,
            "total_phases": 8,
            "phase_name": "build",
            "message": "wired the emitter",
        }

    def test_line_without_a_phase_clause_parses_with_zero_phases(self, hook):
        parsed = hook._parse_last_progress_line("[ts] [verifier] finished the review")
        assert parsed["agent_type"] == "verifier"
        assert parsed["phase"] == 0
        assert parsed["total_phases"] == 0
        assert parsed["phase_name"] == ""

    def test_only_the_last_non_empty_line_is_parsed(self, hook):
        content = "[t] [a] first\n\n[t] [b] second\n\n"
        assert hook._parse_last_progress_line(content)["agent_type"] == "b"

    def test_empty_content_yields_none(self, hook):
        assert hook._parse_last_progress_line("   \n\n") is None

    def test_unparseable_last_line_yields_none(self, hook):
        assert hook._parse_last_progress_line("no brackets here") is None

    def test_progress_write_emits_a_phase_transition_event(self, hook):
        events, _ = hook._build_events(
            {
                "hook_event_name": "PostToolUse",
                "session_id": "s1",
                "tool_name": "Write",
                "tool_input": {
                    "file_path": "/p/.ai-work/slug/PROGRESS.md",
                    "content": "[t] [test-engineer] Phase 4/8: verify -- suite green",
                },
            }
        )
        transitions = [e for e in events if e["event_type"] == "phase_transition"]
        assert len(transitions) == 1
        assert transitions[0]["phase"] == 4
        assert transitions[0]["phase_name"] == "verify"

    def test_progress_write_with_unparseable_content_emits_no_transition(self, hook):
        events, _ = hook._build_events(
            {
                "hook_event_name": "PostToolUse",
                "session_id": "s1",
                "tool_name": "Write",
                "tool_input": {"file_path": "/p/PROGRESS.md", "content": "garbage"},
            }
        )
        assert all(e["event_type"] != "phase_transition" for e in events)

    def test_progress_edit_reads_the_new_string_field(self, hook):
        content = hook._extract_progress_content({"new_string": "[t] [a] Phase 1/2: x -- y"})
        assert content.startswith("[t]")

    def test_non_dict_tool_input_yields_no_progress_content(self, hook):
        assert hook._extract_progress_content("a string") == ""


# ---------------------------------------------------------------------------
# Size accounting and truncation
# ---------------------------------------------------------------------------


class TestSizeAccounting:
    def test_short_text_is_not_truncated(self, hook):
        assert hook._truncate("short") == "short"

    def test_empty_text_becomes_an_empty_string(self, hook):
        assert hook._truncate(None) == ""

    def test_oversized_text_is_cut_and_marked(self, hook):
        result = hook._truncate("y" * 5000, max_bytes=100)
        assert result.endswith("...")
        assert len(result) == 103

    def test_string_tool_input_is_returned_verbatim(self, hook):
        assert hook._raw_tool_input_text({"tool_input": "raw command"}) == "raw command"

    def test_known_input_keys_are_joined(self, hook):
        text = hook._raw_tool_input_text({"tool_input": {"file_path": "/a", "command": "ls"}})
        assert "file_path=/a" in text
        assert "command=ls" in text

    def test_unknown_input_keys_fall_back_to_json(self, hook):
        assert hook._raw_tool_input_text({"tool_input": {"zzz": 1}}) == '{"zzz": 1}'

    def test_dict_tool_output_is_serialized(self, hook):
        assert hook._raw_tool_output_text({"tool_response": {"ok": True}}) == '{"ok": true}'

    def test_absent_tool_output_is_an_empty_string(self, hook):
        assert hook._raw_tool_output_text({}) == ""

    def test_legacy_tool_output_key_is_read(self, hook):
        assert hook._raw_tool_output_text({"tool_output": "done"}) == "done"

    def test_recorded_sizes_reflect_the_untruncated_input(self, hook):
        """Truncation must not shrink the size signal span analytics rely on."""
        events, _ = hook._build_events(
            {
                "hook_event_name": "PostToolUse",
                "session_id": "s1",
                "tool_name": "Bash",
                "tool_input": {"command": "z" * 9000},
                "tool_response": "w" * 9000,
            }
        )
        metadata = events[0]["metadata"]
        assert metadata["input_size_bytes"] > 9000
        assert metadata["output_size_bytes"] == 9000
        assert len(metadata["input_summary"]) < 9000


class TestProjectDir:
    def test_payload_cwd_wins(self, hook, monkeypatch):
        monkeypatch.setenv("CLAUDE_PROJECT_DIR", "/from/env")
        assert hook._project_dir({"cwd": "/from/payload"}) == "/from/payload"

    def test_environment_is_the_fallback(self, hook, monkeypatch):
        monkeypatch.setenv("CLAUDE_PROJECT_DIR", "/from/env")
        assert hook._project_dir({}) == "/from/env"

    def test_neither_available_yields_an_empty_string(self, hook, monkeypatch):
        monkeypatch.delenv("CLAUDE_PROJECT_DIR", raising=False)
        assert hook._project_dir({}) == ""


class TestTaskSlugExtraction:
    def test_slug_is_extracted_from_free_text(self, hook):
        assert hook._extract_task_slug("blah\n\nTask slug: auth-flow\nmore") == "auth-flow"

    def test_absent_slug_yields_an_empty_string(self, hook):
        assert hook._extract_task_slug("no slug here") == ""

    def test_empty_description_yields_an_empty_string(self, hook):
        assert hook._extract_task_slug("") == ""


# ---------------------------------------------------------------------------
# POST transport -- must never raise into the hook
# ---------------------------------------------------------------------------


class TestPostTransport:
    def test_successful_post_sends_json_to_the_derived_port(self, hook, monkeypatch):
        sent = {}

        def _fake_urlopen(req, timeout=None):
            sent["url"] = req.full_url
            sent["body"] = json.loads(req.data.decode())
            sent["content_type"] = req.headers.get("Content-type")
            return None

        monkeypatch.setattr(hook.urllib.request, "urlopen", _fake_urlopen)
        hook._post(9123, "/api/events", {"event_type": "tool_use"})

        assert sent["url"] == "http://localhost:9123/api/events"
        assert sent["body"] == {"event_type": "tool_use"}
        assert sent["content_type"] == "application/json"

    def test_unreachable_relay_is_logged_and_swallowed(self, hook, monkeypatch, capsys):
        """A dead chronograph must never surface as a hook failure."""

        def _refused(_req, timeout=None):
            raise OSError("connection refused")

        monkeypatch.setattr(hook.urllib.request, "urlopen", _refused)
        hook._post(9123, "/api/events", {})

        assert "chronograph: POST /api/events to :9123 failed" in capsys.readouterr().err


# ---------------------------------------------------------------------------
# main() -- end-to-end wiring
# ---------------------------------------------------------------------------


def _drive_main(hook, payload, monkeypatch, raw: str | None = None):
    """Run main() in-process, capturing everything it would POST."""
    posted: list[tuple[int, str, dict]] = []
    monkeypatch.setattr(hook, "_post", lambda port, path, body: posted.append((port, path, body)))
    monkeypatch.setattr(
        sys, "stdin", __import__("io").StringIO(raw if raw is not None else json.dumps(payload))
    )
    hook.main()
    return posted


class TestMainWiring:
    def test_observability_opt_out_posts_nothing(self, hook, monkeypatch):
        monkeypatch.setenv("PRAXION_DISABLE_OBSERVABILITY", "1")
        assert _drive_main(hook, {"hook_event_name": "SessionStart"}, monkeypatch) == []

    def test_malformed_stdin_posts_nothing_and_does_not_raise(self, hook, monkeypatch):
        monkeypatch.delenv("PRAXION_DISABLE_OBSERVABILITY", raising=False)
        assert _drive_main(hook, None, monkeypatch, raw="{{{ not json") == []

    def test_unknown_hook_event_posts_nothing(self, hook, monkeypatch):
        monkeypatch.delenv("PRAXION_DISABLE_OBSERVABILITY", raising=False)
        assert _drive_main(hook, {"hook_event_name": "Nonesuch"}, monkeypatch) == []

    def test_explicit_port_env_overrides_the_derived_port(self, hook, monkeypatch):
        monkeypatch.delenv("PRAXION_DISABLE_OBSERVABILITY", raising=False)
        monkeypatch.setenv("CHRONOGRAPH_PORT", "9999")
        posted = _drive_main(
            hook, {"hook_event_name": "SessionStart", "session_id": "s1"}, monkeypatch
        )
        assert [p for p, _, _ in posted] == [9999]

    def test_events_and_interactions_go_to_their_own_endpoints(self, hook, monkeypatch):
        monkeypatch.delenv("PRAXION_DISABLE_OBSERVABILITY", raising=False)
        monkeypatch.setenv("CHRONOGRAPH_PORT", "9999")
        posted = _drive_main(
            hook,
            {
                "hook_event_name": "SubagentStart",
                "session_id": "s1",
                "agent_id": "a1",
                "agent_type": "i-am:researcher",
            },
            monkeypatch,
        )
        paths = [path for _, path, _ in posted]
        assert paths == ["/api/events", "/api/interactions"]

    def test_every_event_is_tagged_with_the_hook_that_produced_it(self, hook, monkeypatch):
        monkeypatch.delenv("PRAXION_DISABLE_OBSERVABILITY", raising=False)
        monkeypatch.setenv("CHRONOGRAPH_PORT", "9999")
        posted = _drive_main(
            hook,
            {
                "hook_event_name": "PostToolUse",
                "session_id": "s1",
                "tool_name": "Write",
                "tool_use_id": "t1",
                "tool_input": {"file_path": "/p/x.py"},
            },
            monkeypatch,
        )
        assert posted[0][2]["metadata"]["hook_event"] == "PostToolUse"

    def test_an_internal_failure_is_reported_and_swallowed(self, hook, monkeypatch, capsys):
        """Exit 0 unconditionally -- the hook must never block agent execution."""
        monkeypatch.delenv("PRAXION_DISABLE_OBSERVABILITY", raising=False)
        monkeypatch.delenv("CHRONOGRAPH_PORT", raising=False)

        def _boom(_data):
            raise RuntimeError("kaboom")

        monkeypatch.setattr(hook, "_build_events", _boom)
        monkeypatch.setattr(sys, "stdin", __import__("io").StringIO('{"hook_event_name": "Stop"}'))

        hook.main()

        assert "kaboom" in capsys.readouterr().err


class TestPreToolUseSpans:
    def test_pre_tool_use_without_a_correlation_id_opens_no_span(self, hook):
        """No tool_use_id means Pre/Post cannot be paired; PostToolUse emits an
        instant span instead of leaving a dangling one open."""
        events, _ = hook._build_events(
            {"hook_event_name": "PreToolUse", "session_id": "s1", "tool_name": "Write"}
        )
        assert events == []

    def test_pre_tool_use_with_a_correlation_id_opens_a_tool_start(self, hook):
        events, _ = hook._build_events(
            {
                "hook_event_name": "PreToolUse",
                "session_id": "s1",
                "tool_name": "Write",
                "tool_use_id": "t1",
                "tool_input": {"file_path": "/p/x.py"},
            }
        )
        assert events[0]["event_type"] == "tool_start"
        assert events[0]["metadata"]["input_size_bytes"] > 0


class TestFailureEvents:
    def test_dict_error_payload_is_serialized_into_the_message(self, hook):
        events, _ = hook._build_events(
            {
                "hook_event_name": "PostToolUseFailure",
                "session_id": "s1",
                "tool_name": "Bash",
                "error": {"code": 1, "reason": "boom"},
            }
        )
        assert events[0]["event_type"] == "error"
        assert "boom" in events[0]["message"]

    def test_absent_error_field_gets_a_default_message(self, hook):
        events, _ = hook._build_events(
            {"hook_event_name": "PostToolUseFailure", "session_id": "s1", "tool_name": "Bash"}
        )
        assert events[0]["message"] == "Tool call failed"
