"""Structural schema tests for the ci-autofix caller/policy/P2-stub template package.

`claude/project-baseline/ci-autofix/{ci-autofix.yml.tmpl, autofix-policy.yml.tmpl,
cross-model-review.yml.tmpl}` do not exist yet — these tests define the contract
the implementer must satisfy when creating the caller-facing template package
(the counterpart to the hub reusable workflow tested in
`test_ci_autofix_hub_invariants.py`). Every test reads its target file lazily
(inside the function body, not at module import time) so collection succeeds
before the files exist; running this module now is expected to fail with a
clear "file not found" assertion (RED), not an import error.

Scope note: these tests verify the TEMPLATE package as shipped from Praxion —
unresolved `{{...}}` placeholder tokens are expected and tolerated. Resolving
those placeholders into a real, installed caller (a concrete hub SHA, detected
workflow names) is a later onboarding concern, verified separately once the
onboarding install phase exists. Where a placeholder is present here, this
suite asserts its FORM (a documented {{TOKEN}} shape, or an already-resolved
value), never its resolution.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]
TEMPLATE_DIR = PROJECT_ROOT / "claude" / "project-baseline" / "ci-autofix"
CALLER_TEMPLATE_FILE = TEMPLATE_DIR / "ci-autofix.yml.tmpl"
POLICY_TEMPLATE_FILE = TEMPLATE_DIR / "autofix-policy.yml.tmpl"
CROSS_MODEL_REVIEW_STUB_FILE = TEMPLATE_DIR / "cross-model-review.yml.tmpl"

SHA_PIN_PATTERN = re.compile(r"^[0-9a-f]{40}$")
MUSTACHE_TOKEN_PATTERN = re.compile(r"^\{\{[A-Z0-9_]+\}\}$")
_PLACEHOLDER_SUB_PATTERN = re.compile(r"\{\{[A-Z0-9_]+\}\}")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _raw_text(path: Path) -> str:
    """Return a template file's raw content (read lazily so collection succeeds)."""
    return path.read_text(encoding="utf-8")


def _parsed_with_placeholders_stubbed(path: Path) -> dict:
    """Parse a template as YAML after replacing `{{TOKEN}}` mustache tokens.

    Caller/policy templates interleave install-time `{{TOKEN}}` placeholders
    into otherwise-valid YAML (e.g. `uses: {{PRAXION_HUB}}/...@{{HUB_SHA}}`).
    Those tokens are not valid YAML scalars on their own and break the parser
    mid-document. Substituting a safe, quote-free stub lets this suite verify
    the surrounding document structure without depending on the installer's
    rendering step (exercised separately, later, by the dogfooding-parity
    test against a fully-rendered caller).
    """
    stubbed = _PLACEHOLDER_SUB_PATTERN.sub("PLACEHOLDER_STUB", _raw_text(path))
    return yaml.safe_load(stubbed)


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
    raise AssertionError("Template has no `on:` trigger block")


def _mentions_near(raw: str, term_a: str, term_b: str, window: int = 200) -> bool:
    """True if `term_a` and `term_b` co-occur within `window` chars, either order."""
    pattern = re.compile(
        rf"({re.escape(term_a)}.{{0,{window}}}{re.escape(term_b)}"
        rf"|{re.escape(term_b)}.{{0,{window}}}{re.escape(term_a)})",
        re.IGNORECASE | re.DOTALL,
    )
    return bool(pattern.search(raw))


# ---------------------------------------------------------------------------
# Package existence
# ---------------------------------------------------------------------------


def test_template_package_directory_contains_all_three_files() -> None:
    for path in (CALLER_TEMPLATE_FILE, POLICY_TEMPLATE_FILE, CROSS_MODEL_REVIEW_STUB_FILE):
        assert path.exists(), (
            f"{path} not found. The implementer must create the ci-autofix "
            "template package under claude/project-baseline/ci-autofix/."
        )


# ---------------------------------------------------------------------------
# Caller template: claude/project-baseline/ci-autofix/ci-autofix.yml.tmpl
# ---------------------------------------------------------------------------


def test_caller_template_triggers_on_workflow_run_with_a_static_workflows_list() -> None:
    parsed = _parsed_with_placeholders_stubbed(CALLER_TEMPLATE_FILE)
    on_block = _on_block(parsed)
    assert "workflow_run" in on_block, (
        "Caller template must trigger on `workflow_run` — GitHub Actions requires "
        "`on.workflow_run.workflows` to be a static literal list, so this cannot "
        "be sourced from the policy file at runtime"
    )
    workflows = on_block["workflow_run"].get("workflows")
    assert isinstance(workflows, list), "`on.workflow_run.workflows` must be a static list"
    assert workflows, "`on.workflow_run.workflows` must not be empty"


