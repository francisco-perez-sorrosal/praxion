---
id: dec-draft-754fe078
title: Ship kepano/obsidian-skills via the Claude Code marketplace, not a clone+symlink
status: proposed
category: architectural
date: 2026-05-20
summary: Replace the clone+marker+symlink mechanism in dec-197 with `claude plugin marketplace add kepano/obsidian-skills` + `claude plugin install obsidian@obsidian-skills` invoked non-interactively from `scripts/install-obsidian-deps.sh`. Plugin lands at user scope; SKILL.md files are at correct depth; no per-project filesystem mutation.
tags: [obsidian, install, kepano, marketplace, claude-code, supersession]
made_by: agent
agent_type: systems-architect
branch: worktree-obsidian-marketplace-install
pipeline_tier: standard
affected_files:
  - scripts/install-obsidian-deps.sh
  - commands/onboard-project.md
  - commands/onboard-project-obsidian.md
  - commands/new-project.md
  - claude/canonical-blocks/obsidian-integration.md
  - docs/obsidian-integration.md
  - CLAUDE.md
  - rules/swe/plugin-install-conventions.md
supersedes: dec-197
---

## Context

`dec-197` (accepted 2026-05-19) decided that `kepano/obsidian-skills` would be shipped via a shallow `git clone` into `~/.local/share/praxion/kepano-skills` plus a marker file at `~/.config/praxion/obsidian-skills.path`. The per-project surface in `dec-197` was a symlink from `<project>/.claude/skills/obsidian -> $KEPANO_SKILLS_ROOT` written by Phase 8d.3 of `/onboard-project`.

Post-merge dogfood revealed three category errors in this mechanism:

1. **Kepano's repo is a proper Claude Code marketplace + plugin.** It has `.claude-plugin/marketplace.json` and `.claude-plugin/plugin.json` declaring `name: obsidian`, `version: 1.0.1`, and a `plugins:` list — i.e., it is *designed* to be consumed via Claude Code's plugin infrastructure, not as a generic git repo.
2. **Kepano's README documents three install methods** in priority order: marketplace (`/plugin marketplace add kepano/obsidian-skills` + `/plugin install obsidian@obsidian-skills`), `npx skills add`, and manual fetch. The clone-and-place approach the prior pipeline reached for is the *least preferred* of the three.
3. **The symlink puts the full repo at the wrong depth.** The kepano repo's layout is `skills/<name>/SKILL.md`. With `<project>/.claude/skills/obsidian -> <repo>/`, SKILL.md files land at `<project>/.claude/skills/obsidian/skills/<name>/SKILL.md` — Claude Code's skill discovery does not look two levels deep. Concretely, `find -L .claude/skills -name SKILL.md` on the Praxion main checkout that has `dec-197`'s mechanism applied returns the kepano SKILL.md paths but they are not actually discoverable by an agent's skill resolver.

Three unknowns gated the decision rewrite, all verified empirically during the pipeline that authored this ADR:

- **Unknown 1 — Is `claude plugin marketplace add` invocable non-interactively from Bash?** Yes. `claude plugin --help` lists `marketplace add` and `install` as first-class subcommands; both run successfully from a non-interactive Bash invocation and write to the same on-disk state that the in-session slash commands would.
- **Unknown 2 — Where does a marketplace-installed plugin land?** Globally, at `~/.claude/plugins/cache/<marketplace>/<plugin>/<version>/`. Default scope is `user`. Praxion itself (`i-am@bit-agora`) is installed this way at `~/.claude/plugins/cache/bit-agora/i-am/0.2.0/`.
- **Unknown 3 — Are SKILL.md files at correct discovery depth post-install?** Yes. `find ~/.claude/plugins/cache/obsidian-skills/obsidian/1.0.1 -name SKILL.md` returns the five kepano SKILL.md files at `<install-path>/skills/<name>/SKILL.md` — the same convention every other marketplace-shipped plugin uses, including Praxion itself and `huggingface-skills`.

The marketplace mechanism subsumes everything `dec-197`'s clone+symlink path was trying to achieve, with none of the drawbacks (wrong depth, marker-file plumbing, per-project mutation, drift across operators' machines). It is also the same install pattern Praxion uses for itself — so adopting it eliminates an operational inconsistency.

