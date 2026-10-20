---
diataxis: how-to
audience: developer
---

# Switch a role to its kernel

Recipes for the lean-spawn mechanism: regenerate the kernels, put a role on trial, measure it with the adherence instrument (stop, continue or close a run, read its allowance lines, index its results), flip it or hold it, move the eligibility pin, read a `kernel_injected` row and run the liveness check. For what each part is and why, see [Lean spawn: role kernels and the adoption ledger](lean-spawn-kernels.md).

Run commands from the repository root.

> [!IMPORTANT]
> The amended flip rule (allowances sized by each run's own discordance, the coverage statement, the C5 binding, continuation and the earlier-runs scope; draft decision `dec-462`) was ratified by the user on 2026-10-19. No paid run, push or release belongs to the pipeline that built it: each paid run needs the user's go and stated caps. Nothing here claims that a lean spawn does better work; every recipe describes behaviour and the command or file that shows it.

## Regenerate the kernels after a rule or agent change

```bash
python3 scripts/generate_kernels.py          # write claude/kernels/, the agent blocks and the preamble
python3 scripts/generate_kernels.py --check  # write nothing; exit 1 when anything on disk is stale
python3 scripts/check_kernel_manifest.py     # the commit gate: manifest, kernels, ledger
```

A new section in an always-loaded source needs an entry in `rules/_audience.yaml`; the checker names the unclassified section. Never edit the generated files under `claude/kernels/` (only the authored texts under `claude/kernels/src/`) or the three universal blocks inside an agent definition by hand: the next regeneration overwrites them.

## Put a role on trial

1. Pick a role from `ELIGIBLE_ROLES` in `scripts/kernel_eligibility.py` (six roles: `researcher`, `verifier`, `discipline-consultant`, `skill-genesis`, `context-engineer`, `implementer`). The ledger holds no list of its own; see [Move the eligibility pin](#move-the-eligibility-pin).
2. Add a record under `roles:`, in the block layout the hook reads line by line:

   ```yaml
   roles:
     researcher:
       status: trial
       since: 2026-10-14T09:00:00Z
       runs: []
   ```

   Use the current instant for `since`: spawns before it are not judged. Keep this layout (two-space role, four-space unquoted `status`): the gate refuses a record the hook would read differently (`I10-hook-misread`).
3. Commit through the gate. From this commit the hook delivers the role's kernel at every spawn, followed by the project's root `CLAUDE.md`, in which only a line that is wholly `@<relative path>` is expanded, one level deep, resolved from the project root and never inside fenced code (close every fence: one left open inside a list item stays open here to the end of the file, where the harness closes it with the item); an inline `@path` and deeper imports stay as written. The definition is unchanged, so the role also still inherits the project instructions.
4. Spawn the role once and confirm its row (below).

## Run the sessions on a subscription

A paired run launches dozens of headless sessions, and each bills whatever credential it finds. To bill a Claude subscription instead of API credits, make a long-lived token in your own terminal with `claude setup-token`, save it to a file only you can read (for example `~/.claude/praxion-session-token`, mode 600) and name that file on the run:

```bash
praxion-evals-adherence --role verifier --arm full --arm lean --required-pairs 20 --judge-golden \
  --session-oauth-token-file ~/.claude/praxion-session-token --max-total-usd 200
```

Every session then carries the token as `CLAUDE_CODE_OAUTH_TOKEN` and no API key; the runner's own process keeps the key for the judge, which runs on the Messages API and costs cents. A dry run shows the effect in each session's `env_names`. The cost figures a subscription session reports are Claude Code's estimates, not charges, so the run cap bounds an estimate; note that in the run's ledger comment. A subscription has usage windows: if a run is throttled mid-way its remaining sessions error out and the run is listed like any other, so run one role at a time and leave headroom.

> [!WARNING]
> While a paid run writes into this checkout, every gated commit is refused with `I9-run-index-stale`. The runner checkpoints its results file into `.ai-state/eval_ledger/adherence/` after every session and writes the run index only when the run ends, so the gate sees a results file the index does not list. Run the eval with `--output` pointing outside the checkout, or commit nothing until the run ends. Never run `--reindex` on an in-flight file: it indexes a partial run, or an index that names a file git does not hold, which a fresh clone then reports as listed but gone.

The same session route serves the startup probe. `python3 scripts/measure_startup_payload.py agent:researcher --strict-mcp-config --plugin-dir . --json --session-oauth-token-file ~/.claude/praxion-session-token` starts every probe session with the file's token in `CLAUDE_CODE_OAUTH_TOKEN` as its only credential and no `ANTHROPIC_API_KEY` or `ANTHROPIC_AUTH_TOKEN`. It refuses before any session when the file is missing, unreadable or blank, and it never prints or records the token (it is redacted from stderr tails and errors). The reading's profile names `credential: subscription`, so it compares only with a reading taken the same way; a reading taken without the option keeps its old profile. Verify: `python3 -m pytest scripts/test_measure_startup_payload.py -q` and `uv run pytest tests/acceptance/test_startup_probe_bills_the_subscription.py -q`.

## Let a run stop itself on an infrastructure failure

A run stops launching when one arm of one role has failed `N` sessions in a row with the same infrastructure error and the same evidence. The rule is declared in the results file before the first launch, so a stop cannot be tuned after the outcomes are known.

| Option | Meaning |
|---|---|
| `--stop-count N` | Sessions in a row that stop the run. Default 3; below 3 is refused before any launch, so one task's session and its retry can never stop a run |
| `--tail-chars N` | The end of an errored session's stderr and result text kept as its evidence, per stream. Default 2000 |

- **What counts.** Only these error kinds: `timeout`, `exit_nonzero`, `no_result_event`, `envelope_unparseable`, `result_error`, `kernel_missing`. A graded failure, an isolation breach, a refused launch, an evaluation exception, a session stopped by its own budget and any session that ran each end the streak. A behavioural outcome never counts.
- **Masking rule (`v1`).** Two tails are the same when they match after UUIDs, ISO-8601 timestamps, `req_` request ids, `<n>ms` durations, `<n> bytes` counts and hexadecimal ids of 8 or more characters are replaced by fixed placeholders. A request id that differs between two otherwise identical errors does not hide a streak, and two different errors of one kind do not merge.
- **What stops.** Nothing more is launched (no session, no retry, no judge call); every recorded session is kept; the results file ends `infra_stopped` and the run exits 1. The report prints `The run stopped itself: ...` with `continuable` or `not continuable`, and each errored session's `error tail:` and `result tail:` lines. Credentials are redacted before the tail is cut, so none reaches a results file or report.

Verify: `uv run pytest tests/acceptance/test_run_stops_on_repeated_infrastructure_failure.py tests/acceptance/test_errored_session_keeps_its_evidence.py -q`; `uv run praxion-evals-adherence --help` from `eval/` lists both options.

## Continue or close a stopped run

A stopped run is continued or closed; it is never left beside a fresh draw. The reason is statistical: an operator free to restart after seeing interim counts would inflate the rate of clear verdicts.

1. Read the stop line in the report. A run is **continuable** only when its stop touched both arms of the role (the other arm failed alike inside the streak's window) or the spend cap refused launches. A stop in one arm alone, an interrupt, a finished run, a run recorded before endings existed and a run something already continues are not continuable.
2. To continue: `uv run praxion-evals-adherence .. --continue <run id>` from `eval/`, with at most `--max-total-usd`, `--session-budget-usd`, `--keep-sandbox`, `--session-oauth-token-file` and `--output` beside it (a spend limit it does not name is the one the stopped run recorded). An option that would change a declaration is refused, naming it. The part's `--output` must not name any file of its lineage, and `--overwrite` is refused.
3. The continuation is refused before any launch, naming every reason, unless it measures the same thing under the same declarations: the resolved model, seed, planned task list, launch order and every declared setting match, and no file of the tree changed outside `.ai-state/eval_ledger/adherence/` and the `.ai-state/observations*.jsonl` logs (the adoption ledger and every definition count). A committed results file changes nothing, so committing between the stop and the continuation is allowed; committing anything else is not.
4. What relaunches: the sessions inside the stopping streak, and launches the spend cap refused, count as never launched, and their tasks run again whole in every arm in seed order. Every other recorded session keeps its outcome, and a pair that errored on the lean side alone stays a lean failure under the worst-case recount, so no counted pair is redrawn.
5. The lineage is one run: one verdict over the counted pairs under the first part's declarations, and a report that names every part with its id, start, harness version, sessions, spend and the stop that ended it.
6. To give up instead: `uv run praxion-evals-adherence .. --close <run id> --reason "<why>"`. A close without a reason is a usage error. The closed run is listed as a not-clear draw carrying its interim per-check result, and a closed run does not by itself refuse a later switched record.

A fresh run of a role is refused, before anything launches and naming the run, while a continuable stopped run of that role is neither continued nor closed. The check is keyed on the role alone, whatever the other options say; a one-arm stop does not block a fresh run.

Verify: `uv run pytest tests/acceptance/test_stopped_run_is_continued_or_closed.py tests/e2e/test_continued_run_counts_as_one.py -q`.

## Read a run's allowances and coverage

Every new run declares the allowance method `own-discordance-exact` before its first launch. A mechanical check regresses when `fails_lean - fails_full` exceeds its allowance, the exact one-sided quantile, at the declared confidence, of the net discordance at that check's own count of discordant pairs `d` (zero at `d = 0`, the count itself up to 4, then for example 3 at 5, 6 at 10, 8 at 20). Each role and check has its own allowance. No calibration file is an allowance source: `--calibration-run FILE` is accepted for old command lines and writes one stderr line saying it sets none, and `--calibration` is a diagnostic of the slot order that sizes nothing.

The two arms of each task launch in an order drawn from the run's seed for that task, recorded with the task and kept by a continuation. `--dry-run` prints each task's arms in that order, and the same seed gives the same order.

The report states, inside each mechanical check's block, the discordance and the allowance in pairs and in percentage points beside the declared margin. The coverage statement follows from it:

- A check whose allowance exceeds the margin times its usable pairs is listed as **not covered** at the margin, with a `not covered by the flip verdict (...)` line, and is named in the flip claim. It is stated, not hidden: a check with few discordant pairs cannot show a regression of any size.
- **C5 binds only a role the harness stopped at its turn cap.** The record carries the role's own turn count and cap, read from its transcript. A role that ended before its cap is not applicable on C5 and is scored on C2; a session whose cap cannot be established is withheld on C5 with the reason. Results recorded before this binding are never re-scored.
- **C5 coverage floor.** When fewer than five pairs ran out of turns on both sides, C5 is listed as not covered with that reason. The report also counts, per role and arm, forced-stop sessions that ran out of turns and that ended before their cap, and the differential run-out rate; none enters a verdict.

Verify: `uv run pytest tests/acceptance/test_forced_stop_and_allowance_scoring.py -q`; `cd eval && uv run pytest tests/test_adherence_verdict.py -q`; render a results file with `uv run praxion-evals-adherence --report <file>`.

## List the earlier runs of a role

The report lists every earlier run of the same role measured on the same **role definition and kernel identity**, whatever the checkout's commit, as draws in order with their flip verdicts. Runs of another identity are named apart with how they differ; calibration runs are listed apart; a continued lineage appears once; a closed run appears as a not-clear draw; a run recorded before identities existed is listed by the identity its commit held, or as identity unknown, and never dropped. A JSON file beside the output that is not an adherence results file is skipped and named, in the run's output and in the report (`Skipped, not adherence results files, beside this run's: ...`).

Verify: `uv run pytest tests/acceptance/test_runs_are_listed_and_launched_by_what_they_measure.py -q`.

## Index the results and let the gate resolve a cited run

The commit gate does not import the eval. It reads `.ai-state/eval_ledger/adherence/index.json`, which has one writer, the adherence runner: it writes the index when a run ends and when `--close` runs, and rebuilds it with `--reindex`:

```bash
cd eval && uv run praxion-evals-adherence .. --reindex   # rebuild from the results files alone; launches nothing
```

Each entry holds a results file's name and sha256, its lineage root and ending, and per role the complete pairs and flip label (lineage-level for a continued run, `not clear` for a closed one). JSON files that are not results files are named apart. Commit the regenerated `index.json` with the results files it lists; `--reindex` over a clean tree leaves it byte-identical.

For every `switched` record, new or unchanged, the gate resolves each run the record cites, `passing_run` included, through the index to its lineage and refuses, naming the role and run: `I9-run-missing` (no readable results file), `I9-run-wrong-role`, `I9-run-pairs-differ` (complete pairs differ from the record), `I9-run-flag-disagrees` (the record's pass flag disagrees with the verdict) and `I9-run-passing-short` (the passing run has fewer than 20 complete pairs or a verdict other than clear). Citing any part of a lineage resolves to the whole lineage; citing two parts counts one run. `I9-run-index-stale` is a digest that no longer matches, a listed file that is gone, or a results file the index does not list. An unreadable index is an input error (exit 2). The `kernel-manifest` pre-commit hook runs for the index, the results files and `scripts/kernel_run_index.py`.

Verify: `python3 -m pytest scripts/test_kernel_run_index.py -q`; `cd eval && uv run pytest tests/test_adherence_run_index.py -q`; `uv run pytest tests/acceptance/test_switched_records_rest_on_their_results.py -q`; `python3 scripts/check_kernel_manifest.py` over the committed ledger.

## Move the eligibility pin

The roles that may be switched are the literal `ELIGIBLE_ROLES` in `scripts/kernel_eligibility.py`: the five pilot roles and the `implementer`. The pin lives there, not in the adoption ledger, because a flip commit writes the ledger and the definitions and must not be able to widen the list it is judged against.

1. Edit only the tuple, in a commit of its own.
2. The gate refuses a commit that changes the pin together with any adoption record or any definition's `omitClaudeMd` (`I9-eligible-with-move`, naming both). It judges a move to `switched` against the pin as it stood at the parent commit, so a role becomes switchable from the commit after (`I9-eligible-not-yet`). A ledger that carries an `eligible` key is refused (`I9-eligible-in-ledger`).
3. The `implementer` is eligible and has no record in `.ai-state/kernel_adoption.yaml`: it receives nothing at spawn and still inherits the project instructions. Its trial record, and the one spawn that shows a `kernel_injected` row judged clean by `--liveness`, land with its run in the run-preparation commit after the merge, with the user's go. The eval holds no project-convention fixture for the implementer yet, and the run index keeps pairs and a flip label, not which checks were scored (tracked as `td-468`); read an implementer run's report for the checks it scored before citing it.

Verify: `uv run pytest tests/acceptance/test_flag_eligibility_and_liveness_gates.py -q`; `python3 -c "import sys; sys.path.insert(0, 'scripts'); import kernel_eligibility as k; print(k.ELIGIBLE_ROLES)"`.

## Record a run

After each adherence run, append it to the role's `runs` with its `id`, `complete_pairs`, `passes_flip_rule` and `entry`. A run that does not pass stays recorded and the role stays at `trial`. The list only grows: the gate refuses a commit that drops, reorders or rewrites a recorded run (`I9-ledger-runs-rewritten`).

## Flip a role to `switched`

Flip only on a run of at least 20 complete pairs that passes the flip rule, with the startup probe read before and after for the role's first request, and with the user's ratification in hand. The amended flip rule was ratified on 2026-10-19; a report states the rule it was scored under. A flip is also a commit of its own: it may not change the eligibility pin.

1. Take both readings with the same profile:

   ```bash
   python3 scripts/measure_startup_payload.py agent:researcher --strict-mcp-config --plugin-dir . --json
   ```

2. In one commit, change the ledger record and the definition together. The record:

   ```yaml
   researcher:
     status: switched
     since: 2026-10-14T09:00:00Z
     runs: [{id: <run id>, complete_pairs: 20, passes_flip_rule: true, entry: <entry>}]
     passing_run: <run id>
     probe_before_tokens: <reading>
     probe_after_tokens: <reading>
     flip_rule_ratified: true
     flip_ratified: true
   ```

   The definition: add `omitClaudeMd: true` to the frontmatter of `agents/researcher.md` and change nothing else.
3. The gate refuses the commit when the flag has no `switched` record, when a `switched` record has no flag, when an evidence field is missing or a ratification is not `true`, when the move is not one the ledger allows (`switched` is reached only from `trial`), when the role is not in the pin as it stood at the parent commit, or when a cited run does not resolve to its results as [Index the results](#index-the-results-and-let-the-gate-resolve-a-cited-run) describes. The flag is accepted only as the literal `omitClaudeMd: true`; any other value (`false`, `yes`, a quoted `true`, `1`, empty) is `I9-flag-not-literal-true`. An unreadable ledger at the parent commit is an input error (exit 2), never read as no ledger. Fix the reported finding; no switch turns the gate off.

State a reading with its profile (model, setting sources, MCP mode, plugin directory). Readings compare only within one profile.

## Hold a role

Hold a role when its trial closes without a flip: its run failed the flip rule, or no run can reach 20 complete pairs. A held role receives nothing at spawn, keeps inheriting the project instructions and is not judged by `--liveness`, so it costs what it cost before the trial.

1. In one commit, change only the record's `status` and add a `reason` naming why the trial closed. Keep `since` (the closed trial's start) and every run, in order:

   ```yaml
   verifier:
     status: held
     since: 2026-10-14T02:32:49Z
     runs:
       - id: <run id>
         complete_pairs: 24
         passes_flip_rule: false
         entry: praxion-evals-adherence
     reason: the flip rule did not pass on the forced-stop check
   ```

   A role with no run may be held with `runs: []`. Quote a reason that contains `: `, or YAML cannot read the ledger and the gate stops with an input error. The definition is unchanged: a held role never carries `omitClaudeMd`.
2. The gate refuses a held record with no `reason` (`I9-record-incomplete`), a run added while the role stays held (`I9-ledger-held-run-added`), a move to `held` from anything but `trial`, and any move from `held` but back to `trial` (`I9-ledger-transition`).

To re-open a held role, set `status: trial` with a new `since`, keep every run and drop the `reason`. The `since` is the re-opened trial's own start: the gate refuses a re-opening with no `since` (`I9-ledger-reopen-no-since`), one at or before the commit it follows, the held record's old start included (`I9-ledger-reopen-before-parent`), and one later than the re-opening commit itself (`I9-ledger-reopen-after-commit`). Use the current instant. The liveness check judges a re-opened trial from the commit that re-opened it, so a spawn made while the role was held is never reported, whatever `since` the record carries; a plugin root without git history cannot place a re-opening, so its adopted roles are judged from their recorded start and named as unplaced in the report. Record the next run only after the re-open commit.

## Read a `kernel_injected` row

Each delivering spawn leaves one row in the project's observation log. Find the latest:

```bash
grep '"event_type":"kernel_injected"' .ai-state/observations.jsonl | tail -n 3
```

| Field | Meaning |
|---|---|
| `role`, `agent_type`, `agent_id`, `session_id` | which spawn received the kernel |
| `kernel_version` | the full version of the kernel text delivered |
| `strings` | one entry per string delivered, in slot order: `module` (a module label, or `project-claude-md`), `part` (the project-file part number, else `null`) and `chars` (UTF-16 units, the unit of the harness cap) |
| `project_file` | `{chars, parts, omitted}` for the project's `CLAUDE.md`, or `null` when none was delivered; a non-zero `omitted` means the role was told to read the file for the rest |

A spawn that received nothing leaves no row.

## Read the transcript marker

The first line of every injected string is `[praxion <8 hex> #<slot>]`. The hex is the first eight characters of `kernel_version`; the slot is the string's place. A role owed N strings shows markers `#1` to `#N` in its context, each once, in any order. Use the marker where no observation log exists, as in a sandboxed eval session.

The marker is recorded in the role's own transcript, `<config dir>/projects/<cwd, every / and . as ->/<session id>/subagents/agent-<agent id>.jsonl`, never in the parent session's `stream-json`. Look for the `attachment` record of type `hook_additional_context` with `hookEvent` `SubagentStart`: its `content` lists every delivered string. Each hook command also leaves a `hook_success` record whose `stdout` holds that hook's JSON output.

## Run the liveness check

```bash
python3 scripts/check_kernel_manifest.py --liveness
python3 scripts/check_kernel_manifest.py --liveness --since <rev> --json
```

It reads the observation log under the repository root and the plugin's ledger, then judges each spawn of a role at `trial` or `switched`. A spawn counts from its role's `since` (and from the commit time of `--since`, when given) and is an agent's first `agent_start`; a resume is never judged. A spawn with no `kernel_injected` row for its agent id is a `liveness-missing-row` finding: the hook did not run for it. `--plugin-root DIR` names the plugin checkout whose ledger lists the adopted roles.

The report states how many spawns of how many adopted roles it judged, so a clean report over zero spawns reads as such. A log it cannot find or read whole is an input error (exit 2), never a pass. A log segment inside the judged window that is missing or unreadable makes the reading unknown, not clean: the report names each such segment (`liveness-unknown-segment`), still lists the findings from the segments it did read, and exits 2; a segment wholly before the window changes nothing. Exit 0 clean, 1 findings, 2 unknown or unreadable input. Verify: `uv run pytest tests/acceptance/test_flag_eligibility_and_liveness_gates.py -q`.

## When the hook is absent

Agents keep working. Every definition still carries the three universal blocks, the Codex wrappers embed the kernel, and the Cursor rules export is unchanged. A role at `trial` or `switched` whose spawns leave no row is what `--liveness` exists to catch.
