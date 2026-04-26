"""Streamlit 4-panel dashboard — self-improving code-review skill demo.

Run: streamlit run hackathon/dashboard.py
"""

from __future__ import annotations

import difflib
import json
import subprocess
import sys
from pathlib import Path

# Streamlit runs this script with only its own dir on sys.path; insert the
# worktree root so `from hackathon.models import ...` resolves.
_WORKTREE_ROOT = Path(__file__).parent.parent
if str(_WORKTREE_ROOT) not in sys.path:
    sys.path.insert(0, str(_WORKTREE_ROOT))

import streamlit as st

REPO_ROOT = Path(__file__).parent.parent
ARTIFACTS = REPO_ROOT / "hackathon" / "artifacts"
FIXTURES = REPO_ROOT / "hackathon" / "fixtures"
PR_A_PATCH = FIXTURES / "pr_A.patch"
PR_B_PATCH = FIXTURES / "pr_B.patch"
PR_C_PATCH = FIXTURES / "pr_C.patch"
PR_D_PATCH = FIXTURES / "pr_D.patch"
GROUND_TRUTH_A = FIXTURES / "ground_truth_A.json"
GROUND_TRUTH_B = FIXTURES / "ground_truth_B.json"
GROUND_TRUTH_C = FIXTURES / "ground_truth_C.json"
GROUND_TRUTH_D = FIXTURES / "ground_truth_D.json"
SKILL_PATH = REPO_ROOT / "hackathon" / "SKILL_DEMO.md"
BACKUP_PATH = ARTIFACTS / "SKILL_v1.md.bak"
SKILL_V2_BACKUP = ARTIFACTS / "SKILL_v2.md.bak"
TIMELINE_PATH = ARTIFACTS / "timeline.json"
SKILL_RUNS_PATH = ARTIFACTS / "skill_runs.jsonl"
TOTAL_ROUNDS = 4
SUBMISSION_PATH = REPO_ROOT / "hackathon" / "SUBMISSION.md"
USE_CASE_PATH = REPO_ROOT / "COGNEE_HACKATHON_USE_CASE.md"
REWRITE_LOG_PATH = ARTIFACTS / "rewrite_log.md"
PROPOSED_FIX_PATH = ARTIFACTS / "proposed_fix.patch"
MISSING_TEST_PATH = ARTIFACTS / "missing_test.py"
FINDINGS_R1_PATH = ARTIFACTS / "findings_r1.json"
FINDINGS_R2_PATH = ARTIFACTS / "findings_r2.json"
REPORT_R1_PATH = ARTIFACTS / "report_r1.md"
REPORT_R2_PATH = ARTIFACTS / "report_r2.md"
DEMO_CMD = [sys.executable, str(REPO_ROOT / "hackathon" / "demo.py")]

_STATUS_COLORS: dict[str, str] = {
    "idle": "#888888",
    "round-1-running": "#1e88e5",
    "round-2-running": "#1e88e5",
    "rewriting": "#8e24aa",
    "done": "#2e7d32",
    "error": "#c62828",
}

# Must be the first Streamlit call.
st.set_page_config(page_title="Praxion Skill Improvement", layout="wide")

# Force long lines in st.code()/markdown <pre> blocks to wrap instead of horizontal-scroll.
# Streamlit's default monospace rendering uses `white-space: pre` which clips long content;
# pre-wrap + word-break keeps SKILL.md and log output readable in the side-by-side layout.
st.markdown(
    """
    <style>
      div[data-testid="stCodeBlock"] pre,
      div[data-testid="stCodeBlock"] code,
      .stCode pre, .stCode code,
      pre, code {
          white-space: pre-wrap !important;
          word-break: break-word !important;
          overflow-wrap: anywhere !important;
      }
    </style>
    """,
    unsafe_allow_html=True,
)

if "status" not in st.session_state:
    st.session_state.status = "idle"
if "next_round" not in st.session_state:
    st.session_state.next_round = 1
if "log_lines" not in st.session_state:
    st.session_state.log_lines = []
if "log_round" not in st.session_state:
    st.session_state.log_round = None


def render_timeline() -> None:
    if not TIMELINE_PATH.exists():
        st.info("No runs yet. Click **Run Round 1** to begin.")
        return
    events: list[dict] = json.loads(TIMELINE_PATH.read_text(encoding="utf-8"))
    if not events:
        st.info("Timeline is empty.")
        return
    emoji_map: dict[str, str] = {
        "missed_bug": "✗ missed",
        "weak_evidence": "⚠ weak",
        "": "✓ caught",
    }
    lines = []
    for ev in events:
        ts = ev.get("ts", "")[:19].replace("T", " ")
        score = ev.get("score", "?")
        label = emoji_map.get(ev.get("error_type", ""), f"◇ r{ev.get('round', '?')}")
        lines.append(f"- **{ts}** — {label} (score={score})")
    st.markdown("\n".join(lines))


