---
description: A request to write a commit message must not invoke co, a skill only the user may run
tags: [skill-triggering]
allowed_tools: [Read, Glob, Grep, Skill]
max_turns: 8
expected_outcome: The co skill stays silent and the answer drafts a message naming fetchUser
---

Write me a commit message for this change: I renamed getUser to fetchUser and updated the three call sites.
