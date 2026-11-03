"""Readings over the whole checkout for project gating, and the freezing of today's readings.

The always-loaded budget command (`measure_token_budget.py --json --repo-root <dir>`) under a
scratch install, every Codex and Cursor export by digest with the checkout's location
normalised out, the generated kernels by digest, and `freeze`, which writes every fixture under
`tests/acceptance/fixtures/project_gating/` from a tree that must be the pipeline base.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

from tests.acceptance.drivers.kernel_sandbox import isolated_env
from tests.acceptance.drivers.process_text_oracles import (
    CONSTITUTION_TEXTS,
    FIXTURES,
    MANAGED_ONLY_TEXTS,
    REPO_ROOT,
    USER_INSTRUCTIONS,
    mask,
    unit_file,
)
from tests.acceptance.drivers.scratch_projects import (
    copy_home,
    installed_home,
    plugin_root,
    project_with_current_instructions,
    repository,
    shipped_instructions,
    write_blacklist,
)
from tests.acceptance.drivers.session_start_text import (
    HEADLESS,
    HOST_NATIVE,
    INHERITING_ROLE,
    INTERACTIVE,
    LEAN_ROLE,
    Machine,
    session_start,
    spawn_start,
)

# -- Readings over the whole checkout ---------------------------------------------------------------


def budget_reading(machine: Machine, directory: Path) -> tuple[int, dict]:
    """`measure_token_budget.py --json --repo-root <directory>` under the scratch install."""
    env = isolated_env(machine.sandbox / ".budget")
    env["HOME"] = str(machine.home)
    result = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts" / "measure_token_budget.py"),
            "--json",
            "--repo-root",
            str(directory),
        ],
        cwd=directory,
        env=env,
        capture_output=True,
        text=True,
        timeout=600,
    )
    assert result.returncode in (0, 1), result.stdout[-2000:] + result.stderr[-2000:]
    return result.returncode, json.loads(result.stdout)


def counted_text(reading: dict) -> str:
    """The text of every file the always-loaded reading counts."""
    return "\n\n".join(Path(f).read_text(encoding="utf-8") for f in reading["files"])


EXPORTERS = (
    ("codex-agents", "codex/config/export-codex-agents.py"),
    ("codex-adapter", "codex/config/export-codex-pipeline-adapter.py"),
    ("codex-bridge", "codex/config/export-codex-rules-bridge.py"),
    ("codex-skills", "codex/config/export-codex-skills.py"),
)


def export_digests(scratch: Path) -> dict[str, str]:
    """Every file the Codex and Cursor exporters write from this checkout, by digest, with the
    checkout's location and the output location normalised out."""
    found: dict[str, str] = {}
    runs = [
        (name, [script, "--repo-root", str(REPO_ROOT), "--out-dir", "{out}"])
        for name, script in EXPORTERS
    ]
    runs.append(("cursor", ["cursor/config/export-cursor-rules.py", str(REPO_ROOT), "{out}"]))
    for name, argv in runs:
        out = scratch / name
        env = isolated_env(scratch / f".{name}-env")
        result = subprocess.run(
            [
                sys.executable,
                str(REPO_ROOT / argv[0]),
                *(a.replace("{out}", str(out)) for a in argv[1:]),
            ],
            cwd=REPO_ROOT,
            env=env,
            capture_output=True,
            text=True,
            timeout=600,
        )
        assert result.returncode == 0, (
            f"{name} export failed: {result.stdout[-1000:]}{result.stderr[-1000:]}"
        )
        for path in sorted(out.rglob("*")):
            if path.is_file():
                data = path.read_bytes()
                for root, token in ((REPO_ROOT, b"<repo>"), (out, b"<out>")):
                    for form in {str(root), str(root.resolve())}:
                        data = data.replace(form.encode(), token)
                found[f"{name}/{path.relative_to(out)}"] = hashlib.sha256(data).hexdigest()
    return found


def kernel_digests() -> dict[str, str]:
    kernels = REPO_ROOT / "claude" / "kernels"
    files = [*sorted(kernels.glob("*.md")), kernels / "index.json"]
    return {f.name: hashlib.sha256(f.read_bytes()).hexdigest() for f in files}


