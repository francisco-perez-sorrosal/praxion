"""Tests for `ledger_health.py` -- the probe's CLI, digest, and policy surface.

Drives the CLI as a subprocess wherever the assertion is about *behavior*
(the public wire contract a judge or the sentinel consumes) rather than
internal representation -- `ledger_health.py`'s own file does not exist yet,
so every test here is expected to fail at collection or at first invocation
with `ModuleNotFoundError` / a non-existent-script `FileNotFoundError`
surfaced through a non-zero, unexpected subprocess result. That is the RED
signature this file is designed to produce; see `TEST_RESULTS.md`.

The probe's CLI scope here is `--digest` / `--all` / `--ids` / `--class` /
`--repo-root` only -- **not** `--json` (the flat TD07 envelope comes
later, since it needs the anchor/window machinery that step adds). Every
test below stays inside that scope.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

import ledger_health
import ledger_snapshot
import pytest
from _ledger_triage_testkit import (
    IDENTITY,
    build_fixture_repo,
    git_ok,
    one_row_repo,
    tombstone_row,
)

# `base_repo` is a pytest fixture from `conftest.py` (no import needed --
# pytest auto-discovers it by parameter name).

SCRIPT_PATH = Path(__file__).resolve().parent / "ledger_health.py"

REQUIRED_ROW_KEYS = {
    "id",
    "row",
    "key",
    "judgment",
    "candidate_classes",
    "evidence",
    "context",
    "withheld",
    "rank",
}
REQUIRED_ENVELOPE_KEYS = {
    "schema",
    "head",
    "anchor",
    "generated_at",
    "oracles",
    "withheld",
    "rows",
}


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT_PATH), *args],
        capture_output=True,
        text=True,
        check=False,
    )


def _digest(repo_root: Path, *extra: str) -> dict:
    result = _run("--digest", "--repo-root", str(repo_root), *extra)
    assert result.returncode == 0, f"stderr: {result.stderr}"
    return json.loads(result.stdout)


# -- Advisory contract (`--digest` half) ---------------------------------


def test_digest_leaves_ledger_files_byte_identical_and_exits_zero(base_repo: Path) -> None:
    ledger_path = base_repo / ".ai-state" / "TECH_DEBT_LEDGER.md"
    resolved_path = base_repo / ".ai-state" / "TECH_DEBT_RESOLVED.md"
    before = (ledger_path.read_bytes(), resolved_path.read_bytes())
    result = _run("--digest", "--all", "--repo-root", str(base_repo))
    after = (ledger_path.read_bytes(), resolved_path.read_bytes())
    assert result.returncode == 0
    assert before == after
    payload = json.loads(result.stdout)
    assert payload["rows"], "expected findings on the frozen fixture"


def test_script_carries_the_executable_bit() -> None:
    """`os.access(path, X_OK)` -- required by the installer filter so the
    shipped `/triage-debt` command finds this script on `PATH`."""
    assert SCRIPT_PATH.exists(), f"expected {SCRIPT_PATH} to exist"
    assert os.access(SCRIPT_PATH, os.X_OK), f"{SCRIPT_PATH} is missing its executable bit"


def test_the_scripts_catalog_names_every_flag_the_probe_accepts() -> None:
    """Agents read the catalog, not `--help`: a flag it omits is never used, and one it still
    names after removal is passed and fails."""
    flags = set(re.findall(r"--[a-z][a-z-]+", _run("--help").stdout)) - {"--help"}
    catalog = (SCRIPT_PATH.parent / "CLAUDE.md").read_text()
    (entry,) = [line for line in catalog.splitlines() if line.startswith("- `ledger_health.py`")]
    named = set(re.findall(r"--[a-z][a-z-]+", entry))

    assert flags <= named, sorted(flags - named)
    assert named <= flags, sorted(named - flags)


# -- Digest contract --------------------------------------------


def test_digest_envelope_has_every_required_top_level_key(base_repo: Path) -> None:
    payload = _digest(base_repo, "--all")
    assert REQUIRED_ENVELOPE_KEYS <= payload.keys()
    assert payload["schema"] == "ledger-triage-digest/1"


def test_digest_row_carries_every_required_field(base_repo: Path) -> None:
    payload = _digest(base_repo, "--ids", "td-064")
    assert len(payload["rows"]) == 1
    row = payload["rows"][0]
    assert REQUIRED_ROW_KEYS <= row.keys()
    assert row["id"] == "td-064"
    assert row["row"]["notes"], "notes must be carried verbatim, not summarized"


@pytest.mark.parametrize("row_id", ["td-257", "td-264", "td-270", "td-281"])
def test_digest_reports_discriminated_key_status(base_repo: Path, row_id: str) -> None:
    payload = _digest(base_repo, "--ids", row_id)
    assert payload["rows"][0]["key"]["status"] == "discriminated"


def test_digest_all_returns_every_active_row_candidates_first(base_repo: Path) -> None:
    payload = _digest(base_repo, "--all")
    ids = [row["id"] for row in payload["rows"]]
    assert len(ids) == 17, f"expected all 17 fixture rows, got {len(ids)}"
    candidate_ids = {row["id"] for row in payload["rows"] if row["candidate_classes"]}
    first_seven_ids = ids[: len(candidate_ids)]
    assert set(first_seven_ids) == candidate_ids, "candidates must sort first"


def test_ids_filter_restricts_output_to_named_rows(base_repo: Path) -> None:
    payload = _digest(base_repo, "--ids", "td-064,td-185")
    assert {row["id"] for row in payload["rows"]} == {"td-064", "td-185"}


def test_class_filter_restricts_to_rows_carrying_that_evidence_class(base_repo: Path) -> None:
    payload = _digest(base_repo, "--all", "--class", "self-amended")
    for row in payload["rows"]:
        assert "self-amended" in row["candidate_classes"]
    ids = {row["id"] for row in payload["rows"]}
    assert "td-064" in ids
    assert "td-185" not in ids


# -- Withheld reporting (corpus scope) -----------------------------------


def test_missing_adr_corpus_reports_corpus_scope_withheld(tmp_path: Path) -> None:
    repo_root = build_fixture_repo(tmp_path, "base")
    import shutil

    shutil.rmtree(repo_root / ".ai-state" / "decisions")

    payload = _digest(repo_root, "--all")
    corpus_withheld = {
        entry["class"] for entry in payload["withheld"] if entry.get("scope") == "corpus"
    }
    assert "decision-drift" in corpus_withheld
    assert "goal-link-unresolved" in corpus_withheld


# -- Script errors -------------------------------------------------------------------


def test_plugin_cache_repo_root_is_refused_with_exit_two(tmp_path: Path) -> None:
    """An installed plugin's cache is never a project to probe."""
    cache_root = tmp_path / "plugins" / "cache" / "owner" / "praxion" / "1.0.0"
    cache_root.mkdir(parents=True)
    result = _run("--digest", "--repo-root", str(cache_root))
    assert result.returncode == 2
    assert "plugin-cache" in result.stderr


