---
name: stakeholder-communications
description: Developer-oriented stakeholder communication patterns for software engineers.
  Covers technical status updates, RFC and design proposal authoring, release announcements,
  breaking change notifications, migration guides, technical demo scripts, and approval
  workflows. Use when writing status reports on technical work, authoring RFCs or design
  docs, communicating releases or breaking changes to downstream consumers, preparing
  sprint demo scripts, seeking architecture or security approval, or drafting technical
  decision records.
allowed-tools: [Read, Write, Edit, Glob, Grep, Bash]
compatibility: Claude Code
---

# Stakeholder Communications

Patterns and templates for the communications that software engineers produce as part of technical work -- status updates, design proposals, release announcements, demo scripts, and approval requests.

**Satellite files** (loaded on-demand):

- [references/status-updates.md](references/status-updates.md) -- templates and patterns for technical status reports, blocker escalations, milestone announcements
- [references/rfc-process.md](references/rfc-process.md) -- RFC authoring, review workflows, lightweight decision records, scaling guidance
- [references/release-communications.md](references/release-communications.md) -- release announcements, breaking change notifications, migration guides, versioning communication

## Scope

This skill covers **developer-produced communications** -- artifacts that engineers write to inform, propose, or seek approval. It does not cover project management concerns (sprint planning, Jira workflows, standup formats) or documentation artifacts (READMEs, API docs, changelogs -- see the `doc-management` skill).

## Core Principles

**Audience determines depth.** Engineering peers need technical detail; leadership needs impact and timeline. Identify the audience before writing and adjust accordingly.

**Structure over prose.** Use templates, headings, and bullet points. Stakeholders scan -- they do not read walls of text. Front-load the most important information.

**Actionable over informative.** Every communication should make clear what the reader needs to do (or explicitly state that no action is required). A status update without clear next steps or a decision request without options is incomplete.

**Minimal and timely.** Write the shortest document that achieves its purpose. Send it when the information is still actionable -- a late blocker escalation is a missed blocker escalation.

## Communication Type Selection

Select the right format based on the communication need:

