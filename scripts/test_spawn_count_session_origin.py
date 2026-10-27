"""A slug-less spawn is charged to the checkout the hook logged it in, whatever directory the session began in.

The row is written by the real hook from a real checkout tree, then read by the tally: the
session starts in a subdirectory of the pipeline's checkout, and its interactive spawn must
still belong to the pipeline named after that checkout.
"""

from __future__ import annotations

import importlib.util
import io
import json
import sys
from pathlib import Path

import pytest
import spawn_count
from spawn_count import Owned

HOOKS_DIR = Path(__file__).resolve().parent.parent / "hooks"
SLUG = "pipe-slug"


@pytest.fixture
def pipeline_checkout(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    checkout = tmp_path / SLUG
    (checkout / ".git").mkdir(parents=True)
    (checkout / ".ai-state").mkdir()
    monkeypatch.syspath_prepend(str(HOOKS_DIR))
    monkeypatch.setenv("PRAXION_OBSERVATION_LOG", "full")
    monkeypatch.setenv("TMPDIR", str(tmp_path))
    monkeypatch.delenv("PRAXION_DISABLE_OBSERVABILITY", raising=False)
    return checkout


def _spawn_from(started_in: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Run the hook for an interactive session started in `started_in` spawning an agent."""
    monkeypatch.setenv("CLAUDE_CODE_ENTRYPOINT", "cli")
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(started_in))
    payload = {
        "tool_name": "Agent",
        "tool_input": {"prompt": "Explore the module.", "subagent_type": "researcher"},
        "tool_response": {"agentId": "a1"},
        "cwd": str(started_in),
        "session_id": "sess-1",
    }
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(payload)))
    spec = importlib.util.spec_from_file_location(
        "capture_observations", HOOKS_DIR / "capture_observations.py"
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.main()


def _logged_rows(checkout: Path) -> list[dict]:
    lines = (checkout / ".ai-state" / "observations.jsonl").read_text().splitlines()
    return [json.loads(line) for line in lines]


@pytest.mark.parametrize("subdirectory", [".", "packages", "packages/app"])
def test_an_interactive_slugless_spawn_is_charged_to_the_pipeline_whatever_directory_it_began_in(
    pipeline_checkout: Path, monkeypatch: pytest.MonkeyPatch, subdirectory: str
) -> None:
    started_in = pipeline_checkout / subdirectory
    started_in.mkdir(parents=True, exist_ok=True)

    _spawn_from(started_in, monkeypatch)

    (agent,) = spawn_count.tally(_logged_rows(pipeline_checkout), pipeline_checkout.resolve())
    assert agent.owner == Owned(SLUG)
