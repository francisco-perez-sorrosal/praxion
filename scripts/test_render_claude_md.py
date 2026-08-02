"""Behavioral tests for scripts/render_claude_md.py.

Validates the personal-info substitution helper extracted from install_claude.sh:223.
Covers the public contract committed to by the implementation:
    render_claude_md(template_path: Path, output_path: Path, values: dict[str, str]) -> None
    derive_defaults() -> dict[str, str]

Import strategy: deferred imports inside each test body so pytest collection
succeeds before the implementation exists (BDD/TDD RED handshake). This gives
per-test RED/GREEN resolution rather than a collection-time failure that blocks
all tests.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _load_module():
    """Import render_claude_md lazily (deferred import pattern for RED handshake)."""
    sys.path.insert(0, str(SCRIPTS_DIR))
    import importlib

    import render_claude_md as mod

    return importlib.reload(mod)


def _make_template(tmp_path: Path, content: str) -> Path:
    """Write a template file to a temp directory and return the path."""
    t = tmp_path / "CLAUDE.md.tmpl"
    t.write_text(content, encoding="utf-8")
    return t


def _make_output_path(tmp_path: Path) -> Path:
    return tmp_path / "CLAUDE.md"


# ---------------------------------------------------------------------------
# render_claude_md() — template substitution
# ---------------------------------------------------------------------------


def test_all_three_placeholders_are_substituted(tmp_path):
    """render_claude_md replaces {{USERNAME}}, {{EMAIL}}, and {{GITHUB_URL}}
    with the provided values dict."""
    mod = _load_module()
    tmpl = _make_template(
        tmp_path,
        "# Hello {{USERNAME}}\nEmail: {{EMAIL}}\nGitHub: {{GITHUB_URL}}\n",
    )
    out = _make_output_path(tmp_path)
    mod.render_claude_md(
        tmpl,
        out,
        {
            "USERNAME": "@alice",
            "EMAIL": "alice@example.com",
            "GITHUB_URL": "https://github.com/alice",
        },
    )
    rendered = out.read_text(encoding="utf-8")
    assert "@alice" in rendered
    assert "alice@example.com" in rendered
    assert "https://github.com/alice" in rendered
    assert "{{USERNAME}}" not in rendered
    assert "{{EMAIL}}" not in rendered
    assert "{{GITHUB_URL}}" not in rendered


def test_username_placeholder_replaced_by_value(tmp_path):
    """render_claude_md replaces only {{USERNAME}} when email and github
    are absent from the template."""
    mod = _load_module()
    tmpl = _make_template(tmp_path, "User: {{USERNAME}}\n")
    out = _make_output_path(tmp_path)
    mod.render_claude_md(
        tmpl,
        out,
        {"USERNAME": "@bob", "EMAIL": "b@x.com", "GITHUB_URL": "https://github.com/b"},
    )
    rendered = out.read_text(encoding="utf-8")
    assert "@bob" in rendered
    assert "{{USERNAME}}" not in rendered


def test_output_file_is_created(tmp_path):
    """render_claude_md creates the output file even when the template has
    no placeholders."""
    mod = _load_module()
    tmpl = _make_template(tmp_path, "# Static content\n")
    out = _make_output_path(tmp_path)
    assert not out.exists()
    mod.render_claude_md(tmpl, out, {})
    assert out.exists()


def test_rendering_twice_with_same_inputs_produces_identical_output(tmp_path):
    """render_claude_md is idempotent: calling it twice with the same
    template and values yields byte-identical output both times."""
    mod = _load_module()
    tmpl = _make_template(
        tmp_path,
        "# {{USERNAME}} — {{EMAIL}}\nGitHub: {{GITHUB_URL}}\n",
    )
    values = {
        "USERNAME": "@carol",
        "EMAIL": "carol@c.com",
        "GITHUB_URL": "https://github.com/carol",
    }
    out = _make_output_path(tmp_path)
    mod.render_claude_md(tmpl, out, values)
    first_content = out.read_text(encoding="utf-8")
    mod.render_claude_md(tmpl, out, values)
    second_content = out.read_text(encoding="utf-8")
    assert first_content == second_content, "Second render should produce identical output"


def test_template_content_preserved_outside_placeholders(tmp_path):
    """render_claude_md preserves all non-placeholder content in the template
    verbatim (headings, prose, code blocks)."""
    body = "# My Config\n\n## Section\n\nSome prose here.\n"
    mod = _load_module()
    tmpl = _make_template(tmp_path, body + "{{EMAIL}}\n")
    out = _make_output_path(tmp_path)
    mod.render_claude_md(
        tmpl,
        out,
        {"USERNAME": "x", "EMAIL": "x@x.com", "GITHUB_URL": "https://github.com/x"},
    )
    rendered = out.read_text(encoding="utf-8")
    assert "# My Config" in rendered
    assert "## Section" in rendered
    assert "Some prose here." in rendered


# ---------------------------------------------------------------------------
# render_claude_md() — error / edge cases
# ---------------------------------------------------------------------------


def test_residual_placeholder_logged_to_stderr_not_raised(tmp_path, capsys):
    """When a {{PLACEHOLDER}} pattern survives substitution (key not in values),
    render_claude_md logs a warning to stderr but does NOT raise an exception."""
    mod = _load_module()
    # Template contains {{CUSTOM_KEY}} which is not in values
    tmpl = _make_template(tmp_path, "Hello {{CUSTOM_KEY}}\n")
    out = _make_output_path(tmp_path)
    # Must not raise — exit-0 convention for hook-called utilities
    mod.render_claude_md(
        tmpl,
        out,
        {"USERNAME": "u", "EMAIL": "u@u.com", "GITHUB_URL": "https://github.com/u"},
    )
    captured = capsys.readouterr()
    assert "{{CUSTOM_KEY}}" in captured.err, "Residual placeholder warning should appear on stderr"
    # Output file must still be written (partial substitution is acceptable)
    assert out.exists()


def test_missing_template_raises(tmp_path):
    """render_claude_md raises an appropriate exception when the template
    file does not exist (caller contract: caller must verify template path)."""
    mod = _load_module()
    nonexistent = tmp_path / "missing.tmpl"
    out = _make_output_path(tmp_path)
    with pytest.raises((FileNotFoundError, OSError)):
        mod.render_claude_md(
            nonexistent,
            out,
            {"USERNAME": "x", "EMAIL": "x@x.com", "GITHUB_URL": "https://github.com/x"},
        )


def test_output_directory_created_when_parent_missing(tmp_path):
    """render_claude_md creates missing parent directories for the output
    file rather than failing silently."""
    mod = _load_module()
    tmpl = _make_template(tmp_path, "# {{USERNAME}}\n")
    # Output path whose parent does not yet exist
    out = tmp_path / "nested" / "dir" / "CLAUDE.md"
    mod.render_claude_md(
        tmpl,
        out,
        {
            "USERNAME": "@dave",
            "EMAIL": "d@d.com",
            "GITHUB_URL": "https://github.com/dave",
        },
    )
    assert out.exists()


# ---------------------------------------------------------------------------
# derive_defaults() — git-config present
# ---------------------------------------------------------------------------


def test_derives_username_from_git_email_local_part(tmp_path, monkeypatch):
    """derive_defaults derives USERNAME as @<local-part> of git user.email
    when git config is available."""
    mod = _load_module()

    def fake_git_config(key, **kwargs):
        if "user.email" in key:
            return subprocess.CompletedProcess(
                args=[], returncode=0, stdout="frank@example.com\n", stderr=""
            )
        if "user.name" in key:
            return subprocess.CompletedProcess(args=[], returncode=0, stdout="Frank\n", stderr="")
        return subprocess.CompletedProcess(args=[], returncode=1, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_git_config)
    defaults = mod.derive_defaults()
    # USERNAME is derived from email local-part
    assert "frank" in defaults["USERNAME"].lower()


def test_derives_email_from_git_config(tmp_path, monkeypatch):
    """derive_defaults sets EMAIL to the full git user.email value."""
    mod = _load_module()

    def fake_git_config(key, **kwargs):
        if "user.email" in key:
            return subprocess.CompletedProcess(
                args=[], returncode=0, stdout="greta@work.io\n", stderr=""
            )
        return subprocess.CompletedProcess(args=[], returncode=1, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_git_config)
    defaults = mod.derive_defaults()
    assert defaults["EMAIL"] == "greta@work.io"


def test_derives_github_url_from_email_local_part(tmp_path, monkeypatch):
    """derive_defaults sets GITHUB_URL to https://github.com/<sanitized-username>
    derived from the git config email local-part."""
    mod = _load_module()

    def fake_git_config(key, **kwargs):
        if "user.email" in key:
            return subprocess.CompletedProcess(
                args=[], returncode=0, stdout="hank.smith@corp.com\n", stderr=""
            )
        return subprocess.CompletedProcess(args=[], returncode=1, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_git_config)
    defaults = mod.derive_defaults()
    assert defaults["GITHUB_URL"].startswith("https://github.com/")
    # Sanitized: dots/special chars become dashes or are stripped
    assert "hank" in defaults["GITHUB_URL"].lower()


def test_email_local_part_sanitized_to_safe_slug(monkeypatch):
    """derive_defaults sanitizes the email local-part (strips non-alphanumeric,
    lowercases) when building USERNAME and GITHUB_URL."""
    mod = _load_module()

    def fake_git_config(key, **kwargs):
        if "user.email" in key:
            # Local-part with dots and mixed case
            return subprocess.CompletedProcess(
                args=[], returncode=0, stdout="John.Doe@corp.org\n", stderr=""
            )
        return subprocess.CompletedProcess(args=[], returncode=1, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_git_config)
    defaults = mod.derive_defaults()
    username = defaults["USERNAME"]
    # Must be lowercase
    assert username == username.lower(), "USERNAME must be lowercase"
    # Must not contain uppercase characters
    assert all(c.isalnum() or c in "-@_" for c in username), (
        f"USERNAME contains unexpected characters: {username!r}"
    )


# ---------------------------------------------------------------------------
# derive_defaults() — git-config absent (fallback values)
# ---------------------------------------------------------------------------


def test_falls_back_to_anon_when_git_config_absent(monkeypatch):
    """derive_defaults returns 'anon' fallback values when git config is not
    set or git is not available."""
    mod = _load_module()

    def no_git(key, **kwargs):
        return subprocess.CompletedProcess(
            args=[],
            returncode=1,
            stdout="",
            stderr="error: key does not contain a section\n",
        )

    monkeypatch.setattr(subprocess, "run", no_git)
    defaults = mod.derive_defaults()
    # Fallback contract per SYSTEMS_PLAN interface spec
    assert "anon" in defaults["USERNAME"].lower() or "anon" in defaults["EMAIL"].lower()


def test_fallback_email_is_anon_at_unknown(monkeypatch):
    """derive_defaults uses 'anon@unknown' as EMAIL fallback when git config
    user.email is absent."""
    mod = _load_module()

    def no_git(key, **kwargs):
        return subprocess.CompletedProcess(args=[], returncode=1, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", no_git)
    defaults = mod.derive_defaults()
    assert defaults["EMAIL"] == "anon@unknown"


def test_fallback_github_url_is_anon(monkeypatch):
    """derive_defaults uses https://github.com/anon as GITHUB_URL fallback."""
    mod = _load_module()

    def no_git(key, **kwargs):
        return subprocess.CompletedProcess(args=[], returncode=1, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", no_git)
    defaults = mod.derive_defaults()
    assert defaults["GITHUB_URL"] == "https://github.com/anon"


def test_fallback_values_allow_render_to_complete(tmp_path, monkeypatch):
    """Even with anon fallbacks, render_claude_md completes successfully
    (install is never blocked by absent git config)."""
    mod = _load_module()

    def no_git(key, **kwargs):
        return subprocess.CompletedProcess(args=[], returncode=1, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", no_git)
    defaults = mod.derive_defaults()
    tmpl = _make_template(
        tmp_path,
        "# {{USERNAME}}\nEmail: {{EMAIL}}\nGitHub: {{GITHUB_URL}}\n",
    )
    out = _make_output_path(tmp_path)
    mod.render_claude_md(tmpl, out, defaults)
    rendered = out.read_text(encoding="utf-8")
    assert "anon" in rendered
    assert "{{USERNAME}}" not in rendered
    assert "{{EMAIL}}" not in rendered
    assert "{{GITHUB_URL}}" not in rendered


# ---------------------------------------------------------------------------
# derive_defaults() — returns required keys
# ---------------------------------------------------------------------------


def test_derive_defaults_returns_all_required_keys(monkeypatch):
    """derive_defaults always returns a dict with USERNAME, EMAIL, and
    GITHUB_URL keys regardless of git config state."""
    mod = _load_module()

    def no_git(key, **kwargs):
        return subprocess.CompletedProcess(args=[], returncode=1, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", no_git)
    defaults = mod.derive_defaults()
    assert "USERNAME" in defaults, "derive_defaults must return USERNAME"
    assert "EMAIL" in defaults, "derive_defaults must return EMAIL"
    assert "GITHUB_URL" in defaults, "derive_defaults must return GITHUB_URL"


def test_derive_defaults_returns_nonempty_strings(monkeypatch):
    """derive_defaults never returns empty string values — fallbacks ensure
    meaningful content for every key."""
    mod = _load_module()

    def no_git(key, **kwargs):
        return subprocess.CompletedProcess(args=[], returncode=1, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", no_git)
    defaults = mod.derive_defaults()
    for key, value in defaults.items():
        assert value.strip(), f"derive_defaults returned empty value for {key}"
