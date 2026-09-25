"""Drift gate for the canonical artifact registry (scripts/artifact_registry.py).

The dashboard and precompact-hook `.ai-work/<slug>/` artifact lists must agree
with the registry's projection for their consumer. This test is that gate for
both of them, plus the registry's own internal self-consistency.

Gate-liveness contract: a gate must be proven to bite on a known-bad input, not
merely pass on the current good state. The canaries below feed synthetic drifted
consumer text (a stale `SKILL_GENESIS_REPORT.md`; a dropped required artifact)
and assert the comparison the live tests make would FAIL — so a future edit that
re-introduces drift in either consumer turns this suite red.

The dashboard and precompact hook consumers are parsed from source text (no
imports), so the gate works uniformly across the hook and the TypeScript
dashboard module. The eval package's derivation from the registry's per-tier
floor is exercised in its own suite
(eval/tests/test_harness_family1_task_manifest.py) since it imports the
registry as a package dependency rather than being source-parsed.

Per-tier artifact floor (Tier/Signal/Floor/floor()/signal_holds()): every
reader of "what must a Standard/Full pipeline produce" derives from one
registry-owned projection instead of duplicating the list. The tests below
pin that projection, its monotonicity constructor, the file-decidable signal
predicates, and the cross-field self-consistency invariants a floor entry
must satisfy.
"""

from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path
from typing import Any

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent
_REGISTRY_PATH = Path(__file__).resolve().parent / "artifact_registry.py"


def _load_registry() -> Any:
    spec = importlib.util.spec_from_file_location("artifact_registry", _REGISTRY_PATH)
    assert spec is not None
    assert spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


registry = _load_registry()


# -- Source extraction --------------------------------------------------------

_FILE_RE = re.compile(r"""["']([A-Za-z0-9_]+\.(?:md|ya?ml))["']""")
_PATH_RE = re.compile(r'path="([^"]+)"')


def _bracketed_block(text: str, marker: str, open_ch: str, close_ch: str) -> str:
    """Return the balanced `open_ch..close_ch` block that follows `marker`."""
    marker_idx = text.index(marker)
    # Search for the opening bracket AFTER the marker ends, so a type annotation
    # inside the marker (e.g. TS `string[]`) does not get matched as the block.
    start = text.index(open_ch, marker_idx + len(marker))
    depth = 0
    for i in range(start, len(text)):
        if text[i] == open_ch:
            depth += 1
        elif text[i] == close_ch:
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    raise ValueError(f"unbalanced block after {marker!r}")


def _filenames(block: str) -> set[str]:
    return {m.group(1) for m in _FILE_RE.finditer(block)}


def _read(rel: str) -> str:
    return (_REPO_ROOT / rel).read_text(encoding="utf-8")


def _dashboard_workshop() -> set[str]:
    text = _read("dashboard_app/src/server/artifacts/files.ts")
    return _filenames(_bracketed_block(text, "CANONICAL_WORKSHOP_ARTIFACTS: string[] =", "[", "]"))


def _precompact_pipeline_docs() -> set[str]:
    text = _read("hooks/precompact_state.py")
    return _filenames(_bracketed_block(text, "PIPELINE_DOCS", "[", "]"))


# -- Live drift assertions ----------------------------------------------------


def test_dashboard_workshop_matches_registry_dashboard_set() -> None:
    assert _dashboard_workshop() == registry.dashboard_artifacts()


def test_precompact_matches_registry_snapshot_set() -> None:
    assert _precompact_pipeline_docs() == registry.snapshot_artifacts()


def test_every_consumer_filename_is_registered() -> None:
    # No consumer may list an artifact the registry does not know — catches the
    # dead SKILL_GENESIS_REPORT.md class of drift in either direction. The eval
    # consumer moved to a derivation test in
    # eval/tests/test_harness_family1_task_manifest.py (it now builds its set
    # from the registry's floor projection rather than a hand-written literal,
    # so there is nothing left to source-parse here).
    known = registry.all_names()
    for label, names in (
        ("dashboard", _dashboard_workshop()),
        ("precompact", _precompact_pipeline_docs()),
    ):
        unknown = names - known
        assert not unknown, f"{label} lists unregistered artifact(s): {sorted(unknown)}"


