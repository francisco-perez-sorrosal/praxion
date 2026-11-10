"""SessionStart hook: auto-complete marketplace install on first session.

Closes the install-path asymmetry between clone-install and marketplace-install
by detecting missing global surfaces on first session and completing them without
requiring the operator to run /praxion-complete-install manually.

Fast-skip conditions (exit 0, silent):
  (1) Marker file ~/.claude/.praxion-complete-installed exists
      AND marker mtime >= plugin cache directory mtime (post-update rearm)
  (2) PRAXION_DISABLE_AUTO_COMPLETE=1 is set

Otherwise, from the plugin this hook runs from (its own version directory,
`.../praxion/<version>/`, never the unversioned cache parent):
  - Surfaces already present (CLAUDE.md symlink and the rules sentinel, both
    resolving): refresh the rule links -- sweep each stale Praxion link and link
    each manifest rule that has none -- then write the marker. An existing live
    link is never re-pointed, so a clone install's links stay its own.
  - Otherwise (cold path): derive personal-info defaults, optionally prompt the
    operator (30s timeout-accept), run install steps, write marker.

Rule linking goes through the installer's own shell library
(`lib/install_shared.sh`), so this hook, `install.sh` and `install.sh --check`
apply one manifest reading and one stale-link predicate.

Non-interactive auto-accept:
  - PRAXION_AUTO_COMPLETE=1 set: skip prompt, use defaults.
  - stdin is EOF immediately (piped/redirected): treat as timeout-accept.

Exit 0 unconditionally — this hook must NEVER block session start.
"""

from __future__ import annotations

import json
import os
import signal
import stat
import subprocess
import sys
from collections.abc import Iterable
from pathlib import Path

# ---------------------------------------------------------------------------
# Path bootstrap: inject scripts/ so render_claude_md is importable
# without PYTHONPATH being set.
# ---------------------------------------------------------------------------

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
import render_claude_md as _render_mod  # noqa: E402 (after sys.path injection)

