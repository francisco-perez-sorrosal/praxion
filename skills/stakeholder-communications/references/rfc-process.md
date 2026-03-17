# RFC Process

Patterns for authoring RFCs (Requests for Comments), managing review workflows, and recording technical decisions at the right level of formality.

## RFC Template

```markdown
# RFC: [Title]

**Author**: [Name]
**Date**: [Proposal date]
**Status**: [Draft | Under Review | Accepted | Rejected | Superseded by RFC-XXX]
**Reviewers**: [Names or teams]
**Decision deadline**: [Date -- when a decision is needed]

## Problem Statement

[What problem exists, who is affected, and why it matters. Include data or
examples that demonstrate the problem's scope. 3-5 sentences.]

## Proposal

[The recommended approach. Include enough technical detail for reviewers to
evaluate feasibility, but not so much that implementation decisions are locked in
prematurely. Diagrams, interface sketches, and data flow descriptions are
valuable here.]

### Key Design Decisions

- **[Decision 1]**: [Choice and reasoning]
- **[Decision 2]**: [Choice and reasoning]

## Alternatives Considered

### [Alternative A]
- **Approach**: [Brief description]
- **Pros**: [What this gets right]
- **Cons**: [Why it was not chosen]

### [Alternative B]
- **Approach**: [Brief description]
- **Pros**: [What this gets right]
- **Cons**: [Why it was not chosen]

## Trade-offs and Risks

| Trade-off / Risk | Impact | Mitigation |
| --- | --- | --- |
| [Risk 1] | [Severity and scope] | [How to mitigate] |
| [Risk 2] | [Severity and scope] | [How to mitigate] |

## Decision

**Decided**: [Date]
**Outcome**: [Accepted / Rejected / Modified]
**Rationale**: [Summary of why this outcome was chosen, capturing key reviewer feedback.]
```

### Writing Guidance

- **Problem statement**: prove the problem exists before proposing a solution. Reviewers who do not understand the problem cannot evaluate the proposal
- **Proposal**: describe interfaces and contracts, not implementation internals. The goal is stakeholder buy-in on the approach, not a code review
- **Alternatives**: include at least two alternatives. "Do nothing" is always a valid alternative -- explain why it is insufficient
- **Decision section**: leave blank when drafting. Fill in after the review period ends. This section is the historical record

## Review Workflow

### 1. Draft

Author writes the RFC and circulates to 1-2 trusted reviewers for early feedback before the formal review.

### 2. Circulate

Share the RFC with all affected stakeholders. Set a clear review deadline (typically 3-5 business days for standard RFCs, 1-2 weeks for cross-cutting changes). State explicitly who must review and who may optionally review.

### 3. Comment

Reviewers provide feedback inline. The author is responsible for responding to every comment -- either incorporating feedback, explaining why it was not adopted, or flagging it for discussion.

### 4. Decide

After the review period, the decision-maker (typically the tech lead or architect) records the outcome in the Decision section. If consensus was not reached, the decision-maker makes the call and documents the reasoning.

### 5. Record

Update the RFC status. Archive in a discoverable location (project wiki, `docs/decisions/`, or `adr/` directory). Link from relevant code or documentation.

## Lightweight Decision Records

When a full RFC is too heavy -- single-team decisions, reversible choices, or decisions that need recording but not discussion.

```markdown
# Decision: [Title]

**Date**: [Date]
**Deciders**: [Names]
**Status**: [Active | Superseded by [link]]

## Context
[2-3 sentences: what prompted this decision.]

## Decision
[1-2 sentences: what was decided.]

## Consequences
[What follows from this decision -- both positive and negative.]
```

### When to Use

- Decisions that affect only the authoring team
- Choices between equivalent alternatives where the team needs consistency
- Recording a decision that emerged from discussion but was never written down
- Documenting "why we did it this way" for future maintainers

## Scaling: RFC vs. Decision Record vs. Just Do It

| Signal | Format |
| --- | --- |
| Affects 2+ teams, changes public interface, new technology, high cost | Full RFC |
| Single-team, worth recording for future context, not easily rediscoverable | Lightweight decision record |
| Trivial, easily reversible, obvious from code context | No document needed -- decide and implement |

### Organizational Scaling

- **Small teams (2-5)**: informal RFCs via PR description or shared doc. Lightweight decision records for anything worth remembering
- **Medium teams (5-20)**: structured RFC template, designated reviewers, 3-5 day review period. Decision records in a `docs/decisions/` directory
- **Large organizations (20+)**: formal RFC process with numbered RFCs, cross-team review boards, explicit approval gates. RFC index for discoverability

## Common RFC Failure Modes

| Failure | Symptom | Fix |
| --- | --- | --- |
| RFC as rubber stamp | Decision already made, RFC is performative | Circulate before committing. If already decided, use a decision record |
| Review fatigue | Reviewers stop reading long RFCs | Keep RFCs focused -- one decision per RFC. Split compound proposals |
| No decision recorded | RFC discussed but outcome never documented | Require the Decision section before closing the review period |
| Wrong reviewers | Critical stakeholder not consulted | Map affected systems to owners before circulating |
| Stale RFC | Proposal approved but never implemented or conditions changed | Set expiration dates. Review open RFCs quarterly |
