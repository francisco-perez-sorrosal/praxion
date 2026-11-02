# Claude Agent SDK -- Python

Python-specific implementation guide. Load alongside the generic [Agentic SDKs](../SKILL.md) skill.

**Related skills:**
- [Python Development](../../python-development/SKILL.md) -- type hints, testing, code quality, async patterns
- [Python Project Management](../../python-prj-mgmt/SKILL.md) -- uv/pixi setup, dependency management

## Setup

```bash
pip install claude-agent-sdk
```

Requires Python 3.10+. The Claude Code CLI is bundled with the package. Set `ANTHROPIC_API_KEY` environment variable.

**Alternative auth:** Amazon Bedrock (`CLAUDE_CODE_USE_BEDROCK=1`), Google Vertex AI (`CLAUDE_CODE_USE_VERTEX=1`), Microsoft Azure (`CLAUDE_CODE_USE_FOUNDRY=1`).

## Core Abstractions

### query() -- One-Shot Queries

```python
import asyncio
from claude_agent_sdk import query, ClaudeAgentOptions

async def main():
    async for message in query(
        prompt="Find and fix the bug in auth.py",
        options=ClaudeAgentOptions(allowed_tools=["Read", "Edit", "Bash"]),
    ):
        print(message)

asyncio.run(main())
```

**With options:**

```python
from claude_agent_sdk import ClaudeAgentOptions, AssistantMessage, TextBlock

options = ClaudeAgentOptions(
    system_prompt="You are a code reviewer.",
    max_turns=5,
    allowed_tools=["Read", "Glob", "Grep"],
    permission_mode="bypassPermissions",
    cwd="/path/to/project",
)

async for message in query(prompt="Review this codebase", options=options):
    if isinstance(message, AssistantMessage):
        for block in message.content:
            if isinstance(block, TextBlock):
                print(block.text)
```

### ClaudeSDKClient -- Bidirectional Conversations

```python
from claude_agent_sdk import ClaudeSDKClient, ClaudeAgentOptions

options = ClaudeAgentOptions(
    allowed_tools=["Read", "Write", "Bash"],
    permission_mode="acceptEdits",
)

async with ClaudeSDKClient(options=options) as client:
    await client.query("Create a hello.py file")
    async for msg in client.receive_response():
        print(msg)

    # Continue in same session
    await client.query("Add tests for hello.py")
    async for msg in client.receive_response():
        print(msg)
```

### ClaudeAgentOptions

```python
ClaudeAgentOptions(
    # Core
    system_prompt="Custom system prompt",
    max_turns=10,
    cwd="/path/to/project",
    model="claude-sonnet-5-5",

    # Tools
    allowed_tools=["Read", "Write", "Edit", "Bash", "Glob", "Grep", "Task"],
    permission_mode="acceptEdits",  # "default", "acceptEdits", "bypassPermissions", "plan"

    # MCP
    mcp_servers={"my-server": server_config},

    # Subagents
    agents={"reviewer": AgentDefinition(...)},

    # Hooks
    hooks={"PreToolUse": [HookMatcher(matcher="Bash", hooks=[check_cmd])]},

    # Structured output
    output_format={"type": "json_schema", "schema": my_schema},

    # Settings
    setting_sources=["project"],  # Load CLAUDE.md, .claude/settings.json
)
```

## Built-in Tools

| Tool | Purpose |
|------|---------|
| `Read` | Read files (text, images, PDFs, notebooks) |
| `Write` | Create or overwrite files |
| `Edit` | Precise string replacements in files |
| `Bash` | Execute shell commands |
| `Glob` | Find files by pattern |
| `Grep` | Search file contents with regex |
| `WebSearch` | Search the web |
| `WebFetch` | Fetch and parse web pages |
| `Task` | Spawn subagents |
| `AskUserQuestion` | Ask user clarifying questions |

## Custom Tools (In-Process MCP)

```python
from claude_agent_sdk import tool, create_sdk_mcp_server, ClaudeAgentOptions

@tool("search_docs", "Search documentation", {"query": str, "limit": int})
async def search_docs(args):
    results = await docs_db.search(args["query"], limit=args.get("limit", 10))
    return {"content": [{"type": "text", "text": str(results)}]}

@tool("get_user", "Get user by ID", {"user_id": str})
async def get_user(args):
    user = await db.get_user(args["user_id"])
    return {"content": [{"type": "text", "text": user.json()}]}

server = create_sdk_mcp_server(
    name="my-tools",
    version="1.0.0",
    tools=[search_docs, get_user],
)

options = ClaudeAgentOptions(
    mcp_servers={"tools": server},
    allowed_tools=["mcp__tools__search_docs", "mcp__tools__get_user"],
)
```

**Mixed servers** (in-process + external):

```python
options = ClaudeAgentOptions(
    mcp_servers={
        "internal": sdk_server,                              # In-process
        "playwright": {"command": "npx", "args": ["@playwright/mcp@latest"]},  # External
    }
)
```

## Subagents

