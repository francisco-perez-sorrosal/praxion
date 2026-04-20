---
description: Scaffold a greenfield Claude-ready Python project and onboard it to Praxion.
allowed-tools: [Bash, Read, Write, Edit, Glob, Grep, AskUserQuestion, Task, mcp__chub__*]
---

Onboard the current (freshly scaffolded) directory. Ask one question first, show the user *how* Praxion is driven (orchestrator + subagents), frame the build as a pipeline task so they watch the orchestrator in action, then — once the codebase exists — run `/init`, append the Agent Pipeline block, generate a per-run trail map, and hand off to `/co`.

## Sections

1. §Guard — shape check before doing anything
2. §Flow — the sequential recipe this command executes
3. §Phase Gates — `AskUserQuestion` pause points between phases, with escape hatch
4. §What is Praxion — canonical paragraph (sentinel-fenced, copied verbatim by the mushi doc)
5. §How Claude drives Praxion — orchestrator preamble (sentinel-fenced; also mirrored into the mushi doc)
6. §Default App — Pipeline Framing — literal task issued for the default build, shown to the user before execution
7. §Custom App — Pipeline Framing — how the same shape adapts when the user describes their own app
8. §Default App Spec — file inventory + invariants the pipeline must satisfy
9. §SDK smoke check — the import probe and doc-staleness recovery
10. §Init idempotency — predicate for appending the Agent Pipeline block
11. §Mushi Doc Spec — the eight ordered sections
12. §Five-to-Seven Lessons — L1–L7 "Put this in Claude" canonical ladder
13. §Prereq Behaviors — `uv` missing, `ANTHROPIC_API_KEY` unset
14. §Agent Pipeline Block — verbatim source

## §Guard

Before anything else, verify the filesystem shape. The bash layer is supposed to have left a scaffolded-but-empty directory — if any of these checks fail, print the guarded-abort message and stop.

Run these four checks from the project root:

1. `test -d .git` — the directory is a git repo.
2. `grep -q '^# AI assistants$' .gitignore && grep -q '^\.ai-work/$' .gitignore` — the AI-assistants block is present.
3. `test -d .claude && [ -z "$(ls -A .claude 2>/dev/null)" ]` — `.claude/` exists and is empty.
4. `! test -e src || [ -z "$(ls -A src 2>/dev/null)" ]` — `src/` is absent, or is an empty directory.

If any check fails, abort with:

> This directory doesn't look like a freshly-scaffolded Praxion greenfield project. `/new-cc-project` expects to run inside a directory produced by `new_cc_project.sh` (a `.git/` repo with the AI-assistants `.gitignore` block, an empty `.claude/`, and no `src/` tree yet). If you meant to onboard an existing project, run `/onboard-project` instead.

Exit without writing anything.

## §Flow

When the guard passes, follow these steps in order. Each step is a contract — tactics are your call, but the shape is fixed.

**Phase gates.** The thirteen steps below group into eight phases (Phase 1 = step 1; Phase 2 = step 2; Phase 3 = steps 3–4; Phase 4 = step 5, decomposed into sub-steps 5a–5e for the per-subagent previews; Phase 5 = steps 6–8; Phase 6 = steps 9–10; Phase 7 = step 11; Phase 8 = steps 12–13). **Between phases**, fire the `AskUserQuestion` gates defined in §Phase Gates so the user sees and acknowledges each phase before it runs. **Within Phase 4**, additional sub-gates 4a–4e fire before each subagent in the pipeline so the user previews what file(s) will appear (or what in-chat output to expect) before any work runs. Once the user picks `Run all rest` at any gate (top-level or sub-gate), suppress every subsequent gate — including remaining sub-gates — for the rest of this command run.

1. **Ask the single content question FIRST.** Use `AskUserQuestion` with the exact prompt: `What would you like to build? Press enter for the default (mini coding agent with web UI), or describe your own project.` The question precedes `/init` so CLAUDE.md ends up reflecting the user's actual choice once the codebase exists. *(Phase 1 — no preceding gate; this question IS the entry point.)*

2. **Print the orchestrator preamble to chat.** First, fire **GATE 2** per §Phase Gates. Then copy the content between the `PRAXION-ORCHESTRATOR-START` and `PRAXION-ORCHESTRATOR-END` sentinel markers in §How Claude drives Praxion and print it verbatim — *before* the pipeline runs. The user should learn the model *before* watching it execute.

3. **Branch on the answer.** First, fire **GATE 3** per §Phase Gates. Then branch:
   - Empty, `default`, `yes`, `y`, `ok` (case-insensitive) → §Default App — Pipeline Framing.
   - Any non-trivial description → §Custom App — Pipeline Framing.

4. **Show the pipeline-framed prompt you're about to execute.** Print the wrapped task (from §Default App — Pipeline Framing or the custom variant) in a fenced block, preceded by: `Here's the task I'm about to run through the pipeline — watch how Claude orchestrates researcher → architect → planner → implementer + test-engineer → verifier.` The shape of this prompt is the teaching.

