"""SessionStart hook: auto-complete marketplace install on first session.

Closes the install-path asymmetry between clone-install and marketplace-install
by detecting missing global surfaces on first session and completing them without
requiring the operator to run /praxion-complete-install manually.

Fast-skip conditions (exit 0, silent):
  (1) Marker file ~/.claude/.praxion-complete-installed exists
      AND marker mtime >= plugin cache directory mtime (post-update rearm)
  (2) PRAXION_DISABLE_AUTO_COMPLETE=1 is set

Otherwise (cold path):
  - Check whether all surfaces are already present (CLAUDE.md symlink + rules
    sentinel). If present: write marker and exit 0 (no install needed).
  - Otherwise: derive personal-info defaults, optionally prompt the operator
    (30s timeout-accept), run install steps, write marker.

Non-interactive auto-accept:
  - PRAXION_AUTO_COMPLETE=1 set: skip prompt, use defaults.
  - stdin is EOF immediately (piped/redirected): treat as timeout-accept.

Exit 0 unconditionally — this hook must NEVER block session start.
"""

from __future__ import annotations

import os
import signal
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Path bootstrap: inject scripts/ so render_claude_md is importable
# without PYTHONPATH being set.
# ---------------------------------------------------------------------------

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
import render_claude_md as _render_mod  # noqa: E402 (after sys.path injection)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DISABLE_AUTO_COMPLETE = "PRAXION_DISABLE_AUTO_COMPLETE"
_AUTO_COMPLETE_FLAG = "PRAXION_AUTO_COMPLETE"

_TRUTHY = frozenset({"1", "true", "yes"})

_MARKER_FILENAME = ".praxion-complete-installed"
_DECLINE_MARKER_FILENAME = ".praxion-install-declined"

_PLUGIN_CACHE_SUBPATH = Path(".claude") / "plugins" / "cache" / "bit-agora" / "i-am"
_RULES_SENTINEL_SUBPATH = (
    Path(".claude") / "rules" / "swe" / "agent-behavioral-contract.md"
)
_CLAUDE_MD_SUBPATH = Path(".claude") / "CLAUDE.md"

