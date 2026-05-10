from __future__ import annotations

import os
import subprocess
import tomllib
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
INSTALLER = REPO_ROOT / "install_codex.sh"


def make_home(tmp_path: Path) -> tuple[dict[str, str], Path]:
    home_dir = tmp_path / "home"
    home_dir.mkdir()
    env = os.environ.copy()
    env["HOME"] = str(home_dir)
    return env, home_dir


def run_install(
    *args: str, env: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(INSTALLER), *args],
        cwd=REPO_ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


def test_install_codex_exports_canonical_paths_and_check_passes(tmp_path: Path):
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    env, home_dir = make_home(tmp_path)

    install = run_install(str(project_dir), env=env)
    assert install.returncode == 0, install.stderr or install.stdout
    assert "Codex pipeline adapter exported" in install.stdout
    assert "Codex shared MCP config updated" in install.stdout

    researcher = (project_dir / ".codex" / "agents" / "researcher.toml").read_text(
        encoding="utf-8"
    )
    planning = (
        project_dir / ".agents" / "skills" / "software-planning" / "SKILL.md"
    ).read_text(encoding="utf-8")
    command = (
        project_dir / ".agents" / "skills" / "praxion-command-co" / "SKILL.md"
    ).read_text(encoding="utf-8")
    agents_md = (project_dir / "AGENTS.md").read_text(encoding="utf-8")

    assert (
        str((REPO_ROOT / "agents" / "researcher.md").resolve()).replace("\\", "/")
        in researcher
    )
    assert 'model = "gpt-5.4"' in researcher
    assert 'model_reasoning_effort = "medium"' in researcher
    assert "Praxion agent contract:" in researcher
    assert (
        str(
            (REPO_ROOT / "skills" / "software-planning" / "SKILL.md").resolve()
        ).replace("\\", "/")
        in planning
    )
    assert (
        str((REPO_ROOT / "commands" / "co.md").resolve()).replace("\\", "/") in command
    )
    assert "Treat any user text after the command name as `$ARGUMENTS`." in command
    assert (project_dir / ".codex" / "praxion" / "rules_manifest.json").exists()
    assert (project_dir / ".codex" / "praxion" / "hook_runtime.py").exists()
    assert (project_dir / ".codex" / "praxion" / "pipeline_semantics.json").exists()
    assert (project_dir / ".codex" / "praxion" / "model_routing.json").exists()
    assert (
        project_dir / ".codex" / "hooks" / "praxion-memory-session-start.py"
    ).exists()
    assert (project_dir / ".codex" / "hooks" / "praxion-memory-stop.py").exists()
    assert (
        project_dir / ".codex" / "hooks" / "praxion-subagent-pre-tool-use.py"
    ).exists()
    assert (
        project_dir / ".codex" / "hooks" / "praxion-commit-memory-pre-tool-use.py"
    ).exists()
    assert (project_dir / ".codex" / "hooks" / "praxion-precompact-state.py").exists()
    assert (
        project_dir / ".codex" / "hooks" / "praxion-observability-post-tool-use.py"
    ).exists()
    assert ".codex/praxion/pipeline_semantics.json" in agents_md
    assert ".codex/praxion/model_routing.json" in agents_md
    assert "Codex-native translation of Praxion" in agents_md
    assert "Claude-only routing rule" in agents_md
    assert (project_dir / ".codex" / "hooks.json").exists()
    config_text = (project_dir / ".codex" / "config.toml").read_text(encoding="utf-8")
    config_lines = set(config_text.splitlines())
    assert "hooks = true" in config_lines
    assert "codex_hooks" not in config_text
    hooks_text = (project_dir / ".codex" / "hooks.json").read_text(encoding="utf-8")
    assert "praxion-memory-session-start.py" in hooks_text
    assert "praxion-memory-stop.py" in hooks_text
    assert "praxion-subagent-pre-tool-use.py" in hooks_text
    assert "praxion-commit-memory-pre-tool-use.py" in hooks_text
    assert "praxion-precompact-state.py" in hooks_text
    assert "praxion-observability-post-tool-use.py" in hooks_text
    assert '"async"' not in hooks_text
    shared_config = tomllib.loads(
        (home_dir / ".codex" / "config.toml").read_text(encoding="utf-8")
    )
    memory_config = shared_config["mcp_servers"]["memory"]
    chronograph_config = shared_config["mcp_servers"]["task-chronograph"]
    assert memory_config["command"] == "uv"
    assert memory_config["args"][2] == str((REPO_ROOT / "memory-mcp").resolve())
    assert memory_config["env"]["MEMORY_FILE"] == ".ai-state/memory.json"
    assert chronograph_config["args"][2] == str(
        (REPO_ROOT / "task-chronograph-mcp").resolve()
    )
    assert chronograph_config["env"]["OTEL_ENABLED"] == "true"
    assert (home_dir / ".codex" / "praxion" / "mcp_state.json").exists()

    check = run_install(str(project_dir), "--check", env=env)
    assert check.returncode == 0, check.stderr or check.stdout
    assert "Codex pipeline adapter present" in check.stdout
    assert "Codex shared MCP config present" in check.stdout


