# Content Guidelines and Development Workflow

Detailed guidance on choosing content types, building workflows with feedback loops, and developing skills through evaluation-driven iteration. Reference material for the [Skill Creator](../SKILL.md) skill.

## Choosing Content Type

When deciding how to encode behavior in your skill, match the content type to the degree of freedom:

| Content Type | When to Use | Agent Behavior |
|---|---|---|
| **Script** (`scripts/`) | Deterministic operations where consistency is critical (validation, transformation, migration) | Executes the script -- doesn't generate its own |
| **Worked example** | A pattern exists that the agent should follow (commit format, report structure, API response shape) | Pattern-matches the example |
| **Prose instruction** | Multiple approaches are valid and context determines the best one (code review, architecture decisions) | Reasons about the situation |

Prefer scripts for anything a linter, formatter, or validator could do -- deterministic checks are cheaper and more reliable than LLM reasoning. Reserve prose instructions for decisions that genuinely require judgment.

## Gotchas Sections

Build a gotchas section early and grow it iteratively through the author-tester workflow:

1. Use the skill on real tasks and note where the agent fails or deviates
2. Add each failure as a concise gotcha with the wrong behavior and the correct approach
3. Prioritize gotchas that challenge the agent's default reasoning over obvious reminders

Structure:

```markdown
## Gotchas

- **Wrong**: `client.query(sql)` returns a cursor, not results. **Right**: Call `.fetchall()` on the cursor
- **Wrong**: Timestamps default to local time. **Right**: Always use `datetime.utcnow()` or `datetime.now(timezone.utc)`
- **Wrong**: The `--force` flag skips validation. **Right**: Use `--force-with-lease` to preserve safety checks
```

Gotchas accumulate over time. Each iteration of the author-tester workflow may surface new ones. Keep the section near the top of the skill body -- it is the content most likely to prevent errors.

## Workflows with Feedback Loops

For complex tasks, provide step-by-step checklists the agent can track:

```markdown
Task Progress:
- [ ] Step 1: Analyze inputs (run analyze.py)
- [ ] Step 2: Create mapping
- [ ] Step 3: Validate mapping (run validate.py)
- [ ] Step 4: Execute transformation
- [ ] Step 5: Verify output
```

Include validation loops: run validator -> fix errors -> repeat. This dramatically improves output quality.

For high-stakes operations, use the **plan-validate-execute** pattern: create a structured plan file, validate it with a script, then execute. Catches errors before they happen.

## Evaluation-Driven Development

Start with a minimal SKILL.md addressing only observed gaps. Add content only when testing reveals the agent needs it -- not preemptively.

Build evaluations BEFORE writing extensive documentation:

1. **Identify gaps**: Run the agent on representative tasks without the skill. Note specific failures
2. **Create evaluations**: Define three test scenarios covering those gaps
3. **Establish baseline**: Measure performance without the skill
4. **Write minimal instructions**: Just enough to address gaps and pass evaluations
5. **Iterate**: Execute evaluations, compare against baseline, refine

## Iterative Author-Tester Workflow

1. **Instance A** (author): Helps create/refine skill content
2. **Instance B** (tester): Uses the skill on real tasks in a fresh session
3. Observe Instance B's behavior -- where it struggles, succeeds, or makes unexpected choices. Grade outcomes, not paths: agents may find valid approaches you didn't anticipate
4. Bring observations back to Instance A for refinements
5. Repeat until the skill reliably handles target scenarios

**Adversarial review variant**: For code quality and review skills, spawn a fresh-eyes subagent to critique the skill's output. The subagent applies the skill, then a second subagent reviews the result without knowing the original intent. Iterate until findings degrade to nitpicks. This catches blind spots the original author misses.

## Observe Navigation Patterns

Watch how the agent uses the skill:

- Unexpected file access order -> structure isn't intuitive
- Missed references -> links need to be more explicit
- Overreliance on one file -> content should be in `SKILL.md`
- Ignored files -> unnecessary or poorly signaled

## Executable Code Best Practices

**Solve, Don't Punt**: Handle error conditions explicitly rather than letting scripts fail for the agent to debug.

**Justify Constants**: Document why values exist -- no voodoo numbers:

```python
# Three retries balances reliability vs speed
# Most intermittent failures resolve by second retry
MAX_RETRIES = 3
```

**Execution vs Reference**: Be explicit about intent:

- "Run `analyze_form.py` to extract fields" (execute)
- "See `analyze_form.py` for the extraction algorithm" (read as reference)

**Package Dependencies**: List required packages and verify availability.

**MCP Tool Names**: Use fully qualified format: `ServerName:tool_name`

## Visual Analysis

When skill inputs or outputs can be rendered as images, use the agent's vision capabilities for verification:

```markdown
## Layout verification

1. Convert the output to an image: `python scripts/render_preview.py output.pdf`
2. Analyze the rendered image to verify field placement and formatting
3. Compare against the expected layout
```

This pattern is particularly useful for PDF form filling, UI scaffolding, document generation, and any skill where visual correctness matters more than textual content.

## Deprecated Content

When a skill covers evolving APIs or workflows, use collapsible "Old patterns" sections instead of time-based conditionals:

```markdown
## Current method

Use the v2 API endpoint: `api.example.com/v2/messages`

## Old patterns

<details>
<summary>Legacy v1 API (deprecated 2025-08)</summary>

The v1 API used: `api.example.com/v1/messages`

This endpoint is no longer supported.
</details>
```

Never use time-based conditionals ("If before August 2025, use X"). They become wrong silently. The old patterns section provides historical context without cluttering main content.

## Configuration and Setup

For skills that need user-specific setup (API keys, project paths, tool preferences), store configuration in structured files:

```markdown
## Setup

This skill reads configuration from `config.json` in the skill directory:

```json
{
  "api_endpoint": "https://api.example.com",
  "default_format": "markdown"
}
```

When setup varies by user, prompt for necessary details (e.g., via AskUserQuestion in Claude Code) with structured choices rather than expecting users to manually edit config files.
```

## Measurement and Tracking

Track skill adoption and effectiveness using PreToolUse hooks that parse the hook's stdin JSON payload. Log which skills activate, how often, and in what contexts:

```json
{
  "hooks": {
    "PreToolUse": [{
      "matcher": "Read",
      "hooks": [{
        "type": "command",
        "command": "python3 -c \"import sys,json; d=json.load(sys.stdin); print(f'{d.get(\\\"tool_name\\\",\\\"unknown\\\")}', file=open('/tmp/skill-usage.log','a'))\""
      }]
    }]
  }
}
```

Note: Hook payloads arrive via stdin as JSON, not as environment variables. Parse the payload to extract tool and context information.

Compare actual activation frequency against expectations. Skills that under-trigger may need better descriptions. Skills that over-trigger may need narrower descriptions. Skills that activate but produce poor results need content improvements.
