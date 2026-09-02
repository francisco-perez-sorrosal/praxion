#!/usr/bin/env python3
"""Observe, then compose: install/heal/status/uninstall Praxion's git hooks.

Praxion previously wrote straight into ``.git/hooks``, backing up (and
displacing) whatever it found there and never looking at ``core.hooksPath``
at all. That is silently inert in any repo managed by husky, lefthook, or the
``pre-commit`` framework -- most of which set ``core.hooksPath`` to a
directory Praxion never inspected, or occupy ``.git/hooks/pre-commit``
directly. This script is the single writer of both surfaces: it *observes*
the repository's hook configuration (``scripts/_hook_chain_state`` sum
types below) and then installs the shape that *composes* with it rather than
displacing it. See ``dec-draft-c66a19a6``.

Data model (DS-4, ``SYSTEMS_PLAN.md § Data Structures``):

    HooksPathState = Unset | PraxionWrapper{delegate} | Foreign{dir_raw, dir_abs}
                    | Unresolvable{raw, reason}
    HookSlotState  = Absent | PraxionSymlink | PraxionWrapperFile
                    | ForeignOccupied{path}
    DelegateRef    = {raw, is_relative}   -- stored raw; resolved per-worktree
                                             at hook-run time (REQ-09)

Observation -> action table (five branches, ``install_or_heal``):

    Unset + Absent           -> today's symlink (post-*) / inline script (pre-commit)
    Unset + ForeignOccupied  -> preserve occupant at <name>.pre-praxion, install a
                                 wrapper FILE in .git/hooks/<name>
    Foreign(d)                -> wrapper directory in the git COMMON dir, delegate
                                 recorded, core.hooksPath re-pointed
    PraxionWrapper            -> refresh wrapper bodies only, no config write
    Unresolvable               -> refuse, warn once, change nothing

The non-ping-pong invariant (``delegate.resolve() != wrapper_dir``) is
enforced at every site that would write a delegate or re-point
``core.hooksPath``; a violation refuses the write rather than looping.

CLI: ``--install | --heal | --status | --uninstall`` (exactly one),
``--repo-root``, ``--plugin-root``, ``--json``. Exit codes: 0 ok, 1
actionable (``--status`` found a slot Praxion cannot fire), 2 usage
(argparse), 3 refused (``Unresolvable`` / non-ping-pong), 4 environment (not
a git repository).
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from _git_runner import git_output, run_git  # noqa: E402
from _repo_root import resolve_repo_root  # noqa: E402

WRAPPER_MARKER = "# praxion-hook-wrapper v1"
# The marker is scanned within the first few lines rather than required as
# the literal first byte: line 1 must stay `#!/usr/bin/env bash` so the file
# is directly executable by git without an interpreter wrapper.
MARKER_SCAN_LINES = 5
WRAPPER_DIRNAME = "praxion-hooks"
DELEGATE_RECORD_FILENAME = ".praxion-delegate"
FINALIZE_HOOK_NAMES = ("post-merge", "post-commit", "post-checkout")
ALL_HOOK_NAMES = ("pre-commit", *FINALIZE_HOOK_NAMES)
PRECOMMIT_MARKER = "Praxion commit gate (installed by /onboard-project)"
FINALIZE_DISPATCHER = "git-finalize-hook.sh"
WRAPPER_TEMPLATE_PATH = SCRIPT_DIR / "assets" / "praxion-hook-wrapper.sh.tmpl"
PRECOMMIT_TEMPLATE_PATH = SCRIPT_DIR / "assets" / "praxion-precommit-hook.sh.tmpl"

EXIT_OK = 0
EXIT_ACTIONABLE = 1
EXIT_REFUSED = 3
EXIT_ENVIRONMENT = 4


# ---- DS-4 sum types ---------------------------------------------------------


@dataclass(frozen=True)
class DelegateRef:
    raw: str
    is_relative: bool


@dataclass(frozen=True)
class Unset:
    """``core.hooksPath`` is not set (or unreadable-as-empty)."""


@dataclass(frozen=True)
class PraxionWrapper:
    """``core.hooksPath`` already names Praxion's own wrapper directory."""

    delegate: DelegateRef | None


