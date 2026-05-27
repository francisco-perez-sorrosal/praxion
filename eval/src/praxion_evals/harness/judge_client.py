"""JudgeClient ABC and concrete implementations.

Auth-mode selection is runtime, driven by environment variables:
    CLAUDE_CODE_OAUTH_TOKEN set  → AgentSdkJudgeClient
    ANTHROPIC_API_KEY set        → MessagesApiJudgeClient
    Neither                      → RuntimeError naming both vars

Both SDK imports are deferred inside the relevant class __init__ / judge()
so that importing this module never fails even when neither SDK is installed.
Family code must never import claude_agent_sdk or anthropic directly — all
calls flow through this module.
"""

from __future__ import annotations

import asyncio
import os
from abc import ABC, abstractmethod

from praxion_evals.harness.schemas import JudgeVerdict

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_ENV_OAUTH = "CLAUDE_CODE_OAUTH_TOKEN"
_ENV_API_KEY = "ANTHROPIC_API_KEY"

_DEFAULT_MODEL = "claude-haiku-4-5"
_JUDGE_MAX_TOKENS = 1024


# ---------------------------------------------------------------------------
# ABC
# ---------------------------------------------------------------------------


class JudgeClient(ABC):
    """Adapter that encapsulates the auth-mode seam.

    Concrete subclasses implement judge() using a specific SDK.
    Family code always calls this abstract method — never the SDK directly.
    """

    @abstractmethod
    def judge(self, rubric: str, artifact: str, schema: dict) -> JudgeVerdict:  # type: ignore[type-arg]
        """Send rubric + artifact to an LLM and return a parsed verdict.

        Args:
            rubric: Instruction text describing what to evaluate.
            artifact: The content being judged (ADR, SPEC, report excerpt, …).
            schema: JSON Schema dict that the LLM response must conform to.
                    Must have a ``verdict`` field of enum [PASS, WARN, FAIL],
                    a ``findings`` array of strings, and a ``score`` integer.

        Returns:
            JudgeVerdict with parsed fields from the structured response.

        Raises:
            ValueError: If the response is missing required fields
                        (``verdict``, ``findings``, ``score``).
        """


# ---------------------------------------------------------------------------
# Agent SDK implementation
# ---------------------------------------------------------------------------


class AgentSdkJudgeClient(JudgeClient):
    """Routes via claude-agent-sdk with allowed_tools=[] (read-only agent).

    The SDK import is deferred to judge() so that importing this module
    never fails when claude_agent_sdk is absent.  Construction raises
    ImportError only when the module is explicitly blocked in sys.modules
    (the None-sentinel case used in tests and explicit opt-out scenarios).
    """

    def __init__(self) -> None:
        import sys

        # If the module entry exists but is explicitly set to None, the SDK is
        # intentionally blocked — fail fast at construction time rather than
        # silently succeeding and then crashing on the first judge() call.
        if sys.modules.get("claude_agent_sdk") is None and "claude_agent_sdk" in sys.modules:
            raise ImportError(
                "claude-agent-sdk is blocked (sys.modules['claude_agent_sdk'] is None). "
                "Install it with: pip install claude-agent-sdk"
            )

    def judge(self, rubric: str, artifact: str, schema: dict) -> JudgeVerdict:  # type: ignore[type-arg]
        """Call the Agent SDK with output_format=json_schema and parse the result."""
        try:
            import claude_agent_sdk  # type: ignore[import-untyped]
        except ImportError as exc:
            raise ImportError(
                "claude-agent-sdk is required for the OAuth token auth route. "
                "Install it with: pip install claude-agent-sdk"
            ) from exc

        sdk = claude_agent_sdk
        prompt = _build_prompt(rubric, artifact)
        options = sdk.ClaudeAgentOptions(
            allowed_tools=[],
            output_format={"type": "json_schema", "schema": schema},
        )

        raw: dict = {}  # type: ignore[type-arg]

        async def _run() -> None:
            nonlocal raw
            async for message in sdk.query(prompt=prompt, options=options):
                structured = getattr(message, "structured_output", None)
                if structured is not None:
                    raw = dict(structured)

        asyncio.run(_run())
        return _parse_verdict(raw)


# ---------------------------------------------------------------------------
# Messages API implementation
# ---------------------------------------------------------------------------


class MessagesApiJudgeClient(JudgeClient):
    """Routes via anthropic.Anthropic().messages.create() with tool-call-as-output.

    The anthropic SDK is imported lazily inside judge() so that importing
    this module never fails when the anthropic package is absent.
    """

    def judge(self, rubric: str, artifact: str, schema: dict) -> JudgeVerdict:  # type: ignore[type-arg]
        """Call the Messages API with a forced tool_choice and parse the tool input."""
        import anthropic  # type: ignore[import-untyped]

        client = anthropic.Anthropic()
        prompt = _build_prompt(rubric, artifact)

        response = client.messages.create(
            model=_DEFAULT_MODEL,
            max_tokens=_JUDGE_MAX_TOKENS,
            tools=[
                {
                    "name": "verdict",
                    "description": "Structured evaluation verdict",
                    "input_schema": schema,
                }
            ],
            tool_choice={"type": "tool", "name": "verdict"},
            messages=[{"role": "user", "content": prompt}],
        )

        raw: dict = {}  # type: ignore[type-arg]
        for block in response.content:
            if (
                getattr(block, "type", None) == "tool_use"
                and getattr(block, "name", None) == "verdict"
            ):
                raw = dict(block.input)
                break

        return _parse_verdict(raw)


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def select_judge_client() -> JudgeClient:
    """Return the appropriate JudgeClient based on env-var precedence.

    Precedence (first wins):
        1. CLAUDE_CODE_OAUTH_TOKEN → AgentSdkJudgeClient
        2. ANTHROPIC_API_KEY       → MessagesApiJudgeClient
        3. Neither set             → RuntimeError

    Returns:
        An instantiated concrete JudgeClient.

    Raises:
        RuntimeError: When neither CLAUDE_CODE_OAUTH_TOKEN nor ANTHROPIC_API_KEY
                      is set in the environment.
    """
    if os.environ.get(_ENV_OAUTH):
        return AgentSdkJudgeClient()
    if os.environ.get(_ENV_API_KEY):
        return MessagesApiJudgeClient()
    raise RuntimeError(
        f"No auth credentials found. "
        f"Set {_ENV_OAUTH} (for the Agent SDK route) "
        f"or {_ENV_API_KEY} (for the direct Messages API route)."
    )


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _build_prompt(rubric: str, artifact: str) -> str:
    """Compose the judge prompt from rubric + artifact."""
    return (
        f"## Evaluation Rubric\n\n{rubric}\n\n"
        f"## Artifact Under Evaluation\n\n{artifact}\n\n"
        "Evaluate the artifact against the rubric and return a structured verdict."
    )


def _parse_verdict(raw: dict) -> JudgeVerdict:  # type: ignore[type-arg]
    """Validate required fields and construct a JudgeVerdict.

    Raises:
        ValueError: If ``verdict``, ``findings``, or ``score`` are missing.
    """
    missing = [f for f in ("verdict", "findings", "score") if f not in raw]
    if missing:
        raise ValueError(
            f"Judge response is missing required fields: {missing}. Got keys: {list(raw.keys())}"
        )

    return JudgeVerdict(
        verdict=raw["verdict"],
        findings=tuple(raw["findings"]),
        score=int(raw["score"]),
        raw=raw,
    )
