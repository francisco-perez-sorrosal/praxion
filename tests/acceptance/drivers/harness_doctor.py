"""The harness's `claude doctor`, as the stand-in `claude` executables answer it.

Doctor starts no session: it reads the configuration directory's `settings.json` and names each
setting it knows whose value has the wrong JSON type, under the setting's dotted path, and says
nothing of a key it does not know. The adherence eval asks it, before a run of a confined kit
writes anything, whether the kit's sandbox settings are taken as written. A stand-in that
answered `doctor` as a session launch would log a launch that never happened, so both stand-ins
hand the call here, and it is never logged.

The known settings are the ones the real doctor recognized on Claude Code 2.1.316: every key a
confined kit's sandbox block uses. Loaded by path from a stand-in, so stdlib only.
"""

from __future__ import annotations

import json
import os
import re
from collections.abc import Iterator, Mapping
from pathlib import Path
from typing import Any

# Each setting the harness knows (a list index read as `N`) and the JSON type it takes.
KNOWN_SETTINGS: Mapping[str, type] = {
    "permissions.blockReadsOutsideWorkingDirectories": bool,
    "sandbox.enabled": bool,
    "sandbox.failIfUnavailable": bool,
    "sandbox.allowUnsandboxedCommands": bool,
    "sandbox.autoAllowBashIfSandboxed": bool,
    "sandbox.network.strictAllowlist": bool,
    "sandbox.filesystem.denyWrite": list,
    "sandbox.filesystem.denyRead": list,
    "sandbox.filesystem.allowRead": list,
    "sandbox.credentials.files.N.path": str,
    "sandbox.credentials.files.N.mode": str,
    "sandbox.credentials.envVars.N.name": str,
    "sandbox.credentials.envVars.N.mode": str,
}


def answer() -> int:
    """Print doctor's report for the configuration directory's settings file; exit status 0."""
    file = Path(os.environ["CLAUDE_CONFIG_DIR"]) / "settings.json"
    lines = [
        f"- {file} › {path}: Expected {KNOWN_SETTINGS[known].__name__}"
        for path, value in _leaves(json.loads(file.read_text(encoding="utf-8")), "")
        if (known := re.sub(r"\.\d+\.", ".N.", path)) in KNOWN_SETTINGS
        and not isinstance(value, KNOWN_SETTINGS[known])
    ]
    print("Claude Code doctor\n" + ("\nInvalid settings\n" + "\n".join(lines) if lines else ""))
    return 0


def _leaves(value: Any, path: str) -> Iterator[tuple[str, Any]]:
    if isinstance(value, dict) and value:
        for key, child in value.items():
            yield from _leaves(child, f"{path}.{key}" if path else key)
    elif isinstance(value, list) and value and all(isinstance(item, dict) for item in value):
        for index, item in enumerate(value):
            yield from _leaves(item, f"{path}.{index}")
    else:
        yield path, value