@dataclass(frozen=True)
class Foreign:
    """``core.hooksPath`` names a directory Praxion does not own."""

    dir_raw: str
    dir_abs: Path


@dataclass(frozen=True)
class Unresolvable:
    """``core.hooksPath`` is set but cannot be read or resolved to a directory."""

    raw: str
    reason: str


HooksPathState = Unset | PraxionWrapper | Foreign | Unresolvable


@dataclass(frozen=True)
class Absent:
    pass


@dataclass(frozen=True)
class PraxionSymlink:
    """A plain, non-chaining Praxion install: symlink or inline script."""


@dataclass(frozen=True)
class PraxionWrapperFile:
    """A chaining wrapper file, identified by ``WRAPPER_MARKER``."""


@dataclass(frozen=True)
class ForeignOccupied:
    path: Path


HookSlotState = Absent | PraxionSymlink | PraxionWrapperFile | ForeignOccupied


@dataclass(frozen=True)
class InstallResult:
    changed: bool
    messages: list[str]
    refused: bool = False
    reason: str | None = None


# ---- Observation (pure, read-only) ------------------------------------------


def git_common_dir(repo_root: Path) -> Path | None:
    """Return the git COMMON directory -- shared across all linked worktrees.

    ``core.hooksPath`` is repo-local config shared by every worktree, so the
    wrapper directory must live here, never in a linked worktree's own
    ``.git`` file (DS-4).
    """
    out = git_output(repo_root, "rev-parse", "--path-format=absolute", "--git-common-dir")
    return Path(out).resolve() if out else None


def wrapper_dir_path(repo_root: Path) -> Path | None:
    common_dir = git_common_dir(repo_root)
    return None if common_dir is None else common_dir / WRAPPER_DIRNAME


def read_recorded_delegate(wrapper_dir: Path) -> DelegateRef | None:
    """Read the delegate Praxion recorded when it adopted a ``Foreign`` hooksPath.

    ``core.hooksPath`` itself is overwritten to point at the wrapper the
    moment Praxion adopts it, so the original observed value would otherwise
    be unrecoverable -- this file is that record.
    """
    record = wrapper_dir / DELEGATE_RECORD_FILENAME
    if not record.is_file():
        return None
    raw = record.read_text(encoding="utf-8").strip()
    if not raw:
        return None
    return DelegateRef(raw=raw, is_relative=not Path(raw).is_absolute())


def write_recorded_delegate(wrapper_dir: Path, raw: str) -> None:
    (wrapper_dir / DELEGATE_RECORD_FILENAME).write_text(raw + "\n", encoding="utf-8")


def observe_hooks_path(repo_root: Path) -> HooksPathState:
    """Read and classify ``core.hooksPath``. Pure and read-only -- no writes."""
    result = run_git(repo_root, "config", "--get", "core.hooksPath")
    if result.returncode != 0:
        return Unset()
    raw = result.stdout.strip()
    if not raw:
        return Unset()

    candidate = Path(raw)
    if not candidate.is_absolute():
        candidate = repo_root / raw
    try:
        resolved = candidate.resolve()
    except OSError:
        return Unresolvable(raw=raw, reason="cannot-resolve-path")
    if not resolved.is_dir():
        return Unresolvable(raw=raw, reason="not-a-directory")

    wrapper_dir = wrapper_dir_path(repo_root)
    if wrapper_dir is not None and resolved == _safe_resolve(wrapper_dir):
        return PraxionWrapper(delegate=read_recorded_delegate(wrapper_dir))
    return Foreign(dir_raw=raw, dir_abs=resolved)


def _safe_resolve(path: Path) -> Path:
    try:
        return path.resolve()
    except OSError:
        return path


