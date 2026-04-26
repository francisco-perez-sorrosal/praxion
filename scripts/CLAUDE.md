# Scripts

Utility and operational scripts for the Praxion ecosystem.

## Available Scripts

- `praxion-claude-dev` — Launch Claude Code with the Praxion working tree as the plugin source (wraps `claude --plugin-dir`). Passes `--dangerously-skip-permissions` by default; set `PRAXION_DEV_SAFE=1` to keep prompts. See [Session-scoped local testing](../README_DEV.md#session-scoped-local-testing)
- `ccwt` — Claude Code Worktrees: opens a tmux session with one pane per git worktree, each running Claude Code
- `chronograph-ctl` — Development helper for the Task Chronograph MCP server (start/stop/restart/status/logs from source)
- `phoenix-ctl` — Manage the Phoenix observability daemon (install/start/stop/restart/status/uninstall via launchd)
- `reconcile_ai_state.py` — Post-merge reconciliation for `.ai-state/` artifacts: semantic memory.json merge, observations.jsonl dedup, ADR renumbering, index regeneration. Called by `/merge-worktree`
- `regenerate_adr_index.py` — Regenerate `.ai-state/decisions/DECISIONS_INDEX.md` from ADR file frontmatter
- `finalize_adrs.py` — Promote fragment ADRs under `.ai-state/decisions/drafts/` to stable `<NNN>-<slug>.md`, rewrite `dec-draft-<hash>` cross-references across sibling ADRs / `.ai-work/*/LEARNINGS.md` / `SYSTEMS_PLAN.md` / `IMPLEMENTATION_PLAN.md`, regenerate the index. Idempotent; advisory file lock. Invoked by post-merge hook and `/merge-worktree`
- `finalize_tech_debt_ledger.py` — Collapse duplicate rows in `.ai-state/TECH_DEBT_LEDGER.md` by `dedup_key`. Status precedence on collapse is `resolved > in-flight > open > wontfix`; tie-break by newer `last-seen`; non-conflicting fields merged (earliest `first-seen`; notes concatenated with ` // `; locations union-sorted). Idempotent; advisory file lock; fail-loud on malformed rows (exit 1). Invoked by post-merge hook after `finalize_adrs.py`. See `rules/swe/agent-intermediate-documents.md` § `TECH_DEBT_LEDGER.md`
- `check_squash_safety.py` — Post-merge diagnostic: detect `.ai-state/` entry erasure from squash-merges and emit a recovery warning. Non-blocking (exit 0). Invoked by post-merge hook after finalize
- `check_id_citation_discipline.py` — Inbound id-citation discipline check: scans committed code files for ephemeral identifier citations that must not appear in source. Wired into `hooks/commit_gate.sh` on `git commit`. Parallel to the outbound `check_shipped_artifact_isolation.py`. See `rules/swe/id-citation-discipline.md`
- `check_shipped_artifact_isolation.py` — Outbound shipped-artifact isolation check: scans shipped artifact surfaces for references to specific pipeline/state entries. Wired into `hooks/commit_gate.sh`. See `rules/swe/shipped-artifact-isolation.md`
- `migrate_worktree_home.sh` — Print copy-paste-ready `git worktree move` commands to migrate legacy `.trees/<name>/` worktrees to `.claude/worktrees/<name>/`. Performs no automatic move

## Conventions

- Shell scripts (bash), `set -euo pipefail` (except `ccwt` which uses `set -eo pipefail`)
- Each script is self-contained with usage documentation in header comments
- `chronograph-ctl` and `phoenix-ctl` are development/operations tools — in production, MCP servers run via plugin.json

## Installer Filter

`install_claude.sh` links scripts under `~/.local/bin/` only when they are `-f && -x` AND do not match `merge_driver_*` or `git-*-hook.sh`. User-facing tools must be executable (`chmod +x`); merge drivers and git hooks are invoked by git, not by PATH, so they are intentionally skipped. Orphaned symlinks (from renamed/removed scripts) are cleaned on upgrade by `clean_stale_symlinks`. See dec-042.

## Wired into Onboarding

The `/onboard-project` command installs several of these scripts as git hooks and merge drivers in user projects. When changing any of them, verify the onboarding flow's expectations still hold:

- `git-post-merge-hook.sh` — symlinked into `.git/hooks/post-merge` by `/onboard-project` Phase 4 (universally useful — chains reconcile → finalize → tech-debt-dedup → squash-safety)
- `git-pre-commit-hook.sh` — Praxion-author-only (shipped-artifact isolation). User projects get a *tailored* inline hook script written by Phase 4 that runs only `check_id_citation_discipline.py` — Praxion's shipped-artifact concern doesn't apply downstream
- `merge_driver_memory.py`, `merge_driver_observations.py` — registered via `git config merge.<name>.driver` by `/onboard-project` Phase 3 (alongside the `.gitattributes` entries)
- `check_id_citation_discipline.py` — invoked by the user-project pre-commit hook installed in Phase 4
- `finalize_adrs.py`, `finalize_tech_debt_ledger.py`, `reconcile_ai_state.py`, `check_squash_safety.py` — invoked by the post-merge hook chain

Path or interface changes to these scripts must update `/onboard-project` Phase 3 (`git config` driver line) and Phase 4 (inline pre-commit hook body) to match.