# The hook's own directory: the suite loads this file by path, so its sibling
# modules are not importable without it.
sys.path.insert(0, str(Path(__file__).parent))
from _install_refresh import (  # noqa: E402 (after sys.path injection)
    BinEntry,
    EntryKind,
    Keep,
    Link,
    OfferedScript,
    Remove,
    Repoint,
    ScriptAction,
    plan_script_links,
    unreachable,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DISABLE_AUTO_COMPLETE = "PRAXION_DISABLE_AUTO_COMPLETE"
_AUTO_COMPLETE_FLAG = "PRAXION_AUTO_COMPLETE"

_TRUTHY = frozenset({"1", "true", "yes"})

_MARKER_FILENAME = ".praxion-complete-installed"
_DECLINE_MARKER_FILENAME = ".praxion-install-declined"

# The unversioned cache parent: an update adds a version directory under it,
# which moves its mtime past the marker's and re-arms the hook. Install sources
# are read from the version directory `_plugin_root` returns, never from here.
_PLUGIN_CACHE_SUBPATH = Path(".claude") / "plugins" / "cache" / "bit-agora" / "praxion"
_INSTALLED_PLUGINS_SUBPATH = Path(".claude") / "plugins" / "installed_plugins.json"
_PLUGIN_KEY_PREFIX = "praxion@"
_RULES_SENTINEL_SUBPATH = Path(".claude") / "rules" / "swe" / "agent-behavioral-contract.md"
_CLAUDE_MD_SUBPATH = Path(".claude") / "CLAUDE.md"
_BIN_SUBPATH = Path(".local") / "bin"

# Scripts git invokes, never the operator: merge drivers and hook scripts.
_MERGE_DRIVER_PREFIX = "merge_driver_"
_HOOK_SCRIPT_SUFFIX = "-hook.sh"

# Ends the name of the link built beside a destination before it is renamed over it.
_TEMPORARY_LINK_SUFFIX = ".refreshing"

# Relative to the plugin root
_TEMPLATE_RELATIVE = Path("claude") / "config" / "CLAUDE.md.tmpl"
_SHARED_LIB_RELATIVE = Path("lib") / "install_shared.sh"

# One rule-linking run: a few hundred symlinks at most, well inside the hook's
# registered 35-second budget alongside the 30-second prompt.
_LINKER_TIMEOUT_SECS = 20

# Interactive prompt timeout (seconds)
_PROMPT_TIMEOUT_SECS = 30


# ---------------------------------------------------------------------------
# Home directory resolution (uses env var so tests can fake HOME)
# ---------------------------------------------------------------------------


def _home() -> Path:
    """Return the current user's home directory.

    Reads os.environ["HOME"] directly so that test monkeypatching of HOME
    via monkeypatch.setenv("HOME", ...) works correctly.  Path.home() uses
    pwd on some platforms which bypasses the env-var override.
    """
    home_env = os.environ.get("HOME")
    if home_env:
        return Path(home_env)
    return Path.home()


def _plugin_root(home: Path) -> Path | None:
    """Return the directory of the Praxion plugin to install from, or None.

    The hook's own `CLAUDE_PLUGIN_ROOT` comes first: Claude Code sets it to the
    plugin the hook runs from, a cache version directory for a marketplace
    install or a checkout under `--plugin-dir`. Without it, the plugin registry
    (`installed_plugins.json`) names the install path of the praxion plugin.
    Claude Code installs into `.../praxion/<version>/`, so the unversioned
    cache parent never holds the plugin's files.
    """
    env_root = os.environ.get("CLAUDE_PLUGIN_ROOT", "").strip()
    if env_root and Path(env_root).is_dir():
        return Path(env_root)
    try:
        registry = json.loads((home / _INSTALLED_PLUGINS_SUBPATH).read_text(encoding="utf-8"))
        for key, installs in registry.get("plugins", {}).items():
            if not key.startswith(_PLUGIN_KEY_PREFIX):
                continue
            for install in installs:
                root = Path(install.get("installPath", ""))
                if install.get("installPath") and root.is_dir():
                    return root
    except (OSError, ValueError, AttributeError, TypeError):
        pass
    return None


# ---------------------------------------------------------------------------
# Fast-skip predicate
# ---------------------------------------------------------------------------


def _is_install_complete(home: Path) -> bool:
    """Return True when the install marker is fresh relative to the plugin cache.

    Checks:
      1. Marker file exists at ~/.claude/.praxion-complete-installed
      2. Marker mtime >= plugin cache directory mtime

    Returns False when the plugin cache directory does not exist (safe default:
    attempt to install).  Returns False when the marker does not exist.
    """
    marker = home / ".claude" / _MARKER_FILENAME
    if not marker.exists():
        return False

    plugin_cache = home / _PLUGIN_CACHE_SUBPATH
    if not plugin_cache.exists():
        # Cannot perform mtime comparison — treat as incomplete so install runs
        return False

    return marker.stat().st_mtime >= plugin_cache.stat().st_mtime


def _surfaces_present(home: Path) -> bool:
    """Return True when all expected global surfaces are in place.

    Surfaces checked:
      - ~/.claude/CLAUDE.md is a symlink that resolves (a link left dangling
        when an old plugin version's directory is removed is not installed)
      - ~/.claude/rules/swe/agent-behavioral-contract.md exists
    """
    claude_md = home / _CLAUDE_MD_SUBPATH
    rules_sentinel = home / _RULES_SENTINEL_SUBPATH
    return claude_md.is_symlink() and claude_md.exists() and rules_sentinel.exists()


# ---------------------------------------------------------------------------
# Marker helpers
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


# ---------------------------------------------------------------------------
# Install steps
# ---------------------------------------------------------------------------


def _render_claude_md(home: Path, values: dict[str, str], root: Path) -> None:
    """Render ~/.claude/CLAUDE.md from the plugin's template.

    Renders the template into a real file in the plugin's config dir, then
    symlinks ~/.claude/CLAUDE.md to that rendered file.  Raises on any I/O error.
    """
    template_path = root / _TEMPLATE_RELATIVE
    rendered_path = root / "claude" / "config" / "CLAUDE.md"

    _render_mod.render_claude_md(template_path, rendered_path, values)

    claude_md_link = home / _CLAUDE_MD_SUBPATH
    claude_md_link.parent.mkdir(parents=True, exist_ok=True)
    if claude_md_link.exists() or claude_md_link.is_symlink():
        claude_md_link.unlink()
    claude_md_link.symlink_to(rendered_path)


def _run_rule_linker(home: Path, root: Path, function: str) -> None:
    """Run one rule-linking function of the plugin's shell library.

    `function` is `link_rules` (the installer's full link: sweep, then link the
    manifest's `install: symlink` set) or `refresh_rule_symlinks` (sweep, then
    link only the rules that have no working link). The library reads the
    manifest without PyYAML, so the ambient `python3` this hook runs under
    never decides which rules get linked. A plugin without the library or a
    rules directory links nothing.
    """
    rules_src = root / "rules"
    library = root / _SHARED_LIB_RELATIVE
    if not rules_src.is_dir() or not library.is_file():
        return
    subprocess.run(
        ["bash", "-c", 'source "$1" && "$2" "$3" "$4"', "auto_complete_install"]
        + [str(library), function, str(rules_src), str(home / ".claude" / "rules")],
        env={**os.environ, "HOME": str(home)},
        capture_output=True,
        timeout=_LINKER_TIMEOUT_SECS,
        check=True,
    )


def _link_rules(home: Path, root: Path) -> None:
    """Link ~/.claude/rules/ to the manifest's `install: symlink` set.

    The installer's own `link_rules`: stale Praxion links are swept, every
    `install: symlink` rule is linked, hook-delivered rules and directory guides
    are never linked. Used on a cold install.
    """
    _run_rule_linker(home, root, "link_rules")


def _refresh_rules(home: Path, root: Path) -> None:
    """Bring installed rule links to this plugin version without taking any over.

    Sweeps each stale Praxion link (a rule the manifest no longer links, in
    this plugin's rules or any cached version's) and links each manifest rule
    that has no working link. An existing live link is left as it is.
    """
    _run_rule_linker(home, root, "refresh_rule_symlinks")


def offered_scripts(root: Path) -> tuple[OfferedScript, ...]:
    """The user-facing scripts the plugin at `root` offers, in name order.

    A regular, executable file under `scripts/` that is neither a git merge
    driver nor a git hook script. The first install and the update path read
    this one predicate, so they never disagree on which scripts reach the PATH.
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


def _link_scripts(home: Path, root: Path) -> None:
    """Symlink user-facing scripts from the plugin into ~/.local/bin/."""
    if not (root / "scripts").is_dir():
        return

    bin_dest = home / _BIN_SUBPATH
    bin_dest.mkdir(parents=True, exist_ok=True)

    for script in offered_scripts(root):
        dest = bin_dest / script.name
        if dest.is_symlink():
            dest.unlink()
        dest.symlink_to(script.path)


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


def _repoint(bin_dir: Path, name: str, target: str) -> None:
    """Replace the link `name` by one to `target` in a single rename.

    The new link is built beside the old and renamed over it, so there is never
    a moment with no link; it is removed again when the rename fails.
    """
    temporary = bin_dir / f".{name}.{os.getpid()}{_TEMPORARY_LINK_SUFFIX}"
    temporary.unlink(missing_ok=True)
    temporary.symlink_to(target)
    try:
        os.replace(temporary, bin_dir / name)
    except BaseException:
        temporary.unlink(
            missing_ok=True
        )  # a concurrent session may have swept it; keep the original error
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
        _repoint(bin_dir, action.name, action.target)
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


def _run_install(home: Path, values: dict[str, str], root: Path) -> None:
    """Run the full install sequence: render CLAUDE.md, link rules, link scripts."""
    _render_claude_md(home, values, root)
    _link_rules(home, root)
    _link_scripts(home, root)


# ---------------------------------------------------------------------------
# Interactive prompt with timeout
# ---------------------------------------------------------------------------


def _prompt_with_timeout(values: dict[str, str]) -> bool:
    """Prompt the operator to confirm personal-info values.

    Returns True to proceed (accept defaults or user confirmed), False to
    decline.  On timeout, returns True (default-accept).  On EOF (non-
    interactive or piped stdin), returns True immediately.
    """
    username = values.get("USERNAME", "@anon")
    email = values.get("EMAIL", "anon@unknown")
    github = values.get("GITHUB_URL", "https://github.com/anon")

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


# ---------------------------------------------------------------------------
# Main hook entry point
# ---------------------------------------------------------------------------


def main() -> None:
    """Hook entry point: read stdin, run fast-skip or cold path, exit 0."""
    try:
        _run()
    except Exception:
        # Any unhandled error — exit 0 unconditionally to never block session start
        pass


def _resolve_mode() -> bool:
    """Return True when auto-complete mode is active (skip interactive prompt).

    Auto-complete is active when PRAXION_AUTO_COMPLETE=1 is set, indicating
    a non-interactive environment (CI, headless container) or operator opt-in.
    """
    return os.environ.get(_AUTO_COMPLETE_FLAG, "").strip().lower() in _TRUTHY


def _perform_install(home: Path, values: dict[str, str], auto_complete: bool, root: Path) -> None:
    """Run the interactive-prompt + install sequence for the cold path.

    When auto_complete is False, prompts the operator (30s timeout-accept).
    On decline writes a soft-decline marker and returns without installing.
    On accept (or auto_complete=True), runs the full install and writes the
    completion marker. A failed install is reported as one, with the command
    that completes it, never as a success.
    """
    if not auto_complete:
        try:
            accepted = _prompt_with_timeout(values)
        except Exception:
            accepted = True

        if not accepted:
            try:
                _write_decline_marker(home)
            except Exception:
                pass
            return

    # Run install steps (a failure is reported below; the marker is still written)
    failure: Exception | None = None
    try:
        _run_install(home, values, root)
    except Exception as exc:
        failure = exc

    # Write the marker regardless: without it the same failing install would
    # rerun at every session start.
    try:
        _write_marker(home)
    except Exception:
        pass

    if failure is None:
        sys.stderr.write("[Praxion] Auto-install complete.\n")
    else:
        sys.stderr.write(
            f"[Praxion] Auto-install could not finish ({type(failure).__name__}); "
            "run /praxion-complete-install to complete it.\n"
        )
    sys.stderr.flush()


def _run() -> None:
    """Core logic: fast-skip guards then cold path."""
    # Drain stdin (required to avoid SIGPIPE; payload not needed for install logic)
    try:
        sys.stdin.read()
    except Exception:
        pass

    home = _home()

    # Disable opt-out: exit 0 silently
    if os.environ.get(DISABLE_AUTO_COMPLETE, "").strip().lower() in _TRUTHY:
        return

    # Fast-skip: marker fresh relative to plugin cache
    if _is_install_complete(home):
        return

    root = _plugin_root(home)
    if root is None:
        # Nothing to install from: leave the marker unwritten so a later
        # session, once the plugin is resolvable, still completes the install.
        return

    # Surfaces present (an install or an update ran before): refresh the rule
    # links to this version, then record completion.
    if _surfaces_present(home):
        try:
            _refresh_rules(home, root)
        except Exception:
            pass
        try:
            _write_marker(home)
        except Exception:
            pass
        return

    # Cold path: derive defaults and perform install
    try:
        values = _render_mod.derive_defaults()
    except Exception:
        values = {
            "USERNAME": "@anon",
            "EMAIL": "anon@unknown",
            "GITHUB_URL": "https://github.com/anon",
        }

    _perform_install(home, values, _resolve_mode(), root)


if __name__ == "__main__":
    main()
