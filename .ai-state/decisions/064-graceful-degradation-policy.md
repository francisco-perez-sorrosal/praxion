---
id: dec-064
title: Graceful degradation policy — git+stdlib hard floor, everything else optional
status: proposed
category: behavioral
date: 2026-04-23
summary: /project-metrics treats only git + Python 3.11+ stdlib as required; every other tool is optional with per-collector skip markers so the command runs end-to-end on any Praxion-onboarded repository regardless of installed tooling
tags: [behavioral, resilience, dependencies, metrics, project-metrics]
made_by: agent
agent_type: systems-architect
pipeline_tier: standard
affected_files:
  - scripts/project_metrics/cli.py
  - scripts/project_metrics/runner.py
  - scripts/project_metrics/collectors/
  - scripts/project_metrics/report.py
  - commands/project-metrics.md
---

## Context

The user locked Decision #3: lazy tool resolution via `uvx`/`npx`/`go install`, no bundled binaries. The system must remain functional when optional tools are absent. Three reasons this matters beyond simple resilience:

1. **Downstream reach.** `/project-metrics` ships with Praxion to arbitrary user projects. We cannot assume those environments have `uv`, Node, or Go installed; many will not even have `scc`.
2. **First-run latency cost.** `uvx` caches on first use — 30–90 seconds per tool on first invocation. Failing hard when a tool is not in cache would punish first-time users for no reason.
3. **Reporting fidelity.** A skipped metric must be *visibly* skipped in the output, not silently absent. A user looking at the MD needs to know "coverage = null because no artifact" vs "coverage = 0% because tests failed." These are different problems with different fixes.

## Decision

Establish a **three-tier degradation hierarchy** with explicit markers for every skip:

### Hard floor — command errors if missing

| Dependency | Check | Failure mode |
|---|---|---|
| `git` binary on PATH | `shutil.which("git")` + `git rev-parse --is-inside-work-tree` | CLI exits non-zero with `project-metrics: git is required but not found on PATH or not inside a git repository` |
| Python 3.11+ | runtime check | CLI exits non-zero with explicit version |

Nothing else is a hard floor. A Python-only project with no `uv`, no Node, no Go, no `scc` and no coverage artifact still gets a meaningful report (git-based metrics only).

### Soft dependencies — produce report with skip markers

| Tool | Role | Absent behavior | Aggregate impact |
|---|---|---|---|
| `scc` binary | Tier 0 language-breakdown + fast SLOC | Python stdlib SLOC fallback (slower; extension-based language detection) | `aggregate.sloc_total` still populated; `language_count = 0` if scc fallback can't identify languages |
| `uv` / `uvx` meta | Gate for all Python-tier-1 tools | All ephemeral Python collectors return Unavailable | Tier 1 aggregate fields (ccn_p95, cognitive_p95, cyclic_deps) = null |
| `lizard` via uvx | Cross-language CCN | Collector returns Unavailable; hot-spot composition falls back to scc branch-count as complexity dimension, marked `"complexity_source": "scc_fallback"` in the aggregate | `ccn_p95 = null` |
| `complexipy` via uvx | Python cognitive | Collector Unavailable | `cognitive_p95 = null` |
| `pydeps` via uvx | Python coupling/cycles | Collector Unavailable | `cyclic_deps = null` |
| Coverage artifact | Existing `coverage.xml` or `lcov.info` on disk | Collector reports `status: no_artifact`, install hint = `pytest --cov && coverage xml`; NEVER invokes the test suite | `coverage_line_pct = null` |

### Not-applicable — silent

| Collector | Not-applicable trigger |
|---|---|
| `complexipy` | No `.py` sources in git ls-files |
| `pydeps` | No `.py` sources; or no `__init__.py` / no importable packages detected |
| `coverage` | No Python project markers (pyproject.toml / setup.py / requirements.txt) |

Not-applicable collectors produce `status: "not_applicable"` in `tool_availability` and are omitted from the "install to improve" hint section of the MD. This is a distinct state from Unavailable — there is nothing for the user to do.

### Skip-marker shapes

Uniform JSON shapes so the UI and the MD renderer treat all skips the same way:

```
"tool_availability": {
    "<name>": {"status": "available",     "version": "<x.y.z>"}
  | {"status": "unavailable",   "reason": "...",  "install_hint": "..."}
  | {"status": "not_applicable","reason": "..."}
  | {"status": "error",         "reason": "...",  "traceback_excerpt": "..."}
  | {"status": "timeout",       "timeout_seconds": N}
}
```

Namespace blocks for unresolved collectors:

```
"<namespace>": {"status": "skipped", "reason": "tool_unavailable", "tool": "<name>"}
```

This uniform shape lets the MD renderer generate `_not computed — <reason>_` lines with one function regardless of collector.

### User-visible output discipline

- The MD report begins with a **Tool Availability** section listing every collector with a one-line status. The reader sees at a glance what was and was not computed.
- Unavailable collectors generate a **Install to improve** section with actionable one-liners (`uvx pip install lizard && uvx lizard --version` etc.).
- Not-applicable collectors are omitted from the Install section but included in Tool Availability (for completeness).

### Non-negotiable: never run the test suite

Coverage collection reads pre-existing artifacts only. Invoking `pytest`, `coverage run`, or any test runner from `/project-metrics` is out of scope and prohibited — test execution has its own latency, failure modes, and side-effect surface (test DBs, fixtures, external services). A metrics command that might spin up the test suite is a command users will not run.

## Considered Options

### Option 1: Require all tools, fail hard if any absent

**Pros:** Simplest code; one code path.

**Cons:** Command is unusable on any repo where `uv` is not installed — which includes most first-time Praxion installs. Contradicts user Decision #3. Reject.

### Option 2: Tier-gate degradation (all of Tier 1 falls if any Tier 1 tool is missing)

**Pros:** Simpler report shape.

**Cons:** Punishes partial environments. A project with `lizard` available but not `complexipy` should still get CCN data. Tier-gating wastes available signal.

### Option 3: Per-collector degradation with uniform markers (chosen)

**Pros:** Maximum signal preserved; uniform JSON shape lets downstream consumers treat all skips identically; user sees exactly what they are missing and exactly what to install.

**Cons:** Every numeric field in the aggregate can be null; consumers must handle nullability. This is the honest cost of a resilient tool and is preferable to fabricated zeros.

### Option 4: Auto-install missing tools on first run

**Pros:** Best first-run experience — it just works.

**Cons:** Silent installs are a trust violation; `uvx` is not a package manager we should be driving on the user's behalf without asking; introduces install-time failure modes that are hard to diagnose from a metrics command. Reject.

## Consequences

**Positive:**

- The command runs to a useful report on *any* Praxion-onboarded repository with git, regardless of what else is installed.
- Users see actionable install hints for every tool they lack — the output is a self-guided onboarding path.
- Fabricated numbers never ship — `null` means "not measured," and the user always knows why.
- The downstream UI (static HTML, local server, Datasette) can treat nulls uniformly; no special-case "the tool was different last time" logic needs to live in the UI.

**Negative:**

- Null-ridden aggregates on under-tooled repos look sparse. This is honest; a fake 0 would be worse.
- The MD report's "Tool Availability" section adds length that is noise to users who have everything installed. Acceptable cost for the users who don't.
- Schema versioning interacts with degradation: comparing a run-with-lizard against a run-without-lizard produces `null - N = null` deltas, which is a case the trend renderer must handle explicitly (see the schema ADR's delta semantics).
