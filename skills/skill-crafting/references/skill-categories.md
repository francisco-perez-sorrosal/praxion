# Skill Categories

Nine recurring skill archetypes identified from Anthropic's internal practice of managing hundreds of active skills. Skills should fit cleanly into one category -- skills that straddle several are often too broad. Reference material for the [Skill Creator](../SKILL.md) skill.

Use this taxonomy when planning a new skill to guide structural decisions: what content type to use, what resources to bundle, and how to verify the skill works.

## 1. Library & API Reference

Skills that explain how to correctly use a library, CLI, or SDK. Cover both internal libraries and common ones the agent has trouble with.

**Typical structure**: Reference code snippets folder + gotchas list + API patterns
**Content type**: Worked examples and reference files (medium freedom)
**Key signal**: Agent repeatedly makes the same mistake with a specific library

```text
example-library-skill/
├── SKILL.md          # Usage patterns, gotchas, when to use which method
└── references/
    ├── api-surface.md    # Complete method signatures
    ├── gotchas.md        # Common mistakes and corrections
    └── snippets/         # Ready-to-use code patterns
```

## 2. Product Verification

Skills that describe how to test or verify that code is working. Often paired with external tools (Playwright, tmux, screenshots) for doing the verification.

**Typical structure**: Verification scripts + assertion patterns + tool integration
**Content type**: Scripts (low freedom) -- verification must be deterministic
**Key signal**: Agent produces code that looks correct but fails in practice

Techniques: video recordings of outputs, programmatic assertions at each step, visual analysis of rendered outputs, comparison against reference screenshots.

## 3. Data Fetching & Analysis

Skills that connect to data and monitoring stacks. Provide credential-secured data access, dashboard information, and common query workflows.

**Typical structure**: Query templates + schema references + credential handling
**Content type**: Mixed -- scripts for data access, prose for analysis guidance
**Key signal**: Agent needs project-specific schemas, credentials, or query patterns

## 4. Business Process & Team Automation

Simple instruction-based skills automating repetitive workflows: standup generation, ticket creation, weekly recaps, status reports.

**Typical structure**: Workflow instructions + log files for consistency
**Content type**: Prose instructions (high freedom) + append-only logs for state
**Key signal**: A recurring manual task that follows a consistent pattern

Store previous results in log files so the agent maintains consistency across executions (e.g., knowing what was reported last week when generating this week's standup).

## 5. Code Scaffolding & Templates

Skills that generate framework boilerplate for specific functions in a codebase. Especially useful when scaffolding has natural language requirements that code alone cannot address.

**Typical structure**: Template files + generation scripts + naming conventions
**Content type**: Assets (templates) + prose (requirements scripts cannot capture)
**Key signal**: Team repeatedly scaffolds the same kind of component

Examples: `new-service-workflow` (scaffolds a service with your annotations), `new-migration` (migration file template plus common gotchas), `create-app` (new internal app with auth, logging, and deploy config pre-wired).

## 6. Code Quality & Review

Skills that enforce organizational code standards and assist with code review. Can include deterministic scripts or tools for maximum robustness.

**Typical structure**: Linting rules + review checklists + automated scripts
**Content type**: Scripts (low freedom) for deterministic checks + prose for judgment calls
**Key signal**: Code review feedback is repetitive or inconsistent

Can integrate with hooks or GitHub Actions for continuous enforcement. See [content-and-development.md](content-and-development.md#iterative-author-tester-workflow) for the adversarial review pattern.

## 7. CI/CD & Deployment

Skills that help fetch, push, and deploy code. May reference other skills for data collection (e.g., a deployment skill that checks monitoring dashboards).

**Typical structure**: Deployment scripts + environment configs + rollback procedures
**Content type**: Scripts (low freedom) -- deployment must be deterministic
**Key signal**: Deployment process involves multiple manual steps or tool-specific knowledge

## 8. Runbooks

Skills that take a symptom, walk through a multi-tool investigation, and produce a structured report. Map symptoms to appropriate diagnostic tools.

**Typical structure**: Decision trees + diagnostic scripts + report templates
**Content type**: Conditional workflows + scripts for data gathering
**Key signal**: Incident response or debugging follows a repeatable diagnostic pattern

Runbooks benefit from the conditional workflow pattern: branch based on symptoms, run targeted diagnostics, converge on a structured report format.

## 9. Infrastructure Operations

Routine maintenance skills with guardrails for destructive actions: orphaned resource cleanup, dependency updates, certificate rotation, capacity management.

**Typical structure**: Maintenance scripts + safety checks + approval gates
**Content type**: Scripts (low freedom) with explicit guardrails
**Key signal**: Routine operations that carry risk if done incorrectly

Always include safety guardrails for destructive actions. Document recommended hooks to block dangerous commands when working in this domain (see [plugin-and-troubleshooting.md](plugin-and-troubleshooting.md#recommended-hooks)).

## Choosing a Category

When a skill spans multiple categories, split it. A "deploy and monitor" skill should be two skills: one CI/CD & Deployment skill and one Data Fetching & Analysis skill that the deployment skill can reference via skill composition.

If a skill does not fit any category, it may be too novel (proceed with caution) or too broad (narrow the scope).
