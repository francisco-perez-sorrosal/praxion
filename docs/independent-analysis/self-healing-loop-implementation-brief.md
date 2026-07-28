# Self-Healing Loop — Implementation Brief (v3, research-grounded)

> v1: [`cursor-ci-autofix-research-brief.md`](cursor-ci-autofix-research-brief.md) (2026-06-20) — the research task spec.
> v2 (2026-07-22): implementation plan grounded in the shipped `ci-autofix.yml`; Cursor deferred to a spike.
> **v3 (this document)**: the spike ran. Three parallel research passes (Cursor surfaces, GitHub Actions /
> `claude-code-action` mechanics, cross-model review evidence) are synthesized here; Cursor is now
> **embedded by design** — as the cross-model review layer, funded by the prepaid credits — and the whole
> loop is made consistent across Praxion itself and every Praxion-managed project.
>
> Research artifacts (ephemeral, read before implementing): `.ai-work/self-healing-loop/RESEARCH_CURSOR.md`,
> `RESEARCH_GHA.md`, `RESEARCH_CROSS_MODEL.md` — each claim below marked **[V]** (verified), **[S]**
> (single-source), or **[U]** (unverified/open) traces to a tagged row there.

Status: implementation starting point. Consumers: `systems-architect` (ADRs), `implementation-planner` (steps).

---

## 1. Ground truth (2026-07-22)

Praxion already ships a first-iteration autofixer — `.github/workflows/ci-autofix.yml`:
`workflow_run`-triggered on `Test`/`Architecture` failures on `main`, Claude (Opus, SHA-pinned
`claude-code-action@v1`) diagnoses from sanitized logs read as *data*, opens a `ci-autofix/` fix PR
(never pushes to main), flake → issue instead of PR, sensitive-path PRs auto-drafted for human review.
Loop prevention: watch-list exclusion + `head_branch` gate + open-PR dedup + serialized concurrency.

Not yet existing: installability into managed projects, PR-check/Dependabot scope, any Cursor role,
and the upstream feedback channel (healing sidecar). Those are this document.

## 2. What the research established (the deltas that shape v3)

### 2.1 Cross-model evidence → Cursor's role is *reviewer*, not failover-fixer

- Self-preference bias is real and causal: a model's ability to recognize its own output predicts how
  much it overrates it; larger models show it **more**, not less **[V — arXiv:2410.21819]**. A 2026
  companion result extends this to monitoring tasks: models under-flag violations in transcripts they
  believe are their own **[V — arXiv:2603.04582]**. This is the strongest argument for your instinct
  that *a different model family should review work produced by another model*.
- But naive multi-model composition backfires: consensus voting amplifies shared errors (the
  "popularity trap"), and heterogeneous agent teams can underperform their best single member by up to
  37.6% **[V/S — arXiv:2510.21513 + Feb-2026 paper, method unretrieved]**. Diversity pays only with a
  diversity-aware aggregation — or, simpler, when the second model is a **non-generative gate**, not a
  second fixer whose output must be reconciled.
- Evidence-ranked role split for a Cursor+Claude stack **[research verdict]**:
  1. **Claude fixes; Cursor reviews every fix as an independent, non-generative gate** ← adopted.
  2. Claude fixes / Cursor reviews (gate-only scoped) — equivalent if never counter-fixing.
  3. Cursor-first fixer with Claude failover — *rejected as the primary design*: failover is a
     cost/availability pattern, not a diversity pattern; most fixes would get **zero** cross-model
     review. (v1's leading hypothesis is thereby answered: the single-provider steelman won for the
     *fixer* role, and the credits found a better home — see 2.3.)
  4. Alternating fixer — least supported; no aggregation step, still permits self-review across cycles.

### 2.2 Cursor mechanics — what is buildable today

