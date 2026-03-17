# Prioritization Frameworks

Detailed mechanics, scoring scales, and worked examples for each framework. Load this reference when applying a specific framework or when the framework selection table in SKILL.md needs more depth.

## Framework Selection Matrix

| Criterion | RICE | MoSCoW | WSJF | Kano | ICE |
|-----------|------|--------|------|------|-----|
| Data requirements | High (usage data) | Low (stakeholder input) | Medium (cost-of-delay estimates) | Medium (user surveys) | Low (team judgment) |
| Speed | Slow | Fast | Medium | Slow | Fast |
| Quantitative rigor | High | Low | High | Medium | Medium |
| Best for | Mature products | Fixed scope | Flow/queue systems | User satisfaction | Rapid triage |
| Team size | Any | Any with decision authority | Scaled teams | Product teams | Small teams |

## RICE

**Reach x Impact x Confidence / Effort**

Score each dimension, then compute the composite.

| Dimension | Scale | Description |
|-----------|-------|-------------|
| **Reach** | Number of users/events per quarter | How many people or workflows this affects |
| **Impact** | 0.25 (minimal), 0.5 (low), 1 (medium), 2 (high), 3 (massive) | Magnitude of change per person reached |
| **Confidence** | 100% (high), 80% (medium), 50% (low) | Certainty in the estimates |
| **Effort** | Person-months (or person-weeks for small teams) | Total resources required |

**Formula**: `RICE = (Reach x Impact x Confidence) / Effort`

### Worked Example: Ecosystem Skill Prioritization

Scoring three pending ideas from an IDEA_LEDGER:

| Item | Reach | Impact | Confidence | Effort | RICE Score |
|------|-------|--------|------------|--------|------------|
| Memory v2.0 intelligence upgrade | 1 (single user) | 3 (massive) | 80% | 3 person-weeks | 0.8 |
| TypeScript development skill | 1 (single user) | 2 (high) | 80% | 2 person-weeks | 0.8 |
| Roadmap planning skill | 1 (single user) | 2 (high) | 100% | 1 person-week | 2.0 |

For single-user ecosystems, Reach is always 1 -- the differentiator becomes Impact x Confidence / Effort. RICE still works but ICE may be more natural at this scale.

**When to use RICE**: mature products with real usage data where reach varies meaningfully across features.

## MoSCoW

**Must / Should / Could / Won't**

Classify each item into exactly one category. No scoring -- pure categorical.

| Category | Definition | Constraint |
|----------|-----------|------------|
| **Must** | Failure without it. Non-negotiable for this release/cycle | Typically 60% of capacity |
| **Should** | Important but not critical. Workaround exists | Next 20% of capacity |
| **Could** | Desirable. Include if time permits | Remaining 20% of capacity |
| **Won't** | Agreed out of scope for this cycle. May return later | 0% -- explicit exclusion |

**The 60/20/20 rule**: allocate no more than 60% of available capacity to Must items. This leaves room for Should and Could items and protects against estimation errors.

### Worked Example: Quarterly Ecosystem Planning

Given 4 weeks of capacity:

| Item | Category | Rationale |
|------|----------|-----------|
| Fix sentinel SH03 staleness checks | **Must** | Ecosystem health regression; blocks downstream |
| Roadmap planning skill | **Must** | Highest priority gap from lifecycle audit |
| Memory v2.0 Phase 1 | **Should** | Valuable but not blocking other work |
| TypeScript development skill | **Could** | Nice to have; no current TS projects |
| Multi-project memory split | **Won't** | Architectural decision not yet resolved |

**When to use MoSCoW**: fixed scope or timeboxed releases where hard trade-offs between items are needed. Works well for stakeholder alignment.

## WSJF (Weighted Shortest Job First)

**(Business Value + Time Criticality + Risk Reduction) / Job Size**

All dimensions use relative Fibonacci sizing within the current backlog: 1, 2, 3, 5, 8, 13.

| Dimension | Question to Answer |
|-----------|-------------------|
| **Business Value** | How much value does this deliver to the user or project? |
| **Time Criticality** | Does the value decay if we delay? Are there deadlines? |
| **Risk Reduction** | Does this reduce risk or enable future opportunities? |
| **Job Size** | How much effort relative to other items? |