## Decision

Replace the kepano-shipping mechanism with the Claude Code marketplace:

1. **Procedure 1 — `scripts/install-obsidian-deps.sh`** is rewritten as a thin Bash adapter:

   ```bash
   claude plugin marketplace add kepano/obsidian-skills
   claude plugin install obsidian@obsidian-skills
   ```

   Idempotency uses `claude plugin list` as the predicate (skip-if-installed). Soft prerequisite check: `command -v claude` — warn and exit 0 if absent (warn-and-continue contract preserved from `dec-197`). The Obsidian-Desktop soft-check is unchanged. The `--check`, `--uninstall`, `--relink` flags route to `claude plugin list`, `claude plugin uninstall`, and `claude plugin update` respectively. The marker file (`~/.config/praxion/obsidian-skills.path`) goes away — it was only needed because the prior mechanism placed the checkout at an operator-overridable path; the marketplace install has a fixed, well-known location.

2. **Procedure 2 — Phase 8d.3 of `/onboard-project`** is rewritten from a per-project symlink mutation to a predicate-only verification: confirm `obsidian@obsidian-skills` is installed at user scope, warn if not. Phase 8d.2 (`KEPANO_SKILLS_ROOT` resolution) collapses or is repurposed as a `claude` CLI presence check — the marker file is no longer the load-bearing artifact for 8d.3.

3. **`/onboard-project-obsidian` is deleted.** The standalone retrofit command was redundant: `/onboard-project` is already idempotent and re-running it on an existing project enters Gate 8d and runs only missing sub-steps. Every cross-reference in shipped artifacts (`CLAUDE.md`, `claude/canonical-blocks/obsidian-integration.md`, `commands/onboard-project.md`, `commands/new-project.md`, `docs/obsidian-integration.md`) is rewritten to point at re-running `/onboard-project`.

4. **A new path-scoped rule** at `rules/swe/plugin-install-conventions.md` encodes the lesson: when shipping a foreign skill bundle from a Claude Code marketplace repo, prefer marketplace install over clone-and-symlink. Path-scoped to the install-surface files so it loads only when an agent touches those files.

`dec-198` (Shape B default-on) is unchanged — the *behavior* it commits to is preserved; only the *mechanism* under it changes. `dec-196` (CLI allowlist policy) is unchanged — the 8-entry `permissions.deny` block stays byte-identical.

## Considered Options

### Option 1 — Marketplace install via the `claude plugin` CLI (chosen)

- **Pros:** SKILL.md files at correct discovery depth (verified). Mirrors how Praxion itself is installed — operational consistency. No per-project filesystem mutation (the symlink goes away). Refresh, uninstall, and version-pinning are first-class operations the CLI already supports. Mechanism is non-interactive — the CLI subcommands work from Bash, so `./install.sh code` can drive the install without dropping into a Claude Code session. Single source of truth: the kepano marketplace repo is the version pin.
- **Cons:** Hard dependency on `claude` binary on PATH at install time (mitigated: soft prerequisite check, warn-and-continue). Operator cannot pin to an arbitrary kepano-skills git revision — pinning is by plugin version, which is what the marketplace contract specifies.

### Option 2 — Marketplace install but require user to run slash commands

- **Pros:** No additional Bash dependency on the `claude` binary inside `install.sh`.
- **Cons:** Wasteful — the same code path is reachable from Bash, and the prior pipeline's failure was partly that it didn't probe this surface. Requires the operator to open a Claude Code session to complete an install step, breaking the `./install.sh code` one-shot contract.

### Option 3 — `npx skills add` (Node-based install path)

- **Pros:** Kepano-documented path; doesn't require the Claude Code CLI.
- **Cons:** Adds a Node.js dependency for an install step Claude Code already handles natively. Misaligns with Praxion's existing marketplace pattern (every other shipped skill bundle is marketplace-installed). Operator may not have Node.js even when they have Claude Code.

### Option 4 — Fix the existing manual clone by adjusting the symlink depth

