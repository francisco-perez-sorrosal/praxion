"""Behavioral tests for Praxion hackathon mode.

This is the Guardrail-1 surface that keeps both Praxion process modes coherent
in CI. It covers six behavioral areas:

  1. Independence regression — with PRAXION_HACKATHON_MODE unset/0 the two
     affected hooks (remind_adr.py, inject_process_framing.py) behave exactly
     as they did before hackathon mode existed.
  2. remind_adr silencing — with the flag on, the ADR advisory is suppressed
     even when architectural files are staged without an ADR.
  3. inject_process_framing consistency check — flag OFF + a `## Hackathon Mode`
     block left in CLAUDE.md emits the consistency warning.
  4. inject_process_framing test-discipline reminder — the same condition emits
     the coverage-pass reminder.
  5. Canonical block sync — `sync_canonical_blocks.py --check` exits 0.
  6. Sentinel graduation threshold — the >40-source-files-OR->150-commits rule
     that drives the HK01 advisory finding.

The two hook modules live in `hooks/` and import `_hook_utils` as a sibling
module (no package). They are loaded here via `importlib` with `hooks/` placed
on `sys.path` so the sibling import resolves. Loading happens inside each test
body so a missing module surfaces as a per-test failure rather than a
collection-time crash.
"""

from __future__ import annotations

import importlib.util
import io
import json
import subprocess
import sys
from pathlib import Path
from types import ModuleType
from unittest.mock import patch

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
HOOKS_DIR = PROJECT_ROOT / "hooks"
SYNC_SCRIPT = PROJECT_ROOT / "scripts" / "sync_canonical_blocks.py"

HACKATHON_FLAG = "PRAXION_HACKATHON_MODE"
HACKATHON_HEADING = "## Hackathon Mode"


# ---------------------------------------------------------------------------
# Module loading — hooks/ is not a package; load by file path with hooks/ on
# sys.path so the `from _hook_utils import is_disabled` sibling import resolves.
# ---------------------------------------------------------------------------


def _load_hook(module_name: str) -> ModuleType:
    """Load a hook module from hooks/ by name (no .py suffix).

    Adds hooks/ to sys.path for the duration of the import so the module's
    `from _hook_utils import ...` sibling import resolves.
    """
    script_path = HOOKS_DIR / f"{module_name}.py"
    spec = importlib.util.spec_from_file_location(module_name, script_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot build import spec for {script_path}.")
    module = importlib.util.module_from_spec(spec)
    hooks_dir_str = str(HOOKS_DIR)
    added = hooks_dir_str not in sys.path
    if added:
        sys.path.insert(0, hooks_dir_str)
    try:
        spec.loader.exec_module(module)
    finally:
        if added:
            sys.path.remove(hooks_dir_str)
    return module


def _run_hook_capture(module: ModuleType, stdin_text: str) -> str:
    """Call module.main() with stdin patched; return raw stdout text.

    The hook entry points are exception-swallowing (fail-open) and never call
    sys.exit with a non-zero code, so no SystemExit handling is needed.
    """
    captured = io.StringIO()
    with (
        patch.object(sys, "stdin", io.StringIO(stdin_text)),
        patch.object(sys, "stdout", captured),
    ):
        module.main()
    return captured.getvalue()


def _stdout_objects(raw: str) -> list[dict]:
    """Parse stdout that may contain zero or more newline-delimited JSON objects.

    inject_process_framing emits one JSON object per advisory; the consistency
    path emits two. An empty/whitespace stdout yields an empty list.
    """
    return [json.loads(line) for line in raw.splitlines() if line.strip()]


def _commit_payload(command: str) -> str:
    """Build a PreToolUse stdin payload for a Bash tool invocation."""
    return json.dumps({"tool_input": {"command": command}})


def _prompt_payload(prompt: str, cwd: str, transcript_path: str = "") -> str:
    """Build a UserPromptSubmit stdin payload."""
    return json.dumps(
        {
            "hookEventName": "UserPromptSubmit",
            "prompt": prompt,
            "cwd": cwd,
            "transcript_path": transcript_path,
        }
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _clean_hackathon_env(monkeypatch):
    """Every test starts with PRAXION_HACKATHON_MODE and the inject opt-out unset."""
    monkeypatch.delenv(HACKATHON_FLAG, raising=False)
    monkeypatch.delenv("PRAXION_DISABLE_PROCESS_INJECT", raising=False)


def _make_git_repo_with_staged_architectural_file(tmp_path: Path) -> Path:
    """Create a git repo in tmp_path with an architectural file staged, no ADR.

    Returns the repo path. The staged file (`agents/some-agent.md`) matches
    remind_adr's architectural patterns; no ADR is staged or committed, so a
    baseline (flag-off) remind_adr run would emit the advisory.
    """
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=tmp_path,
        check=True,
    )
    subprocess.run(["git", "config", "user.name", "Test"], cwd=tmp_path, check=True)
    # An initial non-architectural commit so HEAD exists for diff-tree.
    (tmp_path / "README.md").write_text("seed\n")
    subprocess.run(["git", "add", "README.md"], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "seed"], cwd=tmp_path, check=True)
    # Stage an architectural file with no accompanying ADR.
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir()
    (agents_dir / "some-agent.md").write_text("# Some Agent\n")
    subprocess.run(["git", "add", "agents/some-agent.md"], cwd=tmp_path, check=True)
    return tmp_path