# -- Canaries (prove the gate bites) ------------------------------------------


def test_canary_stale_skill_genesis_report_would_fail() -> None:
    """The historical drift: a consumer carrying the dead SKILL_GENESIS_REPORT.md."""
    drifted = '_AI_WORK_FILES = [\n  "WIP.md",\n  "SKILL_GENESIS_REPORT.md",\n]'
    items = _filenames(_bracketed_block(drifted, "_AI_WORK_FILES", "[", "]"))
    assert "SKILL_GENESIS_REPORT.md" in items
    assert "SKILL_GENESIS_REPORT.md" not in registry.dashboard_artifacts()
    # The live assertion (items == dashboard set) would fail on this input.
    assert items != registry.dashboard_artifacts()


def test_canary_missing_required_artifact_would_fail() -> None:
    """A consumer that dropped required artifacts must be flagged."""
    drifted = '_AI_WORK_FILES = [\n  "WIP.md",\n]'
    items = _filenames(_bracketed_block(drifted, "_AI_WORK_FILES", "[", "]"))
    missing = registry.dashboard_artifacts() - items
    assert missing  # non-empty => the gate bites
    assert items != registry.dashboard_artifacts()


# -- Registry self-consistency ------------------------------------------------


def test_registry_names_are_unique() -> None:
    names = [a.name for a in registry.ARTIFACTS]
    assert len(names) == len(set(names))


# -- Registry declarative spine self-consistency ------------------------------
# These tests validate the production_gate / cleanup_policy fields and the
# _GATE_KINDS / _CLEANUP_POLICIES constants added in the declarative spine
# (artifact_registry.py).  They are expected RED until the declarative-spine fields are added.
#
# _GATE_KINDS (production): {script, hook, producer, none, deferred}
# _DETECTION_GATE_KINDS: {sentinel, none}
# _CLEANUP_POLICIES: {delete, archive, block-if-active, consume-marker}
# production_gate format: "<kind>:<ref>" | "none" | "deferred"
#   none/deferred carry NO ref; script/hook/producer REQUIRE a ref.
# detection_gate format: "sentinel:<id>" | "none"  (sentinel REQUIRES a ref)
# cleanup_policy: bare string ∈ _CLEANUP_POLICIES


def test_production_gate_kind_is_known() -> None:
    """Every artifact's production_gate names a kind in the allowed vocabulary."""
    for a in registry.ARTIFACTS:
        kind = a.production_gate.split(":")[0]
        assert kind in registry._GATE_KINDS, (
            f"{a.name}: production_gate kind {kind!r} not in _GATE_KINDS"
        )


def test_production_gate_ref_required_when_kind_demands_it() -> None:
    """Ref-bearing kinds (sentinel/script/hook/producer) must carry a non-empty ref;
    ref-free kinds (none/deferred) must not carry any ref component.
    """
    ref_required = {"script", "hook", "producer"}
    no_ref = {"none", "deferred"}

    for a in registry.ARTIFACTS:
        parts = a.production_gate.split(":", 1)
        kind = parts[0]
        ref = parts[1] if len(parts) > 1 else ""

        if kind in ref_required:
            assert ref, (
                f"{a.name}: kind {kind!r} requires a non-empty ref "
                f"(got production_gate={a.production_gate!r})"
            )
        if kind in no_ref:
            assert len(parts) == 1, (
                f"{a.name}: kind {kind!r} must not carry a ref "
                f"(got production_gate={a.production_gate!r})"
            )


def test_cleanup_policy_is_known() -> None:
    """Every artifact's cleanup_policy is drawn from the allowed vocabulary."""
    for a in registry.ARTIFACTS:
        assert a.cleanup_policy in registry._CLEANUP_POLICIES, (
            f"{a.name}: cleanup_policy {a.cleanup_policy!r} not in _CLEANUP_POLICIES"
        )


def test_detection_gate_kind_is_known() -> None:
    """Every artifact's detection_gate names a kind in the detection vocabulary."""
    for a in registry.ARTIFACTS:
        kind = a.detection_gate.split(":")[0]
        assert kind in registry._DETECTION_GATE_KINDS, (
            f"{a.name}: detection_gate kind {kind!r} not in _DETECTION_GATE_KINDS"
        )


