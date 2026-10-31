"""Driver for the landed adr-conventions move: what ships, measured against what was measured.

The frozen fixtures under `tests/acceptance/fixtures/adr_rule_move/` were taken with `freeze`
from the tree as it stood at the pipeline base, so the scenarios compare like with like without
reading git history:

- `measured_rule.md`, `measured_resident.md`, `measured_rows.json`: the measured lean arm's rule,
  resident file and the two manifest rows, built by the move instrument over that tree;
- `base_rule.md`, `base_row.json`: the rule and its manifest row at the base;
- `base_kernels.json`: each generated role kernel and the kernel index, by digest;
- `base_cursor.json`: each Cursor export file, by digest;
- `base_codex.json`: the Codex bridge's always-on rule ids, the rule paths its manifest lists and
  its session-start pointer text, with the repository root written `<repo>`;
- `base_budget_files.json`: the files the always-loaded budget reading counts.

Observations run hermetically: a scratch HOME, a `claude` stand-in first on PATH that records
its arguments and exits 1 (so no session can start), and no inherited `CLAUDE*`, `PRAXION_*`,
`GIT_*` or `ANTHROPIC_*` variable (`kernel_sandbox.isolated_env`).

Nothing here is unbound.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import yaml

from tests.acceptance.drivers.kernel_sandbox import isolated_env

REPO_ROOT = Path(__file__).resolve().parents[3]
FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "adr_rule_move"
MOVED_RULE = "rules/swe/adr-conventions.md"
RESIDENT = "rules/swe/adr-conventions-resident.md"
RULE_IDS = ("swe/adr-conventions", "swe/adr-conventions-resident")
MANIFEST = "rules/_manifest.yaml"
_GENERATED_ROW_ORDER = ("id", "path", "load", "core", "install", "paths", "chars")
PATH_SCOPE = ".ai-state/decisions/**"
RESIDENT_TITLE = "## ADR Conventions"
MEASURED_KEYS = ("id", "path", "load", "core", "install", "paths")
CODEX_RULE_ID = "rules::swe::adr-conventions"
GLOBAL_INSTRUCTIONS = "claude/config/CLAUDE.md"


def split_frontmatter(text: str) -> tuple[str, str]:
    """(frontmatter block with its fences, body); no block reads as ("", text)."""
    if not text.startswith("---\n"):
        return "", text
    end = text.index("\n---\n", 4) + len("\n---\n")
    return text[:end], text[end:]


def frontmatter(text: str) -> dict:
    block, _ = split_frontmatter(text)
    return yaml.safe_load(block.strip("-\n")) or {} if block else {}


def fixture_text(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def fixture_json(name: str):
    return json.loads(fixture_text(name))


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def manifest_rows(root: Path) -> dict[str, dict]:
    rows = yaml.safe_load((root / MANIFEST).read_text(encoding="utf-8"))["rules"]
    return {row["id"]: row for row in rows}


def rule_body_lines(text: str, minimum: int = 20) -> frozenset[str]:
    """The rule body's distinctive lines: stripped, at least `minimum` characters long."""
    _, body = split_frontmatter(text)
    return frozenset(line.strip() for line in body.splitlines() if len(line.strip()) >= minimum)


def scope_takes(globs: list[str], relpath: str) -> bool:
    """Whether a path-scope glob list takes `relpath` (`**` crosses directories)."""
    import fnmatch

    return any(fnmatch.fnmatchcase(relpath, glob) for glob in globs)


def instruction_texts(source: Path) -> list[str]:
    """The text of an instruction file, or of every Markdown file under a directory of them."""
    if source.is_file():
        return [source.read_text(encoding="utf-8")]
    return [p.read_text(encoding="utf-8") for p in sorted(source.rglob("*.md"))]


# -- Observations ---------------------------------------------------------------------------------


def _stand_in_claude(scratch: Path) -> Path:
    bin_dir = scratch / "claude-bin"
    bin_dir.mkdir(parents=True, exist_ok=True)
    stand_in = bin_dir / "claude"
    stand_in.write_text(f'#!/bin/sh\necho "$@" >> "{scratch}/claude-calls.log"\nexit 1\n')
    stand_in.chmod(0o755)
    return bin_dir


def install(scratch: Path) -> subprocess.CompletedProcess[str]:
    """`bash install.sh code --relink` from this checkout into `scratch`'s HOME, never a session."""
    env = isolated_env(scratch)
    env["PATH"] = f"{_stand_in_claude(scratch)}:{env['PATH']}"
    return subprocess.run(
        ["bash", str(REPO_ROOT / "install.sh"), "code", "--relink"],
        input="Y\nY\nY\n",
        cwd=scratch,
        env=env,
        capture_output=True,
        text=True,
        timeout=600,
    )


def session_start_rules(project: Path, scratch: Path) -> subprocess.CompletedProcess[str]:
    """The registered session-start rule injection, over `project`, as the harness runs it."""
    env = isolated_env(scratch, CLAUDE_PLUGIN_ROOT=str(REPO_ROOT), CLAUDE_PROJECT_DIR=str(project))
    event = {"hook_event_name": "SessionStart", "source": "startup", "cwd": str(project)}
    return subprocess.run(
        [sys.executable, str(REPO_ROOT / "hooks" / "inject_rules.py")],
        input=json.dumps(event | {"session_id": "adr-rule-move"}),
        cwd=project,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )


def run_check(
    argv: list[str], scratch: Path, root: Path = REPO_ROOT
) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, *argv],
        cwd=root,
        env=isolated_env(scratch),
        capture_output=True,
        text=True,
        timeout=600,
    )