def test_caller_template_uses_references_the_hub_pinned_by_sha_or_placeholder() -> None:
    raw = _raw_text(CALLER_TEMPLATE_FILE)
    match = re.search(
        r"uses:\s*(?P<owner_repo>\S+?)/\.github/workflows/reusable-ci-autofix\.yml@(?P<ref>\S+)",
        raw,
    )
    assert match, (
        "Caller template must reference the hub workflow via "
        "`uses: <owner/repo>/.github/workflows/reusable-ci-autofix.yml@<ref>`"
    )
    owner_repo = match.group("owner_repo")
    assert owner_repo in ("{{PRAXION_HUB}}", "francisco-perez-sorrosal/praxion"), (
        "Expected the hub owner/repo to be the documented {{PRAXION_HUB}} "
        f"placeholder or the literal francisco-perez-sorrosal/praxion, got {owner_repo!r}"
    )
    ref = match.group("ref")
    is_full_sha = bool(SHA_PIN_PATTERN.match(ref))
    is_placeholder = bool(MUSTACHE_TOKEN_PATTERN.match(ref))
    assert is_full_sha or is_placeholder, (
        "The hub reference must be pinned by a full 40-hex commit SHA or a "
        f"documented {{TOKEN}} placeholder that onboarding resolves to one — "
        f"got {ref!r} (never a mutable tag or branch)"
    )


def test_caller_template_denies_permissions_by_default_at_workflow_level() -> None:
    parsed = _parsed_with_placeholders_stubbed(CALLER_TEMPLATE_FILE)
    assert parsed.get("permissions") == {}, (
        "Top-level `permissions:` must be the empty mapping (deny-by-default); "
        "only the job below should raise the ceiling explicitly"
    )


def test_caller_template_job_carries_least_privilege_permissions() -> None:
    parsed = _parsed_with_placeholders_stubbed(CALLER_TEMPLATE_FILE)
    job = next(iter(parsed["jobs"].values()))
    permissions = job.get("permissions") or {}
    required = {
        "contents": "write",
        "pull-requests": "write",
        "actions": "read",
        "id-token": "write",
    }
    for scope, level in required.items():
        assert permissions.get(scope) == level, (
            f"Caller template's job permissions must grant `{scope}: {level}` — "
            "GitHub caps the reusable workflow's effective token at the "
            "caller's own grant, so an under-scoped caller silently starves "
            "the hub's steps"
        )


def test_caller_template_passes_the_oauth_secret_by_explicit_mapping() -> None:
    parsed = _parsed_with_placeholders_stubbed(CALLER_TEMPLATE_FILE)
    job = next(iter(parsed["jobs"].values()))
    secrets_block = job.get("secrets") or {}
    assert "CLAUDE_CODE_OAUTH_TOKEN" in secrets_block, (
        "Caller template's job must map CLAUDE_CODE_OAUTH_TOKEN explicitly to "
        "the caller repo's own secret store"
    )
    assert "secrets.CLAUDE_CODE_OAUTH_TOKEN" in str(secrets_block["CLAUDE_CODE_OAUTH_TOKEN"]), (
        "The mapped value must reference the caller's own "
        "`secrets.CLAUDE_CODE_OAUTH_TOKEN`, not a different secret name"
    )


# ---------------------------------------------------------------------------
# Policy template: claude/project-baseline/ci-autofix/autofix-policy.yml.tmpl
# ---------------------------------------------------------------------------


def test_policy_template_parses_as_yaml_with_the_five_top_level_sections() -> None:
    parsed = _parsed_with_placeholders_stubbed(POLICY_TEMPLATE_FILE)
    assert isinstance(parsed, dict), "Policy template must parse to a YAML mapping"
    for section in ("watched_workflows", "surfaces", "review", "safety", "provider"):
        assert section in parsed, f"Policy template must declare a top-level `{section}:` section"


def test_policy_template_declares_the_safety_budget_and_tripwire_fields() -> None:
    parsed = _parsed_with_placeholders_stubbed(POLICY_TEMPLATE_FILE)
    safety = parsed["safety"]
    assert (
        "max_runs_per_day" in safety
    ), "policy.safety.max_runs_per_day is the daily-run budget cap the hub reads"
    assert (
        "max_attempts_per_pr" in safety
    ), "policy.safety.max_attempts_per_pr caps repeated-fix attempts on one PR"
    sensitive_paths = safety.get("sensitive_paths")
    assert isinstance(sensitive_paths, list), "policy.safety.sensitive_paths must be a list"
    assert sensitive_paths, (
        "policy.safety.sensitive_paths must be non-empty — the sensitive-path "
        "tripwire sources its watch list from here"
    )
    assert (
        "auto_commit_tiers" in safety
    ), "policy.safety.auto_commit_tiers documents which fix categories may auto-commit"


