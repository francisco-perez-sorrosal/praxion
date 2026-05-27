---
description: Run out-of-band quality evaluation against Praxion pipeline artifacts (mechanical + LLM-as-judge). Opt-in, never hook-driven.
argument-hint: "[<target>] [--task-slug <slug>] [--tier lightweight|standard|full] [--mechanical-only] [--output-dir <dir>]"
allowed-tools: [Bash(uv:*), Bash(git:*), Bash(python3:*)]
disable-model-invocation: true
---

Single user-invoked entrypoint for the `eval/` harness package. Runs two quality-check families against a resolved corpus of pipeline artifacts and emits a Markdown report. This command is opt-in; eval code never runs from hooks, never during a pipeline. The invocation contract is out-of-band by design — LLM-as-judge calls cost real tokens and must remain operator-triggered, never woven into automation.

**Invariant**: if any hook or agent script references `praxion_evals.harness.*`, flag it as a bug.

## Argument Resolver

`TARGET` resolves in this order (first match wins):

| Case | Input | Resolution |
|------|-------|-----------|
| 1 | _(none)_ | `main` branch HEAD SHA via `git rev-parse main` |
| 2 | Existing filesystem path | Reads artifacts from the path directly |
| 3 | Known worktree name | Expands to `.claude/worktrees/<name>/` on the filesystem |
| 4 | Valid git ref | Reads artifacts via `git show <ref>:<file>` plumbing |
| error | Anything else | Non-zero exit with a three-part message: what was tried, what failed, what to try |

When the target is a worktree (case 3) or filesystem path (case 2), the corpus is read from that root — including any in-flight `.ai-work/<slug>/` if `--task-slug` is supplied. For git-ref targets, `.ai-work/` is gitignored, so any `--task-slug` manifest scan falls back to the working tree.

## Modes and Flags

| Flag | Effect |
|------|--------|
| `--task-slug <slug>` | Additionally verdict the in-flight `.ai-work/<slug>/` artifact manifest under Family 1. Without it, only post-merge `.ai-state/` checks run. |
| `--tier lightweight\|standard\|full` | Pipeline tier governing the expected manifest (only consulted when `--task-slug` is set). Defaults to `standard`. |
| `--mechanical-only` | Skip every LLM-judged check across all families. Runs without auth env vars — the cheap, fast structural surface alone (artifact manifest, ADR frontmatter, supersession reciprocity, BC tag scans). |
| `--output-dir <dir>` | Override the report destination. Default: `<repo-root>/.ai-state/praxion_eval_reports/`. |

## Auth Detection

Auth route is implicit — no flag needed (and not required at all when `--mechanical-only` is set):

| Env var set | Route |
|-------------|-------|
| `CLAUDE_CODE_OAUTH_TOKEN` | Agent SDK route (`claude-agent-sdk`) |
| `ANTHROPIC_API_KEY` | Direct Messages API route (`anthropic` SDK) |
| Neither (and not `--mechanical-only`) | Non-zero exit with a one-line message naming both env vars |

The CLI calls `dotenv.load_dotenv(find_dotenv(usecwd=True))` before reading these vars, so the token may live in a `.env` at the project root (or any ancestor of the invocation cwd) instead of being re-exported per shell. Real environment variables take precedence over `.env` values — `export` always wins.

## Families

| Family | Checks |
|--------|--------|
| **Family 1 — Pipeline-outcome fidelity** | In-flight artifact-manifest scan (when `--task-slug` set); ADR frontmatter completeness; body-section presence; supersession reciprocity; re-affirmation reciprocity; spec traceability-matrix presence; `affected_reqs` resolvability (WARN); DECISIONS_INDEX consistency (WARN); option-depth substantiveness (LLM, skipped with `--mechanical-only`) |
| **Family 2 — Behavioral-contract adherence** | Reads `VERIFICATION_REPORT.md` files; extracts `### Behavioral Contract Findings`; mechanical scans for the six BC violation tags; LLM-judges the four behaviors (surface assumptions, register objection, stay surgical, simplicity first) — LLM rubrics skipped with `--mechanical-only` |

Each check emits PASS / WARN / FAIL / SKIP. The report's `## Calibration Notes` section records known corpus gaps.

## Report Destination

- Report file: `.ai-state/praxion_eval_reports/PRAXION_EVAL_REPORT_<ISO-timestamp>.md`
- Append-only log row: `.ai-state/praxion_eval_reports/PRAXION_EVAL_LOG.md`
- Log columns (frozen): `Timestamp / Target / Auth route / Families / Pass / Warn / Fail / Cost (USD) / Report`

## Process

### 1. Resolve target

```bash
cd /path/to/repo && uv run --project eval praxion-evals --help
```

Verify the CLI is invocable and shows the target argument and flags.

### 2. Run the eval

```bash
cd /path/to/repo && uv run --project eval praxion-evals [TARGET] \
    [--task-slug SLUG] [--tier TIER] [--mechanical-only] [--output-dir DIR]
```

Omit `--output-dir` to land the report under `<repo-root>/.ai-state/praxion_eval_reports/` (the resolved default — `<repo-root>` is the invocation cwd). Pass `--output-dir` only to override that destination.

### 3. Surface the report

Print the path to the generated report file and the summary line:

```
Eval complete: <N> PASS / <N> WARN / <N> FAIL
Report: .ai-state/praxion_eval_reports/PRAXION_EVAL_REPORT_<timestamp>.md
```

### 4. Flag anomalies

If any check emits FAIL, surface the check name, the artifact path, and the verdict reason. The user decides whether to act on the finding or defer it.

## Examples

```bash
# Default: eval main HEAD, both families, LLM judging on.
/eval-praxion

# Eval a known worktree by name (preserves the project's branch in-place).
/eval-praxion praxion-self-eval-v1

# Eval a specific git SHA, post-merge corpus only.
/eval-praxion abc1234

# Eval an arbitrary filesystem path; override the report destination.
/eval-praxion /path/to/checkout --output-dir /tmp/reports

# Add the in-flight artifact-manifest check for a live pipeline.
/eval-praxion --task-slug phase3-quality-automation --tier standard

# Fast structural-only run — no LLM calls, no auth required.
/eval-praxion --mechanical-only

# Combine: cheap manifest + ADR-structure pass over an in-flight pipeline.
/eval-praxion --task-slug phase3-quality-automation --mechanical-only
```

## Notes

- LLM judge calls cost real API credits (or subscription quota). The report header shows estimated cost per run. Use `--mechanical-only` to bound cost to zero when only the structural surface matters.
- The PASS-only family-2 corpus available at v1 limits calibration for false-negative detection; the `## Calibration Notes` section in every report records this gap explicitly.
- This command is the single eval entrypoint. The retired `/eval` Tier 1 surface has been folded into Family 1's mechanical artifact-manifest check — invoke via `--task-slug <slug>` to reproduce the old behavior; combine with `--mechanical-only` to keep it free.
