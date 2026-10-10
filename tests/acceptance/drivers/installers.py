"""Driver for the installers and gates, reached only through their command lines.

Each run is hermetic: a scratch `HOME`, a scratch target project, no inherited `CLAUDE*`,
`PRAXION_*` or `GIT_*` variable. The Codex installer also reads a personal-info file named by
`PRAXION_PERSONAL_INFO_ENV`; the live-link mode reads the plugin registry under `HOME` and the
working tree named by `PRAXION_DEV_LINK_SOURCE_DIR`.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]


def scrubbed_env(home: Path, **extra: str) -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if not k.startswith(("CLAUDE", "PRAXION_", "GIT_"))}
    env["HOME"] = str(home)
    env.update(extra)
    return env


def snapshot(root: Path) -> dict[str, str]:
    """Every path under `root` with its file content or link target, to prove nothing was written."""
    state = {}
    for path in sorted(root.rglob("*")):
        key = path.relative_to(root).as_posix()
        if path.is_symlink():
            state[key] = f"-> {os.readlink(path)}"
        elif path.is_file():
            state[key] = path.read_text(encoding="utf-8", errors="replace")
        else:
            state[key] = "<dir>"
    return state


def run_cursor_install(
    tmp_path: Path, project: Path, *flags: str
) -> subprocess.CompletedProcess[str]:
    home = tmp_path / "home"
    home.mkdir(exist_ok=True)
    return subprocess.run(
        ["bash", str(REPO_ROOT / "install_cursor.sh"), str(project), *flags],
        cwd=REPO_ROOT, env=scrubbed_env(home), capture_output=True, text=True, timeout=300,
    )  # fmt: skip


def codex_project(tmp_path: Path) -> Path:
    project = tmp_path / "project"
    project.mkdir()
    (project / "CLAUDE.md").write_text(
        "# Demo\n\n## Build / test / lint\n\n- `pytest -q`\n", encoding="utf-8"
    )
    return project


def run_codex_install(
    tmp_path: Path, project: Path, *flags: str
) -> subprocess.CompletedProcess[str]:
    home = tmp_path / "home"
    home.mkdir(exist_ok=True)
    info = tmp_path / "personal_info.env"
    info.write_text(
        "PRAXION_USERNAME=@zz\nPRAXION_EMAIL=zz@example.invalid\nPRAXION_GITHUB_URL=https://github.com/zz\n",
        encoding="utf-8",
    )
    return subprocess.run(
        ["bash", str(REPO_ROOT / "install_codex.sh"), str(project), *flags],
        cwd=REPO_ROOT, env=scrubbed_env(home, PRAXION_PERSONAL_INFO_ENV=str(info)),
        capture_output=True, text=True, timeout=300,
    )  # fmt: skip


def dev_link_home(tmp_path: Path) -> dict[str, Path]:
    """A pinned plugin install whose fetched copy still carries a commands tree, and a checkout."""
    home = tmp_path / "home"
    cache = home / ".claude" / "plugins" / "cache" / "bit-agora" / "praxion" / "0.48.1"
    for surface in ("hooks", "scripts", "skills", "commands"):
        (cache / surface).mkdir(parents=True)
        (cache / surface / "marker.txt").write_text("fetched-copy\n", encoding="utf-8")
    registry = home / ".claude" / "plugins" / "installed_plugins.json"
    registry.write_text(
        json.dumps(
            {
                "plugins": {
                    "praxion@bit-agora": [
                        {"scope": "user", "installPath": str(cache), "version": "0.48.1"}
                    ]
                }
            }
        ),
        encoding="utf-8",
    )
    source = tmp_path / "checkout"
    for surface in (
        "hooks",
        "scripts",
        "skills",
        "commands",
    ):  # a stray tree: the link list decides
        (source / surface).mkdir(parents=True)
        (source / surface / "marker.txt").write_text("checkout-copy\n", encoding="utf-8")
    return {"home": home, "cache": cache, "source": source}


def run_dev_link(paths: dict[str, Path], flag: str) -> subprocess.CompletedProcess[str]:
    env = scrubbed_env(paths["home"], PRAXION_DEV_LINK_SOURCE_DIR=str(paths["source"]))
    return subprocess.run(
        ["bash", str(REPO_ROOT / "install_claude.sh"), "code", flag],
        cwd=REPO_ROOT, env=env, capture_output=True, text=True, timeout=300,
    )  # fmt: skip


def run_gate(script: str, *args: str) -> dict:
    result = subprocess.run(
        ["python3", str(REPO_ROOT / "scripts" / script), *args, "--json"],
        cwd=REPO_ROOT, capture_output=True, text=True, timeout=300,
    )  # fmt: skip
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise AssertionError(
            f"{script} printed no JSON: {result.stdout[-800:]} {result.stderr[-800:]}"
        ) from error


def findings(report: dict, check: str) -> list[dict]:
    return [f for f in report.get("findings", []) if f.get("check") == check]


def write(root: Path, relative: str, text: str) -> None:
    target = root / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")