def classify_hook_slot(hooks_dir: Path, name: str) -> HookSlotState:
    """Classify one ``.git/hooks/<name>`` slot. Pure and read-only."""
    slot = hooks_dir / name
    if slot.is_symlink():
        if not slot.exists():
            # Dangling symlink: neither trusted as ours nor silently ignored.
            return ForeignOccupied(path=slot)
        target = Path(os.readlink(slot))
        if target.name == FINALIZE_DISPATCHER:
            return PraxionSymlink()
        return ForeignOccupied(path=slot)
    if not slot.exists():
        return Absent()
    if not slot.is_file():
        return ForeignOccupied(path=slot)
    if _has_marker(slot, WRAPPER_MARKER):
        return PraxionWrapperFile()
    if _has_marker(slot, PRECOMMIT_MARKER):
        return PraxionSymlink()
    return ForeignOccupied(path=slot)


def _has_marker(path: Path, marker: str) -> bool:
    try:
        with path.open(encoding="utf-8", errors="replace") as fh:
            head = [next(fh, "") for _ in range(MARKER_SCAN_LINES)]
    except OSError:
        return False
    return any(marker in line for line in head)


# ---- Wrapper rendering (Step 2) ---------------------------------------------

# The two exit-code policies are two distinct, statically-chosen bash
# snippets substituted at render time -- never a runtime `if $HOOK_CLASS`
# branch. A future edit to one class's handling cannot silently touch the
# other because there is no shared code path to edit (DS-4).
_BLOCK_EXIT_HANDLING = (
    '    if [ "$_DELEGATE_STATUS" -ne 0 ]; then\n        exit "$_DELEGATE_STATUS"\n    fi\n'
)
_CONTINUE_EXIT_HANDLING = (
    '    if [ "$_DELEGATE_STATUS" -ne 0 ]; then\n'
    '        echo "praxion-hook-wrapper ({{HOOK_NAME}}): delegate exited'
    ' $_DELEGATE_STATUS (reported, chain continues)" >&2\n'
    "    fi\n"
)


def render_wrapper(
    *, hook_name: str, delegate_raw: str, delegate_mode: str, plugin_root: Path
) -> str:
    """Render one hook's wrapper body from the shared template.

    ``delegate_mode`` is ``"dir"`` (the delegate is a directory; the wrapper
    appends ``/<hook_name>``) or ``"file"`` (the delegate is already the
    exact executable -- the ``<name>.pre-praxion`` backup case).
    """
    template = WRAPPER_TEMPLATE_PATH.read_text(encoding="utf-8")
    if hook_name == "pre-commit":
        exit_handling = _BLOCK_EXIT_HANDLING
        praxion_step = f'bash "{plugin_root}/scripts/assets/praxion-precommit-hook.sh.tmpl"\n'
    else:
        exit_handling = _CONTINUE_EXIT_HANDLING.replace("{{HOOK_NAME}}", hook_name)
        # git-finalize-hook.sh dispatches on `basename "$0"`. A subprocess
        # exec (even `exec -a`) loses that identity the moment the target
        # re-execs through its own `#!/usr/bin/env bash` shebang -- the
        # kernel's shebang handling discards the caller-supplied argv[0].
        # Sourcing runs the dispatcher IN this process instead, so `$0`
        # stays exactly what git invoked this wrapper file as (which
        # already equals `{hook_name}`, since that is this file's own
        # name). The subshell isolates the dispatcher's own variables/exit
        # from the wrapper without touching `$0` (subshells inherit it).
        praxion_step = (
            f'if ( . "{plugin_root}/scripts/{FINALIZE_DISPATCHER}" "$@" ); then\n'
            "    :\n"
            "else\n"
            f'    echo "praxion-hook-wrapper ({hook_name}): Praxion finalize step reported'
            ' a failure (non-blocking)" >&2\n'
            "fi\n"
            "exit 0\n"
        )
    return (
        template.replace("{{HOOK_NAME}}", hook_name)
        .replace("{{DELEGATE_RAW}}", delegate_raw)
        .replace("{{DELEGATE_MODE}}", delegate_mode)
        .replace("{{DELEGATE_EXIT_HANDLING}}", exit_handling)
        .replace("{{PRAXION_STEP}}", praxion_step)
    )


