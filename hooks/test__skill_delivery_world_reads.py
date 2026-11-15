"""Tests for the reads of the world that ``hooks/_skill_delivery.py`` performs.

Where the scripts directory is found, how an agent definition is decoded and how a skill name is
split out of its frontmatter are mutation-sensor territory. This file imports nothing but the
delivery module, the standard library and pytest, so the sensor can copy it flat beside its target.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

HOOKS_DIR = Path(__file__).resolve().parent
PLUGIN_ROOT = HOOKS_DIR.parent
sys.path.insert(0, str(PLUGIN_ROOT / "scripts"))

import _skill_delivery as delivery  # noqa: E402

ROLE = "implementer"


def write_definition(plugin: Path, text: str) -> None:
    (plugin / "agents").mkdir(parents=True, exist_ok=True)
    (plugin / "agents" / f"{ROLE}.md").write_text(text, encoding="utf-8")


# --- where the scripts directory is found ---------------------------------------------------------


def scripts_dir_of_hook_at(monkeypatch, hook_file: Path) -> Path:
    monkeypatch.setattr(delivery, "__file__", str(hook_file))
    return delivery._scripts_dir()


def test_the_scripts_directory_is_the_one_beside_the_hooks_directory(tmp_path, monkeypatch):
    (tmp_path / "hooks").mkdir()
    (tmp_path / "scripts").mkdir()
    hook = tmp_path / "hooks" / "_skill_delivery.py"

    assert scripts_dir_of_hook_at(monkeypatch, hook) == (tmp_path / "scripts").resolve()


def test_the_scripts_directory_one_level_up_serves_a_hook_copied_one_level_down(
    tmp_path, monkeypatch
):
    (tmp_path / "hooks" / "mutants").mkdir(parents=True)
    (tmp_path / "scripts").mkdir()
    hook = tmp_path / "hooks" / "mutants" / "_skill_delivery.py"

    assert scripts_dir_of_hook_at(monkeypatch, hook) == (tmp_path / "scripts").resolve()


def test_the_nearer_scripts_directory_wins_over_the_one_further_up(tmp_path, monkeypatch):
    (tmp_path / "plugin" / "hooks").mkdir(parents=True)
    (tmp_path / "plugin" / "scripts").mkdir()
    (tmp_path / "scripts").mkdir()
    hook = tmp_path / "plugin" / "hooks" / "_skill_delivery.py"

    assert scripts_dir_of_hook_at(monkeypatch, hook) == (tmp_path / "plugin" / "scripts").resolve()


def test_a_hook_reached_through_a_link_finds_the_scripts_beside_its_real_place(
    tmp_path, monkeypatch
):
    (tmp_path / "real" / "hooks").mkdir(parents=True)
    (tmp_path / "real" / "scripts").mkdir()
    (tmp_path / "linked").mkdir()
    (tmp_path / "linked" / "hooks").symlink_to(tmp_path / "real" / "hooks")
    hook = tmp_path / "linked" / "hooks" / "_skill_delivery.py"

    assert scripts_dir_of_hook_at(monkeypatch, hook) == (tmp_path / "real" / "scripts").resolve()


# --- how an agent definition is read ---------------------------------------------------------------


def test_a_definition_is_read_as_utf8_whatever_the_locale(tmp_path):
    write_definition(
        tmp_path,
        "---\nname: implementer\ndescription: café\nskills: [refactoring]\n---\n",
    )
    probe = (
        "import sys; sys.path.insert(0, sys.argv[1]); sys.path.append(sys.argv[2]); "
        "from pathlib import Path; import _skill_delivery as d; "
        "print(type(d.preload_state(Path(sys.argv[3]), 'implementer')).__name__)"
    )
    ascii_only = {
        **{k: v for k, v in os.environ.items() if not k.startswith(("LC_", "PYTHON"))},
        "LC_ALL": "C",
        "PYTHONUTF8": "0",
        "PYTHONCOERCECLOCALE": "0",
    }

    result = subprocess.run(
        [sys.executable, "-c", probe, str(HOOKS_DIR), str(PLUGIN_ROOT / "scripts"), str(tmp_path)],
        capture_output=True,
        text=True,
        env=ascii_only,
        timeout=30,
    )

    assert result.stdout.strip() == "Preloaded", result.stderr


def test_a_skill_name_keeps_the_letters_that_only_look_like_quotes_to_a_sloppy_strip(tmp_path):
    write_definition(tmp_path, "---\nname: implementer\nskills: [XXrefactoringXX]\n---\n")

    assert delivery.preload_state(tmp_path, ROLE) == delivery.NotPreloaded()


def test_a_definition_is_decoded_as_utf8_in_this_process_where_the_default_is_ascii(
    tmp_path, monkeypatch
):
    """The in-process twin of the locale test above: a copy under the mutation sensor runs it."""
    write_definition(
        tmp_path, "---\nname: implementer\ndescription: café\nskills: [refactoring]\n---\n"
    )

    def read_text_defaulting_to_ascii(self, encoding=None, errors=None):
        return self.read_bytes().decode(encoding or "ascii")

    monkeypatch.setattr(Path, "read_text", read_text_defaulting_to_ascii)

    assert delivery.preload_state(tmp_path, ROLE) == delivery.Preloaded()


# --- how much of a skill file is read --------------------------------------------------------------


class _RecordingFile:
    """A real file that remembers how many bytes each read handed out."""

    def __init__(self, real_file, handed_out: list[int]):
        self._real_file = real_file
        self._handed_out = handed_out

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        self._real_file.close()

    def read(self, size=-1):
        data = self._real_file.read(size)
        self._handed_out.append(len(data))
        return data


def test_an_oversize_skill_file_is_read_no_further_than_one_byte_past_the_limit(
    tmp_path, monkeypatch
):
    skill_dir = tmp_path / "refactoring"
    (skill_dir / "references").mkdir(parents=True)
    (skill_dir / "references" / "patterns.md").write_text("patterns\n", encoding="utf-8")
    (skill_dir / "SKILL.md").write_bytes(b"-" * (delivery.MAX_SKILL_BYTES * 2))
    handed_out: list[int] = []
    real_open = open
    monkeypatch.setattr(
        delivery,
        "open",
        lambda path, mode: _RecordingFile(real_open(path, mode), handed_out),
        raising=False,
    )

    assert delivery._read_body_unbounded(skill_dir) == delivery.BodyUnreadable("skill-unreadable")
    assert handed_out == [delivery.MAX_SKILL_BYTES + 1]