def render_diff() -> None:
    if not BACKUP_PATH.exists():
        st.info("v1 baseline not yet backed up — run Round 1 to create it.")
        return
    old_lines = BACKUP_PATH.read_text(encoding="utf-8").splitlines(keepends=True)
    new_lines = SKILL_PATH.read_text(encoding="utf-8").splitlines(keepends=True)
    # unified_diff returns a generator — consume ONCE with join before st.code().
    diff_text = "".join(
        difflib.unified_diff(
            old_lines, new_lines, fromfile="SKILL.md (v1)", tofile="SKILL.md (v2)"
        )
    )
    if diff_text:
        st.code(diff_text, language="diff")
    else:
        st.info("No changes detected between v1 and current SKILL.md.")


def read_skill_runs_local() -> list[dict]:
    """Read SkillRunEntry rows from the local JSONL mirror written by demo.py.

    Decouples the dashboard from Cognee's embedding pipeline so an OpenAI billing
    state does not block visualization. Cognee still holds the canonical record
    for the rubric; this is just the display path.
    """
    from hackathon.models import SkillRunEntry  # noqa: PLC0415

    if not SKILL_RUNS_PATH.exists():
        return []
    rows: list[dict] = []
    for raw in SKILL_RUNS_PATH.read_text(encoding="utf-8").splitlines():
        if not raw.strip():
            continue
        try:
            e = SkillRunEntry.model_validate_json(raw)
            rows.append(
                {
                    "run_id": e.run_id,
                    "skill_id": e.selected_skill_id,
                    "score": e.success_score,
                    "error_type": e.error_type or "—",
                    "summary": e.result_summary[:90],
                }
            )
        except Exception:
            continue
    return sorted(rows, key=lambda r: r["run_id"])


def render_records_table() -> None:
    rows = read_skill_runs_local()
    if not rows:
        st.info("No `SkillRunEntry` records yet — run a round to populate.")
        return
    if len(rows) >= 2:
        delta = rows[-1]["score"] - rows[0]["score"]
        emoji = "📈" if delta > 0 else ("📉" if delta < 0 else "➖")
        st.metric(
            label="Score delta (Round 2 − Round 1)",
            value=f"{rows[-1]['score']:.2f}",
            delta=f"{delta:+.2f}  {emoji}",
        )
    st.dataframe(rows, use_container_width=True, hide_index=True)


_LOG_PHASE_ICON = {
    "Round": "🟢",
    "score": "📊",
    "Cognee": "💾",
    "rewrite": "✏️",
    "REWRITE": "✏️",
    "Fixer": "🔧",
    "Editor": "✏️",
    "Reviewer": "🔍",
    "Sandbox": "📦",
    "Daytona": "📦",
    "ERROR": "❌",
    "Error": "❌",
}


def _decorate_line(line: str) -> str:
    """Prefix log lines with a phase icon when a known keyword is present."""
    for keyword, icon in _LOG_PHASE_ICON.items():
        if keyword in line:
            return f"{icon} {line}"
    return f"   {line}"


_LOG_CAP = 200


def _push_log_line(line: str) -> None:
    """Append a decorated line to the persistent session log (capped at _LOG_CAP)."""
    st.session_state.log_lines.append(line)
    if len(st.session_state.log_lines) > _LOG_CAP:
        st.session_state.log_lines = st.session_state.log_lines[-_LOG_CAP:]


def stream_round(n: int) -> None:
    """Spawn demo.py --round N and stream stdout into st.session_state.log_lines."""
    st.session_state.status = f"round-{n}-running"
    st.session_state.log_round = n
    # Reset log for the new run; previous round's log is replaced (not concatenated)
    # because each round is a self-contained narrative the user wants to inspect cleanly.
    st.session_state.log_lines = []
    placeholder = st.empty()
    with subprocess.Popen(
        [*DEMO_CMD, "--round", str(n)],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    ) as proc:
        assert proc.stdout is not None
        for line in proc.stdout:
            _push_log_line(_decorate_line(line.rstrip()))
            placeholder.code("\n".join(st.session_state.log_lines), language="log")
    st.session_state.status = (
        "done"
        if (proc.returncode == 0 and n >= TOTAL_ROUNDS)
        else ("idle" if proc.returncode == 0 else "error")
    )
    if proc.returncode == 0:
        st.session_state.next_round = n + 1
    st.rerun()


