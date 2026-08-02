"""Dogfooding-parity test: Praxion's own caller stays a faithful instance of
the shipped `ci-autofix.yml.tmpl` caller template.

`.github/workflows/ci-autofix.yml` is still the P0 monolith at the time this
test is written — it runs the full checkout/budget/dedup/fetch/diagnose/
tripwire pipeline inline as a `steps:` job. A later step refactors it into a
thin caller of the public `reusable-ci-autofix.yml` hub, matching the shape
`claude/project-baseline/ci-autofix/ci-autofix.yml.tmpl` already documents.
This suite renders that template with Praxion's own install-time values
(the watched-workflows list and hub owner/repo Praxion itself would receive
from `/onboard-project`) and asserts the installed caller is equivalent to
the rendered result on every dimension **except** the `uses:` ref line — the
one documented, intentional divergence (Praxion's caller tracks HEAD via a
local `./...` ref; every rendered template pins a cross-repo hub by SHA).
Running this module now is expected to fail (RED): the installed caller's
job is still a `steps:`-shaped P0 job with no `uses:`/`with:`/`secrets:`
mapping at all, and the workflow still carries a top-level `concurrency:`
block that belongs in the hub once the refactor lands.

Scope note: the `on.workflow_run.workflows` trigger list is rendered from
Praxion's *actual* watched-workflows values (not a generic template example),
so trigger equality is asserted directly rather than skipped — this is how
the "tolerate the per-repo trigger value" principle is honored for the one
caller (Praxion itself) whose per-repo value is already known.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CALLER_TEMPLATE_FILE = (
    PROJECT_ROOT / "claude" / "project-baseline" / "ci-autofix" / "ci-autofix.yml.tmpl"
)
INSTALLED_CALLER_FILE = PROJECT_ROOT / ".github" / "workflows" / "ci-autofix.yml"

# Praxion's own install-time values — exactly what `/onboard-project` would
# substitute into this template for Praxion itself (caller #1, dogfooding).
_RENDER_SUBSTITUTIONS = {
    "{{WATCHED_WORKFLOWS}}": '"Test", "Architecture"',
    "{{PRAXION_HUB}}": "francisco-perez-sorrosal/praxion",
    # The SHA's actual value is irrelevant to this suite: the whole `uses:`
    # line is the one documented, tolerated divergence. Any
    # well-formed-looking 40-hex value keeps the rendered template parseable.
    "{{HUB_SHA}}": "a" * 40,
}

_HUB_WORKFLOW_PATH_PATTERN = re.compile(r"(\.github/workflows/reusable-ci-autofix\.yml)")

_EXPECTED_JOB_PERMISSIONS = {
    "contents": "write",
    "pull-requests": "write",
    "actions": "read",
    "id-token": "write",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _raw_text(path: Path) -> str:
    """Return a file's raw content (read lazily so collection succeeds)."""
    return path.read_text(encoding="utf-8")


def _render_caller_template_text() -> str:
    """Render the shipped caller template with Praxion's own install-time values."""
    text = _raw_text(CALLER_TEMPLATE_FILE)
    for token, value in _RENDER_SUBSTITUTIONS.items():
        text = text.replace(token, value)
    return text


def _rendered_template_parsed() -> dict:
    """Parse the rendered caller template as YAML."""
    return yaml.safe_load(_render_caller_template_text())


def _installed_caller_parsed() -> dict:
    """Parse Praxion's installed caller (`.github/workflows/ci-autofix.yml`) as YAML."""
    return yaml.safe_load(_raw_text(INSTALLED_CALLER_FILE))


def _on_block(parsed: dict) -> dict:
    """Return the `on:` trigger block, accounting for PyYAML's boolean-key gotcha.

    PyYAML's default (YAML 1.1) resolver treats the bare scalar `on` as the
    boolean `True` when it appears as a mapping key, so a top-level `on:`
    block parses under the key `True`, not the string `"on"`.
    """
    if "on" in parsed:
        return parsed["on"]
    if True in parsed:
        return parsed[True]
    raise AssertionError("Workflow document has no `on:` trigger block")