def _write_wrapper_bodies(
    wrapper_dir: Path, delegate_raw: str, delegate_mode: str, plugin_root: Path
) -> bool:
    """Render + write every hook's wrapper body; return True iff any byte changed.

    Idempotency (REQ-11 / P0-6): a target whose rendered content already
    matches is never rewritten, so a second call performs zero writes.
    """
    wrapper_dir.mkdir(parents=True, exist_ok=True)
    changed = False
    for name in ALL_HOOK_NAMES:
        rendered = render_wrapper(
            hook_name=name,
            delegate_raw=delegate_raw,
            delegate_mode=delegate_mode,
            plugin_root=plugin_root,
        )
        target = wrapper_dir / name
        if target.is_file() and target.read_text(encoding="utf-8") == rendered:
            continue
        target.write_text(rendered, encoding="utf-8")
        target.chmod(0o755)
        changed = True
    return changed


# ---- Plain (non-chaining) install -------------------------------------------


def _install_plain_slot(hooks_dir: Path, name: str, plugin_root: Path) -> bool:
    """Install (or idempotently refresh) one plain, non-chaining slot.

    Returns True iff a write occurred. For ``pre-commit`` this doubles as the
    content-aware top-up mechanism the onboarding skill previously carried
    as a bespoke predicate table: an already-installed hook whose body has
    drifted from the current shipped template is rewritten byte-for-byte,
    and one comparison keeps a current hook from ever being touched.
    """
    target = hooks_dir / name
    if name == "pre-commit":
        rendered = PRECOMMIT_TEMPLATE_PATH.read_text(encoding="utf-8")
        if target.is_file() and target.read_text(encoding="utf-8") == rendered:
            return False
        target.write_text(rendered, encoding="utf-8")
        target.chmod(0o755)
        return True
    dispatcher = plugin_root / "scripts" / FINALIZE_DISPATCHER
    if target.is_symlink() and Path(os.readlink(target)) == dispatcher:
        return False
    if target.exists() or target.is_symlink():
        target.unlink()
    target.symlink_to(dispatcher)
    return True


def _install_wrapper_file(hooks_dir: Path, name: str, occupant: Path, plugin_root: Path) -> None:
    backup = hooks_dir / f"{name}.pre-praxion"
    if not backup.exists():
        # Never overwrite an existing backup (DS-4 / Step 3).
        occupant.replace(backup)
    rendered = render_wrapper(
        hook_name=name, delegate_raw=str(backup), delegate_mode="file", plugin_root=plugin_root
    )
    target = hooks_dir / name
    target.write_text(rendered, encoding="utf-8")
    target.chmod(0o755)


def _install_plain_slots(repo_root: Path, plugin_root: Path) -> InstallResult:
    hooks_dir = repo_root / ".git" / "hooks"
    hooks_dir.mkdir(parents=True, exist_ok=True)
    messages: list[str] = []
    changed = False
    for name in ALL_HOOK_NAMES:
        slot_state = classify_hook_slot(hooks_dir, name)
        if isinstance(slot_state, PraxionWrapperFile):
            messages.append(f"{name}: already Praxion-installed (wrapper) -- unchanged")
            continue
        if isinstance(slot_state, ForeignOccupied):
            _install_wrapper_file(hooks_dir, name, slot_state.path, plugin_root)
            changed = True
            messages.append(
                f"{name}: non-Praxion hook present -> preserved at {name}.pre-praxion + wrapper installed"
            )
            continue
        # Absent or PraxionSymlink -- idempotent install/refresh (the write
        # itself is the content-aware top-up: a byte-identical body is a
        # true no-op, a drifted one is rewritten in place).
        wrote = _install_plain_slot(hooks_dir, name, plugin_root)
        if wrote:
            changed = True
            verb = (
                "installed" if isinstance(slot_state, Absent) else "topped up to current template"
            )
            messages.append(f"{name}: {verb}")
        else:
            messages.append(f"{name}: already current -- unchanged")
    return InstallResult(changed=changed, messages=messages)


