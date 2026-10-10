# Tier-Prompt Scaffolds

Parametric scaffolds for the main agent to construct **delegation prompts** at Standard, Full, and Lightweight tiers. The scaffolds are a **shell**; per-agent deliverables live in the authoritative [Delegation Checklists](coordination-details.md#delegation-checklists). The main agent substitutes placeholders and pastes the checklist payload — no content is duplicated here.

**Placeholder convention:** angle-bracket tokens (inherited from `[Phase: <Name>]` in [SKILL.md](../SKILL.md)). The main agent substitutes each token before sending the prompt; subagents never see angle-bracket forms.

## Placeholder Reference

| Placeholder | Substitution site | Example |
|---|---|---|
| `<task-slug>` | Every prompt (path scoping) | `auth-flow` |
| `<tier>` | Prompt preamble | `Standard`, `Full` |
| `<phase-name>` | Phase-delegated steps | `Refactoring` |
| `<step-n>` | implementer/test-engineer prompts | `3` |
| `<deliverable>` | `produce <deliverable>` clauses | `SYSTEMS_PLAN.md` |
| `<input-artifact>` | `read <input-artifact>` clauses | `RESEARCH_FINDINGS.md` |
| `<parallel-peer-agent>` | Full-tier parallel blocks | `test-engineer` |
| `<instance-k>` | Multi-instance fan-out (1-indexed) | `2` |
| `<instance-total>` | Multi-instance fan-out total count | `3` |
| `<variant-label>` | Speculative-execution variant name | `sync-architecture` |
| `<alternative>` | Speculative-execution topic | `data-flow architecture` |

## Standard-Tier Sequential Scaffold

Use when the pipeline flows one agent at a time (e.g., architect → planner).

```markdown
You are the <agent-role> for the `<task-slug>` pipeline (tier: <tier>).

Task slug: <task-slug>
Phase: <phase-name>
Input: .ai-work/<task-slug>/<input-artifact>
Deliverable: .ai-work/<task-slug>/<deliverable>

<!-- Paste the per-agent checklist from coordination-details.md#delegation-checklists -->

Report back: path of <deliverable>, acceptance-criteria pass/fail table, open questions.
```

Example (architect → planner): `<task-slug>` = `payment-api`, `<tier>` = `Standard`, `<input-artifact>` = `SYSTEMS_PLAN.md`, `<deliverable>` = `IMPLEMENTATION_PLAN.md`.

## Full-Tier Parallel Scaffold (implementer ∥ test-engineer)

Use when the planner assigns an optional paired step (risky logic, property or contract tests) with disjoint file sets. Spawn the test-engineer first and the implementer once its RED is confirmed (never in the same tool-use block); each receives the same slug but distinct step numbers and fragment files.

```markdown
You are the <agent-role> for the `<task-slug>` pipeline (tier: Full).

Task slug: <task-slug>
Step: <step-n>
Parallel peer: <parallel-peer-agent> (disjoint file set)
Input: .ai-work/<task-slug>/WIP.md (your step only)
Deliverable: <deliverable> + .ai-work/<task-slug>/WIP_<agent-role>.md fragment

<!-- Paste the per-agent checklist from coordination-details.md#delegation-checklists -->

Do NOT edit files outside your declared Files set; report [CONFLICT] if you must.
```

## Lightweight Snippet

Lightweight delegates at most one agent (researcher). No scratch file; acceptance criteria inline.

```markdown
You are the researcher for a Lightweight task.

Goal: <one-sentence question>
Scope: <files or APIs in bounds>
Done when: <inline acceptance criterion>

<!-- Paste the researcher checklist from coordination-details.md#delegation-checklists -->

Return findings in your response (no file); cite paths.
```

### Lightweight tier specifics

- **Criteria-first, in one line** — at Direct and Lightweight tiers there is no `WIP.md` / `SYSTEMS_PLAN.md` acceptance-criteria / `traceability.yml` machinery (those only run at Standard/Full). The stand-in: *before touching code*, state in one line what "done" looks like as a testable assertion — *"`parse_config` returns a `Config` for valid YAML and raises `ConfigError` naming the offending key for invalid"*, not "make it work". For multi-step work, list the steps with a `→ verify: <check>` per step. Same verify-before-done discipline, no ceremony.
- **No `TEST_RESULTS.md`** (except a Ralph-lite goal run) — Lightweight test runs use whatever test command the project defines; the canonical handoff artifact is created only when work escalates to Standard.
- **Temporal-only acceptance tests** — the Standard/Full acceptance-design stage ([`coordination-details.md § Acceptance-Design Stage`](coordination-details.md#acceptance-design-stage)) does not run at Lightweight: no stage, no `ACCEPTANCE_TESTS.md`. What survives is the ordering. Before any code, the orchestrator writes failing tests from the `TASK_BRIEF.md` Key Signals and commits them alone, with a subject that says `temporal-only`. Test-first order holds; independence from the design does not, since the orchestrator has already seen the code's neighbourhood — the subject line records that honestly.
- **Architecture-doc update on structural change** — Lightweight respects the same `.ai-state/DESIGN.md` / `docs/architecture.md` update expectation as Standard when the change is structural; trivial-bug Lightweight work does not trigger doc edits.
- **Mid-task escalation, not silent scope-creep** — when scope grows past 3 files or starts requiring architect/planner input, stop and re-scope to Standard rather than expanding silently. Escalation is a controlled transition; the new tier inherits the work-in-progress and the calibration log records both the original tier and the escalation.

## Ralph-lite

Ralph-lite is the step-loop driver's goal mode: an execution mode inside Lightweight, not a tier, for one well-gated single-behaviour task that a pytest command checks. Enter it through `/praxion:ralph-lite <slug> --goal <sentence> --check <command> --expects <expectations> --paths <path>...` in one of two forms: terminal (a person runs `step_loop.py run <slug>` from a scratch worktree) or in-session (the goal plan driven through `/praxion:step-loop <slug>`).

- **Fresh context**: every iteration is a new headless worker with a fresh context; its state lives in the goal plan, the progress record, the ledger and git.
- **The gate decides, never the worker's claim**: the driver runs the derived test scope and the goal's check after each iteration.
- **One committer**: the worker never commits; the driver commits each progressing iteration by pathspec.
- **Bounds**: the `Iterations:` budget bounds the loop; each iteration has a turn bound and a dollar fuse; two non-progressing iterations in a row stop it.
- **Exits to a person**: a `[BLOCKED]` return, the "impossible" verdict or a stall stops the loop with a handoff.
- **Documents**: a goal run writes a plan, a `WIP.md` and a `TEST_RESULTS.md` for its one step, although the task is Lightweight-sized; the calibration row's Source cell names Ralph-lite.
- **Not for** Standard and Full step loops, which run through the `/praxion:step-loop` relay, or goals no pytest command can check.

The goal's check, one statement per line:

- The goal's test module exists before `goal` runs, and an empty module is enough: pytest prints no summary for a missing path, and the scaffold refuses a check it cannot read.
- The check names the project's own test runner: `uv run pytest` where the project runs pytest through uv, never a bare interpreter that may lack pytest.
- The expectation encodes the whole goal: a goal check's `fail=0` is always met, because the goal's own failing tests read `pending`.
- `pending=0` makes the goal's own failing tests part of completion.
- A goal whose tests the loop writes must count every test it asks for in the pass count.
- The goal's oracle goes to `--protect`: the target tests of a make-green goal, the module under test of a test-writing goal.

Safety profile, unattended:

- Run from a scratch worktree.
- The worker runs under `dontAsk` with the check and the `resolve_test_scope.py` resolver allow-listed; `acceptEdits` alone denies the test command, so never use it alone.
- Never use `bypassPermissions` outside a container.
- Deny rules on the protected paths hold in every permission mode.
- Each iteration is bounded by a turn bound and a dollar fuse, and the loop by the `Iterations:` budget.
- The worker may edit only the goal's paths and its progress record, and holds no pre-approval but the check and the resolver.
- `run` refuses before any worker when a settings file pre-approves a tool-wide `Bash` rule, an edit rule, or a `Bash` rule that is a prefix of the check or of the resolver, in either spelling (`X:*` or `X *`).
- `run` denies the worker every other inherited `Bash` pre-approval, and the pre-approval of any tool it is not granted.
- Code the check runs is not fenced by permission rules, so read the kept commits before the scratch branch is merged.
- Nothing removes the deny rules but the person: they stay in that checkout's `.claude/settings.local.json` until the person deletes them when the goal is done, and in a scratch worktree they go with the worktree.
- **Fallback**: the harness's `/goal` command is the fallback for a repository without Praxion; it keeps one context for the whole run and judges printed output, not the check's result.

## Full-Tier Multi-Instance Fan-Out

Use when one agent role decomposes into N independent instances over disjoint file sets (e.g., three implementer instances for three independent modules in the same step group). All instances run concurrently in a single turn; coordinator merges fragment files after completion.

```markdown
You are the <agent-role> for the `<task-slug>` pipeline (tier: Full).

Task slug: <task-slug>
Instance: <instance-k> of <instance-total>
Step: <step-n>
Files (disjoint from other instances): <files>
Peers: instances <other-k> of <instance-total> operating on different file sets
Input: .ai-work/<task-slug>/WIP.md (your step only)
Deliverable: <deliverable> + .ai-work/<task-slug>/WIP_<agent-role>_<instance-k>.md fragment

<!-- Paste the per-agent checklist from coordination-details.md#delegation-checklists -->

Do NOT edit files outside your declared Files set; report [CONFLICT] if you must. Coordinator merges all <instance-total> fragment files into the canonical WIP.md after every instance completes.
```

Key distinction from the implementer ∥ test-engineer scaffold: there the parallel agents have **different roles** on the same step; here N instances of the **same role** operate on disjoint file sets within one step.

## Full-Tier Speculative Execution

Use when two or more instances of the same role explore **alternative approaches** in parallel and the coordinator synthesizes or selects from the outcomes. Reserved for decision points where the comparison itself is load-bearing — not routine work.

```markdown
You are the <agent-role> for the `<task-slug>` pipeline exploring alternative <alternative>.

Task slug: <task-slug>
Variant: <variant-label>
Peer variants: <other-variant-labels>
Deliverable: .ai-work/<task-slug>/<deliverable>__<variant-label>.md

<!-- Paste the per-agent checklist from coordination-details.md#delegation-checklists -->

Report: trade-offs in your approach, strong/weak points, explicit selection criteria you'd propose. Do NOT declare a winner — the coordinator compares variants and decides. Do NOT read peers' variant files; independent reasoning is the point of speculative execution.
```

Coordinator responsibility: after all variants complete, compare the per-variant deliverables and either select one (recording the rationale in an ADR) or synthesize a third approach that absorbs the best of each. Speculative execution is expensive (N × tokens) — justify with a note in the pipeline's SYSTEMS_PLAN.md.

## DRY Boundary

This reference defines **prompt structure only**, except the Ralph-lite section, which describes an execution mode. Every `<!-- Paste ... -->` marker points the main agent at [coordination-details.md § Delegation Checklists](coordination-details.md#delegation-checklists) as the single source of truth for per-agent deliverables. Copying the checklists here would duplicate them across two files — coordination-details is authoritative. Add new placeholders here only when a new delegation pattern emerges; add new deliverables to coordination-details, not here.
