# Hackathon Submission — Praxion Self-Improving `code-review` Skill

> **Tagline:** Do not just fix the PR. Teach the agent to fix the next one.

## Team

- **Team name:** Praxion
- **Participants:** Francisco Perez-Sorrosal
- **Skill name:** `code-review` (live Praxion skill, self-improved)

## Skill

- **Skill path:** `hackathon/SKILL_DEMO.md` (deliberately sparse demo skill — Praxion's live `skills/code-review/SKILL.md` is intentionally not modified)
- **Final `SKILL.md` summary:** Structured PR review methodology with PASS/FAIL/WARN finding classification. The self-improvement loop adds a `## Gotchas` bullet on Python mutable-default arguments after Round 1 reveals the gap.

## Runs

### Baseline Run (Round 1, PR-A)

- **Task or PR:** Review PR-A — adds `def append_event(payload, history=[])` (Python mutable list default)
- **Score:** _populated by demo.py from `artifacts/timeline.json`_
- **Main failure mode:** _populated from `artifacts/skill_runs.jsonl` — error_type field_
- **`SkillRunEntry.run_id`:** `praxion:r1:code-review`
- **Log path:** `hackathon/artifacts/daytona_round1.log`

### Improved Run (Round 2, PR-B)

- **Task or PR:** Review PR-B — adds `def cache_lookup(key, seen=set())` (Python mutable set default; same defect class)
- **Score:** _populated by demo.py from `artifacts/timeline.json`_
- **Improvement over baseline:** _delta from Round 1 score_
- **`SkillRunEntry.run_id`:** `praxion:r2:code-review`
- **Log path:** `hackathon/artifacts/daytona_round2.log`

## Feedback Loop

What feedback did Cognee record?

```text
error_type:     <populated from artifacts/skill_runs.jsonl Round 1>
error_message:  <populated from artifacts/skill_runs.jsonl Round 1>
feedback:       <populated from artifacts/skill_runs.jsonl Round 1>
success_score:  <populated from artifacts/skill_runs.jsonl Round 1>
```

What changed in the skill because of that feedback?

```diff
<populated by demo.py — diff between artifacts/SKILL_v1.md.bak and current hackathon/SKILL_DEMO.md>
```

## PR Rescue Result

- **Bug or regression found:** Mutable default argument in `cache_lookup(key, seen=set())` — the default `set()` is shared across all calls, causing silent state leakage between invocations.
- **Fix proposed:** See `hackathon/artifacts/proposed_fix.patch` — replaces the mutable default with `seen: set | None = None` and an `if seen is None: seen = set()` guard inside the function body.
- **Tests run or specified:** See `hackathon/artifacts/missing_test.py` — pytest case that fails on the original code (state leaks between calls) and passes on the patched version.
- **Remaining risk:** None for the demo defect class. Other defect classes (broad except, bare assert) are documented as extension points but not exercised in this run.

## Agent Team

Three roles, each a plain Python harness on disk (mapped to the Praxion pipeline narrative):

```text
Reviewer  (run_review.py, runs in Daytona sandbox)  — Round 1 + Round 2
                                                       Calls Anthropic via messages.parse(FindingsOutput)

Editor    (rewrite_skill.py, on host between rounds) — Reads Round 1 SkillRunEntry,
                                                       prompts LLM for one Gotcha bullet,
                                                       runs 4-condition is_safe_rewrite gate,
                                                       writes new SKILL.md

Fixer     (fix.py, on host after Round 2 catches)    — Produces proposed_fix.patch + missing_test.py
```

## Reproduction

Commands needed to reproduce:

```bash
git clone <this-repo>
cd hackathon-self-improving-skill
cp hackathon/.env.example hackathon/.env
# Edit hackathon/.env to add ANTHROPIC_API_KEY, DAYTONA_API_KEY, DAYTONA_API_URL
./hackathon/run_dashboard.sh
# Click "Run Round 1" then "Run Round 2" in the browser at http://localhost:8501
```

Environment assumptions:

```text
DAYTONA_API_KEY            (required — sandbox lifecycle)
DAYTONA_API_URL            (required — Daytona server)
ANTHROPIC_API_KEY          (required — LLM calls)
COGNEE_SKIP_CONNECTION_TEST=true  (required — bypass Cognee's first-run LLM probe)
MOSS_PROJECT_ID            (not used)
MOSS_PROJECT_KEY           (not used)
```

## Architecture Reference

Full design rationale: [`COGNEE_HACKATHON_USE_CASE.md`](../COGNEE_HACKATHON_USE_CASE.md)

ADRs (committed under `.ai-state/decisions/drafts/`):

- `cognee-skip-cognify-chunks-only` — single-provider Anthropic, skip `cognify()`
- `sandbox-custom-image-strategy` — pre-built Daytona image with `anthropic` baked in
- `structured-output-messages-parse` — Pydantic-typed output at all 3 LLM call sites
- `inline-sanity-check-replaces-critic` — 4-condition `is_safe_rewrite` gate
- `code-review-gotcha-mutable-default-arguments` — the live skill change itself