def _job(parsed: dict) -> dict:
    """Return the single job body from a workflow document."""
    return next(iter(parsed["jobs"].values()))


def _job_sans_uses(job: dict) -> dict:
    """Return a job body with its `uses:` key removed.

    `uses:` is the one documented, tolerated divergence between Praxion's
    caller (a local `uses: ./...` ref, tracking HEAD) and the rendered
    template (a cross-repo SHA-pinned ref).
    Every other job-level key must match exactly for the two to be
    considered a faithful instance of one another.
    """
    return {key: value for key, value in job.items() if key != "uses"}


def _reusable_workflow_relative_path(uses_value: str | None) -> str | None:
    """Extract the hub workflow's repo-relative path from a `uses:` value.

    Strips whatever precedes it (a local `./` prefix or a cross-repo
    `owner/repo` prefix) and whatever follows it (an `@<ref>` pin), isolating
    just the piece that must always match regardless of caller: which file
    is being invoked.
    """
    if not uses_value:
        return None
    match = _HUB_WORKFLOW_PATH_PATTERN.search(uses_value)
    return match.group(1) if match else None


# ---------------------------------------------------------------------------
# Whole-document parity
# ---------------------------------------------------------------------------


def test_installed_caller_declares_only_the_same_top_level_keys_as_the_rendered_template() -> None:
    rendered = _rendered_template_parsed()
    actual = _installed_caller_parsed()
    assert set(actual.keys()) == set(rendered.keys()), (
        "The installed caller's top-level keys must match the rendered "
        f"template's exactly: template has {sorted(rendered.keys(), key=str)}, "
        f"installed caller has {sorted(actual.keys(), key=str)}. A stray key "
        "(e.g. a leftover `concurrency:` block) signals P0 logic that should "
        "have moved into the hub, not stayed in the thin caller."
    )


def test_installed_callers_watched_workflows_trigger_matches_what_the_template_renders() -> None:
    rendered_on = _on_block(_rendered_template_parsed())
    actual_on = _on_block(_installed_caller_parsed())
    assert actual_on == rendered_on, (
        "The installed caller's `on.workflow_run` trigger must equal what the "
        "template renders with Praxion's own watched-workflows value — got "
        f"installed={actual_on!r}, rendered={rendered_on!r}"
    )


def test_installed_caller_denies_permissions_by_default_at_workflow_level_same_as_template() -> (
    None
):
    rendered = _rendered_template_parsed()
    actual = _installed_caller_parsed()
    assert actual.get("permissions") == {} == rendered.get("permissions"), (
        "Top-level `permissions:` must be the empty mapping in both the "
        "installed caller and the rendered template (deny-by-default)"
    )


def test_installed_caller_job_matches_the_rendered_template_job_on_every_key_except_the_uses_ref() -> (
    None
):
    rendered_job = _job(_rendered_template_parsed())
    actual_job = _job(_installed_caller_parsed())
    assert _job_sans_uses(actual_job) == _job_sans_uses(rendered_job), (
        "The installed caller's job must match the rendered template's job "
        "on every key except `uses:` — any additional, missing, or "
        "differently-valued key (e.g. leftover `steps:`/`if:`/`runs-on:` "
        "from the P0 monolith, or a missing `with:`/`secrets:` mapping) "
        "signals the caller has drifted from the shipped template's "
        f"security contract. installed(sans uses)={_job_sans_uses(actual_job)!r}, "
        f"rendered(sans uses)={_job_sans_uses(rendered_job)!r}"
    )


# ---------------------------------------------------------------------------
# Named security-relevant dimensions (the intentional `uses:` divergence)
# ---------------------------------------------------------------------------