def test_policy_template_declares_main_branch_surface_as_a_valid_toggle() -> None:
    parsed = _parsed_with_placeholders_stubbed(POLICY_TEMPLATE_FILE)
    surfaces = parsed["surfaces"]
    assert surfaces.get("main_branch") in ("fix-pr", "off"), (
        "policy.surfaces.main_branch must be one of the two P1 values "
        "('fix-pr' | 'off') that toggle the main-branch autofix surface"
    )


def test_policy_template_reviewer_family_is_documented_as_never_claude() -> None:
    parsed = _parsed_with_placeholders_stubbed(POLICY_TEMPLATE_FILE)
    review = parsed["review"]
    assert (
        "reviewer_family" in review
    ), "policy.review.reviewer_family selects the P2 cross-model reviewer"
    assert review["reviewer_family"] != "claude", (
        "reviewer_family must never be 'claude' — the fixer already is claude, "
        "so the cross-model reviewer must come from a different model family"
    )
    raw = _raw_text(POLICY_TEMPLATE_FILE)
    assert _mentions_near(raw, "reviewer_family", "claude"), (
        "The template must document, near reviewer_family, that 'claude' is "
        "never a valid value for this field"
    )


def test_policy_template_declares_fixer_and_default_fixer_model() -> None:
    parsed = _parsed_with_placeholders_stubbed(POLICY_TEMPLATE_FILE)
    provider = parsed["provider"]
    assert (
        provider.get("fixer") == "claude"
    ), "policy.provider.fixer must default to 'claude' — the only fixer wired in P1"
    assert provider.get("fixer_model") == "opus", (
        "policy.provider.fixer_model must default to 'opus', replacing the P0 "
        "hardcoded --model opus literal"
    )


def test_policy_template_documents_plugin_dir_as_optional_with_no_default() -> None:
    """Structural proxy: `provider.plugin_dir` may be authored as an active key
    or as a documented (commented-out, opt-in) example — either satisfies the
    contract that it appears in the template and never ships a default value,
    unlike fixer/fixer_model above. Verified as a mention rather than a
    parsed-YAML key so the test does not lock in one authoring style.
    """
    raw = _raw_text(POLICY_TEMPLATE_FILE)
    assert "plugin_dir" in raw, (
        "policy.provider.plugin_dir must appear in the policy template — it "
        "lets a caller opt into the --plugin-dir flag; unlike fixer/"
        "fixer_model, it must ship with NO default value"
    )
    assert _mentions_near(raw, "plugin_dir", "default") or _mentions_near(
        raw, "plugin_dir", "optional"
    ), (
        "plugin_dir must be documented, near its mention, as having no "
        "default / being optional — contrasted with the safety/provider "
        "fields above that do carry safe defaults"
    )


# ---------------------------------------------------------------------------
# P2 placeholder stub: claude/project-baseline/ci-autofix/cross-model-review.yml.tmpl
# ---------------------------------------------------------------------------


def test_cross_model_review_stub_is_recognizable_as_a_deferred_placeholder() -> None:
    raw = _raw_text(CROSS_MODEL_REVIEW_STUB_FILE)
    assert re.search(r"\bP2\b", raw), (
        "The cross-model-review stub must be recognizably marked as a "
        "deferred, not-yet-built phase, not a completed gate"
    )
    assert re.search(r"TODO|placeholder|stub|not (yet )?implemented", raw, re.IGNORECASE), (
        "The stub must carry an explicit not-yet-implemented marker so a "
        "reader (or a future onboarding pass) never mistakes it for the real gate"
    )


def test_cross_model_review_stub_never_invokes_a_real_cursor_gate() -> None:
    raw = _raw_text(CROSS_MODEL_REVIEW_STUB_FILE)
    assert "CURSOR_API_KEY" not in raw, (
        "The stub must not reference CURSOR_API_KEY — that wiring is "
        "deferred, not implemented in this phase"
    )
    assert "cursor-agent" not in raw, (
        "The stub must not shell out to a Cursor CLI/agent — this phase "
        "ships shape/comment-only scaffolding, not the working gate"
    )
    assert (
        "cursor agent" not in raw.lower()
    ), "The stub must not describe invoking a Cursor agent as an active step"


# ---------------------------------------------------------------------------
# Package-wide invariant
# ---------------------------------------------------------------------------


def test_no_template_in_the_package_ever_uses_secrets_inherit() -> None:
    for path in (CALLER_TEMPLATE_FILE, POLICY_TEMPLATE_FILE, CROSS_MODEL_REVIEW_STUB_FILE):
        raw = _raw_text(path)
        assert "secrets: inherit" not in raw, (
            "`secrets: inherit` must never appear anywhere in the ci-autofix "
            f"template package — found in {path.name}. It silently no-ops "
            "cross-org auth for every managed repo that installs this package."
        )
