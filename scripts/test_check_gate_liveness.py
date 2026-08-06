"""Canaries for the Gate Liveness detector (GL02, GL04, GL05).

Cites: rules/swe/gate-liveness.md — a CODE gate ships a canary proving it fails on
a known-bad input, not merely passes on the current good state. These tests feed
the detector deliberately bad fixtures and assert it flags them.

Each canary is paired with an inverse guard, because this detector's failure mode
runs both ways: missing a real orphan is a silent false all-clear, and flagging a
correctly wired gate would make the whole dimension untrustworthy on first use.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import check_gate_liveness as gl  # noqa: E402


def _write(root: Path, rel: str, body: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body)


def test_flags_dead_grep_contradiction(tmp_path: Path) -> None:
    """A canary: an instruction greps test files for a forbidden REQ test-name."""
    _write(
        tmp_path,
        "agents/planner.md",
        "At checkpoints, scan test files for req33_ patterns to find untested REQs.",
    )
    findings = gl.check_forbidden_pattern(tmp_path)
    assert findings, "GL02 must flag a grep for a pattern forbidden in test files"
    assert findings[0]["check"] == "forbidden-pattern"


def test_accepts_traceability_read_instead_of_grep(tmp_path: Path) -> None:
    """Happy path: reading the traceability file (not grepping code) is fine."""
    _write(
        tmp_path,
        "agents/planner.md",
        "At checkpoints, read traceability.yml to find REQs with empty tests lists.",
    )
    assert gl.check_forbidden_pattern(tmp_path) == []


def test_forbidden_pattern_respects_ignore_escape(tmp_path: Path) -> None:
    """A line marked gate-liveness:ignore is a deliberate reference, not a gate."""
    _write(
        tmp_path,
        "agents/doc.md",
        "Detectors may scan test code for req10_ shapes. gate-liveness:ignore",
    )
    assert gl.check_forbidden_pattern(tmp_path) == []


def test_excludes_pattern_defining_files(tmp_path: Path) -> None:
    """The defining rules describe the forbidden patterns; they are not dead gates."""
    _write(
        tmp_path,
        "rules/swe/id-citation-discipline.md",
        "Never scan test files for req33_ — this rule forbids it.",
    )
    assert gl.check_forbidden_pattern(tmp_path) == []


# The bad-case GL02's own definition promises it catches. Kept as one literal so
# the doc and the canary cannot drift apart: if this stops firing, the sentence
# telling a reader the gate bites has become false.
_GOLDEN_BAD_CASE = "a checkpoint that searches test names for req33_ prefixes"


def test_canary_the_documented_golden_bad_case_fires(tmp_path: Path) -> None:
    """A gate nobody has seen fail is indistinguishable from no gate.

    GL02 is documented with a golden bad-case — "a checkpoint that searches test
    names for a REQ-id prefix the citation rule bans". Feeding that sentence back
    to the detector is the whole proof-it-bites, and it did not fire: the verb was
    written inflected ("searches"), and only the bare stem was matched.
    """
    _write(tmp_path, "agents/planner.md", _GOLDEN_BAD_CASE)
    findings = gl.check_forbidden_pattern(tmp_path)
    assert findings, f"GL02's documented golden bad-case must fire: {_GOLDEN_BAD_CASE!r}"
    assert findings[0]["check"] == "forbidden-pattern"


def test_canary_inflected_scan_verbs_are_not_invisible(tmp_path: Path) -> None:
    """Prose writes the directive inflected; matching only bare stems misses it."""
    for verb in ("scan", "scans", "scanned", "greps", "searches", "searching", "matched"):
        _write(tmp_path, "agents/planner.md", f"the checkpoint {verb} test files for req33_ names")
        assert gl.check_forbidden_pattern(tmp_path), f"inflected verb {verb!r} must still fire"


def test_a_bare_look_without_for_is_not_a_scan_directive(tmp_path: Path) -> None:
    """Inverse guard: widening the verbs must not make every mention of a REQ a hit."""
    _write(tmp_path, "agents/planner.md", "Reviewers look at the test plan; req33_ is legacy.")
    assert gl.check_forbidden_pattern(tmp_path) == []


def _findings_under(parent: Path) -> list[dict]:
    """Write one identical bad corpus under ``parent`` and scan it."""
    root = parent / "repo"
    _write(root, "rules/dead.md", _GOLDEN_BAD_CASE)
    _write(root, "rules/swe/id-citation-discipline.md", "Never scan test code for req33_.")
    return gl.check_forbidden_pattern(root)


def test_canary_findings_are_invariant_under_relocation(tmp_path: Path) -> None:
    """Identical bytes at identical repo-relative paths must yield identical findings.

    The exclusion list was matched against the *absolute* path, so a checkout whose
    directory name happened to contain an exclusion substring silently excluded
    every file in the repository — the detector reported clean and exited 0 on a
    corpus it flags anywhere else. A managed project's path differs by definition,
    so the verdict was a property of the disk, not of the code under scan.
    """
    neutral = _findings_under(tmp_path / "neutral")
    poisoned = _findings_under(tmp_path / "gate-liveness")

    assert neutral, "precondition: the corpus must be flagged at a neutral path"
    assert [f["file"] for f in poisoned] == [f["file"] for f in neutral], (
        "relocation changed the verdict — exclusions are matching the absolute path"
    )


def test_exclusions_still_apply_by_repo_relative_path(tmp_path: Path) -> None:
    """Inverse guard: the defining rule stays excluded, poisoned parent or not."""
    findings = _findings_under(tmp_path / "gate-liveness")
    assert [f["file"] for f in findings] == ["rules/dead.md"], (
        "the pattern-defining rule must remain excluded by its repo-relative path"
    )


def test_flags_a_gate_script_nothing_invokes(tmp_path: Path) -> None:
    """A canary: a gate written, tested, and called by nothing.

    The live instance this was written against had a docstring naming the
    dimension that invoked it, and that dimension called a different module
    entirely -- so the file had never executed, which is also why nobody had
    noticed it could not.
    """
    _write(tmp_path, "scripts/check_orphan.py", "# a gate nothing calls\n")
    _write(tmp_path, "scripts/test_check_orphan.py", "import check_orphan\n")
    findings = gl.check_uninvoked_gate(tmp_path)
    assert [f["file"] for f in findings] == ["scripts/check_orphan.py"]
    assert findings[0]["check"] == "uninvoked-gate"


def test_a_gate_invoked_from_pre_commit_is_not_flagged(tmp_path: Path) -> None:
    """The inverse guard: a wired gate must stay silent."""
    _write(tmp_path, "scripts/check_wired.py", "# a gate\n")
    _write(tmp_path, ".pre-commit-config.yaml", "entry: python3 scripts/check_wired.py\n")
    assert gl.check_uninvoked_gate(tmp_path) == []


def test_a_gate_imported_by_a_sibling_script_is_not_flagged(tmp_path: Path) -> None:
    """One gate driving another is a real invocation, and it names the module stem.

    Matching only the filename reports these as orphans -- the false positive
    that would have condemned a gate this project had just finished wiring.
    """
    _write(tmp_path, "scripts/validate_thing.py", "# a library-style gate\n")
    _write(tmp_path, "scripts/detector.py", "from validate_thing import parse\n")
    assert gl.check_uninvoked_gate(tmp_path) == []


# -- GL05: ambient-import ------------------------------------------------------


def _invokes(root: Path, target: str) -> None:
    """An agent instructing a model to run `target` through the ambient shell."""
    _write(root, "agents/auditor.md", f"Run `python3 {target} --json` and emit its rows.\n")


def test_canary_flags_a_gate_the_ambient_interpreter_cannot_load(tmp_path: Path) -> None:
    """A gate that dies on import catches nothing, and its own tests never say so."""
    _write(tmp_path, "scripts/check_thing.py", "import yaml\n")
    _invokes(tmp_path, "scripts/check_thing.py")
    findings = gl.check_ambient_import(tmp_path)
    assert [f["file"] for f in findings] == ["scripts/check_thing.py"]
    assert "yaml" in findings[0]["evidence"]


def test_canary_flags_a_third_party_import_reached_through_a_sibling(tmp_path: Path) -> None:
    """The live shape: the invoked script is clean and its sibling is not.

    A direct-imports-only scan reports this clean, which is how the real
    instance survived a line-by-line reading of the invoked script.
    """
    _write(tmp_path, "scripts/check_wrapper.py", "from spec_lib import detect\n")
    _write(tmp_path, "scripts/spec_lib.py", "import yaml\n\n\ndef detect():\n    return []\n")
    _invokes(tmp_path, "scripts/check_wrapper.py")
    findings = gl.check_ambient_import(tmp_path)
    assert [f["file"] for f in findings] == ["scripts/check_wrapper.py"]
    assert "yaml" in findings[0]["evidence"]


def test_canary_a_fallback_import_in_the_handler_is_still_checked(tmp_path: Path) -> None:
    """An `except ImportError` fallback is not a guard — it can fail identically.

    Pins the live instance's exact shape: a dual-mode import where the handler
    branch is what actually runs standalone. Treating the whole `try` as guarded
    would excuse precisely the file that motivated this check.
    """
    _write(
        tmp_path,
        "scripts/check_wrapper.py",
        "try:\n"
        "    from scripts.spec_lib import detect\n"
        "except ModuleNotFoundError:\n"
        "    from spec_lib import detect\n",
    )
    _write(tmp_path, "scripts/spec_lib.py", "import yaml\n\n\ndef detect():\n    return []\n")
    _invokes(tmp_path, "scripts/check_wrapper.py")
    assert [f["file"] for f in gl.check_ambient_import(tmp_path)] == ["scripts/check_wrapper.py"]


def test_a_stdlib_only_gate_is_not_flagged(tmp_path: Path) -> None:
    """The inverse guard — the shape almost every live gate already has."""
    _write(tmp_path, "scripts/check_thing.py", "import json\nfrom pathlib import Path\n")
    _invokes(tmp_path, "scripts/check_thing.py")
    assert gl.check_ambient_import(tmp_path) == []


def test_a_guarded_import_is_not_flagged(tmp_path: Path) -> None:
    """Handling the absence is the documented remedy, not a defect."""
    _write(
        tmp_path,
        "scripts/check_thing.py",
        "try:\n    import yaml\nexcept ImportError:\n    yaml = None\n",
    )
    _invokes(tmp_path, "scripts/check_thing.py")
    assert gl.check_ambient_import(tmp_path) == []


def test_a_sibling_module_is_not_mistaken_for_a_package(tmp_path: Path) -> None:
    """First-party modules ship with the gate, so they are always loadable."""
    _write(tmp_path, "scripts/check_thing.py", "from _repo_root import resolve\n")
    _write(tmp_path, "scripts/_repo_root.py", "def resolve():\n    return None\n")
    _invokes(tmp_path, "scripts/check_thing.py")
    assert gl.check_ambient_import(tmp_path) == []


def test_an_invocation_that_resolves_its_own_interpreter_is_out_of_scope(
    tmp_path: Path,
) -> None:
    """Documented scope is agent and command prose; hooks resolve an interpreter.

    Scope fidelity runs both ways. This asserts the computed scope is no *wider*
    than the documented one, so the check cannot quietly start reporting call
    sites whose hazard its own scope note disclaims.
    """
    _write(tmp_path, "scripts/check_thing.py", "import yaml\n")
    _write(tmp_path, "hooks/run.sh", "python3 scripts/check_thing.py\n")
    assert gl.check_ambient_import(tmp_path) == []


# -- GL04 (cont.): hook guards and gates belong to the same inventory ---------


def test_canary_flags_a_hook_guard_no_registration_names(tmp_path: Path) -> None:
    """A hook guard nothing registers is as inert as an uninvoked script gate.

    Hook gates were outside this inventory only because `hooks/` is excluded from
    `ambient-import` — two different scopes (candidate gates vs. call sites) that
    one exclusion was standing in for.
    """
    _write(tmp_path, "hooks/policy_guard.py", "# a guard nothing registers\n")
    _write(tmp_path, "hooks/hooks.json", '{"hooks": {}}\n')
    findings = gl.check_uninvoked_gate(tmp_path)
    assert [f["file"] for f in findings] == ["hooks/policy_guard.py"]
    assert findings[0]["check"] == "uninvoked-gate"


def test_a_hook_guard_named_in_the_registrations_is_not_flagged(tmp_path: Path) -> None:
    """Inverse guard: a registered guard is wired, and must stay silent."""
    _write(tmp_path, "hooks/policy_guard.py", "# a guard\n")
    _write(
        tmp_path,
        "hooks/hooks.json",
        '{"hooks": {"PreToolUse": [{"hooks": [{"command": "python3 hooks/policy_guard.py"}]}]}}\n',
    )
    assert gl.check_uninvoked_gate(tmp_path) == []


def test_canary_a_shell_gate_is_not_excused_by_its_own_python_test(tmp_path: Path) -> None:
    """A `.sh` gate's test is `test_<stem>.py`, so the filename form matched nothing.

    The exclusion that keeps a gate's own tests from counting as invocation was
    built as `test_{gate.name}` — `test_audit_gate.sh` for a shell gate, which no
    file is ever called. The real test file therefore read as a live call site and
    excused the orphan it was written for.
    """
    _write(tmp_path, "hooks/audit_gate.sh", "# a shell gate nothing registers\n")
    _write(tmp_path, "hooks/test_audit_gate.py", "import subprocess  # runs audit_gate.sh\n")
    findings = gl.check_uninvoked_gate(tmp_path)
    assert [f["file"] for f in findings] == ["hooks/audit_gate.sh"]


# -- discarded-verdict: is the gate's verdict read? ----------------------------

_EXITS_ON_FINDINGS = "import sys\n\nif findings:\n    sys.exit(1)\n"


def _registers(root: Path, command: str, event: str = "PreToolUse") -> None:
    """Write a hooks.json registering `command` under `event`."""
    _write(
        root,
        "hooks/hooks.json",
        json.dumps({"hooks": {event: [{"matcher": "", "hooks": [{"command": command}]}]}}),
    )


def test_canary_flags_a_hook_whose_findings_exit_cannot_block(tmp_path: Path) -> None:
    """A canary: a gate detects perfectly and its verdict is thrown away.

    Claude Code blocks on exit 2 and on nothing else, so a gate returning the
    POSIX-natural 1-on-findings through a bare registration is computed and
    discarded. This is the live shape `hooks/commit_gate.sh` was written against.
    """
    _write(tmp_path, "hooks/policy_gate.py", _EXITS_ON_FINDINGS)
    _registers(tmp_path, "python3 hooks/policy_gate.py")
    findings = gl.check_discarded_verdict(tmp_path)
    assert [f["file"] for f in findings] == ["hooks/policy_gate.py"]
    assert findings[0]["check"] == "discarded-verdict"


def test_canary_a_findings_exit_reached_through_main_is_still_detected(tmp_path: Path) -> None:
    """`sys.exit(main())` over a `main()` returning 1 is this repo's dominant gate shape.

    A literals-only scan sees no exit code at all here and reports the gate as
    carrying no verdict — a silent pass precisely where the check must bite.
    """
    _write(
        tmp_path,
        "hooks/policy_gate.py",
        "import sys\n\n\ndef main():\n    return 1\n\n\nsys.exit(main())\n",
    )
    _registers(tmp_path, "python3 hooks/policy_gate.py")
    assert [f["file"] for f in gl.check_discarded_verdict(tmp_path)] == ["hooks/policy_gate.py"]


def test_a_gate_routed_through_the_blocking_adapter_is_not_flagged(tmp_path: Path) -> None:
    """Inverse guard: `--blocking` translates 1 -> 2, so the verdict does reach a decision."""
    _write(tmp_path, "scripts/check_policy.py", _EXITS_ON_FINDINGS)
    _registers(tmp_path, "hooks/commit_gate.sh --blocking scripts/check_policy.py")
    assert gl.check_discarded_verdict(tmp_path) == []


def test_a_hook_that_exits_two_directly_is_not_flagged(tmp_path: Path) -> None:
    """Inverse guard: exiting 2 itself needs no adapter."""
    _write(tmp_path, "hooks/policy_guard.py", "import sys\n\nif denied:\n    sys.exit(2)\n")
    _registers(tmp_path, "python3 hooks/policy_guard.py")
    assert gl.check_discarded_verdict(tmp_path) == []


def test_a_deliberately_advisory_reminder_is_not_flagged(tmp_path: Path) -> None:
    """The inverse guard that decides whether this check is usable at all.

    Advisory hooks are the majority of every registration file, and flagging them
    would make the check fire on correct code. It stays silent because such a hook
    has no findings exit to discard — a property of the code, not an exemption
    carved for it, so the silence cannot rot as the hook set grows.
    """
    _write(tmp_path, "hooks/remind_thing.py", "print('consider recording a decision')\n")
    _registers(tmp_path, "python3 hooks/remind_thing.py")
    assert gl.check_discarded_verdict(tmp_path) == []


def test_a_registration_on_an_event_with_no_blocking_path_is_out_of_scope(tmp_path: Path) -> None:
    """Scope fidelity, the narrowing direction: no remedy exists, so no finding.

    `SessionStart` has no blocking exit code at all. Reporting a findings exit
    there would name a defect the author cannot fix, which trains a reader to
    ignore every row the check emits.
    """
    _write(tmp_path, "hooks/policy_gate.py", _EXITS_ON_FINDINGS)
    _registers(tmp_path, "python3 hooks/policy_gate.py", event="SessionStart")
    assert gl.check_discarded_verdict(tmp_path) == []


def test_a_repository_with_no_hook_registrations_yields_nothing(tmp_path: Path) -> None:
    """A managed project has no hooks.json; absence is not a finding."""
    _write(tmp_path, "scripts/check_policy.py", _EXITS_ON_FINDINGS)
    assert gl.check_discarded_verdict(tmp_path) == []


def test_the_live_repo_discards_no_gate_verdict() -> None:
    """The named consumer for `discarded-verdict`, per the rule's clause 6.

    A gate that computes a verdict no document, check, or decision point is named
    to read is the defect this whole check exists to catch — so shipping it with
    only fixture tests would make it the next instance of its own finding. This
    assertion is that reader: it runs against the real repository on every root
    suite run, and a discarded verdict reddens it.
    """
    repo_root = Path(__file__).resolve().parents[1]
    findings = gl.check_discarded_verdict(repo_root)
    assert findings == [], (
        "a registered gate's findings exit cannot reach a decision:\n"
        + "\n".join(f"  - {f['file']}: {f['why']}" for f in findings)
    )


def test_cli_exits_nonzero_on_findings(tmp_path: Path) -> None:
    """A canary for the exit-code gate contract: bad input → exit 1."""
    _write(tmp_path, "agents/planner.md", "scan test files for req33_ patterns.")
    assert gl.main(["--root", str(tmp_path), "--check", "forbidden-pattern"]) == 1


def test_cli_exits_zero_when_clean(tmp_path: Path) -> None:
    """Happy path: a clean corpus exits 0."""
    _write(tmp_path, "agents/planner.md", "Read traceability.yml for coverage.")
    assert gl.main(["--root", str(tmp_path), "--check", "all"]) == 0
