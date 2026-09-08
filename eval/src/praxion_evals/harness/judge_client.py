"""JudgeClient ABC and concrete implementations.

Auth-mode selection is runtime, driven by environment variables:
    CLAUDE_CODE_OAUTH_TOKEN set  → AgentSdkJudgeClient
    ANTHROPIC_API_KEY set        → MessagesApiJudgeClient
    Neither                      → RuntimeError naming both vars

Both SDK imports are deferred inside the relevant class __init__ / judge()
so that importing this module never fails even when neither SDK is installed.
Family code must never import claude_agent_sdk or anthropic directly — all
calls flow through this module.

CachingJudgeClient wraps any JudgeClient to skip a re-judge of previously
seen (rubric, artifact, schema, model) tuples; run_parallel_judged() bounds
the concurrency of a family's judged loop over a ThreadPoolExecutor while
preserving input order and per-item fail-soft behavior.
"""

from __future__ import annotations

import asyncio
import dataclasses
import hashlib
import json
import os
import threading
from abc import ABC, abstractmethod
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from praxion_evals.harness.schemas import JudgeUsage, JudgeVerdict

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_ENV_OAUTH = "CLAUDE_CODE_OAUTH_TOKEN"
_ENV_API_KEY = "ANTHROPIC_API_KEY"

_DEFAULT_MODEL = "claude-haiku-4-5"
_JUDGE_MAX_TOKENS = 1024
_JUDGE_TIMEOUT_SECONDS = 120
_NESTED_ENV = "CLAUDECODE"
_API_TIMEOUT_MS_MARGIN_MS = 5_000

# Bounded concurrency for a family's judged loop (see run_parallel_judged()).
_JUDGE_WORKERS_ENV = "PRAXION_EVAL_JUDGE_WORKERS"
_JUDGE_WORKERS_DEFAULT = 8

# Anthropic first-party rates, skill table cached 2026-06-24 — USD per million
# tokens (input, output). Estimate only, not a billing-accurate figure; a
# model absent from this table is "unpriced" (see estimate_cost_usd()).
_PRICE_USD_PER_MTOK: dict[str, tuple[float, float]] = {
    "claude-haiku-4-5": (1.00, 5.00),
}
_CACHE_READ_DISCOUNT = 0.10  # cache reads bill at 10% of the input rate
_CACHE_WRITE_PREMIUM = 1.25  # cache writes bill at 125% of the input rate
_TOKENS_PER_MTOK = 1_000_000


# ---------------------------------------------------------------------------
# ABC
# ---------------------------------------------------------------------------


class JudgeClient(ABC):
    """Adapter that encapsulates the auth-mode seam.

    Concrete subclasses implement judge() using a specific SDK.
    Family code always calls this abstract method — never the SDK directly.
    """

    # Overridable per subclass; read by CachingJudgeClient to key its cache
    # and by the cost estimator to price a call.
    model: str = _DEFAULT_MODEL

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

        if os.environ.get(_NESTED_ENV) == "1":
            raise RuntimeError(
                "Cannot use Agent SDK route from inside an active Claude Code session.\n"
                f"Detected: {_NESTED_ENV}=1 in the environment. The bundled `claude` CLI "
                "subprocess spawned by claude-agent-sdk attempts a stdin handshake that "
                "deadlocks when the parent's stdio is already managed by an outer Claude Code "
                "session (see https://github.com/anthropics/claude-agent-sdk-python/issues/573).\n"
                f"To fix: run /eval-praxion from a plain shell (no active Claude Code session), "
                "or set ANTHROPIC_API_KEY to take the direct Messages API route."
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
            env={"API_TIMEOUT_MS": str(_JUDGE_TIMEOUT_SECONDS * 1000 + _API_TIMEOUT_MS_MARGIN_MS)},
        )

        raw: dict = {}  # type: ignore[type-arg]

        async def _run() -> None:
            nonlocal raw
            async for message in sdk.query(prompt=prompt, options=options):
                structured = getattr(message, "structured_output", None)
                if structured is not None:
                    raw = dict(structured)

        async def _run_with_timeout() -> None:
            await asyncio.wait_for(_run(), timeout=_JUDGE_TIMEOUT_SECONDS)

        try:
            asyncio.run(_run_with_timeout())
        except TimeoutError as exc:
            raise TimeoutError(
                f"Agent SDK judge call exceeded {_JUDGE_TIMEOUT_SECONDS} s.\n"
                f"Tried: claude_agent_sdk.query(model={_DEFAULT_MODEL!r}, "
                f"max_tokens={_JUDGE_MAX_TOKENS}) for {len(artifact)} chars.\n"
                "No structured_output yielded within the budget.\n"
                "To fix: inspect rate-limit / network state; if the SDK is healthy, "
                "increase _JUDGE_TIMEOUT_SECONDS in "
                "praxion_evals.harness.judge_client."
            ) from exc
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
            model=self.model,
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
            if isinstance(block, anthropic.types.ToolUseBlock) and block.name == "verdict":
                raw = dict(block.input)
                break

        verdict = _parse_verdict(raw)
        return dataclasses.replace(verdict, usage=_usage_from_response(response))


