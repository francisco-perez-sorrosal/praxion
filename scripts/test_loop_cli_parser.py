"""Tests for the step-loop command's argument parser at its home in ``scripts/_step_loop_cli.py``.

The parser is pure text in, ``Namespace`` or ``CallerError`` out, so every case calls it directly.
The entry script (``scripts/step_loop.py``) keeps the names callers import from it; the last
cases pin that each one is still there and that the refusal still reaches the printed envelope.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import _step_loop_cli as cli  # noqa: E402
import step_loop  # noqa: E402

SLUG = "demo"
DESCRIPTION = "the help text the entry script carries"
USAGE = "usage"
EXIT_CALLER_ERROR = 4
RELAY = ("--agent-id", "a1", "--marker", "complete")


def parse(*argv: str):
    return cli.parse(list(argv), DESCRIPTION)


def refusal(*argv: str) -> cli.CallerError:
    with pytest.raises(cli.CallerError) as raised:
        parse(*argv)
    return raised.value


@pytest.mark.parametrize(
    ("extra", "attribute", "expected"),
    [
        ((), "repo_root", None),
        (("--repo-root", "/r"), "repo_root", "/r"),
        (("--worktree-root", "/w"), "worktree_root", "/w"),
        (("--base-ref", "main"), "base_ref", "main"),
    ],
)
def test_next_reads_its_slug_and_options(extra, attribute, expected) -> None:
    args = parse("next", SLUG, *extra)

    assert (args.verb, args.slug, getattr(args, attribute)) == ("next", SLUG, expected)


def test_record_reads_the_request_and_the_relayed_return() -> None:
    args = parse("record", SLUG, "--request", "s2-a1-implement", *RELAY)

    assert (args.request, args.agent_id, args.marker) == ("s2-a1-implement", "a1", "complete")
    assert args.not_started is None


def test_record_reads_a_call_that_never_started() -> None:
    args = parse("record", SLUG, "--request", "r1", "--not-started", "the call failed")

    assert (args.not_started, args.agent_id, args.marker) == ("the call failed", None, None)


@pytest.mark.parametrize(("extra", "expected"), [((), False), (("--json",), True)])
def test_status_reads_whether_the_object_is_asked_for(extra, expected) -> None:
    assert parse("status", SLUG, *extra).json is expected


@pytest.mark.parametrize(
    "argv",
    [
        ("frobnicate", SLUG),
        ("next",),
        (),
        ("record", SLUG),
        ("record", SLUG, "--request", "r1"),
        ("record", SLUG, "--request", "r1", "--agent-id", "a1"),
        ("record", SLUG, "--request", "r1", "--agent-id", "", "--marker", "complete"),
        ("record", SLUG, "--request", "r1", *RELAY, "--not-started", "why"),
        ("record", SLUG, "--request", "r1", "--not-started", "  "),
        ("record", SLUG, "--request", "r1", "--agent-id", "a1", "--marker", "finished"),
    ],
)
def test_a_call_that_cannot_be_read_is_a_usage_refusal(argv) -> None:
    error = refusal(*argv)

    assert error.code == USAGE
    assert error.counts is None
    assert error.message.endswith("--help.")


def test_the_refusal_names_the_script_whose_help_to_read() -> None:
    assert "see step_loop.py --help." in refusal("frobnicate", SLUG).message


def test_a_relay_that_breaks_the_pairing_names_the_record_verb() -> None:
    error = refusal("record", SLUG, "--request", "r1", "--agent-id", "a1")

    assert "see step_loop.py record --help." in error.message


def test_the_description_is_the_help_text_the_caller_gave() -> None:
    assert cli._build_parser(DESCRIPTION).description == DESCRIPTION


def test_the_verbs_and_markers_the_parser_offers_are_the_ones_the_command_documents() -> None:
    assert cli.VERBS == ("next", "record", "status")
    assert set(cli.MARKERS) == {"complete", "blocked", "conflict", "partial", "none"}


@pytest.mark.parametrize(
    "name", ["CallerError", "drive", "AgentRan", "NotStarted", "Spawner", "execute", "main"]
)
def test_the_entry_script_still_offers_every_name_callers_import_from_it(name) -> None:
    assert hasattr(step_loop, name)


def test_the_entry_script_re_exports_the_same_refusal_the_parser_raises() -> None:
    assert step_loop.CallerError is cli.CallerError


def test_a_refused_call_prints_the_usage_envelope_and_exits_four() -> None:
    reply = step_loop.execute(["frobnicate", SLUG])

    assert reply.doc["error"]["code"] == USAGE
    assert reply.exit == EXIT_CALLER_ERROR
