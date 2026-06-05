"""Behavioral tests for the stdlib-``urllib`` Anthropic Messages API judge.

No test makes a real network call — :func:`urllib.request.urlopen` is mocked
throughout. The tests pin:

* ``detect_auth()`` precedence (API key wins over OAuth; neither → None),
* the request shape (endpoint, headers, forced tool_choice, model, grounding),
* ``JudgeUnavailable`` on no-auth and on transport error,
* correct header selection per credential type (``x-api-key`` vs Bearer).

The judge must never import the Anthropic SDK nor spawn a subprocess; a
source-level guard test asserts the absence of any such import line.
"""

from __future__ import annotations

import json
import urllib.error
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from scripts.project_metrics.collectors.readiness import judge


# ---------------------------------------------------------------------------
# Helpers.
# ---------------------------------------------------------------------------


def _verdict_response(passed: bool, rationale: str) -> bytes:
    """Build a Messages-API-shaped response body carrying a verdict tool call."""

    document = {
        "id": "msg_test",
        "content": [
            {
                "type": "tool_use",
                "name": "verdict",
                "input": {"passed": passed, "rationale": rationale},
            }
        ],
    }
    return json.dumps(document).encode("utf-8")


class _FakeResponse:
    """Context-manager stand-in for the urlopen response object."""

    def __init__(self, body: bytes) -> None:
        self._body = body

    def __enter__(self) -> "_FakeResponse":
        return self

    def __exit__(self, *exc: object) -> None:
        return None

    def read(self) -> bytes:
        return self._body


def _criterion() -> dict[str, Any]:
    return {
        "id": "c.docs.readme_quality",
        "pillar": "documentation",
        "level": 2,
        "llm": True,
        "rationale": "the README explains setup, usage, and architecture",
    }


# ---------------------------------------------------------------------------
# detect_auth precedence.
# ---------------------------------------------------------------------------


def test_detect_auth_prefers_api_key_over_oauth(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "oauth-test")
    assert judge.detect_auth() == "api_key"


def test_detect_auth_falls_back_to_oauth(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "oauth-test")
    assert judge.detect_auth() == "oauth"


