# Praxion Onboarding — CLAUDE.md Canonical Blocks

The 8 canonical `CLAUDE.md` block bodies installed by `skills/onboard-project/SKILL.md` and its phase files. Source of truth for `scripts/sync_canonical_blocks.py`.

## §Agent Pipeline Block

<!-- canonical-source: claude/canonical-blocks/agent-pipeline.md — edit the canonical file, then run: python3 scripts/sync_canonical_blocks.py --write -->

```markdown
## Agent Pipeline

This project follows Praxion's tier-driven agent pipeline (Direct → Lightweight → Standard → Full, plus exploratory Spike) under the **Understand, Plan, Verify** methodology. Ephemeral pipeline artifacts live in `.ai-work/<task-slug>/` (deleted after use); permanent decisions and design docs live in `.ai-state/` (committed to git).

When Praxion's assistant tooling is active, its agent coordination protocol rule and `software-planning` skill carry the full agent roster, delegation checklists, and pipeline-branch handling. Always include expected deliverables when delegating to an agent.

Human-readable process overview: [Praxion documentation](https://github.com/francisco-perez-sorrosal/praxion#readme).
```

The block is **self-contained** — no cross-references to files that exist only in the Praxion repo. The previous version pointed at `docs/getting-started.md#journey-poc-to-production`, which dangled in every onboarded project.

## §Compaction Guidance Block

<!-- canonical-source: claude/canonical-blocks/compaction-guidance.md — edit the canonical file, then run: python3 scripts/sync_canonical_blocks.py --write -->

```markdown
## Compaction Guidance

When this conversation compacts, always preserve: the active pipeline stage and task slug, the current WIP step number and status, acceptance criteria from the systems plan, and the list of files modified in the current step. The Praxion `PreCompact` hook snapshots in-flight pipeline documents to `.ai-work/PIPELINE_STATE.md` (one consolidated snapshot at the `.ai-work/` root, with a per-task-slug section for each active pipeline) — re-read that file after compaction to restore orientation.
```

## §Behavioral Contract Block

<!-- canonical-source: claude/canonical-blocks/behavioral-contract.md — edit the canonical file, then run: python3 scripts/sync_canonical_blocks.py --write -->

```markdown
## Behavioral Contract

Four non-negotiable behaviors for any agent (including Claude itself) writing, planning, or reviewing code:

- **Surface Assumptions** — state your interpretation up front and surface gap-filling assumptions as you make them; a plausible default never *feels* like ambiguity. Pause when one is load-bearing and hard to reverse.
- **Register Objection** — when a request violates scope, structure, or evidence, state the conflict with a reason before complying or declining.
- **Stay Surgical** — touch only what the change requires; if scope grew, stop and re-scope instead of expanding silently.
- **Simplicity First** — prefer the smallest solution that meets the behavior; every line, file, or dependency must earn its place.

Self-test: did I state my assumptions, flag conflicts with reasons, stay in scope, and pick the simplest path?
```

## §Praxion Process Block

<!-- canonical-source: claude/canonical-blocks/praxion-process.md — edit the canonical file, then run: python3 scripts/sync_canonical_blocks.py --write -->

```markdown
## Praxion Process

Apply Praxion's tier-driven pipeline for non-trivial work. Use the tier selector from `rules/swe/swe-agent-coordination-protocol.md`: Direct (single-file fix/typo) or Lightweight (2–3 files) may skip the full pipeline; Standard or Full tier work requires researcher → systems-architect → implementation-planner → implementer + test-engineer → verifier.

**Rule-inheritance corollary.** When delegating to any subagent — Praxion-native or host-native (Explore, Plan, general-purpose) — carry the behavioral contract into every delegation prompt. Host-native subagents do not load CLAUDE.md; the orchestrator is the only delivery path.

**Orchestrator obligation.** Every delegation prompt must name the task slug, expected deliverables, and the behavioral contract (Surface Assumptions · Register Objection · Stay Surgical · Simplicity First).
```

## §Hackathon Mode Block

