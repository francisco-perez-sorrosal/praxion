"""Tests for `selection.py` -- the liveness probe for the test-scope resolver.

The failure this closes: a resolver that quietly stopped selecting tests (29 reads
nobody had listed went unselected before anyone noticed). The oracle is the reads
the suite itself makes, so the pure judge below is fed every way a resolver can
fail to select, plus every way the tracer can fail to observe, and each must fail
with a reason. Expected values come from the probe's contract, not from running
the implementation.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

# Flat import (siblings by bare name), the layout the mutation sensor reads.
sys.path.insert(0, str(Path(__file__).resolve().parent))

import selection  # noqa: E402

from gate_probes.verdict import GateId  # noqa: E402

TEST = "tests/test_a.py"
OTHER_TEST = "tests/test_b.py"
DATA = "docs/data.txt"


def _record(test: str, path: str, channel: str) -> str:
    return json.dumps({"t": test, "p": path, "c": channel})


def _observed(
    direct=(), child=(), imported=(), heartbeats=(TEST,), collected=(TEST,)
) -> selection.ObservedReads:
    return selection.ObservedReads(
        pairs_by_channel={
            "direct": frozenset(direct),
            "child": frozenset(child),
            "import": frozenset(imported),
        },
        heartbeats=frozenset(heartbeats),
        collected=frozenset(collected),
    )


def _answer(root_selection: str = "tests", tests: tuple[str, ...] = ()) -> selection.Answer:
    return selection.Answer(root_selection=root_selection, tests=frozenset(tests))


def _payload_line(path: str, root_selection="tests", tests=(), widen=False, root=".") -> str:
    return json.dumps(
        {
            "schema": 2,
            "changed": {"source": "explicit", "paths": [path]},
            "decision": "widened" if widen else "selected",
            "widen": [{"reason": "r", "paths": [path], "detail": "d"}] if widen else [],
            "ignored_non_source": [],
            "pockets": [
                {
                    "root": root,
                    "ecosystem": "python",
                    "adapter": "python-derived",
                    "selection": root_selection,
                    "tests": [{"path": t, "via": "v", "because": path} for t in tests],
                    "invocations": [],
                }
            ],
        }
    )


# -- parsing the trace -------------------------------------------------------------


def test_a_blank_line_between_records_skips_only_itself():
    """Records after a blank line still count: dropping them would judge fewer reads than ran."""
    lines = [_record(TEST, DATA, "direct"), "", _record(TEST, "tools/x.py", "child")]

    observed = selection.parse_records(lines)

    assert observed.pairs_by_channel["direct"] == {(TEST, DATA)}
    assert observed.pairs_by_channel["child"] == {(TEST, "tools/x.py")}


def test_records_are_sorted_into_channels_heartbeats_and_collected_files():
    lines = [
        _record(TEST, DATA, "direct"),
        _record(TEST, "tools/x.py", "child"),
        _record(TEST, "scripts/mod.py", "import"),
        json.dumps({"heartbeat": TEST}),
        json.dumps({"collected": [TEST, OTHER_TEST]}),
        json.dumps({"uncollected": "tests/test_broken.py"}),
        "",
    ]

    observed = selection.parse_records(lines)

    assert observed.pairs_by_channel["direct"] == {(TEST, DATA)}
    assert observed.pairs_by_channel["child"] == {(TEST, "tools/x.py")}
    assert observed.pairs_by_channel["import"] == {(TEST, "scripts/mod.py")}
    assert observed.heartbeats == {TEST}
    assert observed.collected == {TEST, OTHER_TEST}
    assert observed.uncollected == {"tests/test_broken.py"}


def test_verdict_pairs_are_direct_and_child_reads_never_import_credit():
    observed = _observed(
        direct=[(TEST, DATA)], child=[(TEST, "tools/x.py")], imported=[(TEST, "scripts/mod.py")]
    )

    assert observed.verdict_pairs() == {(TEST, DATA), (TEST, "tools/x.py")}


@pytest.mark.parametrize(
    "line",
    [
        "{not json",
        json.dumps({"t": TEST, "p": DATA}),  # no channel
        json.dumps({"t": TEST, "p": DATA, "c": "psychic"}),
        json.dumps({"unknown": 1}),
        json.dumps([1, 2]),
    ],
)
def test_a_record_that_cannot_be_read_is_an_error_not_a_skipped_line(line):
    with pytest.raises(ValueError, match="unrecognised"):
        selection.parse_records([line])


# -- the tracer must have observed something ------------------------------------------


def test_an_empty_record_set_fails_because_the_tracer_observed_nothing():
    reason = selection.dead_tracer_reason(_observed(heartbeats=(), collected=()))

    assert reason is not None
    assert reason.startswith("expected ")
    assert "; observed " in reason


def test_heartbeats_without_any_read_still_fail_a_tracer_that_saw_no_reads():
    assert selection.dead_tracer_reason(_observed()) is not None


def test_a_collected_test_file_that_never_ran_under_the_tracer_is_named():
    observed = _observed(direct=[(TEST, DATA)], heartbeats=(TEST,), collected=(TEST, OTHER_TEST))

    reason = selection.dead_tracer_reason(observed)

    assert reason is not None
    assert OTHER_TEST in reason
    assert TEST not in reason.split("observed")[1]


def test_a_test_file_that_failed_to_collect_is_named_even_when_nothing_was_read():
    observed = selection.ObservedReads(
        pairs_by_channel={"direct": frozenset(), "child": frozenset(), "import": frozenset()},
        heartbeats=frozenset(),
        collected=frozenset(),
        uncollected=frozenset({"tests/test_broken.py"}),
    )

    reason = selection.dead_tracer_reason(observed)

    assert reason is not None
    assert "tests/test_broken.py" in reason


def test_reads_covering_every_collected_file_are_a_working_tracer():
    observed = _observed(
        direct=[(TEST, DATA)], heartbeats=(TEST, OTHER_TEST), collected=(TEST, OTHER_TEST)
    )

    assert selection.dead_tracer_reason(observed) is None


# -- which reads are audited ---------------------------------------------------------


def test_only_tracked_direct_and_child_reads_are_checked_in_sorted_order():
    observed = _observed(
        direct=[(TEST, "z.txt"), (TEST, "untracked.log"), (OTHER_TEST, "a.txt")],
        child=[(TEST, "m.txt")],
        imported=[(TEST, "mod.py")],
    )

    pairs = selection.checked_pairs(
        observed, tracked=frozenset({"z.txt", "a.txt", "m.txt", "mod.py"})
    )

    assert pairs == ((TEST, "m.txt"), (TEST, "z.txt"), (OTHER_TEST, "a.txt"))


# -- reading the resolver's answers ----------------------------------------------------


def test_a_per_path_line_is_keyed_by_its_changed_path():
    stdout = _payload_line(DATA, tests=(TEST,)) + "\n" + _payload_line("b.txt", "full") + "\n"

    answers = selection.parse_answers(stdout)

    assert set(answers) == {DATA, "b.txt"}
    assert answers[DATA].tests == {TEST}
    assert answers["b.txt"].root_selection == "full"


def test_a_line_that_is_not_a_schema_2_answer_is_dropped_so_its_path_selects_nothing():
    wrong_schema = json.loads(_payload_line("c.txt"))
    wrong_schema["schema"] = 1
    stdout = "\n".join(
        [
            "garbage",
            json.dumps(wrong_schema),
            json.dumps({"schema": 2, "changed": {"paths": []}}),
            json.dumps(
                {"schema": 2, "changed": {"paths": ["d.txt"]}, "pockets": "oops", "widen": []}
            ),
            _payload_line("ok.txt"),
        ]
    )

    assert set(selection.parse_answers(stdout)) == {"ok.txt"}


def test_only_the_root_pocket_decides_whether_a_test_is_selected():
    stdout = _payload_line(DATA, "full", root="eval")

    answers = selection.parse_answers(stdout)

    assert answers[DATA].root_selection != "full"
    assert not answers[DATA].selects(TEST)


# -- does a change to the read file select the reading test --------------------------


def test_a_resolver_payload_set_selecting_nothing_leaves_every_read_unselected():
    pairs = ((TEST, DATA), (OTHER_TEST, DATA))
    answers = selection.parse_answers(_payload_line(DATA, "nothing"))

    assert selection.find_unselected(pairs, answers) == pairs


def test_a_missing_payload_selects_nothing_so_the_pair_is_a_finding():
    assert selection.find_unselected(((TEST, DATA),), {}) == ((TEST, DATA),)


def test_a_pair_read_only_by_a_child_process_is_found_when_unselected():
    observed = _observed(child=[(TEST, DATA)])
    pairs = selection.checked_pairs(observed, tracked=frozenset({DATA}))

    assert selection.find_unselected(pairs, {}) == ((TEST, DATA),)


def test_a_widen_scoped_to_another_pocket_leaves_the_root_pockets_list_in_charge():
    answers = selection.parse_answers(_payload_line(DATA, "tests", tests=(OTHER_TEST,), widen=True))

    assert selection.find_unselected(((TEST, DATA), (OTHER_TEST, DATA)), answers) == ((TEST, DATA),)


def test_a_full_root_pocket_selects_every_test():
    answers = {DATA: _answer("full")}

    assert selection.find_unselected(((TEST, DATA),), answers) == ()


def test_a_listed_test_is_selected_and_an_unlisted_one_is_not():
    answers = {DATA: _answer("tests", tests=(TEST,))}

    assert selection.find_unselected(((TEST, DATA), (OTHER_TEST, DATA)), answers) == (
        (OTHER_TEST, DATA),
    )


def test_findings_are_sorted_whatever_order_the_pairs_arrive_in():
    answers: dict[str, selection.Answer] = {}

    found = selection.find_unselected(
        ((TEST, "b.txt"), (OTHER_TEST, "a.txt"), (TEST, "a.txt")), answers
    )

    assert found == ((TEST, "a.txt"), (TEST, "b.txt"), (OTHER_TEST, "a.txt"))


def test_reads_are_dealt_into_sorted_chunks_that_cover_every_read_once():
    reads = [f"f{n}.txt" for n in range(7)]

    chunks = selection.spread(reads, 3)

    assert chunks == [["f0.txt", "f3.txt", "f6.txt"], ["f1.txt", "f4.txt"], ["f2.txt", "f5.txt"]]


def test_fewer_reads_than_ways_yield_no_empty_chunk():
    assert selection.spread(["a.txt", "b.txt"], 8) == [["a.txt"], ["b.txt"]]


# -- the verdict ---------------------------------------------------------------------


def test_unselected_reads_fail_with_an_expected_observed_reason_naming_one_of_them():
    verdict = selection.verdict_from(unselected=((TEST, DATA),), notes=("n",), elapsed_s=1.5)

    assert verdict.passed is False
    assert verdict.gate is GateId.SELECTION_AUDIT
    assert verdict.unselected == ((TEST, DATA),)
    assert verdict.reason.startswith("expected ")
    assert DATA in verdict.reason
    assert verdict.notes == ("n",)


def test_no_unselected_reads_pass_and_keep_their_notes():
    verdict = selection.verdict_from(unselected=(), notes=("n",), elapsed_s=2.0)

    assert verdict.passed is True
    assert verdict.gate is GateId.SELECTION_AUDIT
    assert verdict.reason == ""
    assert verdict.notes == ("n",)


def test_import_only_files_are_counted_apart_as_data_and_code_never_as_findings():
    observed = _observed(
        direct=[(TEST, DATA)],
        imported=[
            (TEST, "mod.py"),
            (OTHER_TEST, "mod.py"),
            (TEST, DATA),
            (TEST, "a.json"),
            (TEST, "b.toml"),
        ],
    )

    note = selection.import_note(observed, tracked=frozenset({DATA, "mod.py", "a.json", "b.toml"}))

    assert "2 data files" in note
    assert "1 code files" in note


# -- the effectful edge --------------------------------------------------------------


def _scratch_repo(tmp_path: Path, resolver: str | None, test_body: str | None = None) -> Path:
    root = tmp_path / "repo"
    (root / "tests").mkdir(parents=True)
    (root / "docs").mkdir()
    (root / "docs" / "data.txt").write_text("x\n")
    (root / "tests" / "test_a.py").write_text(
        test_body
        or textwrap.dedent(
            """
            from pathlib import Path

            ROOT = Path(__file__).resolve().parents[1]


            def test_reads():
                assert (ROOT / "docs" / "data.txt").read_text() == "x\\n"
            """
        )
    )
    if resolver is not None:
        (root / "scripts").mkdir()
        (root / "scripts" / "resolve_test_scope.py").write_text(resolver)
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    subprocess.run(["git", "-C", str(root), "add", "-A"], check=True)
    return root


def _env() -> dict[str, str]:
    return {k: v for k, v in os.environ.items() if not k.startswith(("PYTEST_", "PX_TRACE"))}


_STUB_TEMPLATE = """
import json, sys
if "--help" in sys.argv:
    sys.exit(0)