# -- Stamp check: shape is not enough, every anchor must resolve ---------------------------


def _refusals(repo_root: Path, row_id: str, text: str) -> list[str]:
    snapshot = ledger_snapshot.gather(repo_root)
    stamp = _stamp_at(_head_sha(repo_root), text)
    return ledger_health.stamp_refusals(snapshot, row_id, stamp)


def test_a_stamp_whose_anchors_all_resolve_may_be_written(base_repo: Path) -> None:
    assert _refusals(base_repo, "td-270", "kept: scripts/check_gate_liveness.py:1 holds") == []


def test_a_discard_citing_a_decision_that_does_not_exist_is_refused(base_repo: Path) -> None:
    (reason,) = _refusals(base_repo, "td-270", "discarded: made moot by dec-999")
    assert "dec-999" in reason


def test_a_row_cannot_anchor_its_own_discard(base_repo: Path) -> None:
    reasons = _refusals(base_repo, "td-270", "discarded: duplicate of td-270")
    assert any("own stamp" in reason for reason in reasons)


def test_a_merge_into_a_resolved_row_is_refused(base_repo: Path) -> None:
    reasons = _refusals(base_repo, "td-270", "merged into td-095")
    assert any("survivor" in reason for reason in reasons)


def test_a_stamp_for_a_row_that_is_not_active_is_refused(base_repo: Path) -> None:
    (reason,) = _refusals(base_repo, "td-095", "kept: scripts/check_gate_liveness.py:1 holds")
    assert "not an active row" in reason


def test_the_stamp_check_cli_exits_one_on_refusal_and_zero_when_clean(base_repo: Path) -> None:
    head = _head_sha(base_repo)
    clean = _check(
        base_repo, "td-270", _stamp_at(head, "kept: scripts/check_gate_liveness.py:1 ok")
    )
    refused = _check(base_repo, "td-270", _stamp_at(head, "discarded: moot per dec-999"))
    assert clean == (0, "ok\n")
    assert refused[0] == 1
    assert "dec-999" in refused[1]