# ===========================================================================
# Independence regression — remind_adr.py with the flag unset behaves as before
# ===========================================================================


def test_remind_adr_warns_for_staged_architectural_file_when_flag_unset(
    tmp_path, monkeypatch, capsys
):
    """Baseline: flag unset, architectural file staged, no ADR — advisory fires."""
    repo = _make_git_repo_with_staged_architectural_file(tmp_path)
    monkeypatch.chdir(repo)
    module = _load_hook("remind_adr")

    _run_hook_capture(module, _commit_payload("git commit -m 'change agent'"))

    # remind_adr writes its advisory to stderr; capsys captures it because the
    # hook prints to the real sys.stderr (not patched by _run_hook_capture).
    stderr = capsys.readouterr().err
    assert "[adr-reminder]" in stderr, (
        "With the flag unset and an architectural file staged without an ADR, "
        f"remind_adr must emit its advisory. Got stderr: {stderr!r}"
    )


def test_remind_adr_silent_for_non_architectural_file_when_flag_unset(
    tmp_path, monkeypatch, capsys
):
    """Baseline: flag unset, only a non-architectural file staged — no advisory."""
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=tmp_path,
        check=True,
    )
    subprocess.run(["git", "config", "user.name", "Test"], cwd=tmp_path, check=True)
    (tmp_path / "README.md").write_text("seed\n")
    subprocess.run(["git", "add", "README.md"], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "seed"], cwd=tmp_path, check=True)
    (tmp_path / "notes.txt").write_text("just a note\n")
    subprocess.run(["git", "add", "notes.txt"], cwd=tmp_path, check=True)
    monkeypatch.chdir(tmp_path)
    module = _load_hook("remind_adr")

    _run_hook_capture(module, _commit_payload("git commit -m 'add notes'"))

    stderr = capsys.readouterr().err
    assert "[adr-reminder]" not in stderr, (
        "A non-architectural staged file must not trigger the ADR advisory. "
        f"Got stderr: {stderr!r}"
    )


def test_remind_adr_silent_for_non_commit_command_when_flag_unset(
    tmp_path, monkeypatch, capsys
):
    """Baseline: flag unset, command is not `git commit` — hook is inert."""
    repo = _make_git_repo_with_staged_architectural_file(tmp_path)
    monkeypatch.chdir(repo)
    module = _load_hook("remind_adr")

    _run_hook_capture(module, _commit_payload("git status"))

    stderr = capsys.readouterr().err
    assert "[adr-reminder]" not in stderr, (
        "remind_adr must only act on `git commit` commands. "
        f"Got stderr for `git status`: {stderr!r}"
    )


# ===========================================================================
# remind_adr hackathon silencing — flag on suppresses the advisory
# ===========================================================================


