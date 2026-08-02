"""Structural invariant tests for the server-side finalize backstop workflow.

`.github/workflows/finalize-adrs.yml` does not exist yet — these tests define
the trigger/composition/safety contract the implementer must satisfy when
building the `push:main` backstop that reruns the on-main finalize
composition for web-UI (server-side) merges, where client-side git hooks
cannot fire. Every test reads the file lazily (inside the function body, not
at module import time) so collection succeeds before the file exists; running
this module now is expected to fail — the first test with a clear "file not
found" assertion, the rest with an uncaught `FileNotFoundError` raised while
reading a file that is not there yet — but never with an import error at
collection time.

Scope note: this suite verifies structure — parsed YAML shape, string/regex
presence of required steps, permission grants, and banned patterns. It cannot
verify runtime behavior: whether a `GITHUB_TOKEN`-authenticated push actually
avoids re-triggering the workflow (the runtime half of the anti-recursion
guarantee), or whether the mechanism holds end-to-end against a real web-UI
merge. Those guarantees close only via a live dogfood run on `main` — the
suite asserts only the *structural* half of anti-recursion (no `[skip ci]`
workaround is present, because none should be needed) and leaves the runtime
half, and the live-dogfood confirmation, unverified here by design.

Modeled directly on `tests/test_issue_autofix_workflow_invariants.py` — lazy
file read, `_on_block`/`_jobs`/`_all_steps`/`_uses_refs` helper reuse, and
exact-value assertions over loose substring checks wherever the plan pins an
exact shape.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_FILE = PROJECT_ROOT / ".github" / "workflows" / "finalize-adrs.yml"

SHA_PIN_PATTERN = re.compile(r"^[0-9a-f]{40}$")

# The three finalizers the shared composition owns. The workflow YAML must
# never re-list them directly — only `finalize_chain_run_on_main` may.
INDIVIDUAL_FINALIZERS = (
    "finalize_adrs.py",
    "finalize_tech_debt_ledger.py",
    "build_doc_manifest.py",
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _raw_text() -> str:
    """Return the workflow's raw file content (read lazily so collection succeeds)."""
    return WORKFLOW_FILE.read_text(encoding="utf-8")


def _parsed() -> dict:
    """Parse the workflow as YAML."""
    return yaml.safe_load(_raw_text())


def _on_block(parsed: dict) -> dict:
    """Return the `on:` trigger block.

    PyYAML's default (YAML 1.1) resolver treats the bare scalar `on` as the
    boolean `True` — including when it appears as a mapping key — so a
    top-level `on:` block parses under the key `True`, not the string `"on"`.
    This is a well-known GitHub-Actions-YAML gotcha; every lookup of the
    trigger block must account for it.
    """
    if "on" in parsed:
        return parsed["on"]
    if True in parsed:
        return parsed[True]
    raise AssertionError("Workflow has no `on:` trigger block")


def _jobs(parsed: dict) -> dict:
    """Return the workflow's `jobs:` mapping."""
    return parsed.get("jobs") or {}


def _all_steps(parsed: dict) -> list[dict]:
    """Flatten every step across every job in the workflow."""
    steps: list[dict] = []
    for job in _jobs(parsed).values():
        steps.extend(job.get("steps") or [])
    return steps


def _uses_refs(parsed: dict) -> list[str]:
    """Collect every `uses:` value across every job/step in the workflow."""
    return [step["uses"] for step in _all_steps(parsed) if step.get("uses")]


def _run_blocks(parsed: dict) -> str:
    """Concatenate every step's `run:` body into one searchable string."""
    return " ".join((step.get("run") or "") for step in _all_steps(parsed))


# ---------------------------------------------------------------------------
# Existence and parseability
# ---------------------------------------------------------------------------


def test_workflow_file_exists_and_parses_as_yaml() -> None:
    assert WORKFLOW_FILE.exists(), (
        f"{WORKFLOW_FILE} not found. The implementer must create the "
        "push:main server-side finalize backstop workflow."
    )
    parsed = _parsed()
    assert isinstance(parsed, dict), "Workflow must parse to a YAML mapping"


