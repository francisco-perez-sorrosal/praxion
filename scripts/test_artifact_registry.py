"""Drift gate for the canonical artifact registry (scripts/artifact_registry.py).

The four hard-coded `.ai-work/<slug>/` artifact lists must agree with the
registry's projection for their consumer. This test is that gate.

Gate-liveness contract: a gate must be proven to bite on a known-bad input, not
merely pass on the current good state. The canaries below feed synthetic drifted
consumer text (a stale `SKILL_GENESIS_REPORT.md`; a dropped required artifact)
and assert the comparison the live tests make would FAIL — so a future edit that
re-introduces drift in any of the four consumers turns this suite red.

The dashboard, precompact hook, and eval consumers are parsed from source text
(no imports), so the gate works uniformly across the hook, the eval package, and
the TypeScript dashboard module. build_doc_manifest is the exception: since R18 it
*imports* the registry, so it is verified by reading its effective list rather
than parsing a literal that no longer exists.
"""

from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path
from typing import Any

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


def _load_build_doc_manifest() -> Any:
    """Load build_doc_manifest.py — which imports the registry (R18) — by path.

    Runs after `_load_registry` so its `from artifact_registry import ...` resolves
    to the already-loaded module in sys.modules.
    """
    path = Path(__file__).resolve().parent / "build_doc_manifest.py"
    spec = importlib.util.spec_from_file_location("build_doc_manifest", path)
    assert spec is not None
    assert spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


bdm = _load_build_doc_manifest()


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


def _build_doc_manifest_ai_work() -> set[str]:
    # build_doc_manifest now *imports* the registry (R18); read its effective list
    # rather than parsing a literal that no longer exists in source.
    return set(bdm._AI_WORK_FILES)


def _dashboard_workshop() -> set[str]:
    text = _read("dashboard_app/src/server/artifacts/files.ts")
    return _filenames(_bracketed_block(text, "CANONICAL_WORKSHOP_ARTIFACTS: string[] =", "[", "]"))


def _precompact_pipeline_docs() -> set[str]:
    text = _read("hooks/precompact_state.py")
    return _filenames(_bracketed_block(text, "PIPELINE_DOCS", "[", "]"))


def _eval_standard_required() -> set[str]:
    text = _read("eval/src/praxion_evals/harness/task_manifest.py")
    block = _bracketed_block(text, "_STANDARD_REQUIRED", "(", ")")
    return {Path(m.group(1)).name for m in _PATH_RE.finditer(block)}


def _eval_standard_conditional() -> set[str]:
    text = _read("eval/src/praxion_evals/harness/task_manifest.py")
    block = _bracketed_block(text, "_STANDARD_CONDITIONAL", "(", ")")
    return {Path(m.group(1)).name for m in _PATH_RE.finditer(block)}


# -- Live drift assertions ----------------------------------------------------


def test_build_doc_manifest_matches_registry_dashboard_set() -> None:
    assert _build_doc_manifest_ai_work() == registry.dashboard_artifacts()


def test_build_doc_manifest_reads_registry_in_flow_order() -> None:
    # R18: build_doc_manifest imports dashboard_artifacts_ordered(); the manifest
    # relies on pipeline-flow order, so the list (not just the set) must match.
    assert bdm._AI_WORK_FILES == registry.dashboard_artifacts_ordered()


def test_dashboard_workshop_matches_registry_dashboard_set() -> None:
    assert _dashboard_workshop() == registry.dashboard_artifacts()


def test_doc_manifest_and_dashboard_agree() -> None:
    # The two render surfaces must list exactly the same discoverable set.
    assert _build_doc_manifest_ai_work() == _dashboard_workshop()


def test_precompact_matches_registry_snapshot_set() -> None:
    assert _precompact_pipeline_docs() == registry.snapshot_artifacts()


def test_eval_standard_required_matches_registry() -> None:
    assert _eval_standard_required() == registry.eval_required("standard")


def test_eval_standard_conditional_matches_registry() -> None:
    assert _eval_standard_conditional() == registry.eval_conditional("standard")


def test_every_consumer_filename_is_registered() -> None:
    # No consumer may list an artifact the registry does not know — catches the
    # dead SKILL_GENESIS_REPORT.md class of drift in either direction.
    known = registry.all_names()
    for label, names in (
        ("build_doc_manifest", _build_doc_manifest_ai_work()),
        ("dashboard", _dashboard_workshop()),
        ("precompact", _precompact_pipeline_docs()),
        ("eval-required", _eval_standard_required()),
        ("eval-conditional", _eval_standard_conditional()),
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


def test_canary_eval_drops_learnings_would_fail() -> None:
    """If the eval manifest drops a required deliverable, the gate bites."""
    drifted = '_STANDARD_REQUIRED = (\n  ArtifactSpec(path=".ai-work/{slug}/WIP.md"),\n)'
    block = _bracketed_block(drifted, "_STANDARD_REQUIRED", "(", ")")
    items = {Path(m.group(1)).name for m in _PATH_RE.finditer(block)}
    assert registry.eval_required("standard") - items  # LEARNINGS etc. missing
    assert items != registry.eval_required("standard")


# -- Registry self-consistency ------------------------------------------------


def test_registry_names_are_unique() -> None:
    names = [a.name for a in registry.ARTIFACTS]
    assert len(names) == len(set(names))


def test_eval_flags_imply_eval_tier() -> None:
    for a in registry.ARTIFACTS:
        if a.eval_required or a.eval_conditional:
            assert a.eval_tier is not None, f"{a.name}: eval flag without eval_tier"
        # An artifact is required XOR conditional, never both.
        assert not (a.eval_required and a.eval_conditional), f"{a.name}: required and conditional"


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
        assert (
            kind in registry._GATE_KINDS
        ), f"{a.name}: production_gate kind {kind!r} not in _GATE_KINDS"


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
        assert (
            a.cleanup_policy in registry._CLEANUP_POLICIES
        ), f"{a.name}: cleanup_policy {a.cleanup_policy!r} not in _CLEANUP_POLICIES"


def test_detection_gate_kind_is_known() -> None:
    """Every artifact's detection_gate names a kind in the detection vocabulary."""
    for a in registry.ARTIFACTS:
        kind = a.detection_gate.split(":")[0]
        assert (
            kind in registry._DETECTION_GATE_KINDS
        ), f"{a.name}: detection_gate kind {kind!r} not in _DETECTION_GATE_KINDS"


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
    assert (
        kind not in registry._GATE_KINDS
    ), f"'bogus' should never be a valid gate kind; _GATE_KINDS={registry._GATE_KINDS!r}"