def test_a_stamp_file_without_a_row_is_a_usage_error(tmp_path: Path) -> None:
    stamp = tmp_path / "stamp.txt"
    stamp.write_text("[triage 2026-09-27 @9ad0e205] kept: a/b.py:1 ok\n")
    assert _run("--stamp-file", str(stamp)).returncode == 2


# -- Stamp check: the stamp arrives in a file, never as a shell argument -------------------


def test_the_stamp_is_never_taken_as_a_shell_argument(base_repo: Path) -> None:
    """Ledger text quoted into a shell line can close its quote early and run a backtick span."""
    stamp = _stamp_at(_head_sha(base_repo), "kept: scripts/check_gate_liveness.py:1 ok")
    result = _run("--repo-root", str(base_repo), "--row", "td-270", "--check-stamp", stamp)
    assert result.returncode == 2


def test_a_stamp_with_apostrophes_and_backtick_spans_reaches_the_check_byte_for_byte(
    tmp_path: Path,
) -> None:
    repo_root = one_row_repo(tmp_path, "Premise.", ())
    premise = "realigned: it's `uv run pre-commit run --all-files` in `$(rm -rf ~)`, don't"
    assert _check(repo_root, "td-902", _stamp_at(_head_sha(repo_root), premise)) == (0, "ok\n")


def test_a_stamp_file_spanning_lines_is_refused(tmp_path: Path) -> None:
    repo_root = one_row_repo(tmp_path, "Premise.", ())
    stamp = _stamp_at(_head_sha(repo_root), "kept: scripts/x.py:1 holds\nsecond line")

    code, out = _check(repo_root, "td-902", stamp)

    assert code == 1
    assert "one line" in out


def test_an_unreadable_stamp_file_is_a_script_error(tmp_path: Path) -> None:
    repo_root = one_row_repo(tmp_path, "Premise.", ())
    missing = str(tmp_path / "absent.txt")
    result = _run("--repo-root", str(repo_root), "--row", "td-902", "--stamp-file", missing)
    assert result.returncode == 2
    assert "--stamp-file" in result.stderr


def test_the_command_passes_every_stamp_through_a_file() -> None:
    command = (SCRIPT_PATH.parents[1] / "commands" / "triage-debt.md").read_text()
    assert "--stamp-file" in command
    assert "--check-stamp" not in command


# -- Stamp check: every anchor is resolved against HEAD, through the real git adapters --------


def _head_sha(repo_root: Path) -> str:
    return git_ok(repo_root, "rev-parse", "HEAD").stdout.strip()


def _stamp_at(sha: str, text: str) -> str:
    return f"[triage 2026-09-27 @{sha}] {text}"


def _check(repo_root: Path, row_id: str, stamp: str, *extra: str) -> tuple[int, str]:
    """Check `stamp` the way the apply step does: written to a file, handed over by path."""
    stamp_file = repo_root.parent / "stamp.txt"
    stamp_file.write_text(stamp + "\n")
    args = ("--repo-root", str(repo_root), "--row", row_id, "--stamp-file", str(stamp_file))
    result = _run(*args, *extra)
    return result.returncode, result.stdout


def _side_branch_commit(repo_root: Path) -> str:
    """A commit on a branch that was never merged: it exists, but HEAD cannot reach it."""
    git_ok(repo_root, "checkout", "-q", "-b", "side")
    (repo_root / "side.txt").write_text("side\n")
    git_ok(repo_root, "add", "side.txt")
    git_ok(repo_root, *IDENTITY, "commit", "-q", "-m", "side work")
    sha = _head_sha(repo_root)
    git_ok(repo_root, "checkout", "-q", "main")
    return sha


def test_a_discard_citing_a_gitignored_file_is_refused_though_it_exists_on_disk(
    base_repo: Path,
) -> None:
    (base_repo / ".gitignore").write_text(".ai-work/\n")
    git_ok(base_repo, "add", ".gitignore")
    git_ok(base_repo, *IDENTITY, "commit", "-q", "-m", "ignore scratch")
    survey = base_repo / ".ai-work" / "run" / "DEBT_TRIAGE.md"
    survey.parent.mkdir(parents=True)
    survey.write_text("line\n" * 20)
    stamp = _stamp_at(_head_sha(base_repo), "discarded: stale per .ai-work/run/DEBT_TRIAGE.md:12")

    code, out = _check(base_repo, "td-270", stamp)

    assert code == 1
    assert ".ai-work/run/DEBT_TRIAGE.md" in out


