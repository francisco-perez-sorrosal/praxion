"""Behavioral tests for CachingJudgeClient and run_parallel_judged.

CachingJudgeClient wraps any JudgeClient with a content-addressed,
append-only JSONL verdict cache. run_parallel_judged() bounds the
concurrency of a family's judged loop while preserving input order and
per-item fail-soft behavior.

All production imports are deferred inside each test body (RED-state
handshake, matching the rest of this test suite).
"""

from __future__ import annotations

import json
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Test double: an inner JudgeClient that counts real calls
# ---------------------------------------------------------------------------


class _CountingJudgeClient:
    """Inner JudgeClient stub — counts real calls, returns a scripted verdict."""

    def __init__(
        self,
        verdict: str = "PASS",
        findings: tuple[str, ...] = ("ok",),
        score: int = 90,
        *,
        model: str = "claude-haiku-4-5",
        fail: bool = False,
    ) -> None:
        self.call_count = 0
        self.model = model
        self._verdict = verdict
        self._findings = findings
        self._score = score
        self._fail = fail

    def judge(self, rubric: str, artifact: str, schema: Any) -> Any:
        from praxion_evals.harness.schemas import JudgeVerdict

        self.call_count += 1
        if self._fail:
            raise RuntimeError("boom")
        return JudgeVerdict(
            verdict=self._verdict,  # type: ignore[arg-type]
            findings=self._findings,
            score=self._score,
            raw={"verdict": self._verdict, "findings": list(self._findings), "score": self._score},
        )


# ---------------------------------------------------------------------------
# CachingJudgeClient: miss / hit / round-trip
# ---------------------------------------------------------------------------


def test_cache_miss_calls_through_and_appends_one_row(tmp_path: Path):
    """A cold cache is a miss: the inner client is called and a row is written."""
    from praxion_evals.harness.judge_client import CachingJudgeClient

    inner = _CountingJudgeClient()
    cache_path = tmp_path / "judge_cache.jsonl"
    client = CachingJudgeClient(inner, cache_path)

    verdict = client.judge(rubric="r", artifact="a", schema={"type": "object"})

    assert verdict.verdict == "PASS"
    assert verdict.cached is False, "a fresh call must not be marked cached"
    assert inner.call_count == 1
    lines = cache_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1


def test_cache_hit_returns_stored_verdict_without_a_call(tmp_path: Path):
    """A second identical call is served from the in-memory cache — no second call."""
    from praxion_evals.harness.judge_client import CachingJudgeClient

    inner = _CountingJudgeClient()
    cache_path = tmp_path / "judge_cache.jsonl"
    client = CachingJudgeClient(inner, cache_path)

    first = client.judge(rubric="r", artifact="a", schema={"type": "object"})
    second = client.judge(rubric="r", artifact="a", schema={"type": "object"})

    assert inner.call_count == 1, "an identical second call must be served from cache"
    assert second.cached is True
    assert second.verdict == first.verdict


def test_cache_round_trips_across_client_instances(tmp_path: Path):
    """A cache file written by one client instance is honored by a fresh one."""
    from praxion_evals.harness.judge_client import CachingJudgeClient

    cache_path = tmp_path / "judge_cache.jsonl"
    CachingJudgeClient(_CountingJudgeClient(), cache_path).judge(
        rubric="r", artifact="a", schema={"type": "object"}
    )

    inner2 = _CountingJudgeClient()
    client2 = CachingJudgeClient(inner2, cache_path)
    verdict = client2.judge(rubric="r", artifact="a", schema={"type": "object"})

    assert inner2.call_count == 0, "a fresh client loading the same cache file must hit"
    assert verdict.cached is True


def test_cache_key_includes_model_so_a_model_change_invalidates(tmp_path: Path):
    """A different judge model on the same rubric/artifact/schema is a miss."""
    from praxion_evals.harness.judge_client import CachingJudgeClient

    cache_path = tmp_path / "judge_cache.jsonl"
    CachingJudgeClient(_CountingJudgeClient(model="model-a"), cache_path).judge(
        rubric="r", artifact="a", schema={"type": "object"}
    )

    inner_b = _CountingJudgeClient(model="model-b")
    CachingJudgeClient(inner_b, cache_path).judge(
        rubric="r", artifact="a", schema={"type": "object"}
    )

    assert inner_b.call_count == 1, "a different judge model must be a cache miss"


def test_failed_call_is_never_cached(tmp_path: Path):
    """A judge() call that raises must not create or write to the cache file."""
    import pytest

    from praxion_evals.harness.judge_client import CachingJudgeClient

    cache_path = tmp_path / "judge_cache.jsonl"
    client = CachingJudgeClient(_CountingJudgeClient(fail=True), cache_path)

    with pytest.raises(RuntimeError):
        client.judge(rubric="r", artifact="a", schema={"type": "object"})

    assert not cache_path.exists(), "a failed call must not write a cache file"


def test_no_cache_file_created_when_no_judge_call_is_made(tmp_path: Path):
    """Constructing a CachingJudgeClient must not touch the cache path on disk."""
    from praxion_evals.harness.judge_client import CachingJudgeClient

    cache_path = tmp_path / "nested" / "judge_cache.jsonl"
    CachingJudgeClient(_CountingJudgeClient(), cache_path)

    assert not cache_path.exists()
    assert not cache_path.parent.exists()


