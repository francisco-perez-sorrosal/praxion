# stakeholder-communications

Developer-oriented stakeholder communication patterns for software engineers. Covers technical status updates, RFC and design proposal authoring, release announcements, breaking change notifications, migration guides, technical demo scripts, and approval workflows.

## When to Use

- Writing status reports on technical work (weekly updates, blocker escalations, milestone announcements)
- Authoring RFCs or design proposals for technical decisions
- Communicating releases or breaking changes to downstream consumers
- Preparing demo scripts for sprint reviews or architecture walkthroughs
- Seeking architecture, security, or API approval
- Recording technical decisions (lightweight decision records)

## Activation

Activates automatically when the task context matches communication patterns (status update, RFC, release announcement, demo script, approval workflow). Reference explicitly with "load the `stakeholder-communications` skill."

## Skill Contents

| File | Purpose |
| --- | --- |
| `SKILL.md` | Core principles, communication type selection, overview of all patterns, anti-patterns, checklist |
| `references/status-updates.md` | Templates for weekly status, blocker escalation, milestone announcements, audience adaptation |
| `references/rfc-process.md` | RFC template, review workflow, lightweight decision records, scaling guidance |
| `references/release-communications.md` | Release announcement template, breaking change notifications, migration guides, versioning communication |

## Related Skills

- **[spec-driven-development](../spec-driven-development/)** -- behavioral specifications that translate RFC decisions into implementable requirements
- **[doc-management](../doc-management/)** -- documentation artifacts (READMEs, changelogs, API docs) that complement stakeholder communications
- **[software-planning](../software-planning/)** -- planning documents that feed status updates with concrete progress data
- **[code-review](../code-review/)** -- structured review methodology supporting approval workflows
