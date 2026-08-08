---
id: dec-draft-92fca7f1
title: Rename the Claude Code plugin identity from `i-am` to `praxion`
status: proposed
category: architectural
date: 2026-08-07
summary: Rename the plugin and marketplace entry from `i-am` to `praxion`, changing every namespaced artifact reference, to resolve a verified name collision with the `.i-am` dotfiles skill and align the sole surface that still disagrees with the project's name.
tags: [naming, plugin, marketplace, migration, published-contract, namespace]
made_by: agent
agent_type: systems-architect
branch: main
pipeline_tier: standard
dissent: "The collision is referential, not a hard namespace clash — nothing shadows anything — so prose disambiguation at the three always-loaded sites buys most of the readability benefit for none of the migration risk, and the rename's cost lands hardest on already-distributed managed-project artifacts that no shipped refresh path repairs."
affected_files:
  - .claude-plugin/plugin.json
  - claude/aac-templates/architecture.yml.tmpl
  - claude/aac-templates/precommit-block-d.sh.frag
  - claude/config/CLAUDE.md.tmpl
  - commands/onboard-project.md
  - hooks/inject_subagent_context.py
  - hooks/send_event.py
  - new_project.sh
  - task-chronograph-mcp/src/task_chronograph_mcp/relay_helpers.py
---

# Rename the Claude Code plugin identity from `i-am` to `praxion`

## Context

The plugin ships as `name: "i-am"` in `.claude-plugin/plugin.json` and as `i-am@bit-agora`
in the `bit-agora` marketplace. Every namespaced artifact reference derives from that
identifier: agents resolve as `i-am:sentinel`, commands as `/i-am:eval-praxion`, MCP tools as
`mcp__plugin_i-am_<server>__<tool>`, and the user's `enabledPlugins` key is `i-am@bit-agora`.

Three findings motivate changing it. Each was verified against this machine and this
repository rather than taken from recollection.

**1. A verified name collision, in the worst possible domain.** A different project — the
`.i-am` dotfiles at `github.com/francisco-perez-sorrosal/i-am` — installs a user-scope skill
named exactly `i-am`, symlinked at `~/.claude/skills/i-am -> /Users/fperez/.i-am/config/skills/i-am`.
Its `description` frontmatter reads: *"What this machine is and what may be written on it. Read
before introducing an identity, credential, endpoint, email, git config or API key anywhere on
this machine… a work machine enforces a data boundary that cannot be undone once broken."*
Always-loaded content that says "the `i-am` plugin ecosystem" — which is exactly what
`claude/config/CLAUDE.md.tmpl` says, and which ships into every managed project — therefore has
two plausible referents on any machine with both installed, and the wrong referent governs
secrets handling and work/personal data boundaries.

The collision must be characterised precisely, because the precise form is what the runner-up
option turns on. It is **referential, not a hard namespace clash**: the dotfiles skill is
invoked as `i-am`, plugin skills as `i-am:<name>`, and neither shadows the other. No resolution
breaks today. What breaks is a reader's — or an agent's — ability to tell which thing a bare
`i-am` denotes.

**2. The codebase already believes it is called Praxion.** The identifier is the last holdout,
and the code documents the gap in its own names:

- `task-chronograph-mcp/src/task_chronograph_mcp/relay_helpers.py:41` — `_PRAXION_AGENT_PREFIX = "i-am:"`.
  The constant is *named* Praxion; only its value says `i-am`. Four lines above,
  `TRACER_NAME = "praxion.chronograph"`.
- `hooks/inject_subagent_context.py:109-110` — `def _is_praxion_native(subagent_type: str)` whose
  docstring reads *"Return True for Praxion-native agents (`i-am:*` prefix)"*, returning
  `subagent_type.startswith("i-am:")`.

Every such site pays a translation step at every reading. The rename retires the translation
rather than documenting it.

**3. Alignment.** The repository, `README.md`, `docs/`, the `/praxion-*` command family, the
`praxion.chronograph` tracer and the project's own `CLAUDE.md` all say Praxion. The plugin
identifier is the sole surface that does not.

**Verified environment** (Claude Code 2.1.224): `enabledPlugins` carries `"i-am@bit-agora": true`;
the cache lives at `~/.claude/plugins/cache/bit-agora/i-am/`; the persistent data directory
`~/.claude/plugins/data/i-am-bit-agora/` is **empty**, so no user state is stranded by the move.

## Decision

