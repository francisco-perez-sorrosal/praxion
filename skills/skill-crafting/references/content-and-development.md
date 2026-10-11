# Content Guidelines and Development Workflow

Detailed guidance on choosing content types, shaping skill output with templates and examples, structuring multi-step workflows with feedback loops, splitting a skill's content across files, and iterating on a skill once its evaluations exist. Reference material for the [Skill Creator](../SKILL.md) skill.

## Contents

- Choosing Content Type
- Gotchas Sections
- Output Templates
- Examples Pattern
- Workflow Patterns
- Structuring Content Across Files
- Evaluation-Driven Development
- Iterative Author-Tester Workflow
- Observe Navigation Patterns
- Visual Analysis
- Deprecated Content
- Configuration and Setup
- Measurement and Tracking

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

## Output Templates

Use templates when the skill's output must follow a specific structure. Match template strictness to requirements.

### Strict Template

When the output format is non-negotiable (reports, compliance documents, structured data):

```markdown
Use this EXACT template for every security audit report:

# Security Audit Report

## Executive Summary
[2-3 sentence overview of findings]

## Key Findings
- Finding 1: [description] | Severity: [Critical/High/Medium/Low]
- Finding 2: [description] | Severity: [Critical/High/Medium/Low]

## Recommendations
1. [Immediate action items]
2. [Short-term improvements]
3. [Long-term architectural changes]

## Methodology
[Brief description of audit approach]
```

### Flexible Template

When a sensible default exists but adaptation is expected:

```markdown
Use this format as a sensible default, adapting sections as needed
for the specific context:

# [Component] Design Document

## Problem Statement
## Proposed Solution
## Alternatives Considered
## Implementation Plan
```

## Examples Pattern

Use input/output pairs when the desired style and detail level are easier to show than describe. Examples help the agent understand conventions more clearly than prose descriptions alone.

### Showing Desired Style

Provide concrete before/after pairs that demonstrate the target quality:

```markdown
Format commit messages following this pattern:

type(scope): brief description

Examples:
- feat(auth): add OAuth2 token refresh flow
- fix(parser): handle empty input without panic
- refactor(db): extract connection pooling to module
- docs(api): document rate limiting headers
```

### Showing Detail Level

When the expected depth of output matters, include examples at the target level:

```markdown
When documenting a function, match this level of detail:

Input: `def retry(fn, max_attempts=3, backoff=1.0)`

Output:
Retry a callable with exponential backoff.
- `fn`: Zero-argument callable to retry
- `max_attempts`: Maximum number of attempts before raising (default: 3)
- `backoff`: Initial delay in seconds, doubled after each failure (default: 1.0)
- Raises the last exception if all attempts fail
```

## Workflow Patterns

### Sequential Workflows

Use sequential workflows when the task has clear, ordered steps where each depends on the previous one. Provide an overview of the process early in SKILL.md so the agent understands the full picture before starting.

```markdown
## PDF Form Filling Process

Follow these steps in order:

1. **Analyze** the blank PDF form -- identify all fillable fields
2. **Map** source data to form fields -- create a field mapping
3. **Validate** the mapping -- run `scripts/validate_mapping.py`
4. **Fill** the form -- apply mapped values to fields
5. **Verify** the output -- confirm all fields populated correctly

After each step, check results before proceeding. If validation
fails, return to the mapping step and correct errors.
```

Include validation loops (run validator, fix errors, repeat) between steps where errors are likely. This dramatically improves output quality.

### Conditional Workflows

Use conditional workflows when the task has branching logic based on the current situation. Guide the agent through decision points with clear criteria.

```markdown
## Content Workflow

Determine the starting point:

**Creating new content?**
1. Gather requirements from the user
2. Create outline with target audience and scope
3. Draft content following the style guide
4. Run `scripts/check_style.py` on the draft

**Editing existing content?**
1. Read the current document and identify the change scope
2. Preserve voice and terminology already established
3. Make targeted edits -- avoid rewriting sections unnecessarily
4. Run `scripts/check_style.py` on changed sections only
```

Frame decision points as questions the agent can answer from context. Avoid deeply nested branches -- flatten with guard clauses or split into separate workflows when complexity grows.

### Feedback Loops and Checklists

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

## Structuring Content Across Files

### Pattern 1: High-level guide with references