def test_installed_caller_and_template_invoke_the_same_reusable_workflow_file() -> None:
    rendered_uses = _job(_rendered_template_parsed()).get("uses")
    actual_uses = _job(_installed_caller_parsed()).get("uses")
    assert actual_uses is not None, (
        "The installed caller's job must declare a top-level `uses:` key "
        "invoking the hub reusable workflow — the current P0 job runs its "
        "own inline `steps:` instead"
    )
    rendered_path = _reusable_workflow_relative_path(rendered_uses)
    actual_path = _reusable_workflow_relative_path(actual_uses)
    assert actual_path == rendered_path == ".github/workflows/reusable-ci-autofix.yml", (
        "Both the installed caller and the rendered template must invoke "
        f"the same hub workflow file — got installed={actual_uses!r}, "
        f"rendered={rendered_uses!r}"
    )


def test_installed_caller_pins_the_hub_via_a_local_ref_while_the_template_uses_a_cross_repo_pin() -> (
    None
):
    """Documents the one intentional divergence: Praxion's caller #1
    tracks HEAD via a same-repo local ref; the shipped template ships the
    cross-repo SHA-pinned form every managed caller receives.
    """
    rendered_uses = _job(_rendered_template_parsed()).get("uses", "")
    actual_uses = _job(_installed_caller_parsed()).get("uses")
    assert actual_uses is not None, (
        "The installed caller's job must declare a `uses:` key before its "
        "ref shape can be checked — the current P0 job has none"
    )
    assert actual_uses.startswith("./"), (
        "Praxion's installed caller must reference the hub via a same-repo "
        f"local `uses: ./...` ref (never a cross-repo pin) — got {actual_uses!r}"
    )
    assert not rendered_uses.startswith("./"), (
        "The rendered template must keep the cross-repo pinned `uses:` form "
        f"(every managed caller's shape) — got {rendered_uses!r}"
    )
    assert "@" in rendered_uses, (
        f"The rendered template's `uses:` must be SHA-pinned via `@<ref>` — got {rendered_uses!r}"
    )


def test_installed_callers_job_permissions_ceiling_matches_the_templates_least_privilege_block() -> (
    None
):
    rendered_permissions = _job(_rendered_template_parsed()).get("permissions") or {}
    actual_permissions = _job(_installed_caller_parsed()).get("permissions") or {}
    assert actual_permissions == _EXPECTED_JOB_PERMISSIONS == rendered_permissions, (
        "The installed caller's job permissions must match the template's "
        f"least-privilege ceiling exactly — expected {_EXPECTED_JOB_PERMISSIONS}, "
        f"got installed={actual_permissions!r}, rendered={rendered_permissions!r}"
    )


def test_installed_caller_passes_the_oauth_secret_by_explicit_mapping_never_inherit() -> None:
    rendered_secrets = _job(_rendered_template_parsed()).get("secrets")
    actual_secrets = _job(_installed_caller_parsed()).get("secrets")
    expected = {"CLAUDE_CODE_OAUTH_TOKEN": "${{ secrets.CLAUDE_CODE_OAUTH_TOKEN }}"}
    assert actual_secrets == expected == rendered_secrets, (
        "The installed caller's job must map CLAUDE_CODE_OAUTH_TOKEN "
        f"explicitly, identically to the template — expected {expected}, "
        f"got installed={actual_secrets!r}, rendered={rendered_secrets!r}"
    )
    assert "secrets: inherit" not in _raw_text(INSTALLED_CALLER_FILE), (
        "`secrets: inherit` must never appear in the installed caller — it "
        "silently no-ops cross-org auth, defeating the reason this caller "
        "exercises an explicit mapping even though it happens to be "
        "same-repo"
    )


def test_installed_callers_with_block_points_at_the_same_policy_path_as_the_template() -> None:
    rendered_with = _job(_rendered_template_parsed()).get("with")
    actual_with = _job(_installed_caller_parsed()).get("with")
    expected = {"policy_path": ".github/autofix-policy.yml"}
    assert actual_with == expected == rendered_with, (
        "The installed caller's job must pass `with.policy_path` "
        f"identically to the template — expected {expected}, got "
        f"installed={actual_with!r}, rendered={rendered_with!r}"
    )