- **Headless CLI is the confirmed path** **[V]**: `agent -p "<prompt>" --force --output-format json
  --model <model>`, auth via `CURSOR_API_KEY` secret, official install recipe for GitHub Actions
  (`curl https://cursor.com/install -fsS | bash`). No official first-party GitHub Action exists **[V]**
  — workflows shell out (the third-party marketplace action is unaudited; don't adopt).
- **Per-invocation model pinning** (`--model`, `--list-models`) is confirmed **[V]** — the lever for
  cross-model diversity: pin the review to a **non-Anthropic model** (GPT-class, Gemini-class, or
  Cursor's Composer) so the reviewer's family differs from the fixer's. Model IDs churn; resolve via
  `--list-models` at run time, choose family by prefix, never hardcode an ID.
- **No `--max-turns`/budget flag exists** **[V]** — bound cost externally: job `timeout-minutes`,
  wrapper wall-clock kill, and the policy-file run caps (§4.3).
- **Bugbot** (PR review + optional Autofix via a Cloud Agent) is real and per-repo enableable **[V]**,
  but its REST trigger API is **suspected fetch-tool fabrication** **[U — verify manually before any
  dependence]**. The Cloud Agents REST API is directionally real but its endpoint shape is unconfirmed
  **[S/U]**. → v3 builds on the **CLI only**; Bugbot is an optional per-repo *supplement* (dashboard-
  enabled, zero integration code), Cloud Agents API is out of scope.
- **Credits do not roll over month-to-month** **[V — Cursor forum, company reply]**; no usage/quota API
  and no documented quota-exhaustion exit signature were found **[U]**. Two consequences: (a)
  *use-it-or-lose-it makes spending credits on always-on review economically rational* — better than
  holding them for rare failover; (b) exhaustion handling must **fail open by design**: any non-zero
  exit / malformed JSON from the Cursor step is caught, the gate degrades to "review unavailable"
  (label the PR, never block the fix), and the run is logged. A monthly-cadence check on whether
  CI usage drains the same "fast request" pool as your IDE usage is an operator to-do **[U]**.

### 2.3 The economics, restated honestly

v1 hypothesized "spend prepaid credits on *fixing* first." The evidence flipped the destination, not
the motive: review fires on **every** fix PR (steady, monthly, forfeit-if-unused credits absorb it),
whereas failover-fixing fires only on Anthropic outages/limits (rare, bursty). The review-gate role
spends the credits *more*, more *predictably*, and buys measurable defect-detection value instead of
redundancy you already largely have. Provider redundancy survives in degraded form: if Anthropic is
down, fixes pause but Cursor review of human PRs continues; a manual `provider: cursor` fixer flip
remains a documented break-glass (§4.3), not an automated path.

### 2.4 `claude-code-action` + GitHub mechanics — corrections to v2

- `workflow_run` is a security-recognized trigger for the action (its security doc gives it a named
  secure-checkout recipe alongside `pull_request_target`) **[V]**, resolving the shipped workflow's
  "KNOWN UNVERIFIED ASSUMPTION" in our favor — but confirm against raw `action.yml` at P0 (fetch
  summaries showed one internal contradiction elsewhere). The documented bridge for rejected events is
  `repository_dispatch` **[V — real-world error + docs]**.
- `issues` events (`opened`/`assigned`/**`labeled`**) are documented supported **[V]** — Subsystem C's
  trigger is safe.
- **`track_progress: true` has an open bug (#860): it silently grants all write tools regardless of
  `--allowedTools`** **[V]**. → Never set `track_progress` in any autofix workflow; status comments are
  posted by a plain `gh` step instead.
- Dependabot secrets: `workflow_run` chained off a Dependabot-triggered run draws from the regular
  **Actions** secrets store **[V]** — our trigger architecture solves §2.1-of-v1 by construction.
  Edge case: if a PR's *base* ref was itself Dependabot-created, tokens go read-only regardless
  **[S]** — detect and skip-and-flag.
- Loop prevention must be **layered** **[V]**: actor guard + `conclusion == 'failure'` +
  branch/actor payload gates + concurrency group. `[skip ci]` only suppresses push-triggered runs —
  insufficient alone. (The shipped workflow already layers correctly; the reusable workflow inherits it.)
- Cross-repo reusable workflows: private caller → public hub works (Praxion is public); reference
  syntax supports SHA pinning **[V]**; nested-depth/count limits unverified this session **[U — confirm
  at P1]**.
- Cross-repo `gh issue create` **cannot** use the default `GITHUB_TOKEN` **[V]**; a fine-grained PAT
  needs `Issues: Write` + transitively `Contents: Read` **[V]**; least-privilege long-term answer is a
  GitHub App minting short-lived installation tokens **[V-adjacent]**. → sidecar v1 rides the
  operator's own `gh` auth (HITL anyway); CI-automated filing, if ever, means a fleet App.

## 3. Target end state — the closed loop (unchanged shape, refined internals)

```
[Managed project N]                                [Praxion repo]
  CI / PR check / Dependabot failure                 ecosystem-feedback issue (labeled = armed)
        │                                                  │
        ▼                                                  ▼
  per-repo autofix (installed copy)                  issue-triage autofix
    Claude diagnoses → fix PR                          Claude triages/reproduces → fix PR
        │                                                  │
        ▼                                                  ▼
  Cursor cross-model review gate ──────────────────  Cursor cross-model review gate
    (non-Anthropic model, gate-only)                       │
        │                                                  ▼
        ▼                                            human merge → release / pin bump
  human merge                                              │
        ▲                                                  ▼
  healing sidecar: Praxion-origin defect            managed projects receive the fix via
  observed here → sanitized, deduped,               block-refresh manifest (dec-271) +
  HITL-acked issue filed upstream ─────────────►    version-pin upgrades
```

Every fix — in a managed project or in Praxion itself — is authored by one model family and
independently reviewed by another before a human merges it. The sidecar feeds Praxion-origin defects
into the same machinery, and Praxion's existing distribution channel closes the loop. **The same two
workflows serve both sides**: Praxion is caller #1 of everything it ships.

## 4. Subsystem A — per-project CI/PR autofix + cross-model gate

### 4.1 Package shape (per-project ownership, v1's hard requirement)

- **Hub**: two reusable workflows in the Praxion repo (public → callable from private managed repos [V]):
  - `.github/workflows/reusable-ci-autofix.yml` — trigger gating, log sanitization, Claude fix step,
    sensitive-path tripwire, budget caps (generalizes the shipped workflow).
  - `.github/workflows/reusable-cross-model-review.yml` — the Cursor gate (§4.2).
- **Canonical assets** in `claude/project-baseline/ci-autofix/`: caller templates
  (`ci-autofix.yml.tmpl`, `cross-model-review.yml.tmpl`) + `autofix-policy.yml.tmpl`. Callers pin the
  hub by **full commit SHA** (mirror the action-pinning discipline; confirm workflow_call-specific
  guidance at P1 [U]); upgrades are deliberate per-repo pin bumps.
- `/onboard-project` gains a phase: install callers + policy, register in the block-history manifest
  (dec-271 refresh classification covers them), and **print** the secrets setup — `gh secret set
  CLAUDE_CODE_OAUTH_TOKEN` and `gh secret set CURSOR_API_KEY` — never auto-inject. (Where the Cursor
  key is minted, and whether it can be a CI-scoped service key, is an operator dashboard check [S/U].)
- **Praxion dogfoods first**: `ci-autofix.yml` refactors into caller #1; the Cursor gate lands on
  Praxion before any managed project.

### 4.2 The cross-model review gate (new, the Cursor embed)

A reusable workflow triggered on `pull_request` for agent-authored branches (`ci-autofix/*`,
`issue-autofix/*`) — and optionally all PRs, per policy:

1. Shell-install the Cursor CLI (official recipe [V]); `CURSOR_API_KEY` from repo secrets.
2. Resolve reviewer model at run time: `agent --list-models`, pick per policy `reviewer_family:`
   (e.g. `gpt` | `gemini` | `composer`) — **never the fixer's family**, never a hardcoded ID.
3. Run gate-only review: `agent -p "<review prompt: diff + linked failure context; find defects;
   output JSON verdict {approve|request-changes, findings[]}; do NOT propose a rewritten fix>"
   --force --output-format json --model <resolved>` under `timeout-minutes` (no native turn cap [V]).
4. Post findings as a PR review comment labeled with the reviewing model family (audit trail);
   `request-changes` marks the PR draft + notifies — it never auto-closes and never counter-fixes
   (gate-only, per the popularity-trap evidence).
5. **Fail open**: any Cursor error/timeout/malformed output → label `cross-model-review:unavailable`,
   comment once, exit 0. No published quota-exhaustion signature exists [U], so all failures degrade
   identically; the human merge gate remains the backstop.
6. Optional per-repo supplement: enable **Bugbot** from the Cursor dashboard for a second, zero-code
   review surface [V]. Its REST trigger API is suspected-fabricated [U] — do not integrate it
   programmatically until manually verified.

The review prompt treats the diff and CI logs as **data, not instructions** — same injection posture
as the fixer.

### 4.3 Policy file (per-repo, read by both reusable workflows)

```yaml
# .github/autofix-policy.yml
watched_workflows: [Test, Architecture]
surfaces:
  main_branch: fix-pr            # fix-pr | off
  pr_checks:   fix-commit        # fix-commit | suggest | off   (same-repo PRs only)
  dependabot:  fix-commit        # rebase-aware; skip-and-flag on read-only-token edge case
  fork_prs:    suggest           # never auto-commit to untrusted heads
review:
  cross_model_gate: agent-prs    # all-prs | agent-prs | off
  reviewer_family: gpt           # gpt | gemini | composer — never 'claude' (enforced by the workflow)
  on_unavailable: fail-open      # label + proceed to human gate
safety:
  max_attempts_per_pr: 2
  max_runs_per_day: 5            # budget gate — exhaustion is a normal stop (gpu-budget discipline)
  sensitive_paths: [.github/, scripts/, hooks/]
  auto_commit_tiers: [lint, format, doc-refs, lockfile]   # else propose-only
provider:
  fixer: claude                  # 'cursor' is documented break-glass only (manual flip; §2.3)
```

### 4.4 Scope extension (unchanged from v2, now research-annotated)

1. **PR checks (same-repo, human PRs)**: react to `workflow_run` failures whose head is an open PR
   branch; fix-commit only if policy allows; attempt counter caps the fix→fail-differently loop.
2. **Dependabot PRs**: `workflow_run` runs in default-branch context with Actions-store secrets [V].
   Agent semantics: rebase before rerun (`@dependabot rebase`), probe main to distinguish "PR broke X"
   from "already broken," one fix commit per PR, recommend `groups:` in `dependabot.yml.tmpl`.
   Detect the Dependabot-base-ref read-only edge case [S] → skip-and-flag.
3. **Fork PRs**: suggested-patch comments only; `pull_request_target` stays banned; if PR file
   inspection is ever needed, use the documented base-ref-root + `path: pr-head` subdirectory +
   `--add-dir` recipe [V].
4. **Never set `track_progress`** (tool-scope leak, bug #860 [V]); status via plain `gh` steps.

## 5. Subsystem B — healing sidecar (managed → Praxion feedback)

### 5.0 Build by adaptation, not from scratch — the `/report-upstream` reuse map

Praxion already ships a complete upstream-issue-filing stack; the sidecar is an *instance* of it with
the target fixed to the Praxion repo:

| Existing asset | Reused as-is | Sidecar delta |
|---|---|---|
| `/report-upstream` command (validate → reconnaissance → dedup → draft → sanitize → security gate → HITL file → track) | the whole pipeline shape | new thin `/report-praxion-issue` variant: target hardcoded, category taxonomy (`hooks\|blocks\|agents\|scripts\|skills`), fingerprint embedded, body rendered from the §5.2 schema |
| `upstream-stewardship` skill (dedup decision tree, sanitization pipeline + `secret-patterns.md`, template compliance, Ten Simple Rules, responsible-disclosure path) | verbatim | none — the methodology transfers unchanged |
| `.ai-state/UPSTREAM_ISSUES.md` tracker | verbatim | doubles as the managed-project-side dedup record alongside the fingerprint search |
| Agent Discovery Protocol (document → flag → never file autonomously) | verbatim | capture points additionally append to `PENDING.md` |

Build cost collapses to: the template pair (§5.2), fingerprint computation, category taxonomy,
`PENDING.md` capture plumbing, and the thin command wrapper. Shipped pieces reference path *shapes*
only (shipped-artifact-isolation rule).

- **What it reports**: only defects whose root cause is a *shipped Praxion artifact* observed during
  Praxion-process execution in the managed project — hook crashes, wrong canonical blocks/templates,
  agent/skill protocol defects, script failures on legitimate state, sentinel/verifier findings with
  plugin-origin root cause, td-ledger rows whose owner resolves to the plugin. Never project-local bugs.
- **Mechanism**: `scripts/report_praxion_issue.py` + `/report-praxion-issue` command; capture points
  append candidates to `.ai-state/praxion_feedback/PENDING.md`; the orchestrator surfaces pending
  reports at session start. **HITL-acked filing only in v1** (outward-facing action; behavioral
  contract + `upstream-stewardship` discipline). Dedup by
  `sha(category + artifact-path + normalized-error)` fingerprint searched against open issues before
  filing. Sanitizer strips absolute paths, usernames, secret-shaped strings, and proprietary content.
- **Auth (research-corrected)**: v1 rides the operator's own `gh` auth — the default `GITHUB_TOKEN`
  cannot file cross-repo [V], and this keeps zero new secrets in managed repos. If auto-filing is ever
  justified (see ADR seed 3's reversal trigger), the correct instrument is a **GitHub App** minting
  short-lived installation tokens — not a long-lived wide-allowlist PAT [V]; a fine-grained PAT would
  need `Issues: Write` + `Contents: Read` per target [V].
### 5.2 The issue-template contract (research-grounded)

Studied raw templates from `anthropics/claude-code`, `claude-code-action`, `microsoft/playwright`,
`kubernetes/kubernetes`, `rust-lang/rust` (full comparison:
`.ai-work/self-healing-loop/RESEARCH_ISSUE_TEMPLATES.md`). Two load-bearing facts:

- **GitHub Issue Forms (`.yml`) are UI-only** — `gh issue create`/REST can only post raw
  title+body+labels (`cli/cli#5865` [V]), and once an issue exists it is just a markdown body
  regardless of how it was created. → **No `.yml` form at all.** The single contract is a legacy
  markdown template (`.github/ISSUE_TEMPLATE/ecosystem-defect.md` in the Praxion repo) whose body IS
  the machine schema below: humans get it pre-filled in the browser; the reporter posts the identical
  structure via `--body-file`. One artifact, both entry paths, nothing to keep in sync. Browser-side
  required-field enforcement is not missed — Subsystem C's triage validates the schema and labels
  malformed issues `triage:invalid`, a stronger gate than form validation.
- Best-of-breed borrowings: Claude Code's dedup gate + CLI-driven version capture (→ fingerprint +
  manifest-derived version); Playwright/Rust's *tool-generated environment dump* (an agent runs the
  diagnostic command itself — no dropdowns); Playwright's hard minimal-repro mandate (→ a literal
  runnable reproduction command); a tri-state regression field.

**Markdown body schema** (rendered by `report_praxion_issue.py`, validated by Subsystem C —
five fields no human template has, because a human supplies identity/judgment implicitly):

```markdown
## Fingerprint
`sha256:<hash(category + artifact-path + normalized-error)>`   <!-- the dedup key -->

## Plugin / Component
- Category: hooks | blocks | agents | scripts | skills
- Artifact: `<repo-relative path of the shipped artifact>`
- Plugin version: `<from block-history manifest>` (+ commit SHA if a moving ref)
- Host runtime: `<e.g. Claude Code x.y, Python 3.11>`

## Capture Provenance
- Detected by: `<agent/hook/command name>` at `<detection point>`, `<ISO8601>`
- Confidence: high|med|low — <one-line basis>

## Expected vs Observed
**Expected:** … **Observed:** …

## Reproduction Command
```bash
<exact non-interactive command a fixer agent re-executes>
```
(+ optional numbered prose steps if the command alone is insufficient)

## Evidence Excerpt (sanitized)
<log tail / stack trace after the upstream-stewardship sanitization pipeline>

## Environment
<diagnostic-command dump, not hand-enumerated>

## Regression Status
regression: yes|no|unknown; last known-good: <version|n/a>
```

Labels applied at filing: `ecosystem-feedback` is **not** among them — the maintainer adds it (that
label is Subsystem C's arming gate, §6); the reporter applies `bug`, `auto-filed`,
`category:<slug>`, `from-managed-project`. Human filers use the same markdown template pre-filled by
GitHub in the browser — the machine-only fields (fingerprint, provenance) carry an inline
`<!-- leave blank if filing manually -->` note and triage tolerates their absence from human filings.

## 6. Subsystem C — Praxion-side issue autofix

- **Trigger**: `on: issues, types: [labeled]`, gated on `ecosystem-feedback` — a documented-supported
  event for `claude-code-action` [V]. **Label application is the HITL security gate**: anyone can open
  an issue; only a maintainer applying the label arms the agent. Issue bodies are untrusted data at
  scale — fetched/sanitized in a non-agent step, read as data, exactly like CI logs.
- **Triage-first**: validate against the sidecar's structured template (malformed/duplicate →
  `triage:invalid`/`duplicate` comment, stop) → attempt local reproduction (Praxion's tests +
  evidence) → classify by safety tier: mechanical fixes → `issue-autofix/` fix PR; behavioral/
  architectural defects → analysis comment + `needs-adr`, stop (route to the normal pipeline — an
  issue is not a license to redesign).
- **The same cross-model gate (§4.2) reviews every `issue-autofix/` PR** — Praxion's own fixes get the
  same diversity discipline it prescribes for managed projects.
- Budget caps, concurrency serialization, sensitive-path tripwire, and layered loop prevention
  (actor guard + payload gates + concurrency [V]) all inherit from the reusable workflow.
- **Loop closure**: fix merges → release/pin bump → dec-271 block refresh / pin upgrades carry it to
  the fleet; the workflow closes the issue linking the fix PR and carrying release.

## 7. Security & governance summary

| Surface | Risk | Mitigation |
|---|---|---|
| Fixer prompt channel | injection via CI logs / issue bodies / diffs | non-agent fetch + sanitize; data-not-instructions framing; no `track_progress` (bug #860 [V]); Bash tool allowlisted per command pattern [V] |
| Reviewer prompt channel | same, via the Cursor step | same posture; gate-only output (JSON verdict), no write tools needed at all |
| Privileged triggers | `pull_request_target` footgun; untrusted checkout | `workflow_run` preferred [V]; base-ref-root checkout recipe [V]; fork PRs suggest-only |
| Dependabot context | secrets exposure / read-only edge | Actions-store semantics via `workflow_run` [V]; base-ref edge case skip-and-flag [S] |
| Loops | agent output re-triggering agents | layered: watch-list exclusion + actor guards + payload gates + concurrency + PR dedup [V] |
| Two-vendor secret surface | `CURSOR_API_KEY` joins the Claude token in every repo | reviewer job gets **no** `contents: write`; key scoped CI-only if Cursor supports it [U — operator check]; per-repo secrets, no org-wide blast radius |
| Cursor cost drain | CI review drains the shared credit pool | policy run caps + `timeout-minutes` (no native cap [V]); monthly operator check of pool attribution [U]; fail-open means exhaustion never blocks fixes |
| Cross-repo issues | leaking private content upstream; issue-spam arming the agent | sanitizer + HITL filing (B); maintainer label as arming gate (C) |
| Fleet blast radius | bad hub change hits N repos | SHA-pinned callers; deliberate per-repo bumps; Praxion dogfoods first |
| Auditability | who fixed, who reviewed | fixer PRs carry root-cause bodies; review comments name the model family; metrics rows (fix success, time-to-green, gate catch rate, override rate, cost-per-fix) appendable to `.ai-state/metrics_reports/` |

## 8. Phased roadmap

| Phase | Content | Tier | Depends on |
|---|---|---|---|
| **P0 — verify & harden the seed** | Raw-fetch `claude-code-action` `action.yml`/docs to confirm `workflow_run` + `issues` verbatim (fetch-summary caveat); manually `curl` the Bugbot API page (fabrication check); dashboard check: CURSOR_API_KEY minting + CI scoping + credit-pool attribution; add run-budget cap to shipped workflow; backfill its ADR | Direct/Lightweight | — |
| **P1 — installable core** | Extract `reusable-ci-autofix.yml`; caller + policy templates in `claude/project-baseline/ci-autofix/`; Praxion = caller #1; `/onboard-project` phase + manifest registration; confirm reusable-workflow limits [U] | Standard | P0 |
| **P2 — cross-model gate** | `reusable-cross-model-review.yml` (§4.2) + caller template; dogfood on Praxion's own `ci-autofix/` PRs; optionally enable Bugbot on Praxion as the comparison baseline | Standard | P0 (P1 for fleet rollout) |
| **P3 — PR checks + Dependabot** | §4.4 scope extension | Standard | P1 |
| **P4 — healing sidecar** | Reporter + command + PENDING.md capture + sanitizer + onboarding hook-in (§5) | Lightweight/Standard | — |
| **P5 — Praxion issue autofix** | §6 workflow, triage-first, label-gated, gate-reviewed | Standard | P0 (P2 for the gate) |
| **P6 — measure & recalibrate** | 60–90 days of metrics: gate catch rate vs noise, credit burn, fix success; revisit ADR seeds' reversal triggers (incl. whether Bugbot replaces or complements the CLI gate, and whether auto-filing (B) is justified) | Lightweight | P2+P5 live |

P4 is independent and can start immediately; P2 is the highest-leverage novel piece.

## 9. ADR seeds (Disconfirmation-ready)

1. **Claude-fixes / Cursor-reviews role split** (supersedes v1's Cursor-first-failover hypothesis).
   *Falsifier*: gate catch-rate ≈ 0 with high noise over P6's window, or evidence emerges that
   same-family review performs equivalently. *Steelmanned runner-up*: Cursor-first fixer failover —
   wins if Anthropic availability becomes the binding constraint or credit volume dwarfs review needs.
   *Reversal trigger*: sustained Anthropic outages, or Cursor ships a verified quota API + turn caps
   making it the safer fixer.
2. **Hub reusable workflows + SHA-pinned per-repo callers** (vs fully-copied templates vs GitHub App).
   *Falsifier*: cross-repo `workflow_call` limits or private-repo friction at fleet scale [U → P1].
   *Runner-up*: fully-copied templates refreshed via the dec-271 manifest.
3. **HITL-gated sidecar, no unattended cross-repo filing in v1**. *Reversal trigger*: sustained
   low false-positive rate in PENDING.md candidates → auto-file a whitelisted category subset via a
   minimal-permission GitHub App (never a wide PAT).
4. **Label-application as the arming gate for issue autofix**. *Falsifier*: maintainers rubber-stamp
   labels, collapsing the gate.
5. **Gate fails open** (review unavailability never blocks a fix). *Falsifier*: a defect merges that
   an available gate would plausibly have caught while the gate was down more than rarely — then
   revisit fail-closed for `sensitive_paths` tiers only.

## 10. Open questions (all carried into P0/P6, none blocking P1/P4)

- Verbatim `claude-code-action` event list from raw `action.yml` (fetch-summary contradiction on
  `workflow_dispatch`). — P0
- Bugbot REST API: real or fabricated summary? — P0 manual check.
- Cloud Agents API endpoint/auth shape (SPA blocked automated reads). — only if a future phase wants
  cloud-offloaded fixing.
- Cursor credit-pool attribution (CLI/Bugbot/IDE shared?) and CI-scoped API keys. — P0 dashboard check.
- Quota-exhaustion exit signature — likely answerable only empirically; fail-open design makes it
  non-blocking.
- Reusable-workflow nesting/count limits at fleet scale. — P1.
- Whether `claude-code-action`'s GitHub App auth installs per-repo or fleet-wide (affects onboarding
  instructions, not architecture). — P1.
- Evidence gap to watch: no study yet isolates code-review defect-miss-rate for self- vs cross-model
  review specifically; P6's own metrics become Praxion's first-party evidence.