<!-- canonical-source: claude/canonical-blocks/hackathon-mode.md — edit the canonical file, then run: python3 scripts/sync_canonical_blocks.py --write -->

```markdown
## Hackathon Mode

This project is in **hackathon mode** (`PRAXION_HACKATHON_MODE=1` in `.claude/settings.json`).
The mode applies to every agent and command in this project until the env var is removed
and this block is deleted (see "To exit" below).

### Process — the Hackathon Spine

In hackathon mode the 5-tier selector (Direct/Lightweight/Standard/Full/Spike) is REPLACED
by the **Hackathon Spine** — a pipeline you ENTER, MOVE AROUND IN, and EXIT. The spine has
a fixed ORDER but not a fixed MEMBERSHIP:

    promethean → researcher → systems-architect → implementation-planner
      → (implementer ∥ test-engineer) → verifier

**Entry by natural language.** You declare where to start in plain language; the main
agent infers the entry point:
- "ideate / explore options for X"          → enter at promethean
- "research how X works"                    → enter at researcher
- "design X / work out the approach"        → enter at systems-architect
- "I have the approach — plan and build X"  → enter at implementation-planner
- "fix this typo / implement X exactly so"  → enter at implementer

Everything UPSTREAM of the entry point is SKIPPED — including systems-architect and
implementation-planner. There is no separate "Direct" path: a trivial fix is just
"enter at implementer."

**Ambiguous entry → the main agent ASKS.** If your prompt does not make the entry point
clear, the main agent asks one short question ("start from ideation, or go straight to
planning/implementation?") — it does not silently pick a default.

**Free mid-task movement.** At any point you may move the work to a different stage
("go back and research this properly," "this needs a real design — move it to the
architect," "skip ahead and just build it"). User-driven movement is unbounded — it is
your call. The orchestrator re-routes and records the movement in PROGRESS.md.

**Worktree policy by entry point.** The spine maps entry points onto Praxion's existing
worktree isolation rule: entering at `promethean`, `researcher`, or `systems-architect`
→ the main agent creates a worktree (`EnterWorktree`) before spawning any agent (same as
a Standard/Full pipeline). Entering at `implementation-planner` or `implementer` → the
user decides; on-the-fly, no-worktree work in the current checkout is allowed (mirrors
Direct/Lightweight). If mid-task movement crosses into a worktree-requiring stage, the
orchestrator creates the worktree at that transition and records it in PROGRESS.md.

**Creative-blocker signal.** If an agent hits a genuine design dead-end (the current
approach is exhausted and fresh ideation is needed — NOT "this is hard," NOT "I need more
research"), it appends a `CREATIVE-BLOCKER: <desc> #blocker` line to
`.ai-work/<slug>/PROGRESS.md`, STOPS at that stage, and surfaces it to you. YOU decide
whether to move the work back to ideation. The agent does not auto-loop.

To run a single task at full 5-tier ceremony instead, say so explicitly; that one task
yields back to the normal selector.

### The verifier — default-on, skippable

The verifier runs by DEFAULT as the implementation harness, whatever entry point you
chose. It is skippable ONLY if you explicitly say so ("skip verification on this one").
When the verifier is skipped, the main agent tells you at task end exactly what process
was (not) applied.

### Skipping the architect — the main agent may HOLD

When you direct "just implement X" (entry at implementer, skipping the architect and
planner), the main agent complies — UNLESS it has a genuinely strong, well-founded reason
to believe skipping design is a real mistake. It HOLDS and asks you only when the task:
- touches a SECURITY-SENSITIVE surface (auth, authorization, secrets, trust-boundary input);
- carries DATA-LOSS RISK (schema migration, destructive data operation);
- is VISIBLY FAR BEYOND your framing (many files / multiple subsystems / cross-cutting
  structural change that no incremental step can absorb).
For minor or speculative doubts, it complies silently. The bar to hold is "a really good
motive," not "a doubt."

### Skipped rigor is recorded — the safety net is transparency

