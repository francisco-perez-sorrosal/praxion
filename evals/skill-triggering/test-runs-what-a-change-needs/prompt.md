---
description: A request to run only the tests a change needs should invoke the test skill
tags: [skill-triggering]
allowed_tools: [Read, Glob, Grep, Skill]
max_turns: 8
expected_outcome: The skill is invoked and the answer names resolve_test_scope
---

I just edited scripts/check_staleness_markers.py. Run just the tests that change needs.