# ---- Foreign-hooksPath adoption + wrapper refresh + heal --------------------


def _resolve_delegate_target(repo_root: Path, delegate: DelegateRef) -> Path:
    root = Path(delegate.raw)
    if not root.is_absolute():
        root = repo_root / delegate.raw
    return _safe_resolve(root)


def _is_self_delegation(delegate_abs: Path, wrapper_dir: Path) -> bool:
    return delegate_abs == _safe_resolve(wrapper_dir)


def _adopt_foreign(
    repo_root: Path, dir_raw: str, wrapper_dir: Path, plugin_root: Path
) -> InstallResult:
    wrapper_dir.mkdir(parents=True, exist_ok=True)
    write_recorded_delegate(wrapper_dir, dir_raw)
    _write_wrapper_bodies(wrapper_dir, dir_raw, "dir", plugin_root)
    run_git(repo_root, "config", "core.hooksPath", str(wrapper_dir))
    return InstallResult(
        changed=True, messages=[f"core.hooksPath -> {wrapper_dir} (delegate: {dir_raw})"]
    )


def _refresh_wrapper_bodies(wrapper_dir: Path | None, plugin_root: Path) -> InstallResult:
    if wrapper_dir is None or not wrapper_dir.is_dir():
        return InstallResult(
            changed=False,
            messages=[],
            refused=True,
            reason="core.hooksPath names the Praxion wrapper directory but it is missing on disk",
        )
    delegate = read_recorded_delegate(wrapper_dir)
    if delegate is None:
        return InstallResult(
            changed=False,
            messages=[],
            refused=True,
            reason="wrapper directory has no recorded delegate",
        )
    changed = _write_wrapper_bodies(wrapper_dir, delegate.raw, "dir", plugin_root)
    if changed:
        return InstallResult(changed=True, messages=["wrapper bodies refreshed"])
    return InstallResult(changed=False, messages=["wrapper bodies already current -- no write"])


def _heal_from_unset(repo_root: Path, wrapper_dir: Path | None) -> InstallResult:
    """DS-4's sixth row: hooksPath went Unset while a wrapper directory survives."""
    if wrapper_dir is None or not wrapper_dir.is_dir():
        return InstallResult(
            changed=False,
            messages=[
                "core.hooksPath is unset and no Praxion wrapper directory exists -- nothing to heal"
            ],
        )
    delegate = read_recorded_delegate(wrapper_dir)
    if delegate is not None:
        delegate_abs = _resolve_delegate_target(repo_root, delegate)
        if _is_self_delegation(delegate_abs, wrapper_dir):
            return InstallResult(
                changed=False,
                messages=[],
                refused=True,
                reason=f"recorded delegate '{delegate.raw}' resolves to the wrapper directory itself -- refusing (non-ping-pong invariant)",
            )
    run_git(repo_root, "config", "core.hooksPath", str(wrapper_dir))
    return InstallResult(changed=True, messages=[f"core.hooksPath restored -> {wrapper_dir}"])


# ---- The five(+one)-branch action table (Step 3) ----------------------------