def _render_findings_table(findings_path: Path) -> None:
    """Render findings.json as a tidy dataframe; fall back to raw JSON if malformed."""
    if not findings_path.exists() or findings_path.stat().st_size == 0:
        st.info(f"`{findings_path.name}` not produced yet.")
        return
    try:
        payload = json.loads(findings_path.read_text(encoding="utf-8"))
        findings = payload.get("findings", []) if isinstance(payload, dict) else []
    except json.JSONDecodeError:
        st.code(findings_path.read_text(encoding="utf-8"), language="json")
        return
    if not findings:
        st.info("Empty findings list — the Reviewer flagged nothing.")
        return
    rows = [
        {
            "severity": (f.get("severity") if isinstance(f, dict) else "?") or "?",
            "file": (f.get("file") if isinstance(f, dict) else "?") or "?",
            "line": (f.get("line") if isinstance(f, dict) else 0) or 0,
            "rule": ((f.get("rule") if isinstance(f, dict) else "") or "")[:80],
            "evidence": ((f.get("evidence") if isinstance(f, dict) else "") or "")[
                :120
            ],
        }
        for f in findings
    ]
    fail_count = sum(1 for r in rows if r["severity"] == "FAIL")
    warn_count = sum(1 for r in rows if r["severity"] == "WARN")
    st.caption(f"{len(rows)} finding(s) — {fail_count} FAIL, {warn_count} WARN")
    st.dataframe(rows, use_container_width=True, hide_index=True)


_ROUND_META: dict[int, dict[str, str]] = {
    1: {"label": "baseline", "cycle": "Cycle 1 (mutable defaults)", "kind": "miss"},
    2: {"label": "improved", "cycle": "Cycle 1 (mutable defaults)", "kind": "catch"},
    3: {"label": "baseline", "cycle": "Cycle 2 (broad except)", "kind": "miss"},
    4: {"label": "improved", "cycle": "Cycle 2 (broad except)", "kind": "catch"},
}


def _findings_path(n: int) -> Path:
    return ARTIFACTS / f"findings_r{n}.json"


def _report_path(n: int) -> Path:
    return ARTIFACTS / f"report_r{n}.md"


def _per_round_fix_paths(n: int) -> tuple[Path, Path]:
    return (
        ARTIFACTS / f"proposed_fix_r{n}.patch",
        ARTIFACTS / f"missing_test_r{n}.py",
    )


def _has_round_output(n: int) -> bool:
    fp = _findings_path(n)
    rp = _report_path(n)
    return (fp.exists() and fp.stat().st_size > 0) or (
        rp.exists() and rp.stat().st_size > 0
    )


def _render_round_artifacts(n: int) -> None:
    """Render Round n's review output, plus Fixer artifacts for catch rounds (2, 4)."""
    findings_path = _findings_path(n)
    report_path = _report_path(n)
    has_findings = findings_path.exists() and findings_path.stat().st_size > 0
    has_report = report_path.exists() and report_path.stat().st_size > 0

    if not (has_findings or has_report):
        st.info(f"Round {n} has not run yet. Click **Run Round {n}** to populate.")
        return

    st.markdown(f"**Reviewer findings** &nbsp; `{findings_path.name}`")
    _render_findings_table(findings_path)

    with st.expander(f"Reviewer report ({report_path.name})", expanded=False):
        if has_report:
            st.markdown(report_path.read_text(encoding="utf-8"))
        else:
            st.info("Not produced yet.")

    is_catch_round = _ROUND_META[n]["kind"] == "catch"
    if not is_catch_round:
        st.caption(
            f"Round {n} is a baseline run (review only — no Fixer). Compare with "
            f"Round {n + 1} where the Fixer adds a patch + test below."
        )
        return

    st.markdown("---")
    fix_patch_path, fix_test_path = _per_round_fix_paths(n)
    has_patch = fix_patch_path.exists() and fix_patch_path.stat().st_size > 0
    has_test = fix_test_path.exists() and fix_test_path.stat().st_size > 0
    st.markdown(
        f"**🔧 Fix output** &nbsp; produced by the Fixer (`fix.py`) when Round {n}'s "
        "score ≥ 0.5"
    )
    if not (has_patch or has_test):
        st.info(
            f"Fixer artifacts not produced yet — they appear after Round {n} catches the bug."
        )
        return

    cols = st.columns(2)
    with cols[0]:
        st.markdown(f"**Proposed fix patch** &nbsp; `{fix_patch_path.name}`")
        if has_patch:
            patch_text = fix_patch_path.read_text(encoding="utf-8")
            st.caption(
                f"{len(patch_text.splitlines())} line(s) — applies via `git apply`"
            )
            st.code(patch_text, language="diff")
        else:
            st.info("Not produced yet.")
    with cols[1]:
        st.markdown(f"**Missing test** &nbsp; `{fix_test_path.name}`")
        if has_test:
            test_text = fix_test_path.read_text(encoding="utf-8")
            st.caption(
                f"{len(test_text.splitlines())} line(s) — pytest case the bug should have triggered"
            )
            st.code(test_text, language="python")
        else:
            st.info("Not produced yet.")


