---
id: dec-399
draft_id: dec-draft-30fe8cb6
title: The sentinel runs weekly in its own read-only, secret-scoped workflow; its outputs leave as a public artifact and a state patch, never a commit
status: accepted
category: architectural
date: 2026-09-26
summary: "A new .github/workflows/sentinel.yml (schedule + workflow_dispatch) runs praxion:sentinel via the audited claude-code-action pin with --plugin-dir ., as a main-thread --agent. It carries --max-turns 150 and an explicit sonnet model, and its tool grant equals agents/sentinel.md's. The job has contents:read, no id-token, and passes github_token, so the action cannot mint a write-capable Claude-App token. The OAuth secret appears on one step, with subprocess env scrub on. Plugin MCP servers are off via --strict-mcp-config. Side-effect and context hooks are silenced through --settings env, because project settings pin PRAXION_DISABLE_OBSERVABILITY=0. The agent writes normally; a post-step uploads the report plus an appliable state patch after a no-report failure check and a credential-pattern gate. audits.yml stays model-free and secret-free."
tags: [ci, github-actions, sentinel, scheduled-audits, security, claude-code-action, hooks, process-economy, p3-3]
made_by: agent
agent_type: systems-architect
branch: worktree-process-economy-p3-3-lane2
pipeline_tier: standard
affected_files:
  - .github/workflows/sentinel.yml
  - .github/workflows/audits.yml
  - tests/test_sentinel_workflow_invariants.py
affected_reqs: [REQ-01, REQ-02, REQ-03, REQ-04, REQ-05, REQ-06, REQ-07, REQ-08]
dissent: "The tool grant keeps unrestricted Bash, so a prompt injection that lands on main can still reach the OAuth token through /proc and the network. A narrowed allowlist would at least make that attack take more steps."
---

## Context

Process-economy P3.3 moves Praxion's audits onto a cadence.

- **Lane 1** (`audits.yml`) shipped model-free and secret-free.
- **Lane 2 is the sentinel.** It is the one audit that needs a model. Until now it ran only in interactive sessions, competing with them for context. `SENTINEL_LOG.md` shows gaps of up to 17 days.

The user ruled on 2026-09-26: GitHub Actions, weekly plus `workflow_dispatch`, the report delivered as an artifact and job summary, nothing committed back.

This creates the repo's first **scheduled** job that holds a model and a secret, which is a new component in the CI surface. Six facts, verified at the pinned action SHA and in the repo, shape the design:

1. **The action's default auth does not respect job permissions.** Without a `github_token` input, `claude-code-action@51ea8ea` exchanges OIDC for a Claude-App installation token. Its default grants are `contents: write, pull_requests: write, issues: write` (`src/github/token.ts`). The job's `permissions:` would not bound it.
2. **Project settings override the kill switch.** The committed `.claude/settings.json` sets `env.PRAXION_DISABLE_OBSERVABILITY: "0"`. The action loads user, project and local setting sources, and writes its own `settings` input at user tier, the lowest. A job-level kill switch would therefore be overridden.
3. **Plugin MCP servers run arbitrary code at startup.** `plugin.json` declares two: `task-chronograph` (`uv run`) and `likec4` (`npx -y @likec4/mcp`, a runtime npm fetch).
4. **The sentinel audits the WAL.** It reads `.ai-state/observations.jsonl` for P03/P04. If the plugin's capture hooks ran in CI, the sentinel would audit its own in-flight session.
5. **Outputs are public.** The repository is public, so artifacts can be downloaded by any signed-in GitHub user.
6. **Cost envelope.** Six measured interactive runs used 47–134 turns and took 7–21 min.

## Decision

