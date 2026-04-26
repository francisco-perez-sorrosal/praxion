# Hackathon Skill Loop — Self-Improving `code-review` Skill

## What This Is

A two-round demo that teaches an AI agent to improve at its own job by learning from its
mistakes. Round 1 uses Praxion's `code-review` skill to review a Python PR — the agent misses
a planted mutable-default-argument bug. That failure is recorded in Cognee. The skill's
`## Gotchas` section is automatically rewritten with the missing rule. Round 2 presents an
isomorphic bug in a different file — and the improved skill catches it. The entire loop runs
inside a Streamlit dashboard that streams live output, shows the skill diff, and displays the
Cognee memory table as it grows from one row to two. Sandboxed execution on Daytona provides
a log-backed, replayable trace.

---

## Architecture at a Glance

Six Python files, each with a single responsibility:

| File | Role |
|------|------|
| `demo.py` | Host orchestrator — drives Daytona, Cognee, scoring, and skill rewrite (~140 lines) |
| `run_review.py` | Reviewer — runs *inside* the Daytona sandbox; calls Anthropic, writes `findings.json` |
| `rewrite_skill.py` | Editor — queries Cognee for `missed_bug` entries, patches `SKILL.md` on the host |
| `fix.py` | Fixer — Round 2 only; generates `proposed_fix.patch` and `missing_test.py` |
| `score.py` | Deterministic scorer — compares `findings.json` against `ground_truth.json` |
| `dashboard.py` | Streamlit 4-panel dashboard — one command, no JS, no templates |

Supporting pieces: `models.py` (Pydantic schemas shared by all scripts), `fixtures/` (PR
patches and ground-truth JSON), `tests/` (unit + integration tests).

---

## Quickstart

**Prerequisites**: Python 3.12+, a Daytona account (`https://app.daytona.io`), an Anthropic
API key.

```bash
# 1. Copy the environment template and fill in your keys
cp hackathon/.env.example hackathon/.env
#    Edit hackathon/.env: set ANTHROPIC_API_KEY, DAYTONA_API_KEY, DAYTONA_API_URL

# 2. Run the one-command launcher (from repo root)
./hackathon/run_dashboard.sh
#    This installs deps, pre-warms the Daytona sandbox, then starts Streamlit at localhost:8501

# 3. In the browser:
#    - Click "Run Round 1" — the agent misses the mutable-default bug; skill is rewritten
#    - Click "Run Round 2" — the improved skill catches the isomorphic bug
```

> If the warm step times out (> 60 s), `run_dashboard.sh` exits with a clear error message
> rather than launching a slow dashboard. Check `DAYTONA_API_KEY` and `DAYTONA_API_URL` in
> `hackathon/.env`.

---

## What You Will See

Four panels update live as each round runs:

| Panel | What it shows |
|-------|---------------|
| **Timeline** | Emoji step list — `⚠ missed → ◆ recorded → ✓ approved → ✓ caught → 🔧 fixed` |
| **SKILL.md Diff** | `difflib.unified_diff` output rendered as `st.code(language="diff")`; green `+` lines show the Gotcha bullet appended after Round 1 |
| **Cognee Records** | `st.dataframe` — grows from one row (`success_score=0.0`, `error_type=missed_bug`) to two (`success_score=1.0`, `error_type=`) after Round 2 |
| **Live Log** | `subprocess.Popen` stdout streamed line-by-line; capped at 200 lines; clears between rounds |

Success: Round 1 row shows `success_score=0.0` and the diff shows two new lines; Round 2 row
shows `success_score=1.0` and `artifacts/proposed_fix.patch` + `artifacts/missing_test.py` exist.

---

## The Before/After Skill Diff

The improvement surface is the `## Gotchas` section of
[`hackathon/SKILL_DEMO.md`](SKILL_DEMO.md) — a deliberately-sparse demo skill, NOT the live
Praxion `skills/code-review/SKILL.md`. The demo skill starts with one Gotcha bullet and gets
its second one appended by the Editor between rounds — visible as a multi-line diff in Panel 2:

```diff
  ## Gotchas

  - **Structural findings belong to refactoring**: ...
+
+ - **Mutable default arguments**: In Python, `def f(x=[])` and `def f(x=set())`
+   share the default object across all calls — a silent state mutation bug. ...
```

The change is ADR-backed (`dec-draft-90086b99`). `hackathon/artifacts/` is gitignored, so
only the skill file itself lands in git. A four-condition safety check (`is_safe_rewrite`)
gates the write: frontmatter unchanged, section count unchanged, body grew by less than 400
chars, no fenced Python block longer than 8 lines.

> TODO(S10.1): Add a screenshot of the two-line diff as rendered in Panel 2 once Round 1 has
> been run against real credentials.

---

## Replay

The demo is infinitely replayable. `demo.py` backup-restore protocol: first Round 1 saves
`SKILL.md` → `artifacts/SKILL_v1.md.bak`; every subsequent Round 1 restores from the backup
before re-running. No manual cleanup required.

To reset completely:

```bash
rm -rf hackathon/artifacts/ && mkdir hackathon/artifacts/ && ./hackathon/run_dashboard.sh
```

---

## Sentinel Note

The demo operates on `hackathon/SKILL_DEMO.md`, not on Praxion's live
`skills/code-review/SKILL.md`. This isolates the loop's mutations to a hackathon-scoped
artifact so sentinel does not flag the rewrite as an unanchored change to a real skill.
`hackathon/artifacts/` is gitignored — runtime artifacts (logs, findings, patches, backup)
never land in git.

---

## Links

### Internal — design and implementation

- **Full design doc**: [`../COGNEE_HACKATHON_USE_CASE.md`](../COGNEE_HACKATHON_USE_CASE.md)
- **Implementation plan**: [`.ai-work/hackathon-skill-loop/IMPLEMENTATION_PLAN.md`](../.ai-work/hackathon-skill-loop/IMPLEMENTATION_PLAN.md)
- **ADR drafts**: [`.ai-state/decisions/drafts/`](../.ai-state/decisions/drafts/)

### External — hackathon and partner references

- [Cognee · Daytona · MOSS Hackathon repo](https://github.com/topoteretes/cognee-daytona-moss-hackathon) — challenge spec, submission template, starter PR rescue skill
- [Self-Improving Skills (Cognee deck)](https://github.com/topoteretes/cognee-daytona-moss-hackathon/blob/main/self-improving-skills-cognee.pptx.pdf) — hackathon presentation slides
- [Cognee homepage](https://www.cognee.ai/) — knowledge-graph memory for AI agents
- [Cognee on GitHub](https://github.com/topoteretes/cognee) — `cognee` Python SDK source
- [Daytona sandbox snapshots dashboard](https://app.daytona.io/dashboard/snapshots) — manage running sandboxes (use the cleanup script if quota is hit)

> TODO(S10.1): Add Daytona run IDs, before/after scores, and log file paths once the smoke
> run in Phase 9 completes.
