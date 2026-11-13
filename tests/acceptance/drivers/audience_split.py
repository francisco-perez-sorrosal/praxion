"""Driver for the audience split of what a spawn receives from rule delivery.

The driver is split by cohesion; this module re-exports every name scenarios use:

* `audience_split_delivery` - plugin checkouts and the base arms, projects, the rule delivery a
  session or spawn receives, impaired delivery.
* `audience_split_oracle` - the units, the roles, and the specification's split text computed from
  the sources and the audience manifest alone (never from the hooks).
* `audience_split_plants` - editing a checkout so its spawn delivery disagrees with its sources,
  and the commit-time kernel gate (through `kernel_sandbox.commit_gate`) read against it. The
  regeneration a maintainer runs after editing is bound provisionally to the kernel generator.
* `audience_split_shed` - the no-cost count of the text a split recipient sheds, bound to
  `scripts/count_spawn_shed.py --json`.

Isolation: `kernel_sandbox.isolated_env` (own HOME, a `python3` shim for this interpreter, no
inherited `CLAUDE*`, `PRAXION_*`, `GIT_*` or `ANTHROPIC_*` variable). A user agent lives in that
HOME's `.claude/agents/`. A missing PyYAML is a `yaml` package first on `PYTHONPATH` whose import
fails, so the hooks' interpreter cannot import the parser.
"""

from __future__ import annotations

from tests.acceptance.drivers.audience_split_delivery import (
    BASE_COMMIT,
    IMPAIRMENTS,
    INLINE_CAP,
    KILL_SWITCH,
    LABEL,
    REPO_ROOT,
    RULES_MANIFEST,
    Delivery,
    base_commit_available,
    base_hooks_arm,
    base_tree_arm,
    changes_beyond_declared_edits,
    delivered_as,
    fresh_project,
    impair,
    session_start,
    spawn,
    unreadable,
    user_agents_dir,
    without_pyyaml,
    write_blacklist,
    write_definition,
)
from tests.acceptance.drivers.audience_split_oracle import (
    ADR_RESIDENT,
    CORE_UNITS,
    DROPPED,
    INTERMEDIATE,
    LEAN_ROLES,
    PROTOCOL,
    SCOPES,
    SPLIT_ROLES,
    SPLIT_UNITS,
    Unit,
    audience_entries,
    dropped_headings,
    source_text,
    split_text,
)
from tests.acceptance.drivers.audience_split_plants import (
    PLANTED,
    PLANTS,
    SOURCE_ONLY_PLANTS,
    DriftReading,
    add_dropped_section,
    bring_up_to_date,
    changed_data_files,
    damage,
    drift_reading,
    insert_under_heading,
    kernel_gate,
    names_unit,
    other_unit,
    plant,
    reclassify,
    remove_section,
    restore,
    snapshot,
)
from tests.acceptance.drivers.audience_split_shed import (
    ModelRequestTrap,
    ShedCount,
    UnitCount,
    model_request_trap,
    shed_count,
)
from tests.acceptance.drivers.kernel_sandbox import AUDIENCE_MANIFEST

__all__ = [
    "ADR_RESIDENT",
    "AUDIENCE_MANIFEST",
    "BASE_COMMIT",
    "CORE_UNITS",
    "DROPPED",
    "Delivery",
    "DriftReading",
    "IMPAIRMENTS",
    "INLINE_CAP",
    "INTERMEDIATE",
    "KILL_SWITCH",
    "LABEL",
    "LEAN_ROLES",
    "ModelRequestTrap",
    "PLANTED",
    "PLANTS",
    "PROTOCOL",
    "REPO_ROOT",
    "RULES_MANIFEST",
    "SCOPES",
    "SOURCE_ONLY_PLANTS",
    "SPLIT_ROLES",
    "SPLIT_UNITS",
    "ShedCount",
    "Unit",
    "UnitCount",
    "add_dropped_section",
    "audience_entries",
    "base_commit_available",
    "base_hooks_arm",
    "base_tree_arm",
    "changes_beyond_declared_edits",
    "bring_up_to_date",
    "changed_data_files",
    "damage",
    "delivered_as",
    "drift_reading",
    "dropped_headings",
    "fresh_project",
    "impair",
    "insert_under_heading",
    "kernel_gate",
    "model_request_trap",
    "names_unit",
    "other_unit",
    "plant",
    "reclassify",
    "remove_section",
    "restore",
    "session_start",
    "shed_count",
    "snapshot",
    "source_text",
    "spawn",
    "split_text",
    "unreadable",
    "user_agents_dir",
    "without_pyyaml",
    "write_blacklist",
    "write_definition",
]