# ---------------------------------------------------------------------------
# Trigger contract — push:main only, no paths filter, never pull_request_target
# ---------------------------------------------------------------------------


def test_trigger_is_push_to_main_only() -> None:
    parsed = _parsed()
    on_block = _on_block(parsed)
    assert "push" in on_block, (
        "Workflow's `on:` block must declare the `push` event — this is a "
        "server-side finalize backstop, not a PR or manual-dispatch trigger"
    )
    push_block = on_block["push"] or {}
    branches = push_block.get("branches") or []
    assert branches == ["main"], (
        f"`on.push.branches` must be exactly `['main']` — a push to any other "
        f"branch must not run this workflow (got {branches!r})"
    )


def test_push_trigger_has_no_paths_filter() -> None:
    parsed = _parsed()
    on_block = _on_block(parsed)
    push_block = on_block.get("push") or {}
    assert "paths" not in push_block, (
        "`on.push` must not declare a `paths:` filter — the scripts' own "
        "state-driven no-op gates are the correct filter; a coarser `paths:` "
        "gate would drift from them and could re-strand a ledger-only push"
    )


def test_never_triggers_on_pull_request_target() -> None:
    raw = _raw_text()
    assert "pull_request_target" not in raw, (
        "`pull_request_target` must never appear anywhere in this workflow — "
        "the trigger is `push: branches: [main]`, never a PR-context event "
        "that would run untrusted code with write credentials"
    )


# ---------------------------------------------------------------------------
# Supply-chain pinning — every uses: is a 40-hex SHA with a version comment
# ---------------------------------------------------------------------------


def test_every_uses_reference_is_sha_pinned() -> None:
    parsed = _parsed()
    refs = _uses_refs(parsed)
    assert refs, "Workflow must contain at least one `uses:` step (e.g. checkout)"
    for ref in refs:
        assert "@" in ref, f"`uses: {ref}` must pin a ref via '@<sha>'"
        pinned_ref = ref.rsplit("@", 1)[1]
        assert SHA_PIN_PATTERN.match(pinned_ref), (
            f"`uses: {ref}` must be pinned to a full 40-hex-char commit SHA, "
            f"not a mutable tag or branch (got {pinned_ref!r})"
        )


def test_every_uses_line_carries_a_trailing_version_comment() -> None:
    raw = _raw_text()
    uses_lines = [
        line for line in raw.splitlines() if re.search(r"\buses:\s*\S+@[0-9a-f]{40}", line)
    ]
    assert uses_lines, "Expected at least one SHA-pinned `uses:` line"
    for line in uses_lines:
        assert re.search(r"#\s*v[0-9]+\.[0-9]+\.[0-9]+", line), (
            f"`{line.strip()}` must carry a trailing `# vX.Y.Z` comment "
            "(dec-024 SHA-pin discipline) so the pinned commit is human-legible"
        )


# ---------------------------------------------------------------------------
# Least privilege — empty workflow floor, contents: write on the pushing job only
# ---------------------------------------------------------------------------


def test_workflow_level_permissions_are_empty() -> None:
    parsed = _parsed()
    permissions = parsed.get("permissions")
    assert not permissions, (
        "top-level `permissions:` must be empty (`{}` or omitted) — least "
        "privilege; the job that pushes re-grants only what it needs"
    )


def test_contents_write_granted_only_on_the_pushing_job() -> None:
    parsed = _parsed()
    jobs = _jobs(parsed)
    assert jobs, "Workflow must declare at least one job"
    jobs_with_contents_write = [
        name
        for name, job in jobs.items()
        if (job.get("permissions") or {}).get("contents") == "write"
    ]
    assert jobs_with_contents_write, (
        "at least one job must hold `contents: write` — the job that commits "
        "and pushes the finalize promotion back to `main`"
    )
    assert len(jobs_with_contents_write) == 1, (
        "`contents: write` must be granted to exactly one job (the pushing "
        f"job), not {jobs_with_contents_write}"
    )


# ---------------------------------------------------------------------------
# Deterministic governance only — no agent step, no track_progress
# ---------------------------------------------------------------------------


