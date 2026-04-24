---
id: dec-063
title: Collector protocol as extension seam for /project-metrics
status: proposed
category: architectural
date: 2026-04-23
summary: Define a pluggable collector protocol (resolve/collect/describe) for /project-metrics so v1 Tier 0+Python collectors and deferred v2 TS/Go/Rust collectors share a stable interface and runner can orchestrate them with uniform error isolation
tags: [architecture, protocol, extensibility, metrics, project-metrics]
made_by: agent
agent_type: systems-architect
pipeline_tier: standard
affected_files:
  - scripts/project_metrics/collectors/base.py
  - scripts/project_metrics/collectors/git_collector.py
  - scripts/project_metrics/collectors/scc_collector.py
  - scripts/project_metrics/collectors/lizard_collector.py
  - scripts/project_metrics/collectors/complexipy_collector.py
  - scripts/project_metrics/collectors/pydeps_collector.py
  - scripts/project_metrics/collectors/coverage_collector.py
  - scripts/project_metrics/runner.py
re_affirmed_by:
  - dec-066
---

## Context

`/project-metrics` v1 ships six collectors (git, scc, lizard, complexipy, pydeps, coverage). V2 will add at least three language-specific tiers (TS via `dependency-cruiser` + `eslint --format json`, Go via `golangci-lint --out-format json`, Rust via `cargo-geiger` / fallback to `lizard` for CCN). Without a shared protocol, each collector's integration boilerplate (argument parsing, subprocess orchestration, error handling, JSON shape) duplicates, and the runner grows a switch statement that must be edited for every new language tier.

The research findings (`RESEARCH_FINDINGS_tooling.md:226-231`) establish that collectors fall into two install categories (ephemeral via `uvx`/`npx`/`go install` vs pre-installed binary) and three availability outcomes (available, unavailable-install-me, not-applicable-no-matching-sources). A protocol must cover all of these uniformly.

The integration-ui research (`RESEARCH_FINDINGS_integration-ui.md:129-130`) identifies `memory-mcp/src/memory_mcp/metrics.py:compute_metrics()` as the local idiom for "structured computation that returns data + markdown rendering." The collector protocol extends this idea: each collector is a self-contained `compute_partial_metrics()` with a resolution phase added.

## Decision

Define a three-method protocol in `scripts/project_metrics/collectors/base.py`:

```
# Conceptual shape. Implementation details (dataclass, Protocol vs ABC, frozen vs mutable) are the
# implementer's call. The contract is what matters.

class Collector:
    name: str                          # stable identifier, used as JSON namespace key
    tier: int                          # 0 = universal, 1 = language/tool-specific
    required: bool                     # True only for GitCollector
    languages: frozenset[str]          # empty => language-agnostic (git, scc, lizard)

    def resolve(self, env) -> ResolutionResult:
        """Check whether this collector's tool is available for this run.
        MUST NOT execute the analysis. Returns one of:
          - Available(version: str, details: dict)
          - Unavailable(reason: str, install_hint: str)
          - NotApplicable(reason: str)    # e.g., Python collector on a Go-only repo
        Called exactly once per run, before collect()."""

    def collect(self, ctx) -> CollectorResult:
        """Perform the analysis. Called only when resolve() returned Available.
        Returns a CollectorResult with:
          - status: "ok" | "partial" | "error" | "timeout"
          - data: dict                   # this collector's JSON namespace contribution
          - issues: list[str]            # non-fatal problems (malformed file skipped, etc.)
          - duration_seconds: float
        MAY raise only for bugs in the collector itself. Analysis-level errors MUST downgrade
        to status='partial' or status='error' with data={} rather than propagating.
        MUST be deterministic given the same git SHA and file-system state."""

    def describe(self) -> CollectorDescription:
        """Static metadata: human-readable description, tool URL, expected runtime order of
        magnitude. Used by runner and report.py. Never invokes the tool."""
```

### Resolution outcomes — semantic difference matters

- **Available** — tool is present; `collect()` will run.
- **Unavailable** — tool is applicable but absent. The user can fix this by installing it. Reported with an actionable install hint. Shows up in MD as `_not computed — install <tool>_`.
- **NotApplicable** — tool does not apply to this repo (e.g., pydeps on a repo with zero `.py` files). Distinct from Unavailable because there is nothing for the user to do. Shows up in MD as `_not applicable for this repository_`.

The runner must respect this distinction — an Unavailable actionable gap is a user-facing call-to-action; NotApplicable is silent background information.

