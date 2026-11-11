"""The effects the auto-complete hook shares with its update path, and the update path itself.

A private sibling of `auto_complete_install.py`, like `_rule_delivery.py` and
`_install_refresh.py`: the hook keeps its entry point, the gate that chooses
between the update path and the install paths, and the cold first install; this
module holds what the update path does to the global surfaces. It is the
effectful half of the refresh, `_install_refresh` the pure half: each step
gathers a snapshot, asks the pure core what to do, then applies the answer with
a rename, so no surface is ever left without a working entry.

The update path runs when an install ran before (the marker) and the plugin runs
from a cache version directory. It has three independent steps, each fail-open.
The instructions step classifies `~/.claude/CLAUDE.md` into one of five states:

- a live link into another cached version's render is re-rendered from this
  version's template with the values that render carried;
- nothing there, or a link into the cache that no longer resolves, is set up as
  a first install sets it up, confirmation prompt included;
- a regular file, or a link outside the cache (a clone's), is never replaced.

The rules and scripts steps refresh: they re-point what lies in another cached
version and add what is missing, and never take over a live link of a clone.

The hook puts `scripts/` (for `render_claude_md`) and its own directory on
`sys.path` before importing this module, which is why neither is injected here.
Stdlib only and importable on Python 3.9, like the hook.
"""

from __future__ import annotations

import contextlib
import os
import signal
import stat
import subprocess
import sys
from collections.abc import Callable, Iterable
from pathlib import Path