def test_workflow_contains_no_agent_or_track_progress_step() -> None:
    raw = _raw_text()
    assert "track_progress" not in raw, (
        "`track_progress` must never appear — this workflow has no agent "
        "step to grant a tool-scope shortcut to"
    )
    assert "claude-code-action" not in raw, (
        "this is a deterministic governance workflow — no agent/LLM step; "
        "the finalize scripts already encode every judgment call "
        "(frontmatter validation, collision handling, ordering)"
    )


# ---------------------------------------------------------------------------
# Structural anti-recursion — no [skip ci] workaround should be present
# ---------------------------------------------------------------------------


def test_no_skip_ci_workaround_is_present() -> None:
    """The anti-recursion guarantee is structural: a `GITHUB_TOKEN`-authenticated
    push does not re-trigger a `push` workflow run. A `[skip ci]` (or
    `[ci skip]`) commit-message hack would signal the author didn't trust (or
    verify) that structural guarantee — the runtime half of this guarantee is
    dogfood-only and is NOT asserted here.
    """
    raw = _raw_text()
    assert "[skip ci]" not in raw, (
        "no `[skip ci]` workaround should be needed — the `GITHUB_TOKEN` "
        "anti-recursion guarantee is structural, not something the workflow "
        "must engineer around"
    )
    assert "[ci skip]" not in raw, (
        "no `[ci skip]` workaround should be needed — same rationale as `[skip ci]`"
    )


# ---------------------------------------------------------------------------
# Concurrency — serialized, never cancels an in-flight run
# ---------------------------------------------------------------------------


def test_concurrency_group_and_no_cancel_in_progress() -> None:
    parsed = _parsed()
    assert "concurrency" in parsed, (
        "Workflow must declare a top-level `concurrency:` group so two rapid "
        "pushes to `main` are serialized, not run in parallel"
    )
    concurrency = parsed["concurrency"]
    assert concurrency.get("group"), "`concurrency.group` must be a non-empty key"
    assert concurrency.get("cancel-in-progress") is False, (
        "`concurrency.cancel-in-progress` must be exactly `false` — a mid-push "
        "run must never be cancelled; the queued run re-scans idempotently"
    )


# ---------------------------------------------------------------------------
# Single source of truth — sources finalize_chain.sh, never re-lists finalizers
# ---------------------------------------------------------------------------


def test_finalize_step_sources_the_shared_chain_library() -> None:
    run_blocks = _run_blocks(_parsed())
    assert re.search(r"(?:^|\s)(?:source|\.)\s+\S*finalize_chain\.sh", run_blocks), (
        "a step's `run:` body must `source` (or `.`) `scripts/finalize_chain.sh` "
        "— the composition must be sourced from the shared library, never "
        "re-implemented in the workflow"
    )


def test_finalize_step_invokes_the_shared_entry_point() -> None:
    run_blocks = _run_blocks(_parsed())
    assert "finalize_chain_run_on_main" in run_blocks, (
        "a step must call `finalize_chain_run_on_main` — the single public "
        "entry point both the local hooks and this workflow share"
    )


def test_finalize_invocation_sets_the_strict_env_flag() -> None:
    raw = _raw_text()
    assert re.search(r"FINALIZE_CHAIN_STRICT\s*[:=]\s*['\"]?1\b", raw), (
        "the CI invocation must set `FINALIZE_CHAIN_STRICT=1` — fail-loud mode "
        "is required server-side so a finalizer error cannot land a "
        "partial/corrupt commit on `main`"
    )


def test_workflow_does_not_re_invoke_individual_finalizers_directly() -> None:
    """The composition is defined once, in `scripts/finalize_chain.sh`.

    The workflow YAML must not re-list `finalize_adrs.py` /
    `finalize_tech_debt_ledger.py` / `build_doc_manifest.py` as separate
    invocations in a `run:` step — doing so would duplicate the ordering
    logic the shared entry point already owns, reintroducing exactly the
    drift risk the shared-entry-point decision exists to prevent.
    """
    run_blocks = _run_blocks(_parsed())
    for finalizer in INDIVIDUAL_FINALIZERS:
        assert finalizer not in run_blocks, (
            f"{finalizer!r} must not be invoked directly in a workflow `run:` "
            "step — the composition is owned exclusively by "
            "`finalize_chain_run_on_main` in scripts/finalize_chain.sh"
        )