### Error isolation contract

One faulty collector cannot fail the whole run. The runner wraps each `collect()` call in a try/except:

- If the collector returns `status='error'` cleanly (it caught its own exception), the runner records it and moves on.
- If the collector raises uncaught, the runner catches, records the traceback (truncated) in `tool_availability[name].error`, sets that namespace to `{"status": "error", "data": null}`, and moves on.

The only fatal error is GitCollector raising — git is the hard floor, and without it there is no meaningful output to produce.

### Lifecycle ordering

1. **Registration** — collectors register themselves in a deterministic order: Git, Scc, Lizard, Complexipy, Pydeps, Coverage. Ordering is stable so JSON output is byte-reproducible across runs given identical inputs.
2. **Resolution pass** — runner calls `resolve()` on all collectors, populating `tool_availability`.
3. **Collection pass** — runner calls `collect()` only on collectors that resolved Available, in registration order.
4. **Composition** — runner's composer steps (`hotspot.py`, `trends.py`) read the namespace outputs; they are NOT collectors and NOT subject to the protocol.

### JSON contribution shape

Every collector writes into its own namespace key at the JSON root (`git`, `scc`, `lizard`, etc.). Collectors never write into the `aggregate` block directly — the runner composes aggregate values from namespace outputs via an explicit mapping in `schema.py`. This separation means a collector schema change never silently moves an aggregate column.

### V2 preservation

A v2 TS collector (`dependency_cruiser_collector.py`) implements the same three methods with `languages = frozenset({"typescript", "javascript"})` and contributes to a `dependency_cruiser` namespace. The runner and `schema.py` need to be told about it (add to registration list, add aggregate mappings). No change to the base class; no change to existing collectors.

## Considered Options

### Option 1: Single monolithic script with per-tool functions

**Pros:** Minimal scaffolding for v1; readable end-to-end in one file.

**Cons:** Zero extension seam. Adding the TS collector in v2 means finding six different places in the same file to edit and hoping the runner's assumptions about order/shape still hold. This reproduces the exact flat-decomposition problem that protocol-based designs solve.

### Option 2: Function-per-collector with a registry list

**Pros:** Lightweight; no base class.

**Cons:** Resolution and collection are different phases with different contracts (different return types, different failure semantics). Forcing them into a single function signature loses type safety at exactly the boundary where errors are most expensive. Registration becomes a tuple of two functions, which is awkward.

### Option 3: Protocol with resolve/collect/describe methods (chosen)

**Pros:** Clear contracts; testable in isolation; v2 extension is a new file + one line in a registration list; resolution pass gives the runner a clean `tool_availability` block without any collector having to invoke the tool twice.

**Cons:** More scaffolding for v1 (base class, result types, resolution envelope). Mitigated by the fact that the base class is small (three abstract methods, two small dataclasses) and each collector's boilerplate amortizes across the fleet.

### Option 4: Plugin discovery via entry points (`importlib.metadata.entry_points`)

**Pros:** Third parties could ship their own collectors as pip packages.

**Cons:** Gross over-design for v1. Praxion is not a plugin host for metrics collectors; it ships with a known fleet. Entry-point discovery adds import-time mystery and worsens debuggability. Reject on Simplicity First grounds.

## Consequences

**Positive:**

- V2 language tiers land without refactoring. A v2 TS collector is a new file plus two lines elsewhere (registration, schema mapping).
- Resolution and collection are cleanly separated: the resolution pass is fast (a few `subprocess.run` with `--version` or `shutil.which` calls) and completes before any heavy work; users see the availability summary immediately.
- Testing is trivial — each collector is a self-contained unit with a pure contract; `resolve()` can be stubbed, `collect()` can be exercised against fixture repos.
- Error isolation is a property of the runner, not of any individual collector — collectors can be written naturally without special runner-aware try/except scaffolding.

**Negative:**

- Three methods per collector feel like ceremony when the collector is a 40-line wrapper around one subprocess call (coverage collector is the extreme case). Mitigated by providing sensible `describe()` defaults in the base class.
- The Available/Unavailable/NotApplicable distinction is three states where two might seem enough. Worth the cost — see Context; the user-action signal differs between Unavailable and NotApplicable.
- Forces the implementer to think about resolution separately from collection. This is a feature, not a cost, because bugs in resolution (e.g., assuming `uvx` works when it doesn't) are debugged differently from bugs in analysis.