def test_remind_adr_silent_for_staged_architectural_file_when_hackathon_on(
    tmp_path, monkeypatch, capsys
):
    """With PRAXION_HACKATHON_MODE=1 the ADR advisory is silenced entirely.

    Same preconditions as the baseline warn test (architectural file staged,
    no ADR) — only the flag differs. The advisory must not appear.
    """
    repo = _make_git_repo_with_staged_architectural_file(tmp_path)
    monkeypatch.chdir(repo)
    monkeypatch.setenv(HACKATHON_FLAG, "1")
    module = _load_hook("remind_adr")

    _run_hook_capture(module, _commit_payload("git commit -m 'change agent'"))

    stderr = capsys.readouterr().err
    assert "[adr-reminder]" not in stderr, (
        "With PRAXION_HACKATHON_MODE=1, remind_adr must emit no advisory even "
        f"when an architectural file is staged without an ADR. Got: {stderr!r}"
    )


# ===========================================================================
# Independence regression — inject_process_framing with the flag unset
# ===========================================================================


def test_inject_framing_emits_context_for_non_trivial_prompt_when_flag_unset(
    tmp_path, monkeypatch
):
    """Baseline: a non-trivial prompt in a Praxion project still gets framing."""
    (tmp_path / ".ai-state").mkdir()
    monkeypatch.chdir(tmp_path)
    module = _load_hook("inject_process_framing")

    raw = _run_hook_capture(
        module,
        _prompt_payload(
            prompt=(
                "Design and implement a new payment pipeline with retry logic, "
                "idempotency keys, and dead-letter queue handling"
            ),
            cwd=str(tmp_path),
        ),
    )

    objects = _stdout_objects(raw)
    assert any("additionalContext" in obj for obj in objects), (
        "A non-trivial prompt in a Praxion project must still emit "
        f"additionalContext when the hackathon flag is unset. Got: {objects}"
    )


def test_inject_framing_silent_for_non_praxion_project_when_flag_unset(
    tmp_path, monkeypatch
):
    """Baseline: no .ai-state/ directory — the hook emits nothing."""
    monkeypatch.chdir(tmp_path)
    module = _load_hook("inject_process_framing")

    raw = _run_hook_capture(
        module,
        _prompt_payload(
            prompt="Implement the full authentication module with JWT refresh logic",
            cwd=str(tmp_path),
        ),
    )

    assert _stdout_objects(raw) == [], (
        "With no .ai-state/ directory the hook must stay silent regardless of "
        f"prompt content. Got: {raw!r}"
    )


def test_inject_framing_silent_for_trivial_prompt_when_flag_unset(
    tmp_path, monkeypatch
):
    """Baseline: a trivial prompt ('go') gets no framing — pre-hackathon behavior."""
    (tmp_path / ".ai-state").mkdir()
    monkeypatch.chdir(tmp_path)
    module = _load_hook("inject_process_framing")

    raw = _run_hook_capture(module, _prompt_payload(prompt="go", cwd=str(tmp_path)))

    assert _stdout_objects(raw) == [], (
        f"A trivial prompt must not trigger framing. Got: {raw!r}"
    )


def test_inject_framing_no_consistency_warning_when_no_hackathon_block(
    tmp_path, monkeypatch
):
    """Flag unset and CLAUDE.md has no hackathon block — no advisory leaks out.

    This is the independence guarantee: a normal Praxion project (flag unset,
    no hackathon block) sees only ordinary framing, never the hackathon
    advisories.
    """
    (tmp_path / ".ai-state").mkdir()
    (tmp_path / "CLAUDE.md").write_text("# Project\n\nNormal project, no hackathon.\n")
    monkeypatch.chdir(tmp_path)
    module = _load_hook("inject_process_framing")

    raw = _run_hook_capture(
        module,
        _prompt_payload(
            prompt=(
                "Refactor the order service to extract the pricing engine "
                "into its own cohesive module with clear boundaries"
            ),
            cwd=str(tmp_path),
        ),
    )

    objects = _stdout_objects(raw)
    advisory_text = " ".join(obj.get("additionalContext", "") for obj in objects)
    assert "Hackathon Mode" not in advisory_text, (
        "A project with no hackathon block must never see a hackathon "
        f"advisory. Got: {advisory_text!r}"
    )


# ===========================================================================
# inject_process_framing consistency check — flag OFF + block present
# ===========================================================================