def render_round_artifacts_tabs() -> None:
    """Four tabs spanning both improvement cycles — judges compare round-by-round evidence."""
    any_run = any(_has_round_output(n) for n in (1, 2, 3, 4))
    if not any_run:
        st.info(
            "No round artifacts yet. Run Round 1 to populate the first tab. Each "
            "subsequent round adds its own findings + report; even rounds (2, 4) also "
            "add the Fixer's patch + test."
        )
        return

    labels = []
    for n in (1, 2, 3, 4):
        meta = _ROUND_META[n]
        captured = "✓" if _has_round_output(n) else "(pending)"
        labels.append(f"R{n} — {meta['label']} {captured}")
    tabs = st.tabs(labels)
    for tab, n in zip(tabs, (1, 2, 3, 4)):
        with tab:
            meta = _ROUND_META[n]
            st.caption(f"**{meta['cycle']}** · {meta['label']} run")
            _render_round_artifacts(n)


def render_log_panel() -> None:
    """Render the persistent log from session_state; called on every page pass."""
    if not st.session_state.log_lines:
        st.info("No log yet — click **Run Round** to populate.")
        return
    round_label = (
        f"Round {st.session_state.log_round}"
        if st.session_state.log_round is not None
        else "Latest run"
    )
    st.caption(f"{round_label} — {len(st.session_state.log_lines)} line(s) captured")
    st.code("\n".join(st.session_state.log_lines), language="log")


def _read_ground_truth(path: Path) -> dict | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def _render_pr_tab(
    patch_path: Path,
    gt_path: Path,
    bug_summary: str,
    fallback_class: str,
) -> None:
    gt = _read_ground_truth(gt_path) or {}
    gt_lines = gt.get("line_range", ["?", "?"])
    st.markdown(bug_summary)
    st.caption(
        f"Ground truth: bug expected at `{gt.get('file', '?')}:"
        f"{gt_lines[0]}-{gt_lines[1]}` · defect class: "
        f"`{gt.get('defect_class', fallback_class)}`"
    )
    if patch_path.exists():
        st.code(patch_path.read_text(encoding="utf-8"), language="diff")
    else:
        st.info(f"`{patch_path.name}` not found.")


def render_sample_prs() -> None:
    """Show the seeded buggy PRs the demo reviews — context for the audience.

    Two defect classes are shown: the LIVE one (mutable defaults) drives the demo
    runs, and a BONUS one (overly broad exception handlers) is included as a
    showcase of what else the loop could improve on.
    """
    has_a = PR_A_PATCH.exists()
    has_b = PR_B_PATCH.exists()
    if not (has_a or has_b):
        st.warning("PR fixtures not found at `hackathon/fixtures/`.")
        return

    section_tabs = st.tabs(
        [
            "🐛 Live demo defect — mutable defaults",
            "✨ Bonus defect — overly broad exception handlers",
        ]
    )

    with section_tabs[0]:
        st.caption(
            "These two PRs drive the actual Round 1 / Round 2 demo. Same defect class, "
            "different container types — tests the skill's ability to generalize."
        )
        sub = st.tabs(
            [
                "PR-A — Round 1 (mutable list default)",
                "PR-B — Round 2 (mutable set default)",
            ]
        )
        with sub[0]:
            _render_pr_tab(
                PR_A_PATCH,
                GROUND_TRUTH_A,
                "**The bug:** a new function `append_event(payload, history=[])` is "
                "added to `sample_project/events.py`. The empty list default is "
                "evaluated **once** at function-definition time, so every call that "
                "omits `history` shares the same list — state silently leaks between calls.",
                "mutable default,shared state",
            )
        with sub[1]:
            _render_pr_tab(
                PR_B_PATCH,
                GROUND_TRUTH_B,
                "**The bug:** a new function `cache_lookup(key, seen=set())` is added "
                "to `sample_project/cache.py`. Same defect class (mutable default), "
                "different container — tests whether the rule the skill *learned* "
                "in Round 1 generalizes to a sibling case in Round 2.",
                "mutable default,shared state",
            )

    with section_tabs[1]:
        st.caption(
            "Not wired into the live demo runner — included as a showcase. The same "
            "loop machinery would handle this defect class with no code changes; only "
            "the fixtures and ground truths differ. **What the skill currently misses:** "
            "the bare `except:` and `except Exception:` patterns that silently swallow "
            "real bugs."
        )
        sub = st.tabs(
            [
                "PR-C — bare `except:`",
                "PR-D — broad `except Exception:`",
            ]
        )
        with sub[0]:
            _render_pr_tab(
                PR_C_PATCH,
                GROUND_TRUTH_C,
                "**The bug:** `load_config(path)` wraps `json.loads(...)` in a bare "
                "`except:` and returns `DEFAULT_CONFIG`. The bare `except:` catches "
                "**everything** — `KeyboardInterrupt`, `SystemExit`, `MemoryError` — "
                "and silently masks real bugs (corrupt JSON, missing file, permission "
                "denied) as if the file simply did not exist.",
                "bare except,silent error swallowing",
            )
        with sub[1]:
            _render_pr_tab(
                PR_D_PATCH,
                GROUND_TRUTH_D,
                "**The bug:** `is_premium_user(user)` catches `Exception` to handle a "
                "missing `subscription` key, but also masks `AttributeError`, "
                "`TypeError`, and any upstream bug. A user whose code accidentally "
                "passes `None` will look indistinguishable from a non-premium user — "
                "the bug is invisible at runtime.",
                "broad exception,silent error swallowing",
            )


