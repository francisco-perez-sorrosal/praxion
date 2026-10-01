# Footprint Criteria

A footprint is a measurable cost a change can move: always-loaded tokens, prompt size, suite time. A change that moves one carries a quantitative criterion in its spec, the plan measures it, and the verifier fails a missing or out-of-bound value. A criterion argued as "plausibly held" is not a measurement. Back to [SKILL.md](../SKILL.md).

## Where the rules live

This page is the workflow. It restates no grammar.

- Table grammars, the finding table (FP01-FP05) and the stages: the module docstring of `scripts/_footprint_grammar.py`. A test compares that docstring row by row with the code, so it cannot drift.
- The command, its exit codes and `--json`: the docstring of `scripts/check_footprint_criteria.py`.
- The registry of what counts as a footprint in a project is optional: `.ai-state/FOOTPRINTS.md`. Without it and without tables the check is inactive and costs nothing.

Run the check as `check_footprint_criteria.py <slug> --stage <stage> ...` (`python3 scripts/check_footprint_criteria.py` when self-hosting; managed projects get the script on `PATH`).

## Workflow by role

| Role | Does | Check |
|---|---|---|
| Systems architect | Reads the registry; for each footprint the change can move, writes a row in `### Footprint Criteria` (bounded, with a command) or in `### Footprints Not Measured` (with a real reason), both inside `## Acceptance Criteria` of `SYSTEMS_PLAN.md` | `--stage spec` |
| Acceptance designer | Routes every footprint row to `## Not Black-Box Testable` as "measurement step, then verifier". A test pinned to a dated baseline fails the next legitimate growth, and the suite's own elapsed time cannot be a test inside that suite | none |
| Implementation planner | Adds a baseline measurement step before the first production step that touches the footprint's paths (only for `baseline:` rows) and a final step after the last step whose `Files` match them. The step shape is in [document-templates.md](../../software-planning/references/document-templates.md). Reports an FP01 (a moved footprint the spec neither bounds nor declares) to the orchestrator as a Spec Question, and does not proceed past it silently | `--stage plan --paths <step files>` |
| Measurer (the measurement step's executor) | Runs each row's command and appends one row per criterion to `.ai-work/<slug>/MEASUREMENTS.md`, never editing an earlier row. Earlier steps are committed first, so `Head` names the measured tree | none |
| Verifier | Runs the check with `--stage verify --base-ref <pipeline base>`, then compares each recorded value to its limit, comparator and baseline. A missing or out-of-bound value is FAIL | `--stage verify` |

The check decides whether a measurement exists, is valid and is fresh. Whether a value is within its limit is the verifier's judgment; the instruments measure and never judge.

## Worked example

The two tables as the architect writes them, with placeholder footprints. A test parses this block through the shipped parser, so it stays correct.

```markdown
### Footprint Criteria

| Id | Footprint | Metric | Comparator | Limit | Against | Command |
|---|---|---|---|---|---|---|
| FC-01 | widget-size | largest widget, in lines | at or below | 400 lines | baseline: 380 lines | `python3 tools/count_widget_lines.py --json` |
| FC-02 | startup-cost | tokens loaded at startup | at or below | 12000 tokens | reference: the published budget | `python3 tools/startup_tokens.py --json` |

### Footprints Not Measured

| Footprint | Reason |
|---|---|
| render-time | the only instrument times a whole production deploy, which a change cannot run |
```

- `baseline:` obliges a baseline row in the log taken before the change; `reference:` does not (the limit is absolute).
- A footprint is either bounded or declared, never both. A declaration with a placeholder reason (`n/a`, `tbd`) counts as a missing criterion.
- Quote a table in a plan or a spec only inside a code fence; an unfenced table with these columns outside its own `###` heading is reported as misplaced.

## Reading a result

- A reading the instrument labels `estimate` is not `measured`. Baseline and final must carry the same kind, or the pair is `incomparable`; copy the instrument's own label into `Reading`.
- A breach whose diff touches none of the footprint's paths is still a FAIL; say so in the finding so the user can decide whether to re-baseline.
- The registry is how a footprint nobody wrote a row for is noticed (FP01, a warning naming the moved footprint and the paths). A warning is not a license to skip the row.
