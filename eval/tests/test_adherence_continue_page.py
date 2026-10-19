"""The page a continuation lets its sessions fetch: the one its first part recorded, so the
tasks launched again are measured against the page the earlier tasks were."""

from __future__ import annotations

from pathlib import Path

from praxion_evals.adherence import session_loop, tasks
from praxion_evals.adherence.cli import parse_config
from praxion_evals.adherence.run_ending import Continuation
from tests.test_adherence_results import run_results

RECORDED = "https://raw.example/praxion/0123abc/page.html"
COMMIT = "f" * 40
ROLE = "researcher"


def _part(run_id: str, page_url: str | None = None):
    extra = {"tasks": {ROLE: ["t1"]}}
    if page_url is not None:
        extra["c6_page"] = {"url": page_url, "fetchable": True}
    return run_results(run_id=run_id, extra=extra)


def _config(*options: str) -> session_loop.RunConfig:
    return parse_config(["--role", ROLE, *options])


def _checkout() -> session_loop.Checkout:
    return session_loop.Checkout(Path("."), COMMIT, False)


def test_a_continuation_carries_the_page_its_first_part_recorded() -> None:
    continuation = Continuation.of([_part("a", RECORDED), _part("b", "https://raw.example/other")])

    assert continuation.page_url == RECORDED


def test_a_continuation_takes_the_page_from_the_first_part_that_probed_one() -> None:
    continuation = Continuation.of([_part("a"), _part("b", RECORDED)])

    assert continuation.page_url == RECORDED


def test_a_continuation_of_parts_that_recorded_no_page_carries_none() -> None:
    assert Continuation.of([_part("a"), _part("b")]).page_url is None


def test_a_continuation_reuses_the_recorded_page_whatever_commit_the_checkout_is_at() -> None:
    continuation = Continuation.of([_part("a", RECORDED)])

    url = session_loop.page_url_of(_config(), _checkout(), continuation)

    assert url == RECORDED
    assert COMMIT not in url


def test_a_page_base_url_named_beside_the_continuation_wins_over_the_recorded_one() -> None:
    continuation = Continuation.of([_part("a", RECORDED)])
    config = _config("--fixture-pages-base-url", "https://pages.example/dir/")

    url = session_loop.page_url_of(config, _checkout(), continuation)

    assert url == "https://pages.example/dir/" + tasks.PAGE_PATH.rsplit("/", 1)[-1]


def test_a_first_run_and_a_continuation_with_no_recorded_page_use_the_checkouts_commit() -> None:
    first_run = session_loop.page_url_of(_config(), _checkout(), None)
    unrecorded = session_loop.page_url_of(_config(), _checkout(), Continuation.of([_part("a")]))

    assert first_run == unrecorded == tasks.fixture_page_url(COMMIT)
