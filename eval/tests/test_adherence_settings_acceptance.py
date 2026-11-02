"""The no-cost check that the harness takes a confined kit's sandbox settings as written.

A stand-in ``claude doctor`` answers in the real one's report shape from a small schema: it
reports a known setting of the wrong type and passes over a key it does not know, as the real
doctor does (read on Claude Code 2.1.316). That second behaviour is why the check gives every
value a wrong type: these tests prove an unknown key is caught, and that a doctor whose report
cannot be read refuses rather than accepts.
"""

from __future__ import annotations

import json
import os
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from praxion_evals.adherence import cli, session_loop, settings_acceptance
from praxion_evals.adherence.settings_acceptance import (
    Reported,
    leaf_paths,
    refuse_unaccepted_settings,
    reported_for,
    unaccepted,
)
from tests.adherence_run_support import ROLE, Script, scripted_checkout

KIT_SHAPED = {
    "permissions": {"blockReadsOutsideWorkingDirectories": True},
    "sandbox": {
        "enabled": True,
        "network": {"strictAllowlist": True},
        "filesystem": {"denyRead": ["/real/home"], "allowRead": []},
        "credentials": {"files": [{"path": "/real/home/.ssh", "mode": "deny"}]},
    },
}
KIT_LEAVES = (
    "permissions.blockReadsOutsideWorkingDirectories",
    "sandbox.enabled",
    "sandbox.network.strictAllowlist",
    "sandbox.filesystem.denyRead",
    "sandbox.filesystem.allowRead",
    "sandbox.credentials.files.0.path",
    "sandbox.credentials.files.0.mode",
)

# The stand-in's schema: each known setting's path (a list index read as `N`) and its type.
_STAND_IN = r"""
import json, os, re, sys
from pathlib import Path

SCHEMA = {
    "permissions.blockReadsOutsideWorkingDirectories": "boolean",
    "sandbox.enabled": "boolean",
    "sandbox.network.strictAllowlist": "boolean",
    "sandbox.filesystem.denyRead": "array",
    "sandbox.filesystem.allowRead": "array",
    "sandbox.credentials.files.N.path": "string",
    "sandbox.credentials.files.N.mode": "deny|mask",
}
KINDS = {"boolean": bool, "array": list, "string": str}

def leaves(value, path):
    if isinstance(value, dict) and value:
        for key, child in value.items():
            yield from leaves(child, f"{path}.{key}" if path else key)
    elif isinstance(value, list) and value and all(isinstance(v, dict) for v in value):
        for index, item in enumerate(value):
            yield from leaves(item, f"{path}.{index}")
    else:
        yield path, value

Path(RECORD).write_text(json.dumps({"argv": sys.argv[1:], "env": dict(os.environ)}))
if MODE == "fails":
    sys.exit(3)
print("Claude Code doctor\n\nRunning: native (9.9.9)")
if MODE == "silent":
    sys.exit(0)
file = Path(os.environ["CLAUDE_CONFIG_DIR"]) / "settings.json"
lines = []
for path, value in leaves(json.loads(file.read_text()), ""):
    kind = SCHEMA.get(re.sub(r"\.\d+\.", ".N.", path))
    if kind is None:
        continue  # an unknown key: the real doctor says nothing of it either
    if "|" in kind and value not in kind.split("|"):
        lines.append(f"- {file} › {path}: Invalid value. Expected one of: {kind}")
    elif "|" not in kind and not isinstance(value, KINDS[kind]):
        lines.append(f"- {file} › {path}: Expected {kind}, but received something else")
        lines.append("  Suggested fix: Use true or false without quotes.")
if lines:
    print("\nInvalid settings\n" + "\n".join(lines))
print("\n2 warnings found")
"""


def stand_in_doctor(directory: Path, mode: str = "reads") -> tuple[Path, Path]:
    """A `claude` whose `doctor` answers in the real report shape; and where it records its call."""
    directory.mkdir(parents=True, exist_ok=True)
    binary, record = directory / "claude", directory / "doctor-call.json"
    header = f"#!{sys.executable}\nMODE = {mode!r}\nRECORD = {str(record)!r}\n"
    binary.write_text(header + _STAND_IN, encoding="utf-8")
    binary.chmod(0o755)
    return binary, record


def with_key(settings: dict[str, Any], section: str, key: str, value: object) -> dict[str, Any]:
    changed = json.loads(json.dumps(settings))
    changed[section][key] = value
    return changed


def test_settings_the_harness_knows_and_types_rightly_are_accepted(tmp_path: Path) -> None:
    binary, _ = stand_in_doctor(tmp_path / "bin")

    assert unaccepted(KIT_SHAPED, tmp_path / "scratch", str(binary)) == ()


def test_a_key_the_harness_does_not_know_is_named_as_dropped(tmp_path: Path) -> None:
    binary, _ = stand_in_doctor(tmp_path / "bin")
    planted = with_key(KIT_SHAPED, "sandbox", "bogusCanaryKey", True)

    found = unaccepted(planted, tmp_path / "scratch", str(binary))

    assert found == ("the harness does not know `sandbox.bogusCanaryKey` and would drop it",)


