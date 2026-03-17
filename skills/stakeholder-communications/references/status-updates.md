# Status Updates

Detailed templates and patterns for technical status reports, blocker escalations, and milestone announcements.

## Status Update Types

| Type | Frequency | Audience | Purpose |
| --- | --- | --- | --- |
| Weekly technical status | Weekly | Engineering lead, team | Progress visibility, early risk detection |
| Blocker escalation | As needed | Anyone who can unblock | Remove impediment quickly |
| Milestone announcement | At milestone | Broader team, stakeholders | Celebrate progress, reset expectations |

## Weekly Technical Status Template

```markdown
# Status: [Project/Feature Name] -- [Date]

**Health**: [GREEN / AMBER / RED]

## Progress
- [Completed item with measurable outcome]
- [Completed item with measurable outcome]
- [PR/commit references if relevant]

## Current Focus
- [Active work item] -- expected completion [date]
- [Active work item] -- expected completion [date]

## Blockers and Risks
- **[Blocker/Risk]**: [Description]. Owner: [name]. Mitigation: [plan]. Impact if unresolved: [consequence].

## Next Steps
- [Planned item] -- target [date]
- [Planned item] -- target [date]

## Metrics (optional)
- Test coverage: [X]% (+/- [Y]% from last week)
- Open issues: [N] (was [M])
- Build time: [X]s (target: [Y]s)
```

### Writing Guidance

- **Health indicator**: GREEN means on track with no significant risks. AMBER means at risk -- timeline, scope, or quality may be affected without intervention. RED means blocked or off track -- immediate attention needed.
- **Progress**: Report outcomes ("Migrated 3 endpoints to v2 API"), not activity ("Worked on API migration"). Include links to PRs or commits when the audience is technical.
- **Blockers**: Always include owner, mitigation plan, and impact. A blocker without a mitigation plan is just a complaint.
- **Metrics**: Include only when the audience tracks them. Do not pad with vanity metrics.

## Blocker Escalation Template

Use when a blocker persists beyond 24 hours or when immediate help is needed.

```markdown
# Blocker: [Short description]

**Severity**: [Critical / High / Medium]
**Blocked since**: [Date]
**Impact**: [What cannot proceed and the downstream effect]

## Context
[1-3 sentences explaining the situation. Include what was attempted.]

## Ask
[Specific action needed from the reader. Name the person or team if known.]

## If Unresolved
[What happens if this is not resolved by [date]. Be specific: "Release X will slip by Y days" not "things will be delayed."]
```

### Escalation Principles

- **Escalate early** -- waiting "one more day" turns a 1-day slip into a week
- **Be specific about the ask** -- "I need access to the staging database" not "I need help"
- **Quantify impact** -- "Blocks 3 downstream tasks affecting release date" not "this is blocking"
- **Propose a workaround** if one exists, even if it is not ideal -- it shows you have tried to self-solve

## Milestone Announcement Template

Use when a significant deliverable is complete -- feature shipped, migration finished, system cutover.

```markdown
# Milestone: [What was achieved]

**Date**: [Completion date]
**Team**: [Contributors]

## Summary
[2-3 sentences: what was delivered, why it matters, key numbers.]

## What Changed
- [Change 1 with user-visible impact]
- [Change 2 with user-visible impact]

## What's Next
- [Immediate follow-up work]
- [Future phases or iterations]

## Acknowledgments (optional)
[Call out specific contributions or cross-team collaboration.]
```

## Audience Adaptation

The same underlying information is framed differently depending on the audience.

### Example: Database Migration Progress

**To engineering peers**:
> Migrated 12 of 18 tables to the new schema. The `orders` table migration required a backfill script due to NULL values in `shipping_address` (see PR #847). Remaining tables have no data quality issues -- expecting completion by Thursday. Test suite passes on the new schema with 2 flaky tests under investigation.

**To engineering leadership**:
> Database migration is 67% complete (12/18 tables). On track for Thursday completion. One data quality issue was found and resolved in the orders table. No impact on the release timeline.

**To cross-functional stakeholders**:
> The infrastructure upgrade supporting faster order processing is on track. We completed a major milestone this week and expect to finish the remaining work by Thursday. No changes to the release schedule.

### Adaptation Rules

- **Peers**: include technical specifics (table names, PR numbers, error details)
- **Leadership**: include progress percentage, timeline impact, resource needs
- **Cross-functional**: translate to business outcomes, omit technical implementation details
- **All audiences**: lead with the health indicator, state next steps clearly
