# Commands

Reusable slash commands for AI coding assistants. Each `.md` file becomes a `/command-name` invocable during interactive sessions where the assistant supports slash commands. **Tool-agnostic:** compatible with Claude Code (plugin), Cursor (exported as plain Markdown by `./install.sh cursor`), and Codex (exposed as `praxion-command-<name>` skill wrappers by `./install.sh codex`).

## Available Commands

| Command | Description |
|---------|-------------|
| `/add-rules` | Copy rules into the current project for customization |
| `/clean-auto-memory` | Enumerate orphan Claude Code auto-memory directories for removed worktrees and help the user delete them |
| `/clean-work` | Safely clean `.ai-work/` after pipeline completion — state-aware (blocks on live/unarchived state), with `--dry-run` |
| `/co` | Create a commit for staged (or all) changes |
| `/consult` | Convene a discipline consultant to adversarially challenge a target artifact |
| `/cop` | Create a commit and push to remote |
| `/create-simple-python-prj` | Create a basic Python project with pixi or uv |
| `/create-worktree` | Create a new git worktree in `.claude/worktrees/` |
| `/eval-praxion` | Single out-of-band quality eval entrypoint: mechanical + LLM-as-judge over completed `.ai-state/` artifacts and (with `--task-slug`) in-flight `.ai-work/<slug>/` manifest. Use `--mechanical-only` for the cheap structural surface alone. Reports land in `.ai-state/praxion_eval_reports/` |
| `/explore-project` | Explore and understand an unfamiliar project's architecture, patterns, and workflow |
| `/full-security-scan` | Run a full-project security audit against all security-critical paths |
| `/landscape-refresh` | Bootstrap or refresh the project's landscape watchlist — flag stale entries (>90 days) and optionally re-validate URLs |
| `/manage-readme` | Create or refine README.md files |
| `/check-experiment` | Poll an in-flight or report a completed ML training experiment |
| `/dashboard` | Launch the Praxion pipeline dashboard for the current project |
| `/decisions` | Disposition decision-health findings — repairs as grouped approvals, retirement candidates one at a time, never in bulk |
| `/decontaminate-ids` | Detect and remediate REQ/AC/step citations in the current project's source code |
| `/merge-worktree` | Merge a worktree branch back into current branch |
| `/new-project` | Scaffold a greenfield Claude-ready Python project and onboard it to Praxion |
| `/onboard-project` | Onboard the current project for the Praxion plugin ecosystem |
| `/project-coverage` | Run the project's canonical coverage target and render a terminal summary via the `test-coverage` skill |
| `/project-metrics` | Compute project complexity/health metrics (churn, complexity, coupling, hot-spots, trends) and write a timestamped report triple to `.ai-state/` |
| `/refresh-claude-blocks` | Refresh a project's onboarded `CLAUDE.md` canonical blocks against the installed plugin, dispositioning locally customized blocks |
| `/refresh-skill` | Refresh version-sensitive sections of a skill against current upstream documentation |
| `/refresh-topology` | Create or refresh the project's test-group topology for scoped test execution (`--init` for first-time creation, no flag for drift-response refresh) |
| `/release` | Bump version, update changelog, and create a release tag |
| `/report-praxion-issue` | File a Praxion-origin `ecosystem-defect` issue on the Praxion repo from a captured healing-sidecar candidate — HITL-gated (never auto-files), category taxonomy `hooks\|blocks\|agents\|scripts\|skills` |
| `/report-upstream` | File a well-formed bug report on an upstream open-source project |
| `/praxion-complete-install` | Reconfigure or recover a marketplace-installed Praxion setup — symlink rules, CLI scripts, and optional context-hub MCP |
| `/praxion-complete-uninstall` | Reverse `/praxion-complete-install` — remove rule/script symlinks and optional context-hub MCP; plugin body is preserved |
| `/review-interface` | Run an interface design review on a file, PR, branch, or named surface via the interface-designer agent |
| `/review-pr` | Code review a pull request |
| `/dispatch-reworks` | Fan out `/resume-rework` into every rework worktree from `REWORK_MANIFEST.md` — background sessions by default, `--terminals` for visible windows |
| `/document-api` | Scaffold best-in-class API documentation for a project's own API surface — auto-detects language/protocol, scaffolds skeleton + Spectral ruleset + CI gate, registers in `doc_manifest.yaml`, idempotent |
| `/resume-rework` | Dispatch the appropriate agent for a rework worktree; cwd-driven auto-discovery of `VERIFIER_FINDINGS.md` (cite `commands/resume-rework.md`) |
| `/resume-pipeline` | Reconcile a pipeline's `WIP.md` against ground truth (git + tests + the `observations.jsonl` WAL) and recover truncated steps — auto-mark verified-complete work, auto-resume partials scoped to the remainder, surface the ambiguous — with a five-surface audit trail (cite `commands/resume-pipeline.md`) |
| `/roadmap` | Produce a project-audited `ROADMAP.md` via a project-derived evaluation lens set (SPIRIT, DORA, SPACE, FAIR, CNCF Platform Maturity, or Custom) through the roadmap-cartographer agent; covers strengths, weaknesses, **opportunities (forward lines of work)**, phased improvements, and deprecations |
| `/run-experiment` | Dispatch an ML training experiment, validate compute budget, stream metrics, write `TRAINING_RESULTS.md` |
| `/scores` | Render a ranked leaderboard of eval runs from `.ai-state/eval_ledger/EVAL_LOG.md` (read-only); supports `--task`, `--sort`, and `--top` filters |
| `/sdd-coverage` | Report spec-to-test and spec-to-code coverage for REQ IDs |
| `/skill-genesis` | Run the skill-genesis agent to autonomously harvest patterns from accumulated learnings (LEARNINGS.md, verification reports, sentinel findings, ADRs); write a timestamped report to `.ai-state/skill_genesis_reports/` for later disposition via `/skill-genesis-review` |
| `/skill-genesis-review` | Disposition pending proposals from a skill-genesis report — batch multi-select presentation, append-only disposition log, surface delegation handoffs |
| `/star-repo` | Star the Praxion repo on GitHub |
| `/test` | Auto-detect test framework and run tests |
| `/upgrade-project` | Re-point this project's version-pinned Praxion surfaces (git hooks, merge driver) to the live plugin install after a praxion plugin upgrade |

## How Commands Work

- **Claude Code**: Loaded from plugin `commands/`, `.claude/commands/` (project), or `~/.claude/commands/` (personal). Invoke with `/` (plugin commands may be namespaced, e.g. `/praxion:co`).
- **Cursor**: Exported to `.cursor/commands/` or `~/.cursor/commands/` by `./install.sh cursor` (frontmatter stripped). Invoke with `/`.
- **Codex**: Exported to `.agents/skills/praxion-command-<name>/SKILL.md` by `./install.sh codex`. Invoke by asking Codex to run the Praxion command, e.g. `run /co with message ...`; the wrapper reads the canonical `commands/<name>.md` file before acting.

For authoring guidance, see the [`command-crafting`](../skills/command-crafting/) skill.