def test_a_known_setting_of_the_wrong_type_is_named_as_rejected(tmp_path: Path) -> None:
    binary, _ = stand_in_doctor(tmp_path / "bin")
    mistyped = with_key(KIT_SHAPED, "sandbox", "enabled", "yes")

    found = unaccepted(mistyped, tmp_path / "scratch", str(binary))

    assert found == (
        "the harness rejects `sandbox.enabled`: Expected boolean, but received something else",
    )


def test_a_doctor_report_that_cannot_be_read_leaves_every_setting_unknown(tmp_path: Path) -> None:
    binary, _ = stand_in_doctor(tmp_path / "bin", mode="silent")

    found = unaccepted(KIT_SHAPED, tmp_path / "scratch", str(binary))

    assert found == tuple(
        f"the harness does not know `{path}` and would drop it" for path in KIT_LEAVES
    )


def test_a_doctor_that_ends_in_error_refuses_rather_than_accepts(tmp_path: Path) -> None:
    binary, _ = stand_in_doctor(tmp_path / "bin", mode="fails")

    found = unaccepted(KIT_SHAPED, tmp_path / "scratch", str(binary))

    assert len(found) == 1, found
    assert found[0].startswith(f"`{binary} doctor` exited 3"), found


def test_a_doctor_that_cannot_be_started_refuses_rather_than_accepts(tmp_path: Path) -> None:
    missing = tmp_path / "no-such" / "claude"

    found = unaccepted(KIT_SHAPED, tmp_path / "scratch", str(missing))

    assert len(found) == 1, found
    assert found[0].startswith(f"`{missing} doctor` did not run"), found


def test_doctor_runs_with_no_credential_and_a_scratch_home(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "must-not-reach-doctor")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "must-not-reach-doctor")
    binary, record = stand_in_doctor(tmp_path / "bin")

    unaccepted(KIT_SHAPED, tmp_path / "scratch", str(binary))
    call = json.loads(record.read_text())

    assert call["argv"] == ["doctor"]
    assert not {"CLAUDE_CODE_OAUTH_TOKEN", "ANTHROPIC_API_KEY"} & set(call["env"])
    assert Path(call["env"]["HOME"]).is_relative_to(tmp_path / "scratch")


def test_report_lines_are_read_for_the_file_under_either_spelling(tmp_path: Path) -> None:
    real = tmp_path / "real"
    real.mkdir()
    (tmp_path / "linked").symlink_to(real)
    file = tmp_path / "linked" / "settings.json"
    output = "\n".join(
        [
            "Invalid settings",
            f"- {real / 'settings.json'} › sandbox.enabled: Expected boolean",
            "  Suggested fix: Use true or false without quotes.",
            f"- {file}: Invalid or malformed JSON",
            f"- {tmp_path / 'other.json'} › sandbox.enabled: Expected boolean",
        ]
    )

    assert reported_for(file, output) == (
        Reported("sandbox.enabled", "Expected boolean"),
        Reported("", "Invalid or malformed JSON"),
    )


def test_leaf_paths_index_records_and_keep_plain_lists_whole() -> None:
    assert leaf_paths(KIT_SHAPED) == KIT_LEAVES


def test_a_run_naming_no_confined_kit_starts_no_doctor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    binary, record = stand_in_doctor(tmp_path / "bin")
    monkeypatch.setenv("PATH", f"{binary.parent}{os.pathsep}{os.environ['PATH']}")

    refuse_unaccepted_settings(["researcher"], None)

    assert not record.exists()


def test_a_confined_kit_whose_settings_hold_an_unknown_key_refuses_the_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    binary, _ = stand_in_doctor(tmp_path / "bin")
    monkeypatch.setenv("PATH", f"{binary.parent}{os.pathsep}{os.environ['PATH']}")
    planted = with_key(KIT_SHAPED, "sandbox", "bogusCanaryKey", True)
    monkeypatch.setattr(settings_acceptance, "kit_settings", lambda role, token_file: planted)

    with pytest.raises(ValueError, match=r"implementer: .*`sandbox\.bogusCanaryKey`"):
        refuse_unaccepted_settings(["implementer", "researcher"], None)


def test_a_run_whose_settings_are_refused_writes_nothing_and_launches_nothing(
    paid: Callable[[Script], None], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    script = Script()
    paid(script)

    def refused(roles: object, token_file: object) -> None:
        raise ValueError("the harness would not take the settings")

    monkeypatch.setattr(session_loop, "refuse_unaccepted_settings", refused)

    code = cli.main(
        [str(scripted_checkout()), "--role", ROLE, "--output", str(tmp_path / "o.json")]
    )

    assert code == 2
    assert not (tmp_path / "o.json").exists()
    assert script.specs == []