| Need | Format | Reference |
| --- | --- | --- |
| Regular progress visibility | Weekly technical status | [status-updates.md](references/status-updates.md) |
| Blocked and need help | Blocker escalation | [status-updates.md](references/status-updates.md) |
| Significant milestone reached | Milestone announcement | [status-updates.md](references/status-updates.md) |
| Proposing a technical approach | RFC / design doc | [rfc-process.md](references/rfc-process.md) |
| Recording a decision already made | Lightweight decision record | [rfc-process.md](references/rfc-process.md) |
| Shipping a version | Release announcement | [release-communications.md](references/release-communications.md) |
| Breaking change for consumers | Breaking change notification | [release-communications.md](references/release-communications.md) |
| Helping consumers upgrade | Migration guide | [release-communications.md](references/release-communications.md) |
| Showing work to stakeholders | Demo script | See [Demo Scripts](#demo-scripts) below |
| Need sign-off before proceeding | Approval request | See [Approval Workflows](#approval-workflows) below |

## Status Updates

Technical status updates answer three questions: Is this on track? Are there blockers? What happens next?

### Structure

1. **Health indicator** -- green (on track), amber (at risk), red (blocked or off track)
2. **Progress since last update** -- completed items, measurable outcomes
3. **Current focus** -- what is actively being worked on
4. **Blockers and risks** -- anything impeding progress, with owner and mitigation plan
5. **Next steps** -- planned work for the next period, with expected outcomes

### Audience Adaptation

- **Engineering peers**: include technical detail (PRs merged, test coverage changes, architecture decisions made)
- **Engineering leadership**: focus on milestone progress, risk assessment, resource needs
- **Cross-functional stakeholders**: translate technical progress to business impact, avoid jargon

--> See [references/status-updates.md](references/status-updates.md) for templates, blocker escalation patterns, and worked examples.

## RFC / Design Proposals

Use an RFC when a technical decision affects multiple teams, changes a public interface, or has significant cost/risk. Skip the RFC for decisions that are easily reversible or affect only the author's code.

### RFC Structure

1. **Problem statement** -- what problem exists and why it matters
2. **Proposal** -- the recommended approach with enough detail for reviewers to evaluate
3. **Alternatives considered** -- other approaches and why they were not chosen
4. **Trade-offs and risks** -- what the proposal sacrifices and what could go wrong
5. **Decision** -- the outcome after review (filled in after discussion)

### When to RFC vs. When to Skip

| Signal | Action |
| --- | --- |
| Affects 2+ teams or services | RFC |
| Changes a public API or data schema | RFC |
| Introduces a new dependency or technology | RFC |
| Cost exceeds a sprint of work | RFC |
| Easily reversible, single-team scope | Decide and document inline |
| Trivial implementation choice | Just do it |

### Relationship to Behavioral Specs

RFCs define the *why* and *what* at the system level. Behavioral specifications (see the `spec-driven-development` skill) define the *what* at the implementation level with testable acceptance criteria. For medium/large features, the RFC produces a decision; the behavioral spec translates that decision into implementable requirements.

--> See [references/rfc-process.md](references/rfc-process.md) for the full RFC template, review workflow, lightweight decision records, and scaling guidance.

## Release Communications

Release communications inform downstream consumers about changes. The audience is anyone who depends on the released artifact -- other teams, external users, or automated systems.

### Release Announcement Structure

1. **Version and date**
2. **Highlights** -- 3-5 most important changes, user-impact language
3. **Breaking changes** -- clearly labeled, with migration path
4. **New features** -- what was added and how to use it
5. **Bug fixes** -- what was broken and how it was fixed
6. **Deprecations** -- what will be removed in a future version and what to use instead

### Breaking Change Communication

Breaking changes require extra care:

- **Announce early** -- notify consumers before the release, not after
- **Label clearly** -- use `[BREAKING]` prefix or equivalent marker
- **Provide migration steps** -- before/after code examples, not just a description of what changed
- **Offer a transition period** -- when possible, deprecate before removing
- **Name a contact** -- someone consumers can reach for migration help

--> See [references/release-communications.md](references/release-communications.md) for templates, migration guide structure, and versioning communication patterns.

## Demo Scripts

Technical demos show working software to stakeholders. A demo script ensures the presentation is focused, reproducible, and time-boxed.

### Demo Script Structure

1. **Context** (30 seconds) -- what problem this addresses and why it matters
2. **Setup** -- prerequisites, environment state, test data needed
3. **Walkthrough** -- step-by-step actions with expected outcomes
4. **Key talking points** -- 2-3 things to emphasize during the demo
5. **Questions to ask** -- prompts to drive stakeholder feedback
6. **Fallback plan** -- what to show if the live demo fails (screenshots, recorded video)

### Demo Principles

- **Show behavior, not code** -- stakeholders care about what the system does, not how it is implemented
- **Use realistic data** -- dummy data undermines credibility
- **Rehearse the path** -- run through the exact sequence before the demo to catch environment issues
- **Time-box strictly** -- plan for 5-10 minutes of demo, leave equal time for discussion
- **Script transitions** -- "Now that we've seen X, let me show how that connects to Y"

### Audience Adaptation

- **Sprint review (team)**: focus on acceptance criteria met, technical decisions made, trade-offs
- **Stakeholder demo (leadership)**: focus on user value delivered, progress toward goals
- **Architecture walkthrough (technical)**: focus on design decisions, integration points, constraints

## Approval Workflows

Seek technical approval when a decision is irreversible, costly, or affects security/compliance. Approval is not bureaucracy -- it is risk-proportional review.

### When to Seek Approval

| Change Type | Approval Needed | Approver |
| --- | --- | --- |
| New external dependency | Yes | Tech lead or architect |
| Public API change | Yes | API owner + affected consumers |
| Data schema migration | Yes | Data owner + dependent teams |
| Security-sensitive change | Yes | Security team |
| Infrastructure cost increase | Yes | Engineering manager or budget owner |
| Internal refactoring | No (inform, don't ask) | -- |
| Feature behind a flag | No (standard review) | Code reviewer |

### Approval Request Structure

1. **What** -- the specific change requiring approval
2. **Why** -- the business or technical motivation
3. **Impact** -- who and what is affected
4. **Alternatives** -- what else was considered
5. **Risk** -- what could go wrong and how to mitigate
6. **Timeline** -- when the decision is needed and why

### Lightweight vs. Formal Approval

- **Lightweight**: Slack message or PR comment with the decision context. Suitable for low-risk, single-approver decisions
- **Formal**: RFC with structured review period. Suitable for high-risk, multi-stakeholder decisions (feeds into the RFC process)

## Anti-Patterns

| Anti-Pattern | Fix |
| --- | --- |
| **Status update as activity log** -- listing tasks completed without context | Report outcomes and progress toward goals, not activity |
| **RFC as fait accompli** -- writing an RFC after the decision is made | Circulate before committing; if already decided, use a decision record instead |
| **Burying breaking changes** -- mentioning breaking changes mid-paragraph | Label with `[BREAKING]` prefix, place in a dedicated section |
| **Demo without rehearsal** -- assuming the live environment will work | Run through the exact demo sequence beforehand; prepare a fallback |
| **Over-communicating** -- sending updates nobody reads | Match frequency and detail to audience need; ask if the cadence is right |
| **Under-communicating blockers** -- hoping blockers resolve themselves | Escalate within 24 hours with a clear ask and impact statement |
| **Approval as bottleneck** -- requiring approval for low-risk changes | Use the decision table above; only gate irreversible or high-impact decisions |

## Integration with Other Skills

- **[spec-driven-development](../spec-driven-development/SKILL.md)** -- behavioral specifications that translate RFC decisions into implementable requirements with testable acceptance criteria
- **[doc-management](../doc-management/SKILL.md)** -- documentation artifacts (READMEs, changelogs, API docs) that complement stakeholder communications
- **[software-planning](../software-planning/SKILL.md)** -- planning documents (IMPLEMENTATION_PLAN.md, WIP.md) that feed status updates with concrete progress data
- **[code-review](../code-review/SKILL.md)** -- structured review methodology that supports the approval workflow for code-level decisions

## Checklist

Before sending a stakeholder communication:

### Content Quality

- [ ] Audience identified and content depth matched accordingly
- [ ] Purpose is clear within the first two sentences
- [ ] Actionable: reader knows what to do (or that no action is needed)
- [ ] Structured with headings, bullets, or tables -- not prose walls
- [ ] Jargon appropriate to the audience (technical for peers, impact-focused for leadership)

### Completeness

- [ ] All required sections present for the communication type (see templates in references)
- [ ] Breaking changes labeled and migration path provided
- [ ] Blockers include owner, impact, and mitigation plan
- [ ] Decision requests include options with trade-offs

### Timing

- [ ] Sent while the information is still actionable
- [ ] Breaking changes communicated before the release, not after
- [ ] Approval requests sent with enough lead time for review
