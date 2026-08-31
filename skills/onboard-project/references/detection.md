# Praxion Onboarding — Detection

Single source for state detection and the two hard guards. See [../SKILL.md](../SKILL.md) §Pre-flight for how these are invoked in the existing-project flow.

## § State detection (6-state predicate table)

Evaluated top-to-bottom; first match wins.

| # | State | Predicate |
|---|-------|-----------|
| G1 | **abort: plugin-source repo** | `.claude-plugin/plugin.json` exists at root ∧ `PRAXION_ALLOW_SELF_ONBOARD != 1` — see [§ Guard G1](#-guard-g1--plugin-source-repo-guard) |
| 1 | `empty` | target path absent, or exists and contains no entries other than `.`/`..` |
| 2 | `hackathon-managed` | `.ai-state/.praxion-onboard.json` exists ∧ its `.mode == "hackathon"` (fallback: `.claude/settings.json` `env.PRAXION_HACKATHON_MODE == "1"`) |
| 3 | `fully-managed` | `.ai-state/.praxion-onboard.json` exists ∧ `.mode != "hackathon"` |
| 4 | `partially-managed` | `.ai-state/` non-empty ∨ `CLAUDE.md` contains `^## Agent Pipeline$` ∨ any `.git/hooks/post-merge` → `git-finalize-hook.sh` — but no stamp |
| 5 | `git-no-praxion` | `.git/` exists, none of the above |
| 6 | `code-no-git` | source files present, no `.git/` |

**Mode defaults from state.** `empty` → `new`; `hackathon-managed` → `hackathon` (or `promote` when `--full` / `--mode promote` is given); all others → `existing`. `code-no-git` additionally offers `git init` as the first gated action. Argument presence also selects the mode: a positional `<project-name>` means `new`, no positional means "onboard this directory". An explicit `--mode` overrides and fails fast (exit 2) when it contradicts the detected state.

**Bash/skill split.** The launcher's classification is authoritative when it ran (passed in the seed trailer as `# Detected state: <state>`); Phase 0 **re-runs the same predicates** and, on disagreement or when the skill was invoked directly (no trailer), uses its own result and says so. A test asserts the bash script's state-name set equals this file's enumerated set.

## § Guard G1 — plugin-source-repo guard

**Predicate.** `test -e .claude-plugin/plugin.json` succeeds AND the environment variable `PRAXION_ALLOW_SELF_ONBOARD` is not set to `1`.

**Why this guard exists.** Detect whether the user has invoked onboarding on a Claude Code plugin source repo (Praxion itself, or any plugin in development that ships skills/agents/rules/commands). Plugin source repos curate their own `CLAUDE.md`, `.ai-state/` skeleton, and onboarding artifacts as the **canonical** sources of those patterns; running onboarding against them would either duplicate content under conflicting headings (the repo's bespoke sections plus newly-injected blocks like `## Agent Pipeline` / `## Praxion Process`) or skew bespoke sections from their downstream-injected counterparts as edits land in only one of the two locations.

**Action on match.** Abort with:

> `This project root contains .claude-plugin/plugin.json — it looks like a Claude Code plugin source repo, not a consumer project. Plugin source repos curate their own CLAUDE.md and .ai-state/ as canonical sources of the onboarding patterns; running /onboard-project would either duplicate content under conflicting headings or skew bespoke sections from their downstream-injected counterparts. If you genuinely want to onboard this repo (rare — only useful for divergent forks), set PRAXION_ALLOW_SELF_ONBOARD=1 in the environment and re-run.`

Exit without writing.

**Override.** If `PRAXION_ALLOW_SELF_ONBOARD=1` is set, print a single-line warning to chat (`Self-onboard override active — proceeding on plugin source repo at <project-root>.`) and continue.

## § Guard — greenfield-shape guard

**Predicate.** `.git/` exists, `.gitignore` contains the AI-assistants header, `.claude/` is empty, AND there is no `src/`, `pyproject.toml`, `package.json`, `Cargo.toml`, or `go.mod` (no source code yet).

**Why this guard exists.** Detect whether the user has accidentally invoked existing-project onboarding on a freshly-scaffolded greenfield project that should run the `new` mode instead.

**Action on match.** Abort with:

> `This directory looks like a freshly-scaffolded greenfield project (.git/ + AI-assistants .gitignore + empty .claude/ + no source tree). Run the new-project entry instead — it scaffolds the codebase via the agent pipeline AND applies the existing-project onboarding surfaces at the end. This entry is for projects that already have code.`

Exit without writing.