def test_a_discard_citing_a_commit_on_an_unmerged_branch_is_refused(base_repo: Path) -> None:
    side = _side_branch_commit(base_repo)
    stamp = _stamp_at(_head_sha(base_repo), f"discarded: fixed by {side}")

    code, out = _check(base_repo, "td-270", stamp)

    assert code == 1
    assert side in out


def test_a_discard_citing_an_ancestor_commit_is_accepted(base_repo: Path) -> None:
    head = _head_sha(base_repo)
    assert _check(base_repo, "td-270", _stamp_at(head, f"discarded: fixed by {head}")) == (
        0,
        "ok\n",
    )


@pytest.mark.parametrize("anchor", ["side", "deadbeef1234"])
def test_a_stamp_anchored_to_a_commit_head_cannot_reach_is_refused(
    base_repo: Path, anchor: str
) -> None:
    sha = _side_branch_commit(base_repo) if anchor == "side" else anchor
    stamp = _stamp_at(sha, "kept: scripts/check_gate_liveness.py:1 holds")

    code, out = _check(base_repo, "td-270", stamp)

    assert code == 1
    assert sha in out


# -- Stamp check: the cell the stamp produces must read back as that judgment ---------------


def test_a_stamp_carrying_a_segment_separator_is_refused(base_repo: Path) -> None:
    stamp = _stamp_at(_head_sha(base_repo), "realigned: the premise said a // b")

    code, out = _check(base_repo, "td-270", stamp)

    assert code == 1
    assert "notes" in out


def test_a_stamp_an_unbalanced_backtick_in_the_notes_would_hide_is_refused(
    tmp_path: Path,
) -> None:
    repo_root = one_row_repo(tmp_path, "Premise about `x.", ())
    stamp = _stamp_at(_head_sha(repo_root), "kept: scripts/x.py:1 holds for `x")

    code, _ = _check(repo_root, "td-902", stamp)

    assert code == 1


def test_a_realign_is_checked_against_the_notes_it_rewrites(tmp_path: Path) -> None:
    repo_root = one_row_repo(tmp_path, "Premise about `x.", ())
    stamp = _stamp_at(_head_sha(repo_root), "realigned: the premise named `x")

    notes = tmp_path / "notes.txt"
    notes.write_text("Premise about scripts/x.py.\n")

    assert _check(repo_root, "td-902", stamp)[0] == 1
    assert _check(repo_root, "td-902", stamp, "--notes-file", str(notes)) == (0, "ok\n")


def test_rewritten_notes_reach_the_check_byte_for_byte_from_a_file(tmp_path: Path) -> None:
    """Repo notes carry apostrophes and shell syntax; a file hands them over unquoted."""
    repo_root = one_row_repo(tmp_path, "Premise about `x.", ())
    stamp = _stamp_at(_head_sha(repo_root), "realigned: the premise named `x")
    notes = tmp_path / "notes.txt"
    notes.write_text("It's `$(rm -rf ~)` in scripts/x.py; don't run it.\n")

    assert _check(repo_root, "td-902", stamp, "--notes-file", str(notes)) == (0, "ok\n")


def test_rewritten_notes_spanning_lines_are_refused(tmp_path: Path) -> None:
    """A table cell is one line: a newline inside the notes would split the row."""
    repo_root = one_row_repo(tmp_path, "Premise.", ())
    stamp = _stamp_at(_head_sha(repo_root), "realigned: the premise")
    notes = tmp_path / "notes.txt"
    notes.write_text("First line.\nSecond line.\n")

    code, out = _check(repo_root, "td-902", stamp, "--notes-file", str(notes))

    assert code == 1
    assert "one line" in out


def test_rewritten_notes_carrying_the_table_delimiter_are_refused(tmp_path: Path) -> None:
    """A `|` inside the notes splits the row into one cell too many once it is written."""
    repo_root = one_row_repo(tmp_path, "Premise.", ())
    stamp = _stamp_at(_head_sha(repo_root), "realigned: the premise")
    notes = tmp_path / "notes.txt"
    notes.write_text("Premise a | b.\n")

    code, out = _check(repo_root, "td-902", stamp, "--notes-file", str(notes))

    assert code == 1
    assert "|" in out