def test_detection_gate_ref_required_for_sentinel() -> None:
    """`sentinel` detection gates carry a check-id ref; `none` carries no ref."""
    for a in registry.ARTIFACTS:
        parts = a.detection_gate.split(":", 1)
        kind = parts[0]
        ref = parts[1] if len(parts) > 1 else ""
        if kind == "sentinel":
            assert ref, f"{a.name}: sentinel detection_gate needs a ref ({a.detection_gate!r})"
        if kind == "none":
            assert len(parts) == 1, f"{a.name}: 'none' detection_gate must carry no ref"


def test_detection_is_not_labelled_as_production() -> None:
    """The EA-02 fix: a sentinel presence-check is detection, never production.

    No artifact may name a `sentinel:` value in production_gate — that conflation
    (TASK_BRIEF/INTERFACE_DESIGN/TRANSACTIONS_DESIGN before Wave 4b) is exactly what
    the detection_gate split corrects. Sentinel checks belong in detection_gate.
    """
    for a in registry.ARTIFACTS:
        assert not a.production_gate.startswith("sentinel:"), (
            f"{a.name}: sentinel check {a.production_gate!r} is detection, not production — "
            "move it to detection_gate"
        )


def test_core_artifacts_have_a_gate() -> None:
    """Always-active (core) artifacts must declare a real production gate.

    A hollow 'none' gate on a core artifact means the obligation has no
    enforcement mechanism — exactly the gap the declarative spine is closing.
    'deferred' is also disallowed on always-active artifacts (those are
    specialist/conditional entries that have not been gated yet).
    """
    gateless = {"none", "deferred"}
    for a in registry.ARTIFACTS:
        if a.activation != "always":
            continue
        kind = a.production_gate.split(":")[0]
        assert kind not in gateless, (
            f"{a.name}: always-active artifact has ungated production_gate "
            f"({a.production_gate!r}); core artifacts must name a real gate"
        )


# -- Declarative-spine canary (gate-liveness proof) ---------------------------


def test_canary_bogus_gate_kind_is_rejected() -> None:
    """A production_gate with an unknown kind must be caught by the kind check.

    This canary proves the gate bites on known-bad input: 'bogus' is not a
    member of _GATE_KINDS, so any row carrying 'bogus:x' would make
    test_production_gate_kind_is_known fail.  If _GATE_KINDS were accidentally
    widened to include 'bogus', this assertion catches the regression.
    """
    bogus_gate = "bogus:x"
    kind = bogus_gate.split(":")[0]
    assert kind not in registry._GATE_KINDS, (
        f"'bogus' should never be a valid gate kind; _GATE_KINDS={registry._GATE_KINDS!r}"
    )


# -- Per-tier artifact floor ---------------------------------------------------
# Expected RED against the base (522302ca) registry: `Tier`, `Signal`,
# `Requirement`, `Floor`, `floor()`, `signal_holds()`, `NO_TEST_TARGET_MARKER`,
# and the per-`Artifact` `.floor` field do not exist yet — every test below
# fails with AttributeError until the registry gains them. That is the correct
# RED state for a not-yet-implemented contract (as opposed to the assertion
# failures below, which pin behavior against artifacts the registry already
# self-consistency-tests).


def test_floor_standard_matches_the_documented_projection() -> None:
    """The Standard floor: seven always artifacts, two signal-gated, five when-produced."""
    entries = {e.name: e.requirement for e in registry.floor("standard")}

    always = {
        "TASK_BRIEF.md",
        "SYSTEMS_PLAN.md",
        "IMPLEMENTATION_PLAN.md",
        "WIP.md",
        "LEARNINGS.md",
        "TEST_BASELINE.md",
        "VERIFICATION_REPORT.md",
    }
    for name in always:
        assert entries[name] == "always", f"{name}: expected always, got {entries.get(name)!r}"

    assert entries["TEST_RESULTS.md"] == registry.Signal.TESTS_RAN
    assert entries["traceability.yml"] == registry.Signal.SDD_ACTIVE

    produced = {
        "RESEARCH_FINDINGS.md",
        "SPEC_DELTA.md",
        "CONTEXT_REVIEW.md",
        "INTERFACE_DESIGN.md",
        "TRANSACTIONS_DESIGN.md",
    }
    for name in produced:
        assert entries[name] == registry.Signal.PRODUCED, f"{name}: expected 'when produced'"