**New file, one job.** `.github/workflows/sentinel.yml` (`name: Scheduled sentinel`) runs one job on `schedule: "0 7 * * 1"` (an hour after lane 1's metrics commit) and on `workflow_dispatch`.

**Permissions.**
- The workflow floor is `permissions: {}`.
- The job has exactly `contents: read`, with no `id-token`.
- Checkout pins `ref:` to the default branch and uses `persist-credentials: false` and `fetch-depth: 0`. In agent mode the pinned action still rewrites `remote.origin.url` with the job token, so the agent's Bash can read a `contents: read` token; checkout adds no second copy.
- No cache is saved after the agent runs: setup-uv has `enable-cache: false`, and Bun is installed by the workflow (`oven-sh/setup-bun`, the pin the action nests) with `no-cache: true` and passed as `path_to_bun_executable`. That skips the action's own setup-bun, whose post-step would save a cache under a key the write-scoped autofix workflows restore.

**The action step.** `anthropics/claude-code-action@51ea8ea…` (the autofix lockstep pin, td-057), with:
- `github_token: ${{ github.token }}`
- `claude_code_oauth_token: ${{ secrets.CLAUDE_CODE_OAUTH_TOKEN }}` — the secret's only reference
- env `CLAUDE_CODE_SUBPROCESS_ENV_SCRUB: "1"`
- `continue-on-error: true` and `timeout-minutes: 40`; the job has `timeout-minutes: 50`
- `claude_args`:
  - `--plugin-dir .`
  - `--agent praxion:sentinel`
  - `--model claude-sonnet-5`
  - `--max-turns 150`
  - `--strict-mcp-config`
  - `--settings '{"env":{…}}'` setting ten `PRAXION_DISABLE_*` switches to `"1"`: OBSERVABILITY, AUTO_COMPLETE, HOOK_CHAIN_HEAL, RULE_INJECTION, DECISION_INJECTION, PROCESS_INJECT, FEEDBACK_SURFACING, SIDECAR_BANNER, SIDECAR_AUTOCOMMIT, plus EVENT_POSTING (subsumed)
  - `--allowedTools "Read,Glob,Grep,Bash,Write"`
  - `--disallowedTools "Edit"`

This tool grant equals `agents/sentinel.md`'s.

**The agent's writes.** The agent runs its unchanged protocol, so its report, log row and ledger rows land in the runner checkout.

**Post-steps.** Inline YAML; step outputs reach scripts only through `env:`, never as shell source.
1. The job fails when no new `SENTINEL_REPORT_*.md` exists. New reports are found by diffing against a pre-agent snapshot of report names; the last new report is kept, since a second clock reading orphans the first. A non-`success` agent outcome raises a warning.
2. A credential-pattern gate (`sk-ant-…`, `gh[opsru]_…`) scans the report and the patch. It prints per-file counts, never the matching lines, and fails closed on a scan error.
3. The grade, Summary, Recommended Actions and the new log row go to `$GITHUB_STEP_SUMMARY`.
4. The report plus `sentinel-state.patch` (the log row and ledger rows as a diff) upload as `sentinel-report-<run_id>`, retained 30 days. The action's execution file is never uploaded.

Steps 1 and 2 run under `if: always()`. Steps 3 and 4 run only when the credential gate succeeded (`always() && steps.credential_gate.outcome == 'success'`), so a token-shaped string publishes nothing.

Adopting the patch (`git apply` + `check_state_ledgers.py --check`) is a maintainer act.

**`audits.yml`.** Only its "sentinel stays interactive" wording changes.

**Tests.** `tests/test_sentinel_workflow_invariants.py` asserts every clause above, with a mutation canary for each security invariant a single edit could silently break (triggers, permissions, the token, repeated or banned flags, the settings payload, publication gating, both caches, output passing, the checkout ref).

Activation: fired — stakes(security) + multiple plausible paths (placement, invocation mode, tool grant, ledger treatment); lens set = Security, Performance, Simplicity, Testability; convergence = stable, pending user acceptance.

## Considered Options

### Placement: a job inside `audits.yml` (rejected)

- **Pro:** `needs:` sequencing after the metrics commit.
- **Con:** `audits.yml` keeps a `contents: write` job, so "no write grant" and "secret present" become per-job properties rather than per-file ones. An LLM or quota flake would redden the deterministic audits. Dispatching metrics would spend a model run. It also breaks the brief's "audits.yml behaviour unchanged".
- The cron offset and the sentinel's TD06 freshness gate replace the lost sequencing.

### Invocation: a subagent spawned by a thin parent session (rejected)

- **Pro:** closest to how the sentinel runs interactively.
- **Con:** the subagent runs to its frontmatter `maxTurns: 300`, and the parent's `--max-turns` does not bound it. It also needs an `Agent` grant and fires the `Agent|Task` hooks.
- **Kept as fallback:** a prompt-driven "execute `agents/sentinel.md`", the `architecture.yml` shape.

### Tool grant: a narrowed Bash allowlist (rejected; the steelmanned runner-up, see Disconfirmation)

- **Pro:** the file itself shows fewer capabilities, and it adds defense in depth against casual misuse.
- **Con:** the sentinel's documented batching (`for …; do sed -n …; done`) and its drill-downs need general shell. `architecture.yml` records a too-narrow allowlist that burned every turn on denials and returned no verdict. With `Write` granted, every prefix rule is bypassable (`python3 scripts/../x.py`, GNU `sed '1e cmd'`, `find -exec`). The restriction would be nominal, while its turn cost would be real.

### Ledger rows: a prompt-level "report-only" mode (rejected)

- **Pro:** nothing is written that could be mistaken for a committed row.
- **Con:** it forks the agent's behaviour through the prompt, so CI would no longer run the repo's own definition. Rows would survive only as prose, and re-filing them would mean re-typing them. A patch keeps the exact row form and fails loudly (`git apply` conflict, or a `check_state_ledgers` collision) when `main` has moved.

### Kill-switch transport: job `env:` or the action's `settings` input (rejected)

- **Con:** both are overridden by the committed project `env.PRAXION_DISABLE_OBSERVABILITY: "0"`. The flag would read as set and not bite.
- `--settings` is the CLI-argument tier.

## Consequences

**Positive.**
- The sentinel audits `main` weekly without a session.
- The job cannot write to the repository: a `contents: read` token and no OIDC path. It cannot write through a cache either, since nothing it runs saves one.
- The secret has one reference, and subprocesses never see it in their environment.
- The plugin's MCP servers never start, so their runtime npm fetch never runs. The action's own install (`bun install`, the Claude Code installer) still runs inside the secret-bearing step.
- The CI run's context now matches the interactive subagent's: no SessionStart or UserPromptSubmit injection.
- The permission, token, flag, settings-payload, publication-gate and cache clauses are pinned by tests, each with a mutation canary. `--strict-mcp-config`, the env scrub and `--max-turns` are asserted present but have no canary.
- Lane 1 keeps its model-free, secret-free guarantee as a per-file property.

**Negative.**
- The committed `SENTINEL_LOG.md` does not advance on scheduled runs until a maintainer applies a patch. Trend comparisons and `audits.yml`'s age advisory see only committed rows.
- The run consumes the OAuth subscription quota: about $2.6–8.1 per run at assumed Sonnet list prices, with quota contention as the real cost.
- Unrestricted Bash leaves an accepted residual: an injection that lands on `main` can read `/proc/<ppid>/environ` and exfiltrate over the network. This is the same class the autofix workflows already accept, on less-trusted input.
- Post-agent steps run after an agent with unrestricted Bash, so their integrity is best-effort. They hold no secret.
- The pinned CLI (2.1.142) predates fixes to `--agent` and `--strict-mcp-config`. First-dispatch evidence must confirm both: R1 and R3 in SYSTEMS_PLAN.

## Disconfirmation

- **Falsifier:** the envelope is wrong if the first `workflow_dispatch` run shows any of these:
  - (a) an OIDC or App-token exchange in the action log instead of "Using provided GITHUB_TOKEN"
  - (b) `.ai-state/observations.jsonl` present after the run, meaning the `--settings` switches did not reach the hooks
  - (c) any MCP server listed in the session's init message
  - (d) a report that does not follow `agents/sentinel.md`'s structure, meaning `--agent` did not load the definition
  - (e) turn exhaustion before the Phase 1 report file exists
- **Steelmanned runner-up:** a narrowed Bash allowlist. Suppose every bypass is closable only by a determined attacker. Then narrowing still raises the cost of a *casual* injection ("run `env` and paste it") from one command to a crafted chain. And since P2's residual extraction moved Pass 1 into ~30 named scripts (`run_check_families.py --table` covers 29 families in one call), the sentinel may no longer need general shell to finish. If a measured CI run shows Pass 1 + Pass 2 completing within 150 turns under an enumerated grant, the runner-up wins: it is equal coverage for strictly less capability.
- **Reversal trigger:**
  - Switch to the enumerated grant if either holds: an enumerated-grant dispatch completes a non-`[PARTIAL]` report in ≤150 turns, or any credential-gate hit or suspicious tool call appears in a scheduled run.
  - Switch to the prompt-driven invocation fallback if (d) fires.
  - Move the kill switches to `--setting-sources user` if (b) fires.