Rename the plugin identity from `i-am` to `praxion` in both `.claude-plugin/plugin.json` and the
`bit-agora` marketplace entry, and propagate the change through every namespaced reference:
`i-am:<agent>` → `praxion:<agent>`, `/i-am:<command>` → `/praxion:<command>`,
`mcp__plugin_i-am_<server>__<tool>` → `mcp__plugin_praxion_<server>__<tool>`, and the settings
key `i-am@bit-agora` → `praxion@bit-agora`.

Publish a `renames` map (`{"i-am": "praxion"}`) in the marketplace manifest to auto-migrate
`enabledPlugins` and `pluginConfigs` for users on Claude Code v2.1.193+.

Historical `.ai-state` records — finalized ADRs, sentinel and eval reports, the resolved
tech-debt ledger, archived specs, and `observations.jsonl` — are **deliberately not rewritten**.
They are records of what was true when written; rewriting them to match the present is precisely
what the frozen-artifact convention forbids. Only the three live `.ai-state` artifacts
(`DESIGN.md`, `SYSTEM_DEPLOYMENT.md`, and the deployment diagram whose SVG is regenerated) change.

### Why this qualifies as `architectural`

Applying the falsifier in `rules/swe/adr-conventions.md` honestly: **no component is added,
removed, merged, or split, and no responsibility moves.** The inventory is byte-for-byte
identical on both sides — the same 17 agents, the same skills and commands, the same two MCP
servers. On the *internal* limb of the test this decision is not architectural, and it would be
inflation to claim otherwise.

It qualifies solely on the **published** limb — "it changes a canonical block, a shipped
template, or an onboard-contract phase" — and it changes two of those three:

- **Shipped templates.** `claude/aac-templates/architecture.yml.tmpl:170` carries the CI prompt
  `Load the i-am:architect-validator agent`; `claude/aac-templates/precommit-block-d.sh.frag:47`
  keys its plugin detection on the same identifier; `claude/config/CLAUDE.md.tmpl` carries the
  ambiguous "the `i-am` plugin ecosystem" sentence. All three are instantiated into managed
  projects.
- **Onboard-contract phases.** `/onboard-project` Phase 3 gates on
  `jq -r '.plugins["i-am@bit-agora"]'` (line 43) and skips Phase 4 when absent (line 46); Phase 4
  resolves `PLUGIN_ROOT` from the same key (line 431); the settings block it writes names
  `"plugin": "i-am@bit-agora"` (line 1276).
- **Canonical blocks are *not* affected** — verified: no occurrence of `i-am` in
  `claude/canonical-blocks/` at HEAD or in the working tree. Recording the negative matters, so a
  future reader does not assume the whole published surface moved.

The contract that changes is the identifier every consumer, downstream project and CI workflow
references.

## Considered Options

### (a) Rename the plugin to `praxion` — **chosen**

Fixes the cause once. Removes the referential ambiguity at its source, retires the internal
translation tax, and makes the identifier agree with every other surface of the project.

*Cost:* 66 tracked files outside `.ai-state` plus three live `.ai-state` artifacts; roughly a
dozen hard predicates; a permanent seam in the observation log; a migration step for users below
v2.1.193 and for any managed-settings deployment.

### (b) Keep `i-am` and disambiguate in prose where the collision bites

**Steelman.** This is genuinely the cheaper option and it carries *no* migration risk whatsoever
— no marketplace change, no `renames` map, no orphaned cache, no settings-key churn, no
observation-log seam, and none of the silent-failure class described below. Crucially, the
verified form of the collision supports it: because nothing shadows anything, no resolution is
broken today, so the entire benefit of (a) is *readability*. And readability is buyable far more
cheaply — the ambiguous always-loaded sentence occurs in a small number of places, principally
`claude/config/CLAUDE.md.tmpl`'s "This agent operates within the `i-am` plugin ecosystem". Editing
that one sentence to say "the Praxion plugin (`i-am@bit-agora`)" removes the ambiguity for every
downstream reader at a cost of one line and zero risk. On a strict cost-benefit reading of
today's evidence, (b) dominates. It was the orchestrator's first proposal, and it is not a
foolish one.

