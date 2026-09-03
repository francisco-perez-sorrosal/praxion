#!/usr/bin/env python3
"""Reconcile the instantiated AaC surfaces of a managed project.

/onboard-project Phase 8b instantiates two templates into a project tree —
`.github/workflows/architecture.yml` and a Block D fragment appended to
`.git/hooks/pre-commit`. Neither is re-rendered by an onboarding re-run (both
sub-step predicates are file-existence guards), so a project onboarded before
a plugin change carries a stale copy until this reconciler runs. Two drift
classes are handled:

1. **Namespace token drift** (both surfaces): the plugin namespace is embedded
   in one line of static text per file — the workflow's agent-load prompt and
   Block D's skip-gracefully notice. Detected by comparing each installed
   file's token against the live template's (never a hardcoded name, so this
   survives future renames) and fixed by patching only that one line, never a
   full re-render — the workflow's project-specific template substitutions and
   any hand edits survive untouched.

2. **Broken Block D resolution** (structural repair): every Block D installed
   from the pre-fix template resolves ``PLUGIN_ROOT`` by iterating the top
   level of ``installed_plugins.json`` and reading a ``path`` key — the real
   registry is ``{"version": N, "plugins": {key: [{"installPath": ...}]}}``,
   so resolution always came back empty and the gate silently skipped. When
   the installed Block D region carries that broken shape, the whole region is
   replaced with the live template (safe: the fragment embeds no
   project-specific substitutions). The region is located structurally — the
   ``# Block D`` banner down to the column-0 ``fi`` closing the outer
   ``if [ -n "$STAGED_AAC" ]`` — so both historical template variants match.

A Block D that differs from the template without the broken marker and with a
current namespace (a hand edit, or a future template this reconciler predates)
is reported and left untouched.

Invoked by ``scripts/upgrade_project_pins.sh`` (the ``[aac]`` section) and
runnable standalone. Stdlib-only; the only subprocess is ``git add``.

Usage:
  reconcile_aac_surfaces.py --plugin-root PATH [--repo-root PATH]
                            [--mode check|dry-run|apply] [--no-stage]

Exit codes: 0 = reconciled / no drift (also dry-run and apply);
1 = drift found under --mode check; 2 = precondition or runtime error.
The final stdout line is always ``aac-changes: N`` so the wrapping script can
fold N into its own change count.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

from _git_runner import git_output, run_git

WORKFLOW_REL = ".github/workflows/architecture.yml"
WORKFLOW_TEMPLATE_REL = "claude/aac-templates/architecture.yml.tmpl"
HOOK_REL = ".git/hooks/pre-commit"
BLOCK_D_TEMPLATE_REL = "claude/aac-templates/precommit-block-d.sh.frag"

WORKFLOW_ANCHOR = re.compile(r"Load the (\S+):architect-validator agent")
NOTICE_ANCHOR = re.compile(r"info: (\S+) plugin not found in installed_plugins\.json")

# The two lines unique to the broken pre-fix resolution snippet; either one
# identifies a Block D region that must be structurally repaired.
BROKEN_RESOLUTION_MARKERS = ("data.items()", "entry.get('path'")

BLOCK_D_HEADER = re.compile(r"^# Block D: AaC golden-rule gate\s*$")
BLOCK_D_BANNER = re.compile(r"^# -{10,}\s*$")
BLOCK_D_OUTER_IF = re.compile(r'^if \[ -n "\$STAGED_AAC" \]')
BLOCK_D_OUTER_FI = re.compile(r"^fi\s*$")


def find_block_d_region(hook_lines: list[str]) -> tuple[int, int] | None:
    """Return (start, end) inclusive line indexes of the Block D region.

    Start is the banner line preceding the ``# Block D`` header when present,
    else the header itself; end is the first column-0 ``fi`` after the outer
    ``if [ -n "$STAGED_AAC" ]``. Returns None when the structure is absent.
    """
    header_idx = next((i for i, line in enumerate(hook_lines) if BLOCK_D_HEADER.match(line)), None)
    if header_idx is None:
        return None
    start = header_idx
    if header_idx > 0 and BLOCK_D_BANNER.match(hook_lines[header_idx - 1]):
        start = header_idx - 1
    outer_if_idx = next(
        (
            i
            for i in range(header_idx + 1, len(hook_lines))
            if BLOCK_D_OUTER_IF.match(hook_lines[i])
        ),
        None,
    )
    if outer_if_idx is None:
        return None
    end = next(
        (
            i
            for i in range(outer_if_idx + 1, len(hook_lines))
            if BLOCK_D_OUTER_FI.match(hook_lines[i])
        ),
        None,
    )
    if end is None:
        return None
    return start, end


class Reconciler:
    def __init__(self, plugin_root: Path, repo_root: Path, mode: str, stage: bool):
        self.plugin_root = plugin_root
        self.repo_root = repo_root
        self.mode = mode
        self.stage = stage
        self.changes = 0

    def say(self, msg: str) -> None:
        print(msg)

    def mutating(self) -> bool:
        return self.mode == "apply"

    def _template(self, rel: str) -> Path | None:
        """Prefer the live plugin install; fall back to this script's checkout."""
        for base in (self.plugin_root, Path(__file__).resolve().parent.parent):
            candidate = base / rel
            if candidate.is_file():
                return candidate
        return None

    def _git_add(self, path: Path) -> None:
        """Stage `path` through the shared runner, which scrubs git's
        repository-scoping environment.

        This reconciler is invoked from inside the finalize hook chain, where
        git exports `GIT_INDEX_FILE`/`GIT_DIR` *relative* to the firing hook's
        repository. A plain `subprocess.run(["git", "add", ...])` inherits
        them, so the add lands in whatever index those resolve to rather than
        `self.repo_root`'s -- and against a repository whose `.git` is a
        worktree pointer file it fails outright.
        """
        if not self.stage:
            return
        result = run_git(self.repo_root, "add", "--", str(path))
        if result.returncode != 0:
            # Same exception the previous `check=True` raised, so callers that
            # already handle a failed stage keep working unchanged.
            raise subprocess.CalledProcessError(
                result.returncode, result.args, result.stdout, result.stderr
            )
        self.say(f"staged: {path.relative_to(self.repo_root)}")

    # -- surface: architecture.yml namespace token ---------------------------

    def reconcile_workflow(self) -> None:
        installed = self.repo_root / WORKFLOW_REL
        if not installed.is_file():
            self.say("architecture.yml: not installed — nothing to reconcile")
            return
        template = self._template(WORKFLOW_TEMPLATE_REL)
        if template is None:
            self.say("architecture.yml: shipped template not found — skipping")
            return
        current = WORKFLOW_ANCHOR.search(template.read_text())
        installed_text = installed.read_text()
        found = WORKFLOW_ANCHOR.search(installed_text)
        if not current or not found:
            self.say("architecture.yml: anchor line not found — skipping (manual review)")
            return
        if current.group(1) == found.group(1):
            self.say(f"architecture.yml: current (namespace={current.group(1)})")
            return
        self.changes += 1
        old_token, new_token = found.group(1), current.group(1)
        if self.mode == "check":
            self.say(
                f"architecture.yml: STALE — names '{old_token}', template now says '{new_token}'"
            )
        elif self.mode == "dry-run":
            self.say(f"architecture.yml: would re-point namespace '{old_token}' → '{new_token}'")
        else:
            installed.write_text(
                installed_text.replace(
                    f"Load the {old_token}:architect-validator agent",
                    f"Load the {new_token}:architect-validator agent",
                )
            )
            self.say(f"architecture.yml: fixed — re-pointed to '{new_token}'")
            self._git_add(installed)

    # -- surface: pre-commit Block D -----------------------------------------

    def reconcile_block_d(self) -> None:
        hook = self.repo_root / HOOK_REL
        if not hook.is_file():
            self.say("pre-commit Block D: no pre-commit hook — nothing to reconcile")
            return
        hook_text = hook.read_text()
        if "check_aac_golden_rule" not in hook_text and "Block D" not in hook_text:
            self.say("pre-commit Block D: not installed — nothing to reconcile")
            return
        template = self._template(BLOCK_D_TEMPLATE_REL)
        if template is None:
            self.say("pre-commit Block D: shipped template not found — skipping")
            return
        template_text = template.read_text()

        hook_lines = hook_text.splitlines(keepends=True)
        region = find_block_d_region(hook_lines)
        if region is None:
            self.say(
                "pre-commit Block D: marker present but region structure not found"
                " — skipping (manual review)"
            )
            return
        start, end = region
        region_text = "".join(hook_lines[start : end + 1])

        if region_text.rstrip("\n") == template_text.rstrip("\n"):
            self.say("pre-commit Block D: current")
            return

        if any(marker in region_text for marker in BROKEN_RESOLUTION_MARKERS):
            self._replace_region(hook, hook_lines, start, end, template_text)
            return

        current = NOTICE_ANCHOR.search(template_text)
        found = NOTICE_ANCHOR.search(region_text)
        if current and found and current.group(1) != found.group(1):
            self._patch_notice_line(hook, hook_text, found.group(1), current.group(1))
            return

        self.say(
            "pre-commit Block D: diverges from the shipped template without the"
            " known-broken shape (hand-edited?) — left untouched"
        )

    def _replace_region(
        self, hook: Path, hook_lines: list[str], start: int, end: int, template_text: str
    ) -> None:
        self.changes += 1
        if self.mode == "check":
            self.say(
                "pre-commit Block D: BROKEN — carries the pre-fix PLUGIN_ROOT"
                " resolution (gate has been silently skipping); repair available"
            )
        elif self.mode == "dry-run":
            self.say(
                "pre-commit Block D: would replace the whole block with the fixed"
                " shipped template (broken PLUGIN_ROOT resolution)"
            )
        else:
            if not template_text.endswith("\n"):
                template_text += "\n"
            new_lines = hook_lines[:start] + [template_text] + hook_lines[end + 1 :]
            hook.write_text("".join(new_lines))
            self.say(
                "pre-commit Block D: repaired — broken PLUGIN_ROOT resolution"
                " replaced with the fixed shipped template"
            )

    def _patch_notice_line(
        self, hook: Path, hook_text: str, old_token: str, new_token: str
    ) -> None:
        self.changes += 1
        old_line = f"info: {old_token} plugin not found in installed_plugins.json"
        new_line = f"info: {new_token} plugin not found in installed_plugins.json"
        if self.mode == "check":
            self.say(
                f"pre-commit Block D: STALE — names '{old_token}', template now says '{new_token}'"
            )
        elif self.mode == "dry-run":
            self.say(f"pre-commit Block D: would replace:\n  - {old_line}\n  + {new_line}")
        else:
            hook.write_text(hook_text.replace(old_line, new_line))
            self.say(f"pre-commit Block D: fixed — re-pointed to '{new_token}'")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plugin-root", required=True, type=Path)
    parser.add_argument("--repo-root", type=Path, default=None)
    parser.add_argument("--mode", choices=("check", "dry-run", "apply"), default="apply")
    parser.add_argument("--no-stage", action="store_true")
    parser.add_argument(
        "--surface",
        choices=("workflow", "block-d", "all"),
        default="all",
        help=(
            "restrict to one surface; the finalize-chain backstop passes"
            " block-d so a git hook never touches tracked files"
        ),
    )
    args = parser.parse_args(argv)

    repo_root = args.repo_root
    if repo_root is None:
        toplevel = git_output(Path.cwd(), "rev-parse", "--show-toplevel")
        if toplevel is None:
            print("reconcile-aac: not inside a git repository", file=sys.stderr)
            return 2
        repo_root = Path(toplevel)
    repo_root = repo_root.resolve()

    reconciler = Reconciler(
        plugin_root=args.plugin_root,
        repo_root=repo_root,
        mode=args.mode,
        stage=not args.no_stage,
    )
    if args.surface in ("workflow", "all"):
        reconciler.reconcile_workflow()
    if args.surface in ("block-d", "all"):
        reconciler.reconcile_block_d()
    print(f"aac-changes: {reconciler.changes}")
    return 1 if (args.mode == "check" and reconciler.changes > 0) else 0


if __name__ == "__main__":
    sys.exit(main())