def test_install_codex_dry_run_reports_pipeline_adapter(tmp_path: Path):
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    env, _home_dir = make_home(tmp_path)

    dry_run = run_install(str(project_dir), "--dry-run", env=env)

    assert dry_run.returncode == 0, dry_run.stderr or dry_run.stdout
    assert "Would export Praxion pipeline adapter" in dry_run.stdout
    assert "Would install Praxion MCP servers" in dry_run.stdout


def test_install_codex_check_fails_on_unexpected_generated_wrappers(tmp_path: Path):
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    env, _home_dir = make_home(tmp_path)
    install = run_install(str(project_dir), env=env)
    assert install.returncode == 0, install.stderr or install.stdout

    fake_agent = project_dir / ".codex" / "agents" / "fake-agent.toml"
    fake_agent.write_text(
        '# Generated by Praxion Codex exporter.\nname = "fake-agent"\ndescription = "bogus"\n',
        encoding="utf-8",
    )
    fake_skill_dir = project_dir / ".agents" / "skills" / "fake-skill"
    fake_skill_dir.mkdir(parents=True)
    (fake_skill_dir / "SKILL.md").write_text(
        "---\nname: fake-skill\ndescription: 'bogus'\n---\n\nThis is a Codex skill wrapper for Praxion.\n",
        encoding="utf-8",
    )
    fake_command_dir = project_dir / ".agents" / "skills" / "praxion-command-fake"
    fake_command_dir.mkdir(parents=True)
    (fake_command_dir / "SKILL.md").write_text(
        "---\nname: praxion-command-fake\ndescription: 'bogus'\n---\n\n"
        "This is a Codex command-skill wrapper for a Praxion slash command.\n",
        encoding="utf-8",
    )

    check = run_install(str(project_dir), "--check", env=env)
    assert check.returncode == 1
    assert "Unexpected stale Praxion agent wrapper" in check.stdout
    assert "Unexpected stale Praxion skill wrapper" in check.stdout


def test_install_codex_reinstall_prunes_unexpected_generated_wrappers(tmp_path: Path):
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    env, _home_dir = make_home(tmp_path)
    install = run_install(str(project_dir), env=env)
    assert install.returncode == 0, install.stderr or install.stdout

    fake_agent = project_dir / ".codex" / "agents" / "fake-agent.toml"
    fake_agent.write_text(
        '# Generated by Praxion Codex exporter.\nname = "fake-agent"\ndescription = "bogus"\n',
        encoding="utf-8",
    )
    fake_skill_dir = project_dir / ".agents" / "skills" / "fake-skill"
    fake_skill_dir.mkdir(parents=True)
    fake_skill = fake_skill_dir / "SKILL.md"
    fake_skill.write_text(
        "---\nname: fake-skill\ndescription: 'bogus'\n---\n\nThis is a Codex skill wrapper for Praxion.\n",
        encoding="utf-8",
    )
    fake_command_dir = project_dir / ".agents" / "skills" / "praxion-command-fake"
    fake_command_dir.mkdir(parents=True)
    fake_command = fake_command_dir / "SKILL.md"
    fake_command.write_text(
        "---\nname: praxion-command-fake\ndescription: 'bogus'\n---\n\n"
        "This is a Codex command-skill wrapper for a Praxion slash command.\n",
        encoding="utf-8",
    )

    reinstall = run_install(str(project_dir), env=env)
    assert reinstall.returncode == 0, reinstall.stderr or reinstall.stdout
    assert not fake_agent.exists()
    assert not fake_skill.exists()
    assert not fake_command.exists()


