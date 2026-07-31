---
name: violating-fixture
description: >
  Negative fixture for tests/test_agent_frontmatter_plugin_compat.py. Declares all
  three fields Claude Code ignores for plugin subagents. Never registered in
  plugin.json; never shipped. Exists so the detector can be observed failing.
tools: Read
permissionMode: acceptEdits
mcpServers:
  example:
    command: "echo"
hooks:
  Stop:
    - hooks:
        - type: command
          command: "true"
---

Fixture body. Not a real agent.
