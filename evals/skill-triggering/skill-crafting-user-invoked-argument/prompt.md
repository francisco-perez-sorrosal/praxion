---
description: A question about declaring and reading a user-invoked skill's argument should invoke skill-crafting
tags: [skill-triggering]
allowed_tools: [Read, Glob, Grep, Skill]
max_turns: 8
expected_outcome: The skill is invoked and the answer names argument-hint and the argument substitution
---

I'm writing a skill people run as /deploy with an environment name after it. How should its frontmatter declare that argument, and how does the body read it?