_GUIDE_STEPS: dict[int, str] = {
    1: (
        "**Step 1 of 4 — click `Run Round 1` (mutable defaults baseline)** to send "
        "PR-A through the Daytona sandbox. The skill will likely miss the mutable-"
        "default bug (score < 1.0); the Editor will then patch `## Gotchas` automatically."
    ),
    2: (
        "**Step 2 of 4 — click `Run Round 2` (mutable defaults catch)** to send PR-B "
        "through the sandbox using the v2 skill. Same defect class, different container "
        "— the new bullet should help the skill catch it. Fixer fires on success."
    ),
    3: (
        "**Step 3 of 4 — click `Run Round 3` (broad except baseline)** to send PR-C "
        "through the sandbox. The v2 skill has no rule for overly-broad exception "
        "handlers, so it will likely miss; the Editor will add a second bullet."
    ),
    4: (
        "**Step 4 of 4 — click `Run Round 4` (broad except catch)** to send PR-D "
        "through the v3 skill. With both bullets in place, the skill should catch the "
        "second defect class. Fixer fires again."
    ),
}


def render_guide() -> None:
    """Explain what the user is looking at on the page (4-round, 2-cycle aware)."""
    next_round = st.session_state.next_round
    status = st.session_state.status

    if "running" in status:
        step = "**Round in flight** — watch the Live Demo Log on the right; panels refresh on completion."
    elif status == "done":
        step = (
            "**Demo complete** — the SKILL.md diff, score deltas, and Fixer artifacts "
            "below show two completed self-improvement cycles."
        )
    elif status == "error":
        step = "**Run failed** — see the Live Demo Log for stderr; click `Reset` to start over."
    else:
        step = _GUIDE_STEPS.get(next_round, "**Ready** — click `Run Round 1` to begin.")

    st.markdown(
        f"""
**What is this?** A self-improving Praxion skill demo. The `code-review` skill reviews
four seeded Python pull requests across **two improvement cycles** — each cycle is a
*miss → learn → catch* arc on a different defect class. The skill accumulates rules:
**v1 → v2** (mutable defaults rule added) **→ v3** (broad-except rule added).

{step}

**Loop per cycle:** Reviewer misses → SkillRunEntry recorded → Editor appends a `## Gotchas` bullet → Reviewer catches the sibling defect → Fixer proposes patch + test.
"""
    )


def render_rewrite_log() -> None:
    if not REWRITE_LOG_PATH.exists():
        return
    text = REWRITE_LOG_PATH.read_text(encoding="utf-8").strip()
    if not text:
        return
    with st.expander("Editor rewrite log", expanded=False):
        st.code(text, language="markdown")


def _render_v2_with_highlights(v1_text: str, v2_text: str) -> None:
    """Render the full v2 skill with added lines highlighted in green inline."""
    import html as _html  # noqa: PLC0415

    v1_lines = set(v1_text.splitlines())
    rows: list[str] = []
    for raw in v2_text.splitlines():
        escaped = _html.escape(raw) if raw.strip() else "&nbsp;"
        is_new = raw.strip() and raw not in v1_lines
        bg = "#1b3a2f" if is_new else "transparent"
        bar = "3px solid #2e7d32" if is_new else "3px solid transparent"
        color = "#e8f5e9" if is_new else "#cfd8dc"
        rows.append(
            f'<div style="background:{bg};border-left:{bar};'
            f'padding:1px 10px;color:{color}">{escaped}</div>'
        )
    st.markdown(
        '<div style="font-family:ui-monospace,SFMono-Regular,Menlo,monospace;'
        "font-size:12.5px;line-height:1.55;background:#0e1117;padding:12px;"
        f'border-radius:6px;max-height:520px;overflow:auto">{"".join(rows)}</div>',
        unsafe_allow_html=True,
    )