def test_inject_framing_emits_consistency_warning_when_block_present_flag_off(
    tmp_path, monkeypatch
):
    """Flag OFF and `## Hackathon Mode` left in CLAUDE.md — consistency warning fires."""
    (tmp_path / ".ai-state").mkdir()
    (tmp_path / "CLAUDE.md").write_text(
        f"# Project\n\n{HACKATHON_HEADING}\n\nLeftover hackathon block.\n"
    )
    monkeypatch.chdir(tmp_path)
    module = _load_hook("inject_process_framing")

    raw = _run_hook_capture(
        module,
        _prompt_payload(
            prompt=(
                "Plan the migration of the reporting subsystem to the new "
                "event-sourced data model with backward compatibility"
            ),
            cwd=str(tmp_path),
        ),
    )

    objects = _stdout_objects(raw)
    advisory_text = " ".join(obj.get("additionalContext", "") for obj in objects)
    assert "PRAXION_HACKATHON_MODE" in advisory_text and (
        "Hackathon Mode" in advisory_text
    ), (
        "Flag OFF with a `## Hackathon Mode` block present must emit a "
        f"consistency warning naming the env var. Got: {advisory_text!r}"
    )


def test_consistency_warning_suppressed_when_hackathon_flag_on(tmp_path, monkeypatch):
    """With the flag ON the consistency check is a no-op — the block is expected."""
    (tmp_path / ".ai-state").mkdir()
    (tmp_path / "CLAUDE.md").write_text(
        f"# Project\n\n{HACKATHON_HEADING}\n\nActive hackathon block.\n"
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv(HACKATHON_FLAG, "1")
    module = _load_hook("inject_process_framing")

    raw = _run_hook_capture(
        module,
        _prompt_payload(
            prompt=(
                "Build the new search indexing pipeline with incremental "
                "updates and a fallback to full reindex on schema change"
            ),
            cwd=str(tmp_path),
        ),
    )

    objects = _stdout_objects(raw)
    advisory_text = " ".join(obj.get("additionalContext", "") for obj in objects)
    assert "PRAXION_HACKATHON_MODE is not set" not in advisory_text, (
        "With the hackathon flag ON, the consistency warning must not fire — "
        f"the block is expected. Got: {advisory_text!r}"
    )


# ===========================================================================
# inject_process_framing test-discipline reminder — flag OFF + block present
# ===========================================================================


def test_inject_framing_emits_test_discipline_reminder_when_block_present_flag_off(
    tmp_path, monkeypatch
):
    """Flag OFF and the block still present — the coverage-pass reminder fires."""
    (tmp_path / ".ai-state").mkdir()
    (tmp_path / "CLAUDE.md").write_text(
        f"# Project\n\n{HACKATHON_HEADING}\n\nLeftover hackathon block.\n"
    )
    monkeypatch.chdir(tmp_path)
    module = _load_hook("inject_process_framing")

    raw = _run_hook_capture(
        module,
        _prompt_payload(
            prompt=(
                "Implement the data export feature with CSV and JSON output, "
                "pagination, and per-organization rate limiting"
            ),
            cwd=str(tmp_path),
        ),
    )

    objects = _stdout_objects(raw)
    advisory_text = " ".join(
        obj.get("additionalContext", "") for obj in objects
    ).lower()
    assert "test discipline" in advisory_text and ("coverage" in advisory_text), (
        "Flag OFF with the hackathon block present must emit the "
        f"test-discipline / coverage-pass reminder. Got: {advisory_text!r}"
    )


# ===========================================================================
# Canonical block sync — sync_canonical_blocks.py --check exits 0
# ===========================================================================


def test_canonical_block_sync_check_passes():
    """`sync_canonical_blocks.py --check` exits 0 — all embedded blocks in sync.

    Subprocess is used here because it is a genuine system boundary: the script
    is a standalone CLI with its own argparse entry point and exit-code
    contract. This test fails until the hackathon-mode canonical block is fully
    embedded in both onboarding command files (plan Steps 4-6).
    """
    result = subprocess.run(
        [sys.executable, str(SYNC_SCRIPT), "--check"],
        capture_output=True,
        text=True,
        cwd=str(PROJECT_ROOT),
    )
    assert result.returncode == 0, (
        "sync_canonical_blocks.py --check must exit 0 (all canonical blocks "
        f"in sync). Exit {result.returncode}.\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )


# ===========================================================================
# Sentinel graduation threshold logic — >40 source files OR >150 commits
# ===========================================================================
#
# The HK01 graduation rule (agents/sentinel.md) is agent-prose, not an importable
# function. These tests encode the threshold predicate as the contract the
# sentinel's prose describes: a project in hackathon mode that exceeds *either*
# a source-file count of 40 or a commit count of 150 warrants an advisory
# finding. The predicate below mirrors that rule; the tests exercise its
# boundaries with real `tmp_path` filesystem state and real git history.


# Thresholds as stated in the sentinel HK01 check rule.
_SOURCE_FILE_THRESHOLD = 40
_COMMIT_THRESHOLD = 150


def _graduation_advisory_warranted(
    *, hackathon_on: bool, source_file_count: int, commit_count: int
) -> bool:
    """Mirror of the sentinel HK01 graduation rule.

    Advisory is warranted only when hackathon mode is active AND the project
    exceeds either threshold. Inert on non-hackathon projects.
    """
    if not hackathon_on:
        return False
    return (
        source_file_count > _SOURCE_FILE_THRESHOLD or commit_count > _COMMIT_THRESHOLD
    )


def _count_source_py_files(root: Path) -> int:
    """Count non-test Python source files under root, mirroring the HK01 find.

    HK01's command: find . -name "*.py" -not -path "*/test*" -not -path "*/.git/*"
    """
    count = 0
    for path in root.rglob("*.py"):
        rel_parts = path.relative_to(root).parts
        if any(part.startswith("test") for part in rel_parts):
            continue
        if ".git" in rel_parts:
            continue
        count += 1
    return count


def test_graduation_advisory_not_warranted_when_hackathon_off():
    """The graduation advisory is inert on a non-hackathon project."""
    assert not _graduation_advisory_warranted(
        hackathon_on=False, source_file_count=999, commit_count=9999
    ), "With hackathon mode off, no graduation advisory is ever warranted."


def test_graduation_advisory_not_warranted_below_both_thresholds():
    """Hackathon on but small project (<=40 files AND <=150 commits) — no advisory."""
    assert not _graduation_advisory_warranted(
        hackathon_on=True, source_file_count=40, commit_count=150
    ), "At exactly the thresholds (not exceeding), no advisory is warranted."


def test_graduation_advisory_warranted_when_source_files_exceed_threshold():
    """Hackathon on and >40 source files — advisory warranted on the file axis alone."""
    assert _graduation_advisory_warranted(
        hackathon_on=True, source_file_count=41, commit_count=10
    ), "41 source files (>40) must warrant the graduation advisory."


def test_graduation_advisory_warranted_when_commits_exceed_threshold():
    """Hackathon on and >150 commits — advisory warranted on the commit axis alone."""
    assert _graduation_advisory_warranted(
        hackathon_on=True, source_file_count=5, commit_count=151
    ), "151 commits (>150) must warrant the graduation advisory."


def test_source_file_count_excludes_test_files(tmp_path):
    """The source-file count counts non-test .py files and skips test paths."""
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "module_a.py").write_text("x = 1\n")
    (tmp_path / "pkg" / "module_b.py").write_text("y = 2\n")
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_module_a.py").write_text("def test_x(): pass\n")
    (tmp_path / "pkg" / "test_inline.py").write_text("def test_y(): pass\n")

    count = _count_source_py_files(tmp_path)

    assert count == 2, (
        "Only the two non-test source modules should be counted; files under "
        f"a test path and test_*.py files are excluded. Got {count}."
    )


def test_small_hackathon_project_below_thresholds_warrants_no_advisory(tmp_path):
    """End-to-end: a small real hackathon project on disk warrants no advisory."""
    (tmp_path / "main.py").write_text("print('hi')\n")
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=tmp_path,
        check=True,
    )
    subprocess.run(["git", "config", "user.name", "Test"], cwd=tmp_path, check=True)
    subprocess.run(["git", "add", "main.py"], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "initial"], cwd=tmp_path, check=True)

    source_count = _count_source_py_files(tmp_path)
    commit_count = int(
        subprocess.run(
            ["git", "rev-list", "--count", "HEAD"],
            cwd=tmp_path,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
    )

    assert source_count == 1 and commit_count == 1
    assert not _graduation_advisory_warranted(
        hackathon_on=True,
        source_file_count=source_count,
        commit_count=commit_count,
    ), "A 1-file, 1-commit hackathon project is well below both thresholds."