- **Pros:** Smallest mechanical change (one-line fix: `ln -s "$KEPANO_SKILLS_ROOT/skills" .claude/skills/obsidian`).
- **Cons:** Repairs the symptom, not the category error. Keeps Praxion in the "ship a skill by cloning a foreign repo and pointing at it" pattern when the upstream is a proper marketplace plugin. Future maintenance burden: no automatic version updates, marker file proliferation, drift across operators' checkouts. Doesn't match the precedent Praxion sets for itself (`i-am@bit-agora` is marketplace-installed).

### Option 5 — Vendor the kepano-skills repo into Praxion's tree

- **Pros:** No network dependency at install time.
- **Cons:** Already considered and rejected by `dec-197` for sound reasons (repo size, drift, the `shipped-artifact-isolation` boundary). Marketplace install has all of vendor's advantages (no operator-side clone) with none of the disadvantages.

## Consequences

**Positive:**

- The integration *actually works*. Skills are discoverable. Before this ADR, `find -L .claude/skills -name SKILL.md` on the post-`dec-197` Praxion checkout returned the kepano SKILL.md files at a depth Claude Code doesn't resolve. After this ADR, the user-scope marketplace install puts them where the resolver looks.
- Operational consistency with how Praxion is installed. Operators learn one pattern (`claude plugin marketplace add` + `claude plugin install`), not two.
- The per-project surface shrinks. `<project>/.claude/skills/obsidian` no longer exists; only the three genuinely per-project surfaces remain (gitignore block, CLAUDE.md block, settings.json deny entries). The "what does Phase 8d do to my project" model is cleaner.
- The standalone retrofit command's ~270 lines of shipped surface goes away. One fewer command to keep in sync with `/onboard-project`'s Phase 8d body.
- Refresh, uninstall, and version-pinning use the same CLI verbs every other plugin uses.

**Negative:**

- Hard dependency on `claude` binary at install time. Mitigated by soft prerequisite check + warn-and-continue, but a CI runner without the `claude` binary cannot complete this step (it warns and skips). For operators on a dev machine, the binary is virtually always present (it's what they're installing Praxion *for*).
- Operator loses control over kepano-skills's git revision. Refresh now means "whatever version kepano publishes next to the marketplace." For the strategic-signal-anchored upstream (Obsidian CEO maintaining their own reputation-bearing plugin), this is a feature, not a bug.
- The marker file (`~/.config/praxion/obsidian-skills.path`) is removed. Any operator who relied on it for tooling outside Praxion will need to switch to `claude plugin list --json`. Risk is low — the marker file was introduced by `dec-197` 24 hours before this supersession; no external tooling has had time to grow a dependency on it.

## Prior Decision

This ADR supersedes `dec-197` (kepano-shipping-mechanism). The shipping mechanism `dec-197` chose — shallow git clone to a deterministic global location plus a marker file plus a per-project symlink — is replaced by the marketplace-based install path. The rationale for that supersession is the three category errors documented in the Context section above:

> Kepano's upstream is a proper Claude Code marketplace plugin (with `.claude-plugin/marketplace.json` and `plugin.json`), and the install mechanism `dec-197` reached for did not put SKILL.md files at the depth Claude Code's skill discovery looks for.

`dec-197`'s "fetch-at-install via shallow git clone" decision was an honest reach: at the time of authoring, the available evidence was kepano's repo on GitHub and the Claude Code plugin documentation. The marketplace install path was not probed before commitment. This ADR closes that loop by probing the `claude plugin` CLI directly and committing to the result.

`dec-198` (Shape B default-on) is **not superseded**. The behavior it commits to — Obsidian Shape B as Praxion's default-on integration — is preserved. Only the mechanism beneath it changes. The references to "kepano-skills in `.claude/skills/`" in `dec-198`'s body remain accurate at the directory-of-discoverable-skills level; the path simply shifts from `<project>/.claude/skills/obsidian/` (the broken `dec-197` location) to `~/.claude/plugins/cache/obsidian-skills/obsidian/1.0.1/skills/`. `dec-198`'s "standalone retrofit command" sentence becomes inaccurate after this ADR — the retrofit happens by re-running `/onboard-project`. Body text is preserved as a point-in-time artifact; no supersession is needed.

`dec-196` (CLI allowlist policy) is **not superseded** and the 8-entry `permissions.deny` block stays byte-identical.
