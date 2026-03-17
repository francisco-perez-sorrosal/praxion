# Roadmap Formats

Templates and guidance for different roadmap representations. Load this reference when choosing a format or when building a roadmap from the templates.

## Format Selection

| Format | Best For | Avoids | Default? |
|--------|----------|--------|----------|
| **Now-Next-Later** | Evolving scope, uncertain timelines, continuous delivery | False deadline precision | Yes -- default for this ecosystem |
| **Timeline** | Committed dates, external stakeholder coordination | Scope flexibility |
| **Theme-based** | Strategic alignment, communicating direction to leadership | Granular item tracking |
| **Outcome-based** | OKR-driven organizations, measuring impact over output | Feature-level detail |

When in doubt, use **Now-Next-Later**. It communicates priority and intent without committing to dates that will change.

## Now-Next-Later

Three time horizons based on confidence, not calendar dates.

| Horizon | Confidence | Typical Scope | Detail Level |
|---------|-----------|---------------|--------------|
| **Now** | High -- actively working or about to start | Current sprint/cycle | Full: scope, dependencies, owner, next step |
| **Next** | Medium -- validated, ready when capacity opens | 1-3 months out | Moderate: scope, dependencies, effort estimate |
| **Later** | Low -- promising but needs more discovery | 3+ months out | Light: title, rationale, open questions |

### Template

```markdown
# Roadmap: [Area Name]

**Updated**: [ISO 8601 timestamp]
**Framework**: [prioritization framework used]
**Review cadence**: [e.g., every 6 weeks, after each promethean run]

## Now

### [Item 1 title]
- **Score**: [framework score]
- **Effort**: [S/M/L]
- **Dependencies**: [none | blocking items]
- **Owner**: [agent or person]
- **Status**: [not started | in progress | blocked]
- **Next step**: [specific action]

### [Item 2 title]
...

## Next

### [Item 3 title]
- **Score**: [framework score]
- **Effort**: [S/M/L]
- **Dependencies**: [blocking items]
- **Blocked by**: [Now items that must complete first]
- **Open questions**: [if any]

## Later

### [Item 4 title]
- **Score**: [framework score]
- **Rationale**: [why this is worth tracking]
- **Open questions**: [what needs resolution before moving to Next]

## Done (This Cycle)

- [Completed item] -- [completion date]

## Dependency Graph

[See dependency-mapping.md for notation]

## Decision Log

- [Date]: [Decision and rationale]
```

### Promotion Criteria

| Transition | Trigger |
|-----------|---------|
| Later --> Next | Open questions resolved, scope is estimable, priority score warrants it |
| Next --> Now | Dependencies cleared, capacity available, commitment made |
| Now --> Done | Delivered and verified (or explicitly cancelled) |
| Any --> Removed | No longer relevant; document in Decision Log |

### Review Cadence

Review the roadmap at these triggers:

- After each promethean run (new ideas to incorporate)
- When a "Now" item completes (capacity freed; promote from "Next")
- When priorities shift (re-score and re-sequence)
- On a fixed cadence (every 4-6 weeks) to catch stale items

## Timeline-Based

Calendar-anchored roadmap with date commitments. Use only when external coordination requires dates.

### Template

```markdown
# Roadmap: [Area Name]

**Updated**: [ISO 8601 timestamp]

## Q1 2026 (Jan - Mar)

### Month 1: [Theme or focus]
- [ ] [Item] -- [effort] -- [owner]
- [ ] [Item] -- [effort] -- [owner]

### Month 2: [Theme or focus]
- [ ] [Item] -- [effort] -- [owner]

### Month 3: [Theme or focus]
- [ ] [Item] -- [effort] -- [owner]

## Q2 2026 (Apr - Jun)

### [Similar structure]

## Dependencies

[Cross-quarter dependencies noted here]

## Risks

- [Risk]: [mitigation]
```

**Caution**: timeline roadmaps create implicit promises. Every date becomes an expectation. Use buffer time (20-30% of estimated effort) and mark uncertain items explicitly.

## Theme-Based

Groups items by strategic theme rather than time horizon. Useful for communicating direction without granular sequencing.

### Template

```markdown
# Roadmap: [Area Name]

**Updated**: [ISO 8601 timestamp]
**Planning horizon**: [e.g., Next 2 quarters]

## Theme: [Strategic Direction 1]

**Objective**: [What this theme achieves]

| Item | Effort | Priority | Status |
|------|--------|----------|--------|
| [Feature A] | M | High | Next |
| [Feature B] | S | Medium | Later |

## Theme: [Strategic Direction 2]

**Objective**: [What this theme achieves]

| Item | Effort | Priority | Status |
|------|--------|----------|--------|
| [Feature C] | L | High | Now |
| [Feature D] | M | Low | Later |

## Cross-Theme Dependencies

- [Feature C] --> [Feature A] (Theme 2 enables Theme 1)

## Unthemed Items

Items that do not fit a current theme. Review for relevance.

- [Maintenance item] -- [rationale for inclusion]
```

### Theme Examples for This Ecosystem

| Theme | Objective | Example Items |
|-------|-----------|---------------|
| Pipeline Maturity | Close gaps in the ideation-to-verification pipeline | Roadmap planning, test infrastructure |
| Developer Experience | Reduce friction in daily development workflows | Memory v2.0, language skills |
| Ecosystem Quality | Improve health scores and coherence | Sentinel enhancements, cross-reference fixes |
| Distribution | Make the ecosystem usable by others | Plugin marketplace, documentation |

## Outcome-Based

Maps features to measurable outcomes (OKRs, KPIs, or success metrics). Each item justifies its existence by the outcome it serves.

### Template

```markdown
# Roadmap: [Area Name]

**Updated**: [ISO 8601 timestamp]
**Planning period**: [e.g., Q1 2026]

## Outcome 1: [Measurable goal]

**Key Result**: [How we measure success]
**Current**: [Baseline measurement]
**Target**: [Target measurement]

### Initiatives

| Item | Contribution | Effort | Status |
|------|-------------|--------|--------|
| [Feature A] | [How it moves the metric] | M | Now |
| [Feature B] | [How it moves the metric] | S | Next |

## Outcome 2: [Measurable goal]

**Key Result**: [Measurement]
**Current**: [Baseline]
**Target**: [Target]

### Initiatives

| Item | Contribution | Effort | Status |
|------|-------------|--------|--------|
| [Feature C] | [Contribution] | L | Now |

## Items Without Clear Outcomes

Review these -- if no outcome can be articulated, the item may not be worth building.

- [Item] -- [why it exists despite no clear outcome]
```

### Outcome Examples for This Ecosystem

| Outcome | Key Result | Initiatives |
|---------|-----------|-------------|
| Reduce pipeline friction | Time from idea to implementation < 1 session | Roadmap planning skill, improved promethean flow |
| Improve ecosystem health | Sentinel health grade >= A- consistently | Fix critical findings, sentinel enhancements |
| Expand language coverage | 3+ language skills with full quality gates | TypeScript skill, Rust skill |

## Hybrid Formats

Combine formats when a single format does not capture all dimensions:

- **Theme + Now-Next-Later**: themes provide strategic context; NNL provides sequencing within each theme
- **Outcome + Timeline**: outcomes provide the "why"; timeline provides the "when" for external coordination
- **Theme + Outcome**: themes group related work; outcomes within each theme provide measurable targets

Avoid combining more than two formats -- complexity erodes the roadmap's primary value as a communication tool.
