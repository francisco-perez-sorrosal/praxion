---
id: dec-016
title: Naming convention for project exploration components
status: accepted
category: architectural
date: 2026-04-06
summary: Command named /explore-project, skill named project-exploration -- differentiates from existing /onboard-project, follows verb-first convention
tags: [project-exploration, naming, commands, skills]
made_by: agent
agent_type: systems-architect
pipeline_tier: standard
affected_files: [skills/project-exploration/SKILL.md, commands/explore-project.md]
---

## Context

The Praxion ecosystem has an existing `/onboard-project` command that onboards a project TO the Praxion plugin (gitignore, plugin install, CLAUDE.md setup). The new feature helps developers understand a project -- a completely different purpose. The name must be distinct enough to avoid confusion while being intuitive and following existing conventions.

## Decision

Command: `/explore-project`. Skill: `project-exploration`.

## Considered Options

### Option 1: `/explore-project` + `project-exploration`

- **Pro**: Verb-first matches convention (`review-pr`, `report-upstream`, `onboard-project`)
- **Pro**: "Explore" conveys interactive discovery, not one-time setup
- **Pro**: Clear differentiation from `/onboard-project` (explore vs onboard)
- **Pro**: Descriptive and unambiguous skill name
- **Con**: Two commands with "-project" suffix -- but descriptions clearly differentiate

### Option 2: `/orient` + `project-orientation`

- **Pro**: Concise
- **Con**: Less discoverable -- "orient" is not immediately clear
- **Con**: Does not follow verb-noun convention

### Option 3: `/explore` + `project-cartography`

- **Pro**: Short command name
- **Con**: Too generic -- could collide with future commands
- **Con**: "Cartography" is evocative but not immediately understandable

### Option 4: `/understand-project` + `project-understanding`

- **Pro**: Very descriptive
- **Con**: Verbose for a frequently used command
- **Con**: "Understanding" is abstract -- does not convey interactive process

### Option 5: `/project-tour` + `project-tour`

- **Pro**: Guided metaphor
- **Con**: Breaks verb-first convention (noun-first)
- **Con**: Implies a fixed path -- the system is adaptive, not a fixed tour

## Consequences

- **Positive**: Intuitive name that developers can guess the purpose of
- **Positive**: Consistent with existing naming conventions
- **Positive**: Clear differentiation from `/onboard-project`
- **Negative**: None significant