# -- Freezing --------------------------------------------------------------------------------------


def base_readings(scratch: Path) -> dict[str, str]:
    """Today's readings the scenarios compare with, masked: name -> text."""
    template = installed_home(scratch / "install")
    readings: dict[str, str] = {}

    def machine(name: str) -> Machine:
        sandbox = scratch / name
        sandbox.mkdir()
        return Machine(
            copy_home(template, sandbox / "home"), plugin_root(sandbox / "plugin"), sandbox
        )

    m = machine("managed")
    project = repository(m.sandbox / "project", state_marker="root gating fixture")
    for entry in (INTERACTIVE, HEADLESS):
        readings[f"managed-main-{entry}"] = mask(
            session_start(m, project, entrypoint=entry).process_text, m.tokens()
        )
    for kind in ("off", "injection-off"):
        readings[f"managed-main-hooks-{kind}"] = mask(
            session_start(m, project, hooks=kind).process_text, m.tokens()
        )
    for agent in (f"praxion:{INHERITING_ROLE}", HOST_NATIVE, f"praxion:{LEAN_ROLE}"):
        readings[f"managed-spawn-{agent}"] = mask(
            spawn_start(m, project, agent).process_text, m.tokens()
        )
    m = machine("onboarded")
    onboarded = project_with_current_instructions(m.sandbox / "onboarded")
    readings["project-CLAUDE.md"] = shipped_instructions()
    readings["managed-main-onboarded"] = mask(session_start(m, onboarded).process_text, m.tokens())
    m = machine("blacklisted")
    plain = m.sandbox / "plain"
    plain.mkdir()
    write_blacklist(plain, BLACKLIST_PATTERNS)
    started = session_start(m, plain)
    readings["unmanaged-blacklist-writes"] = json.dumps(
        {k: [mask(str(v), m.tokens()) for v in pair] for k, pair in started.writes.items()}
    )
    settings = plain / ".claude" / "settings.json"
    readings["unmanaged-blacklist-settings"] = mask(
        settings.read_text(encoding="utf-8") if settings.exists() else "", m.tokens()
    )
    readings["unmanaged-blacklist-warnings"] = "\n".join(
        line for line in mask(started.warnings, m.tokens()).splitlines() if CORE_RULE in line
    )
    m = machine("budget")
    budget_project = repository(m.sandbox / "budget-project", managed=True)
    _, reading = budget_reading(m, budget_project)
    readings["managed-budget-text"] = mask(counted_text(reading), m.tokens())
    return readings


BLACKLIST_PATTERNS = [
    "swe/vcs/git-conventions",
    "swe/coding-style",
    "swe/agent-behavioral-contract",
]
CORE_RULE = "swe/agent-behavioral-contract"


def freeze(scratch: Path) -> None:
    """Write every fixture from this tree, which must be the pipeline base."""
    units = FIXTURES / "base_units"
    units.mkdir(parents=True, exist_ok=True)
    for unit, rel in {**MANAGED_ONLY_TEXTS, **CONSTITUTION_TEXTS}.items():
        if rel == "user CLAUDE.md":
            continue
        (units / unit_file(unit)).write_bytes((REPO_ROOT / rel).read_bytes())
    readings = base_readings(scratch)
    home_claude = scratch / "install" / "home" / ".claude" / "CLAUDE.md"
    (units / unit_file(USER_INSTRUCTIONS)).write_text(
        mask(home_claude.read_text(encoding="utf-8"), {}), encoding="utf-8"
    )
    (FIXTURES / "base_project_CLAUDE.md").write_text(
        readings.pop("project-CLAUDE.md"), encoding="utf-8"
    )
    (FIXTURES / "base_readings.json").write_text(
        json.dumps(readings, indent=1, sort_keys=True) + "\n", encoding="utf-8"
    )
    (FIXTURES / "base_exports.json").write_text(
        json.dumps(export_digests(scratch / "exports"), indent=1, sort_keys=True) + "\n"
    )
    (FIXTURES / "base_kernels.json").write_text(
        json.dumps(kernel_digests(), indent=1, sort_keys=True) + "\n"
    )
