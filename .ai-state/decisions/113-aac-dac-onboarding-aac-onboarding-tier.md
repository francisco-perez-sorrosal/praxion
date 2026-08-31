---
id: dec-113
title: AaC tier integrates into onboarding via plugin-path-resolved scripts and templated artifacts — greenfield default-ON, existing-project default-OFF
status: accepted
category: architectural
date: 2026-05-01
summary: 'Idea 8 wires the v1+v1.1+W4 AaC stack into /onboard-project Phase 8b (default-OFF, opt-in gate) and /new-project + new_project.sh (default-ON, --no-aac opt-out). Per-project surfaces are minimal: fence-region template seed, fitness/ scaffold, golden-rule pre-commit Block D resolved to plugin-installed scripts, architecture.yml workflow with placeholder substitution, and <doc-dir>/diagrams/ directory scaffold per dec-099. No per-project script copies; AaC enforcement scripts stay canonical in the i-am plugin install path and are invoked via the same Phase 4 plugin-path-resolution pattern.'
tags: [aac, onboarding, idea-8, greenfield, existing-project, plugin-path-resolution, workflow-template, fitness-scaffold]
made_by: agent
agent_type: systems-architect
pipeline_tier: standard
affected_files:
  - skills/onboard-project/SKILL.md
  - skills/onboard-project/references/seed-pipeline.md
  - scripts/onboard-project
  - claude/aac-templates/architecture.yml.tmpl
  - claude/aac-templates/fitness-import-linter.cfg.tmpl
  - claude/aac-templates/fitness-test-meta-citation.py.tmpl
  - claude/aac-templates/fitness-test-starter.py.tmpl
  - claude/aac-templates/fitness-conftest.py.tmpl
  - claude/aac-templates/fitness-README.md.tmpl
  - claude/aac-templates/precommit-block-d.sh.frag
re_affirms: dec-099
---

## Context

The v1+v1.1+W4 AaC stack is now on main: fence convention (Idea 2), traceability convention in SDD skill (Idea 3, convention-only), fitness scaffold (Idea 5), golden-rule hook + sentinel EC07 (Idea 6, hook is the per-project surface — sentinel is global), architecture.yml workflow (Idea 7), and sentinel AC dimension (Idea 10, global agent — no per-project surface).

Idea 8 (deferred when v1 shipped) packages this stack into Praxion's onboarding so user projects can opt into Architecture-as-Code with one decision. Three blocking tensions had to be resolved before designing it:

1. **Per-project script ownership.** Scripts like `check_aac_golden_rule.py` and `aac_fence_validator.py` are not currently executable in the Praxion repo and so are not linked into `~/.local/bin/` by `install_claude.sh`. User projects therefore cannot invoke them via PATH today. Fixing executability AND adding to the install filter would change the install-script contract; copying the scripts into each user project creates drift; symlinking couples user projects to plugin install layout.

2. **Greenfield vs. existing-project gating asymmetry.** The ledger directs greenfield ON, existing-project OFF. This asymmetry must be encoded in two different command bodies plus one bash bootstrap, with consistent conflict detection so re-running either flow on an already-AaC project is a no-op.

3. **Forward-binding constraint from dec-099.** The original ledger text described scaffolding a top-level `architecture/` directory; dec-099 already settled that `<doc-dir>/diagrams/` (typically `docs/diagrams/`) is canonical per dec-094. The Phase 8b prompt language must explicitly use `<doc-dir>/diagrams/` and never `architecture/`, so a future implementer reading only the IDEA_PROPOSAL would not silently re-introduce the conflict.

Additionally, the per-project surface for Idea 6 had to be disambiguated: sentinel EC07 (audit) is global because sentinel is a global agent — only the pre-commit gate (Block D) needs to land in user projects.

## Decision

Wire Idea 8 into onboarding with five per-project installable surfaces, two opt-in vectors, and one canonical script-invocation pattern.

**Surfaces (all idempotent; conflict-detected; never overwriting existing files):**