Because you can skip the architect, the planner, and the verifier, and move freely
mid-task, the safety net is that NONE of it is invisible:
- Every skipped stage is recorded in PROGRESS.md and in the VERIFICATION_REPORT.md header
  (or, if the verifier was skipped, a one-line terminal note at task end).
- Every mid-task movement is recorded in PROGRESS.md.
A reviewer or a graduation audit can always reconstruct exactly what process was applied
to any change.

### Discovery is full-strength — only delivery ceremony is relaxed

When promethean and researcher run, they run at FULL depth: unbounded internet research,
multi-source synthesis, idea ledgers. External web research via `WebSearch`/`WebFetch` is
unbounded — those are TOOLS, unaffected by `--disable-slash-commands`. A wrapper-launched
researcher loses skill auto-trigger only — invoke `/external-api-docs` explicitly for
curated API docs; raw web access is always available. The relaxation below applies ONLY
to the delivery ceremony, NEVER to discovery.

### The Behavioral Contract still applies — in every mode

Hackathon mode is NOT license to skip the four-behavior contract. Every agent that
writes, plans, or reviews code still honors:
- **Surface Assumptions** — list assumptions before acting; ask when ambiguity could
  produce the wrong artifact.
- **Register Objection** — when a request violates scope, structure, or evidence, state
  the conflict with a reason before complying or declining. Silent agreement is a violation.
- **Stay Surgical** — touch only what the change requires; re-scope rather than silently expand.
- **Simplicity First** — prefer the smallest solution that meets the behavior.
The architect's Surface Assumptions and Registered Objections sections are MANDATORY
even in the slim SYSTEMS_PLAN shape.

### Launching for full context trimming

Start sessions with the `praxion-hackathon` wrapper (`scripts/praxion-hackathon`). It
adds `--disable-slash-commands` (skills resolve only via explicit `/name`) and
`--effort low`. A plain `claude` launch still gets hackathon mode (env var + this block)
but NOT the skill-surface token trim. To resume, use `praxion-hackathon --resume`.

### SDD ceremony — OFF by default

- Do NOT add a `## Behavioral Specification` section to `SYSTEMS_PLAN.md`.
- Do NOT initialize `traceability.yml`.
- Do NOT archive specs to `.ai-state/specs/` at end-of-feature.
- Acceptance Criteria stays — write 3-7 testable AC bullets, no REQ IDs. If the architect
  was skipped, the planner emits light ACs; if the planner was also skipped, the verifier
  derives what to check from the diff.

### ADR ceremony — deferred by default

- Do NOT auto-write ADR fragments under `.ai-state/decisions/drafts/`.
- IF the user explicitly says "write an ADR for X" — use the direct-tier path
  (`.ai-state/decisions/<NNN>-<slug>.md`, no fragment, no draft lifecycle).
- The `remind_adr.py` hook's advisory warning is silenced; its check still runs.

### Test discipline — RELAXED

- Implementer writes production code AND a happy-path smoke test in the same step.
- test-engineer is invoked only on explicit request (property/contract/integration suites).
- Tests still run; `pytest` failures still surface honestly — but a red test is a WARN,
  not a FAIL, and does NOT gate the verifier or the pipeline. A happy-path smoke test is
  still expected; its ABSENCE for new behavior is also a WARN.

### Slim artifact shapes

- **Architect (`SYSTEMS_PLAN.md`):** Surface Assumptions, Registered Objections, Goals &
  Non-Goals, Context (1 para), Architecture (Overview, Components, Data Flow if
  non-trivial), Acceptance Criteria, Risks (top 3), Out-of-scope. Skip: Behavioral
  Specification, ADR fragment, tech-debt sweep, Tier-2 Stakeholder Review, DESIGN.md /
  docs/architecture.md updates.
- **Planner (`IMPLEMENTATION_PLAN.md`):** numbered steps + file paths + per-step
  acceptance. WIP.md and LEARNINGS.md still produced. No traceability.yml, no REQ IDs,
  no paired test-engineer step required. Coarser decomposition (3-5 steps for 4-8 files
  is fine). If the architect was skipped, add a short top-level "what 'done' means" list.
