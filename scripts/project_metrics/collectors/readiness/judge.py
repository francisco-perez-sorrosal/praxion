"""Stdlib-``urllib`` Anthropic Messages API judge for the LLM-scored criteria.

This module deliberately does **not** import the ``anthropic`` SDK and never
spawns a subprocess (no ``claude`` CLI, no ``uv run``). It POSTs directly to
``https://api.anthropic.com/v1/messages`` using :mod:`urllib.request`, keeping
the metrics package's zero-third-party-dependency contract intact — the
capability ships to every managed project via the plugin alone, with no
``pyproject.toml`` edit and no ``install.sh`` change.

Auth precedence (mirrors the eval harness, but never takes the Agent-SDK /
``claude`` subprocess route that the deadlock guard forbids under a Claude
Code session):

* ``ANTHROPIC_API_KEY`` set → ``x-api-key`` header.
* else ``CLAUDE_CODE_OAUTH_TOKEN`` set → ``Authorization: Bearer`` header.
* else → :class:`JudgeUnavailableError`.

The judge uses a forced ``tool_choice`` ("verdict" tool) so the model returns
structured ``{passed: bool, rationale: str}`` rather than free text. Any
no-auth, network, or parse failure raises :class:`JudgeUnavailableError`; the
caller decides whether to degrade gracefully or hard-fail.

Tokens are read at call time and used only in request headers — never logged,
never written to any report or ``.ai-state/`` file.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any

__all__ = [
    "DEFAULT_MODEL",
    "JudgeUnavailableError",
    "detect_auth",
    "judge_criterion",
]


class JudgeUnavailableError(RuntimeError):
    """Raised when the LLM judge cannot run (no auth, network, or parse error)."""


# ---------------------------------------------------------------------------
# Constants — endpoint, headers, model, and request sizing.
# ---------------------------------------------------------------------------

_MESSAGES_ENDPOINT: str = "https://api.anthropic.com/v1/messages"
_ANTHROPIC_VERSION: str = "2023-06-01"
DEFAULT_MODEL: str = "claude-haiku-4-5"
_MAX_TOKENS: int = 1024
_DEFAULT_TIMEOUT_SECONDS: int = 30

_ENV_API_KEY: str = "ANTHROPIC_API_KEY"
_ENV_OAUTH: str = "CLAUDE_CODE_OAUTH_TOKEN"

_VERDICT_TOOL_NAME: str = "verdict"
_VERDICT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "passed": {
            "type": "boolean",
            "description": "Whether the artifact satisfies the criterion.",
        },
        "rationale": {
            "type": "string",
            "description": "One- or two-sentence justification for the verdict.",
        },
        "recommendation": {
            "type": "string",
            "description": (
                "When 'passed' is false, one concrete, project-specific next step "
                "the maintainer can take to satisfy the criterion, grounded in the "
                "artifact under evaluation. Empty string when 'passed' is true."
            ),
        },
    },
    "required": ["passed", "rationale"],
}


# ---------------------------------------------------------------------------
# Auth detection.
# ---------------------------------------------------------------------------


def detect_auth() -> str | None:
    """Return the auth mode: ``"api_key"``, ``"oauth"``, or ``None``.

    Precedence: ``ANTHROPIC_API_KEY`` wins over ``CLAUDE_CODE_OAUTH_TOKEN``.
    Never spawns a subprocess and never inspects anything beyond the two
    environment variables.
    """

    if os.environ.get(_ENV_API_KEY):
        return "api_key"
    if os.environ.get(_ENV_OAUTH):
        return "oauth"
    return None


def _auth_headers() -> dict[str, str]:
    """Build the auth + version headers for the detected credential.

    API keys go in ``x-api-key``; OAuth tokens go in ``Authorization: Bearer``.
    Raises :class:`JudgeUnavailableError` when neither credential is present.
    """

    api_key = os.environ.get(_ENV_API_KEY)
    if api_key:
        return {
            "x-api-key": api_key,
            "anthropic-version": _ANTHROPIC_VERSION,
            "content-type": "application/json",
        }
    oauth = os.environ.get(_ENV_OAUTH)
    if oauth:
        return {
            "Authorization": f"Bearer {oauth}",
            "anthropic-version": _ANTHROPIC_VERSION,
            "content-type": "application/json",
        }
    raise JudgeUnavailableError(
        f"no Anthropic credential found ({_ENV_API_KEY} or {_ENV_OAUTH} must be set)"
    )


# ---------------------------------------------------------------------------
# Prompt + request body.
# ---------------------------------------------------------------------------


def _build_prompt(
    criterion: dict[str, Any], artifact: str, prior_verdict: dict[str, Any] | None
) -> str:
    """Compose the judge prompt, grounding on a prior verdict when present.

    Grounding keeps run-to-run variance low: the model is shown its previous
    verdict and asked to change it only on clear evidence.
    """

    crit_id = criterion.get("id", "<unknown>")
    rationale = criterion.get("rationale", "")
    lines = [
        "You are evaluating one agent-readiness criterion against a project artifact.",
        f"Criterion id: {crit_id}",
        f"Criterion intent: {rationale}",
        "",
        "Artifact under evaluation:",
        "---",
        artifact,
        "---",
    ]
    if prior_verdict is not None:
        prior_passed = prior_verdict.get("passed")
        prior_rationale = prior_verdict.get("rationale", "")
        lines.extend(
            [
                "",
                "Prior verdict for this criterion (change only on clear evidence):",
                f"  passed={prior_passed}; rationale={prior_rationale!r}",
            ]
        )
    lines.extend(
        [
            "",
            "Call the 'verdict' tool with a boolean 'passed' and a short 'rationale'.",
            "If 'passed' is false, also set 'recommendation' to one concrete, "
            "actionable next step tailored to this artifact (not generic advice); "
            "leave it empty when 'passed' is true.",
        ]
    )
    return "\n".join(lines)


def _build_request_body(
    criterion: dict[str, Any],
    artifact: str,
    prior_verdict: dict[str, Any] | None,
    model: str,
) -> dict[str, Any]:
    """Assemble the Messages API request body with a forced verdict tool."""

    return {
        "model": model,
        "max_tokens": _MAX_TOKENS,
        "tools": [
            {
                "name": _VERDICT_TOOL_NAME,
                "description": "Structured pass/fail verdict for a readiness criterion.",
                "input_schema": _VERDICT_SCHEMA,
            }
        ],
        "tool_choice": {"type": "tool", "name": _VERDICT_TOOL_NAME},
        "messages": [
            {
                "role": "user",
                "content": _build_prompt(criterion, artifact, prior_verdict),
            }
        ],
    }


# ---------------------------------------------------------------------------
# Public entry point.
# ---------------------------------------------------------------------------


def judge_criterion(
    criterion: dict[str, Any],
    artifact: str,
    prior_verdict: dict[str, Any] | None,
    *,
    model: str = DEFAULT_MODEL,
    timeout_s: int = _DEFAULT_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    """Judge one criterion against ``artifact``; return ``{passed, rationale}``.

    POSTs to the Anthropic Messages API via :func:`urllib.request.urlopen` with
    a forced verdict tool. Grounds on ``prior_verdict`` when supplied. Raises
    :class:`JudgeUnavailableError` on missing auth, any network/HTTP error, or a
    response that does not carry a parseable verdict tool call.
    """

    headers = _auth_headers()
    body = _build_request_body(criterion, artifact, prior_verdict, model)
    payload = json.dumps(body).encode("utf-8")
    request = urllib.request.Request(
        _MESSAGES_ENDPOINT, data=payload, headers=headers, method="POST"
    )

    try:
        with urllib.request.urlopen(request, timeout=timeout_s) as response:
            raw = response.read()
    except (urllib.error.URLError, OSError, TimeoutError) as exc:
        raise JudgeUnavailableError(f"Anthropic Messages API request failed: {exc}") from exc

    return _parse_verdict(raw)


def _parse_verdict(raw: bytes) -> dict[str, Any]:
    """Extract ``{passed, rationale}`` from a Messages API response body.

    The forced tool_choice guarantees a ``tool_use`` content block named
    ``verdict``; this reads its ``input``. Any structural surprise (non-JSON,
    missing block, wrong shape) raises :class:`JudgeUnavailableError` so the caller
    treats it as a judge failure rather than a silent bad verdict.
    """

    try:
        document = json.loads(raw.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise JudgeUnavailableError(f"judge response was not valid JSON: {exc}") from exc

    content = document.get("content")
    if not isinstance(content, list):
        raise JudgeUnavailableError("judge response missing a content list")

    for block in content:
        if (
            isinstance(block, dict)
            and block.get("type") == "tool_use"
            and block.get("name") == _VERDICT_TOOL_NAME
        ):
            verdict = block.get("input")
            if not isinstance(verdict, dict) or "passed" not in verdict:
                raise JudgeUnavailableError("verdict tool call carried no usable input")
            return {
                "passed": bool(verdict["passed"]),
                "rationale": str(verdict.get("rationale", "")),
                "recommendation": str(verdict.get("recommendation", "")),
            }

    raise JudgeUnavailableError("judge response contained no 'verdict' tool call")
