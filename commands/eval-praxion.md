---
description: Run out-of-band LLM-as-judge quality evaluation against Praxion pipeline artifacts. Opt-in, never hook-driven.
argument-hint: "[<target>] [--output-dir <dir>]"
allowed-tools: [Bash(uv:*), Bash(git:*), Bash(python3:*)]
disable-model-invocation: true
---

User-invoked entrypoint for the `eval/` harness package. Runs two quality-check families against a resolved corpus of pipeline artifacts and emits a Markdown report. This command is opt-in; eval code never runs from hooks, never during a pipeline. The invocation contract is out-of-band by design — LLM-as-judge calls cost real tokens and must remain operator-triggered, never woven into automation.

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

## Auth Detection

Auth route is implicit — no flag needed:

| Env var set | Route |
|-------------|-------|
| `CLAUDE_CODE_OAUTH_TOKEN` | Agent SDK route (`claude-agent-sdk`) |
| `ANTHROPIC_API_KEY` | Direct Messages API route (`anthropic` SDK) |
| Neither | Non-zero exit with a one-line message naming both env vars |

The CLI calls `dotenv.load_dotenv(find_dotenv(usecwd=True))` before reading these vars, so the token may live in a `.env` at the project root (or any ancestor of the invocation cwd) instead of being re-exported per shell. Real environment variables take precedence over `.env` values — `export` always wins.

## Families

| Family | Checks |
|--------|--------|
| **Family 1 — Pipeline-outcome fidelity** | ADR frontmatter completeness, body-section presence, supersession reciprocity, re-affirmation reciprocity, spec traceability-matrix presence, `affected_reqs` resolvability (WARN), DECISIONS_INDEX consistency (WARN), option-depth substantiveness (LLM) |
| **Family 2 — Behavioral-contract adherence** | Reads `VERIFICATION_REPORT.md` files; extracts `### Behavioral Contract Findings`; LLM-judges presence and quality of the four behaviors (surface assumptions, register objection, stay surgical, simplicity first) |

Each check emits PASS / WARN / FAIL. The report's `## Calibration Notes` section records known corpus gaps.

## Report Destination

- Report file: `.ai-state/praxion_eval_reports/PRAXION_EVAL_REPORT_<ISO-timestamp>.md`
- Append-only log row: `.ai-state/praxion_eval_reports/PRAXION_EVAL_LOG.md`
- Log columns (frozen): `Timestamp / Target / Auth route / Families / Pass / Warn / Fail / Cost (USD) / Report`

## Process

### 1. Resolve target

```bash
cd /path/to/repo && uv run --project eval python -m praxion_evals.harness.cli --help
```

Verify the CLI is invocable and shows the target argument.

### 2. Run the eval

```bash
cd /path/to/repo && uv run --project eval python -m praxion_evals.harness.cli [TARGET] [--output-dir DIR]
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
/eval-praxion                                              # eval main HEAD (default)
/eval-praxion praxion-self-eval-v1                        # eval a known worktree by name
/eval-praxion abc1234                                      # eval a specific git SHA
/eval-praxion /path/to/checkout --output-dir /tmp/reports  # eval a filesystem path
```

## Notes

- LLM judge calls cost real API credits (or subscription quota). The report header shows estimated cost per run.
- The PASS-only family-2 corpus available at v1 limits calibration for false-negative detection; the `## Calibration Notes` section in every report records this gap explicitly.
- `/eval` (the original command) runs the Tier 1 behavioral eval (artifact-manifest check). `/eval-praxion` runs the Tier 2 LLM-as-judge harness. Both are out-of-band; use `/eval` for fast artifact-presence checks and `/eval-praxion` for semantic quality assessment.
