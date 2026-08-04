"""Tests for inject_decisions.py -- SessionStart ADR-context injection."""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

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