**Why it loses.** The ambiguity is not confined to prose that Praxion controls. The identifier is
the token users *type* (`claude plugin install i-am@bit-agora`), the key in their settings file,
the prefix on every agent and command reference, and a literal string inside shipped CI templates.
Prose cannot disambiguate any of those. An agent or reader that encounters `i-am:sentinel` cold —
in a CI log, a settings diff, a tool name — has no adjacent prose to consult. Worse, (b) is a
standing obligation rather than a fix: it must be re-applied at every new site, forever, by every
future author and every future agent, and it fails silently the first time someone forgets. That
is the definition of a workaround — it treats the symptom at N sites in perpetuity instead of the
cause once. It also leaves the internal translation tax (`_PRAXION_AGENT_PREFIX = "i-am:"`) fully
in place. Finally, the domain raises the cost of being wrong: the competing referent governs
credentials and an irreversible work/personal data boundary, which is the worst subject about
which to leave a standing ambiguity that depends on authorial discipline.

### (c) Rename the `.i-am` dotfiles project instead

**Steelman.** The dotfiles arguably hold the better claim to the name. Their subject *is* machine
identity — "what this machine is" — for which `i-am` is a semantically perfect name, whereas for a
development-workflow toolkit it is semantically arbitrary. In absolute terms it is also the
smaller job: one repository, one skill, one symlink, and no marketplace, no plugin cache, no
namespaced artifact references, and no downstream managed projects.

**Why it loses.** It resolves the collision in the wrong direction. Both projects have already
converged internally — Praxion on "Praxion" (repo, docs, `_PRAXION_*` constants,
`praxion.chronograph`, `/praxion-*` commands), the dotfiles on `i-am` (repo name, skill name,
`iam-doctor` on PATH, `~/.i-am/`). Renaming the dotfiles would manufacture a fresh mismatch to
retire an old one, and it would leave Praxion's own translation tax untouched. It is also outside
this decision's scope: a separate repository with its own users and its own release surface.

### (d) Do nothing

**Steelman.** No incident has been recorded. Both artifacts coexist without breakage. Effort is
finite and better spent on capability.

**Why it loses.** (d) is (b) minus even the mitigation: it retains both the ambiguity and the
translation tax, and every artifact added from here deepens the debt. "No recorded incident" is
also weak evidence for a failure mode whose signature is silent — an agent that consults the wrong
`i-am` and acts on guidance about credential boundaries emits no error, so absence of reports is
close to uninformative.

## Consequences

### Positive

- One name across the whole project. `i-am:sentinel` becomes `praxion:sentinel`; the identifier a
  user types matches the project they installed.
- The internal translation tax disappears: `_PRAXION_AGENT_PREFIX` and `_is_praxion_native` become
  self-consistent rather than self-documenting a mismatch.
- The always-loaded sentence shipped into every managed project stops having two referents, one of
  which is about secrets and data boundaries.
- Nothing is stranded: `~/.claude/plugins/data/i-am-bit-agora/` was verified empty, and the old
  cache directory is orphaned and reaped after roughly 14 days.

### Negative — migration burden on existing users

The `renames` map auto-migrates `enabledPlugins` and `pluginConfigs` on **v2.1.193+** with a
one-line notice. Everyone else migrates by hand:

- Users on Claude Code below v2.1.193.
- Any managed-settings (enterprise/policy) deployment, where `enabledPlugins` is not writable by
  the auto-migration.
- Anything that hardcodes the key outside settings — CI, dotfiles, scripts, documentation.

*Surfaced assumption:* the `renames`-map behaviour, its version floor, and its append-only
validation under `claude plugin validate` were **not** independently reproduced here; they are
carried from the decision brief. `claude plugin validate` exists on 2.1.224 and accepts a
`--strict` mode, which is the mechanism the append-only claim would be checked by, but the
`renames` key itself is undocumented in this repository. If that mechanic proves weaker than
stated, the manual-migration cohort is larger than assumed and the cost of (a) rises accordingly.

### Negative — a permanent seam in the observation log

`.ai-state/observations.jsonl` is a frozen historical record and is not rewritten. Its
`agent_type` field therefore changes value mid-file: today it holds 27 rows of
`i-am:test-engineer` and 6 of `i-am:systems-architect`; after the rename the same agents record
as `praxion:test-engineer` and `praxion:systems-architect`. **Any analysis grouping by
`agent_type` must accept both spellings.** (The field already requires care for an unrelated
reason — 12 rows carry a bare, unprefixed `claude-code-guide` — so consumers are not starting from
a clean invariant.)

### Negative — a silent-failure class

