"""Every session sees only the checkout under test.

Each launched session gets its own sandbox `HOME` and `CLAUDE_CONFIG_DIR`,
receives the checkout copy only through `--plugin-dir`, runs with MCP servers off,
and inherits nothing from the operator's environment outside the allowlist.
"""

from __future__ import annotations

from pathlib import Path

from tests.e2e.drivers.adherence_journey import run_journey

PROBES = {"PRAXION_ADHERENCE_LEAK_PROBE": "leaked", "CLAUDE_PLUGIN_ROOT": "/operator/plugin"}


def test_every_session_runs_in_its_own_sandbox_with_only_the_checkout_copy(tmp_path):
    journey = run_journey(tmp_path, roles=("verifier",), arms=("lean",), extra_env=PROBES)
    operator_home = Path.home()

    launches = journey.launches

    assert launches, f"the run launched no session; {journey.describe()}"
    for launch in launches:
        home, config = launch.env.get("HOME"), launch.env.get("CLAUDE_CONFIG_DIR")
        assert home, "a session ran without its own HOME"
        assert Path(home) != operator_home, "a session ran with the operator's HOME"
        assert config, "a session ran without its own CLAUDE_CONFIG_DIR"
        assert not Path(config).is_relative_to(operator_home / ".claude"), (
            "a session read the operator's Claude configuration"
        )
        assert len(launch.option_values("--plugin-dir")) == 1
        assert "--strict-mcp-config" in launch.argv
        assert not set(PROBES) & set(launch.env), (
            "an operator variable outside the allowlist leaked in"
        )
