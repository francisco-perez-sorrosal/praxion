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
  - Update path: the marker is present (an install ran before) and the plugin
    root lies in a cache version directory, whatever `~/.claude/CLAUDE.md` holds.
    The steps and the five states of the instructions are described in
    `_install_update`: a cached render is carried forward with its personal
    values, a missing or dangling cache link is set up as a first install sets
    it up, and a regular file or a clone's link is left alone; the rule and
    script links are refreshed, never taken over. Each step is fail-open and
    the marker is written whatever happened, except after a refused
    confirmation. A fully successful run prints nothing; a failure prints one
    stderr line carrying the exception type and the command that completes the
    refresh by hand.
  - Surfaces already present (CLAUDE.md symlink and the rules sentinel, both
    resolving) but no update path (a first session after a clone install, or a
    `--plugin-dir` checkout root): refresh the rule links -- sweep each stale
    Praxion link and link each manifest rule that has none -- then write the
    marker. An existing live link is never re-pointed, so a clone install's links
    stay its own.
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
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Path bootstrap: inject scripts/ so `_install_update` can import
# render_claude_md without PYTHONPATH being set.
# ---------------------------------------------------------------------------

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

# The hook's own directory: the suite loads this file by path, so its sibling
# modules are not importable without it.
sys.path.insert(0, str(Path(__file__).parent))
from _install_refresh import (  # noqa: E402 (after sys.path injection)
    CachedRender,
    ForeignLink,
    cache_version_dir,
    classify_instructions,
)
from _install_update import (  # noqa: E402 (after sys.path injection)
    _BIN_SUBPATH,
    _CLAUDE_MD_SUBPATH,
    _MARKER_FILENAME,
    _TRUTHY,
    _confirm_install,
    _default_values,
    _render_claude_md,
    _report_incomplete,
    _report_install_complete,
    _resolve_mode,
    _run_rule_linkers,
    _run_update_path,
    _write_marker,
    offered_scripts,
    snapshot_instructions,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DISABLE_AUTO_COMPLETE = "PRAXION_DISABLE_AUTO_COMPLETE"
# The unversioned cache parent: an update adds a version directory under it,
# which moves its mtime past the marker's and re-arms the hook. Install sources
# are read from the version directory `_plugin_root` returns, never from here.
_PLUGIN_CACHE_SUBPATH = Path(".claude") / "plugins" / "cache" / "bit-agora" / "praxion"
_INSTALLED_PLUGINS_SUBPATH = Path(".claude") / "plugins" / "installed_plugins.json"
_PLUGIN_KEY_PREFIX = "praxion@"
_RULES_SENTINEL_SUBPATH = Path(".claude") / "rules" / "swe" / "agent-behavioral-contract.md"


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


def _surfaces_installed(home: Path) -> bool:
    """Return True when all expected global surfaces are in place.

    Surfaces checked:
      - ~/.claude/CLAUDE.md is a link that resolves, into the cache or outside
        it (a link left dangling when an old plugin version's directory is
        removed, and a file the user wrote, are not installed)
      - ~/.claude/rules/swe/agent-behavioral-contract.md exists
    """
    link = home / _CLAUDE_MD_SUBPATH
    snapshot = snapshot_instructions(link)
    state = classify_instructions(snapshot, str(link.parent))
    working_link = isinstance(state, (CachedRender, ForeignLink)) and snapshot.resolves
    return working_link and (home / _RULES_SENTINEL_SUBPATH).exists()


# ---------------------------------------------------------------------------
# Install steps
# ---------------------------------------------------------------------------


def _run_rule_linker(home: Path, root: Path, function: str) -> None:
    """Run one rule-linking function of the plugin's shell library.

    `function` is `link_rules` (the installer's full link: sweep, then link the
    manifest's `install: symlink` set) or `refresh_rule_symlinks` (sweep, then
    link only the rules that have no working link). The library reads the
    manifest without PyYAML, so the ambient `python3` this hook runs under
    never decides which rules get linked. A plugin without the library or a
    rules directory links nothing.
    """
    _run_rule_linkers(home, root, (function,))


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


def _is_update_run(home: Path, root: Path) -> bool:
    """True when a completed install meets a newer cache version directory.

    The marker says an install ran before and the root lying in a cache version
    directory rules out a checkout (`--plugin-dir`, a clone). Whatever the
    instructions hold, the update path knows what to do with it. The root is
    read lexically, so a root that is itself a link into the cache counts as
    the cache.
    """
    marker = home / ".claude" / _MARKER_FILENAME
    in_cache = cache_version_dir(str(root), str(home / ".claude")) is not None
    return marker.exists() and in_cache


def _run_install(home: Path, values: dict[str, str], root: Path) -> None:
    """Run the full install sequence: render CLAUDE.md, link rules, link scripts."""
    _render_claude_md(home, values, root)
    _link_rules(home, root)
    _link_scripts(home, root)


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


def _perform_install(home: Path, values: dict[str, str], auto_complete: bool, root: Path) -> None:
    """Run the interactive-prompt + install sequence for the cold path.

    When auto_complete is False, prompts the operator (30s timeout-accept).
    On decline writes a soft-decline marker and returns without installing.
    On accept (or auto_complete=True), runs the full install and writes the
    completion marker. A failed install is reported as one, with the command
    that completes it, never as a success.
    """
    if not _confirm_install(home, values, auto_complete):
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
        _report_install_complete()
    else:
        _report_incomplete("Auto-install", failure)


def _run() -> None:
    """Core logic: fast-skip guards, the update path, then the install paths."""
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

    if _is_update_run(home, root):
        _run_update_path(home, root)
        return

    # Surfaces present without an update path (a clone install, or a checkout
    # root): refresh the rule links to this version, then record completion.
    if _surfaces_installed(home):
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
    _perform_install(home, _default_values(), _resolve_mode(), root)


if __name__ == "__main__":
    main()