```python
from claude_agent_sdk import ClaudeAgentOptions, AgentDefinition

options = ClaudeAgentOptions(
    allowed_tools=["Read", "Glob", "Grep", "Task"],
    agents={
        "code-reviewer": AgentDefinition(
            description="Expert code reviewer for quality and security reviews.",
            prompt="Analyze code quality and suggest improvements.",
            tools=["Read", "Glob", "Grep"],
            model="sonnet",  # "sonnet", "opus", "haiku", "inherit"
        ),
        "test-writer": AgentDefinition(
            description="Test writer for generating comprehensive test suites.",
            prompt="Write tests following project conventions.",
            tools=["Read", "Write", "Glob", "Grep"],
        ),
    },
)
```

**Constraint:** Subagents cannot spawn subagents (single level of delegation).

## Hooks

```python
from claude_agent_sdk import ClaudeAgentOptions, HookMatcher

async def block_dangerous_commands(input_data, tool_use_id, context):
    if input_data["tool_name"] != "Bash":
        return {}

    command = input_data.get("tool_input", {}).get("command", "")
    dangerous = ["rm -rf", "sudo", "chmod 777"]

    for pattern in dangerous:
        if pattern in command:
            return {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": f"Blocked: {pattern}",
                }
            }
    return {}

async def log_file_changes(input_data, tool_use_id, context):
    file_path = input_data.get("tool_input", {}).get("file_path", "unknown")
    with open("audit.log", "a") as f:
        f.write(f"Modified: {file_path}\n")
    return {}

options = ClaudeAgentOptions(
    hooks={
        "PreToolUse": [
            HookMatcher(matcher="Bash", hooks=[block_dangerous_commands]),
        ],
        "PostToolUse": [
            HookMatcher(matcher="Edit|Write", hooks=[log_file_changes]),
        ],
    },
)
```

**Hook events:** `PreToolUse`, `PostToolUse`, `PostToolUseFailure`, `Stop`, `SubagentStart`, `SubagentStop`, `SessionStart`, `SessionEnd`, `UserPromptSubmit`, `PreCompact`, `Notification`, `PermissionRequest`.

## Session Management

```python
# Capture session ID
session_id = None
async for message in query(prompt="Read auth.py", options=options):
    if hasattr(message, "subtype") and message.subtype == "init":
        session_id = message.session_id

# Resume session
async for message in query(
    prompt="Now fix the bug you found",
    options=ClaudeAgentOptions(resume=session_id),
):
    print(message)

# Fork session (branch from existing)
async for message in query(
    prompt="Try a different approach",
    options=ClaudeAgentOptions(resume=session_id, fork_session=True),
):
    print(message)
```

## Permissions

**Custom permission handler:**

```python
async def custom_permissions(tool_name, tool_input, options):
    if tool_name == "Bash" and "rm" in tool_input.get("command", ""):
        return {"behavior": "deny", "message": "Deletion not allowed"}
    return {"behavior": "allow", "updatedInput": tool_input}

options = ClaudeAgentOptions(can_use_tool=custom_permissions)
```

## Message Types

```python
from claude_agent_sdk import AssistantMessage, ResultMessage, TextBlock, ToolUseBlock

async for message in query(prompt="Hello", options=options):
    if isinstance(message, AssistantMessage):
        for block in message.content:
            if isinstance(block, TextBlock):
                print(f"Text: {block.text}")
            elif isinstance(block, ToolUseBlock):
                print(f"Tool: {block.name}({block.input})")
    elif isinstance(message, ResultMessage):
        print(f"Done: {message.result}")
        print(f"Cost: ${message.total_cost_usd:.4f}")
        print(f"Turns: {message.num_turns}")
```

## Error Handling

```python
from claude_agent_sdk import (
    ClaudeSDKError,
    CLINotFoundError,
    CLIConnectionError,
    ProcessError,
    CLIJSONDecodeError,
)

try:
    async for message in query(prompt="Hello", options=options):
        pass
except CLINotFoundError:
    print("Install Claude Code CLI")
except ProcessError as e:
    print(f"Process failed: exit code {e.exit_code}")
except CLIJSONDecodeError as e:
    print(f"Parse error: {e}")
```

## Structured Outputs

```python
import json

schema = {
    "type": "object",
    "properties": {
        "findings": {"type": "array", "items": {"type": "string"}},
        "severity": {"type": "string", "enum": ["low", "medium", "high"]},
    },
    "required": ["findings", "severity"],
}

options = ClaudeAgentOptions(
    output_format={"type": "json_schema", "schema": schema},
    allowed_tools=["Read", "Glob", "Grep"],
)

async for message in query(prompt="Analyze this code for issues", options=options):
    if isinstance(message, ResultMessage) and message.structured_output:
        data = message.structured_output  # Validated against schema
```

## Common Pitfalls

- Not setting `setting_sources=["project"]` when CLAUDE.md is needed
- Forgetting to include `Task` in `allowed_tools` when using subagents
- Using `permission_mode="bypassPermissions"` without understanding the security implications
- MCP tool names follow `mcp__<server>__<tool>` pattern -- must match in `allowed_tools`
- `query()` returns `AsyncIterator` -- must iterate even if only `ResultMessage` is needed
- Subagents cannot spawn subagents (single level of delegation)