# ---------------------------------------------------------------------------
# Mechanical-only sentinel
# ---------------------------------------------------------------------------


class NullJudgeClient(JudgeClient):
    """Sentinel client for ``--mechanical-only`` runs.

    Families that respect ``mechanical_only=True`` must not call ``judge()``;
    if one does anyway, this client raises so the bug surfaces immediately
    instead of silently returning a fake verdict.
    """

    def judge(self, rubric: str, artifact: str, schema: dict) -> JudgeVerdict:  # type: ignore[type-arg]
        raise RuntimeError(
            "NullJudgeClient.judge() was called in mechanical-only mode. "
            "A family attempted an LLM-judged check despite mechanical_only=True; "
            "the family's run() must skip every judge.judge() call when this flag is set."
        )


# ---------------------------------------------------------------------------
# Caching decorator
# ---------------------------------------------------------------------------


class CachingJudgeClient(JudgeClient):
    """Decorator over a JudgeClient that skips a re-judge of a seen input.

    The cache key content-addresses (rubric, artifact, schema, judge model)
    via sha256 — a model change therefore invalidates naturally, without any
    explicit versioning field. The store is an append-only JSONL file: a hit
    short-circuits the wrapped client (no network call) and returns the
    stored verdict with ``cached=True``; a miss calls through and appends one
    fresh row. A failed call is never written to the cache.

    Safe to share one instance across a ThreadPoolExecutor — cache reads,
    cache writes, and the running counters are all serialized under one lock.
    """

    def __init__(
        self,
        inner: JudgeClient,
        cache_path: Path | str,
        *,
        read_cache: bool = True,
    ) -> None:
        self._inner = inner
        self._cache_path = Path(cache_path)
        self._read_cache = read_cache
        self._lock = threading.Lock()
        self._cache: dict[str, JudgeVerdict] = _load_cache(self._cache_path) if read_cache else {}
        # Exposed for callers that report run-level judging stats (see
        # Orchestrator.run()) — total .judge() invocations and the subset
        # served from cache.
        self.call_count = 0
        self.cache_hit_count = 0

    @property
    def model(self) -> str:  # type: ignore[override]
        return getattr(self._inner, "model", _DEFAULT_MODEL)

    def judge(self, rubric: str, artifact: str, schema: dict) -> JudgeVerdict:  # type: ignore[type-arg]
        key = _cache_key(rubric, artifact, schema, self.model)

        if self._read_cache:
            with self._lock:
                hit = self._cache.get(key)
            if hit is not None:
                with self._lock:
                    self.call_count += 1
                    self.cache_hit_count += 1
                return hit

        verdict = self._inner.judge(rubric, artifact, schema)

        with self._lock:
            self.call_count += 1
            # A future hit costs nothing — the stored copy never carries usage.
            self._cache[key] = dataclasses.replace(verdict, cached=True, usage=None)
            self._append_row(key, verdict)
        return verdict

    def _append_row(self, key: str, verdict: JudgeVerdict) -> None:
        """Append one JSONL row. Caller already holds ``self._lock``."""
        self._cache_path.parent.mkdir(parents=True, exist_ok=True)
        row = {
            "key": key,
            "verdict": verdict.verdict,
            "findings": list(verdict.findings),
            "score": verdict.score,
            "raw": verdict.raw,
        }
        with self._cache_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row) + "\n")


# ---------------------------------------------------------------------------
# Parallel execution of a judged loop
# ---------------------------------------------------------------------------


def judge_workers() -> int:
    """Return the configured worker-pool size for a family's judged loop.

    Reads ``PRAXION_EVAL_JUDGE_WORKERS``; falls back to the default when the
    variable is unset or is not a positive integer.
    """
    raw = os.environ.get(_JUDGE_WORKERS_ENV)
    if raw is None:
        return _JUDGE_WORKERS_DEFAULT
    try:
        value = int(raw)
    except ValueError:
        return _JUDGE_WORKERS_DEFAULT
    return value if value > 0 else _JUDGE_WORKERS_DEFAULT