- **Verifier (`VERIFICATION_REPORT.md`):** Phases 1, 2, 3 (AC), 5 (lint/typecheck),
  5.5 (Behavioral Contract), 10 (test status), 12 (report). Auto-skip 4, 7, 8, 9, 11.
  FAIL: lint/typecheck/behavioral-contract failure. WARN (not FAIL): a failing or
  absent test. The report header records the entry point and the skipped stages.

### To exit hackathon mode

Set `PRAXION_HACKATHON_MODE=0`, delete this `## Hackathon Mode` block from `CLAUDE.md`,
remove the `hackathon` preset from `.claude/praxion-rules.yaml`, and stop launching via
the `praxion-hackathon` wrapper. Subsequent sessions resume the full 5-tier process.
```

This block is installed into the user project's `CLAUDE.md` by Phase 5b **only when hackathon mode is enabled**. It is guarded by `grep -q '^## Hackathon Mode$' CLAUDE.md` (Phase 5b artifact 2 predicate). When installed, it activates the Hackathon Spine in the project's agent sessions. The fence is kept byte-identical to `claude/canonical-blocks/hackathon-mode.md` by `scripts/sync_canonical_blocks.py`.

## §Project Essentials Block

<!-- canonical-source: claude/canonical-blocks/project-essentials.md — edit the canonical file, then run: python3 scripts/sync_canonical_blocks.py --write -->

```markdown
## Working in this project

This `CLAUDE.md` is the **index**; `docs/` and the skills it points to are the **library** — read the index, follow the links the task needs. When I correct you, propose a durable rule for review (a `CLAUDE.md` or rule edit, or a skill note) so the correction outlasts this session.

### Verification

After every change, run these in order — fix at each step before moving on:

1. `<typecheck command>`
2. `<test command>`
3. `<lint command>`
4. `<build command>`

### Frequent operations

You'll most often be asked to:

- `<list 3–5 of this project's most common task intents>`
```

The fenced content above is a **template** — Phase 6 appends it and then fills the `<placeholders>` from the project's config (see §Phase 6 Action step 3); in `new` mode the seed pipeline fills them at scaffold time. The fence is kept byte-identical to `claude/canonical-blocks/project-essentials.md` by `scripts/sync_canonical_blocks.py`; the `<placeholders>` are intentional and must survive the sync.

## §Obsidian Integration Block

<!-- canonical-source: claude/canonical-blocks/obsidian-integration.md — edit the canonical file, then run: python3 scripts/sync_canonical_blocks.py --write -->

```markdown
## Obsidian Integration

This project is configured for **Obsidian integration**: the vault lives inside the project repository, and the agent has access to kepano/obsidian-skills for vault navigation and note manipulation. Kepano skills are discovered automatically once `obsidian@obsidian-skills` is installed at user scope. If the plugin is absent from a session, run `./install.sh code` in your Praxion checkout first.

### CLI Allowlist

The `obsidian` CLI is available for file CRUD, search, link analysis, properties, tags, outline, structured queries (`base:query`), templates, and read-only sync/publish diagnostics.

**Allowed subcommands include:** `read`, `create`, `append`, `prepend`, `delete` (without `--permanent`), `search`, `search:context`, `backlinks`, `links`, `unresolved`, `orphans`, `deadends`, `outline`, `tags`, `tag`, `properties`, `base:query`, `daily`, `daily:read`, `daily:append`, `template:read`, `template:insert`, `unique`, `publish:list`, `publish:status`, `sync:status`, `sync:history`, `sync:read`.

**Denied subcommands — blocked at the tool-permission layer:**

| Subcommand | Reason |
|---|---|
| `obsidian eval` (any args) | Executes arbitrary JavaScript in the renderer — remote code execution risk |
| `obsidian plugin:install`, `plugin:enable`, `plugin:disable`, `plugin:uninstall` | Plugin lifecycle commands expose OS-level attack surface |
| `obsidian theme:set`, `theme:install` | Theme code runs with full app privileges |
| `obsidian delete --permanent` | Bypasses Obsidian's trash; operation is unrecoverable |
| `obsidian move`, `rename` | Renaming/moving a tracked file through Obsidian can rewrite link bodies across the repo and hides the rename from git. Use `git mv` so git tracks the rename and project link conventions stay intact. |