# ---------------------------------------------------------------------------
# Conditional commit-back — gated on git status --porcelain, never unconditional
# ---------------------------------------------------------------------------


def test_commit_step_is_gated_on_porcelain_output() -> None:
    parsed = _parsed()
    steps = _all_steps(parsed)
    commit_steps = [step for step in steps if "git commit" in (step.get("run") or "")]
    assert commit_steps, "Expected a step whose `run:` body executes `git commit`"
    for step in commit_steps:
        run = step.get("run") or ""
        step_if = step.get("if") or ""
        assert "porcelain" in run or "porcelain" in step_if, (
            "the commit step must be gated on `git status --porcelain` — an "
            "unconditional `git commit` would create an empty commit when "
            "finalize produced no tracked-file change"
        )


# ---------------------------------------------------------------------------
# Bot authorship, no AI trailer
# ---------------------------------------------------------------------------


def test_commit_identity_is_github_actions_bot() -> None:
    raw = _raw_text()
    assert "github-actions[bot]" in raw, (
        "the workflow must configure the `github-actions[bot]` git identity "
        "before committing — the bot, not a human or an AI agent, owns the "
        "server-side finalize commit"
    )


def test_commit_message_carries_no_ai_authorship_trailer() -> None:
    raw = _raw_text()
    assert "Co-Authored-By" not in raw, (
        "the commit message must never contain a `Co-Authored-By` trailer — "
        "no AI-authorship trailer per repo convention"
    )
    assert "Generated by" not in raw, (
        "the commit message must never contain a `Generated by` trailer — "
        "no AI-authorship trailer per repo convention"
    )


# ---------------------------------------------------------------------------
# PyYAML dependency + shallow checkout
# ---------------------------------------------------------------------------


def test_pip_install_pyyaml_step_exists() -> None:
    run_blocks = _run_blocks(_parsed())
    assert re.search(r"pip install\s+.*pyyaml", run_blocks, re.IGNORECASE), (
        "a step must `pip install pyyaml` into the same interpreter the "
        "finalize chain invokes — `build_doc_manifest.py` requires it and "
        "would otherwise `ImportError` on every push"
    )


def test_checkout_step_fetches_full_history_for_the_manifest_generator() -> None:
    """Checkout depth is a deliberate, tested choice — and the choice inverted.

    This invariant previously required a shallow checkout on the grounds that
    `finalize_adrs.py` needs no history: its NNN assignment scans the working
    tree, and the commit-back is one commit onto the just-checked-out tip. Both
    remain true, and full history breaks neither.

    What changed is that a second consumer joined the same job.
    `build_doc_manifest.py` derives each surface's `last_modified` from the
    commit that last touched it, precisely so the manifest is identical in
    every checkout. Under `fetch-depth: 1` git log exposes one commit, every
    other file falls back to filesystem mtime, and mtime in a fresh checkout is
    checkout day — so the manifest churns on every CI run and the regenerate-
    in-place step commits that churn back. The shallow requirement was correct
    for its original consumer and became wrong when a history-dependent one was
    added alongside it.

    The cost is a slower clone; the benefit is a reproducible manifest and the
    end of a self-inflicted commit-per-run loop.
    """
    parsed = _parsed()
    steps = _all_steps(parsed)
    checkout_steps = [step for step in steps if "actions/checkout" in (step.get("uses") or "")]
    assert checkout_steps, "Expected an `actions/checkout` step"
    for step in checkout_steps:
        with_block = step.get("with") or {}
        fetch_depth = with_block.get("fetch-depth")
        assert fetch_depth == 0, (
            "checkout must use `fetch-depth: 0` (full history) — "
            "`build_doc_manifest.py` derives `last_modified` from git commit "
            "dates so the manifest is reproducible across checkouts; under a "
            "shallow clone it falls back to mtime and the manifest churns on "
            f"every run (got fetch-depth={fetch_depth!r})"
        )
