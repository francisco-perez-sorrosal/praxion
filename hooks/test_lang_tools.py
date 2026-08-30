"""Tests for hooks/_lang_tools.py — the extension-to-toolchain registry.

Two groups:
  - Registry invariants: every row is complete-or-absent (per the module's own
    legal-state contract), and the import-time `_assert_registry_is_legal()`
    assertion actually fires on a malformed row rather than merely documenting
    the invariant.
  - The Rust `--edition` resolver contract (`resolve_rust_edition`): reads the
    edition from the nearest `rustfmt.toml`, falls back to the nearest
    `Cargo.toml`, and defaults to `"2024"` when neither declares one. This
    function does not exist yet -- these three tests are the RED-first
    interface contract the Step 4 implementer must satisfy (per the BDD/TDD
    pairing rule, the test-engineer's canary defines the shape of the
    to-be-built argv builder's edition resolution).
"""

from __future__ import annotations

from pathlib import Path

import _lang_tools
import pytest
from _lang_tools import LangTool

# ---------------------------------------------------------------------------
# Registry invariants (parametrized over the live registry -- these grow
# automatically to cover the `.rs` row once Step 4 adds it, with no edit here)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("extension", "entry"),
    list(_lang_tools.LANG_TOOLS.items()),
    ids=list(_lang_tools.LANG_TOOLS.keys()),
)
def test_registry_key_starts_with_a_dot(extension: str, entry: LangTool) -> None:
    """Every registry key is a dotted extension -- never a bare suffix."""
    assert extension.startswith("."), f"registry key {extension!r} must start with '.'"


@pytest.mark.parametrize(
    ("extension", "entry"),
    list(_lang_tools.LANG_TOOLS.items()),
    ids=list(_lang_tools.LANG_TOOLS.keys()),
)
def test_resolver_returns_a_complete_argv_prefix_or_none(extension: str, entry: LangTool) -> None:
    """`resolve()` returns a full argv prefix, or `None` -- never a partial list.

    `None` means "tool absent on this machine" (a silent no-op for every
    consumer); anything else must be usable as a subprocess argv prefix as-is.
    """
    result = entry.resolve()
    assert result is None or (isinstance(result, list) and len(result) > 0)


def _valid_resolve() -> list[str] | None:
    return None


def _valid_build_format_argv(prefix, file_path):
    return [*prefix, file_path]


MALFORMED_REGISTRIES = {
    "key-missing-leading-dot": {
        "py": LangTool(
            extension="py",
            tool_name="ruff",
            resolve=_valid_resolve,
            build_format_argv=_valid_build_format_argv,
        ),
    },
    "extension-disagrees-with-key": {
        ".py": LangTool(
            extension=".rs",
            tool_name="ruff",
            resolve=_valid_resolve,
            build_format_argv=_valid_build_format_argv,
        ),
    },
    "empty-tool-name": {
        ".py": LangTool(
            extension=".py",
            tool_name="",
            resolve=_valid_resolve,
            build_format_argv=_valid_build_format_argv,
        ),
    },
    "non-callable-resolve": {
        ".py": LangTool(
            extension=".py",
            tool_name="ruff",
            resolve=None,  # type: ignore[arg-type]
            build_format_argv=_valid_build_format_argv,
        ),
    },
    "non-callable-build-format-argv": {
        ".py": LangTool(
            extension=".py",
            tool_name="ruff",
            resolve=_valid_resolve,
            build_format_argv=None,  # type: ignore[arg-type]
        ),
    },
}


@pytest.mark.parametrize(
    "registry",
    list(MALFORMED_REGISTRIES.values()),
    ids=list(MALFORMED_REGISTRIES.keys()),
)
def test_assert_registry_is_legal_rejects_a_malformed_row(
    registry: dict[str, LangTool], monkeypatch: pytest.MonkeyPatch
) -> None:
    """The import-time legality assertion fires on every malformed row shape.

    Proves the invariant is enforced, not just documented in a docstring: a
    partially-populated entry must be a loud `AssertionError` at import time,
    never a silent misdispatch discovered later at runtime.
    """
    monkeypatch.setattr(_lang_tools, "LANG_TOOLS", registry)

    with pytest.raises(AssertionError):
        _lang_tools._assert_registry_is_legal()


# ---------------------------------------------------------------------------
# Rust `--edition` resolution (RED -- `resolve_rust_edition` does not exist
# yet; Step 4 adds it alongside the `.rs` registry row)
# ---------------------------------------------------------------------------


def test_resolves_edition_from_nearest_rustfmt_toml(tmp_path: Path) -> None:
    """The edition is read from the nearest `rustfmt.toml`'s `edition` key."""
    project = tmp_path / "proj"
    src = project / "src"
    src.mkdir(parents=True)
    (project / "rustfmt.toml").write_text('edition = "2021"\n', encoding="utf-8")
    target = src / "lib.rs"
    target.write_text("fn f() {}\n", encoding="utf-8")

    edition = _lang_tools.resolve_rust_edition(str(target))

    assert edition == "2021"


def test_resolves_edition_from_nearest_cargo_toml_when_no_rustfmt_toml(
    tmp_path: Path,
) -> None:
    """Absent a `rustfmt.toml`, the edition falls back to `Cargo.toml`'s."""
    project = tmp_path / "proj"
    src = project / "src"
    src.mkdir(parents=True)
    (project / "Cargo.toml").write_text(
        '[package]\nname = "demo"\nedition = "2018"\n', encoding="utf-8"
    )
    target = src / "lib.rs"
    target.write_text("fn f() {}\n", encoding="utf-8")

    edition = _lang_tools.resolve_rust_edition(str(target))

    assert edition == "2018"


def test_defaults_to_2024_when_neither_config_file_declares_an_edition(
    tmp_path: Path,
) -> None:
    """No `rustfmt.toml`, no `Cargo.toml` anywhere above the file: default `2024`."""
    target = tmp_path / "orphan.rs"
    target.write_text("fn f() {}\n", encoding="utf-8")

    edition = _lang_tools.resolve_rust_edition(str(target))

    assert edition == "2024"
