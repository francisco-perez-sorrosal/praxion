"""The cited-run judging of kernel_ledger_checks.py reads no file: it judges what was gathered.

`cited_run_findings` takes the run evidence the checker gathered (the results files, the ones that
could not be read, the run index) and gives the same findings once every file read is denied. The
plant builders are the evidence tests'; the gate modules are imported alone (never
`check_kernel_manifest`), so the mutation sensor can run this file.
"""

from __future__ import annotations

import builtins
import shutil
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import kernel_ledger as kl  # noqa: E402
import kernel_ledger_checks as lc  # noqa: E402
import kernel_run_index as kri  # noqa: E402
import test_kernel_ledger_checks_evidence as ev  # noqa: E402

READS = ("read_bytes", "read_text", "open", "glob", "rglob", "iterdir")


def judged(ledger: kl.Ledger, evidence: lc.RunEvidence) -> list[tuple[str, str, str]]:
    return [(f.kind, f.subject, f.detail) for f in lc.cited_run_findings(ledger, evidence)]


def _denied(*_args: object, **_kwargs: object) -> None:
    raise AssertionError("a file was read while judging")


@contextmanager
def file_reads_denied() -> Iterator[None]:
    """Every way the standard library offers to read a file or list a directory now raises."""
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(builtins, "open", _denied)
        for name in READS:
            patch.setattr(Path, name, _denied)
        yield


def test_the_denial_bites(tmp_path: Path) -> None:
    with file_reads_denied():
        with pytest.raises(AssertionError, match="a file was read"):
            (tmp_path / "x.json").read_bytes()
        with pytest.raises(AssertionError, match="a file was read"):
            open(tmp_path / "x.json", "rb")  # noqa: SIM115 -- the call is the thing denied


def test_judging_gathered_evidence_gives_the_same_findings_with_every_file_read_denied(
    tmp_path: Path,
) -> None:
    ev.plant(tmp_path, ev.whole(ev.EARLY, 13, "underpowered"), ev.whole(ev.PASSING))
    ledger = ev.switched(ev.cited(ev.EARLY, 13, False), ev.cited(ev.PASSING, 30))
    evidence = ev.gathered(tmp_path)
    before = judged(ledger, evidence)
    assert [kind for kind, _, _ in before] == ["I9-run-pairs-differ"]  # the case judges something

    shutil.rmtree(tmp_path / kri.RESULTS_DIR)  # the files are gone, and any attempt to read raises
    with file_reads_denied():
        after = judged(ledger, evidence)

    assert after == before


def test_the_same_gathered_evidence_always_gives_the_same_findings(tmp_path: Path) -> None:
    ev.plant(tmp_path, ev.whole(ev.PASSING, 24, "not clear"))
    ledger = ev.switched(ev.cited(ev.PASSING))
    evidence = ev.gathered(tmp_path)

    assert judged(ledger, evidence) == judged(ledger, evidence) != []


def test_the_judging_uses_the_files_it_was_handed_not_the_directory(tmp_path: Path) -> None:
    index = kri.Adherence({}, frozenset(), {}, tmp_path / "nowhere")
    ledger = ev.switched(ev.cited(ev.PASSING))

    with file_reads_denied():
        found = judged(ledger, lc.RunEvidence((), {}, index))

    assert [kind for kind, _, _ in found] == ["I9-run-missing"]