def render_skill_evolution() -> None:
    """Tabs showing the full SKILL.md text at each accumulated version (v1, v2, v3)."""
    if not SKILL_PATH.exists():
        st.info("`hackathon/SKILL_DEMO.md` not found.")
        return

    has_v1_backup = BACKUP_PATH.exists()
    has_v2_backup = SKILL_V2_BACKUP.exists()
    live_text = SKILL_PATH.read_text(encoding="utf-8")
    v1_text = BACKUP_PATH.read_text(encoding="utf-8") if has_v1_backup else live_text
    v2_text = (
        SKILL_V2_BACKUP.read_text(encoding="utf-8") if has_v2_backup else live_text
    )

    # Determine which version the live text corresponds to.
    # - No v1 backup → live IS v1 (no rounds yet).
    # - v1 backup but no v2 backup → live is v2 (only cycle 1 has run/started).
    # - both backups → live is v3 (cycle 2's editor has fired).
    if not has_v1_backup:
        current_version = 1
    elif not has_v2_backup:
        current_version = 2
    else:
        current_version = 3

    has_v2_diff = has_v1_backup and v1_text != v2_text
    has_v3_diff = has_v2_backup and v2_text != live_text

    tab_labels: list[str] = []
    tab_labels.append(
        f"v1 — original ({len(v1_text):,} chars)"
        if has_v1_backup
        else f"v1 — current baseline ({len(v1_text):,} chars, no rounds yet)"
    )
    if has_v2_diff or current_version >= 2:
        delta = len(v2_text) - len(v1_text)
        sign = "+" if delta >= 0 else ""
        suffix = "after Round 1" if has_v2_backup else "live (cycle 1 in flight)"
        tab_labels.append(f"v2 — {suffix} ({len(v2_text):,} chars, {sign}{delta})")
    if has_v3_diff:
        delta = len(live_text) - len(v2_text)
        sign = "+" if delta >= 0 else ""
        tab_labels.append(
            f"v3 — after Round 3 ({len(live_text):,} chars, {sign}{delta})"
        )
    tabs = st.tabs(tab_labels)

    # v1 tab — original baseline -----------------------------------------------
    with tabs[0]:
        if has_v1_backup:
            st.caption(
                f"Captured to `{BACKUP_PATH.relative_to(REPO_ROOT)}` at the start of "
                "Round 1. The demo's `--reset` restores from here."
            )
        else:
            st.caption(
                f"Live at `{SKILL_PATH.relative_to(REPO_ROOT)}`. No rounds run yet — "
                "this is the current baseline."
            )
        st.code(v1_text, language="markdown")

    # v2 tab — after cycle 1 ---------------------------------------------------
    if len(tabs) >= 2:
        with tabs[1]:
            if has_v2_backup:
                st.caption(
                    f"Snapshotted to `{SKILL_V2_BACKUP.relative_to(REPO_ROOT)}` at the "
                    "start of Round 3 — captures cycle 1's accumulated improvements. "
                    "Lines highlighted green are new relative to v1."
                )
                _render_v2_with_highlights(v1_text, v2_text)
            else:
                st.caption(
                    f"Live at `{SKILL_PATH.relative_to(REPO_ROOT)}` — cycle 1 "
                    "added the first new bullet but cycle 2 hasn't snapshotted v2 yet. "
                    "Lines highlighted green are new relative to v1."
                )
                _render_v2_with_highlights(v1_text, v2_text)

    # v3 tab — after cycle 2 ---------------------------------------------------
    if len(tabs) >= 3:
        with tabs[2]:
            st.caption(
                f"Live at `{SKILL_PATH.relative_to(REPO_ROOT)}` — cycle 2 added "
                "another bullet on top of cycle 1's. Lines highlighted green are new "
                "relative to v2 (the cycle-1 baseline)."
            )
            _render_v2_with_highlights(v2_text, live_text)


def _added_lines(old_text: str, new_text: str) -> list[str]:
    """Return only lines added in `new_text` relative to `old_text` (drops `+ ` prefix)."""
    diff = difflib.unified_diff(
        old_text.splitlines(keepends=False),
        new_text.splitlines(keepends=False),
        n=0,
    )
    out: list[str] = []
    for line in diff:
        if line.startswith("+++") or line.startswith("@@") or not line.startswith("+"):
            continue
        out.append(line[1:])
    return out


def _extract_gotchas_section(text: str) -> str:
    """Slice from '## Gotchas' to the next top-level heading or EOF."""
    marker = "## Gotchas"
    idx = text.find(marker)
    if idx == -1:
        return ""
    rest = text[idx:]
    next_idx = rest.find("\n## ", len(marker))
    return rest if next_idx == -1 else rest[:next_idx]


_CALLOUT_STYLES = {
    "fail": ("#3a1b1b", "#c62828", "#ffcdd2"),
    "learn": ("#1b3a2f", "#2e7d32", "#e8f5e9"),
    "info": ("#1b2a3a", "#1565c0", "#bbdefb"),
    "warn": ("#3a2f1b", "#f9a825", "#fff8e1"),
}


def _callout(kind: str, body_html: str) -> None:
    bg, bar, fg = _CALLOUT_STYLES[kind]
    st.markdown(
        f'<div style="background:{bg};border-left:4px solid {bar};'
        f"padding:12px 16px;border-radius:6px;color:{fg};font-size:14px;"
        f"line-height:1.55;white-space:pre-wrap;"
        f'word-break:break-word">{body_html}</div>',
        unsafe_allow_html=True,
    )


