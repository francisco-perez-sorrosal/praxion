---
diataxis: reference
audience: developer
---

# Claude Code Behavior Verification — 2026-05-12

> The empirical appendix to the [context-engineering comparison study](05-comparison.md). It records what was confirmed (and refuted) about Claude Code's actual behavior so the [roadmap](07-praxion-roadmap.md) doesn't rest on unverified claims. Verified against the current official docs (`code.claude.com/docs/en/memory`) + GitHub issues, 2026-05-12. (Done by direct WebFetch/WebSearch because the `claude-code-guide` agent crashed — `td-021`, the many-skill-session `Explore`/sub-agent bug.)

## V1 — Path-scoped rules (`paths:` frontmatter) trigger on Read, NOT Write/Edit/MultiEdit — CONFIRMED
- Official docs, verbatim: *"Path-scoped rules trigger when Claude reads files matching the pattern, not on every tool use."* and *"Rules without a `paths` field are loaded unconditionally and apply to all files."*
- Corroborating GitHub issues: [#23478](https://github.com/anthropics/claude-code/issues/23478) ("Path-based rules ... not loaded on Write tool — only on Read"), [#38487](https://github.com/anthropics/claude-code/issues/38487) ("[FEATURE] Path-scoped rules should load when Write/Edit targets a matching path"), [#16853](https://github.com/anthropics/claude-code/issues/16853).
- **Praxion impact:** Praxion's 13 path-scoped rules (`coding-style`, `testing-conventions`, `pr-conventions`, `diagram-conventions`, `html-output-conventions`, `readme-style`, `aac-dac-conventions`, `id-citation-discipline`, `staleness-policy`, `shipped-artifact-isolation`, `eval-driven-verification`, `experiment-tracking-conventions`, `gpu-budget-conventions`) do NOT load when an agent *creates* a matching file via Write without Reading it first. An implementer creating a new `.py` won't get `coding-style.md`; a doc-engineer creating a new `.md` won't get `readme-style.md` / `diagram-conventions.md`.

## V2 — `paths:` frontmatter in `~/.claude/rules/` (user-level) is IGNORED — CONFIRMED (likely still live)
- [Issue #21858](https://github.com/anthropics/claude-code/issues/21858) — opened 2026-01-30, **Closed** with label `stale` (auto-closed for inactivity, not fixed). Bug: `paths:` frontmatter in `~/.claude/rules/` is completely ignored — those rules are NEVER loaded. Table from the issue:
  | Location | With `paths:` | Result |
  |---|---|---|
  | `~/.claude/rules/` | yes | ❌ NOT loaded |
  | `./.claude/rules/` | yes | ✅ loaded |
  | `./.claude/rules/` (symlink → user-level) | yes | ✅ loaded |
  | `~/.claude/rules/` | no `paths:` | ✅ loaded unconditionally |
  - Workaround: symlink FROM `./.claude/rules/` TO the user-level file (project-level symlinks resolve & load normally — docs confirm `.claude/rules/` supports symlinks).
- **Praxion impact (HIGH — needs empirical check):** `rules/CLAUDE.md` says *"install_claude.sh symlinks rules to ~/.claude/rules/ for global availability."* If that's the active install path, Praxion's 15 path-scoped rules live at `~/.claude/rules/*.md` WITH `paths:` frontmatter → per this bug they are **never loaded** (or, per the conflicting [#16299](https://github.com/anthropics/claude-code/issues/16299), loaded *unconditionally always* — either way it's wrong). **Action: verify with `/memory` in a project + the `InstructionsLoaded` hook (see V7) whether `coding-style.md` etc. actually appear when editing matching files.** This could be a real, silent gap in globally-installed Praxion.

## V3 — `paths:` (quoted/YAML-list) vs `globs:` frontmatter format — AMBIGUOUS, needs empirical check
- [Issue #17204](https://github.com/anthropics/claude-code/issues/17204) — opened 2026-01-09, **Open**, label `stale`. Reports: `paths: "**/*.cs"` (quoted scalar) and `paths:` as a YAML list both silently fail to load; `globs: **/*.cs, **/Controllers/**` (unquoted, comma-separated) works.
- BUT the **current official docs** present `paths:` as a YAML list with quoted strings as the canonical, working format, with an explicit example: `paths:\n  - "src/api/**/*.ts"`. So either a fix landed and the issue is just stale, or the docs are aspirational.
- **Praxion impact:** Praxion's path-scoped rules use `paths:` with YAML-list quoted values (the documented format). **Action: empirically confirm they parse — `/memory` + `InstructionsLoaded` hook.** If they don't, the rules are dark and the fix is trivial (the conventions themselves are fine).

## V4 — "~150–200 instruction ceiling" is NOT an official Anthropic figure — be skeptical
- Official docs say: *"target under 200 **lines** per CLAUDE.md file. Longer files consume more context and reduce adherence."* — that's about *lines per file*, a soft guideline, not a hard instruction-count ceiling. Also: *"CLAUDE.md content is delivered as a user message after the system prompt, not as part of the system prompt itself ... there's no guarantee of strict compliance."*
- abhishekray's "frontier models follow ~150–200 total instructions before adherence drops uniformly; Claude Code's system prompt consumes ~50 slots" is a **community estimate / interpretation** — possibly conflating the "200 lines" guidance with something else. Do NOT enshrine "150–200 instructions" as fact in any Praxion artifact.
- **Citable framing for the roadmap instead:** "CLAUDE.md / always-loaded rules are *context, not enforced config* — specific, concise, well-structured wins; target <200 lines per file; longer reduces adherence; for hard guarantees use a hook." (All directly from the docs.)

## V5 — "rule re-injection multiplies cost" — plausible community observation, mechanism not officially confirmed
- Docs say unconditional rules "are loaded at launch with the same priority as `.claude/CLAUDE.md`" and path-scoped rules load "when matching files are opened" — they do NOT document a per-tool-call re-injection multiplier. abhishekray's "93K from re-injections over ~30 tool calls" (43K initial / 93K re-injections / 50K conversation) is a single observed session, not a documented mechanism. Plausible *if* path-scoped rules re-inject on each matching Read, but unconfirmed.
- **For the roadmap:** the *budget discipline* is sound (every always-loaded token earns its attention share; <200 lines/file); the *specific numbers* are not citable. Frame the cost qualitatively, cite the docs' "loaded into context at the start of every session, consuming tokens" + "longer reduces adherence", and present abhishekray's table (if at all) as "one practitioner's observed session, mechanism uncertain."

## V6 — Ancestor / nested CLAUDE.md loading — CONFIRMED (and it makes the "workspace layer" free)
- Ancestor `CLAUDE.md` + `CLAUDE.local.md`: **loaded in full at launch**, walking cwd → filesystem root. Order is root-down (parent before child); cwd's file read last (highest precedence). Precedence chain: managed-policy → user (`~/.claude/CLAUDE.md`) → ancestor dirs → cwd → (subdir files on-demand).
- Subdirectory `CLAUDE.md`: **loaded on-demand** when Claude reads a file in that subdir — NOT at launch.
- **Praxion impact:** (a) A "workspace / directory-of-repos" `CLAUDE.md` at e.g. `~/repos/myorg/` would be picked up automatically when running `claude` from a project nested inside — **no new mechanism needed, just a convention + a template.** (b) Praxion's `scripts/CLAUDE.md` and `rules/CLAUDE.md` are *subdirectory* files relative to the repo root → they load **on-demand** (when an agent reads a file under `scripts/` or `rules/`), not at session start. Worth knowing — they're not part of the launch-time always-loaded surface.
- `--add-dir` does NOT load CLAUDE.md from extra dirs unless `CLAUDE_CODE_ADDITIONAL_DIRECTORIES_CLAUDE_MD=1`.

## V7 — `CLAUDE.local.md`, `claudeMdExcludes`, `InstructionsLoaded` hook — all real & current
- `CLAUDE.local.md` — **supported, not deprecated.** Per-project private prefs, `.gitignore` it; loads alongside `CLAUDE.md`, treated the same. Worktree caveat: only exists in the worktree where created — to share across worktrees, `@~/.claude/...` import instead.
- `claudeMdExcludes` — **real setting** (array, merges across layers; set in `.claude/settings.local.json` etc.): skip specific CLAUDE.md / rules files by absolute-path glob. Managed-policy CLAUDE.md can't be excluded. Useful for monorepos with irrelevant ancestor files.
- `InstructionsLoaded` hook — docs explicitly recommend it to **log exactly which instruction files load, when, and why** — *"useful for debugging path-specific rules or lazy-loaded files in subdirectories."* This is the tool to verify V2/V3.
- Managed-policy CLAUDE.md locations: macOS `/Library/Application Support/ClaudeCode/CLAUDE.md`; Linux/WSL `/etc/claude-code/CLAUDE.md`; Windows `C:\Program Files\ClaudeCode\CLAUDE.md`. Plus `claudeMd` key in `managed-settings.json`. Can't be excluded.

## V8 — Auto memory — CONFIRMED, matches Praxion's `memory-protocol.md`
- `~/.claude/projects/<project>/memory/MEMORY.md` + topic files. First 200 lines OR 25 KB of `MEMORY.md` loaded every session; topic files on-demand. Requires CC v2.1.59+. `autoMemoryEnabled` setting; `CLAUDE_CODE_DISABLE_AUTO_MEMORY=1`; `autoMemoryDirectory` (user/policy settings only — not project/local, for security). Keyed by git repo → shared across worktrees & subdirs of one repo, machine-local. Subagents can have their own auto memory (`/en/sub-agents#enable-persistent-memory`).
- Distinct from user-authored CLAUDE.md. Praxion's `memory-protocol.md` already models the dual system (Claude auto-memory vs. memory-mcp) + conflict-resolution order — this verification confirms the auto-memory side.
- Note: `/init` has an interactive multi-phase mode (`CLAUDE_CODE_NEW_INIT=1`) that sets up CLAUDE.md + skills + hooks — overlaps Praxion's `/onboard-project`; worth a glance when revisiting onboarding.
- Note: block-level HTML comments in CLAUDE.md are stripped before injection (free maintainer-notes channel) — matches `diagram-conventions.md`'s note about react-markdown escaping `<img>`; relevant to `html-output-conventions`.

---

### Net effect on the roadmap
- **Promote** "path-scoped rule trigger gotcha" from a doc note to a **two-part action**: (1) document the Read-only trigger in `rules/CLAUDE.md` + `rule-crafting`; (2) **empirically verify** whether Praxion's path-scoped rules load at all under the `~/.claude/rules/` install (V2/V3) — and if not, fix the install (project-level symlink, or `globs:` format, or move the load-bearing parts into always-loaded rules / skills). Add a tech-debt-ledger row.
- **Soften** the "import the token-economy numbers" item: import the *discipline* and the *citable doc guidance* (<200 lines/file; context-not-config; specific/concise/structured), NOT the unverified "150–200 instructions / 43-93-50K" figures.
- **Confirm** the workspace-layer (option C2) is cheap & native — no new mechanism, just convention + template.
- **Add** to the onboarding/docs work: surface `CLAUDE.local.md`, `claudeMdExcludes`, and the `InstructionsLoaded` debugging hook (Praxion doesn't currently mention these and they're genuinely useful for onboarded projects, esp. monorepos).
