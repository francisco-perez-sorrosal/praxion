"""The no-cost count of the text a split recipient sheds.

Bound to `scripts/count_spawn_shed.py --json`, run over a plugin root.
"""

from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

from tests.acceptance.drivers.kernel_sandbox import isolated_env


@dataclass(frozen=True)
class UnitCount:
    whole_chars: int  # the strings a whole recipient receives for the unit, labels included
    split_chars: int  # the strings a split recipient receives for the unit, labels included
    difference: int
    tokens: int  # the shed text's token figure
    token_basis: str  # "tokenizer" or "estimate"


@dataclass(frozen=True)
class ShedCount:
    exit_code: int
    units: dict[str, UnitCount]  # by unit id, for both split units
    total: UnitCount


@dataclass(frozen=True)
class ModelRequestTrap:
    """A `claude` stand-in that records any call and exits 1, and proxies that reach nothing."""

    bin_dir: Path
    calls: Path

    @property
    def env(self) -> dict[str, str]:
        dead = "http://127.0.0.1:9"
        return {"HTTP_PROXY": dead, "HTTPS_PROXY": dead, "ALL_PROXY": dead, "NO_PROXY": ""}

    def recorded(self) -> list[str]:
        return self.calls.read_text(encoding="utf-8").splitlines() if self.calls.exists() else []


def model_request_trap(scratch: Path) -> ModelRequestTrap:
    bin_dir = scratch / "trap-bin"
    bin_dir.mkdir(parents=True, exist_ok=True)
    calls = scratch / "claude-calls.log"
    stand_in = bin_dir / "claude"
    stand_in.write_text(f'#!/bin/sh\necho "$@" >> "{calls}"\nexit 1\n', encoding="utf-8")
    stand_in.chmod(0o755)
    return ModelRequestTrap(bin_dir, calls)


_NO_FIGURES = UnitCount(whole_chars=0, split_chars=0, difference=0, tokens=0, token_basis="")
_COUNT_TIMEOUT = 120


def shed_count(plugin_root: Path, scratch: Path, trap: ModelRequestTrap | None = None) -> ShedCount:
    """Run the no-cost count of the text a split recipient sheds, over `plugin_root`.

    With a `trap`, the command runs with `trap.bin_dir` first on PATH and `trap.env` applied.
    A command that exits non-zero yields a `ShedCount` that carries its exit code and no figures.
    """
    environment = isolated_env(scratch)
    if trap is not None:
        environment["PATH"] = f"{trap.bin_dir}{os.pathsep}{environment['PATH']}"
        environment.update(trap.env)
    proc = subprocess.run(
        ["python3", "scripts/count_spawn_shed.py", "--repo-root", str(plugin_root), "--json"],
        cwd=plugin_root,
        env=environment,
        capture_output=True,
        text=True,
        timeout=_COUNT_TIMEOUT,
    )
    if proc.returncode != 0:
        return ShedCount(proc.returncode, {}, _NO_FIGURES)
    try:
        return _parse_shed_report(proc.returncode, json.loads(proc.stdout))
    except (ValueError, KeyError, TypeError) as error:
        raise AssertionError(
            f"the shed-count command exited 0 but its report cannot be read ({error!r}); "
            f"stdout starts {proc.stdout[:200]!r}; stderr ends {proc.stderr[-500:]!r}"
        ) from error


def _parse_shed_report(exit_code: int, report: dict) -> ShedCount:
    basis = report["tokens"]["basis"]

    def unit_count(figures: dict, tokens: dict) -> UnitCount:
        return UnitCount(
            whole_chars=figures["whole_chars"],
            split_chars=figures["split_chars"],
            difference=figures["shed_chars"],
            tokens=tokens["shed"],
            token_basis=basis,
        )

    units = {
        unit_id: unit_count(figures, figures["tokens"])
        for unit_id, figures in report["units"].items()
    }
    return ShedCount(exit_code, units, unit_count(report["total"], report["tokens"]))