def test_floor_full_promotes_traceability_to_always_and_matches_standard_otherwise() -> None:
    """Full = Standard with exactly one promotion — no other entry may diverge."""
    standard = {e.name: e.requirement for e in registry.floor("standard")}
    full = {e.name: e.requirement for e in registry.floor("full")}

    assert set(full) == set(standard), (
        "full floor must cover exactly the same artifact names as standard"
    )
    assert full["traceability.yml"] == "always"
    for name, requirement in standard.items():
        if name == "traceability.yml":
            continue
        assert full[name] == requirement, (
            f"{name}: full requirement {full[name]!r} diverges from standard "
            f"{requirement!r} outside the documented traceability.yml promotion"
        )


def test_floor_construction_rejects_full_weaker_than_standard() -> None:
    """A Full requirement weaker than its Standard counterpart is illegal at construction."""
    with pytest.raises(ValueError, match="weaker"):
        registry.Floor(standard="always", full=registry.Signal.TESTS_RAN)


def test_signal_holds_tests_ran_true_when_baseline_present_without_marker(
    tmp_path: Path,
) -> None:
    task_dir = tmp_path / "task"
    task_dir.mkdir()
    (task_dir / "TEST_BASELINE.md").write_text("clean baseline @ abc1234\n", encoding="utf-8")
    assert registry.signal_holds(registry.Signal.TESTS_RAN, task_dir) is True


def test_signal_holds_tests_ran_false_when_baseline_starts_with_no_test_target_marker(
    tmp_path: Path,
) -> None:
    task_dir = tmp_path / "task"
    task_dir.mkdir()
    marker_line = f"{registry.NO_TEST_TARGET_MARKER} @ abc1234\n"
    (task_dir / "TEST_BASELINE.md").write_text(marker_line, encoding="utf-8")
    assert registry.signal_holds(registry.Signal.TESTS_RAN, task_dir) is False


def test_signal_holds_tests_ran_false_when_baseline_absent(tmp_path: Path) -> None:
    task_dir = tmp_path / "task"
    task_dir.mkdir()
    assert registry.signal_holds(registry.Signal.TESTS_RAN, task_dir) is False


# Fixture bodies for the SDD-activation predicate: the literal shape is the
# grammar under test, not a citation of any real spec's requirements.
_PLAN_WITH_REQ_HEADING = (
    "## Requirements\n### REQ-01: Login works\n"  # id-citation-discipline:ignore
)
_PLAN_WITH_REQ_IN_PROSE = (
    "A config task. No `REQ-NN` block is warranted.\n"  # id-citation-discipline:ignore
)


def test_signal_holds_sdd_active_true_for_numbered_requirement_heading(tmp_path: Path) -> None:
    task_dir = tmp_path / "task"
    task_dir.mkdir()
    (task_dir / "SYSTEMS_PLAN.md").write_text(_PLAN_WITH_REQ_HEADING, encoding="utf-8")
    assert registry.signal_holds(registry.Signal.SDD_ACTIVE, task_dir) is True


def test_signal_holds_sdd_active_false_for_prose_only_mention(tmp_path: Path) -> None:
    task_dir = tmp_path / "task"
    task_dir.mkdir()
    (task_dir / "SYSTEMS_PLAN.md").write_text(_PLAN_WITH_REQ_IN_PROSE, encoding="utf-8")
    assert registry.signal_holds(registry.Signal.SDD_ACTIVE, task_dir) is False


def test_signal_holds_sdd_active_false_when_plan_absent(tmp_path: Path) -> None:
    task_dir = tmp_path / "task"
    task_dir.mkdir()
    assert registry.signal_holds(registry.Signal.SDD_ACTIVE, task_dir) is False


def test_signal_holds_produced_is_undecidable_from_files(tmp_path: Path) -> None:
    """A 'when produced' signal is declarative — the registry never guesses at it."""
    task_dir = tmp_path / "task"
    task_dir.mkdir()
    assert registry.signal_holds(registry.Signal.PRODUCED, task_dir) is None