def _find_round_record(target_round: int) -> dict | None:
    rows = read_skill_runs_local()
    suffix = f":r{target_round}:code-review"
    return next((r for r in rows if r["run_id"].endswith(suffix)), None)


_CYCLE_DEFINITIONS: list[dict] = [
    {
        "title": "Cycle 1 — mutable defaults",
        "miss_round": 1,
        "catch_round": 2,
        "before_path": BACKUP_PATH,
        "after_path": SKILL_V2_BACKUP,  # the v2 snapshot taken at start of Round 3
    },
    {
        "title": "Cycle 2 — broad except",
        "miss_round": 3,
        "catch_round": 4,
        "before_path": SKILL_V2_BACKUP,
        "after_path": SKILL_PATH,  # live skill is v3 once cycle 2 has rewritten
    },
]


def _round_rule_citation(n: int) -> str | None:
    """Surface the catch-round finding's `rule` field if it cites a SKILL.md rule."""
    findings_path = ARTIFACTS / f"findings_r{n}.json"
    if not findings_path.exists():
        return None
    try:
        findings = json.loads(findings_path.read_text(encoding="utf-8")).get(
            "findings", []
        )
    except json.JSONDecodeError:
        return None
    for f in findings:
        rule = f.get("rule", "") if isinstance(f, dict) else ""
        if (
            "SKILL.md" in rule
            or "Mutable default" in rule
            or "shared state" in rule.lower()
            or "broad except" in rule.lower()
            or "bare except" in rule.lower()
        ):
            return rule
    return None


def _render_one_cycle(cycle: dict, index: int) -> bool:
    """Render the failure → learning → success arc for one cycle.

    Returns True if the cycle had any visible content (used by the parent panel
    to decide whether to render a global empty-state message).
    """
    miss_n = cycle["miss_round"]
    catch_n = cycle["catch_round"]
    before_path: Path = cycle["before_path"]
    after_path: Path = cycle["after_path"]

    miss = _find_round_record(miss_n)
    catch = _find_round_record(catch_n)

    if miss is None and catch is None and not before_path.exists():
        # Cycle hasn't started at all — render a placeholder so judges see what's pending.
        st.markdown(f"#### {cycle['title']}")
        _callout(
            "info",
            f"Cycle {index + 1} has not started. Click <strong>Run Round {miss_n}</strong> "
            "to begin.",
        )
        return False

    st.markdown(f"#### {cycle['title']}")

    # Diff + bullet detection -----------------------------------------------
    bullet_text: str | None = None
    char_delta = 0
    new_bullets = 0
    if before_path.exists() and after_path.exists():
        before_text = before_path.read_text(encoding="utf-8")
        after_text = after_path.read_text(encoding="utf-8")
        if before_text != after_text:
            before_g = _extract_gotchas_section(before_text)
            after_g = _extract_gotchas_section(after_text)
            added = _added_lines(before_g, after_g)
            if added:
                bullet_text = "\n".join(line for line in added if line.strip()).strip()
                char_delta = len(after_text) - len(before_text)
                new_bullets = max(0, after_g.count("\n- ") - before_g.count("\n- "))

    # Step 1: failure --------------------------------------------------------
    st.markdown(f"##### 1️⃣ &nbsp; What was missed in Round {miss_n}")
    if miss is not None:
        score_str = f"{miss['score']:.1f}"
        err = miss["error_type"] or "—"
        summary = miss["summary"] or "(no summary)"
        _callout(
            "fail",
            f"<strong>Score:</strong> {score_str} &nbsp; · &nbsp; "
            f"<strong>Error:</strong> <code style='background:#5a2a2a;padding:1px 6px;"
            f"border-radius:3px'>{err}</code><br>"
            f"<strong>What happened:</strong> {summary}",
        )
    else:
        st.caption(f"Round {miss_n} record not yet captured.")

    # Step 2: learning -------------------------------------------------------
    st.markdown("##### 2️⃣ &nbsp; What the skill learned")
    if bullet_text is None:
        _callout(
            "warn",
            "<strong>No new bullet detected for this cycle yet.</strong> Either the "
            "Editor has not run, or the rewrite was rejected by the sanity check, or "
            "the cycle hasn't completed.",
        )
    else:
        cols = st.columns(2)
        cols[0].metric("New Gotcha bullets", new_bullets, f"+{new_bullets}")
        cols[1].metric("Characters added", char_delta, f"+{char_delta}")
        _callout("learn", bullet_text.replace("\n", "<br>"))

    # Step 3: success --------------------------------------------------------
    st.markdown(f"##### 3️⃣ &nbsp; What changed in Round {catch_n}")
    if catch is None:
        _callout(
            "info",
            f"Round {catch_n} has not run yet. Click <strong>Run Round {catch_n}</strong> "
            "to see whether the new rule helps the skill catch the sibling defect.",
        )
    else:
        score_str = f"{catch['score']:.1f}"
        err = catch["error_type"] or "(none)"
        delta = catch["score"] - (miss["score"] if miss else 0.0)
        emoji = "📈" if delta > 0 else "➖" if delta == 0 else "📉"
        _callout(
            "info",
            f"<strong>Score:</strong> {score_str} &nbsp; "
            f"<span style='font-size:18px'>{emoji}</span> &nbsp;"
            f"<strong>Δ vs Round {miss_n}:</strong> {delta:+.1f} &nbsp; · &nbsp;"
            f"<strong>Error:</strong> {err}<br>"
            f"<strong>Summary:</strong> {catch['summary']}",
        )
        rule_citation = _round_rule_citation(catch_n)
        if rule_citation:
            st.success(
                f"**Rule citation evidence** — Round {catch_n}'s finding explicitly "
                "references the new rule the Editor wrote:"
            )
            _callout("learn", f"<em>{rule_citation}</em>")
    return True


