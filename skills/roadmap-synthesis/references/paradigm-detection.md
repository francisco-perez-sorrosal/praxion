# Paradigm Detection

Back to: [../SKILL.md](../SKILL.md)

How the cartographer classifies a target project as **deterministic**, **agentic**, or **hybrid** before deriving the lens set and running the audit. Paradigm detection feeds the lens-framework derivation Step 2 (domain constraints) and shapes which sub-questions fire within each chosen lens (see [lens-framework.md](lens-framework.md) and [audit-methodology.md](audit-methodology.md)).

## Why detection matters

Deterministic projects (libraries, CLIs, services without LLMs in their critical path) and agentic projects (systems whose behavior is driven by LLM calls, tool use, or agent orchestration) require materially different evaluation. A uniform roadmap tuned to one paradigm misfires on the other — for example, "hallucination rate" is a critical metric for agentic systems and inapplicable to deterministic ones; "uptime SLO" matters for both but has very different connotations when the workload is non-deterministic.

Misclassification is a named anti-pattern: R15 "paradigm mismatch" in the audit risk register.

## Detection heuristics

The cartographer scans the target project for signals across three axes. Each signal contributes evidence toward `deterministic`, `agentic`, or `both`.

### Dependency signals

| Signal | Weight | Paradigm |
|---|---|---|
| `anthropic`, `openai`, `google-generativeai`, `cohere` in manifest | Strong | agentic |
| `langchain`, `langgraph`, `llamaindex`, `haystack`, `crewai`, `autogen` | Strong | agentic |
| `@anthropic-ai/sdk`, `@anthropic-ai/claude-code` in `package.json` | Strong | agentic |
| `@modelcontextprotocol/*` (MCP SDK) | Strong | agentic |
| Only stdlib / infra deps (database drivers, web frameworks, cloud SDKs) | Strong | deterministic |
| Testing/linting deps only | Neutral | — |

### Filesystem signals

| Signal | Weight | Paradigm |
|---|---|---|
| `AGENTS.md`, `CLAUDE.md`, `.cursorrules`, `.github/copilot-instructions.md` at root | Strong | agentic |
| `skills/`, `agents/`, `prompts/`, `system-prompts/` directories | Strong | agentic |
| `.mcp.json`, `mcp-servers/`, `*-mcp/` subprojects | Strong | agentic |
| `evals/`, `benchmarks/` with LLM-eval frameworks (Inspect AI, DeepEval, Promptfoo) | Strong | agentic |
| `src/` + `tests/` + `docs/` canonical layout without the above | Strong | deterministic |
| `migrations/`, `schema.sql`, or Alembic folders | Medium | deterministic |

### Manifest signals

| Signal | Weight | Paradigm |
|---|---|---|
| `pyproject.toml` / `package.json` describes a library | Medium | deterministic |
| Project keywords include "agent", "llm", "prompt", "mcp", "ai-coding" | Strong | agentic |
| Project declares `plugin.json` in Claude Code plugin format | Strong | agentic |

### Scoring and classification

- **≥2 strong agentic signals and ≥1 strong deterministic** → `hybrid` (common; Praxion itself falls here)
- **≥2 strong agentic signals and 0 strong deterministic** → `agentic`
- **≥2 strong deterministic and 0 strong agentic** → `deterministic`
- **All other combinations** → escalate to user (see below)

## Sub-question selection and lens derivation mapping

Detection output feeds the cartographer's audit in two ways:

1. **Lens set derivation** (Step 2 of the [lens-framework.md](lens-framework.md) methodology) — paradigm is a domain constraint that shapes which exemplar lens set is likely to fit: agentic → SPIRIT or Custom; deterministic → SPACE / DORA / FAIR / Custom; hybrid → SPIRIT or blended. Full table in [`audit-methodology.md §Paradigm-tuning rules`](audit-methodology.md#paradigm-tuning-rules).
2. **Sub-question selection within each chosen lens** — each lens can declare paradigm-specific sub-questions (deterministic vs agentic). The cartographer fires the set that matches the detected paradigm; for `hybrid`, it asks both sets and tags findings by paradigm layer. Worked example: the SPIRIT Appendix in [lens-framework.md](lens-framework.md#spirit-appendix-six-dimensions-in-detail).

## Escalation to user

Detection is not always confident. The cartographer escalates to the user (Gate 1, which also confirms the derived lens set) when:

- Signal count is low (fewer than 2 strong signals in any direction).
- Signals point in conflicting directions without a clear hybrid pattern (e.g., one strong agentic signal + one strong deterministic signal, nothing else).
- The user invoked `/roadmap <focus>` where the focus itself suggests a specific paradigm the evidence doesn't corroborate.

Escalation format (via `AskUserQuestion`):

> "Detected paradigm: **[classification]** based on: [top-3 signals]. Continue with the [classification] lens set, or override to [alternative]?"

## Paradigm-agnostic core

Some audit items apply regardless of paradigm. Treat these as universally applicable and do not gate them on detection:

- Is there a README with getting-started instructions?
- Is there a LICENSE?
- Do tests run in CI?
- Are dependencies pinned or managed by a lockfile?
- Is there a CHANGELOG or release-notes practice?

These go into the roadmap regardless of classification — under whichever dimension they fit (usually Quality or Pragmatism).

## Failure modes to guard against

- **Single-signal classification** — one `langchain` dep in a library test-fixture does not make the project agentic. Require ≥2 strong signals.
- **Stale signals** — `AGENTS.md` present but empty, `skills/` directory exists but contains only README. Inspect content before counting.
- **User override without rationale** — if the user rejects the detected paradigm, capture their stated reason in the Methodology Footer so the override is auditable.