def test_no_test_target_marker_is_documented_in_planner_agent() -> None:
    """The paired site: the planner must write the exact marker the registry checks for."""
    text = _read("agents/implementation-planner.md")
    assert f"{registry.NO_TEST_TARGET_MARKER} @ <sha>" in text


def test_task_brief_floor_entry_is_standard_always_and_bound_to_p06() -> None:
    """TASK_BRIEF's floor entry and its P06 detection gate must never drift apart."""
    entries = {e.name: e.requirement for e in registry.floor("standard")}
    assert entries["TASK_BRIEF.md"] == "always"
    assert registry.by_name("TASK_BRIEF.md").detection_gate == "sentinel:P06"


def test_floor_projection_only_returns_registered_artifact_names() -> None:
    """Canary: floor() output must always be a subset of the registry's known names."""
    known = registry.all_names()
    for tier in ("standard", "full"):
        names = {e.name for e in registry.floor(tier)}
        unknown = names - known
        assert not unknown, f"{tier}: floor() named unregistered artifact(s) {sorted(unknown)}"


def test_produced_floor_entries_have_a_producer_production_gate() -> None:
    """A 'when produced' floor entry with no producer:<agent> gate can never be checked."""
    for a in registry.ARTIFACTS:
        if a.floor is None:
            continue
        for requirement in (a.floor.standard, a.floor.full):
            if requirement is registry.Signal.PRODUCED:
                assert a.production_gate.startswith("producer:"), (
                    f"{a.name}: floor entry is 'when produced' but production_gate="
                    f"{a.production_gate!r} does not name a producer"
                )


def test_standard_always_floor_entries_have_a_real_production_gate() -> None:
    """A Standard-always floor entry with a hollow gate has no enforcement mechanism."""
    gateless = {"none", "deferred"}
    for a in registry.ARTIFACTS:
        if a.floor is None or a.floor.standard != "always":
            continue
        kind = a.production_gate.split(":")[0]
        assert kind not in gateless, (
            f"{a.name}: Standard-always floor entry has ungated production_gate "
            f"({a.production_gate!r})"
        )


_FLOOR_TABLE_ROW_RE = re.compile(
    r"^\|\s*([A-Za-z0-9_]+\.(?:md|ya?ml))\s*\|\s*([a-z-]+)\s*\|\s*([a-z-]+)\s*\|\s*$",
    re.MULTILINE,
)


def _requirement_label(requirement: object) -> str:
    """'always' stays 'always'; a Signal enum member becomes its string value."""
    return requirement if isinstance(requirement, str) else requirement.value


def test_inventory_floor_table_matches_registry_projection() -> None:
    """The LLM-readable copy in artifact-inventory.md must equal the registry's own floor.

    Expected table shape (one row per floor artifact, `| name | standard | full |`):

        ### Per-tier artifact floor

        | Artifact | Standard | Full |
        |---|---|---|
        | TASK_BRIEF.md | always | always |
        ...
    """
    text = _read("skills/software-planning/references/artifact-inventory.md")
    assert "### Per-tier artifact floor" in text, (
        "artifact-inventory.md is missing the '### Per-tier artifact floor' table"
    )
    table = text.split("### Per-tier artifact floor", 1)[1]
    rows = {m.group(1): (m.group(2), m.group(3)) for m in _FLOOR_TABLE_ROW_RE.finditer(table)}

    expected_standard = {
        e.name: _requirement_label(e.requirement) for e in registry.floor("standard")
    }
    expected_full = {e.name: _requirement_label(e.requirement) for e in registry.floor("full")}

    assert set(rows) == set(expected_standard), (
        f"table artifact set {sorted(rows)} != registry floor projection "
        f"{sorted(expected_standard)}"
    )
    for name, (std_label, full_label) in rows.items():
        assert std_label == expected_standard[name], (
            f"{name}: table Standard={std_label!r} != registry {expected_standard[name]!r}"
        )
        assert full_label == expected_full[name], (
            f"{name}: table Full={full_label!r} != registry {expected_full[name]!r}"
        )