paths = sys.argv[sys.argv.index("--changed") + 1 :]
for path in paths:
    print(json.dumps({{
        "schema": 2, "changed": {{"source": "explicit", "paths": [path]}},
        "decision": "selected", "widen": [], "ignored_non_source": [],
        "pockets": {pockets},
    }}))
"""
_SELECTS_ALL = _STUB_TEMPLATE.format(
    pockets='[{"root": ".", "ecosystem": "python", "adapter": "x", "selection": "full", "tests": [], "invocations": []}]'
)
_SELECTS_NOTHING = _STUB_TEMPLATE.format(pockets="[]")


def test_a_missing_resolver_fails_in_seconds_saying_which_file_is_missing(tmp_path):
    root = _scratch_repo(tmp_path, resolver=None)

    verdict = selection.run(root, _env())

    assert not verdict.passed
    assert "scripts/resolve_test_scope.py" in verdict.reason
    assert "missing" in verdict.reason


def test_a_resolver_whose_help_fails_is_dead_before_any_tracing(tmp_path):
    root = _scratch_repo(tmp_path, resolver="import sys\nsys.exit(1)\n")

    verdict = selection.run(root, _env())

    assert not verdict.passed
    assert "--help" in verdict.reason


def test_a_resolver_that_selects_nothing_fails_listing_the_reads_it_missed(tmp_path):
    root = _scratch_repo(tmp_path, resolver=_SELECTS_NOTHING)

    verdict = selection.run(root, _env())

    assert not verdict.passed, verdict
    assert (TEST, DATA) in verdict.unselected


def test_a_resolver_that_selects_every_read_passes_and_the_run_leaves_no_trace(tmp_path):
    root = _scratch_repo(tmp_path, resolver=_SELECTS_ALL)
    before = _tree(root)

    verdict = selection.run(root, _env())

    assert verdict.passed, verdict
    assert _tree(root) == before


def test_two_runs_over_one_tree_give_the_same_verdict_and_findings(tmp_path):
    root = _scratch_repo(tmp_path, resolver=_SELECTS_NOTHING)

    first, second = selection.run(root, _env()), selection.run(root, _env())

    assert (first.passed, first.unselected, first.reason) == (
        second.passed,
        second.unselected,
        second.reason,
    )


def test_a_suite_that_cannot_be_collected_fails_instead_of_passing_on_no_reads(tmp_path):
    root = _scratch_repo(tmp_path, resolver=_SELECTS_ALL, test_body="def test_x(:\n")

    verdict = selection.run(root, _env())

    assert not verdict.passed
    assert verdict.reason.startswith("expected ")


def test_a_file_read_by_a_child_process_is_audited_too(tmp_path):
    body = textwrap.dedent(
        """
        import subprocess, sys
        from pathlib import Path

        ROOT = Path(__file__).resolve().parents[1]


        def test_child_reads():
            target = str(ROOT / "docs" / "data.txt")
            subprocess.run([sys.executable, "-c", "open(" + repr(target) + ").read()"], check=True)
        """
    )
    root = _scratch_repo(tmp_path, resolver=_SELECTS_NOTHING, test_body=body)

    verdict = selection.run(root, _env())

    assert (TEST, DATA) in verdict.unselected


def _tree(root: Path) -> list[str]:
    return sorted(str(p.relative_to(root)) for p in root.rglob("*") if ".git" not in p.parts)


def test_canary_pair_is_the_first_co_located_scripts_test_and_its_source():
    tracked = frozenset(
        {"hooks/test_a.py", "hooks/a.py", "scripts/test_b.py", "scripts/b.py", "scripts/test_c.py"}
    )
    assert selection.canary_pair(tracked) == ("scripts/test_b.py", "scripts/b.py")


def test_canary_pair_skips_a_co_located_pair_that_is_not_python():
    tracked = frozenset({"scripts/test_a.sh", "scripts/a.sh", "scripts/test_b.py", "scripts/b.py"})
    assert selection.canary_pair(tracked) == ("scripts/test_b.py", "scripts/b.py")


def test_canary_pair_is_none_without_a_co_located_scripts_pair():
    assert selection.canary_pair(frozenset({"scripts/test_orphan.py", "hooks/a.py"})) is None


CANARY = ("scripts/test_b.py", "scripts/b.py")

_ANSWERS_NOTHING = 'import sys\nif "--help" in sys.argv:\n    sys.exit(0)\n'
_CRASHES_WHEN_ASKED = 'import sys\nsys.exit(0 if "--help" in sys.argv else 1)\n'


def _add_files(root: Path, files: dict[str, str]) -> Path:
    for rel, text in files.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(text)
    subprocess.run(["git", "-C", str(root), "add", "-A"], check=True)
    return root


def _with_canary_pair(root: Path) -> Path:
    return _add_files(
        root, {"scripts/b.py": "B = 1\n", "scripts/test_b.py": "def test_b():\n    pass\n"}
    )


@pytest.mark.parametrize(
    "resolver",
    [_SELECTS_NOTHING, _ANSWERS_NOTHING, _CRASHES_WHEN_ASKED],
    ids=["selects-nothing", "answers-nothing", "crashes-when-asked"],
)
def test_a_dead_resolver_fails_the_canary_listing_its_pair_and_saying_why(tmp_path, resolver):
    root = _with_canary_pair(_scratch_repo(tmp_path, resolver=resolver))

    verdict = selection.run(root, _env())

    assert not verdict.passed
    assert verdict.unselected == (CANARY,)
    assert "resolver canary" in verdict.reason


def test_good_twin_a_live_resolver_passes_the_canary_and_the_audit(tmp_path):
    root = _with_canary_pair(_scratch_repo(tmp_path, resolver=_SELECTS_ALL))

    verdict = selection.run(root, _env())

    assert verdict.passed, verdict
    assert selection.CANARY_SKIPPED not in verdict.notes


def test_without_a_co_located_pair_the_canary_is_skipped_and_the_notes_say_so(tmp_path):
    root = _scratch_repo(tmp_path, resolver=_SELECTS_ALL)

    verdict = selection.run(root, _env())

    assert selection.CANARY_SKIPPED in verdict.notes


def test_a_resolver_that_answers_no_path_fails_naming_the_unanswered_reads(tmp_path):
    root = _scratch_repo(tmp_path, resolver=_ANSWERS_NOTHING)

    verdict = selection.run(root, _env())

    assert not verdict.passed
    assert "no usable answer" in verdict.reason
    assert DATA in verdict.reason


def test_a_failing_test_exit_is_a_note_and_a_clean_exit_is_none():
    assert len(selection.suite_notes(1)) == 1
    assert selection.suite_notes(0) == ()


@pytest.mark.parametrize(
    ("name", "body"),
    [
        ("tests/test_broken.py", "import a_module_that_does_not_exist\n"),
        (
            "tests/test_class.py",
            "import pytest\n\n\n@pytest.mark.parametrize('a', [1])\n"
            "class TestC:\n    def test_x(self):\n        pass\n",
        ),
        ("tests/test_a space.py", "def test_x(:\n"),
    ],
    ids=["module-import", "class-level", "space-in-name"],
)
def test_an_uncollectable_test_file_fails_the_audit_even_when_every_read_is_selected(
    tmp_path, name, body
):
    root = _scratch_repo(tmp_path, resolver=_SELECTS_ALL)
    _add_files(root, {name: body, "pyproject.toml": '[tool.pytest.ini_options]\naddopts = "-rN"\n'})

    verdict = selection.run(root, {**_env(), "FORCE_COLOR": "1"})

    assert not verdict.passed, verdict
    assert name in verdict.reason