def test_install_codex_uninstall_preserves_user_codex_config_and_hooks(tmp_path: Path):
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    env, home_dir = make_home(tmp_path)
    codex_dir = project_dir / ".codex"
    codex_dir.mkdir()
    (codex_dir / "config.toml").write_text(
        "[features]\nother_flag = true\nhooks = false\ncodex_hooks = false\n",
        encoding="utf-8",
    )
    (codex_dir / "hooks.json").write_text(
        '{\n  "hooks": {\n    "SessionStart": [\n      {\n        "hooks": [\n          {\n            "type": "command",\n            "command": "python3 user-hook.py",\n            "statusMessage": "User hook"\n          }\n        ]\n      }\n    ]\n  }\n}\n',
        encoding="utf-8",
    )
    shared_codex_dir = home_dir / ".codex"
    shared_codex_dir.mkdir()
    (shared_codex_dir / "config.toml").write_text(
        '[profiles.default]\nmodel = "gpt-5"\n\n[mcp_servers.memory]\n'
        'command = "python3"\nargs = ["-m", "user_memory"]\nstartup_timeout_sec = 30\n',
        encoding="utf-8",
    )

    install = run_install(str(project_dir), env=env)
    assert install.returncode == 0, install.stderr or install.stdout

    installed_config = (codex_dir / "config.toml").read_text(encoding="utf-8")
    installed_config_lines = set(installed_config.splitlines())
    assert "other_flag = true" in installed_config
    assert "hooks = true" in installed_config_lines
    assert "codex_hooks" not in installed_config
    hooks_text = (codex_dir / "hooks.json").read_text(encoding="utf-8")
    assert "python3 user-hook.py" in hooks_text
    assert "praxion-session-start.py" in hooks_text
    shared_config = tomllib.loads(
        (shared_codex_dir / "config.toml").read_text(encoding="utf-8")
    )
    assert shared_config["profiles"]["default"]["model"] == "gpt-5"
    assert shared_config["mcp_servers"]["memory"]["command"] == "uv"

    uninstall = run_install(str(project_dir), "--uninstall", env=env)
    assert uninstall.returncode == 0, uninstall.stderr or uninstall.stdout

    final_config = (codex_dir / "config.toml").read_text(encoding="utf-8")
    assert "other_flag = true" in final_config
    assert "hooks = false" in final_config
    assert "codex_hooks = false" in final_config
    final_hooks = (codex_dir / "hooks.json").read_text(encoding="utf-8")
    assert "python3 user-hook.py" in final_hooks
    assert "praxion-session-start.py" not in final_hooks
    assert not (codex_dir / "praxion" / "config_state.json").exists()
    assert not (codex_dir / "praxion" / "pipeline_semantics.json").exists()
    assert not (codex_dir / "praxion" / "model_routing.json").exists()
    restored_shared_config = (shared_codex_dir / "config.toml").read_text(
        encoding="utf-8"
    )
    assert '[profiles.default]\nmodel = "gpt-5"' in restored_shared_config
    assert 'command = "python3"' in restored_shared_config
    assert 'args = ["-m", "user_memory"]' in restored_shared_config
    assert "startup_timeout_sec = 30" in restored_shared_config
    assert not (shared_codex_dir / "praxion" / "mcp_state.json").exists()