def test_a_realign_premise_is_history_so_its_stale_anchors_are_not_resolved(
    tmp_path: Path,
) -> None:
    """A realign keeps the premise it replaced: the path it quoted is gone by definition,
    and a dedup key in it is shaped like a sha. Only the stamp's own anchor must resolve."""
    repo_root = one_row_repo(tmp_path, "Premise.", ())
    premise = "realigned from 37b588259209: cited scripts/old.py:4 under key 37b588259209"

    assert _check(repo_root, "td-902", _stamp_at(_head_sha(repo_root), premise)) == (0, "ok\n")
    assert _check(repo_root, "td-902", _stamp_at("deadbeef1234", premise))[0] == 1


def test_a_discard_still_resolves_every_anchor_it_cites(tmp_path: Path) -> None:
    repo_root = one_row_repo(tmp_path, "Premise.", ())
    stamp = _stamp_at(_head_sha(repo_root), "discarded: moot, see scripts/old.py:4")

    code, out = _check(repo_root, "td-902", stamp)

    assert code == 1
    assert "scripts/old.py" in out


def test_a_realign_onto_a_location_head_does_not_track_is_refused(tmp_path: Path) -> None:
    """A mistyped new location is absent from every later anchor tree, so no run would ever
    flag it: the check is the only place it can be caught."""
    repo_root = one_row_repo(tmp_path, "Premise.", ("scripts/y.py",))
    stamp = _stamp_at(_head_sha(repo_root), "realigned: the premise named scripts/x.py")

    code, out = _check(repo_root, "td-902", stamp, "--location", "scripts/y.py, scripts/typo.py")

    assert code == 1
    assert "scripts/typo.py" in out
    assert _check(repo_root, "td-902", stamp, "--location", "scripts/y.py:1, scripts/")[0] == 0


def test_a_cited_line_past_the_end_of_its_file_is_refused(tmp_path: Path) -> None:
    repo_root = one_row_repo(tmp_path, "Premise.", ())
    head = _head_sha(repo_root)

    code, out = _check(repo_root, "td-902", _stamp_at(head, "kept: scripts/x.py:99 holds"))

    assert code == 1
    assert "scripts/x.py:99" in out
    assert _check(repo_root, "td-902", _stamp_at(head, "kept: scripts/x.py:1 holds"))[0] == 0


def test_rewritten_notes_must_keep_every_segment_and_earlier_stamp(tmp_path: Path) -> None:
    earlier = "[triage 2026-09-01 @abc1234def56] kept: scripts/x.py:1 ok"
    repo_root = one_row_repo(tmp_path, f"Premise. // Amended. // {earlier}", ())
    stamp = _stamp_at(_head_sha(repo_root), "realigned: the premise")
    kept_all, dropped, edited = (
        f"Premise now. // Amended. // {earlier}",
        f"Premise now. // {earlier}",
        f"Premise now. // Amended. // {earlier} and more",
    )

    def check(notes: str) -> int:
        path = tmp_path / "notes.txt"
        path.write_text(notes)
        return _check(repo_root, "td-902", stamp, "--notes-file", str(path))[0]

    assert (check(kept_all), check(dropped), check(edited)) == (0, 1, 1)


# -- Stamp check: a row tombstoned earlier in the same run is still a ledger row --------------


def test_a_survivor_stamp_citing_a_row_merged_earlier_in_the_run_is_accepted(
    base_repo: Path,
) -> None:
    head = _head_sha(base_repo)
    tombstone_row(base_repo, "td-264", _stamp_at(head, "merged into td-257"))
    survivor = _stamp_at(head, "kept: hooks/remind_calibration.py:1 holds, absorbed td-264")

    assert _check(base_repo, "td-257", survivor) == (0, "ok\n")


# -- Index: the ids a run fans out, without the row bodies -----------------------------------


def test_the_index_lists_the_digest_rows_ids_in_rank_order_without_their_bodies(
    base_repo: Path,
) -> None:
    result = _run("--index", "--all", "--repo-root", str(base_repo))
    assert result.returncode == 0, result.stderr
    index, digest = json.loads(result.stdout), _digest(base_repo, "--all")

    assert index["ids"] == [row["id"] for row in digest["rows"]]
    assert "rows" not in index
    assert (index["anchor"], index["examined"]) == (digest["anchor"], digest["examined"])


def test_the_index_and_the_digest_are_exclusive_output_modes(base_repo: Path) -> None:
    assert _run("--index", "--digest", "--repo-root", str(base_repo)).returncode == 2
