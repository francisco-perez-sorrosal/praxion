# SPEC: P5 — Praxion-Side Issue Autofix (Self-Healing Loop Subsystem C)

**Task slug**: `p5-issue-autofix`
**Feature**: Label-gated, triage-first workflow that lets Praxion auto-fix `ecosystem-feedback`-labeled issues filed by the P4 sidecar, with every resulting PR reviewed by the P2 cross-model gate
**Tier**: Standard
**Pipeline branch**: `feat/self-healing-p5` (stacked on `feat/self-healing-p4`)
**Start date**: 2026-07-24
**End date**: 2026-07-28
**Archived**: 2026-07-29 (retroactively, per ground-truth reconciliation — see Note below)
**Status**: Shipped — verifier PASS-WITH-FINDINGS (0 FAIL, 6 WARN all known-and-accepted/minor); ADRs finalized as `dec-281`, `dec-282`, `dec-283`
**ADRs**: `dec-281` (label application as the HITL arming gate), `dec-282` (Praxion-only workflow, hub extraction deferred), `dec-283` (triage-first, deny-by-default safety-tier classification)

## Note on Archival

This SPEC was archived retroactively on 2026-07-29 after ground-truth reconciliation found the pipeline's actual work (code, tests, ADRs) was complete and merged to `main` between 2026-07-24 and 2026-07-28, but the `.ai-work/p5-issue-autofix/` close-out (WIP.md checkboxes, fragment-file merge, this SPEC archival) was never performed — a bookkeeping lapse, not incomplete work. See `reconcile_pipeline_state.py` output and the verifier's final report for the evidence trail. This archival specifically closes finding **W-05** from that report (canonical `traceability.yml` left unreconciled).

## Feature Summary