def test_malformed_cache_line_is_skipped_not_fatal(tmp_path: Path):
    """A torn/malformed line in the cache file is skipped, not a load failure."""
    from praxion_evals.harness.judge_client import CachingJudgeClient

    cache_path = tmp_path / "judge_cache.jsonl"
    cache_path.write_text('not json\n{"key": "abc"}\n', encoding="utf-8")

    inner = _CountingJudgeClient()
    client = CachingJudgeClient(inner, cache_path)
    verdict = client.judge(rubric="r", artifact="a", schema={"type": "object"})

    assert verdict.verdict == "PASS"
    assert inner.call_count == 1, "malformed prior rows must not satisfy a real lookup"


# ---------------------------------------------------------------------------
# --no-judge-cache: read_cache=False bypasses reads but still writes
# ---------------------------------------------------------------------------


def test_read_cache_false_bypasses_reads_but_still_writes(tmp_path: Path):
    """read_cache=False (--no-judge-cache) re-judges even an existing cache entry."""
    from praxion_evals.harness.judge_client import CachingJudgeClient

    cache_path = tmp_path / "judge_cache.jsonl"
    CachingJudgeClient(_CountingJudgeClient(), cache_path).judge(
        rubric="r", artifact="a", schema={"type": "object"}
    )

    inner2 = _CountingJudgeClient()
    client2 = CachingJudgeClient(inner2, cache_path, read_cache=False)
    verdict = client2.judge(rubric="r", artifact="a", schema={"type": "object"})

    assert inner2.call_count == 1, "read_cache=False must bypass the existing cache entry"
    assert verdict.cached is False
    lines = cache_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2, "a miss under read_cache=False must still append a fresh row"


# ---------------------------------------------------------------------------
# Thread-safety: concurrent misses append distinct, uncorrupted lines
# ---------------------------------------------------------------------------


def test_sixteen_concurrent_misses_append_sixteen_distinct_lines(tmp_path: Path):
    """16 concurrent distinct calls append 16 well-formed, distinct-keyed rows."""
    from praxion_evals.harness.judge_client import CachingJudgeClient
    from praxion_evals.harness.schemas import JudgeVerdict

    class _UniqueJudge:
        model = "claude-haiku-4-5"

        def judge(self, rubric: str, artifact: str, schema: Any) -> Any:
            return JudgeVerdict(verdict="PASS", findings=("ok",), score=50, raw={})

    cache_path = tmp_path / "judge_cache.jsonl"
    client = CachingJudgeClient(_UniqueJudge(), cache_path)

    def _call(i: int) -> None:
        client.judge(rubric=f"r{i}", artifact=f"a{i}", schema={"type": "object"})

    with ThreadPoolExecutor(max_workers=16) as pool:
        list(pool.map(_call, range(16)))

    lines = cache_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 16, f"expected 16 distinct cache rows; got {len(lines)}"
    for line in lines:
        json.loads(line)  # every line must be independently parseable — no torn writes
    keys = {json.loads(line)["key"] for line in lines}
    assert len(keys) == 16, "each of the 16 distinct calls must produce a distinct cache key"


# ---------------------------------------------------------------------------
# run_parallel_judged: order preservation + fail-soft under the pool
# ---------------------------------------------------------------------------


def test_run_parallel_judged_preserves_input_order_regardless_of_completion_order():
    """Results are re-assembled in call-submission order, not completion order."""
    from praxion_evals.harness.judge_client import run_parallel_judged
    from praxion_evals.harness.schemas import JudgeVerdict

    def _make(i: int, delay: float):
        def _call() -> JudgeVerdict:
            time.sleep(delay)
            return JudgeVerdict(verdict="PASS", findings=(str(i),), score=i, raw={})

        return _call

    # Index 0 finishes last, index 1 finishes first — completion order is reversed.
    calls = [_make(0, 0.05), _make(1, 0.0), _make(2, 0.02)]
    results = run_parallel_judged(calls, max_workers=3)

    assert [r.score for r in results] == [0, 1, 2]


def test_run_parallel_judged_isolates_a_failure_to_its_own_slot():
    """One callable's exception lands in its own slot; the others still succeed."""
    from praxion_evals.harness.judge_client import run_parallel_judged
    from praxion_evals.harness.schemas import JudgeVerdict

    def _ok() -> JudgeVerdict:
        return JudgeVerdict(verdict="PASS", findings=("ok",), score=1, raw={})

    def _boom() -> JudgeVerdict:
        raise RuntimeError("boom")

    results = run_parallel_judged([_ok, _boom, _ok])

    assert isinstance(results[0], JudgeVerdict)
    assert isinstance(results[1], Exception)
    assert isinstance(results[2], JudgeVerdict)


def test_run_parallel_judged_empty_list_returns_empty_list():
    """An empty call list returns an empty list without spinning up a pool."""
    from praxion_evals.harness.judge_client import run_parallel_judged

    assert run_parallel_judged([]) == []


# ---------------------------------------------------------------------------
# judge_workers(): env override
# ---------------------------------------------------------------------------


def test_judge_workers_defaults_to_eight(monkeypatch):
    from praxion_evals.harness.judge_client import judge_workers

    monkeypatch.delenv("PRAXION_EVAL_JUDGE_WORKERS", raising=False)
    assert judge_workers() == 8


def test_judge_workers_honors_env_override(monkeypatch):
    from praxion_evals.harness.judge_client import judge_workers

    monkeypatch.setenv("PRAXION_EVAL_JUDGE_WORKERS", "3")
    assert judge_workers() == 3


def test_judge_workers_falls_back_on_invalid_value(monkeypatch):
    from praxion_evals.harness.judge_client import judge_workers

    monkeypatch.setenv("PRAXION_EVAL_JUDGE_WORKERS", "not-a-number")
    assert judge_workers() == 8

    monkeypatch.setenv("PRAXION_EVAL_JUDGE_WORKERS", "-2")
    assert judge_workers() == 8