# Template is inside the plugin cache directory
_TEMPLATE_RELATIVE = Path("claude") / "config" / "CLAUDE.md.tmpl"

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
      - ~/.claude/CLAUDE.md exists AND is a symlink
      - ~/.claude/rules/swe/agent-behavioral-contract.md exists
    """
    claude_md = home / _CLAUDE_MD_SUBPATH
    rules_sentinel = home / _RULES_SENTINEL_SUBPATH
    return claude_md.is_symlink() and rules_sentinel.exists()


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


def _render_claude_md(home: Path, values: dict[str, str]) -> None:
    """Render ~/.claude/CLAUDE.md from the plugin cache template.

    Finds the template in the plugin cache, renders it into a real file
    in the plugin cache's config dir, then symlinks ~/.claude/CLAUDE.md
    to that rendered file.  Raises on any I/O error.
    """
    plugin_cache = home / _PLUGIN_CACHE_SUBPATH
    template_path = plugin_cache / _TEMPLATE_RELATIVE
    rendered_path = plugin_cache / "claude" / "config" / "CLAUDE.md"

    _render_mod.render_claude_md(template_path, rendered_path, values)

    claude_md_link = home / _CLAUDE_MD_SUBPATH
    claude_md_link.parent.mkdir(parents=True, exist_ok=True)
    if claude_md_link.exists() or claude_md_link.is_symlink():
        claude_md_link.unlink()
    claude_md_link.symlink_to(rendered_path)


def _load_hook_deliver_set(rules_src: Path) -> frozenset[Path] | None:
    """Return the set of rule paths (relative to rules_src) with install: hook-deliver.

    Reads rules/_manifest.yaml from the plugin cache.  Returns None when the manifest
    is missing or unparseable, signalling the caller to fall back to linking all files.
    """
    import yaml  # third-party PyYAML; declared in pyproject.toml dev group

    manifest_path = rules_src / "_manifest.yaml"
    if not manifest_path.exists():
        return None

    try:
        raw = manifest_path.read_text(encoding="utf-8")
        data = yaml.safe_load(raw)
        if not isinstance(data, dict) or "rules" not in data:
            return None
        hook_deliver: set[Path] = set()
        for entry in data["rules"]:
            if isinstance(entry, dict) and entry.get("install") == "hook-deliver":
                rule_path = entry.get("path", "")
                # path field is relative to repo root (e.g. "rules/swe/memory-protocol.md")
                # Strip the leading "rules/" prefix to get path relative to rules_src
                if rule_path.startswith("rules/"):
                    hook_deliver.add(Path(rule_path[len("rules/") :]))
        return frozenset(hook_deliver)
    except Exception:
        return None


_SKIP_NAMES = frozenset({"README.md", "_manifest.yaml"})
_REFERENCES_SEGMENT = "references"


def _should_skip_rule(rel_path: Path) -> bool:
    """Return True for files that should never be symlinked as rules.

    Skips README.md, _manifest.yaml, and anything under a references/ directory.
    Matches the filter applied by lib/install_shared.sh link_rules().
    """
    if rel_path.name in _SKIP_NAMES:
        return True
    return _REFERENCES_SEGMENT in rel_path.parts


def _link_rules(home: Path) -> None:
    """Symlink ~/.claude/rules/ entries from the plugin cache rules directory.

    Switches from directory-level to per-file symlinking so that manifest-based
    filtering (install: hook-deliver) can exclude individual rule files.
    Rules with install: hook-deliver are delivered by inject_rules.py at session
    start instead; symlinking them here would defeat the blacklist mechanism.

    Fall-back: if the manifest is missing or unparseable, all .md files are
    linked (preserves backward compatibility with pre-manifest installs).

    Idempotency: stale symlinks that now map to hook-deliver files are removed
    so a re-install cleans up entries from previous installs.
    """
    plugin_cache = home / _PLUGIN_CACHE_SUBPATH
    rules_src = plugin_cache / "rules"
    rules_dest = home / ".claude" / "rules"

    if not rules_src.is_dir():
        return

    rules_dest.mkdir(parents=True, exist_ok=True)

    hook_deliver = _load_hook_deliver_set(rules_src)
    # None means manifest missing/unparseable → link everything (backward compat)
    manifest_available = hook_deliver is not None

    for rule_file in sorted(rules_src.rglob("*.md")):
        rel = rule_file.relative_to(rules_src)
        if _should_skip_rule(rel):
            continue

        dest_file = rules_dest / rel
        dest_file.parent.mkdir(parents=True, exist_ok=True)

        if manifest_available and rel in hook_deliver:
            # This file is now hook-delivered — remove any stale symlink from
            # a previous install that linked it directly
            if dest_file.is_symlink():
                dest_file.unlink()
            continue

        if dest_file.is_symlink():
            dest_file.unlink()
        dest_file.symlink_to(rule_file)


def _link_scripts(home: Path) -> None:
    """Symlink user-facing scripts from the plugin cache into ~/.local/bin/."""
    plugin_cache = home / _PLUGIN_CACHE_SUBPATH
    scripts_src = plugin_cache / "scripts"
    bin_dest = home / ".local" / "bin"

    if not scripts_src.is_dir():
        return

    bin_dest.mkdir(parents=True, exist_ok=True)

    for script in scripts_src.iterdir():
        if not script.is_file() or not os.access(script, os.X_OK):
            continue
        name = script.name
        if name.startswith("merge_driver_") or name.endswith("-hook.sh"):
            continue
        dest = bin_dest / name
        if dest.is_symlink():
            dest.unlink()
        dest.symlink_to(script)


def _run_install(home: Path, values: dict[str, str]) -> None:
    """Run the full install sequence: render CLAUDE.md, link rules, link scripts."""
    _render_claude_md(home, values)
    _link_rules(home)
    _link_scripts(home)


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


def _perform_install(home: Path, values: dict[str, str], auto_complete: bool) -> None:
    """Run the interactive-prompt + install sequence for the cold path.

    When auto_complete is False, prompts the operator (30s timeout-accept).
    On decline writes a soft-decline marker and returns without installing.
    On accept (or auto_complete=True), runs the full install and writes the
    completion marker.
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

    # Run install steps (each failure is swallowed; marker still written)
    try:
        _run_install(home, values)
    except Exception:
        pass

    # Write completion marker regardless of install success
    try:
        _write_marker(home)
    except Exception:
        pass

    sys.stderr.write("[Praxion] Auto-install complete.\n")
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

    # Surfaces present (CLAUDE.md symlink + rules sentinel): write marker, done
    if _surfaces_present(home):
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

    _perform_install(home, values, _resolve_mode())


if __name__ == "__main__":
    main()
