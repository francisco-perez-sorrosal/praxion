"""The spawn-count liveness probe under the entry point `check_gates_bite.py` registers.

The probe shares its scratch project and hook replay with the observation-hook
probe, so it lives in `observation.py`; this module only gives it the
`gate_probes.spawn_count:run` name the registry resolves.
"""

from __future__ import annotations

from gate_probes.observation import run_spawn_count as run

__all__ = ["run"]
