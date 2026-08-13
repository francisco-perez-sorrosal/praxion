"""Tests for inject_decisions.py -- SessionStart ADR-context injection."""

from __future__ import annotations

import importlib.util
import io
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

MODULE_PATH = Path(__file__).parent / "inject_decisions.py"

_INDEX_HEADER = (
    "| ID | Title | Status | Category | Date | Tags | Summary |\n"
    "|----|-------|--------|----------|------|------|---------|\n"
)


def _load_module():
    """Load inject_decisions.py by path (hooks/ is not a package)."""
    sys.path.insert(0, str(MODULE_PATH.parent))  # so `import _hook_utils` resolves
    spec = importlib.util.spec_from_file_location("inject_decisions_under_test", MODULE_PATH)
    assert spec is not None
    assert spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


decisions = _load_module()


def _write_index(cwd: Path, body_rows: str) -> None:
    """Create .ai-state/decisions/DECISIONS_INDEX.md with the given table rows."""
    index = cwd / ".ai-state" / "decisions" / "DECISIONS_INDEX.md"
    index.parent.mkdir(parents=True, exist_ok=True)
    index.write_text(_INDEX_HEADER + body_rows, encoding="utf-8")


def _run_hook(
    payload: dict, cwd: Path, extra_env: dict | None = None
) -> subprocess.CompletedProcess:
    """Invoke the hook as a subprocess with a JSON payload on stdin."""
    env = {**os.environ, **(extra_env or {})}
    return subprocess.run(
        [sys.executable, str(MODULE_PATH)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        cwd=str(cwd),
        env=env,
        timeout=10,
    )


def _injected_context(result: subprocess.CompletedProcess) -> str:
    parsed = json.loads(result.stdout)
    return parsed["hookSpecificOutput"]["additionalContext"]


class TestDecisionsInjected:
    """A populated index must surface accepted/proposed decisions (the gate bites)."""

    def test_emits_decision_context_for_accepted_adr(self, tmp_path: Path) -> None:
        _write_index(
            tmp_path,
            "| dec-009 | Dual-layer memory | accepted | architectural | 2026-01-01 | memory | A memory design |\n",
        )
        result = _run_hook({"cwd": str(tmp_path)}, tmp_path)
        assert result.returncode == 0
        context = _injected_context(result)
        assert "## Decision Context (auto-injected)" in context
        assert "dec-009" in context
        assert "Dual-layer memory" in context

    def test_includes_proposed_status(self, tmp_path: Path) -> None:
        _write_index(
            tmp_path,
            "| dec-200 | A proposal | proposed | architectural | 2026-02-02 | x | Some summary |\n",
        )
        context = _injected_context(_run_hook({"cwd": str(tmp_path)}, tmp_path))
        assert "dec-200" in context

    def test_falls_back_to_cwd_when_payload_lacks_cwd(self, tmp_path: Path) -> None:
        _write_index(
            tmp_path,
            "| dec-001 | First | accepted | architectural | 2026-01-01 | a | Sum |\n",
        )
        result = _run_hook({}, tmp_path)
        assert result.returncode == 0
        assert "dec-001" in _injected_context(result)


class TestDecisionsSuppressed:
    """Cases where no context must be emitted."""

    def test_silent_when_index_missing(self, tmp_path: Path) -> None:
        result = _run_hook({"cwd": str(tmp_path)}, tmp_path)
        assert result.returncode == 0
        assert result.stdout.strip() == ""

    def test_silent_when_no_injectable_rows(self, tmp_path: Path) -> None:
        # Only superseded/rejected rows -- none are injectable.
        _write_index(
            tmp_path,
            "| dec-009 | Old | superseded | architectural | 2026-01-01 | x | Gone |\n"
            "| dec-010 | Bad | rejected | architectural | 2026-01-02 | y | Nope |\n",
        )
        result = _run_hook({"cwd": str(tmp_path)}, tmp_path)
        assert result.returncode == 0
        assert result.stdout.strip() == ""

    def test_disable_flag_suppresses_injection(self, tmp_path: Path) -> None:
        _write_index(
            tmp_path,
            "| dec-001 | First | accepted | architectural | 2026-01-01 | a | Sum |\n",
        )
        result = _run_hook(
            {"cwd": str(tmp_path)},
            tmp_path,
            extra_env={decisions.DISABLE_FLAG: "1"},
        )
        assert result.returncode == 0
        assert result.stdout.strip() == ""


class TestFailsOpen:
    """Internal errors must never wedge session creation."""

    def test_malformed_payload_exits_zero(self, tmp_path: Path) -> None:
        result = subprocess.run(
            [sys.executable, str(MODULE_PATH)],
            input="not-json",
            capture_output=True,
            text=True,
            cwd=str(tmp_path),
            timeout=10,
        )
        assert result.returncode == 0

    def test_empty_payload_exits_zero(self, tmp_path: Path) -> None:
        result = subprocess.run(
            [sys.executable, str(MODULE_PATH)],
            input="{}",
            capture_output=True,
            text=True,
            cwd=str(tmp_path),
            timeout=10,
        )
        assert result.returncode == 0


class TestOutputBuilder:
    """Unit-level checks on the ADR output builder."""

    def test_recent_decisions_sorted_first(self) -> None:
        rows = [
            {
                "id": "dec-001",
                "title": "Old",
                "status": "accepted",
                "category": "x",
                "date": "2026-01-01",
                "tags": "a",
                "summary": "s1",
            },
            {
                "id": "dec-050",
                "title": "New",
                "status": "accepted",
                "category": "x",
                "date": "2026-06-01",
                "tags": "b",
                "summary": "s2",
            },
        ]
        out = decisions._build_adr_output(rows, budget=decisions.ADR_SOFT_CAP)
        assert out.index("dec-050") < out.index("dec-001")

    def test_empty_rows_yield_empty_string(self) -> None:
        assert decisions._build_adr_output([], budget=decisions.ADR_SOFT_CAP) == ""

    def test_soft_cap_truncates_and_footers(self) -> None:
        rows = [
            {
                "id": f"dec-{i:03d}",
                "title": "T" * 40,
                "status": "accepted",
                "category": "architectural",
                "date": f"2026-01-{i:02d}",
                "tags": "tag",
                "summary": "S" * 60,
            }
            for i in range(1, 40)
        ]
        out = decisions._build_adr_output(rows, budget=decisions.ADR_SOFT_CAP)
        assert len(out) <= decisions.ADR_SOFT_CAP
        assert "more decisions" in out


def _row(id_: str, title: str, date: str, tags: str) -> dict:
    """Build an index row dict for ranking tests."""
    return {
        "id": id_,
        "title": title,
        "status": "accepted",
        "category": "architectural",
        "date": date,
        "tags": tags,
        "summary": "s",
    }


class TestSessionTokens:
    """Topical tokens derived from the session's git context."""

    def test_tokenizes_path_dropping_extensions_and_noise(self) -> None:
        tokens = decisions._tokenize("scripts/finalize_adrs.py")
        assert "finalize" in tokens
        assert "adrs" in tokens
        assert "py" not in tokens

    def test_drops_short_and_numeric_fragments(self) -> None:
        assert decisions._tokenize("a/bc/123/observability") == {"observability"}

    def test_domain_directories_survive_as_topical_signal(self) -> None:
        """`skills` is a real ADR tag, so editing under skills/ is evidence."""
        assert "skills" in decisions._tokenize("skills/refactoring/SKILL.md")

    def test_no_git_repo_yields_no_tokens(self, tmp_path: Path) -> None:
        assert decisions._session_tokens(tmp_path) == {}


class TestTermMatching:
    """Containment matching stands in for a stemmer."""

    def test_plural_path_token_matches_singular_tag(self) -> None:
        assert decisions._terms_match("adrs", "adr")

    def test_token_matches_compound_tag(self) -> None:
        assert decisions._terms_match("finalize", "adr-finalize")

    def test_three_char_token_does_not_match_by_containment(self) -> None:
        """Three-char tags are real (adr, api, mcp); containment stays >=4 so
        `adr` cannot match `quadrant`."""
        assert not decisions._terms_match("api", "rapid")
        assert not decisions._terms_match("adr", "quadrant")

    def test_short_stem_is_not_depluralized(self) -> None:
        """`css` must not collapse to `cs` and start matching unrelated terms."""
        assert decisions._singular("css") == "css"
        assert decisions._singular("rules") == "rule"


class TestRelevanceRanking:
    """Relevance outranks recency; absent signal preserves recency exactly."""

    def test_relevant_older_decision_outranks_irrelevant_newer_one(self) -> None:
        rows = [
            _row("dec-001", "ADR finalize scope", "2026-01-01", "adr, finalize"),
            _row("dec-050", "Dashboard charting", "2026-06-01", "dashboard, charts"),
        ]
        out = decisions._build_adr_output(
            rows, budget=decisions.ADR_SOFT_CAP, tokens={"finalize": 3, "adrs": 3}
        )
        assert out.index("dec-001") < out.index("dec-050")

    def test_without_tokens_ranking_is_pure_recency(self) -> None:
        """No session signal must reproduce the previous behavior exactly."""
        rows = [
            _row("dec-001", "ADR finalize scope", "2026-01-01", "adr, finalize"),
            _row("dec-050", "Dashboard charting", "2026-06-01", "dashboard, charts"),
        ]
        out = decisions._build_adr_output(rows, budget=decisions.ADR_SOFT_CAP, tokens={})
        assert out.index("dec-050") < out.index("dec-001")

    def test_recency_breaks_ties_among_equally_relevant_rows(self) -> None:
        rows = [
            _row("dec-001", "ADR scope", "2026-01-01", "adr"),
            _row("dec-050", "ADR index", "2026-06-01", "adr"),
        ]
        out = decisions._build_adr_output(rows, budget=decisions.ADR_SOFT_CAP, tokens={"adr": 3})
        assert out.index("dec-050") < out.index("dec-001")

    def test_relevance_counts_distinct_tokens_not_repeats(self) -> None:
        """Breadth of overlap, weighted -- one repeated term cannot dominate."""
        row = _row("dec-001", "adr adr adr adr", "2026-01-01", "adr, adr, adr")
        assert decisions._relevance(row, {"adr": 3}) == 3


class TestSignalWeighting:
    """Signal proximity decides, so mechanical history cannot outvote the task."""

    def test_worktree_outweighs_history(self) -> None:
        current = _row("dec-001", "Decision injection ranking", "2026-01-01", "hooks, inject")
        adjacent = _row("dec-050", "Onboarding plugin manifest", "2026-06-01", "onboard, plugin")
        tokens = {
            "inject": decisions._WEIGHT_WORKTREE,
            "onboard": decisions._WEIGHT_HISTORY,
            "plugin": decisions._WEIGHT_HISTORY,
        }
        out = decisions._build_adr_output(
            [current, adjacent], budget=decisions.ADR_SOFT_CAP, tokens=tokens
        )
        assert out.index("dec-001") < out.index("dec-050")

    def test_mechanical_commit_is_excluded_from_history(self, tmp_path: Path) -> None:
        """A release bump touches most of the repo; its tokens describe nothing.

        Regression guard for the observed failure: a version-bump commit
        flooded the token set and surfaced onboarding decisions during
        ADR-finalize work.
        """
        subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
        subprocess.run(["git", "config", "user.email", "t@t.t"], cwd=tmp_path, check=True)
        subprocess.run(["git", "config", "user.name", "t"], cwd=tmp_path, check=True)
        for i in range(decisions._MAX_COMMIT_FILES + 5):
            (tmp_path / f"mechanical{i}.py").write_text("x", encoding="utf-8")
        subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True)
        subprocess.run(["git", "commit", "-qm", "bump"], cwd=tmp_path, check=True)

        assert decisions._recent_commit_paths(tmp_path) == []

    def test_focused_commit_is_kept(self, tmp_path: Path) -> None:
        subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
        subprocess.run(["git", "config", "user.email", "t@t.t"], cwd=tmp_path, check=True)
        subprocess.run(["git", "config", "user.name", "t"], cwd=tmp_path, check=True)
        (tmp_path / "observability.py").write_text("x", encoding="utf-8")
        subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True)
        subprocess.run(["git", "commit", "-qm", "feat"], cwd=tmp_path, check=True)

        assert decisions._recent_commit_paths(tmp_path) == [["observability.py"]]