def test_detect_auth_none_when_no_credential(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("CLAUDE_CODE_OAUTH_TOKEN", raising=False)
    assert judge.detect_auth() is None


# ---------------------------------------------------------------------------
# Request shape + headers.
# ---------------------------------------------------------------------------


def test_judge_criterion_posts_to_messages_endpoint_with_api_key_header(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    monkeypatch.delenv("CLAUDE_CODE_OAUTH_TOKEN", raising=False)

    captured: dict[str, Any] = {}

    def _fake_urlopen(request: Any, timeout: int = 0) -> _FakeResponse:
        captured["url"] = request.full_url
        captured["headers"] = dict(request.header_items())
        captured["body"] = json.loads(request.data.decode("utf-8"))
        captured["method"] = request.get_method()
        return _FakeResponse(_verdict_response(True, "looks good"))

    with patch("urllib.request.urlopen", _fake_urlopen):
        result = judge.judge_criterion(_criterion(), "README content", None)

    assert captured["url"] == "https://api.anthropic.com/v1/messages"
    assert captured["method"] == "POST"
    # Header keys are capitalized by urllib's Request; match case-insensitively.
    header_keys = {k.lower(): v for k, v in captured["headers"].items()}
    assert header_keys.get("x-api-key") == "sk-test"
    assert "authorization" not in header_keys
    assert header_keys.get("anthropic-version")
    assert captured["body"]["tool_choice"] == {"type": "tool", "name": "verdict"}
    assert captured["body"]["model"] == judge.DEFAULT_MODEL
    assert result == {
        "passed": True,
        "rationale": "looks good",
        "recommendation": "",
    }


def test_judge_criterion_uses_bearer_header_for_oauth(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "oauth-test")

    captured: dict[str, Any] = {}

    def _fake_urlopen(request: Any, timeout: int = 0) -> _FakeResponse:
        captured["headers"] = {
            k.lower(): v for k, v in dict(request.header_items()).items()
        }
        return _FakeResponse(_verdict_response(False, "missing setup section"))

    with patch("urllib.request.urlopen", _fake_urlopen):
        result = judge.judge_criterion(_criterion(), "README content", None)

    assert captured["headers"].get("authorization") == "Bearer oauth-test"
    assert "x-api-key" not in captured["headers"]
    assert result["passed"] is False


def test_judge_criterion_grounds_on_prior_verdict(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    captured: dict[str, Any] = {}

    def _fake_urlopen(request: Any, timeout: int = 0) -> _FakeResponse:
        captured["body"] = json.loads(request.data.decode("utf-8"))
        return _FakeResponse(_verdict_response(True, "still good"))

    prior = {"passed": True, "rationale": "was good last run"}
    with patch("urllib.request.urlopen", _fake_urlopen):
        judge.judge_criterion(_criterion(), "README content", prior)

    prompt = captured["body"]["messages"][0]["content"]
    assert "Prior verdict" in prompt
    assert "was good last run" in prompt


# ---------------------------------------------------------------------------
# Failure modes → JudgeUnavailable.
# ---------------------------------------------------------------------------


def test_judge_criterion_raises_when_no_auth(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("CLAUDE_CODE_OAUTH_TOKEN", raising=False)
    with pytest.raises(judge.JudgeUnavailable):
        judge.judge_criterion(_criterion(), "README content", None)


def test_judge_criterion_raises_on_urllib_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")

    def _raising_urlopen(request: Any, timeout: int = 0) -> Any:
        raise urllib.error.URLError("connection refused")

    with patch("urllib.request.urlopen", _raising_urlopen):
        with pytest.raises(judge.JudgeUnavailable):
            judge.judge_criterion(_criterion(), "README content", None)


def test_judge_criterion_raises_on_unparseable_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")

    def _bad_urlopen(request: Any, timeout: int = 0) -> _FakeResponse:
        return _FakeResponse(b"not json at all")

    with patch("urllib.request.urlopen", _bad_urlopen):
        with pytest.raises(judge.JudgeUnavailable):
            judge.judge_criterion(_criterion(), "README content", None)


def test_judge_criterion_raises_when_no_verdict_tool_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    body = json.dumps(
        {"content": [{"type": "text", "text": "I cannot decide"}]}
    ).encode("utf-8")

    def _textonly_urlopen(request: Any, timeout: int = 0) -> _FakeResponse:
        return _FakeResponse(body)

    with patch("urllib.request.urlopen", _textonly_urlopen):
        with pytest.raises(judge.JudgeUnavailable):
            judge.judge_criterion(_criterion(), "README content", None)


# ---------------------------------------------------------------------------
# Source-level guard — no anthropic SDK import, no subprocess invocation.
# ---------------------------------------------------------------------------


def test_judge_module_does_not_import_anthropic_sdk() -> None:
    source = Path(judge.__file__).read_text(encoding="utf-8")
    # Build the forbidden module name dynamically so this guard file itself
    # stays clean under the package-wide `grep -r "import <sdk>"` invariant.
    sdk = "anthropic"
    forbidden_prefixes = (f"import {sdk}", f"from {sdk}")
    import_lines = [
        line
        for line in source.splitlines()
        if line.strip().startswith(forbidden_prefixes)
    ]
    assert import_lines == [], (
        f"judge.py must not import the {sdk} SDK; found {import_lines!r}"
    )


def test_judge_module_does_not_invoke_a_subprocess() -> None:
    source = Path(judge.__file__).read_text(encoding="utf-8")
    forbidden_call_tokens = ("subprocess.run", "subprocess.Popen", "os.system(")
    for token in forbidden_call_tokens:
        assert token not in source, (
            f"judge.py must not spawn a subprocess; found {token!r}"
        )
