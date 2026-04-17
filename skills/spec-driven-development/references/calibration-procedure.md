# Calibration Procedure

Structured assessment protocol for selecting the process calibration tier (Direct/Lightweight/Standard/Full/Spike) at task intake. The main agent runs this procedure before spawning any pipeline agents. See the [SDD skill](../SKILL.md#process-calibration) for integration with complexity triage.

## Signal Catalog

Collect these 6 signals from the user's request and quick codebase probes. Total collection time target: under 30 seconds.

### Phase 1 — Textual Signal Extraction (from request text)

| Signal | Collection Method | Scoring |
|--------|------------------|---------|
| **File count proxy** | Count explicit file/path mentions in the request. Include module/directory references that imply multiple files. | 0-1 files: 1pt, 2-3: 2pt, 4-8: 3pt, 9+: 4pt |
| **Behavior count** | Count distinct "when/should/must/does" verb phrases describing system actions. Each independent observable behavior is one count. | 0-1: 1pt, 2-3: 2pt, 4+: 3pt |
| **Architectural scope** | Check for indicators: new abstractions, interface changes, cross-cutting concerns, data model changes. Each indicator is binary (present/absent). | 0 indicators: 0pt, 1: 1pt, 2+: 2pt |
| **Request complexity** | Count conjunctions linking separate concerns ("and also", "as well as"), scope words ("all", "every", "across"), and multi-clause sentences describing distinct outcomes. | Low (0-1 markers): 0pt, Medium (2-3): 1pt, High (4+): 2pt |

### Phase 2 — Quick Codebase Probes (targeted, optional)

Run only when Phase 1 identified file mentions or directory references. Skip entirely for requests with no codebase references.

| Signal | Collection Method | Scoring |
|--------|------------------|---------|
| **Prior spec existence** | Check `.ai-state/specs/` for `SPEC_*.md` files relevant to the affected area. | No specs: 0pt, Specs exist: 1pt (brownfield risk) |
| **Test coverage signal** | If files identified, glob for corresponding test files (`tests/test_<module>.py`, `__tests__/<module>.test.ts`, etc.). | Tests exist: 0pt (lower risk), No tests: 1pt (higher risk) |

Phase 2 also refines the file count proxy: if the request mentions a directory, glob for actual file count and update the Phase 1 estimate.

### Spike Detection (independent of scoring)

Before computing the numeric score, check for spike indicators in the request:

- Exploratory language: "investigate", "explore", "figure out", "research", "evaluate options", "spike"
- Uncertain outcome: "not sure if", "might need to", "depends on what we find"
- No clear acceptance criteria: the request describes a question, not a desired behavior

When spike indicators are present, recommend **Spike** regardless of the numeric score. A spike can have any scope — the uncertainty is about outcome, not size.

## Calibration Matrix

Sum the signal scores to produce a composite score, then map to a tier:

| Score Range | Recommended Tier | Rationale |
|-------------|-----------------|-----------|
| 0-3 | Direct | Single-file, minimal behavior, no architectural scope |
| 4-6 | Lightweight | Few files, single behavior, clear scope |
| 7-10 | Standard | Multiple files, multiple behaviors, some architecture |
| 11+ | Full | Many files, many behaviors, cross-cutting architecture |

Spike bypasses the matrix — it is detected by language patterns, not by score.

**Boundary cases**: when the score falls exactly on a tier boundary (3, 6, 10), the procedure recommends the lower tier. The user can override to the higher tier if they judge the task warrants it. Default to less process — process can be added later, but overhead cannot be reclaimed.

## Evidence Output

Present the assessment as a structured block so the user can inspect per-signal reasoning:

```markdown
### Calibration Assessment

| Signal | Value | Score |
|--------|-------|-------|
| File count | 5 files mentioned (6 confirmed by glob) | 3 |
| Behavior count | 3 distinct behaviors | 2 |
| Architectural scope | 1 (new interface) | 1 |
| Prior specs | Yes (SPEC_auth_YYYY-MM-DD.md) | 1 |
| Test coverage | Tests exist for 4/6 files | 0 |
| Request complexity | Medium (2 conjunctions, 1 scope word) | 1 |
| **Total** | | **8** |

**Recommended tier**: Standard (score 8, range 7-10)
**Rationale**: Multiple files with distinct behaviors and a new interface. Brownfield area with existing specs.

Override? [user confirms or specifies different tier]
```

After the user confirms or overrides, log the decision and proceed with the selected tier.

## Calibration Log

Append each tier decision to `.ai-state/calibration_log.md`. Create the file on first use.

**Log format**:

```markdown
# Calibration Log

| Timestamp | Task | Signals | Score | Recommended | Actual | Source | Retrospective |
|-----------|------|---------|-------|-------------|--------|--------|---------------|
| 2026-03-15T10:00:00Z | Add OAuth2 flow | F:5 B:3 A:1 P:1 T:0 C:1 | 8 | Standard | Standard | recommended | [pending] |
| 2026-03-15T14:00:00Z | Fix typo in README | F:1 B:0 A:0 P:0 T:0 C:0 | 1 | Direct | Direct | recommended | correct |
```

**Field definitions**:

- **Timestamp**: ISO 8601 UTC
- **Task**: one-sentence description of the task
- **Signals**: abbreviated signal values — F=File count, B=Behavior count, A=Architectural scope, P=Prior specs, T=Test coverage (inverted: 1=no tests), C=Request complexity
- **Score**: composite numeric score
- **Recommended**: the tier the procedure recommended
- **Actual**: the tier actually used (may differ if overridden)
- **Source**: `recommended` (user accepted), `user-override` (user chose different tier)
- **Retrospective**: filled post-pipeline — `correct` (tier was appropriate), `under-calibrated` (should have been higher), `over-calibrated` (should have been lower), `[pending]` (not yet assessed)

## Assessment Examples

### Example 1: Direct Task

> "Fix the typo in `README.md` line 42 — 'recieve' should be 'receive'"

| Signal | Value | Score |
|--------|-------|-------|
| File count | 1 file (README.md) | 1 |
| Behavior count | 0 (no system behavior) | 1 |
| Architectural scope | 0 | 0 |
| Prior specs | No | 0 |
| Test coverage | N/A | 0 |
| Request complexity | Low (single clause) | 0 |
| **Total** | | **2** |

**Recommended**: Direct (score 2, range 0-3). Fix → verify → commit.

### Example 2: Standard Task

> "Add OAuth2 login alongside existing email/password auth. Users should be able to log in with Google, and existing accounts should be linkable."

| Signal | Value | Score |
|--------|-------|-------|
| File count | ~5 implied (auth module, config, UI, tests, routes) | 3 |
| Behavior count | 3 (Google login, existing login preserved, account linking) | 2 |
| Architectural scope | 1 (new auth provider interface) | 1 |
| Prior specs | Yes (SPEC_auth_YYYY-MM-DD.md) | 1 |
| Test coverage | Tests exist for auth module | 0 |
| Request complexity | Medium ("alongside", "and") | 1 |
| **Total** | | **8** |

**Recommended**: Standard (score 8, range 7-10). Full pipeline with SDD behavioral spec.

### Example 3: Full Task

> "Redesign the plugin system to support hot-reloading, versioned dependencies, and cross-plugin communication. All existing plugins must continue working."

| Signal | Value | Score |
|--------|-------|-------|
| File count | 12+ (plugin loader, registry, dependency resolver, IPC, all plugin adapters) | 4 |
| Behavior count | 4+ (hot-reload, versioning, cross-plugin IPC, backward compat) | 3 |
| Architectural scope | 2+ (new abstractions, cross-cutting, interface changes) | 2 |
| Prior specs | Yes (SPEC_plugins_YYYY-MM-DD.md) | 1 |
| Test coverage | Partial (loader tested, no IPC tests) | 1 |
| Request complexity | High ("all existing", "and...and...and") | 2 |
| **Total** | | **13** |

**Recommended**: Full (score 13, range 11+). Full pipeline with parallel execution, doc-engineer, spec archival.

## Composing with Complexity Triage

The calibration procedure and the [complexity triage](../SKILL.md#complexity-triage) are two stages of the same decision:

1. **Calibration** (this procedure) selects the process tier — how much pipeline machinery to deploy
2. **Complexity triage** (in the SDD skill) refines spec depth within the selected tier — how detailed the behavioral specification should be

They share the same signal vocabulary (file count, behavior count, architectural scope) but serve different purposes. Calibration runs first; triage runs during the architect's Phase 1 when the SDD skill is loaded for Standard/Full tasks.