```markdown
# PDF Processing

## Quick start
Extract text with pdfplumber: [code example]

## Advanced features
- **Form filling**: See [FORMS.md](FORMS.md) for complete guide
- **API reference**: See [REFERENCE.md](REFERENCE.md) for all methods
```

### Pattern 2: Domain-specific organization

Organize by domain when a skill covers multiple areas. The agent only reads the relevant domain file:

```text
bigquery-skill/
├── SKILL.md (overview and navigation)
└── references/
    ├── finance.md, sales.md, product.md, marketing.md
```

### Pattern 2b: Language/context-specific references

When a skill provides cross-cutting knowledge (e.g., testing strategy, API design), keep the SKILL.md body language-agnostic and place language-specific or context-specific content in separate reference files. The agent loads only the reference relevant to the active project:

```text
testing-strategy/
├── SKILL.md (language-agnostic strategy)
└── references/
    ├── python-testing.md     # pytest, hypothesis, coverage
    ├── typescript-testing.md  # vitest, jest, type-safe mocks (future)
    └── rust-testing.md        # cargo test, proptest (future)
```

The SKILL.md lists all available references as satellite files. New language support is added by creating a reference file — no changes to the core SKILL.md. Use illustrative examples from specific languages (e.g., `tmp_path` in pytest) but frame them as instances of a general principle, not as the only valid approach.

### Pattern 2c: Polyglot skill (mutually-exclusive contexts)

When a skill covers multiple languages/runtimes/SDKs and each user is in exactly one at a time, place runnable mechanics under `contexts/` — distinct from Pattern 2b's references/-only approach for language-tinged conceptual depth.

```text
mcp-crafting/
├── SKILL.md               # Language-agnostic protocol + decisions
├── references/            # Cross-language conceptual depth (transports, primitives)
└── contexts/
    ├── python.md          # FastMCP commands, runnable Python examples
    └── typescript.md      # @modelcontextprotocol/sdk commands, runnable TS examples
```

The SKILL.md body stays language-agnostic, carries a Language Contexts table (columns: Language | Context File | Tooling), and redirects at every divergence point ("see `contexts/<language>.md` for X"). Activation is local: the agent loads `contexts/typescript.md` without loading `contexts/python.md`. The frontmatter `description` ends with "Language modules available for `<list>`."

**Decision rule** when authoring a file:

- Does the content compile / run / install? → `contexts/`
- Does the content explain a cross-language concept? → `references/`
- Multi-language comparison? → SKILL.md body or `references/`

A reference may *use* one language for illustrative examples, but its *claims* must be language-agnostic; otherwise the file is a context regardless of current directory.

**File-naming convention:**

- `contexts/<language>.md` — one-per-language (e.g., `contexts/python.md`)
- `contexts/<framework>-<language>.md` — matrix cases (e.g., `contexts/openai-agents-typescript.md`)
- `contexts/<framework>.md` — when the parent skill is language-rooted and frameworks layer above the baseline language context (e.g., `typescript-development/contexts/react.md`)

**Body discipline:** Language-agnostic prose; no language-specific code blocks in SKILL.md except (a) one-line pseudocode showing *shape*, (b) "Python: X / TypeScript: Y" inline pairs for direct comparison. No version pins in the body — versions live in contexts.

**Extension protocol** — to add a new language to an existing polyglot skill:

1. Create `contexts/<language>.md`
2. Add a row to the Language Contexts table
3. Update the frontmatter `description` to include the new language
4. Add language-specific gotchas only if any exist
5. The body is NOT modified

### Pattern 3: Conditional details

Show basic content, link to advanced:

```markdown
## Creating documents
Use docx-js. See [DOCX-JS.md](DOCX-JS.md).

## Editing documents
For simple edits, modify XML directly.
**For tracked changes**: See [REDLINING.md](REDLINING.md)
```

--> See [plugin-and-troubleshooting.md](plugin-and-troubleshooting.md) for plugin-specific progressive disclosure mechanics (base path injection, permission caveats, debugging).

## Evaluation-Driven Development

The eval-first creation loop is on the entry page: [Creating a Skill: the Eval-First Loop](../SKILL.md#creating-a-skill-the-eval-first-loop).
Eval file formats, grading and the `claude plugin eval` case layout are in [evaluating-skills.md](evaluating-skills.md).
The sections below cover iterating on a skill once its scenarios exist.

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