Roughly a dozen occurrences are **hard predicates**, not prose: `startswith("i-am:")`
(`hooks/inject_subagent_context.py:110`), the `_MCP_PRAXION_PREFIX = "mcp__plugin_i-am_"` constant
(`hooks/send_event.py:287`), cache-path segments, and the `PLUGIN_KEY='i-am@bit-agora'` shell
variable (`new_project.sh:59`). A missed one **fails silently**: an agent simply stops being
recognised as Praxion-native, with no error and no log line.

The mitigation must therefore assert the **negative**: a canary that the *old* prefix is no longer
recognised, not merely that the new one is. A test that only checks `praxion:` passes happily
while a stale `i-am:` predicate quietly stops matching.

### Negative — stale shipped templates in downstream managed projects (not covered by `renames`)

This consequence is **not** addressed by the `renames` map, and it is the least visible of the
four. The map migrates a user's `enabledPlugins`/`pluginConfigs`; it does not rewrite files
already committed to *other* repositories. Two shipped templates were instantiated into managed
projects by `/onboard-project` (Phase 8b) and `/new-project`, and both carry the old identifier in
a **fail-open** position:

1. `.github/workflows/architecture.yml`, rendered from `architecture.yml.tmpl`, contains the CI
   prompt `Load the i-am:architect-validator agent`. After the rename that agent name no longer
   resolves. Because the reference lives inside a free-text prompt to `claude-code-action` rather
   than in a validated field, nothing rejects it — the job can go green while the pre-merge
   architectural sweep never runs.
2. The Block D pre-commit fragment keys plugin detection on the old marketplace name and carries an
   explicit *"Skip-gracefully guard: if plugin root not found, exit 0 (non-blocking)"*
   (`precommit-block-d.sh.frag:45-47`). After the rename, detection fails, the guard fires, and the
   golden-rule gate silently stops enforcing behind one `info:` line and a zero exit code.

Verified: **neither `/upgrade-project` nor `/refresh-claude-blocks` re-renders these templates.**
`/refresh-claude-blocks` refreshes only `claude/canonical-blocks/`, which — as established above —
contains no occurrence of the identifier. So no shipped refresh path repairs either file today.

This is the same silent-failure class as above, relocated downstream, where the in-repo canary
cannot see it. It does not change the decision, but it enlarges its cost and adds a remediation
obligation: managed projects need an explicit re-render path (or a documented manual step) for
`architecture.yml` and the Block D fragment, and the release notes must say so.

## Disconfirmation

**Falsifier.** The decision is wrong if the rename's realised cost exceeds the ambiguity it
removes. Concretely, any of: (i) the `renames` map does not behave as documented — it fails to
migrate `enabledPlugins`, is rejected by `claude plugin validate`, or applies at a higher version
floor than v2.1.193 — pushing a material fraction of installs into manual migration; (ii) a
post-rename audit finds surviving `i-am` hard predicates in fail-open positions after the canary
was believed green, demonstrating the silent-failure class is not containable by testing; or (iii)
evidence emerges that the two names never actually confused a reader or an agent — for instance
the `.i-am` dotfiles skill is retired or renamed independently — in which case the collision
premise dissolves and the migration bought nothing.

**Steelmanned runner-up.** Option (b), keep `i-am` and disambiguate in prose, is the strongest
rival and is genuinely cheaper. Because the collision is referential rather than a hard namespace
clash — verified: `i-am` and `i-am:<artifact>` coexist with neither shadowing the other — nothing
is broken today, so the whole benefit of renaming is readability, and editing the handful of
always-loaded sentences buys most of that readability for zero migration risk, zero downstream
breakage, and no observation-log seam. It loses on durability rather than on cost: prose cannot
disambiguate the token users type, the settings key, the artifact prefix, or a string inside a
shipped CI template, and it converts a one-time fix into a standing obligation on every future
author. Had the collision been confined to documentation Praxion controls, (b) would be the
correct call.

**Reversal trigger.** Revisit if, within one release cycle of shipping the rename, either (i) the
migration generates support burden or breakage reports beyond the manual-migration cohort
anticipated here — particularly from managed-settings deployments or from the stale shipped
templates described above — or (ii) a `praxion`-namespace collision of comparable severity appears,
which would show that renaming buys only temporary relief and that the durable fix is
disambiguation discipline rather than identifier choice. Reversal is technically possible (rename
back, add a second `renames` entry) but is **not cheap**: it doubles the churn and cuts a second
seam in the observation log, so treat the trigger as a signal to invest in migration tooling first
and to reverse only on sustained evidence.
