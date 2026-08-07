"""Structural invariants for the ci-autofix hub's package-manager-aware install.

Covers the `JS_PM_INSTALL` table (keyed on a package manager detected from
the trusted default-branch lockfile), `detect_pm`'s directory scoping and
pnpm > yarn > npm precedence, the non-agent install step's own robustness
contract (`id`, `continue-on-error`, corepack prompt suppression,
`--ignore-scripts`), and the fixer step's gate on the install outcome.

Several assertions here execute the classify step's embedded Python script
directly — extracted from its `run:` text into a temp file and run against a
fixture directory — rather than pattern-matching source text. That is the
strongest available proxy for "detection reads the declared project dir, not
wherever the job happens to run", since that is precisely the mechanism the
#48 dogfood broke.

Scope note: this suite verifies structure — parsed YAML shape, string/regex
presence of required steps and gates. It cannot verify runtime behavior (what
actually happens on a live run); where a test is a structural proxy for a
runtime guarantee, its docstring says so explicitly, and the guarantee closes
via dogfooding once Praxion's own caller exercises the hub in production CI.

Every test reads the workflow lazily (inside the function body, never at module
import time) so collection succeeds even when the file is absent — an absent
hub then fails with a clear assertion, never an import error.

Sibling modules covering the same workflow file:
`test_ci_autofix_hub_contract.py` (file-wide interface/security contract),
`test_ci_autofix_hub_surfaces.py` (classify / same-repo-pr / fork jobs),
`test_ci_autofix_hub_finalize.py` (green-decline finalize step),
`test_ci_autofix_hub_js_runner.py` (policy-gated JS/TS runner grant),
`test_ci_autofix_hub_pm_install.py` (package-manager detection + install step).
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]
HUB_WORKFLOW_FILE = PROJECT_ROOT / ".github" / "workflows" / "reusable-ci-autofix.yml"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _raw_text() -> str:
    """Return the hub workflow's raw file content (read lazily so collection succeeds)."""
    return HUB_WORKFLOW_FILE.read_text(encoding="utf-8")


def _parsed() -> dict:
    """Parse the hub workflow as YAML."""
    return yaml.safe_load(_raw_text())


def _all_steps(parsed: dict) -> list[dict]:
    """Flatten every step across every job in the workflow."""
    steps: list[dict] = []
    for job in (parsed.get("jobs") or {}).values():
        steps.extend(job.get("steps") or [])
    return steps


def _uses_refs(parsed: dict) -> list[str]:
    """Collect every `uses:` value across every job/step in the workflow."""
    return [step["uses"] for step in _all_steps(parsed) if step.get("uses")]


def _job(parsed: dict, name: str) -> dict:
    """Return a named job's body, or `{}` if the job doesn't exist yet (RED-safe)."""
    return (parsed.get("jobs") or {}).get(name) or {}


def _agent_steps(job: dict) -> list[dict]:
    """Return every `claude-code-action` step within a single job."""
    return [
        step for step in job.get("steps") or [] if "claude-code-action" in (step.get("uses") or "")
    ]


def _classify_step(job: dict) -> dict | None:
    """Return the `classify` job's `id: classify` step, or `None` if absent."""
    return next((step for step in job.get("steps") or [] if step.get("id") == "classify"), None)


def _classify_run_text(parsed: dict) -> str:
    """Return the classify job's `classify` step `run:` text (empty string
    if the step is absent — RED-safe)."""
    classify_step = _classify_step(_job(parsed, "classify"))
    return (classify_step.get("run") if classify_step else "") or ""


def _terms_co_occur(text: str, term_a: str, term_b: str, window: int = 60) -> bool:
    """True if the literal strings `term_a` and `term_b` co-occur within
    `window` chars of each other, either order."""
    pattern = re.compile(
        rf"({re.escape(term_a)}.{{0,{window}}}{re.escape(term_b)}|"
        rf"{re.escape(term_b)}.{{0,{window}}}{re.escape(term_a)})",
        re.DOTALL,
    )
    return bool(pattern.search(text))