def kernel_digests(root: Path = REPO_ROOT) -> dict[str, str]:
    kernels = root / "claude" / "kernels"
    files = [*sorted(kernels.glob("*.md")), kernels / "index.json"]
    return {f.name: digest(f.read_bytes()) for f in files}


def cursor_digests(scratch: Path, root: Path = REPO_ROOT) -> dict[str, str]:
    out = scratch / "cursor-rules"
    result = run_check(["cursor/config/export-cursor-rules.py", str(root), str(out)], scratch, root)
    assert result.returncode == 0, result.stdout + result.stderr
    return {
        str(p.relative_to(out)): digest(p.read_bytes())
        for p in sorted(out.rglob("*"))
        if p.is_file()
    }


def codex_reach(scratch: Path, root: Path = REPO_ROOT) -> dict:
    out = scratch / "codex-bridge"
    argv = [
        "codex/config/export-codex-rules-bridge.py",
        "--repo-root",
        str(root),
        "--out-dir",
        str(out),
    ]
    result = run_check(argv, scratch, root)
    assert result.returncode == 0, result.stdout + result.stderr
    manifest = json.loads((out / "praxion" / "rules_manifest.json").read_text(encoding="utf-8"))
    project = scratch / "codex-project"
    project.mkdir(exist_ok=True)
    started = subprocess.run(
        [sys.executable, str(out / "hooks" / "praxion-session-start.py")],
        input=json.dumps(
            {"hook_event_name": "SessionStart", "source": "startup", "cwd": str(project)}
        ),
        cwd=project,
        env=isolated_env(scratch),
        capture_output=True,
        text=True,
        timeout=60,
    )
    pointer = json.loads(started.stdout)["hookSpecificOutput"]["additionalContext"]
    return {
        "always_on": sorted(manifest["always_on_rule_ids"]),
        "rule_paths": sorted(rule["relpath"] for rule in manifest["rules"]),
        "pointer": pointer.replace(str(root), "<repo>"),
    }


def budget_files(scratch: Path, root: Path = REPO_ROOT) -> list[str]:
    """The files the always-loaded reading counts, under a HOME holding only the global file."""
    home = scratch / "home"
    (home / ".claude").mkdir(parents=True, exist_ok=True)
    (home / ".claude" / "CLAUDE.md").write_bytes((root / GLOBAL_INSTRUCTIONS).read_bytes())
    result = run_check(["scripts/measure_token_budget.py", "--json"], scratch, root)
    assert result.returncode in (0, 1), result.stdout + result.stderr
    files = json.loads(result.stdout)["files"]
    return sorted(
        f.replace(str(home.resolve()), "<home>")
        .replace(str(home), "<home>")
        .replace(str(root), "<repo>")
        for f in files
    )


# -- The checkout before the move, for the move instrument's own scenarios ------------------------


def restore_before_the_move(root: Path) -> None:
    """Put the moved rule, its manifest row and the resident file back as they were at the base.

    The move instrument measures a move that has not landed; its scenarios run over a checkout
    in that state. A checkout already in it is left byte for byte as it is."""
    resident = root / RESIDENT
    if not resident.exists() and (root / MOVED_RULE).read_text(encoding="utf-8") == fixture_text(
        "base_rule.md"
    ):
        return
    resident.unlink(missing_ok=True)
    (root / MOVED_RULE).write_text(fixture_text("base_rule.md"), encoding="utf-8")
    text = (root / MANIFEST).read_text(encoding="utf-8")
    header = "".join(line for line in text.splitlines(keepends=True) if line.startswith("#"))
    manifest = yaml.safe_load(text)
    frozen = fixture_json("base_row.json")
    # The generator writes `id` first and readers find a row by its `- id:` line, so the frozen
    # row (stored with sorted keys) goes back in the generator's key order.
    base_row = {k: frozen[k] for k in _GENERATED_ROW_ORDER if k in frozen} | {
        k: v for k, v in frozen.items() if k not in _GENERATED_ROW_ORDER
    }
    manifest["rules"] = [
        base_row if row["id"] == RULE_IDS[0] else row
        for row in manifest["rules"]
        if row["id"] != RULE_IDS[1]
    ]
    (root / MANIFEST).write_text(
        header + yaml.safe_dump(manifest, sort_keys=False), encoding="utf-8"
    )


# -- Freezing ---------------------------------------------------------------------------------------


def freeze(lean_copy: Path, scratch: Path) -> None:
    """Write every fixture from this tree (at the base) and the lean arm the instrument built."""
    FIXTURES.mkdir(parents=True, exist_ok=True)
    (FIXTURES / "measured_rule.md").write_bytes((lean_copy / MOVED_RULE).read_bytes())
    (FIXTURES / "measured_resident.md").write_bytes((lean_copy / RESIDENT).read_bytes())
    (FIXTURES / "base_rule.md").write_bytes((REPO_ROOT / MOVED_RULE).read_bytes())
    lean_rows = manifest_rows(lean_copy)
    dumps = {
        "measured_rows.json": {
            i: {k: lean_rows[i].get(k) for k in MEASURED_KEYS} for i in RULE_IDS
        },
        "base_row.json": manifest_rows(REPO_ROOT)[RULE_IDS[0]],
        "base_kernels.json": kernel_digests(),
        "base_cursor.json": cursor_digests(scratch / "cursor"),
        "base_codex.json": codex_reach(scratch / "codex"),
        "base_budget_files.json": budget_files(scratch / "budget"),
    }
    for name, value in dumps.items():
        (FIXTURES / name).write_text(json.dumps(value, indent=1, sort_keys=True) + "\n")
