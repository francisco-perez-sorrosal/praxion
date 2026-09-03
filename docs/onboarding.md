---
diataxis: how-to
audience: developer
---

# Project Onboarding

How to bring a project into the Praxion ecosystem — one command, one engine, four modes. `onboard-project` replaces the former two-path split (`new_project.sh` + `/new-project` for greenfield, `/onboard-project` for existing projects): detection now resolves the mode for you, so there is nothing left to choose between.

## Contents

- [What onboarding does](#what-onboarding-does)
- [Pick your entry](#pick-your-entry)
- [Quick start](#quick-start)
- [The phase list](#the-phase-list)
- [Modes in depth](#modes-in-depth)
- [Placement](#placement)
- [Hackathon → full promotion](#hackathon--full-promotion)
- [Re-running and upgrading](#re-running-and-upgrading)
- [Troubleshooting](#troubleshooting)
- [Limits](#limits)
- [Design decisions](#design-decisions)

## What onboarding does

One phase engine, parameterized by mode, installs a fixed end-state contract onto disk. Every write is idempotent — re-running the command on an already-onboarded project produces zero diff.

| Lands on disk | Why |
|---|---|
| `.gitignore` AI-assistants block | Excludes `.ai-work/`, lock files, `.env*`, `.claude/settings.local.json` from version control |
| `.ai-state/` skeleton (decisions, tech-debt ledger, calibration log, consult ledgers) | Persistent project intelligence — the durable memory the agent pipeline reads and writes |
| `.gitattributes` + `merge.observations-jsonl.driver` `git config` entry | Structural JSONL merge for `.ai-state/observations.jsonl` — prevents line-based merge corruption |
| `.git/hooks/{pre-commit,post-merge,post-commit,post-checkout}` | id-citation discipline gate + the finalize chain (ADR promotion, tech-debt dedupe, squash-safety warning) |
| `.claude/settings.json` toggles + `permissions.allow` baseline | Observability opt-in/out; the standing grant that keeps subagent `.ai-work/` writes from stalling on an unanswerable permission prompt |
| Four canonical `CLAUDE.md` blocks (Agent Pipeline, Compaction Guidance, Behavioral Contract, Praxion Process) + Project Essentials | The always-loaded context that makes every future Claude Code session Praxion-aware |
| *Opt-in*: architecture baseline, code-quality baseline, CI autofix, Architecture-as-Code tier, ML/AI conventions, Obsidian integration | Selected via the capability Profile (§Pick your entry) |

Nothing is ever committed. Every phase stages its own changes; you review and commit with `/co`.

## Pick your entry

You do not choose an entry point — `onboard-project` detects the directory's state and resolves exactly one of four modes. The 6 detected states collapse to 3 base modes plus `promote`:

| Detected state | Resolved mode | What happens |
|---|---|---|
| `empty` | `new` | Minimal scaffold (`git init`, `.gitignore`, empty `.claude/`), then hands off to the seed pipeline — builds an app from scratch |
| `code-no-git` | `existing` | `git init` offered as the first gated action, then the retrofit flow |
| `git-no-praxion` | `existing` | Retrofit flow — the common case for "I have a repo, make it Praxion-aware" |
| `partially-managed` | `existing` | Retrofit flow; already-present surfaces are skipped by their idempotency predicates |
| `fully-managed` | `existing` (no-op) | Re-run confirms everything is current and exits without launching Claude |
| `hackathon-managed` | `hackathon` (or `promote` with `--full` / `--mode promote`) | Minimal-ceremony flow, or the mechanical graduation path |

An explicit `--mode` overrides detection and fails fast (exit `2`) if it contradicts the detected state (for example, `--mode new` against a non-empty directory).

## Quick start

Two equivalent invocations, same as before the unification — only the binary name changed (`new-project` → `onboard-project`; `install.sh code` still symlinks the entry into `~/.local/bin/`):

```bash
# Create a new project
onboard-project my-app

# Onboard the project you're standing in (existing repo)
cd ~/dev/acme-api && onboard-project
```

Already in a Claude Code session inside a project? Invoke the skill directly:

```
/praxion:onboard-project
```

See what would change without writing anything:

```bash
onboard-project --check
```

## The phase list

Phase identifiers are preserved verbatim from the two prior surfaces — `0.5, 1–7, 5b, 6, 7, 8, 8b–8e, 9`, plus two new ids (`0s` greenfield seed, `5b.t` hackathon teardown). Everything user-facing speaks **capability IDs** instead; the mapping below is the single join point.

| Capability | Phases | Writes | Idempotency predicate | Runs in |
|---|---|---|---|---|
| `core` | `0.5, 1, 2, 3, 4, 6, 7, 9` | gitignore block, `.ai-state/` skeleton, gitattributes + merge driver, git hooks, CLAUDE.md blocks | Per-phase — see [`SKILL.md` §Idempotency Predicates](../skills/onboard-project/SKILL.md#idempotency-predicates--per-phase-contracts) | every mode, always on |
| `observability` | `5` | `.claude/settings.json` `env.PRAXION_DISABLE_OBSERVABILITY` | Key present, any value | every mode |
| `0s` (seed pipeline) | `0s` | the app itself — delegates to the full agent pipeline | n/a — implied by `new` mode | `new` only |
| `5b` / `5b.t` | `5b`, `5b.t` | six hackathon artifacts / their removal | `PRAXION_HACKATHON_MODE` key presence; teardown fires only under `promote` | `5b`: `hackathon`; `5b.t`: `promote` |
| `arch` | `8` | `.ai-state/DESIGN.md`, `docs/architecture.md` | Either file exists → skip | `new` (mechanically skipped — the seed pipeline already wrote them), `existing` (default-on) |
| `quality` | `8e.1`–`8e.7` | `.editorconfig`, pre-commit config, per-stack linter/formatter/type config, `CONTRIBUTING.md` | Per-sub-step file/config presence | `new`, `existing` (default = stack detected) |
| `ci` | `8e.8`, `8e.9` | CI-autofix + cross-model-review + label-reconcile callers | Per-sub-step | opt-in only (`--profile all` or explicit `--with ci`) |
| `aac` | `8b` | `fitness/` scaffold, golden-rule pre-commit block, `architecture.yml` workflow, `docs/diagrams/` | Per-sub-step | opt-in only |
| `ml` | `8c` | `program.md`, `.ai-state/experiments/`, checkpoint `.gitignore` block, `.ai-state/gpu_budget.yaml` | Per-sub-step; whole phase skipped if no ML signals and not selected | default-on when ML signals detected |
| `obsidian` | `8d` | Obsidian `.gitignore` block, `CLAUDE.md` block, `.obsidian/app.json` link-safety pins, `permissions.deny` entries | Per-sub-step; whole phase skipped if `claude` CLI or the marketplace plugin is absent | detection-gated |

Full per-phase detail (writes, predicates, sub-steps) lives in [`skills/onboard-project/references/phases-core.md`](../skills/onboard-project/references/phases-core.md) and [`phases-optional.md`](../skills/onboard-project/references/phases-optional.md) — this table is the navigation layer, not a restatement.

## Modes in depth

### `new` — empty directory

Runs the **seed pipeline** ([`references/seed-pipeline.md`](../skills/onboard-project/references/seed-pipeline.md)): the bash entry scaffolds `.git/`, the AI-assistants `.gitignore` block, and an empty `.claude/`, then hands off to a Claude Code session. That session asks one question (what to build — default is a mini coding agent with a web UI), runs the full Standard-tier agent pipeline (researcher → systems-architect → implementation-planner → implementer ∥ test-engineer → verifier), generates the default app (Python + `uv` + Claude Agent SDK + FastAPI), and produces a per-run `onboarding_for_mushi_busy_ppl.md` trail map.

The default app is prose-specified, not templated: the pipeline mandates an `external-api-docs` lookup of the current Claude Agent SDK and `uv` docs at run time, so generated code matches the SDK release on your machine — not a version baked into training data. Full rationale: [`dec-053`](../.ai-state/decisions/053-prompt-over-template-greenfield-scaffold.md).

**The `claude-desktop` editor caveat.** `--editor claude-desktop` (or `PRAXION_NEW_PROJECT_EDITOR=claude-desktop`) launches `Claude.app` and copies the project path to the clipboard. Anthropic ships no documented CLI flag or URL scheme to point the desktop app at a folder — so you click **Select folder** in the app and paste. macOS only.

**Illustrative end-to-end transcript** (actual output depends on the installed Claude Code version and the just-fetched SDK docs):

```text
$ onboard-project my-app
→ Scaffolded my-app at /Users/you/code/my-app. Launching Claude Code...

[Claude Code session starts]

Claude: What would you like to build? Press enter for the default
        (mini coding agent with web UI), or describe your own project.
> [enter]

Claude: Before I build, here's how this works:

        You don't call Praxion subagents by name. You write tasks in plain
        English, and Claude (the orchestrator) routes the work to specialists:
          • researcher — explores docs, libraries, external APIs
          • systems-architect — module shape, dependency direction
          • implementation-planner — decomposes into small steps
          • implementer + test-engineer — code + tests in parallel
          • verifier — checks acceptance criteria
        You speak English, Claude delegates. No /command memorization required.

Claude: [researcher] Fetching Claude Agent SDK + uv + FastAPI docs via context-hub ...
        [systems-architect] Module shape: src/agent/{core,tools,prompts}, src/web/{app},
          tests/. One-way dependency src/agent → src/web.
          → Wrote .ai-work/<slug>/SYSTEMS_PLAN.md, .ai-state/DESIGN.md,
            docs/architecture.md, and one ADR draft in .ai-state/decisions/drafts/
            for the dependency rule.
        [implementation-planner] 4 steps: (1) pyproject+env, (2) agent core+tools,
          (3) web app+static, (4) smoke test.
        [implementer ∥ test-engineer] Step 2: src/agent/*.py + tests/test_agent.py.
          [implementer ∥ test-engineer] Step 3: src/web/app.py + streaming assertions.
        [verifier] Layer isolation ✓ safe-list frozenset at module scope ✓ smoke green ✓.

Claude: Running test gate: uv sync && uv run pytest -q
        1 passed in 0.34s

Claude: Now running /init so CLAUDE.md reflects the actual codebase, then
        appending the Praxion canonical blocks and running the onboard-project
        skill for the remaining surfaces (git hooks, merge drivers, settings) ...

Claude: Generated onboarding_for_mushi_busy_ppl.md (trail map for busy people).
        Scaffold staged. Run /co to make the first commit (or /cop for commit+push).
```

### `existing` — retrofit

The default flow, and the common case: `.gitignore`, `.ai-state/`, `.gitattributes`/hooks, settings, `CLAUDE.md` blocks land on an already-populated repo, plus the architecture baseline (delegates to `systems-architect` in baseline-audit mode) and stack-detected quality tooling. Opt-in tiers you can add explicitly with `--with`:

```bash
onboard-project --with aac,ci --without obsidian
```

### `hackathon` — minimal, promotable

`onboard-project my-app --hackathon` (or `--mode hackathon` on an existing repo) installs the invariant `core` surfaces plus six hackathon artifacts, skipping every opt-in tier. See [Hackathon → full promotion](#hackathon--full-promotion).

## Placement

By default, `.ai-state/` is committed in your project repository — the normal case, and the only one on a repo you own outright. On a team repo you do not own alone, that same commit history broadcasts every ADR, tech-debt row, and pipeline artifact to every co-owner. **Placement** answers where Praxion's state lives without changing the path contract agents read and write: `.ai-state/DESIGN.md` still resolves, `CLAUDE.local.md` still loads, only *what owns the git history behind that path* moves.

`--placement sidecar` moves state ownership to a separate, per-operator git repository — the **sidecar** — while the project repo sees, at most, a plain doc you chose to share. `--placement in-repo` (the default) is unchanged from every example above this section.

### The state mount

Sidecar state is projected into each checkout as a real directory, not a plain symlink:

```
<checkout>/.praxion/                       REAL dir; git worktree of the sidecar, branch per checkout
    .ai-state/                             tracked in the sidecar
    CLAUDE.local.md                        tracked in the sidecar
    settings.local.json                    tracked in the sidecar
    .git                                   FILE: "gitdir: <sidecar>/.git/worktrees/<name>"
<checkout>/.ai-state                    -> .praxion/.ai-state                 (relative)
<checkout>/CLAUDE.local.md              -> .praxion/CLAUDE.local.md           (relative)
<checkout>/.claude/settings.local.json  -> ../.praxion/settings.local.json    (relative)
```

**Why a mount, not a plain symlink.** Claude Code's worktree isolation refuses a `Write`/`Edit` on any lexically-in-worktree path whose `realpath` escapes the worktree — a symlink from inside a linked pipeline worktree straight out to `~/.praxion/sidecars/...` is refused mid-step, not at session start, with a harness message that points at a copy that does not exist. The mount avoids the refusal structurally: `<checkout>/.praxion` is a `git worktree` of the sidecar **materialised inside the checkout**, so every shadow symlink resolves to a realpath still under the checkout. This is the **in-checkout realpath invariant** — for every path Praxion asks an agent to write, `realpath(path)` stays inside the checkout the session is running in — and it holds uniformly for the main checkout and for every linked worktree, with no discriminator between them. `worktree_guard.py`'s containment check and the dashboard's `project-root.ts` containment check both stay correct **without modification**, because the paths they see never leave the checkout to begin with.

The cost is a branch per checkout — the sidecar carries `main` for the main checkout and `wt/<name>` per linked worktree — and a merge step to bring a worktree's state home. That merge is a **convergence step**, not an ordering rule you must remember: three independent, idempotent channels can perform it (below), so skipping the explicit path costs latency, never correctness.

### Onboarding with `--placement sidecar`

**Mode rule.** `--placement sidecar` is legal only with mode `existing` — a `Sidecar` onboarding plan carries no mode field at all; it is structurally `existing`. `new` scaffolds a repo you just created and own; `hackathon` is a deliberately minimal, throwaway footprint; `promote` (hackathon → full) has no meaning without the in-repo hackathon artifacts sidecar placement would hide. Any other combination fails fast at exit `2`, naming the legal one.

**`--shadow` / `--share`** move a path between the sidecar (shadowed — symlinked, excluded, never committed in the project) and the project (shared — a real tracked file). The allowlist and defaults:

| Path | Default | Opt-out |
|---|---|---|
| `.ai-state/` | shadow | — (a sidecar without it is not a sidecar) |
| `CLAUDE.local.md`, `.claude/settings.local.json` | shadow | — |
| `CLAUDE.md` — repo already has one | untouched (Praxion blocks go to `CLAUDE.local.md` instead) | — (never touched, by construction) |
| `CLAUDE.md` — repo has none | shadow | `--share CLAUDE.md` |
| `docs/architecture.md` | share (a plain doc; cites ADRs by **id text**, never by `.ai-state/` path) | `--shadow docs/architecture.md` |
| `architecture/`, `fitness/` (AaC tier) | shadow, when the tier is selected | `--share architecture` |

Before any write, the confirmation block names the exact split:

```
Praxion onboarding · plugin 0.27.1

  Directory   /Users/me/work/billing
  Placement   sidecar

  Project intelligence will live OUTSIDE this repository, in
    ~/.praxion/sidecars/github.com--acme--billing

  Shadowed — symlinked in, excluded via .git/info/exclude, never committed here:
    .ai-state/                        the whole pipeline + decision record
    CLAUDE.local.md                   your Praxion instructions (loads last, wins)
    .claude/settings.local.json       your local Claude Code settings

  Shared — committed in this repository, visible to the team:
    docs/architecture.md              a plain architecture doc; cites ADRs by id
                                      text, never by .ai-state/ path

  Unavailable under sidecar placement:
    ci                                CI workflows are GitHub-visible by construction

  Your teammates see no Praxion files. Only the sidecar autocommits; commits in
  this repository stay yours.

Proceed? [y/N]
```

**The three `CLAUDE.md` cases**, decided once at `init` and immutable except through an explicit migration:

| Case | Precondition | Praxion block target | `CLAUDE.md` on disk |
|---|---|---|---|
| `untouched` | project already has a tracked `CLAUDE.md` | `CLAUDE.local.md` (shadowed) | untouched, tracked, byte-unchanged |
| `shadow` (default) | no `CLAUDE.md` exists | `CLAUDE.md` (shadowed) | symlink into the sidecar, excluded |
| `share` | no `CLAUDE.md`, `--share CLAUDE.md` passed | `CLAUDE.md` | real file, tracked, committed |

**Capability × placement.** Every `core` surface redirects into the sidecar (`.gitignore` → `.git/info/exclude`, `.gitattributes` + merge driver → the sidecar's own, `.claude/settings.json` → the shadowed `settings.local.json`). Beyond `core`:

| Class | Capabilities | Behavior |
|---|---|---|
| **local** | `core`, `observability`, `arch` (with `docs/architecture.md` shared by default), `aac`, `ml` | Every tracked artifact redirects into the sidecar; the project repo sees nothing new (or, for `arch`, exactly the one shared doc) |
| **share-gated** | `quality`, `obsidian` | These write ordinary tracked hygiene files (`.editorconfig`, `.pre-commit-config.yaml`, `.obsidian/app.json` pins). Never silent: the operator sees the exact file list and confirms, or declines and proposes them to the team as a normal PR |
| **unavailable** | `ci` | `.github/workflows/*` and friends are GitHub-visible by construction — there is no invisible variant. Refused with a one-line reason naming the local hook chain as the closest equivalent |

**What `git status` shows afterwards.** Nothing — and that is the point:

```console
$ git status --porcelain
$ git add -A
$ git add .ai-state/x
fatal: adding files failed
```

The last command fails loudly (`... is beyond a symbolic link`) rather than silently leaking a shadowed file into a commit.

### `praxion-sidecar`

```
praxion-sidecar <command> [options]

  init         Create the sidecar for this project, move state into it, link it back
  link         (Re)project the sidecar into this checkout — the idempotent repair verb
  status       Where project intelligence lives, and whether it is clean       [--json]
  doctor       Health checks with per-row verdicts and one-line fixes          [--json]
  commit       Commit the sidecar's working tree (called by the finalize chain + Stop hook)
  merge-back   Merge one worktree's state branch back, or converge them all
  publish      Move sidecar state into the project repo, history preserved
  absorb       Move committed project state out into the sidecar
  remote       Show or set the sidecar's git remote (trust-boundary gated)
```

One example per verb:

```console
$ praxion-sidecar status
  Placement   sidecar
  Sidecar     ~/.praxion/sidecars/github.com--acme--billing
              branch main · clean · 4 commits unpushed
  Healthy. State is shared live across 3 checkouts — no branch isolation.

$ praxion-sidecar doctor
  PASS  exclude-block         6 Praxion entries in .git/info/exclude
  FAIL  shadow:CLAUDE.md      a real file occupies the slot, not a symlink
        why   a `git pull` brought a committed CLAUDE.md into a shadowed slot
        fix   mv CLAUDE.md CLAUDE.md.team && praxion-sidecar link
  WARN  sidecar-repo          3 files uncommitted in the sidecar
        fix   praxion-sidecar commit
  1 failed · 1 warning · 6 passed.

$ praxion-sidecar init --share docs/architecture.md
$ praxion-sidecar link
Linked 2 surface(s) into /Users/me/work/billing/.claude/worktrees/auth-flow.
$ praxion-sidecar commit
Committed 3 file(s) to the sidecar (a1b2c3d) — chore(state): session 0e2bf758.
$ praxion-sidecar merge-back --auto
$ praxion-sidecar publish   # sidecar -> project repo, history preserved, --yes or TTY-confirmed
$ praxion-sidecar absorb    # project repo -> sidecar
$ praxion-sidecar remote git@github.com:acme/billing-praxion.git --push on-autocommit
```

**Exit codes.**

| Exit | Meaning |
|---|---|
| `0` | success, healthy, or nothing to do |
| `1` | actionable: `doctor` found drift, `--dry-run` found pending work, or an automatic `merge-back --auto` aborted a conflict |
| `2` | usage error |
| `3` | refused on safety grounds (the message always names the exact fix) |
| `4` | environment: not a git repo, no manifest, sidecar unreadable, git failed |

**When it refuses (exit 3, unless noted).** A real directory occupies the `.ai-state` slot at `init`. `.ai-state` symlinks to a *different* sidecar. `--shadow .claude` (Claude Code refuses a worktree when `.claude/` itself is a symlink — shadow the settings file instead). `remote` targets a host that differs from the project origin's host, without `--allow-foreign-host`. `--placement sidecar` in `hackathon`/`promote` mode. `publish`/`absorb` with a dirty project working tree. `init` when the sidecar root already belongs to a different origin. Usage errors (`2`) cover a `--shadow` path off the allowlist and a confirmation prompt with no TTY and no `--yes`.

### State convergence and merge-back

Each checkout — main and every linked worktree — carries its own sidecar branch (`main`, `wt/<name>`). A worktree's writes need to reach the base branch before ADR promotion sees its drafts.

**Positive evidence, not memory.** A branch is judged **eligible** to merge back only when its recorded project branch is provably merged — an ancestor test, or (for squash merges) a squashed-branch patch-identity test. A deleted project branch, a removed worktree, or a missing mapping is **not** evidence of a merge; each leaves the branch `UnmergedIneligible` with its own named reason. Nothing is ever dropped on absent evidence.

**Three idempotent channels**, none of them mandatory:

1. The project's own `post-merge` finalize chain — converges **before** draft promotion, so a manual `git merge` or a GitHub-merge-then-`git pull` promotes drafts in the same run.
2. SessionStart self-heal (`praxion-sidecar link`) — covers `git reset --hard origin/main`, which fires no hook at all.
3. `/merge-worktree` step 4.5, explicit (`praxion-sidecar merge-back --from wt/<name>`) — **preferred, not required**: earliest visibility, and the only form allowed to leave conflict markers for you to resolve, because an operator is present.

**On conflict.** An automatic channel (1 or 2) **aborts** the merge and exits `1`, naming the branch — the mount is never left mid-merge. Only the explicit verb (`merge-back --from`) may leave markers; it prints both the resolve and the abort commands.

**`doctor`'s convergence rows**, each with its exact fix:

| Id | Level | Condition | Fix |
|---|---|---|---|
| `state-unmerged` | WARN | a branch has unmerged commits and no positive evidence of a merge | `praxion-sidecar merge-back --from wt/<name>` |
| `state-eligible` | WARN | eligible but not yet converged | `praxion-sidecar link` |
| `mount-orphaned` | WARN | a sidecar worktree entry with no project checkout behind it | `praxion-sidecar link --prune` |
| `mount-conflict` | FAIL | a mount is left mid-merge | resolve then commit in the mount, or abort the merge in the mount |

A **new** linked worktree starts with no mount of its own; `post-checkout` materialises one on `git worktree add`, and the SessionStart heal is the backstop for any creation path that skips hooks.

### Autocommit and remotes

| Policy | Meaning |
|---|---|
| `autocommit: on-finalize-and-stop` (default) | The sidecar commits on the finalize chain and on the `Stop` hook |
| `autocommit: on-finalize` | Finalize-triggered commits only |
| `autocommit: manual` | Nothing autocommits; run `praxion-sidecar commit` yourself |

**No remote by default.** `praxion-sidecar remote` prints "No remote configured. Push policy: never." until you set one. Setting a remote on a host that differs from the project origin's is refused (`--allow-foreign-host` overrides it deliberately) — on a work machine, project intelligence must not leave the boundary the code already lives in.

**The project repo never autocommits.** The one exception, and the only commit `praxion-sidecar` ever makes in the *project* repository, is `publish`'s single history-preserving import merge — operator-confirmed, never automatic.

> [!WARNING]
> With no remote configured (the default), the sidecar's history exists only on the machine that created it. A lost or wiped laptop loses the project intelligence with it. Backing up the sidecar — a remote, a periodic copy, whatever fits your setup — is an **operator responsibility**; Praxion does not solve it for you.

### Reversibility

Nothing here is a one-way door. `publish` moves sidecar state into the project repo with history preserved; `absorb` moves it back out. `PRAXION_DISABLE_SIDECAR_BANNER=1` and `PRAXION_DISABLE_SIDECAR_AUTOCOMMIT=1` opt out of the SessionStart banner and the autocommit hook respectively. `praxion-sidecar link --prune` removes a stale mount entry after a worktree is gone.

### Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `doctor` reports `shadow:<path>` as `dangling` or `missing` | The symlink target moved or was never created in this checkout | `praxion-sidecar link` |
| `doctor` reports `shadow:<path>` as `blocked`/`foreign` | A real file or directory occupies a shadowed slot (e.g. `git pull` brought in a tracked `CLAUDE.md`) | move it aside, then `praxion-sidecar link` |
| `mount-conflict` FAIL | A mount was left mid-merge by the explicit `merge-back --from` | resolve then commit in the mount, or abort the merge in the mount — never a "rule was violated," an operator may legitimately be mid-resolution |
| Project directory moved or was re-cloned | `.ai-state` (or the mount) now points at a stale sidecar path | `rm .ai-state && praxion-sidecar link`, or `praxion-sidecar link --repair` if the mount itself is foreign |
| A worktree's `.ai-state` looks empty right after creation | `NotYetLinked` — the mount has not materialised yet | `post-checkout` or the next SessionStart heals it; run `praxion-sidecar link` to force it now |
| `praxion-sidecar` hooks silently do nothing on an older Python | The consumer hooks require **Python ≥3.9** | upgrade the interpreter git invokes hooks with |

---

## Hackathon → full promotion

Passing `--hackathon` writes six artifacts: `PRAXION_HACKATHON_MODE=1` in `.claude/settings.json`, the `## Hackathon Mode` `CLAUDE.md` block, the `.claude/praxion-rules.yaml` preset, and the launch trio `scripts/praxion-hackathon` + `.claude/hackathon-directive.md` + `.claude/hackathon-settings.json`.

**Worked example** — create, work through the wrapper, graduate out:

```bash
# 1 — Scaffold and seed a hackathon project
onboard-project url-shortener-poc --hackathon
```

```bash
# 2 — Work through the wrapper
cd url-shortener-poc
./scripts/praxion-hackathon
```

The wrapper launches Claude with the skill surface trimmed and the hackathon directive appended. You describe what you need in plain English, and the orchestrator enters the **Hackathon Spine** at the stage it infers:

| You say… | Spine enters at… |
|---|---|
| "Ideate a few options for link-expiry" | `promethean` |
| "I have the approach — plan and build the redirect endpoint" | `implementation-planner` |
| "Fix the off-by-one in the base62 encoder" | `implementer` |

The verifier still runs by default — say "skip verification" to opt out. The behavioral contract is never relaxed.

**3 — Graduate out mechanically** when the PoC becomes a real project:

```bash
onboard-project --full          # from inside the project
# or, before entering: onboard-project --mode promote
```

This is now a mechanical path, not a manual checklist. `--full` fires **Sub-step 5b.t** — enumerate-before-remove of all six hackathon artifacts (each template-compared and skipped-with-warning if you've diverged from it, never a blind delete) — then runs the full phase set (the opt-in Profile you select at G3), then flips the stamp's `mode` field to `"full"`. If you promoted a project by hand before this path existed, check for orphaned artifacts yourself: the old manual procedure named only three of the six (the settings.json flag, the CLAUDE.md block, and the rules preset) and silently left the launch trio behind.

```
$ cd ~/dev/hack-demo && onboard-project --full

Praxion onboarding · plugin 0.23.0
  Directory   ~/dev/hack-demo
  Praxion     hackathon mode, onboarded 2026-08-24 with 0.22.0
  Mode        promote — hackathon → fully managed

  - hackathon             removed all 6 hackathon artifacts (was: 3 documented, 3 orphaned)
  + arch                  .ai-state/DESIGN.md · docs/architecture.md
  + quality               .editorconfig · pre-commit · CONTRIBUTING.md

Promoted hack-demo to fully-managed Praxion 0.23.0.
```

## Re-running and upgrading

Every phase's write is gated by an idempotency predicate — re-running `onboard-project` on an already-onboarded project produces zero `git diff` and zero new `git config` entries. A clean re-run resolves "nothing to do" at the bash layer and **never launches a Claude session** — the biggest perceived-performance win over the old two-command flow, which walked every phase and gate to reach the same conclusion.

Use `onboard-project` again to **add** a capability you skipped (`onboard-project --with aac`) or to promote out of hackathon mode (`--full`).

Use `/upgrade-project` (wrapping `scripts/upgrade_project_pins.sh`) instead when the **plugin version changed** and you need the pinned surfaces re-pointed at the live install — finalize-hook symlinks, the merge-driver `git config` entry, the hub-SHA workflow callers, the `.github/labels.yml` baseline block, and the instantiated AaC surfaces (`architecture.yml` prompt + pre-commit Block D, including the structural repair of the broken pre-fix Block D resolution). A narrower, gate-free operation than a full re-run — and for the caller SHAs, labels baseline, and AaC surfaces it is the **only** refresh path, since a re-run's file-existence predicates skip them.

Use `/refresh-claude-blocks` when you only need the four refreshable `CLAUDE.md` canonical blocks brought current. After a plugin upgrade, the complete runbook is `/upgrade-project` (pins) followed by `/refresh-claude-blocks` (block content).

## Hook chaining

Phase 4's git hooks are installed and repaired by one deterministic reconciler, `scripts/install_git_hooks.py`, rather than by writing straight into `.git/hooks` and hoping nothing else is using it. It **observes** the repository's hook configuration first and installs the shape that *composes* with what it finds, instead of silently doing nothing or displacing an existing hook manager.

**Why this matters.** A repo managed by [husky](https://typicode.github.io/husky/) or [lefthook](https://github.com/evilmartians/lefthook) points git at its own hooks via `core.hooksPath` — a config value the pre-chaining installer never inspected, so Praxion's hooks silently never fired there. A repo using the [`pre-commit`](https://pre-commit.com/) framework occupies `.git/hooks/pre-commit` directly; the pre-chaining installer would back that file up and overwrite it, silently disabling the team's own gate. Both are now composed with, not fought:

- **`core.hooksPath` set to a directory Praxion does not own** (husky's `.husky/_`, lefthook's `.lefthook/`) — a Praxion *wrapper directory* is created inside the repository's **git common** directory (`git rev-parse --git-common-dir`; shared across all worktrees, never a linked worktree's own `.git`), the observed value is recorded as the delegate, and `core.hooksPath` is re-pointed at the wrapper. No tracked file is ever touched — the takeover is entirely local `.git/config` state, invisible to teammates' clones.
- **A hook slot is occupied by a non-Praxion script** (e.g., `pre-commit` framework's `.git/hooks/pre-commit`) — the occupant is preserved at `<name>.pre-praxion` and a chaining wrapper takes its place: the preserved hook runs **first**.
- **Per-hook-class exit-code policy.** For `pre-commit`, a non-zero delegate exit aborts the commit immediately with that exit code and Praxion's own gates do **not** run — the team's gate stays authoritative and its failure is never masked. For `post-merge` / `post-commit` / `post-checkout`, a non-zero delegate exit is reported on stderr and the chain continues, always exiting `0` — matching the finalize chain's existing non-blocking contract (a hook cannot abort an already-completed git operation).
- **`core.hooksPath` unset and every slot empty** — today's plain symlink (`post-*`) or the tailored inline pre-commit script, byte-identical to a pre-chaining install. Nothing changes for the majority of projects.
- **`core.hooksPath` set but unresolvable** (garbage value, not a directory) — refuses to install or heal, warns once naming the observed value, and changes nothing rather than guessing.

**Self-heal.** A package manager's `prepare` script (husky's on `npm install`, lefthook's `install`) can re-point `core.hooksPath` away from the wrapper without any Praxion code path running. A `SessionStart` hook (`hooks/heal_hook_chain.py`) detects this on every Claude Code session start and restores the chain, printing one line when it does. It fast-exits on a handful of pure filesystem reads (no subprocess) for the overwhelming majority of sessions that never installed a wrapper directory at all, and never invokes `install_git_hooks.py --heal` (its one possible subprocess call) unless the wrapper directory is confirmed present. Opt out with `PRAXION_DISABLE_HOOK_CHAIN_HEAL=1`. Repeated heals converge — `core.hooksPath` never oscillates, and the recorded delegate is never the wrapper directory itself (the non-ping-pong invariant: a wrapper can never delegate to itself).

**Diagnosing and reversing.**

```console
$ python3 <plugin-root>/scripts/install_git_hooks.py --status --repo-root .
core.hooksPath: Foreign
  delegate: .husky/_
  pre-commit: PraxionWrapperFile [ok]
  post-merge: PraxionWrapperFile [ok]
  post-commit: PraxionWrapperFile [ok]
  post-checkout: PraxionWrapperFile [ok]
```

`--status` reports the observed `core.hooksPath` state, the delegate, per-slot ownership, and names any slot where Praxion's hooks currently cannot fire — the diagnosis path for a silently-inert install without reading `.git/` by hand. `--uninstall` restores the recorded pre-Praxion `core.hooksPath` (or unsets it if none was recorded) and re-installs each delegate hook in its original slot from its `.pre-praxion` backup where one exists — full reversibility, no manual `.git/config` surgery required. Exit codes: `0` ok, `1` actionable (`--status` found a slot that cannot fire), `2` usage, `3` refused, `4` environment (not a git repository).

## Troubleshooting

The bash layer uses distinct exit codes for each failure so you can diagnose without reading the source:

| Exit | Symptom | Cause | Fix |
|---|---|---|---|
| `2` | "Usage error: ..." on stderr | Missing/invalid argument, invalid project name, or `--mode` contradicts the detected state | Check the flag or project-name regex (`^[A-Za-z0-9][A-Za-z0-9._-]*$`); run `onboard-project --help` |
| `3` | "Claude Code CLI not found on PATH" | Claude Code is not installed | `npm install -g @anthropic-ai/claude-code`, then re-run |
| `4` | "the 'praxion' plugin is not installed" | `~/.claude/plugins/installed_plugins.json` has no `praxion@bit-agora` entry | `/plugin marketplace add bit-agora/praxion` then `/plugin install praxion`, or `./install.sh code` from a Praxion checkout |
| `5` | "'git' not found in PATH" | git is not installed | Install git (`brew install git`, `apt install git`, ...) |
| `6` | "already exists and is not empty" | `<target-dir>/<project-name>` is a non-empty path | Pick a different name/target, or `cd` into it and run `onboard-project` with no positional |
| `7` | "Refusing to onboard: this is a Praxion plugin source repository" | `.claude-plugin/plugin.json` exists at the target and `PRAXION_ALLOW_SELF_ONBOARD` is unset | Intentional dogfooding? Re-run with `PRAXION_ALLOW_SELF_ONBOARD=1 onboard-project` |
| `8` | (only with `--check`) "Pending: ... needs work" | `--check` found drift or an incomplete onboard | Run `onboard-project` (no `--check`) to apply, or `--check --json` for machine output |

**Two Claude-side failure modes** the bash layer cannot detect:

| Symptom | Cause | Fix |
|---|---|---|
| Claude session starts but the `onboard-project` skill never fires | Plugin registered but skill files are not linked into the active config | Re-run `./install.sh --relink code` to refresh plugin links |
| The launcher's detected state and the skill's own Phase 0 re-detection disagree | Directory state changed between the bash launcher running and the Claude session starting (rare — e.g., a concurrent `git init`) | Not an error: Phase 0 always re-runs the same predicates and uses its own result when it disagrees, printing why. If the result still looks wrong, re-run `onboard-project` from a clean state |

Also refusable at the shape-guard boundary: `onboard-project` on a `git-no-praxion` state that looks like a freshly-scaffolded-but-abandoned greenfield project (empty `.claude/`, AI-assistants `.gitignore`, no source tree) is refused with a pointer to run `onboard-project <project-name> <target-dir>` instead — running the seed pipeline over what looks like an empty scaffold, rather than silently treating it as "existing."

## Limits

- **Claude Code CLI only** as the pipeline-driving surface. Running the seed pipeline inside Cursor's AI assistant or Claude Desktop's chat is not supported — the bash entry `exec`s a `claude` CLI process. (The *editor* that opens to view files while the pipeline runs is independent — `--editor` covers Cursor, VS Code, and Claude.app.)
- **Default app is Python only** (`uv` + `claude-agent-sdk` + FastAPI). No JS/TS or other-language variant in the default branch.
- **Custom-app branch tailors only L1 + L2** of the seed pipeline's lesson ladder; L3–L7 stay generic Praxion-ecosystem lessons.
- **The bash integration test (`tests/onboard_project_test.sh`) is single-file**, run manually — not yet wired into CI.
- **Plugin install check is user-scope only.** Project-scope plugin installs are also detected, but the bash layer's own prereq check only reads the user-scope registry path.

## Design decisions

- [`dec-053`](../.ai-state/decisions/053-prompt-over-template-greenfield-scaffold.md) — prompt-over-template discipline for the seed pipeline's default app.
- [`dec-054`](../.ai-state/decisions/054-separate-new-cc-project-from-install.md) — separating project scaffolding from plugin installation.
- [`dec-055`](../.ai-state/decisions/055-hybrid-bash-slash-command-orchestration.md) — hybrid bash + Claude-session orchestration (deterministic prereqs in bash, conversational flow in Claude).
- `dec-340` — unifying the two onboarding commands into one user-invocable skill plus one entry script.
- `dec-342` — preserving onboarding phase identifiers verbatim across the migration.
- `dec-343` — one idempotency mechanism and one embedding site for the seven canonical `CLAUDE.md` blocks.
- `dec-341` — persisting the onboarding mode in the onboard stamp and making hackathon promotion mechanical.

(The four `dec-draft-*` ids above finalize to `dec-NNN` records under `.ai-state/decisions/` at merge-to-main; look them up by title in [`DECISIONS_INDEX.md`](../.ai-state/decisions/DECISIONS_INDEX.md) once finalized.)
