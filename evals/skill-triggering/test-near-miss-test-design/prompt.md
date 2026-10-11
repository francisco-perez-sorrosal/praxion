---
description: A question about test design, not about running tests, must not invoke the test skill
tags: [skill-triggering]
allowed_tools: [Read, Glob, Grep, Skill]
max_turns: 8
expected_outcome: The test skill stays silent and the answer explains when generated inputs and invariants beat hand-picked examples
---

When should I write a property-based test instead of an example-based one?