**Formula**: `WSJF = (BV + TC + RR) / Job Size`

### Worked Example

| Item | BV | TC | RR | Job Size | WSJF |
|------|----|----|-----|----------|------|
| Roadmap planning skill | 8 | 5 | 3 | 3 | 5.3 |
| Memory v2.0 Phase 1 | 5 | 2 | 5 | 5 | 2.4 |
| Fix sentinel SH03 | 3 | 8 | 5 | 2 | 8.0 |

The sentinel fix scores highest due to time criticality (ecosystem health degrades further with delay) and small job size.

**When to use WSJF**: flow-based systems where cost of delay matters. Effective for continuous delivery teams managing a queue of work.

## Kano

**Basic / Performance / Delighter classification**

Kano classifies features by their relationship to user satisfaction, not by a numeric score. Apply it when deciding what type of value a feature delivers.

| Category | If Present | If Absent | Priority Implication |
|----------|-----------|-----------|---------------------|
| **Basic** (must-be) | No increase in satisfaction | Strong dissatisfaction | Build first -- table stakes |
| **Performance** (one-dimensional) | Proportional satisfaction increase | Proportional dissatisfaction | Build next -- competitive differentiator |
| **Delighter** (attractive) | Disproportionate satisfaction | No dissatisfaction | Build when basics and performance are covered |
| **Indifferent** | No effect | No effect | Skip -- no value |
| **Reverse** | Dissatisfaction | Satisfaction | Avoid -- actively harmful |

### Worked Example: Ecosystem Feature Classification

| Feature | Category | Rationale |
|---------|----------|-----------|
| Skills load correctly on activation | **Basic** | Expected behavior; broken = unusable |
| Prioritization framework in roadmap skill | **Performance** | More rigorous = better roadmaps |
| Auto-generated dependency diagrams | **Delighter** | Unexpected; high value when present |
| Verbose logging in every agent | **Indifferent** | No user-facing impact |

**Dynamic decay**: today's delighter becomes tomorrow's performance expectation and eventually a basic requirement. Reassess periodically.

**When to use Kano**: user-facing products where understanding the nature of satisfaction matters more than numeric ranking. Less useful for internal tooling where the user and builder are the same person.

## ICE

**Impact x Confidence x Ease**

Each dimension scored 1-10. Multiply for composite score (range: 1-1000).

| Dimension | Scale | Description |
|-----------|-------|-------------|
| **Impact** | 1-10 | How much this moves the needle on the target goal |
| **Confidence** | 1-10 | How certain the team is about Impact and Ease estimates |
| **Ease** | 1-10 | How easy to implement (10 = trivial, 1 = massive) |

**Formula**: `ICE = Impact x Confidence x Ease`

### Worked Example: Quick Triage of IDEA_LEDGER Pending Items

| Item | Impact | Confidence | Ease | ICE Score |
|------|--------|------------|------|-----------|
| Roadmap planning skill | 8 | 9 | 7 | 504 |
| Memory v2.0 Phase 1 | 7 | 6 | 4 | 168 |
| TypeScript development skill | 6 | 8 | 6 | 288 |
| Multi-project memory | 5 | 3 | 3 | 45 |

High confidence and ease push the roadmap planning skill to the top. Multi-project memory scores lowest due to low confidence (architectural unknowns) and low ease.

**When to use ICE**: rapid triage, small teams, early-stage projects where data is scarce and speed matters. The default for this ecosystem.

## Combining Frameworks

Frameworks are not mutually exclusive. Common combinations:

- **Kano + RICE**: classify features by Kano category first, then RICE-score within each category. Ensures basics are covered before optimizing delighters
- **MoSCoW + ICE**: MoSCoW for strategic bucketing, ICE for ordering within buckets
- **WSJF for queue, Kano for discovery**: WSJF sequences the delivery queue; Kano informs which features to investigate next

## Scoring Hygiene

- **Score as a team** when possible -- individual scores carry individual bias
- **Re-score periodically** -- estimates decay as context changes
- **Document assumptions** -- a score without rationale is a guess, not a decision
- **Compare within a scoring session** -- do not compare scores across different sessions or different scorers
- **Scores inform, judgment decides** -- never let a formula override clear thinking