def render_learned_panel() -> None:
    """Cumulative learning narrative across both improvement cycles."""
    if not SKILL_PATH.exists():
        st.info("`hackathon/SKILL_DEMO.md` not found.")
        return

    if not BACKUP_PATH.exists():
        st.info(
            "No baseline yet — run **Round 1** to capture v1 of the skill. The "
            "loop builds up bullets across two cycles: cycle 1 adds a rule about "
            "mutable defaults; cycle 2 adds a rule about overly-broad exception handlers."
        )
        return

    rendered_any = False
    for index, cycle in enumerate(_CYCLE_DEFINITIONS):
        if index > 0:
            st.markdown("---")
        rendered = _render_one_cycle(cycle, index)
        rendered_any = rendered_any or rendered

    if not rendered_any:
        _callout(
            "warn",
            "<strong>Cycles defined but nothing was rendered.</strong> Re-run Round 1 "
            "and check the rewrite log if this persists.",
        )


# Layout -----------------------------------------------------------------------

st.title("Self-Improving `code-review` Skill — Live Loop")
st.caption(
    "Praxion · Cognee + Daytona Hackathon · "
    f"📄 [SUBMISSION.md](file://{SUBMISSION_PATH}) · "
    f"📐 [Use Case](file://{USE_CASE_PATH})"
)

with st.container(border=True):
    render_guide()

with st.expander(
    "🐛 The buggy code the skill will review (click to inspect both PRs)",
    expanded=False,
):
    render_sample_prs()

_BUTTON_LABELS: dict[int, str] = {
    1: "Run Round 1 — mutable defaults baseline",
    2: "Run Round 2 — mutable defaults catch",
    3: "Run Round 3 — broad except baseline",
    4: "Run Round 4 — broad except catch",
}

col_btn, col_status = st.columns([1, 3])
with col_btn:
    next_round: int = st.session_state.next_round
    btn_label = _BUTTON_LABELS.get(next_round, "Demo complete")
    run_clicked = st.button(
        btn_label, disabled=(next_round > TOTAL_ROUNDS), type="primary"
    )
    reset_clicked = st.button("Reset", help="Restore SKILL.md and clear artifacts")

with col_status:
    color = _STATUS_COLORS.get(st.session_state.status, "#888888")
    st.markdown(
        f'<span style="background:{color};color:#fff;padding:4px 12px;'
        f'border-radius:12px;font-weight:600;font-size:14px">'
        f"status: {st.session_state.status}</span>",
        unsafe_allow_html=True,
    )

left, right = st.columns(2)
with left:
    st.subheader("🧠 What the Skill Learned")
    render_learned_panel()
    st.subheader("📜 Skill Evolution (round by round)")
    render_skill_evolution()
    st.subheader("Improvement Timeline")
    render_timeline()
    st.subheader("SKILL.md cumulative diff (v1 → current)")
    render_diff()
    render_rewrite_log()

with right:
    st.subheader("Run Records (`SkillRunEntry`)")
    st.caption(
        "Mirrored locally from `artifacts/skill_runs.jsonl`; "
        "Cognee dataset `skill-runs` holds the canonical record."
    )
    render_records_table()
    st.subheader("📋 Per-Round Artifacts")
    st.caption(
        "Four rounds across two improvement cycles. Odd rounds (1, 3) are baselines "
        "(review only); even rounds (2, 4) are improved runs that also produce Fixer "
        "artifacts (patch + missing test)."
    )
    render_round_artifacts_tabs()
    st.subheader("Live Demo Log")
    render_log_panel()
    log_area = st.empty()

# Button actions — after layout so panels render first. ----------------------

if reset_clicked:
    subprocess.run([*DEMO_CMD, "--reset"], check=False)
    st.session_state.status = "idle"
    st.session_state.next_round = 1
    st.session_state.log_lines = []
    st.session_state.log_round = None
    st.rerun()

if run_clicked and next_round <= TOTAL_ROUNDS:
    with right:
        with log_area:
            stream_round(next_round)