def install_or_heal(repo_root: Path, mode: str, plugin_root: Path) -> InstallResult:
    """Observe, then act. ``mode`` is ``"install"`` or ``"heal"``.

    Only the ``Unset`` branch distinguishes install from heal: ``heal`` never
    onboards a fresh ``Absent``/``ForeignOccupied`` slot (that is
    install-only territory), it only restores a **known** wrapper. The
    ``Foreign`` and ``PraxionWrapper`` branches behave identically under
    either mode.
    """
    assert mode in ("install", "heal")
    hooks_state = observe_hooks_path(repo_root)

    if isinstance(hooks_state, Unresolvable):
        return InstallResult(
            changed=False,
            messages=[],
            refused=True,
            reason=f"core.hooksPath is set to '{hooks_state.raw}' but {hooks_state.reason} -- refusing to install or heal",
        )

    if isinstance(hooks_state, PraxionWrapper):
        return _refresh_wrapper_bodies(wrapper_dir_path(repo_root), plugin_root)

    if isinstance(hooks_state, Foreign):
        wrapper_dir = wrapper_dir_path(repo_root)
        if wrapper_dir is None:
            return InstallResult(
                changed=False,
                messages=[],
                refused=True,
                reason="cannot resolve the git common directory",
            )
        if _is_self_delegation(hooks_state.dir_abs, wrapper_dir):
            return InstallResult(
                changed=False,
                messages=[],
                refused=True,
                reason=f"observed core.hooksPath '{hooks_state.dir_raw}' resolves to Praxion's own wrapper directory -- refusing to self-delegate (non-ping-pong invariant)",
            )
        return _adopt_foreign(repo_root, hooks_state.dir_raw, wrapper_dir, plugin_root)

    # hooks_state is Unset from here.
    if mode == "heal":
        return _heal_from_unset(repo_root, wrapper_dir_path(repo_root))
    return _install_plain_slots(repo_root, plugin_root)


# ---- Status (Step 4) --------------------------------------------------------


def build_status(repo_root: Path, plugin_root: Path) -> dict:
    hooks_state = observe_hooks_path(repo_root)
    report: dict = {
        "hooks_path_state": type(hooks_state).__name__,
        "delegate": None,
        "slots": [],
        "cannot_fire": [],
    }

    if isinstance(hooks_state, Unresolvable):
        report["reason"] = hooks_state.reason
        report["raw"] = hooks_state.raw
        report["cannot_fire"] = ["all slots -- core.hooksPath is set but unresolvable"]
        return report

    if isinstance(hooks_state, PraxionWrapper):
        report["delegate"] = hooks_state.delegate.raw if hooks_state.delegate else None
        wrapper_dir = wrapper_dir_path(repo_root)
        for name in ALL_HOOK_NAMES:
            present = wrapper_dir is not None and (wrapper_dir / name).is_file()
            report["slots"].append(
                {
                    "name": name,
                    "state": "wrapper-file" if present else "absent",
                    "praxion_can_fire": present,
                }
            )
            if not present:
                report["cannot_fire"].append(name)
        return report

    if isinstance(hooks_state, Foreign):
        report["delegate"] = hooks_state.dir_raw
        report["cannot_fire"] = list(ALL_HOOK_NAMES)
        report["slots"] = [
            {"name": n, "state": "not-yet-adopted", "praxion_can_fire": False}
            for n in ALL_HOOK_NAMES
        ]
        return report

    # Unset
    hooks_dir = repo_root / ".git" / "hooks"
    for name in ALL_HOOK_NAMES:
        slot_state = classify_hook_slot(hooks_dir, name)
        can_fire = isinstance(slot_state, (PraxionSymlink, PraxionWrapperFile))
        report["slots"].append(
            {"name": name, "state": type(slot_state).__name__, "praxion_can_fire": can_fire}
        )
        if not can_fire:
            report["cannot_fire"].append(name)
    return report


# ---- Uninstall (Step 4) ------------------------------------------------------