1. **Fence-region template seed** in user-project `ARCHITECTURE.md` / `docs/architecture.md` (when present). Appends a commented-out fence example pointing at the convention rule; does NOT inject a real fence into existing prose.
2. **`fitness/` directory scaffold** — copy 5 template files (`import-linter.cfg`, `tests/{conftest,test_meta_citation,test_starter}.py`, `README.md`). Per-file existence check; existing files are never overwritten.
3. **Golden-rule pre-commit Block D fragment** — appended into the user-project `.git/hooks/pre-commit` that Phase 4 already wrote. Block D's plugin-path resolution mirrors Phase 4's `check_id_citation_discipline.py` pattern: resolve `${PLUGIN_ROOT}` from `~/.claude/plugins/installed_plugins.json` at hook-run time, invoke `python3 ${PLUGIN_ROOT}/scripts/check_aac_golden_rule.py --mode=gate`. No per-project script copy.
4. **`architecture.yml` workflow template** — render `claude/aac-templates/architecture.yml.tmpl` with `{{PROJECT_*}}` placeholder substitution (paths, Python version, plugin dir) and write to `.github/workflows/architecture.yml`.
5. **`<doc-dir>/diagrams/` directory scaffold** — create `docs/diagrams/` (per dec-099); write `.gitkeep` only when otherwise empty so the scaffolded path is visible to git.

**Opt-in vectors:**

- **Existing-project (`/onboard-project` Phase 8b):** New gate between current Phase 8 and Phase 9, three options — `Skip AaC (recommended)` (default), `Install AaC tier`, `Run all rest` (defaults the AaC choice to skip).
- **Greenfield (`/new-project` + `new_project.sh`):** Default-ON; opt-out via `new_project.sh --no-aac` flag or `PRAXION_NEW_PROJECT_NO_AAC=1` env var. The seed prompt context line `# AaC scaffolding: <enabled|disabled>` propagates the choice into `/new-project`'s flow.

**Sentinel-only set (no per-project install needed, made explicit in command body):** Idea 3 (traceability convention — documented in the global SDD skill which user projects inherit) and Idea 10 (sentinel AC dimension — sentinel is a global agent invoked against user projects on demand).

**Script-invocation pattern:** Praxion-shipped AaC enforcement scripts (`check_aac_golden_rule.py`, `aac_fence_validator.py`) stay canonical in the `i-am` plugin install path. User projects invoke them via plugin-path resolution at hook-run time and CI workflow time. No per-project copies. This matches Phase 4's existing pattern for `check_id_citation_discipline.py`.

**Forward-binding compliance:** Phase 8b language and `/new-project` AaC sub-flow both use `<doc-dir>/diagrams/`; no `architecture/` directory is created anywhere. Re-affirms dec-099.

**Token-budget impact:** Zero. Commands are slash-command-discovered, not always-loaded. Per-project artifacts install locally — never reach Praxion's CLAUDE.md or rules surface.

## Considered Options

### Option 1 — Copy scripts into every user project

Each onboarding installs `scripts/check_aac_golden_rule.py` and `scripts/aac_fence_validator.py` into the user project's `scripts/` (or `.praxion/scripts/`).

**Pros:** User project owns a snapshot — independent of plugin install state. Works without the i-am plugin installed.

**Cons:** Maintenance surface explosion — every script bugfix requires re-running onboarding to refresh user copies. Drift between Praxion's own AaC enforcement and user-project enforcement grows over time. Inconsistent with Phase 4's existing `check_id_citation_discipline.py` pattern. Adds two new sub-steps for snapshot updates.

### Option 2 — Symlink scripts to plugin install path

User project `.git/hooks/pre-commit` calls `python3 ~/.claude/plugins/.../i-am/scripts/check_aac_golden_rule.py` directly via a hardcoded path.

**Pros:** Zero copies; plugin upgrades flow through.

**Cons:** Hardcodes the plugin install layout into the user's hooks. If the plugin is uninstalled or moved, user projects break silently. Not portable across user-scope vs. project-scope plugin installs.

### Option 3 — Invoke via plugin path resolved at hook-run time (CHOSEN)

Block D resolves `${PLUGIN_ROOT}` from `~/.claude/plugins/installed_plugins.json` on each hook fire and invokes the canonical script in place. Same pattern as Phase 4.

**Pros:** Zero copies. Consistent with existing onboarding pattern. Plugin upgrades flow automatically. Plugin uninstall produces a clean no-op (the script-not-found guard exits 0), not a hard error.