import render_claude_md as _render_mod
from _install_refresh import (
    BinEntry,
    CachedRender,
    EntryKind,
    ForeignLink,
    InstructionsSnapshot,
    Keep,
    Link,
    MissingCachedRender,
    NoInstructions,
    OfferedScript,
    Remove,
    Repoint,
    ScriptAction,
    SnapshotKind,
    UserOwned,
    cache_version_dir,
    classify_instructions,
    plan_script_links,
    unreachable,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_MARKER_FILENAME = ".praxion-complete-installed"
_DECLINE_MARKER_FILENAME = ".praxion-install-declined"

_AUTO_COMPLETE_FLAG = "PRAXION_AUTO_COMPLETE"
_TRUTHY = frozenset({"1", "true", "yes"})

# Interactive prompt timeout (seconds)
_PROMPT_TIMEOUT_SECS = 30

# What a first install writes when no git identity can be derived.
_ANONYMOUS_VALUES = {
    "USERNAME": "@anon",
    "EMAIL": "anon@unknown",
    "GITHUB_URL": "https://github.com/anon",
}

_CLAUDE_MD_SUBPATH = Path(".claude") / "CLAUDE.md"
_BIN_SUBPATH = Path(".local") / "bin"

# Scripts git invokes, never the operator: merge drivers and hook scripts.
_MERGE_DRIVER_PREFIX = "merge_driver_"
_HOOK_SCRIPT_SUFFIX = "-hook.sh"

# Ends the name of the entry built beside a destination before it is renamed over it.
_TEMPORARY_SUFFIX = ".refreshing"

# Relative to the plugin root
_TEMPLATE_RELATIVE = Path("claude") / "config" / "CLAUDE.md.tmpl"
_RENDER_RELATIVE = Path("claude") / "config" / "CLAUDE.md"
_SHARED_LIB_RELATIVE = Path("lib") / "install_shared.sh"

# One rule-linking run: a few hundred symlinks at most, well inside the hook's
# registered 35-second budget alongside the 30-second prompt.
_LINKER_TIMEOUT_SECS = 20

# The shell for `_run_rule_linkers`: $1 the library, $2 the rules source, $3 the
# rules target, then the functions to call with the two directories, in order.
_LINKER_SCRIPT = (
    'source "$1" && source_dir=$2 && target_dir=$3 && shift 3 && '
    'for function; do "$function" "$source_dir" "$target_dir" || exit $?; done'
)


# ---------------------------------------------------------------------------
# Effects shared with the install paths
# ---------------------------------------------------------------------------


def _write_marker(home: Path) -> None:
    """Write (or overwrite) the completion marker file."""
    marker = home / ".claude" / _MARKER_FILENAME
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text("")


def _write_decline_marker(home: Path) -> None:
    """Write a soft-decline marker (operator chose not to install)."""
    marker = home / ".claude" / _DECLINE_MARKER_FILENAME
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text("")


def _resolve_mode() -> bool:
    """Return True when auto-complete mode is active (skip interactive prompt).

    Auto-complete is active when PRAXION_AUTO_COMPLETE=1 is set, indicating
    a non-interactive environment (CI, headless container) or operator opt-in.
    """
    return os.environ.get(_AUTO_COMPLETE_FLAG, "").strip().lower() in _TRUTHY


def _default_values() -> dict[str, str]:
    """The personal values a first install renders: derived from git, else anonymous."""
    try:
        return _render_mod.derive_defaults()
    except Exception:
        return dict(_ANONYMOUS_VALUES)


def _render_claude_md(home: Path, values: dict[str, str], root: Path) -> None:
    """Render ~/.claude/CLAUDE.md from the plugin's template.

    Renders the template into a real file in the plugin's config dir, then
    symlinks ~/.claude/CLAUDE.md to that rendered file.  Raises on any I/O error.
    """
    template_path = root / _TEMPLATE_RELATIVE
    rendered_path = root / _RENDER_RELATIVE

    _render_mod.render_claude_md(template_path, rendered_path, values)

    claude_md_link = home / _CLAUDE_MD_SUBPATH
    claude_md_link.parent.mkdir(parents=True, exist_ok=True)
    if claude_md_link.exists() or claude_md_link.is_symlink():
        claude_md_link.unlink()
    claude_md_link.symlink_to(rendered_path)


def _prompt_with_timeout(values: dict[str, str]) -> bool:
    """Prompt the operator to confirm personal-info values.

    Returns True to proceed (accept defaults or user confirmed), False to
    decline.  On timeout, returns True (default-accept).  On EOF (non-
    interactive or piped stdin), returns True immediately.
    """
    username = values.get("USERNAME", _ANONYMOUS_VALUES["USERNAME"])
    email = values.get("EMAIL", _ANONYMOUS_VALUES["EMAIL"])
    github = values.get("GITHUB_URL", _ANONYMOUS_VALUES["GITHUB_URL"])

    msg = (
        "\n[Praxion] First-session auto-install\n"
        f"  username: {username}\n"
        f"  email:    {email}\n"
        f"  github:   {github}\n"
        "\nProceed with install? [Y/n, auto-accepts in 30s]: "
    )

    accepted = True

    def _on_timeout(signum: int, frame: object) -> None:
        # Timeout fires — proceed with defaults
        pass

    try:
        old_handler = signal.signal(signal.SIGALRM, _on_timeout)
        signal.alarm(_PROMPT_TIMEOUT_SECS)
        try:
            sys.stderr.write(msg)
            sys.stderr.flush()
            line = sys.stdin.readline()
            signal.alarm(0)  # Cancel alarm on successful read
            stripped = line.strip().lower()
            if stripped in ("n", "no"):
                accepted = False
        except (EOFError, OSError):
            # stdin is EOF or not readable — auto-accept
            signal.alarm(0)
            accepted = True
        finally:
            signal.signal(signal.SIGALRM, old_handler)
            signal.alarm(0)
    except Exception:
        # signal.SIGALRM may not be available on all platforms (e.g., Windows)
        # Fall back to non-interactive accept
        accepted = True

    return accepted


def _confirm_install(home: Path, values: dict[str, str], auto_complete: bool) -> bool:
    """Whether a first install of `values` goes ahead.

    Auto-complete mode skips the prompt. Otherwise the operator is asked (30s
    timeout-accept, a prompt that cannot run counts as consent); a refusal
    writes the soft-decline marker.
    """
    if auto_complete:
        return True
    try:
        accepted = _prompt_with_timeout(values)
    except Exception:
        accepted = True
    if not accepted:
        try:
            _write_decline_marker(home)
        except Exception:
            pass
    return accepted


def _install_complete_line() -> str:
    """The line to report when a first install's setup completed."""
    return "[Praxion] Auto-install complete."


def _run_rule_linkers(home: Path, root: Path, functions: tuple[str, ...]) -> None:
    """Run several rule-linking functions of the shell library, in order, in one shell.

    Each gets the plugin's rules directory and `~/.claude/rules`; the first to
    fail ends the run. One shell keeps a single timeout and the one `HOME`
    override for the whole sequence.
    """
    rules_src = root / "rules"
    library = root / _SHARED_LIB_RELATIVE
    if not rules_src.is_dir() or not library.is_file():
        return
    subprocess.run(
        ["bash", "-c", _LINKER_SCRIPT, "auto_complete_install"]
        + [str(library), str(rules_src), str(home / ".claude" / "rules"), *functions],
        env={**os.environ, "HOME": str(home)},
        capture_output=True,
        timeout=_LINKER_TIMEOUT_SECS,
        check=True,
    )


def offered_scripts(root: Path) -> tuple[OfferedScript, ...]:
    """The user-facing scripts the plugin at `root` offers, in name order.

    A regular, executable file under `scripts/` that is neither a git merge
    driver nor a hook script (`*-hook.sh`, which git or pre-commit runs by path).
    The first install and the update path read this one predicate, and the
    installer's `script_is_user_facing` is its twin, held equal by
    `hooks/test_install_script_predicate.py`, so no install path links a script
    another removes.
    """
    scripts_src = root / "scripts"
    if not scripts_src.is_dir():
        return ()
    return tuple(
        OfferedScript(script.name, str(script))
        for script in sorted(scripts_src.iterdir())
        if script.is_file()
        and os.access(script, os.X_OK)
        and not script.name.startswith(_MERGE_DRIVER_PREFIX)
        and not script.name.endswith(_HOOK_SCRIPT_SUFFIX)
    )


# ---------------------------------------------------------------------------
# Update path
# ---------------------------------------------------------------------------


def _update_rules(home: Path, root: Path) -> None:
    """Bring installed rule links to the cached version at `root`.

    First re-points each rule link that lies in another cached version's rules,
    then refreshes as `_refresh_rules` does. A live link outside the cache is
    still never taken over.
    """
    _run_rule_linkers(home, root, ("repoint_cached_rule_symlinks", "refresh_rule_symlinks"))


def snapshot_bin(bin_dir: Path) -> tuple[BinEntry, ...]:
    """One `BinEntry` per entry of `bin_dir`; a missing directory has none.

    Reads each entry with `lstat`, so a link is never followed to classify it;
    a link also carries its text and its real path (None when it dangles).
    """
    if not bin_dir.is_dir():
        return ()
    entries = []
    for path in sorted(bin_dir.iterdir()):
        try:
            mode = path.lstat().st_mode
            if stat.S_ISLNK(mode):
                real = os.path.realpath(path) if path.exists() else None
                entries.append(BinEntry(path.name, EntryKind.LINK, os.readlink(path), real))
            elif stat.S_ISREG(mode):
                entries.append(BinEntry(path.name, EntryKind.FILE, "", None))
            else:
                entries.append(BinEntry(path.name, EntryKind.OTHER, "", None))
        except FileNotFoundError:
            continue  # removed between the listing and the read: nothing to plan for
    return tuple(entries)


def _replace_link(link: Path, target: str) -> None:
    """Point `link` at `target` in a single rename, never leaving a moment with no link."""
    _build_and_rename(link, lambda temporary: temporary.symlink_to(target))


def _build_and_rename(destination: Path, build: Callable[[Path], object]) -> None:
    """Build an entry beside `destination` with `build`, then rename it over `destination`.

    The rename is atomic, so `destination` holds the old entry or the new one,
    never neither. When building or renaming fails the temporary is removed and
    the original error is the one raised.
    """
    temporary = destination.with_name(f".{destination.name}.{os.getpid()}{_TEMPORARY_SUFFIX}")
    temporary.unlink(missing_ok=True)
    try:
        build(temporary)
        os.replace(temporary, destination)
    except BaseException:
        with contextlib.suppress(OSError):  # never built, or swept by a concurrent session
            temporary.unlink()
        raise


def apply_script_actions(bin_dir: Path, actions: Iterable[ScriptAction]) -> None:
    """Apply every action, then raise the first error met, if any.

    One failing link never stops the rest. `Remove` unlinks a link and nothing
    else; `Link` creates `bin_dir` when it is missing and never overwrites.
    """
    first_error: OSError | None = None
    for action in actions:
        try:
            _apply_script_action(bin_dir, action)
        except OSError as error:
            first_error = first_error or error
    if first_error is not None:
        raise first_error


def _apply_script_action(bin_dir: Path, action: ScriptAction) -> None:
    if isinstance(action, Keep):
        return
    if isinstance(action, Repoint):
        _replace_link(bin_dir / action.name, action.target)
    elif isinstance(action, Remove):
        if (bin_dir / action.name).is_symlink():
            (bin_dir / action.name).unlink(
                missing_ok=True
            )  # gone since planning is the goal reached
    elif isinstance(action, Link):
        bin_dir.mkdir(parents=True, exist_ok=True)
        (bin_dir / action.name).symlink_to(action.target)
    else:
        unreachable(action)


def refresh_scripts(home: Path, root: Path) -> None:
    """Bring the script links in ~/.local/bin to the plugin at `root`.

    Gathers the bin directory, plans from it, then applies the plan: a link into
    another cached version moves to `root`, a free name is linked, and nothing
    the plugin cache does not own is touched.
    """
    bin_dir = home / _BIN_SUBPATH
    actions = plan_script_links(snapshot_bin(bin_dir), offered_scripts(root), str(bin_dir))
    apply_script_actions(bin_dir, actions)


class UnrecoverableRenderError(Exception):
    """A previous render is not its template filled with single-line values."""


def snapshot_instructions(path: Path) -> InstructionsSnapshot:
    """What `path` holds, read with `lstat` so a link is never followed to classify it."""
    try:
        mode = path.lstat().st_mode
    except FileNotFoundError:
        return InstructionsSnapshot(SnapshotKind.ABSENT, "", False)
    if stat.S_ISLNK(mode):
        return InstructionsSnapshot(SnapshotKind.LINK, os.readlink(path), path.exists())
    if stat.S_ISREG(mode):
        return InstructionsSnapshot(SnapshotKind.FILE, "", False)
    return InstructionsSnapshot(SnapshotKind.OTHER, "", False)


def _update_instructions(home: Path, root: Path) -> str | None:
    """Bring ~/.claude/CLAUDE.md to the plugin at `root`, by what it holds.

    A regular file and a link outside the cache are never touched. A live link
    into another cached version's render moves to `root`'s; one already into
    `root`'s version stays. Nothing there, or a link into the cache that no
    longer resolves, is set up as a first install sets it up, and only that
    setup returns a line for the user: its completion.
    """
    link = home / _CLAUDE_MD_SUBPATH
    link_dir = str(link.parent)
    state = classify_instructions(snapshot_instructions(link), link_dir)
    if isinstance(state, (UserOwned, ForeignLink)):
        return None
    if isinstance(state, CachedRender):
        if state.version_dir != cache_version_dir(str(root), link_dir):
            carry_forward_instructions(home, root, state)
        return None
    if isinstance(state, (NoInstructions, MissingCachedRender)):
        return _fresh_instructions_setup(home, root)
    unreachable(state)


class InstallDeclinedError(Exception):
    """The operator refused the confirmation: nothing is set up, no completion is recorded."""


def _fresh_instructions_setup(home: Path, root: Path) -> str:
    """Set up ~/.claude/CLAUDE.md as the cold first install does, rules and scripts aside.

    Derives the personal values, asks the operator to confirm them (unless
    auto-complete mode is on), renders into `root` and links the render, then
    returns the completion line. The prompt goes to the terminal only. Raises
    InstallDeclinedError on a refusal.
    """
    values = _default_values()
    if not _confirm_install(home, values, _resolve_mode()):
        raise InstallDeclinedError
    _render_claude_md(home, values, root)
    return _install_complete_line()


def carry_forward_instructions(home: Path, root: Path, state: CachedRender) -> None:
    """Render `root`'s template with the values the render `state` names carried, and link it.

    The values are read back from `state.render`, the file the link names, not from
    the version's primary render: a second render beside it can be the live one.
    Raises UnrecoverableRenderError, before anything is written, when that render
    cannot be opened, decoded or read back as its version's template: falling back
    to defaults would replace the user's identity with today's derived one.
    """
    try:
        render_text = Path(state.render).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as error:
        raise UnrecoverableRenderError from error
    carried = _render_mod.recover_values(
        (Path(state.version_dir) / _TEMPLATE_RELATIVE).read_text(encoding="utf-8"), render_text
    )
    if carried is None:
        raise UnrecoverableRenderError
    write_instructions(home, root, carried)


def write_instructions(home: Path, root: Path, values: dict[str, str]) -> None:
    """Render `root`'s template with `values` into its render, then link the render.

    A key `values` lacks is filled from today's derived values; a derived value
    never replaces one given. The render is renamed into place before the link is
    swapped, so ~/.claude/CLAUDE.md resolves to a complete render, the previous
    one or the new one, whatever fails. Prints nothing of its own and saves no other
    copy of the values: the terminal path shares this writer. `render_claude_md`
    still warns on stderr, naming the placeholders, of a key left unfilled.
    """
    template_path = root / _TEMPLATE_RELATIVE
    missing = _missing_keys(template_path.read_text(encoding="utf-8"), values)
    # Derived only when a key is missing: it reads today's git identity.
    filled = _with_defaults(values, missing, _render_mod.derive_defaults()) if missing else values
    rendered_path = root / _RENDER_RELATIVE
    _build_and_rename(
        rendered_path,
        lambda temporary: _render_mod.render_claude_md(template_path, temporary, filled),
    )
    _replace_link(home / _CLAUDE_MD_SUBPATH, str(rendered_path))


# Each placeholder is its name inside `{{` and `}}`, as PLACEHOLDER_PATTERN reads it.
_PLACEHOLDER_BRACE_WIDTH = len("{{")


def _missing_keys(template_text: str, carried: dict[str, str]) -> frozenset[str]:
    """The placeholder names `template_text` holds that `carried` has no value for.

    A carried value equal to its own placeholder is no value: the previous render
    left that key unfilled, so a default may fill it now.
    """
    width = _PLACEHOLDER_BRACE_WIDTH
    placeholders = {
        m.group()[width:-width]: m.group()
        for m in _render_mod.PLACEHOLDER_PATTERN.finditer(template_text)
    }
    return frozenset(
        name for name, token in placeholders.items() if carried.get(name, token) == token
    )


def _with_defaults(
    carried: dict[str, str], missing: frozenset[str], defaults: dict[str, str]
) -> dict[str, str]:
    """The carried values plus a default for each missing key, and only those keys.

    A default never replaces a carried value; a missing key with no default stays
    out, so its placeholder survives the render as a named residual.
    """
    return {**carried, **{key: defaults[key] for key in missing if key in defaults}}


# The update path's steps, in the one place that orders them. Each takes
# (home, plugin root) and runs on its own, so a failing step never costs the next;
# a step may return a line for the user, and one that returns None has none.
_UPDATE_STEPS = (_update_instructions, _update_rules, refresh_scripts)


def _run_update_path(home: Path, root: Path) -> list[str]:
    """Refresh a completed install to the plugin at `root`, never raising.

    Returns the lines for the user in firing order: those the steps return, then
    the first failure's. Every step runs and the first failure is remembered;
    the marker is written whatever happened, so a failing refresh is not retried
    at each session. The exception is a refused first-install confirmation: it
    is no failure, and it leaves the marker as it was, so the next session asks
    again.
    """
    lines: list[str] = []
    first_failure: Exception | None = None
    declined = False
    for step in _UPDATE_STEPS:
        try:
            line = step(home, root)
        except InstallDeclinedError:
            declined = True
        except Exception as exc:
            first_failure = first_failure or exc
        else:
            if line is not None:
                lines.append(line)
    if not declined:
        try:
            _write_marker(home)
        except Exception:
            pass
    if first_failure is not None:
        lines.append(_incomplete_line("Update refresh", first_failure))
    return lines


def _incomplete_line(what: str, failure: Exception) -> str:
    """The line to report that `what` stopped: the exception type and the way to finish.

    The type only: a message or value could carry a path or a personal detail.
    """
    return (
        f"[Praxion] {what} could not finish ({type(failure).__name__}); "
        "run /praxion-complete-install to complete it."
    )
