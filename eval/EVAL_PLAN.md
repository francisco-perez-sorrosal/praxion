# Praxion Self-Eval Plan

Design narrative for `/eval-praxion` — the out-of-band quality gate Praxion applies to itself.

## Motivation

The `eval/` framework predates v1. Before v1, it shipped two modes:

- **Behavioral** (`/eval behavioral`) — filesystem-only artifact-manifest check against a completed `.ai-work/<slug>/`. This mode works and remains unchanged under `/eval`.
- **Regression** (`/eval regression`) — Phoenix trace diff against a committed baseline JSON. This mode was **broken by design**: baselines were keyed by `task_slug`, but Praxion slugs are one-shot — each feature generates a unique slug, runs once, and gets cleaned up. There is never a "next run" on the same slug, so drift detection has no corpus to work with. The bug was compounded by a missing `arize-phoenix` dependency that swallowed the connectivity error silently.

`td-005` in `.ai-state/TECH_DEBT_LEDGER.md` tracked this as a scheduled full effort. The trigger for v1 was `dec-040`'s deferred LLM-as-judge clause: the now-retired `judges/anthropic.py` stub explicitly cited dec-040 as the deferral reason, and the proper resolution required a new ADR (partial supersession of clause 3) plus a real harness. The `judges/` package was retired in v1 alongside `regression/` — the `harness/judge_client.py` adapter is the sole judge surface.

`dec-204` narrows dec-040 clause 3 to allow LLM-as-judge calls over **completed artifacts** out-of-band, while re-affirming clauses 1, 2, and 4. v1 implements that resolution. `td-005` migrates to `TECH_DEBT_RESOLVED.md` with `resolved-by: dec-204` (rewritten to `dec-NNN` at merge-to-main via `scripts/finalize_adrs.py`).

## Why separate from sentinel

The sentinel (`/sentinel`) is an ecosystem-wide coherence auditor. It checks ten dimensions (DL/SH/TT/TD/CA/EC/ID/AT/HK/EV) against current on-disk state and produces a health grade. Its job is **structural health** — are the right files present, do cross-references resolve, are conventions followed?

`/eval-praxion` is a **semantic quality gate**. It asks: are the artifacts that pipelines produce actually good? Specifically:

- Are Praxion's own ADRs well-reasoned, with substantive `## Considered Options` content rather than token options?
- Do finalized decisions carry reciprocal cross-references (supersession links, re-affirmation back-links)?
- Does the verifier's behavioral-contract analysis in `VERIFICATION_REPORT.md` reflect a genuine four-behavior audit?

These questions require reading artifact content and applying judgment — they are not answerable by structural inspection alone. The sentinel runs mechanical checks at scale; the eval harness runs LLM-judged checks on semantics.

Boundary summary:

| | Sentinel | `/eval-praxion` |
|---|---|---|
| Input | Entire ecosystem | Completed artifact corpus (specs, ADRs, verification reports) |
| Method | Mechanical scan | Mechanical + LLM-judged |
| Output | Health grade, 10 dimensions | Per-check PASS/WARN/FAIL, cost estimate |
| Invocation | `/sentinel` | `/eval-praxion [target]` |
| When to run | Ecosystem health check, pre-release | After a multi-ADR pipeline, periodic quality audit |

## Shipped (v1)

v1 ships two check families.

### Family 1 — Pipeline-outcome fidelity

Source: `eval/src/praxion_evals/harness/families/family1_pipeline_fidelity.py`

Corpus: `.ai-state/specs/SPEC_*.md`, `.ai-state/decisions/*.md`, `.ai-state/decisions/DECISIONS_INDEX.md`

**Mechanical checks** (no API calls):

| Check | Corpus slice | Verdict |
|-------|-------------|---------|
| ADR frontmatter completeness | All finalized ADRs | PASS / FAIL per ADR |
| ADR body section presence | All finalized ADRs | PASS / FAIL per ADR |
| Supersession reciprocity | ADRs with `supersedes` | PASS / FAIL per link |
| Re-affirmation reciprocity | ADRs with `re_affirms` | PASS / FAIL per link |
| SPEC traceability-matrix presence | All archived SPECs | PASS / FAIL per SPEC |
| `affected_reqs` resolvability | ADRs with populated `affected_reqs` (~20%) | PASS / **WARN** per unresolvable link |
| DECISIONS_INDEX consistency | `DECISIONS_INDEX.md` | PASS / WARN |

**LLM-judged checks** (one API call per ADR/subset):

| Check | Model | Corpus slice | Verdict |
|-------|-------|-------------|---------|
| Option-depth substantiveness | Haiku | All finalized ADRs | PASS / WARN / FAIL per ADR |
| Decision-to-options proportionality | Sonnet | All finalized ADRs | PASS / WARN / FAIL per ADR |

The `affected_reqs` check fires only on the ~20% of ADRs that have a populated `affected_reqs` field. The 80% without the field are not flagged — the field predates the REQ convention for most of the corpus.

