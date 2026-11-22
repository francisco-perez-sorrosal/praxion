"""No file tracked at the base selects less, in any pocket, than it selected there.

The resolver's answer for each file changed alone was frozen from a clean checkout of the base
commit (`selection_before_every_tracked_file.json.gz`, which records that commit and the query).
For every such file still tracked, today's answer holds, in every pocket, every test the frozen
answer named that still exists, and is the full suite wherever the frozen answer was. Closing a
selection gap may widen an answer; it may never narrow one.
"""

from __future__ import annotations

import gzip
import json
from pathlib import Path

from tests.acceptance.drivers.gate_liveness import make_copy
from tests.acceptance.drivers.selection_answers import (
    FULL,
    answers_for,
    pocket_answer,
    tracked_files,
)

FROZEN = (
    Path(__file__).resolve().parent / "fixtures" / "selection_before_every_tracked_file.json.gz"
)


def frozen_answers() -> dict[str, dict[str, object]]:
    """Each file's frozen answer: pocket root to `"full"` or the list of tests it selected."""
    record = json.loads(gzip.decompress(FROZEN.read_bytes()))
    tests = record["tests"]
    return {
        path: {
            root: chosen if chosen == FULL else [tests[index] for index in chosen]
            for root, chosen in group["answer"].items()
        }
        for group in record["groups"]
        for path in group["paths"]
    }


def narrowings(before: dict[str, dict], after: dict[str, dict], root: Path) -> list[str]:
    """Each way today's answer selects less than the frozen one, as a readable line."""
    found = []
    for path, pockets in sorted(before.items()):
        for pocket_root, chosen_before in sorted(pockets.items()):
            chosen_now = pocket_answer(after[path], pocket_root)
            if chosen_now == FULL:
                continue
            if chosen_before == FULL:
                found.append(f"{path} [{pocket_root}]: was the full suite, now {chosen_now}")
                continue
            lost = [
                test
                for test in chosen_before
                if (root / test).is_file() and test not in (chosen_now or ())
            ]
            if lost:
                found.append(f"{path} [{pocket_root}]: no longer selects {lost[:10]}")
    return found


def test_no_file_tracked_at_the_base_selects_less_than_it_did_there(tmp_path):
    before = frozen_answers()
    copy = make_copy(tmp_path)
    still_tracked = {path: before[path] for path in tracked_files(copy) if path in before}

    after = answers_for(copy, still_tracked)

    narrowed = narrowings(still_tracked, after, copy.root)
    assert narrowed == [], f"{len(narrowed)} narrowed answers:\n" + "\n".join(narrowed[:40])
