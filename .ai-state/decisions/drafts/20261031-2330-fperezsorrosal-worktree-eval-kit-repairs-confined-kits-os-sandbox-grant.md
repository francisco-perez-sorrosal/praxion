---
id: dec-draft-4999dfd9
title: Confine the implementer and verifier kits' shell with the harness's OS sandbox
status: proposed
category: architectural
date: 2026-10-31
summary: The adherence eval's implementer and verifier sessions get Claude Code's own Bash sandbox, delivered as --settings JSON (required, no unconfined retry, auto-approved inside, copy write-denied, real home read-denied except the runner's interpreter, credentials unset), instead of narrow allow patterns; the first such session that shows the sandbox inactive or a prescribed command refused stops the run.
tags: [eval, adherence, permissions, sandbox, security, td-544]
made_by: agent
agent_type: systems-architect
branch: worktree-eval-kit-repairs
pipeline_tier: standard
affected_files:
  - eval/src/praxion_evals/adherence/confinement.py
  - eval/src/praxion_evals/adherence/tasks.py
  - eval/src/praxion_evals/adherence/cli.py
  - eval/src/praxion_evals/adherence/session_loop.py
  - eval/src/praxion_evals/live/session.py
  - eval/src/praxion_evals/adherence/fixtures/repos/ledger-cli/pyproject.toml.tmpl
  - eval/src/praxion_evals/adherence/fixtures/repos/notes-service/pyproject.toml.tmpl
---

## Context

Every adherence kit narrowed its shell grant to a read-only set (`READ_ONLY_BASH`): git status/diff/log/show, plus `ls`, `cat`, `head`, `tail`, `wc` and `grep`. In implementer run 20261031T194025Z-257479, every one of the 48 sessions was denied its test run. As a result C2, the 5-line return check and the `TEST_RESULTS.md` shape check bound nothing. In verifier run 20261031T203813Z-47ce6d, 30 of the 48 returns report a denied Bash. The principle over `READ_ONLY_BASH` is that a broad grant is unrestricted execution under another name, because nothing at the OS level confines a session.

A $0 spike on materialized task sandboxes found three more problems. The fixtures' tests do not collect under plain `python -m pytest` (src layout with no `pythonpath`). Bare-name Praxion scripts resolve to the operator's real `~/.local/bin`. And `rework_manifest.compute_row_id` can only be reached through `python3 -c`.

This decision is architectural because it adds a component (the confinement builder) and moves the trust boundary of a measured session from command-text matching to OS enforcement.

## Decision

The implementer and verifier kits ("confined kits") launch with Claude Code's Bash sandbox, passed as a `--settings` JSON string in the session's argv. The keys below are checked against code.claude.com/docs/en/sandboxing.md and settings-reference.md as of 2026-10-31:

- `sandbox.enabled: true`
- `sandbox.failIfUnavailable: true`
- `sandbox.allowUnsandboxedCommands: false`
- `sandbox.autoAllowBashIfSandboxed: true`
- `sandbox.filesystem.denyWrite: [<copy root>]`
- `sandbox.filesystem.denyRead: [<real home>]`
- `sandbox.filesystem.allowRead`: the runner's `sys.prefix` and `sys.base_prefix`, the copy root and the run root, each in its given and realpath spelling
- `sandbox.credentials.files`: `mode: "deny"` entries for the session token file and the operator's credential locations, by absolute real-home path, since `~` resolves to the sandbox home
- `sandbox.credentials.envVars`: `mode: "deny"` for `CLAUDE_CODE_OAUTH_TOKEN`, `ANTHROPIC_API_KEY` and `ANTHROPIC_AUTH_TOKEN`. These are unset before each sandboxed command, while the session process and its hooks keep them.
- No `network.allowedDomains`.

`READ_ONLY_BASH` stays in `--allowedTools`. Every other kit is unchanged.

Three enabling repairs ship with the sandbox:

1. The copy's `scripts/` directory is first on the session PATH, ahead of the runner's bin and the ambient PATH.
2. Both fixtures declare `[tool.pytest.ini_options] pythonpath = ["src"]`.
3. Each session record names the shell commands the harness refused.

A session of a confined kit that shows the sandbox inactive or a prescribed command refused is recorded as `confinement_broken`. That kind is not a counting kind and is never retried, and the run stops after that session. This is a separate stop condition, not an `infra_stop.StopRule`, whose count of at least 3 exists for transient channel failures.

## Considered Options

1. **Narrow per-role allow patterns** (`Bash(python -m pytest *)`, each script by path). Rejected. pytest runs code the role just wrote, so the pattern narrows nothing that runs. Patterns also miss the forms the definitions prescribe: absolute paths into a per-run copy, `python3 -c`, env-prefixed runs and `git -C`.
2. **Harness OS sandbox** (chosen).
3. **No grant, score the vacuous checks not applicable on a denied run.** Rejected. The kernel trials would then measure none of the shell protocol.
4. **`CLAUDE_CODE_SUBPROCESS_ENV_SCRUB=1` for credentials.** Rejected. It also strips the hooks' environment and `CLAUDE_CONFIG_DIR`, which is the layer under test. `credentials.envVars` deny touches only sandboxed Bash.
5. **Sandbox settings in the sandbox's user `settings.json`.** Rejected in favour of `--settings`. The flag is a trusted scope for credentials keys, and its JSON is in the argv the dry run already prints, so REQ-17 needs no materialization.

## Consequences

- Positive: the prescribed shell work runs in every form. Writes outside the fixture, temp and added dirs are refused by the OS, and the copy is write-denied. The real home and credentials are unreadable from the shell, which also closes today's `cat *` read of the real home for these kits. The first paired run verifies its own grant.
- Negative: `git add` and `git commit` now work inside the fixture, so C4 can see a real commit. Hooks, the Read tool and WebFetch stay outside the sandbox. Print mode silently ignores invalid settings, so only the first paid session (REQ-16) proves enforcement. The grant depends on the eval venv's `dev` group providing pytest, ruff and pyright.
- Activation: no. The design-synthesis gate did not fire. One-way-door stakes are absent: the change is reversible by removing `--settings`, and recorded runs are untouched.

## Disconfirmation

- **Falsifier.** The component added is `eval/src/praxion_evals/adherence/confinement.py`, the confinement builder. The responsibility that moves is keeping a measured session's shell inside its sandbox: it moves from `tasks.allowed_tools` (command-text patterns) to the harness's OS sandbox. If, once this lands, the confined kits still depend on `READ_ONLY_BASH` patterns for safety, the decision did not take effect.
- **Steelmanned runner-up.** Narrow patterns plus the sandbox with auto-allow off, so every command is both pattern-approved and OS-confined. This is defence in depth, and each approval is explicit and reviewable in the argv. It loses because the verifier run's denials were form failures (absolute copy paths, `python3 -c`, env prefixes, `git -C`), and each new form would need a new pattern. It becomes the right choice if auto-allow turns out not to approve under print mode.
- **Reversal trigger.** The first paired run stops `confinement_broken` because a prescribed command was refused while the sandbox was active, which means auto-allow did not approve it under `--permission-prompts none`. Switch to the runner-up. If a sandboxed command ever writes outside the sandbox, as seen in the post-session copy digest or a write outside the run root, withdraw the grant entirely.