**Cons:** Requires the i-am plugin to be installed for AaC enforcement to fire — not a regression vs. Phase 4's behavior, but worth documenting in the Phase 8b body.

### Option 4 — Default-ON for existing projects (mirroring greenfield)

Symmetric onboarding behavior — both flows install AaC by default; users opt out.

**Pros:** Consistent UX. Stronger AaC adoption.

**Cons:** Risks colliding with the existing project's established conventions (e.g., a project that already runs import-linter from a different config path). Existing projects have established discipline; greenfield does not. Asymmetry is the right model.

### Option 5 — Standalone `/onboard-aac` command (no integration with onboarding)

Split AaC scaffolding into its own slash command instead of Phase 8b.

**Pros:** Clear single-purpose command. No coupling between onboarding and AaC.

**Cons:** Loses the discoverability of the AaC tier — users running `/onboard-project` would not learn about `/onboard-aac` unless documented elsewhere. Two paths converge later anyway. Phase 8b is the natural home.

## Consequences

**Positive:**

- Idea 8 ships with zero new always-loaded tokens; the entire AaC tier integrates as command-extension and template-file surface.
- AaC enforcement is consistent between Praxion's own dogfooding and user projects — they invoke the same scripts via the same plugin-path resolution.
- Greenfield projects get AaC discipline from day one without the user needing to know what AaC is; the seed pipeline produces fence-marked architecture docs and the user sees real CI on first push.
- Existing projects opt in deliberately; no unwanted surprises in established codebases.
- Forward-binding constraint from dec-099 is honored mechanically — the Phase 8b body uses `<doc-dir>/diagrams/` and never `architecture/`.
- Idempotence is enforced by per-sub-step predicate; re-runs are clean.

**Negative:**

- User projects without the i-am plugin installed get silent no-op AaC enforcement. This matches Phase 4's behavior for id-citation, but is worth surfacing in the Phase 8b body so users debugging "why isn't my hook firing" can find the cause.
- The rendered `architecture.yml` drifts from Praxion's own `architecture.yml` over time as we evolve the workflow. Users updating action versions or workflow logic do so as normal ongoing maintenance; not a Praxion-level concern. Mitigated by a header comment in the rendered file naming the convention rule.
- Five sub-steps in Phase 8b adds command-body length (~80–120 lines per command). Two large command files (`onboard-project.md` 486 lines today, `new-project.md` 487 lines today) grow ~12–15%. Comfortably under the 800-line ceiling.
- The Block D append into the user's pre-commit hook adds a third block to a hook that was previously a single inline check — small ordering concern (AaC check appended AFTER existing id-citation check so failure of one does not mask the other).

**Neutral:**

- Sentinel EC07 audits run against user projects via the global sentinel agent — no per-project install. Same for SDD traceability convention. Future maintainers reading Phase 8b see this explicitly so no one tries to "complete" the onboarding by adding redundant per-project copies.

## Prior Decision

**dec-099** — *Idea 8 directory premise reconciled — `.c4` source lives at `<doc-dir>/diagrams/`, not `architecture/` at project root* — was a forward-binding constraint recorded during the v1 architect-stage trade-off analysis, when Idea 8 was deferred to v1.2. dec-099 declared that whenever Idea 8 ships, `/onboard-project` Phase 8b and `/new-project` and `new_project.sh` must scaffold `<doc-dir>/diagrams/` per dec-094, never a top-level `architecture/`.

This ADR re-affirms dec-099 by encoding the constraint mechanically into the v1.2 implementation: the Phase 8b body's sub-step 8b.5 creates `<doc-dir>/diagrams/` (with `docs/` as default doc-dir); the greenfield AaC sub-flow does the same; no `architecture/` path appears anywhere in the surfaces touched. dec-099 was correctly forward-binding — no new evidence has emerged that would justify revisiting the directory choice.

The reason this is a re-affirmation rather than a routine consequence: dec-099 was made *speculatively* (about a future feature), and re-affirming it at the moment of implementation creates a public record that the constraint was actively considered, not silently inherited. Future architects re-opening the directory question would need new evidence (e.g., a tooling change that breaks `<doc-dir>/diagrams/`); silent drift is prevented.
