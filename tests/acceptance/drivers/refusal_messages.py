"""Driver for the commands whose stop or refusal text tells the reader what to do.

Each surface is reached only from outside, as its real caller reaches it:

- the test-scope resolver, run in a throwaway repository with no change-set argument,
  its stdout, stderr and exit status kept apart;
- the footprint check, run at `--stage verify` over a scratch repository whose task
  directory holds a spec with criteria and a measurement log;
- the session commit gate, run as the harness runs a PreToolUse hook: the Bash payload
  on stdin, from inside a scratch repository with something staged;
- the task-brief reminder, from the main checkout of a repository whose pipeline
  worktree holds the brief.

What a session reads from a refused PreToolUse call is the harness's rule, not the
hook's: on exit 2 the hook's stderr; on exit 0 a JSON `permissionDecision: deny`
carries its `permissionDecisionReason` (Claude Code hooks documentation, read
2026-11-12). Stdout at exit 2 never reaches the model.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
RESOLVER = REPO_ROOT / "scripts" / "resolve_test_scope.py"
FOOTPRINT_CHECK = REPO_ROOT / "scripts" / "check_footprint_criteria.py"
COMMIT_GATE = REPO_ROOT / "hooks" / "commit_gate.sh"
ID_CITATION_CHECK = REPO_ROOT / "scripts" / "check_id_citation_discipline.py"


@dataclass(frozen=True)
class Run:
    exit_code: int
    stdout: str
    stderr: str


def _clean_env(**extra: str) -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if not k.startswith(("GIT_", "CLAUDE", "PRAXION_"))}
    env.pop("PYTEST_ADDOPTS", None)
    env.update(extra)
    return env


def _run(argv: list[str], cwd: Path, *, stdin: str | None = None, timeout: int = 180) -> Run:
    result = subprocess.run(
        argv,
        cwd=cwd,
        input=stdin,
        capture_output=True,
        text=True,
        env=_clean_env(),
        timeout=timeout,
    )
    return Run(result.returncode, result.stdout, result.stderr)


def git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
        env=_clean_env(),
        timeout=60,
    ).stdout.strip()


def scratch_repo(path: Path, files: dict[str, str]) -> Path:
    """A git repository whose one commit holds `files`."""
    path.mkdir(parents=True)
    git(path, "init", "-q")
    for key, value in (
        ("user.name", "Acceptance"),
        ("user.email", "acceptance@example.invalid"),
        ("commit.gpgsign", "false"),
        ("core.hooksPath", "/dev/null"),
    ):
        git(path, "config", key, value)
    for rel, text in files.items():
        target = path / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
    git(path, "add", "-A")
    git(path, "commit", "-qm", "base")
    return path


# -- The test-scope resolver ---------------------------------------------------------------

WIDGET_PROJECT = {
    "pyproject.toml": '[project]\nname = "widget"\nversion = "0"\n',
    "src/widget.py": "def value():\n    return 1\n",
    "tests/test_widget.py": "from src.widget import value\n\n\ndef test_value():\n    assert value() == 1\n",
}


def resolve_working_tree(repo: Path, *, as_json: bool) -> Run:
    """The resolver with no change-set argument: it reads the working-tree diff."""
    flags = ["--json"] if as_json else []
    return _run([sys.executable, str(RESOLVER), "--repo-root", str(repo), *flags], repo)


# -- The footprint check ---------------------------------------------------------------------

FP_SLUG = "footprint-task"


def footprint_plan(criterion_command: str) -> str:
    return (
        "# Footprint-moving change\n\n## Acceptance Criteria\n\n- [ ] The change behaves as described\n\n"
        "### Footprint Criteria\n\n"
        "| Id | Footprint | Metric | Comparator | Limit | Against | Command |\n"
        "|---|---|---|---|---|---|---|\n"
        f"| FC-01 | prompt-size | longest prompt, in lines | at or below | 400 lines | "
        f"reference: an absolute limit | `{criterion_command}` |\n\n"
        "## Behavioral Specification\n\n"
        "### REQ-01\n\nThe change behaves as described.\n"  # id-citation-discipline:ignore
    )


def verify_footprints(
    workspace: Path, *, criterion_command: str, logged_command: str
) -> list[dict]:
    """`--stage verify --json` findings for one criterion whose final row logged `logged_command`."""
    repo = scratch_repo(workspace / "repo", {"README.md": "# change\n"})
    head = git(repo, "rev-parse", "--short=8", "HEAD")
    task = repo / ".ai-work" / FP_SLUG
    task.mkdir(parents=True)
    (task / "SYSTEMS_PLAN.md").write_text(footprint_plan(criterion_command), encoding="utf-8")
    (task / "MEASUREMENTS.md").write_text(
        "| Criterion | Phase | Value | Reading | Head | Taken | Command |\n"
        "|---|---|---|---|---|---|---|\n"
        f"| FC-01 | final | 398 lines | measured | {head} | 2026-11-12T09:16Z | `{logged_command}` |\n",
        encoding="utf-8",
    )
    run = _run(
        [
            sys.executable,
            str(FOOTPRINT_CHECK),
            FP_SLUG,
            "--stage",
            "verify",
            "--base-ref",
            "HEAD",
            "--repo-root",
            str(repo),
            "--json",
        ],
        repo,
    )
    try:
        return json.loads(run.stdout)["findings"]
    except (json.JSONDecodeError, KeyError) as exc:
        raise AssertionError(
            f"the footprint check printed no findings (exit {run.exit_code}):\n{run.stdout}{run.stderr}"
        ) from exc


def wrong_command_findings(findings: list[dict]) -> list[dict]:
    return [f for f in findings if f.get("reason") == "wrong-command"]


# -- The session commit gate -----------------------------------------------------------------

# A pipeline-local criterion id, joined at run time so this source never carries its literal shape.
CITED_ID = "-".join(("AC", "14"))
AC_VIOLATION = f"def value():\n    # see {CITED_ID} for the acceptance criterion\n    return 1\n"
CLEAN_CODE = "def value():\n    return 1\n"
OTHER_CHECK_FINDING = "decision record misplaced: .ai-state/decisions/record.md"


def staged_repo(workspace: Path, rel: str, text: str) -> Path:
    repo = scratch_repo(workspace / "repo", {"README.md": "# widget\n"})
    target = repo / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")
    git(repo, "add", rel)
    return repo


def refusing_check(workspace: Path) -> Path:
    """A stand-in for another check run through the gate: it reports one finding and exits 1."""
    script = workspace / "another_check.py"
    script.write_text(
        f"import sys\nsys.stdin.read()\nprint({OTHER_CHECK_FINDING!r}, file=sys.stderr)\nsys.exit(1)\n",
        encoding="utf-8",
    )
    return script


def commit_payload(repo: Path, command: str = "git commit -m 'add widget'") -> str:
    return json.dumps(
        {
            "hook_event_name": "PreToolUse",
            "tool_name": "Bash",
            "tool_input": {"command": command},
            "cwd": str(repo),
        }
    )


def run_commit_gate(repo: Path, check: Path) -> Run:
    """`commit_gate.sh --blocking <check>` as hooks.json registers it, for a commit call."""
    return _run([str(COMMIT_GATE), "--blocking", str(check)], repo, stdin=commit_payload(repo))


def refusal_the_session_reads(run: Run) -> str | None:
    """The refusal text that reaches the session, or None when the call is not refused."""
    if run.exit_code == 2:
        return run.stderr
    if run.exit_code == 0 and run.stdout.strip():
        try:
            doc = json.loads(run.stdout)
        except json.JSONDecodeError:
            return None
        output = doc.get("hookSpecificOutput", {}) if isinstance(doc, dict) else {}
        if output.get("permissionDecision") == "deny":
            return output.get("permissionDecisionReason", "")
        if doc.get("decision") == "block":
            return doc.get("reason", "")
    return None


def run_id_citation_by_hand(repo: Path, rel: str) -> Run:
    return _run(
        [sys.executable, str(ID_CITATION_CHECK), "--files", rel, "--repo-root", str(repo)], repo
    )


NO_COMMAND_RAN = r"no command|none of (its|the|that call's) commands|did(n't| not) run|nothing .{0,30}ran|not run"
JUDGED_BEFORE_THE_CALL = r"before (the|this|that) call|as (they|it) stood"
STAGE_THEN_COMMIT_SEPARATELY = (
    r"stage.{0,120}(separate|another|second|next|its own|own) (tool )?call"
)


def says(text: str, pattern: str) -> bool:
    return re.search(pattern, text, re.IGNORECASE | re.DOTALL) is not None


# -- The task-brief reminder from the main checkout --------------------------------------------


def main_with_briefed_worktree(workspace: Path, slug: str) -> tuple[Path, Path]:
    """A main checkout and a linked pipeline worktree; only the worktree holds the brief."""
    main = scratch_repo(
        workspace / "main", {"README.md": "# project\n", ".gitignore": ".ai-work/\n"}
    )
    worktree = workspace / "worktrees" / "pipeline"
    git(main, "worktree", "add", "-q", "-b", "pipeline", str(worktree))
    brief = worktree / ".ai-work" / slug / "TASK_BRIEF.md"
    brief.parent.mkdir(parents=True)
    brief.write_text("# Task Brief\n", encoding="utf-8")
    return main, worktree