def uninstall(repo_root: Path) -> InstallResult:
    hooks_state = observe_hooks_path(repo_root)
    messages: list[str] = []
    changed = False

    if isinstance(hooks_state, (Foreign, PraxionWrapper)):
        wrapper_dir = wrapper_dir_path(repo_root)
        delegate = hooks_state.delegate if isinstance(hooks_state, PraxionWrapper) else None
        if wrapper_dir is not None and wrapper_dir.is_dir():
            recorded = read_recorded_delegate(wrapper_dir)
            if recorded is not None:
                delegate = recorded
        if delegate is not None:
            run_git(repo_root, "config", "core.hooksPath", delegate.raw)
            messages.append(f"core.hooksPath restored -> {delegate.raw}")
        else:
            run_git(repo_root, "config", "--unset", "core.hooksPath")
            messages.append("core.hooksPath unset")
        changed = True
        if wrapper_dir is not None and wrapper_dir.is_dir():
            shutil.rmtree(wrapper_dir)
            messages.append(f"removed wrapper directory {wrapper_dir}")

    hooks_dir = repo_root / ".git" / "hooks"
    for name in ALL_HOOK_NAMES:
        slot_state = classify_hook_slot(hooks_dir, name)
        if not isinstance(slot_state, (PraxionSymlink, PraxionWrapperFile)):
            continue
        backup = hooks_dir / f"{name}.pre-praxion"
        (hooks_dir / name).unlink()
        changed = True
        if backup.is_file():
            backup.replace(hooks_dir / name)
            messages.append(f"{name}: restored from backup")
        else:
            messages.append(f"{name}: removed (no backup -- was a fresh install)")

    if not changed:
        messages.append("nothing to uninstall")
    return InstallResult(changed=changed, messages=messages)


# ---- CLI ---------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--install",
        action="store_true",
        help="Install the hook chain (Unset+Absent/ForeignOccupied + Foreign adoption)",
    )
    mode.add_argument(
        "--heal", action="store_true", help="Restore a known wrapper; never onboards a fresh slot"
    )
    mode.add_argument(
        "--status",
        action="store_true",
        help="Report observed chain state; exit 1 if a slot cannot fire",
    )
    mode.add_argument(
        "--uninstall", action="store_true", help="Fully reverse Praxion's hook chain presence"
    )
    parser.add_argument(
        "--repo-root", help="Target repository root (default: git rev-parse --show-toplevel)"
    )
    parser.add_argument(
        "--plugin-root", help="Praxion plugin install root (default: this script's parent)"
    )
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    return parser


def _print_result(result: InstallResult, *, as_json: bool) -> None:
    if as_json:
        payload = {
            "changed": result.changed,
            "messages": result.messages,
            "refused": result.refused,
            "reason": result.reason,
        }
        print(json.dumps(payload, indent=2))
        return
    if result.refused:
        print(f"install_git_hooks: refused -- {result.reason}", file=sys.stderr)
        return
    for message in result.messages:
        print(f"  {message}")


def _print_status(report: dict, *, as_json: bool) -> None:
    if as_json:
        print(json.dumps(report, default=str, indent=2))
        return
    print(f"core.hooksPath: {report['hooks_path_state']}")
    if report.get("delegate"):
        print(f"  delegate: {report['delegate']}")
    for slot in report.get("slots", []):
        marker = "ok" if slot["praxion_can_fire"] else "CANNOT FIRE"
        print(f"  {slot['name']}: {slot['state']} [{marker}]")
    for name in report.get("cannot_fire", []):
        print(f"  cannot fire: {name}")


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    repo_root = resolve_repo_root(args.repo_root, script_dir=SCRIPT_DIR)
    if not (repo_root / ".git").exists():
        print(f"install_git_hooks: not a git repository: {repo_root}", file=sys.stderr)
        return EXIT_ENVIRONMENT

    plugin_root = Path(args.plugin_root).resolve() if args.plugin_root else SCRIPT_DIR.parent

    if args.status:
        report = build_status(repo_root, plugin_root)
        _print_status(report, as_json=args.json)
        return EXIT_ACTIONABLE if report.get("cannot_fire") else EXIT_OK

    if args.uninstall:
        result = uninstall(repo_root)
        _print_result(result, as_json=args.json)
        return EXIT_OK

    mode = "install" if args.install else "heal"
    result = install_or_heal(repo_root, mode, plugin_root)
    _print_result(result, as_json=args.json)
    return EXIT_REFUSED if result.refused else EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