def _extract_classify_script(run: str) -> str:
    """Extract the embedded Python heredoc body from the classify step's
    `run:` shell text (the part between `<<'PY'` and the closing `PY`)."""
    match = re.search(r"<<'PY'\n(.*?)\nPY\b", run, re.DOTALL)
    return match.group(1) if match else ""


def _run_classify_script(tmp_path: Path, *, policy: dict) -> dict[str, str]:
    """Execute the classify step's embedded Python script against `policy`,
    with `tmp_path` as its working directory — mirroring the real job, whose
    script runs against the already-checked-out default-branch tree rooted
    at the repo root.

    Any lockfile fixtures must already be seeded under `tmp_path` (optionally
    inside a project-dir-shaped subdirectory) before calling this.
    """
    source = _extract_classify_script(_classify_run_text(_parsed()))
    assert source, "Expected an embedded Python heredoc body in the classify step's run: text"
    script_path = tmp_path / "_classify_script.py"
    script_path.write_text(source, encoding="utf-8")
    policy_path = tmp_path / "autofix-policy.yml"
    policy_path.write_text(yaml.safe_dump(policy), encoding="utf-8")
    result = subprocess.run(
        [sys.executable, str(script_path), str(policy_path)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, (
        f"classify script exited {result.returncode}; stderr:\n{result.stderr}"
    )
    outputs: dict[str, str] = {}
    for line in result.stdout.splitlines():
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        outputs[key] = value
    return outputs


def _install_step(job: dict) -> dict | None:
    """Return the JS/TS install step in a job, or `None` if absent (RED-safe)."""
    for step in job.get("steps") or []:
        name = (step.get("name") or "").lower()
        if "install" in name and re.search(r"js|ts|npm|pnpm|node", name, re.IGNORECASE):
            return step
    return None


# ---------------------------------------------------------------------------
# PM-aware install (autofix-pm-detect) — table split, detect_pm, robustness
#
# RED-phase note: today's classify step still derives js_install_cmd from the
# single coupled JS_RUNNER_TABLE keyed on js_test_runner alone — no lockfile
# detection exists. Assertions below that require actual PM detection are
# expected RED (a pnpm-lock.yaml fixture still yields "npm ci"). A handful are
# explicitly flagged as naturally-satisfied-today regression guards: today's
# code always falls back to "npm ci" regardless of any lockfile fixture, so
# scenarios whose CORRECT answer is also "npm ci" (no lockfile, only
# package-lock.json, or a lockfile sitting outside the declared project dir)
# already pass — they only start proving something once detect_pm lands.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("pm", "expected_row"),
    [
        ("npm", "npm ci"),
        ("pnpm", "corepack enable && pnpm install --frozen-lockfile"),
        ("yarn", "corepack enable && yarn install --frozen-lockfile"),
    ],
)
def test_js_pm_install_row_ends_with_its_install_verb(pm: str, expected_row: str) -> None:
    """Each JS_PM_INSTALL row's value must end with its install verb, so the
    install step's appended ` --ignore-scripts` binds to the right command;
    pnpm/yarn rows are corepack-prefixed, npm's is not.
    """
    run = _classify_run_text(_parsed())
    assert re.search(rf'"{pm}":\s*"{re.escape(expected_row)}"', run), (
        f"Expected JS_PM_INSTALL[{pm!r}] == {expected_row!r} — install verb as "
        "the row's tail, decoupled from the js_test_runner enum"
    )


def test_js_runner_table_yields_runner_only_commands_decoupled_from_install() -> None:
    """After the split, JS_RUNNER_TABLE rows must be runner-only strings (no
    install half) — js_test_grant's vitest derivation must stay byte-identical
    to the pre-split baseline.
    """
    run = _classify_run_text(_parsed())
    assert re.search(r'"vitest":\s*"\./node_modules/\.bin/vitest run"', run), (
        "JS_RUNNER_TABLE['vitest'] must be the runner-only string "
        "'./node_modules/.bin/vitest run' (byte-identical to the pre-split "
        "baseline), not paired with an install command in a tuple"
    )
    assert not re.search(r'"vitest":\s*\(\s*"[^"]*"\s*,', run), (
        "JS_RUNNER_TABLE must no longer pair each runner with an install "
        "command in a tuple — the install half moves to JS_PM_INSTALL"
    )


def test_js_install_cmd_no_longer_derives_from_the_runner_enum_table() -> None:
    """Regression guard against re-coupling the two axes: js_install_cmd must
    no longer be unpacked from JS_RUNNER_TABLE — PM detection must drive it
    independently of the js_test_runner enum.
    """
    run = _classify_run_text(_parsed())
    assert not re.search(r"js_install_cmd\s*,\s*js_runner_cmd\s*=\s*JS_RUNNER_TABLE", run), (
        "js_install_cmd must no longer be unpacked from the coupled JS_RUNNER_TABLE tuple"
    )


def test_js_install_cmd_is_selected_through_the_pm_install_table_not_interpolated() -> None:
    """Injection-safety idiom re-asserted for the new table: js_install_cmd
    must be selected via a closed-table lookup keyed on the detected package
    manager, never an f-string interpolating a value directly into it.
    """
    run = _classify_run_text(_parsed())
    assert "JS_PM_INSTALL[" in run or "JS_PM_INSTALL.get(" in run, (
        "js_install_cmd must be selected via a JS_PM_INSTALL[...] (or "
        ".get(...)) closed-table lookup, keyed on the detected package manager"
    )
    assert not re.search(r'js_install_cmd\s*=\s*f["\']', run), (
        "js_install_cmd must never be produced by f-string-interpolating a "
        "detected/raw value directly — select it through the closed "
        "JS_PM_INSTALL table instead"
    )


def test_detect_pm_is_invoked_with_the_declared_js_project_dir() -> None:
    """detect_pm must be called with js_project_dir as its argument — never a
    bare call with no directory scoping, which would probe the process's
    working directory (repo root) instead of the caller's JS/TS project dir.
    """
    run = _classify_run_text(_parsed())
    assert re.search(r"detect_pm\(\s*js_project_dir\s*\)", run), (
        "Expected a detect_pm(js_project_dir) call — passing the declared "
        "project dir so detection reads the right subdirectory, not repo root"
    )


@pytest.mark.parametrize("lockfile", ["pnpm-lock.yaml", "yarn.lock", "package-lock.json"])
def test_detect_pm_joins_each_lockfile_name_onto_a_directory_variable(lockfile: str) -> None:
    """Each lockfile-presence check must join the filename onto a directory
    variable (e.g. os.path.join(base, "pnpm-lock.yaml")) rather than testing
    a bare, process-CWD-relative literal — a bare check silently probes repo
    root instead of the caller's JS/TS project directory.
    """
    run = _classify_run_text(_parsed())
    assert lockfile in run, f"Expected a {lockfile!r} presence check driving PM detection"
    assert _terms_co_occur(run, "os.path.join(", lockfile, window=60), (
        f"The {lockfile!r} presence check must join the filename onto a "
        "directory variable via os.path.join — a bare literal check would "
        "silently probe the process's working directory (repo root)"
    )


def test_detect_pm_checks_lockfiles_in_pnpm_yarn_npm_precedence_order() -> None:
    """Fixed precedence keeps detection deterministic if a stale second
    lockfile ever reappears alongside the real one.
    """
    run = _classify_run_text(_parsed())
    pnpm_pos = run.find("pnpm-lock.yaml")
    yarn_pos = run.find("yarn.lock")
    npm_pos = run.find("package-lock.json")
    assert pnpm_pos != -1, "Expected a pnpm-lock.yaml presence check"
    assert yarn_pos != -1, "Expected a yarn.lock presence check"
    assert npm_pos != -1, "Expected a package-lock.json presence check"
    assert pnpm_pos < yarn_pos, "pnpm-lock.yaml must be checked before yarn.lock (pnpm > yarn)"
    assert yarn_pos < npm_pos, "yarn.lock must be checked before package-lock.json (yarn > npm)"


def test_pnpm_lockfile_under_the_project_dir_selects_a_pnpm_install(tmp_path: Path) -> None:
    """The highest-value regression guard: detection must probe under the
    caller's js_project_dir, not the process's working directory (repo
    root) — Praxion's own repo root carries no lockfile at all, so a
    root-scoped probe would silently fall back to npm and reproduce the
    original #48 defect.
    """
    project_dir = tmp_path / "dashboard_app"
    project_dir.mkdir()
    (project_dir / "pnpm-lock.yaml").write_text("", encoding="utf-8")
    outputs = _run_classify_script(
        tmp_path,
        policy={"provider": {"js_test_runner": "vitest", "js_project_dir": "dashboard_app"}},
    )
    assert "pnpm install" in outputs.get("js_install_cmd", ""), (
        "Expected a pnpm install command for a pnpm-lock.yaml found under "
        f"js_project_dir; got js_install_cmd={outputs.get('js_install_cmd')!r}"
    )


def test_yarn_lockfile_under_the_project_dir_selects_a_yarn_install(tmp_path: Path) -> None:
    """When no pnpm-lock.yaml is present but yarn.lock is, detection must
    select the yarn install row.
    """
    project_dir = tmp_path / "dashboard_app"
    project_dir.mkdir()
    (project_dir / "yarn.lock").write_text("", encoding="utf-8")
    outputs = _run_classify_script(
        tmp_path,
        policy={"provider": {"js_test_runner": "vitest", "js_project_dir": "dashboard_app"}},
    )
    assert "yarn install" in outputs.get("js_install_cmd", ""), (
        f"Expected a yarn install command; got js_install_cmd={outputs.get('js_install_cmd')!r}"
    )


def test_package_lock_json_under_the_project_dir_selects_npm_ci(tmp_path: Path) -> None:
    """Naturally satisfied today (npm ci is the universal current fallback,
    regardless of any lockfile) — becomes a real regression guard once
    detect_pm's per-PM branching lands: package-lock.json alone must still
    resolve to npm ci, not silently drift to another package manager.
    """
    project_dir = tmp_path / "dashboard_app"
    project_dir.mkdir()
    (project_dir / "package-lock.json").write_text("", encoding="utf-8")
    outputs = _run_classify_script(
        tmp_path,
        policy={"provider": {"js_test_runner": "vitest", "js_project_dir": "dashboard_app"}},
    )
    assert "npm ci" in outputs.get("js_install_cmd", ""), (
        f"Expected npm ci as the install command; got js_install_cmd={outputs.get('js_install_cmd')!r}"
    )


def test_pnpm_lockfile_takes_precedence_over_a_stale_package_lock_json(tmp_path: Path) -> None:
    """Defense-in-depth: fixed precedence (pnpm > yarn > npm) keeps detection
    correct even if a stale second lockfile lingers alongside the real one —
    exactly Praxion's own dashboard_app/ situation pre-cleanup.
    """
    project_dir = tmp_path / "dashboard_app"
    project_dir.mkdir()
    (project_dir / "pnpm-lock.yaml").write_text("", encoding="utf-8")
    (project_dir / "package-lock.json").write_text("", encoding="utf-8")
    outputs = _run_classify_script(
        tmp_path,
        policy={"provider": {"js_test_runner": "vitest", "js_project_dir": "dashboard_app"}},
    )
    assert "pnpm install" in outputs.get("js_install_cmd", ""), (
        "Expected pnpm to win over a stale package-lock.json; got "
        f"js_install_cmd={outputs.get('js_install_cmd')!r}"
    )


def test_no_lockfile_under_the_project_dir_falls_back_to_npm_ci(tmp_path: Path) -> None:
    """Naturally satisfied today (npm ci is the universal current fallback);
    becomes a real regression guard once detect_pm lands, proving its
    fail-safe default still resolves to npm ci rather than raising or
    silently emitting an empty command.
    """
    project_dir = tmp_path / "dashboard_app"
    project_dir.mkdir()
    outputs = _run_classify_script(
        tmp_path,
        policy={"provider": {"js_test_runner": "vitest", "js_project_dir": "dashboard_app"}},
    )
    assert "npm ci" in outputs.get("js_install_cmd", ""), (
        "Expected npm ci as the fail-safe default when no lockfile is present; "
        f"got js_install_cmd={outputs.get('js_install_cmd')!r}"
    )


def test_a_pnpm_lockfile_at_repo_root_is_ignored_when_js_project_dir_points_elsewhere(
    tmp_path: Path,
) -> None:
    """Directly closes the highest-likelihood regression: a lockfile sitting
    at repo root must NOT satisfy detection when js_project_dir points
    elsewhere — detection must probe the declared project dir, never
    wherever the classify job's working directory happens to be. Naturally
    satisfied today (npm ci is the universal current fallback); becomes the
    load-bearing regression guard once detect_pm lands.
    """
    (tmp_path / "pnpm-lock.yaml").write_text("", encoding="utf-8")
    project_dir = tmp_path / "dashboard_app"
    project_dir.mkdir()
    outputs = _run_classify_script(
        tmp_path,
        policy={"provider": {"js_test_runner": "vitest", "js_project_dir": "dashboard_app"}},
    )
    assert "npm ci" in outputs.get("js_install_cmd", ""), (
        "A repo-root lockfile must not be detected when js_project_dir points "
        f"elsewhere; got js_install_cmd={outputs.get('js_install_cmd')!r}"
    )


def test_js_install_cmd_stays_empty_when_the_runner_is_off_even_with_a_lockfile_present(
    tmp_path: Path,
) -> None:
    """Closes the surface-widening invariant: a repo with any lockfile but
    js_test_runner: off must never receive an install command — the
    JS_PM_INSTALL lookup must stay gated on a granted runner, not on
    lockfile presence alone. Naturally satisfied today (the coupled table's
    "off" row already pairs an empty install with an empty runner); becomes
    the regression guard proving the split didn't drop this gate.
    """
    (tmp_path / "pnpm-lock.yaml").write_text("", encoding="utf-8")
    outputs = _run_classify_script(
        tmp_path,
        policy={"provider": {"js_test_runner": "off"}},
    )
    assert outputs.get("js_install_cmd", "") == "", (
        "js_install_cmd must stay empty when js_test_runner is off, "
        f"regardless of lockfile presence; got {outputs.get('js_install_cmd')!r}"
    )


# ---------------------------------------------------------------------------
# Install-step robustness + fixer gate (autofix-pm-detect)
#
# RED-phase note: today's install step has no `id`, no `continue-on-error`,
# and no env block; the fixer step's `if` has no install-outcome clause.
# Two assertions are explicitly flagged as preventive regression guards
# (already true today, must stay true after the change): the install step
# already ends in --ignore-scripts, and the fixer's if already requires the
# budget-proceed flag.
# ---------------------------------------------------------------------------


def test_install_js_deps_step_is_non_agent_and_uses_ignore_scripts() -> None:
    parsed = _parsed()
    job = _job(parsed, "autofix-same-repo-pr")
    install_steps = [
        step
        for step in job.get("steps") or []
        if "install" in (step.get("name") or "").lower()
        and re.search(r"js|ts|npm|pnpm|node", step.get("name") or "", re.IGNORECASE)
    ]
    assert install_steps, (
        "autofix-same-repo-pr must contain a non-agent step installing "
        "JS/TS dependencies from the lockfile"
    )
    install_step = install_steps[0]
    assert "uses" not in install_step, "The JS/TS install step must be a non-agent `run:` step"
    assert "--ignore-scripts" in (install_step.get("run") or ""), (
        "The JS/TS install step must disable lifecycle scripts via --ignore-scripts"
    )
    condition = install_step.get("if") or ""
    assert "js_test_grant" in condition, (
        "The JS/TS install step must be guarded on "
        "needs.classify.outputs.js_test_grant being non-empty"
    )
    assert "steps.budget.outputs.proceed" in condition, (
        "The JS/TS install step must also be guarded on steps.budget.outputs.proceed == 'true'"
    )


def test_install_step_declares_an_addressable_id_for_the_fixer_gate() -> None:
    parsed = _parsed()
    job = _job(parsed, "autofix-same-repo-pr")
    install_step = _install_step(job)
    assert install_step is not None, "autofix-same-repo-pr must contain a JS/TS install step"
    assert install_step.get("id") == "js_install", (
        "The install step must declare `id: js_install` so the fixer step's "
        "gate can address its outcome"
    )


def test_install_step_is_continue_on_error_so_a_failure_does_not_fail_the_job() -> None:
    parsed = _parsed()
    job = _job(parsed, "autofix-same-repo-pr")
    install_step = _install_step(job)
    assert install_step is not None, "autofix-same-repo-pr must contain a JS/TS install step"
    assert install_step.get("continue-on-error") is True, (
        "The install step must carry `continue-on-error: true` so a failed "
        "install degrades the run to a green decline instead of a red job"
    )


def test_install_step_disables_the_corepack_interactive_download_prompt() -> None:
    parsed = _parsed()
    job = _job(parsed, "autofix-same-repo-pr")
    install_step = _install_step(job)
    assert install_step is not None, "autofix-same-repo-pr must contain a JS/TS install step"
    env = install_step.get("env") or {}
    assert str(env.get("COREPACK_ENABLE_DOWNLOAD_PROMPT")) == "0", (
        "The install step's env must set COREPACK_ENABLE_DOWNLOAD_PROMPT=0 so "
        "corepack's first-use provisioning never blocks on an interactive "
        "prompt in non-TTY CI"
    )


def test_install_step_still_appends_ignore_scripts_after_the_corepack_prefix() -> None:
    """Regression guard, naturally satisfied today: the corepack provisioning
    prefix must not disturb the pre-existing --ignore-scripts flag the
    install step always appends.
    """
    parsed = _parsed()
    job = _job(parsed, "autofix-same-repo-pr")
    install_step = _install_step(job)
    assert install_step is not None, "autofix-same-repo-pr must contain a JS/TS install step"
    run = install_step.get("run") or ""
    assert run.rstrip().endswith("--ignore-scripts"), (
        "The install step's run line must still end in --ignore-scripts"
    )


def test_no_new_third_party_action_provisions_pnpm_or_yarn() -> None:
    """Regression guard, naturally satisfied today (neither reference exists
    yet): pnpm/yarn are provisioned via the runner's bundled corepack, not a
    new SHA-pinned uses: action — a privileged CI surface should not grow
    its supply-chain footprint to fix an install-detection bug.
    """
    parsed = _parsed()
    refs = _uses_refs(parsed)
    assert not any("pnpm/action-setup" in ref for ref in refs), (
        "No pnpm/action-setup reference is expected — pnpm is provisioned via corepack"
    )
    assert not any("actions/setup-node" in ref for ref in refs), (
        "No actions/setup-node reference is expected — Node ships pre-installed "
        "on the runner; only corepack enable is needed"
    )


def test_fixer_step_is_gated_on_the_install_step_not_having_failed() -> None:
    parsed = _parsed()
    job = _job(parsed, "autofix-same-repo-pr")
    agent_steps = _agent_steps(job)
    assert agent_steps, "autofix-same-repo-pr must contain a claude-code-action fixer step"
    condition = agent_steps[0].get("if") or ""
    assert "steps.js_install.outcome != 'failure'" in condition, (
        "The fixer step's `if:` must skip when the install step's outcome is "
        "'failure', so the fixer never thrashes against a missing node_modules"
    )


def test_fixer_gate_still_requires_the_budget_proceed_flag() -> None:
    """Regression guard, naturally satisfied today: the new install-outcome
    clause must be additive — the pre-existing budget-proceed gate must
    still hold alongside it, never be replaced by it.
    """
    parsed = _parsed()
    job = _job(parsed, "autofix-same-repo-pr")
    agent_steps = _agent_steps(job)
    assert agent_steps, "autofix-same-repo-pr must contain a claude-code-action fixer step"
    condition = agent_steps[0].get("if") or ""
    assert "steps.budget.outputs.proceed == 'true'" in condition, (
        "The fixer step's `if:` must still require "
        "steps.budget.outputs.proceed == 'true' alongside the new "
        "install-outcome gate"
    )