# ---------------------------------------------------------------------------
# In-process drive of the index reader, the table parser, and main().
#
# The subprocess tests above pin the hook's runtime shape; the parser they
# exercise is the widest untested surface in the module, and it is the one
# thing standing between a hand-edited DECISIONS_INDEX.md and injected
# nonsense.
# ---------------------------------------------------------------------------


def _drive_main(payload_text: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """Run `main()` in-process with `payload_text` standing in for stdin."""
    monkeypatch.setattr(sys, "stdin", io.StringIO(payload_text))
    decisions.main()


def _index_path(cwd: Path) -> Path:
    return cwd / ".ai-state" / "decisions" / "DECISIONS_INDEX.md"


class TestIndexReading:
    def test_returns_the_text_of_a_populated_index(self, tmp_path: Path) -> None:
        _write_index(
            tmp_path, "| dec-001 | T | accepted | architectural | 2026-01-01 | adr | s |\n"
        )

        content = decisions._read_decisions_index(_index_path(tmp_path))

        assert content is not None
        assert "dec-001" in content

    def test_absent_index_reads_as_nothing_to_inject(self, tmp_path: Path) -> None:
        assert decisions._read_decisions_index(_index_path(tmp_path)) is None

    def test_whitespace_only_index_reads_as_nothing_to_inject(self, tmp_path: Path) -> None:
        index = _index_path(tmp_path)
        index.parent.mkdir(parents=True)
        index.write_text("   \n\n\t\n", encoding="utf-8")

        assert decisions._read_decisions_index(index) is None

    def test_an_unreadable_index_degrades_instead_of_raising(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _write_index(tmp_path, "| dec-001 | T | accepted | a | 2026-01-01 | adr | s |\n")

        def _unreadable(*args: object, **kwargs: object) -> str:
            raise OSError("permission denied")

        monkeypatch.setattr(Path, "read_text", _unreadable)

        assert decisions._read_decisions_index(_index_path(tmp_path)) is None


class TestIndexParsing:
    """The markdown table parser: what becomes an injectable row, and what does not."""

    def test_parses_every_column_of_a_well_formed_row(self) -> None:
        content = _INDEX_HEADER + (
            "| dec-042 | Adopt uv | accepted | architectural | 2026-03-04 | tooling, uv | Faster |\n"
        )

        rows = decisions._parse_index_rows(content)

        assert rows == [
            {
                "id": "dec-042",
                "title": "Adopt uv",
                "status": "accepted",
                "category": "architectural",
                "date": "2026-03-04",
                "tags": "tooling, uv",
                "summary": "Faster",
            }
        ]

    @pytest.mark.parametrize("status", ["accepted", "proposed", "ACCEPTED", "Proposed"])
    def test_live_decisions_are_injectable_whatever_the_status_casing(self, status: str) -> None:
        content = _INDEX_HEADER + f"| dec-001 | T | {status} | a | 2026-01-01 | adr | s |\n"

        assert len(decisions._parse_index_rows(content)) == 1

    @pytest.mark.parametrize("status", ["superseded", "rejected", "retired", "re-affirmation"])
    def test_settled_decisions_are_not_injected_as_live_constraints(self, status: str) -> None:
        # Injecting a superseded decision would present a reversed constraint
        # to every agent as though it still held.
        content = _INDEX_HEADER + f"| dec-001 | T | {status} | a | 2026-01-01 | adr | s |\n"

        assert decisions._parse_index_rows(content) == []

    @pytest.mark.parametrize(
        "line",
        [
            "Some prose paragraph above the table.",
            "",
            "   ",
            "| dec-001 | T | accepted |",
            "| dec-001 | T | accepted | a | 2026-01-01 | adr |",
        ],
        ids=["prose", "blank", "whitespace", "three-columns", "six-columns"],
    )
    def test_lines_that_are_not_complete_rows_are_skipped(self, line: str) -> None:
        assert decisions._parse_index_rows(_INDEX_HEADER + line + "\n") == []

    def test_the_header_and_separator_never_become_decisions(self) -> None:
        # The header alone must yield nothing -- otherwise "ID"/"Title" would
        # be injected as a decision on every session start.
        assert decisions._parse_index_rows(_INDEX_HEADER) == []

    def test_keeps_the_live_rows_of_a_mixed_index(self) -> None:
        content = _INDEX_HEADER + (
            "| dec-001 | Old | superseded | a | 2026-01-01 | adr | s |\n"
            "| dec-002 | New | accepted | a | 2026-02-01 | adr | s |\n"
            "not a table row at all\n"
            "| dec-003 | Draft | proposed | a | 2026-03-01 | adr | s |\n"
        )

        assert [row["id"] for row in decisions._parse_index_rows(content)] == ["dec-002", "dec-003"]


class TestGitSignalDegradation:
    def test_a_missing_git_binary_yields_no_signal_rather_than_a_crash(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def _no_git(*args: object, **kwargs: object):
            raise OSError("git: command not found")

        monkeypatch.setattr(decisions.subprocess, "run", _no_git)

        assert decisions._git_lines(tmp_path, "status", "--porcelain") == []

    def test_a_hung_git_call_yields_no_signal(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def _hangs(*args: object, **kwargs: object):
            raise subprocess.TimeoutExpired(cmd="git", timeout=1)

        monkeypatch.setattr(decisions.subprocess, "run", _hangs)

        assert decisions._git_lines(tmp_path, "log") == []


class TestOutputBudgetFloor:
    def test_a_single_row_too_large_for_the_budget_injects_nothing(self) -> None:
        # Rather than emitting a header with an empty body, the builder yields
        # nothing at all so `main()` can stay silent.
        oversized = _row("dec-001", "T" * 500, "2026-01-01", "adr")

        assert decisions._build_adr_output([oversized], budget=100) == ""

    def test_no_rows_injects_nothing(self) -> None:
        assert decisions._build_adr_output([], budget=4000) == ""


class TestEmittedEnvelope:
    def test_context_is_wrapped_in_the_session_start_hook_envelope(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        decisions._emit_additional_context("hello")

        parsed = json.loads(capsys.readouterr().out)
        assert parsed["hookSpecificOutput"]["hookEventName"] == "SessionStart"
        assert parsed["hookSpecificOutput"]["additionalContext"] == "hello"


class TestMainInProcess:
    def test_injects_the_decisions_of_a_populated_index(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        _write_index(
            tmp_path, "| dec-042 | Adopt uv | accepted | a | 2026-03-04 | tooling | Faster |\n"
        )

        _drive_main(json.dumps({"cwd": str(tmp_path)}), monkeypatch)

        context = json.loads(capsys.readouterr().out)["hookSpecificOutput"]["additionalContext"]
        assert context.startswith(decisions._ADR_HEADER)
        assert "dec-042" in context

    def test_stays_silent_when_the_project_has_no_index(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        _drive_main(json.dumps({"cwd": str(tmp_path)}), monkeypatch)

        assert capsys.readouterr().out == ""

    def test_stays_silent_when_no_row_is_injectable(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        _write_index(tmp_path, "| dec-001 | Old | superseded | a | 2026-01-01 | adr | s |\n")

        _drive_main(json.dumps({"cwd": str(tmp_path)}), monkeypatch)

        assert capsys.readouterr().out == ""

    def test_kill_switch_suppresses_injection(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        _write_index(tmp_path, "| dec-042 | Adopt uv | accepted | a | 2026-03-04 | tooling | s |\n")
        monkeypatch.setenv(decisions.DISABLE_FLAG, "1")

        _drive_main(json.dumps({"cwd": str(tmp_path)}), monkeypatch)

        assert capsys.readouterr().out == ""

    def test_falls_back_to_the_process_directory_when_the_payload_omits_cwd(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        _write_index(tmp_path, "| dec-042 | Adopt uv | accepted | a | 2026-03-04 | tooling | s |\n")
        monkeypatch.chdir(tmp_path)

        _drive_main("{}", monkeypatch)

        assert "dec-042" in capsys.readouterr().out

    def test_unparseable_payload_still_resolves_from_the_process_directory(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        _write_index(tmp_path, "| dec-042 | Adopt uv | accepted | a | 2026-03-04 | tooling | s |\n")
        monkeypatch.chdir(tmp_path)

        _drive_main("<<not json>>", monkeypatch)

        assert "dec-042" in capsys.readouterr().out

    @pytest.mark.parametrize("payload_text", ["[]", "null", '"a bare string"', "123"])
    def test_well_formed_non_object_payload_still_resolves_from_the_process_directory(
        self,
        payload_text: str,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        _write_index(tmp_path, "| dec-042 | Adopt uv | accepted | a | 2026-03-04 | tooling | s |\n")
        monkeypatch.chdir(tmp_path)

        _drive_main(payload_text, monkeypatch)

        assert "dec-042" in capsys.readouterr().out


@pytest.fixture
def signalled_repo(tmp_path: Path) -> Path:
    """A repo carrying all three ranking signals, each with distinct tokens.

    history -> `billing/invoicing.py` (committed)
    branch  -> `feature/telemetry-relay`
    worktree-> `warehouse/shipment.py` (uncommitted)

    Keeping the token sets disjoint is what makes the weights readable: a
    token appearing in two signals takes the higher weight, which would hide
    a mis-weighted signal behind a correctly weighted one.
    """
    repo = tmp_path / "signalled"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.email", "t@example.com"], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.name", "test"], check=True)

    committed = repo / "billing" / "invoicing.py"
    committed.parent.mkdir()
    committed.write_text("x\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-q", "-m", "seed"], check=True)

    subprocess.run(
        ["git", "-C", str(repo), "checkout", "-q", "-b", "feature/telemetry-relay"], check=True
    )

    dirty = repo / "warehouse" / "shipment.py"
    dirty.parent.mkdir()
    dirty.write_text("y\n", encoding="utf-8")
    return repo


class TestSessionSignalWeighting:
    """What the session is editing outranks what it is merely adjacent to."""

    def test_working_tree_outranks_branch_which_outranks_history(
        self, signalled_repo: Path
    ) -> None:
        tokens = decisions._session_tokens(signalled_repo)

        assert tokens["warehouse"] == decisions._WEIGHT_WORKTREE
        assert tokens["telemetry"] == decisions._WEIGHT_BRANCH
        assert tokens["billing"] == decisions._WEIGHT_HISTORY
        assert tokens["warehouse"] > tokens["telemetry"] > tokens["billing"]

    def test_default_branch_name_contributes_no_topical_signal(self, main_repo_on_main: Path):
        tokens = decisions._session_tokens(main_repo_on_main)

        # "main"/"master"/"HEAD" describe no topic; treating them as one would
        # score every decision tagged `main` on every default-branch session.
        assert "main" not in tokens
        assert "master" not in tokens

    def test_a_mechanical_commit_does_not_flood_the_token_set(self, tmp_path: Path) -> None:
        # The documented failure this filter exists to prevent: a wide
        # release-bump commit contributes more tokens than every real commit
        # combined, and outvotes the handful describing the actual task.
        repo = tmp_path / "bulk"
        repo.mkdir()
        subprocess.run(["git", "init", "-q", str(repo)], check=True)
        subprocess.run(["git", "-C", str(repo), "config", "user.email", "t@e.com"], check=True)
        subprocess.run(["git", "-C", str(repo), "config", "user.name", "t"], check=True)
        bulk_dir = repo / "vendored"
        bulk_dir.mkdir()
        for index in range(decisions._MAX_COMMIT_FILES + 5):
            (bulk_dir / f"module{index}.py").write_text("x\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True)
        subprocess.run(["git", "-C", str(repo), "commit", "-q", "-m", "bulk"], check=True)

        tokens = decisions._session_tokens(repo)

        assert "vendored" not in tokens

    def test_a_focused_commit_of_the_same_shape_does_contribute(self, tmp_path: Path) -> None:
        # The inverse of the filter above: proves it discriminates by breadth
        # rather than suppressing history wholesale.
        repo = tmp_path / "focused"
        repo.mkdir()
        subprocess.run(["git", "init", "-q", str(repo)], check=True)
        subprocess.run(["git", "-C", str(repo), "config", "user.email", "t@e.com"], check=True)
        subprocess.run(["git", "-C", str(repo), "config", "user.name", "t"], check=True)
        focused_dir = repo / "vendored"
        focused_dir.mkdir()
        for index in range(3):
            (focused_dir / f"module{index}.py").write_text("x\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True)
        subprocess.run(["git", "-C", str(repo), "commit", "-q", "-m", "focused"], check=True)

        assert decisions._session_tokens(repo)["vendored"] == decisions._WEIGHT_HISTORY


@pytest.fixture
def main_repo_on_main(tmp_path: Path) -> Path:
    """A clean repo sitting on the default branch -- the common session shape."""
    repo = tmp_path / "onmain"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main", str(repo)], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.email", "t@example.com"], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.name", "test"], check=True)
    (repo / "README.md").write_text("seed\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-q", "-m", "init"], check=True)
    return repo


class TestUnreadableStdin:
    def test_a_hook_whose_stdin_cannot_be_read_still_injects_from_the_process_directory(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        _write_index(tmp_path, "| dec-042 | Adopt uv | accepted | a | 2026-03-04 | tooling | s |\n")
        monkeypatch.chdir(tmp_path)

        class _Unreadable:
            def read(self) -> str:
                raise OSError("stdin is closed")

        monkeypatch.setattr(sys, "stdin", _Unreadable())

        decisions.main()

        assert "dec-042" in capsys.readouterr().out


class TestOversizedIndexRow:
    def test_a_row_too_large_for_the_budget_yields_silence_not_a_bare_header(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        # A header with nothing under it is worse than no injection: it spends
        # context to tell the agent that decisions exist without naming one.
        huge_title = "T" * (decisions.ADR_SOFT_CAP + 100)
        _write_index(
            tmp_path, f"| dec-001 | {huge_title} | accepted | a | 2026-01-01 | adr | s |\n"
        )

        _drive_main(json.dumps({"cwd": str(tmp_path)}), monkeypatch)

        assert capsys.readouterr().out == ""