**Why you may see permission errors:** The denied subcommands above are enforced mechanically via `.claude/settings.json` `permissions.deny` rules written by the onboarding step. If a `Bash(obsidian ...)` call is rejected by the harness, check this list — the subcommand is intentionally blocked, not broken. Use an allowed alternative or ask the user to perform the operation manually.

### Link safety

Because the repository doubles as a vault, Obsidian's default link behavior is pinned so vault tooling cannot corrupt project-artifact links (standard Markdown `[text](path)` links and ADR id cross-references). The onboarding step writes two keys into `.obsidian/app.json` (merged non-destructively, committed so every clone inherits them):

- `useMarkdownLinks: true` — any link Obsidian authors uses Markdown `[text](path)` form, never `[[wikilink]]` (which Praxion's docs and cross-reference validators do not use).
- `alwaysUpdateLinks: false` — Obsidian never auto-rewrites links across files when a file is renamed or moved.

This is why `move`/`rename` are denied above: file renames go through `git mv`, so git tracks them and no link bodies are silently rewritten.

### Opt-out

Obsidian integration can be skipped with `onboard-project --without obsidian` (the legacy `--no-obsidian` flag is accepted for one release with a deprecation warning). To retrofit integration later, re-run `onboard-project --with obsidian` — Phase 8d is idempotent.

### Reference

See `docs/obsidian-integration.md` for installation, configuration, troubleshooting, and the full allowlist rationale.
```

This block is installed into the user project's `CLAUDE.md` by Phase 8d sub-step 8d.5. It is guarded by `grep -q '^## Obsidian Integration$' CLAUDE.md`. The fence is kept byte-identical to `claude/canonical-blocks/obsidian-integration.md` by `scripts/sync_canonical_blocks.py`.

## §Sidecar Placement Block

<!-- canonical-source: claude/canonical-blocks/sidecar-placement.md — edit the canonical file, then run: python3 scripts/sync_canonical_blocks.py --write -->

```markdown
## Praxion Sidecar Placement

This project onboarded with `--placement sidecar`: Praxion's project intelligence lives
**outside** this repository, in a separate git-tracked sidecar repository at
`~/.praxion/sidecars/<sidecar-id>`. The state mount at `<project>/.praxion-state` is a real
`git worktree` of that sidecar; `.ai-state/`, this file, and `.claude/settings.local.json`
are symlinks into it, excluded via `.git/info/exclude` — **your commits in this repository
never include Praxion state**.

`docs/architecture.md`, when shared, cites ADRs by **id text** (e.g. `dec-NNN`), never by
an `.ai-state/` path — a path reference would dangle for anyone without sidecar access.

`.ai-state/` (a directory shadow) accepts a direct `Write`/`Edit`; `CLAUDE.local.md`, a shadowed
`CLAUDE.md`, and `.claude/settings.local.json` (file shadows) load through their links but refuse
a direct tool write — edit those three at their mount path instead (`.praxion-state/<name>`).

Run `praxion-sidecar doctor` to confirm the mount and shadow projection are intact. See
`docs/onboarding.md#placement` for the full placement model.
```

This block is a **conditional, placeholder-filled** block (like Hackathon Mode and Project Essentials, never a `REFRESHABLE_SLUGS` member) — installed into the shadowed `CLAUDE.local.md` (the `untouched`/`shadow` placement cases) or a shared `CLAUDE.md` (the `share` case) by §Phase 6, only under `--placement sidecar`, with `<sidecar-id>` filled from the manifest's `project.id`. It is guarded by `grep -q '^## Praxion Sidecar Placement$'` against whichever file §Phase 6's placement lookup resolved. The fence is kept byte-identical to `claude/canonical-blocks/sidecar-placement.md` by `scripts/sync_canonical_blocks.py`; the `<sidecar-id>` placeholder is intentional and must survive the sync.