### Family 2 — Behavioral-contract adherence

Source: `eval/src/praxion_evals/harness/families/family2_bc_adherence.py`

Corpus (v1): `VERIFICATION_REPORT.md` files only. `LEARNINGS.md` is deferred — see [LEARNINGS-distillation prerequisite](#learnings-distillation-prerequisite) below.

**Mechanical checks** (no API calls):

| Check | What it detects |
|-------|----------------|
| `### Behavioral Contract Findings` section present | Verifier reached Phase 5.5 |
| `[UNSURFACED-ASSUMPTION]` tag scan | Count of tagged occurrences |
| `[MISSING-OBJECTION]`, `[NON-SURGICAL]`, `[SCOPE-CREEP]`, `[BLOAT]`, `[DEAD-CODE-UNREMOVED]` tag scans | Count per tag |

**LLM-judged checks** (one API call per behavior per file):

| Check | Behavior | Model |
|-------|---------|-------|
| BC rubric — Surface Assumptions | Did the verifier's BC findings match the actual evidence? | Sonnet |
| BC rubric — Register Objection | Same pattern | Sonnet |
| BC rubric — Stay Surgical | Same pattern | Sonnet |
| BC rubric — Simplicity First | Same pattern | Sonnet |

The judge runs **per-behavior**, not per-file, so a v2 adversarial-fixture set can be added without changing the rubric.

**v1 calibration gap.** The only available `VERIFICATION_REPORT.md` at v1 launch has no BC violation tags — the verifier emitted clean PASS findings. The LLM judge's false-negative detection is therefore unvalidated against an adversarial fixture. Every v1 report records this gap explicitly in its `## Calibration Notes` section. See also [Family 2 real-corpus validation note](#family-2-real-corpus-validation-note).

## Deferred families

### Family 3 — Dogfooding fidelity

**What it measures.** Verifies that Praxion's own development follows Praxion's conventions end-to-end: does every recent pipeline have an archived SPEC? Are WIP.md completion markers consistent with the commit history? Are LEARNINGS.md patterns distilled into skills on the expected cadence?

**Why deferred.** This family requires a richer corpus model than v1's corpus reader provides — it needs to correlate pipeline artifacts (`WIP.md`, `VERIFICATION_REPORT.md`) with git commit timestamps and skill-genesis report disposition logs. The resolver and corpus schema need extensions to support multi-artifact join semantics.

**What's needed before v2.** A SPEC-to-pipeline-to-commit join capability in `CorpusReader`; a query interface for `SKILL_GENESIS_LOG.md`; possibly a small SQL or DataFrame layer for multi-artifact joins.

**Dependencies.** LEARNINGS-distillation prerequisite (see below); family 5 (token-budget surface stability) for the cost-side correlation.

### Family 4 — Onboarding outcome quality

**What it measures.** Checks that newly onboarded projects have all required artifacts in the expected state: `.ai-state/` skeleton complete, `CLAUDE.md` blocks present and byte-identical to canonical, merge drivers registered, git hooks installed, `DECISIONS_INDEX.md` present and non-empty.

**Why deferred.** This family operates on a different corpus shape — it reads a *target project's* repo, not Praxion's own `.ai-state/`. It is the primary motivation for the deferred `--project=<external>` flag (see [Open design questions](#open-design-questions)).

**What's needed before v2.** The `--project=<external>` corpus resolution mode; a project-structure snapshot schema distinct from the ADR/SPEC corpus.

**Dependencies.** `--project=<external>` design (see open questions).

### Family 5 — Token-budget surface stability

**What it measures.** Tracks the always-loaded surface size (CLAUDE.md files + always-on rules) across pipeline runs, comparing against the 25,000-token guardrail and flagging trends that approach the ceiling. Each report row carries the byte count and token estimate so the operator sees a time-series.

**Why deferred.** This is a pure mechanical check with no LLM call, but it requires a reliable `wc -c` + token-estimate calculation across the always-loaded surface — a collector, not a family in the current sense. The collector pattern does not yet have a home in the harness (the existing families run per-artifact; this family runs per-file-set).

**What's needed before v2.** A collector sub-protocol in the harness for non-artifact-per-item checks; a byte-to-token estimation utility; a v1 baseline to compare against.

**Dependencies.** None blocking; complexity is in the harness extension, not the check logic.

### Family 6 — Learning-loop closure latency

**What it measures.** Measures the lag between when a pipeline pattern first appears in a `LEARNINGS.md` and when it appears as a distilled artifact (skill addition, rule update, CLAUDE.md addition, memory entry). A long lag indicates the learning loop is not closing — patterns accumulate without being absorbed.

**Why deferred.** This family requires the LEARNINGS-distillation prerequisite (see below) to be operational before the latency can be measured. Without a normalized, per-feature `LEARNINGS_<spec>_YYYY-MM-DD.md` artifact at pipeline-end, the only available source is the ephemeral `.ai-work/<slug>/LEARNINGS.md` — which is gitignored and not available for historical analysis.

**What's needed before v2.** LEARNINGS-distillation step (see below); skill-genesis log parsing; a correlation between LEARNINGS entries and disposition timestamps in `SKILL_GENESIS_LOG.md`.

**Dependencies.** LEARNINGS-distillation prerequisite; family 3 (dogfooding fidelity) for the broader corpus.

## Prerequisites for deferred work

### LEARNINGS-distillation step

Per-feature LEARNINGS distillation is the single most load-bearing prerequisite for families 3 and 6. The current pipeline ends with an ephemeral `.ai-work/<slug>/LEARNINGS.md` that is gitignored and deleted after the pipeline. This means:

- No historical corpus of per-feature learnings exists for family-6 latency analysis.
- Family 3 dogfooding fidelity cannot correlate learnings with skill-genesis disposition timelines.

The prerequisite is a new pipeline step (modeled on `scripts/finalize_adrs.py`) that archives `LEARNINGS.md` alongside the SPEC at pipeline-end:

```
.ai-state/specs/LEARNINGS_<spec-slug>_YYYY-MM-DD.md
```

This step should run at the same time as SPEC archival (implementation-planner's end-of-feature action). The distilled artifact is committed to git, making it available for historical analysis. The `skill-genesis` agent's harvest corpus expands to include these distilled artifacts.

Until this step ships, families 3 and 6 remain blocked on an absent corpus.

### Family 2 real-corpus validation note

v1 ships with a single synthetic PASS-case fixture (`VERIFICATION_REPORT.md` in `.ai-work/head-milestone-verify/`). The first time `/eval-praxion` runs against a real commit that produced a `VERIFICATION_REPORT.md` with actual behavioral-contract tag violations, that run is effectively the first real-data integration sanity check for family 2's tag-scan and LLM-rubric paths.

The result of that first adversarial run should be treated as a calibration signal: if the judge's verdict disagrees with the human reviewer's assessment of the BC findings, the rubric or the tag-scan parser needs adjustment. This is expected at v1 — the PASS-only calibration gap is acknowledged, not a defect.

## `--project=<external>` design block

The deferred `--project=<external>` flag would allow `/eval-praxion` to evaluate another Praxion-managed project's `.ai-state/`. The use case is verifying that a downstream project's ADR corpus and pipeline artifacts meet quality standards from within the Praxion dev environment.

Three open questions remain before this can be designed:

**A. Report location.** Where does the report land?
- Option A: in the *target* project's `.ai-state/praxion_eval_reports/` — co-located with that project's own eval reports.
- Option B: in Praxion's `.ai-state/praxion_eval_reports/` with a `target=<project>` label in the filename.
- Option C: in the current working directory as a one-off report.

Option A is cleanest for long-term auditability (the project's history includes all eval reports against it), but requires write access to the target repo. Option B keeps Praxion's own audit trail in one place but conflates multiple projects' reports. Option C is simplest but ephemeral.

**B. Auth scope.** If the target project's `.ai-state/` is in another repo, the `CorpusReader`'s `git show` plumbing needs a repo-root override. The current design assumes Praxion's own root.

**C. Cross-project family applicability.** Not all families make sense for an external project. Family 1 (pipeline-outcome fidelity) is universally applicable. Family 2 (behavioral-contract adherence) is applicable if the target project uses Praxion's verifier. Families 3–6 are Praxion-internal.

Until these questions are resolved, `--project=<external>` is deferred. The current corpus reader accepts any valid `target` argument (path / worktree / git ref), which already allows evaluating a different branch or worktree of Praxion itself — the most common use case.

## Open design questions

1. **`--project=<external>` report location.** The three options above (A/B/C) each have different auditability tradeoffs. No consensus yet; needs a user decision before implementing.

2. **LEARNINGS-distillation step.** The archival schema (filename, frontmatter, distillation procedure) is not yet designed. It should be modeled on `finalize_adrs.py` but operates on ephemeral Markdown rather than structured YAML frontmatter.

3. **Family 5 collector sub-protocol.** The harness currently assumes families consume artifact-per-item corpora. A token-budget surface collector operates per-file-set. The extension point (a new `CollectorFamily` ABC alongside `Family`) needs to be designed before family 5 can be implemented without hacking the orchestrator.

4. **Cost caching.** At Haiku rates, 203 ADR option-depth calls cost ~$0.06–0.30 per full run. A SHA-keyed cache on `(adr_id, content_hash)` → `CheckResult` would eliminate repeat calls for unchanged ADRs. Not implemented in v1; the report header shows the per-run cost estimate so operators can decide when to add caching.

5. **Adversarial fixture corpus for family 2.** The v1 PASS-only corpus cannot validate the judge's false-negative detection. A future task should author several synthetic `VERIFICATION_REPORT.md` fixtures with known BC violation patterns and integrate them into the test corpus. This is the primary v2 calibration investment.
