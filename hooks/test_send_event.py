"""Tests for secret redaction in hooks/send_event.py.

Verifies that the hook redacts common secret patterns (API keys, tokens,
bearer credentials, AWS/GitHub/Slack identifiers) from tool input and output
before transmission to the observability relay.
"""

from __future__ import annotations

import importlib.util
import json
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
    """Praxion MCP tool names are classified across supported adapter shapes."""

    @pytest.mark.parametrize(
        ("tool_name", "expected"),
        [
            (
                "mcp__plugin_i-am_memory__remember",
                ("memory", "remember"),
            ),
            (
                "mcp__memory__remember",
                ("memory", "remember"),
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
            "claude_plugin_memory",
            "codex_memory",
            "codex_task_chronograph_underscore",
            "codex_task_chronograph_hyphen",
        ],
    )
    def test_praxion_mcp_tool_names_classify(self, classify_mcp_tool, tool_name, expected):
        """Praxion MCP tools return their server and tool components."""
        assert classify_mcp_tool(tool_name) == expected

    def test_non_praxion_mcp_tool_is_ignored(self, classify_mcp_tool):
        """Non-Praxion MCP tools do not get classified as Praxion events."""
        assert classify_mcp_tool("mcp__github__get_pull_request") is None


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