def run_parallel_judged(
    calls: Sequence[Callable[[], JudgeVerdict]],
    *,
    max_workers: int | None = None,
) -> list[JudgeVerdict | Exception]:
    """Run zero-arg judge callables concurrently, preserving input order.

    Each element of the returned list corresponds positionally to the same
    index in *calls*: the JudgeVerdict on success, or the raised exception
    instance on failure. This function itself never raises — one callable's
    exception never prevents the others from completing or corrupts another
    slot's result (fail-soft under the pool). Callers turn an Exception entry
    into a single FAIL CheckResult, matching the pre-parallel per-item
    fail-soft behavior of the judged loops.

    Args:
        calls: Zero-arg callables, each performing one judge() call.
        max_workers: Pool size override; defaults to judge_workers().
    """
    if not calls:
        return []
    workers = max(1, min(max_workers or judge_workers(), len(calls)))
    results: list[JudgeVerdict | Exception] = [None] * len(calls)  # type: ignore[list-item]
    with ThreadPoolExecutor(max_workers=workers) as pool:
        future_to_index = {pool.submit(call): index for index, call in enumerate(calls)}
        for future in as_completed(future_to_index):
            index = future_to_index[future]
            try:
                results[index] = future.result()
            except Exception as exc:  # noqa: BLE001 - fail-soft boundary; caller maps to CheckResult
                results[index] = exc
    return results


def estimate_cost_usd(model: str, usage: JudgeUsage) -> float | None:
    """Estimate USD cost for summed *usage* against a judge *model*.

    Returns None ("unpriced") when *model* is absent from the price table —
    an unrecognized model is a genuine pricing unknown, not a zero cost,
    even when *usage* itself is all zeros.

    See _PRICE_USD_PER_MTOK's comment for the pricing source; cache reads
    and cache writes are billed at a discount/premium off the input rate
    (Anthropic prompt-caching pricing), not a flat per-token rate.
    """
    price = _PRICE_USD_PER_MTOK.get(model)
    if price is None:
        return None
    input_rate, output_rate = price
    cost = (
        usage.input_tokens * input_rate
        + usage.output_tokens * output_rate
        + usage.cache_read_input_tokens * input_rate * _CACHE_READ_DISCOUNT
        + usage.cache_creation_input_tokens * input_rate * _CACHE_WRITE_PREMIUM
    )
    return cost / _TOKENS_PER_MTOK


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


def _usage_from_response(response: Any) -> JudgeUsage | None:
    """Extract token usage from a Messages API response.

    Cache-related fields are absent on responses that never touched the
    prompt cache; default to 0 rather than raising. Returns None only when
    the response carries no ``usage`` attribute at all.
    """
    usage = getattr(response, "usage", None)
    if usage is None:
        return None
    return JudgeUsage(
        input_tokens=getattr(usage, "input_tokens", 0) or 0,
        output_tokens=getattr(usage, "output_tokens", 0) or 0,
        cache_read_input_tokens=getattr(usage, "cache_read_input_tokens", 0) or 0,
        cache_creation_input_tokens=getattr(usage, "cache_creation_input_tokens", 0) or 0,
    )


def _cache_key(rubric: str, artifact: str, schema: dict, model: str) -> str:  # type: ignore[type-arg]
    """Content-address one judge call: rubric + artifact + schema + model.

    The schema dict is serialized with sorted keys so key order never affects
    the hash. Joined with a separator that cannot appear inside any of the
    plain-text parts, so no two distinct inputs can collide by concatenation.
    """
    canonical_schema = json.dumps(schema, sort_keys=True, separators=(",", ":"))
    blob = "\x1e".join([model, canonical_schema, rubric, artifact])
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _load_cache(path: Path) -> dict[str, JudgeVerdict]:
    """Load a judge-verdict cache file, tolerant of malformed lines.

    A line that fails to parse, or is missing a required field, is skipped —
    a torn write from an interrupted prior run must not make the whole cache
    file unusable for every other, well-formed row.
    """
    cache: dict[str, JudgeVerdict] = {}
    if not path.exists():
        return cache
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            stripped = line.strip()
            if not stripped:
                continue
            try:
                row: dict[str, Any] = json.loads(stripped)
                cache[row["key"]] = JudgeVerdict(
                    verdict=row["verdict"],
                    findings=tuple(row["findings"]),
                    score=row["score"],
                    raw=row.get("raw", {}),
                    cached=True,
                )
            except (json.JSONDecodeError, KeyError, TypeError, ValueError):
                continue
    return cache