Ships `.github/workflows/issue-autofix.yml` (label-gated on `ecosystem-feedback`, non-Bot actor) and `scripts/praxion_feedback/issue_triage.py` (template validation + fingerprint/dedup). A defect classified mechanical gets a smallest-fix PR (`issue-autofix/<n>-<slug>`, `Fixes #<n>`); a defect classified behavioral/architectural gets a root-cause comment + `needs-adr` label and no PR. Sensitive-path fixes auto-convert to draft with a human-review warning. Daily run budget, idempotency guard, and SHA-pinned actions (matching P1's pins) round out the safety envelope.

## Acceptance Criteria

- [x] **AC-01**: Workflow triggers only on `ecosystem-feedback` applied by a non-Bot actor; any other label or Bot-applied label is a no-op.
- [x] **AC-02**: Untrusted issue body/title is fetched and sanitized in a non-agent step, read by the agent strictly as DATA.
- [x] **AC-03**: A malformed issue (missing required §5.2 sections) gets `triage:invalid` + comment; the fix step never runs.
- [x] **AC-04**: A duplicate issue (fingerprint match) gets `duplicate` + a comment linking the original; the fix step never runs.
- [x] **AC-05**: A mechanical defect produces an `issue-autofix/<n>-<slug>` PR with `Fixes #<n>`; the workflow never pushes to the default branch.
- [x] **AC-06**: A behavioral/architectural defect produces a root-cause comment + `needs-adr`, no PR.
- [x] **AC-07**: A mechanical fix touching a sensitive path (`.github/`, `scripts/`, `hooks/`) auto-converts to draft with a human-security-review warning.
- [x] **AC-08**: No `track_progress`; fixer job holds exactly the four declared permissions, no `actions:` grant.
- [x] **AC-09**: All action refs SHA-pinned to P1's exact commits; Bash tool allowlisted (no blanket shell).
- [x] **AC-10**: Daily run budget enforced; exceeding it is a clean skip with a notice.
- [x] **AC-11**: Re-applying `ecosystem-feedback` to an already-terminally-labeled or open-PR issue is idempotent (skips).
- [x] **AC-12**: Every `issue-autofix/*` PR is reviewed by the P2 cross-model gate (PASS-by-composition — P2's `agent-prs` scope already matches; no P5-side gate code needed).
- [x] **AC-13**: No AI-authorship lines in any commit the fixer creates.

## Traceability Matrix

| REQ | Description | Tests | Implementation | Notes | Status |
|-----|-------------|-------|-----------------|-------|--------|
| REQ-01 | Trigger only on `ecosystem-feedback` + non-Bot sender | `test_arming_gate_requires_exact_label_and_non_bot_sender`, `test_trigger_is_issues_labeled_only` | `.github/workflows/issue-autofix.yml` | job `if:` (label==ecosystem-feedback && sender.type!=Bot) | PASS |
| REQ-02 | Any other label or Bot sender is a structural no-op | `test_arming_gate_conjuncts_are_joined_by_and_not_or`, `test_agent_cannot_self_arm_via_its_own_label_applications` | `.github/workflows/issue-autofix.yml` | job `if:` (structural skip) | PASS |
| REQ-03 | Per-issue concurrency, no cancel-in-progress | `test_concurrency_group_is_scoped_per_issue`, `test_concurrency_never_cancels_an_in_flight_run` | `.github/workflows/issue-autofix.yml` | top-level concurrency group | PASS |
| REQ-04 | Daily run budget enforced | `test_daily_budget_gate_step_exists` | `.github/workflows/issue-autofix.yml` | step "Enforce daily run budget" | PASS |
| REQ-05 | Idempotency guard on terminal labels / open PR | `test_idempotency_guard_checks_terminal_labels_or_open_pr` | `.github/workflows/issue-autofix.yml` | step "Skip if already triaged..." | PASS |
| REQ-06 | Untrusted body/title fetched+sanitized, read as DATA | `test_issue_body_fetch_step_is_non_agent`, `test_raw_issue_body_and_title_never_appear_in_a_prompt_block`, `test_fetch_output_is_sanitized_before_the_agent_reads_it`, `test_prompt_frames_issue_content_as_untrusted_data` | `.github/workflows/issue-autofix.yml` | step "Fetch and sanitize issue body" | PASS |
| REQ-07 | Missing required §5.2 sections -> `triage:invalid`, stop | `test_template_validate_step_references_the_triage_module`, `test_malformed_issue_gets_triage_invalid_label`, + 6 `issue_triage.py` unit tests (`parse_sections`/`missing_required_sections`) | `scripts/praxion_feedback/issue_triage.py`, `.github/workflows/issue-autofix.yml` | first: `parse_sections()`, `missing_required_sections()`, `REQUIRED_SECTIONS`; second: step "Template-validate and dedup" | PASS |
| REQ-08 | Fingerprint/dedup match -> `duplicate`, stop | `test_duplicate_issue_gets_duplicate_label`, `test_dedup_search_excludes_the_current_issue`, + 7 `issue_triage.py` unit tests (`extract_fingerprint`/`dedup_signature`) | `scripts/praxion_feedback/issue_triage.py`, `.github/workflows/issue-autofix.yml` | first: `extract_fingerprint()`, `dedup_signature()`; second: step "Template-validate and dedup" | PASS |
| REQ-09 | Reproduction contained to an allowlisted, non-blanket Bash set | `test_allowed_tools_declares_no_blanket_shell_pattern`, `test_allowed_tools_is_an_enumerated_git_gh_pytest_set`, `test_allowed_tools_excludes_gh_issue_create`, `test_allowed_tools_excludes_gh_run_view`, `test_allowed_tools_never_grants_a_blanket_git_push`, `test_no_step_pushes_directly_to_the_default_branch`, `test_prompt_forbids_pushing_to_the_default_branch` | `.github/workflows/issue-autofix.yml` | fixer step `claude_args.allowedTools` + prompt REPRODUCTION section | PASS |
| REQ-10 | Mechanical fix -> `issue-autofix/<n>-<slug>` PR, `Fixes #<n>` | `test_prompt_references_the_mechanical_fix_pr_path`, `test_prompt_distinguishes_mechanical_from_behavioral` | `.github/workflows/issue-autofix.yml` | fixer prompt MECHANICAL path | PASS |
| REQ-11 | Behavioral/architectural -> root-cause comment + `needs-adr`, no PR | `test_prompt_references_the_behavioral_needs_adr_path` | `.github/workflows/issue-autofix.yml` | fixer prompt BEHAVIORAL/ARCHITECTURAL path | PASS |
| REQ-12 | Deny-by-default on governance surfaces | `test_prompt_names_the_deny_by_default_governance_surfaces` | `.github/workflows/issue-autofix.yml` | fixer prompt CLASSIFY section | PASS |
| REQ-13 | Sensitive-path fix -> draft + human-review warning | `test_sensitive_path_tripwire_step_exists`, `test_sensitive_path_tripwire_targets_the_issue_autofix_branch_prefix`, `test_sensitive_path_tripwire_toggles_draft_via_gh_pr_ready_undo` | `.github/workflows/issue-autofix.yml` | sensitive-path tripwire step | PASS |
| REQ-14 | No `track_progress`; status via `gh` comment/edit only | `test_never_references_track_progress` | `.github/workflows/issue-autofix.yml` | fixer step (no track_progress) | PASS |
| REQ-15 | All action refs SHA-pinned, matching P1 | `test_every_uses_reference_is_sha_pinned`, `test_checkout_pin_matches_p1_exact_commit`, `test_setup_uv_pin_matches_p1_exact_commit`, `test_claude_code_action_pin_matches_p1_exact_commit` | `.github/workflows/issue-autofix.yml` | checkout/setup-uv/claude-code-action pins | PASS |
| REQ-16 | Fixer job holds exactly the four declared permissions | `test_fixer_job_permissions_are_exactly_the_four_declared_grants`, `test_no_job_grants_actions_permission`, `test_no_job_grants_broader_permissions_than_declared` | `.github/workflows/issue-autofix.yml` | job permissions block | PASS |
| REQ-17 | Every `issue-autofix/*` PR reviewed by P2 cross-model gate | — (no P5 code by design) | — | `.github/workflows/reusable-cross-model-review.yml`'s `agent-prs` scope already matches `issue-autofix/*` | PASS-by-composition (P2's `reusable-cross-model-review.yml` `agent-prs` scope already matches `issue-autofix/*`; realized once `feat/self-healing-p2` merges to `main`) |
| REQ-18 | No AI-authorship lines in fixer commits | `test_prompt_forbids_ai_authorship_commit_lines` | `.github/workflows/issue-autofix.yml` | fixer prompt COMMIT HYGIENE section | PASS |

## Decisions Made

| ADR | Title | Category | Key Decision |
|-----|-------|----------|---------------|
| `dec-282` | Praxion-only issue-autofix workflow, hub extraction deferred | architectural | Ships as a Praxion-only direct workflow, not a hub reusable workflow — only Praxion receives `ecosystem-feedback` issues in v1; extraction is a clean bounded refactor if a second consumer appears |
| `dec-281` | Label application is the HITL arming gate | architectural | Applying `ecosystem-feedback` arms the fixer, enforced by three independent layers (GitHub's label-permission model, non-Bot actor guard, payload gate) — zero new secrets, single auditable arming event |
| `dec-283` | Triage-first, deny-by-default safety-tier classification | architectural | Fixer opens a PR only for mechanical defects; behavioral/architectural defects and any touch of governance surfaces route to `needs-adr` with no PR |

No ADR filed for the `scripts/praxion_feedback/issue_triage.py` module-structure choice — a mechanical, option-free application of the existing sibling-module pattern (`render.py`/`fingerprint.py`/`sanitizer.py`), not a genuine trade-off fork.

## Verification Summary

Final verifier pass (2026-07-24): **0 FAIL, 6 WARN** — all "Known-and-accepted" or minor hygiene (live-dogfood-only behavioral verification W-01; no branch protection on `main` W-02; one-time label bootstrap W-03; P2-merge-order sequencing W-04; this traceability reconciliation W-05, now closed; no `TEST_BASELINE.md` since P5 is purely additive W-06). Full test suite: 43 (`tests/test_issue_autofix_workflow_invariants.py`) + 15 (`scripts/praxion_feedback/tests/test_issue_triage.py`) + 79 (full `praxion_feedback` package, no regression). Project-wide suite: 325 passed at verification time, no regressions. All 6 pre-mortem failure modes (FM-1 through FM-6) addressed with dedicated tests.