5. **Execute the pipeline.** First, fire **GATE 4** per §Phase Gates (the umbrella headline that announces the whole pipeline). Then act as orchestrator — delegate to Praxion subagents via the `Task` tool per `rules/swe/swe-agent-coordination-protocol.md`. Use the **Standard-tier pipeline with full delegation checklists** for architect and planner — the seed's pedagogical goal is to show every canonical artifact Praxion produces, so the user's first observation matches what real feature work will later produce. The one seed-specific trim is formal SPEC archival (no REQ IDs, no `.ai-state/specs/SPEC_*.md`) and the verifier's written report (the seed's in-chat summary is enough). Each delegation is wrapped in its own sub-gate (4a–4e per §Phase Gates) — fire the sub-gate *before* invoking the subagent so the user sees what file(s) will appear before any work runs. Sub-gates honor the same one-way `Run all rest` flag set at any earlier gate, so users who opted out of pauses are not re-prompted.
   - **5a.** Fire **GATE 4a**, then delegate to `researcher` — fetch current Claude Agent SDK + `uv` + FastAPI signatures via `external-api-docs` (chub). Output: `.ai-work/<task-slug>/RESEARCH_FINDINGS.md` (structured doc with API summaries, version checks, capability gaps).
   - **5b.** Fire **GATE 4b**, then delegate to `systems-architect` — full delegation checklist. Outputs: `.ai-work/<task-slug>/SYSTEMS_PLAN.md` (trade-offs + module-shape + dependency-direction), `.ai-state/ARCHITECTURE.md` (architect-facing design target), `docs/architecture.md` (developer-facing navigation guide, Built components only), and at least one ADR draft in `.ai-state/decisions/drafts/` pinned to the one-way `src/agent/` → `src/web/` dependency rule (leaving the SSE-over-WebSockets decision as genuinely novel material for L5 later). Use the fragment-filename scheme from `rules/swe/adr-conventions.md` and include the standard MADR body (Context / Decision / Considered Options / Consequences).
   - **5c.** Fire **GATE 4c**, then delegate to `implementation-planner` — full three-doc model on first invocation. Outputs: `.ai-work/<task-slug>/IMPLEMENTATION_PLAN.md` (3–5 step decomposition; the canonical ordered step list), `.ai-work/<task-slug>/WIP.md` (live step-tracking the implementer updates as it works), `.ai-work/<task-slug>/LEARNINGS.md` (cross-session insights — seed it with at least the planner's decomposition decisions and any gotchas surfaced by the architect so the file is not empty).
   - **5d.** Fire **GATE 4d**, then delegate to `implementer` + `test-engineer` concurrently on disjoint file sets. Output: code under `src/agent/`, `src/web/`, `tests/` (full file inventory in §Default App Spec).
   - **5e.** Fire **GATE 4e**, then delegate to `verifier` — one-paragraph acceptance check against §Default App Spec invariants (skip the formal report for the seed). Output: in-chat pass/fail summary.
   Ephemeral plan docs live in `.ai-work/<task-slug>/`; persistent design docs live in `.ai-state/` (architecture + ADR drafts) and `docs/` (developer-facing architecture guide). The seed writes every canonical artifact so the user's first pipeline observation includes the full document set — the subsequent `/co` will commit them.

6. **Run the SDK smoke check** per §SDK smoke check. First, fire **GATE 5** per §Phase Gates. If the probe fails, follow the recovery path (re-fetch chub, introspect installed package, regenerate the affected file, submit `chub_feedback`).

7. **Run the test gate.** `uv sync && uv run pytest -q`. If `uv` is absent, see §Prereq Behaviors.

8. **Regenerate the `.gitignore` Python block.** Append (without duplicating) `__pycache__/`, `.venv/`, `*.egg-info/`, `.pytest_cache/`. Do NOT exclude `uv.lock` — it stays tracked.

9. **Invoke `/init` NOW.** First, fire **GATE 6** per §Phase Gates. Then invoke `/init` — the codebase exists and reflects the user's choice, so `/init`'s CLAUDE.md describes reality. Do not author CLAUDE.md by hand.

10. **Append the Agent Pipeline block idempotently.** Per §Init idempotency, check whether `CLAUDE.md` already has a `## Agent Pipeline` heading. If not, append the block verbatim from §Agent Pipeline Block.

11. **Generate the mushi doc LAST.** First, fire **GATE 7** per §Phase Gates. Then generate the mushi doc — file anchors (§Mushi Doc Spec) must be computed against the final on-disk state, so this step follows everything that writes source code.

12. **Stage the scaffold.** `git add -A` (the `.gitignore` keeps `.env` and `.ai-work/` out). Do NOT run `git commit`. *(Phase 8 — no preceding gate; the staging+handoff is short and the exit message itself is the natural pause.)*

13. **Print the exit handoff** (verbatim wording at the end of this file).

## §Phase Gates

The seed onboarding is the densest pedagogical moment in a Praxion user's whole journey, and the default §Flow runs it end-to-end without pause. To let the user *learn* the orchestrator + subagent pattern instead of just *watching* it whoosh by, fire an `AskUserQuestion` gate at every phase boundary defined below. Each gate explains what's about to happen *before* it happens; the user clicks `Continue` to proceed (or opts out via `Run all rest`).

**Escape hatch (one-way).** Each gate offers two options: `Continue` and `Run all rest`. If the user picks `Run all rest`, set an internal "no-more-gates" flag for the remainder of this command run and skip every subsequent gate without asking. The flag is one-way — once set, it persists until the command exits. This honors users who have run the onboarding before and want it to play through.

**Fallback.** If `AskUserQuestion` is unavailable (tool error, headless invocation), print the headline as a chat message and proceed without blocking. Do not fail the onboarding because a gate cannot fire.

**Format.** Every gate uses these `AskUserQuestion` parameters:

- `header` — `"Next?"`
- `question` — the headline from the table below (forward-looking; describes the phase about to start, not the one just finished)
- `multiSelect` — `false`
- `options` — exactly two:
  - `{ label: "Continue", description: "Proceed with this phase. I'll pause again before the next." }`
  - `{ label: "Run all rest", description: "Skip remaining gates and run the rest autonomously." }`

**Phase-to-gate map.** Phase 1 (the content question) is itself an `AskUserQuestion`, so it needs no preceding gate. Phase 8 (stage + exit handoff) is a short close-out where the final message is itself the stopping point, so it also has no gate. The six phase gates between (2, 3, 4, 5, 6, 7), plus five sub-gates inside Phase 4 (4a–4e — one per subagent in the headline pipeline run, so the user previews each agent's outputs before it executes), are:

| Gate | Fires before §Flow step | Headline (use verbatim as `question`) |
|------|------------------------|--------------------------------------|
| 2 | step 2 (orchestrator preamble) | `Phase 2 of 7: I'll explain how Claude drives Praxion — orchestrator routes plain-English tasks to specialist subagents (researcher / architect / planner / implementer / test-engineer / verifier). Reading this once now means you won't need to memorize slash commands later. Continue?` |
| 3 | step 3 (branch + framed prompt) | `Phase 3 of 7: I'll show you the exact English task I'm about to feed the orchestrator. The shape of this prompt — concrete behaviors + acceptance criteria + explicit pipeline invocation — is the pattern you'll reuse forever. Continue?` |
| 4 | step 5 (execute pipeline) | `Phase 4 of 7: HEADLINE EVENT. I delegate to researcher → systems-architect → implementation-planner → implementer + test-engineer (concurrent) → verifier. I'll pause before each subagent so you can see what file it will produce. Continue?` |
| 4a | step 5a (researcher) | `Pipeline step 1 of 5: researcher. Fetches current Claude Agent SDK / uv / FastAPI signatures via context-hub (the chub MCP). Produces .ai-work/<task-slug>/RESEARCH_FINDINGS.md — API summaries, version checks, capability notes — so downstream agents design against real signatures, not training-data guesses. Continue?` |
| 4b | step 5b (systems-architect) | `Pipeline step 2 of 5: systems-architect. Full delegation checklist on first invocation — this is Praxion's complete architecture artifact set, appearing on your screen for the first time. Produces .ai-work/<task-slug>/SYSTEMS_PLAN.md (trade-offs + module shape), .ai-state/ARCHITECTURE.md (architect-facing design target; persists across every future feature), docs/architecture.md (developer-facing navigation guide), and an ADR draft in .ai-state/decisions/drafts/ pinning the one-way src/agent/ → src/web/ dependency rule. The ADR starts as a dec-draft-<hash> fragment and is promoted to a stable dec-NNN at merge-to-main. Continue?` |
| 4c | step 5c (implementation-planner) | `Pipeline step 3 of 5: implementation-planner. Full three-doc model on first invocation. Produces .ai-work/<task-slug>/IMPLEMENTATION_PLAN.md (the canonical ordered step list), WIP.md (live step-tracking the implementer updates as it works), and LEARNINGS.md (cross-session insights — seeded with the planner's decomposition decisions so the file is not empty). This is the full planner artifact set you will see on every future feature. Continue?` |
| 4d | step 5d (implementer + test-engineer) | `Pipeline step 4 of 5: implementer + test-engineer running concurrently on disjoint file sets. Writes src/agent/, src/web/, and tests/ — real code lands in your project tree. Watch your editor's file tree refresh as files appear. Continue?` |
| 4e | step 5e (verifier) | `Pipeline step 5 of 5: verifier. Checks the three §Default App acceptance criteria — agent→web import isolation, SAFE_COMMANDS shape, pytest green. Compact-seed output is a one-paragraph in-chat report; the formal VERIFICATION_REPORT.md is reserved for full-tier features. Continue?` |
| 5 | step 6 (SDK smoke check) | `Phase 5 of 7: I verify the Claude Agent SDK import surface (chub docs sometimes drift from the installed package), run the test suite via uv, and lock down the .gitignore Python block. Continue?` |
| 6 | step 9 (/init) | `Phase 6 of 7: I run /init so CLAUDE.md describes the code that ACTUALLY exists (not what I imagined), then append the Agent Pipeline reference idempotently. Continue?` |
| 7 | step 11 (mushi doc) | `Phase 7 of 7: I generate onboarding_for_mushi_busy_ppl.md — your project-specific map with a happy-path Mermaid diagram, file inventory, lesson ladder, and PoC-to-production journey. Continue?` |

**Don't paraphrase the headlines.** Copy each cell verbatim into the `question` field — they're sized to teach the user *why* each phase exists, not just *what* it does, and the wording was chosen so the seven gates form a coherent narrative across the run.

## §What is Praxion

Canonical paragraph. Enclosed between sentinel markers so the mushi-doc generation step can copy it verbatim by matching the markers. Do not paraphrase — copy the bytes between (but not including) the markers.

<!-- PRAXION-PARAGRAPH-START -->
Praxion is a toolbox that turns Claude Code into a disciplined engineering partner. It ships a curated set of skills, agents, rules, commands, and memory that wire Claude into a clean Understand → Plan → Verify workflow. As you work, the system researches external APIs, plans in small known-good increments, writes and runs tests, verifies its own output against acceptance criteria, and remembers what you've agreed on across sessions — so you spend your attention on deciding what to build next, not on hand-holding the tools.
<!-- PRAXION-PARAGRAPH-END -->

## §How Claude drives Praxion

Orchestrator preamble. Same copy-verbatim rule as §What is Praxion — printed to chat in Flow step 2, and copied into the mushi doc as section 2.

<!-- PRAXION-ORCHESTRATOR-START -->
**You don't call Praxion subagents by name.** You write tasks in plain English, and Claude (the orchestrator) routes the work to the right specialists:

- **researcher** — explores docs, libraries, prior art, external APIs
- **systems-architect** — designs module shape, dependency direction, trade-offs
- **implementation-planner** — breaks a design into small, testable steps
- **implementer** — writes code for one step at a time
- **test-engineer** — writes tests; runs in parallel with the implementer when possible
- **verifier** — checks the result against explicit acceptance criteria

The pattern that triggers routing is a task written with **concrete behaviors + acceptance criteria + (when you want the full pipeline) an explicit "use Praxion's Standard-tier pipeline" invocation**. You speak English, Claude delegates. No `/command` memorization required.
<!-- PRAXION-ORCHESTRATOR-END -->

## §Default App — Pipeline Framing

When the user accepts the default, emit the following pipeline-framed task in chat (in a fenced block, preceded by the Flow-step-4 one-liner). Then execute it — you read this as the orchestrator and delegate to subagents via `Task`.

```
Build a minimal conversational coding agent for Python 3.11+ using the Claude Agent SDK.

Behaviors:
- An agent loop over user turns via the Claude Agent SDK (use symbols fetched from external-api-docs; do NOT guess SDK surface).
- Two starter tools: `read_file(path: str) -> str` (filesystem read) and `run_command(cmd: str) -> str` (safe-listed via a module-scope `SAFE_COMMANDS = frozenset({"ls", "pwd", "cat", "python"})` — first token not in the frozenset returns a refusal string, does not raise).
- A FastAPI POST `/chat` that streams the agent's response as Server-Sent Events, plus a minimal HTML page at `static/index.html` that POSTs and renders the stream.
- Strict one-way dependency: `src/agent/` imports nothing from `src/web/`; `src/web/` may import from `src/agent/`.
- One smoke test at `tests/test_agent.py` that constructs the agent without hitting the network.

Tech: Python 3.11+, uv for project management, Claude Agent SDK, FastAPI + sse-starlette (or current-doc equivalent), pytest.

Acceptance:
- `grep -r 'from src.web\|import src.web' src/agent/` returns no matches.
- `SAFE_COMMANDS` is a module-scope `frozenset` in `src/agent/tools.py`.
- `uv run pytest -q` passes on a fresh `uv sync` with only `ANTHROPIC_API_KEY` optionally set.

Use Praxion's Standard-tier pipeline with the full delegation checklist for architect and planner (this is a seed app, so skip only SPEC archival and the verifier's formal written report — everything else fires):
- researcher fetches current Claude Agent SDK + uv + FastAPI signatures via external-api-docs
- systems-architect produces SYSTEMS_PLAN.md, .ai-state/ARCHITECTURE.md, docs/architecture.md, and one ADR draft in .ai-state/decisions/drafts/ for the one-way src/agent/ → src/web/ dependency rule (leave SSE-over-WebSockets as a future decision — it is tutorial material for a later lesson)
- implementation-planner decomposes into 3–5 steps and produces the full three-doc model: IMPLEMENTATION_PLAN.md + WIP.md + LEARNINGS.md (seeded with the planner's decomposition decisions)
- implementer + test-engineer run concurrently on disjoint file sets
- verifier checks the three acceptance criteria above and reports pass/fail in one paragraph (no written VERIFICATION_REPORT.md for the seed — that artifact is reserved for the first real feature, so L4 has something fresh to teach)
```

The shape of this prompt — specific behaviors, explicit acceptance, explicit pipeline invocation — is the pattern the user will reuse in the mushi-doc lessons.

## §Custom App — Pipeline Framing

When the user describes a non-trivial app (not empty, not a default-synonym), emit the SAME shape — **behaviors + tech + acceptance + explicit pipeline invocation** — with fields derived from their description. Ask at most one clarifying question if the description is missing any of: target language/framework, a concrete behavior, or an observable acceptance criterion. If all three are present, do not ask — build.

Example (user said: "I want a Discord bot that greets new members"):

```
Build a Discord bot in Python 3.11+ that greets new members.

Behaviors:
- Connects to a Discord guild via a bot token read from the `DISCORD_TOKEN` env var.
- On `member_join` event, posts a configurable greeting string in a configurable channel.
- Greeting string and channel id come from `config.toml` at project root; defaults do not leak any guild id.

Tech: Python 3.11+, uv, `discord.py` (or `hikari` if the user expresses a preference).

Acceptance:
- `uv run pytest -q` passes; tests cover (a) config parse, (b) greeting-string formatting, (c) dispatcher selects the right channel by id.
- No hardcoded tokens, channel ids, or guild ids in source.

Use Praxion's Standard-tier pipeline with the full delegation checklist for architect and planner (skip only SPEC archival and the verifier's written report for this seed). The architect produces SYSTEMS_PLAN.md + .ai-state/ARCHITECTURE.md + docs/architecture.md + one ADR draft for the defining trade-off; the planner produces the full three-doc model (IMPLEMENTATION_PLAN.md + WIP.md + LEARNINGS.md).
```

The custom branch still runs every step of §Flow (orchestrator preamble, pipeline framing shown and executed, `/init` after code exists, mushi doc last) and produces the same full artifact set (SYSTEMS_PLAN + ARCHITECTURE + docs/architecture + ADR draft + three-doc planner model). The only lesson-ladder difference is that **L1 and L2 are tailored to the user's app** (new tool analog, refactor analog) while **L3–L7 remain generic** — see §Five-to-Seven Lessons. Tailored count is fixed at 2 regardless of final ladder size (5–7 total).

If Claude cannot produce a concrete `src/<path>:<line>` anchor for a tailored lesson (e.g., user described a Haskell library with no `src/` tree), fall back to the generic L1/L2 and note the fallback in the mushi doc's troubleshooting line.

## §Default App Spec

Structural reference — the pipeline (§Flow step 5) must produce these paths and honor these invariants.

**File inventory (paths are mandatory):**

- `src/agent/__init__.py` — package marker.
- `src/agent/core.py` — agent entry point using symbols from `claude_agent_sdk` (or the current equivalent module path from chub). Exports one constructor/factory.
- `src/agent/tools.py` — two tools: `read_file`, `run_command`. See safe-list invariant.
- `src/agent/prompts.py` — system prompt(s) as plain constants.
- `src/web/__init__.py` — package marker.
- `src/web/app.py` — FastAPI POST `/chat` streaming SSE. Imports agent entry from `src.agent.core`.
- `src/web/static/index.html` — minimal chat UI.
- `tests/__init__.py` — package marker.
- `tests/test_agent.py` — smoke test (no network).
- `pyproject.toml` — uv-managed, deps per fetched docs.
- `.env.example` — `ANTHROPIC_API_KEY=` placeholder.

**Dependency-direction invariant:** `src/agent/` imports nothing from `src/web/`; `src/web/` may import from `src/agent/`. Verify with `grep -r 'from src.web\|import src.web' src/agent/` → zero matches.

**Safe-list invariant for `run_command`:** module-scope `SAFE_COMMANDS = frozenset({"ls", "pwd", "cat", "python"})`; first-token comparison; refusal returns a plain `str` and does not raise.

**FastAPI `/chat` shape:** POST with `{"message": str}` body, `text/event-stream` response.

**Smoke test:** constructs the agent without hitting the network (mock/stub per fetched doc).

**`.ai-state/` writes are expected** during the seed build — `.ai-state/ARCHITECTURE.md` (architect-facing design target) and at least one ADR draft under `.ai-state/decisions/drafts/<fragment>.md` (pinning the one-way `src/agent/` → `src/web/` dependency rule). The developer-facing `docs/architecture.md` is also produced. All three land in the working tree and are staged by the exit handoff's `git add -A`, so `/co` commits them with the rest of the scaffold. The one-but-not-the-other pedagogical choice here: the seed is the user's *first* view of Praxion's architecture-artifact set, so producing them surfaces the philosophy early; formal SPEC archival and `VERIFICATION_REPORT.md` stay deferred to L4 so a later lesson has genuinely novel material.

## §SDK smoke check

After `uv add claude-agent-sdk` succeeds, before or immediately after writing `src/agent/core.py`, probe the import surface:

```
uv run python -c "from claude_agent_sdk import ClaudeSDKClient, query, tool; print('ok')"
```

If it prints `ok`, proceed. If the import fails with `ImportError` / `ModuleNotFoundError` / `AttributeError`, the fetched chub doc has drifted from the installed SDK. Recovery:

1. Re-read the fetched chub entry; request it again and prefer entries marked `official` or `maintainer`.
2. Inspect the installed package: `uv run python -c "import claude_agent_sdk; print(dir(claude_agent_sdk))"` and pick the actually-present public symbols.
3. Regenerate `src/agent/core.py` against those symbols.
4. Submit `chub_feedback` with `vote: "down"`, `label: "outdated"`, naming the missing symbol and the installed SDK version. Append the identity suffix per the `external-api-docs` skill.

Never copy symbol names from this file into generated code — this file deliberately does not pin them.

## §Init idempotency

Before appending the §Agent Pipeline Block to `CLAUDE.md`, run:

```
grep -q '^## Agent Pipeline' CLAUDE.md
```

- Exit `0` (match found) → block already exists; skip the append.
- Exit non-zero → append the block verbatim from §Agent Pipeline Block.

This predicate mirrors `/onboard-project`, so re-running either command does not duplicate the section.

## §Mushi Doc Spec

Generate `<project-root>/onboarding_for_mushi_busy_ppl.md` with these nine sections in this exact order:

1. **Canonical Praxion paragraph** — copied verbatim (byte-for-byte) from between the `PRAXION-PARAGRAPH-START` and `PRAXION-PARAGRAPH-END` sentinel markers in §What is Praxion. Do not paraphrase.
2. **How Claude drives Praxion** — copied verbatim from between the `PRAXION-ORCHESTRATOR-START` and `PRAXION-ORCHESTRATOR-END` sentinel markers in §How Claude drives Praxion. Placed immediately after the canonical paragraph — the first thing the user reads after "what is Praxion" is "how I talk to it."
3. **TL;DR card** — exactly three lines: "what you have", "what you can do right now", "what to do next".
4. **Mermaid happy-path diagram** — ≤10 nodes per `rules/writing/diagram-conventions.md`. One concept only.
5. **What got created table** — columns `Artifact | Purpose | Edit when…`. One row per generated file. **Just-in-time verification:** `ls -la <path>` every row; do not ship a row whose path does not resolve.
6. **Five-to-seven lesson ladder** — `<details>` collapsibles, one per lesson, in the "Put this in Claude" four-bullet format defined in §Five-to-Seven Lessons. L6 is mandatory.
7. **Glossary collapsible** — short definitions for: Praxion, skill, agent, rule, command, **orchestrator**, **subagent**, pipeline, Understand/Plan/Verify, Claude Agent SDK, uv, `.ai-state/`, `.ai-work/`, `/co`, `/cop`, **ADR** (`dec-NNN`), **sentinel report**.
8. **Journey to Production** — heading `## From PoC to Production`. Open content (NOT a `<details>` — this is core, not optional depth). Eight rows in a milestone table (`Milestone | Trigger | Produces`) covering: (1) Working PoC + architecture baseline + first ADR = the seed already lands all three (`.ai-state/ARCHITECTURE.md`, `docs/architecture.md`, and one ADR draft under `.ai-state/decisions/drafts/`), (2) Health audit via `sentinel` agent producing `.ai-state/SENTINEL_REPORT_*.md`, (3) Architecture *evolves* — each feature updates `.ai-state/ARCHITECTURE.md` + `docs/architecture.md` via `systems-architect`, (4) ADR fleet accumulates — each decision-worthy choice becomes a new draft in `.ai-state/decisions/drafts/` (promoted to stable `dec-NNN` at merge-to-main by `scripts/finalize_adrs.py`), (5) CI/CD via `cicd-engineer` producing `.github/workflows/*.yml`, (6) Deployment via `deployment` skill producing `compose.yaml` + `.ai-state/SYSTEM_DEPLOYMENT.md`, (7) First release via `/release` producing version bump + `CHANGELOG.md` + git tag, (8) Cross-session memory via `remember()` writing `.ai-state/memory.json`. Each `Trigger` cell shows the exact prompt or command. Each `Produces` cell names a real path the user will see. Close the section with a 6-step "Suggested order for this project" numbered list anchored to the just-generated app: iterate via L1–L7 (each feature evolves the architecture docs + may add an ADR) → sentinel audit at ~10 files → CI/CD before first user → deployment when ready to host → first release at stable behavior → record ADRs continuously as you go, never batched. The table mirrors `docs/getting-started.md#journey-poc-to-production` in shape; the language stack column reflects what was actually scaffolded (e.g., row 5 names `pyproject.toml` if uv was detected).
9. **What to read next** — one-line pointer to `docs/project-onboarding.md` in the Praxion repo, plus: "Run `/co` to make your first commit (or `/cop` for commit+push); both apply `rules/swe/vcs/git-conventions.md` automatically, so you don't hand-craft commit messages."

**File anchors:** every lesson references at least one concrete anchor of the form `src/<path>:<line>` that resolves to a real line. Generate the mushi doc after all source files are written so anchors are stable.

**Journey verification:** the eight milestones in section 8 must each name a concrete path the user can `ls` after triggering it (paths are aspirational at generation time — they will not exist in the freshly-scaffolded project, which is the point). Do not invent paths; cite the same paths used in `docs/getting-started.md` and the `## Agent Pipeline` block in `CLAUDE.md`.

## §Five-to-Seven Lessons

Each lesson in the mushi doc uses this exact four-bullet shape:

- **What you'll learn** — the Praxion concept or competency the lesson unlocks.
- **Put this in Claude** — a block-quoted, plain-English task the user copy-pastes into their next Claude session. Big enough to trigger orchestrator routing.
- **What will happen** — which subagents Claude will delegate to, and what they'll produce.
- **Expected touches** — concrete file anchors that will change.

Ship all seven by default; L1 / L2 / L7 may be omitted only if anchor generation fails (final ladder ≥ 5). **L6 is mandatory.**

### L1 — Add a new tool to the agent

- **What you'll learn:** how the orchestrator routes a multi-file feature through research → design → plan → paired implement+test → verify.
- **Put this in Claude:**
  > Add a tool called `list_dir(path: str) -> str` to the agent that returns the entries of a given directory, enforcing the same safe-list pattern as `run_command`. Apply Praxion's Standard-tier pipeline: research any relevant SDK conventions for tool registration, design the tool contract, decompose into steps, implement with paired tests, and verify the safe-list invariant still holds.
- **What will happen:** Claude spawns `researcher` (SDK conventions), `systems-architect` (tool contract + invariant reuse), `implementation-planner` (3-step decomposition), `implementer` + `test-engineer` in parallel (new tool + test), `verifier` (acceptance check).
- **Expected touches:** `src/agent/tools.py:<line-near-SAFE_COMMANDS>`, `tests/test_agent.py`, maybe `src/agent/prompts.py` (tool intro).

### L2 — Refactor the web layer safely

- **What you'll learn:** restructure code without changing behavior, using an isolated worktree so `main` never sees half-done state.
- **Put this in Claude:**
  > Refactor `src/web/app.py` into two modules: one for routes, one for the SSE streaming helper. Create a worktree for the refactor, preserve behavior (the existing smoke test must pass unchanged), and merge back only when tests are green.
- **What will happen:** Claude creates a worktree, then routes the refactor through the `refactoring` skill; `implementer` splits the module, `test-engineer` verifies no behavior change; merged back on green.
- **Expected touches:** `src/web/app.py:<line-of-POST-/chat>` → split into `src/web/routes.py` and `src/web/streaming.py`; `tests/test_agent.py` unchanged.

### L3 — Fetch current SDK docs before writing code

- **What you'll learn:** never guess an SDK signature — fetch the current doc first, even when Claude seems confident.
- **Put this in Claude:**
  > Before I extend the agent, I want a current summary of Claude Agent SDK's public API. Use context-hub (the external-api-docs skill) to fetch the latest Claude Agent SDK Python signatures, then produce a one-page cheat-sheet in this chat covering tool registration, hooks, and multi-turn sessions. No code changes — this is a read.
- **What will happen:** Claude spawns `researcher`, which invokes the `external-api-docs` skill (`mcp__chub__chub_search` + `mcp__chub__chub_get`), then summarizes in-chat.
- **Expected touches:** none (read-only). Your transcript now has a fresh cheat-sheet you can anchor `src/agent/core.py:<line-of-import>` against.

### L4 — Add a feature end-to-end with full quality gates

- **What you'll learn:** how a real feature *evolves* Praxion's persistent artifacts — the architecture docs from the seed get updated (not replaced), the next ADR joins the existing fleet, `VERIFICATION_REPORT.md` appears for the first time, and you see the full Plan → Implement → Verify traceability chain end-to-end.
- **Put this in Claude:**
  > Add a request-size gate to POST `/chat`: reject bodies larger than 4 KB with HTTP 413, and emit the accepted size as the first SSE event. Apply Praxion's Standard-tier pipeline in full — I want the architect to update the existing `.ai-state/ARCHITECTURE.md` and `docs/architecture.md` (do not rewrite them from scratch), the planner to produce a fresh `IMPLEMENTATION_PLAN.md`/`WIP.md`/`LEARNINGS.md` triad for this feature, paired implementer/test work, and a VERIFICATION_REPORT.md against explicit acceptance criteria. Leave the `.ai-work/` artifacts in place so I can read them.
- **What will happen:** full pipeline fires — `researcher` → `systems-architect` (updates `ARCHITECTURE.md` + `docs/architecture.md`, writes a fresh `SYSTEMS_PLAN.md`, adds a new ADR draft if the gate introduces a trade-off) → `implementation-planner` (fresh `IMPLEMENTATION_PLAN.md` + `WIP.md` + `LEARNINGS.md`) → `implementer` + `test-engineer` → `verifier` (NEW: `VERIFICATION_REPORT.md`).
- **Expected touches:** `src/web/app.py:<line-of-POST-/chat>`, `tests/test_agent.py`, updated `.ai-state/ARCHITECTURE.md`, updated `docs/architecture.md`, possibly a new `.ai-state/decisions/drafts/<fragment>.md`, and a fresh `.ai-work/<slug>/` directory with the full four-doc pipeline set + `VERIFICATION_REPORT.md`.

### L5 — Persist a second decision as an ADR

- **What you'll learn:** how ADRs accumulate as a project evolves — the seed already wrote your first ADR (the `src/agent/` → `src/web/` dependency rule), and this lesson grows the fleet. You'll see the fragment-filename-at-create scheme, understand that drafts under `.ai-state/decisions/drafts/` only promote to stable `dec-NNN` at merge-to-main, and watch `DECISIONS_INDEX.md` accumulate as decisions compound over the project's lifetime.
- **Put this in Claude:**
  > Record a decision: we chose Server-Sent Events for POST `/chat` streaming over WebSockets and long-polling because SSE gives simpler server code and automatic reconnect. Write this as a new ADR following `rules/swe/adr-conventions.md` (MADR frontmatter + Context / Decision / Considered Options / Consequences) — use the fragment-filename scheme (`<YYYYMMDD-HHMM>-<user>-<branch>-<slug>.md` under `.ai-state/decisions/drafts/`) with `id: dec-draft-<hash>` and `status: proposed`, since we have not merged to main yet. The cross-reference-aware finalize script will promote it later.
- **What will happen:** Claude writes `.ai-state/decisions/drafts/<fragment>.md` with full frontmatter + body. The draft sits alongside the seed's dependency-rule ADR in `drafts/` until merge-to-main, at which point `scripts/finalize_adrs.py` renames both to stable `dec-NNN` files and regenerates `DECISIONS_INDEX.md`.
- **Expected touches:** `.ai-state/decisions/drafts/<fragment>-sse-over-websockets.md` (new draft). Anchored to `src/web/app.py:<line-of-streaming-return>`.

### L6 — Testing workflow (MANDATORY)

- **What you'll learn:** Praxion's testing rhythm — behavioral tests first, tight feedback loop via `pytest -q`, full suite green before a commit lands.
- **Put this in Claude:**
  > Extend `tests/test_agent.py` with a behavioral test that asserts `run_command("rm -rf /")` (or any first token outside the safe-list) returns the refusal string without raising. Then run the full pytest suite and report pass/fail. If the invariant is looser than I described, flag it — don't silently tighten it.
- **What will happen:** Claude spawns `test-engineer`, adds the behavioral test, runs `uv run pytest -q`, reports results. If the invariant is loose, Claude surfaces the gap without auto-fixing.
- **Expected touches:** `tests/test_agent.py:<line-of-smoke-test>`, possibly `src/agent/tools.py:<line-of-SAFE_COMMANDS>` if the check needed tightening.

### L7 — Project exploration as code grows (OPTIONAL)

- **What you'll learn:** orient yourself once the seed shape has grown past a handful of files.
- **Put this in Claude:**
  > The codebase has grown past the seed shape. Produce a current architecture view: map modules, entry points, external dependencies, and any surprising coupling. Output a one-page summary with a Mermaid component diagram (≤10 nodes). Skip anything CLAUDE.md already says.
- **What will happen:** Claude runs the `project-exploration` skill, generates a compact summary with a diagram.
- **Expected touches:** none (read-only). Useful once the project has ≥10 files.

## §Prereq Behaviors

**`uv` missing.** Before running the test gate, check `command -v uv`. If absent:

- Print: `uv is not installed. Install with: curl -LsSf https://astral.sh/uv/install.sh | sh (then re-run 'uv sync && uv run pytest -q' from this project root).`
- Skip `uv sync` and `uv run pytest -q`. Do not fail the session.
- Note the skipped step in the mushi doc's "What to do next": add a bullet `Install uv, then run: uv sync && uv run pytest -q` above the `/co` line.

**`ANTHROPIC_API_KEY` unset.** Do NOT block the flow. The smoke test is designed to pass without the key (constructs the agent against a mock transport). Handle it this way:

- `.env.example` lists `ANTHROPIC_API_KEY=` as a placeholder.
- The mushi doc's "What to do next" mentions that live agent calls require `export ANTHROPIC_API_KEY=sk-ant-...` (in a `.env` file, which is gitignored) before running `uv run python -m src.web.app`.

## §Agent Pipeline Block

Append this block to `CLAUDE.md` when the idempotency predicate (§Init idempotency) reports no existing heading. **Source of truth:** the identical block lives in `commands/onboard-project.md`. If that file changes, mirror the change here — both commands must produce byte-identical CLAUDE.md sections.

```markdown
## Agent Pipeline

Follow the Understand, Plan, Verify methodology. For multi-step work (Standard/Full tier), delegate to specialized agents in pipeline order. Each pipeline operates in an ephemeral `.ai-work/<task-slug>/` directory (deleted after use); permanent artifacts go to `.ai-state/` (committed to git).

1. **researcher** → `.ai-work/<slug>/RESEARCH_FINDINGS.md` — codebase exploration, external docs
2. **systems-architect** → `.ai-work/<slug>/SYSTEMS_PLAN.md` + ADR drafts under `.ai-state/decisions/drafts/` (promoted to stable `<NNN>-<slug>.md` at merge-to-main by `scripts/finalize_adrs.py`) + `.ai-state/ARCHITECTURE.md` (architect-facing) + `docs/architecture.md` (developer-facing)
3. **implementation-planner** → `.ai-work/<slug>/IMPLEMENTATION_PLAN.md` + `WIP.md` — step decomposition
4. **implementer** + **test-engineer** (concurrent) → code + tests — execute steps from the plan
5. **verifier** → `.ai-work/<slug>/VERIFICATION_REPORT.md` — post-implementation review

**Independent audits**: the `sentinel` agent runs outside the pipeline and writes timestamped `.ai-state/SENTINEL_REPORT_*.md` plus an append-only `.ai-state/SENTINEL_LOG.md`. Trigger it for ecosystem health baselines (before first ideation, after major refactors).

**From PoC to production**: the feature pipeline is one milestone of many. The full journey runs through sentinel audit → CI/CD (`cicd-engineer`) → deployment (`deployment` skill) → first release (`/release`) → persistent decisions as ADRs → cross-session memory (`memory.json` + `observations.jsonl`). See the milestone table at `docs/getting-started.md#journey-poc-to-production`.

Always include expected deliverables when delegating to an agent. The agent coordination protocol rule has full delegation checklists.
```

## Test gate

After all files are generated and before the mushi doc is finalised, run:

```
uv sync && uv run pytest -q
```

If `uv` is absent, see §Prereq Behaviors and skip gracefully. If tests fail, surface the output — do not hide a red test. The mushi doc notes the failure in "What to do next".

## Exit handoff

Stage everything (`git add -A`). Do NOT commit. Print exactly:

```
Scaffold staged. Run /co to make the first commit (or /cop for commit+push); both apply rules/swe/vcs/git-conventions.md automatically, so you don't hand-craft commit messages.
```

The mushi doc's "What to do next" carries the same language — `/co` as default, `/cop` as commit-and-push, and the explicit note that the user is outsourcing commit-message authoring to the git-conventions rule.
