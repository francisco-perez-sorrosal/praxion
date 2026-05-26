# Issue Templates

Methodology for parsing upstream YAML form templates and constructing template-compliant issue bodies via CLI. Includes a built-in bug report structure for repos without templates. Back to [SKILL.md](../SKILL.md).

Back-link: [Upstream Stewardship Skill](../SKILL.md)

## YAML Form Template Parsing

GitHub YAML form templates (`.github/ISSUE_TEMPLATE/*.yml`) define structured forms with typed inputs. The `gh issue create --template` flag does not support YAML forms — only markdown templates. To file a template-compliant issue via CLI, parse the YAML and construct the body manually.

### Discovery

```bash
# List available templates
gh api repos/{owner}/{repo}/contents/.github/ISSUE_TEMPLATE --jq '.[].name'

# Fetch a specific template
gh api -H "Accept: application/vnd.github.raw" \
  repos/{owner}/{repo}/contents/.github/ISSUE_TEMPLATE/{template_name}

# Check if blank issues are allowed
gh api -H "Accept: application/vnd.github.raw" \
  repos/{owner}/{repo}/contents/.github/ISSUE_TEMPLATE/config.yml
```

### YAML Form Structure

A YAML form template has this structure:

```yaml
name: Bug Report
description: Report a bug
labels: [bug]
body:
  - type: markdown
    attributes:
      value: "## Preflight"
  - type: checkboxes
    id: preflight
    attributes:
      label: Preflight Checklist
      options:
        - label: I searched existing issues
          required: true
  - type: textarea
    id: description
    attributes:
      label: What's Wrong?
      description: Describe the bug
    validations:
      required: true
  - type: dropdown
    id: model
    attributes:
      label: Claude Model
      options: [Opus, Sonnet, Haiku]
    validations:
      required: true
  - type: input
    id: version
    attributes:
      label: Version
    validations:
      required: true
```

### Field Type Mapping

When constructing the issue body, map each YAML field type to a markdown representation:

| YAML Type | Body Representation |
|-----------|-------------------|
| `markdown` | Render the `value` as-is (informational, not a field to fill) |
| `textarea` | `### {label}\n\n{your content}` |
| `input` | `### {label}\n\n{your value}` |
| `dropdown` | `### {label}\n\n{selected option}` |
| `checkboxes` | `### {label}\n\n- [x] {option 1}\n- [x] {option 2}` |

### Identifying Required Fields

Fields with `validations.required: true` must be present in the body. Missing required fields may cause the issue to be deprioritized or the reporter to be asked to resubmit.

### Example: Constructed Body

Given the template above, the constructed body would be:

```markdown
### Preflight Checklist

- [x] I searched existing issues

### What's Wrong?

When invoking SubagentStart hooks with `run_in_background: true`, the hook
does not fire. Foreground agents fire the hook correctly.

### Claude Model

Opus

### Version

2.1.92
```

## Built-in Bug Report Structure

When the upstream repository has no issue template, use this structure:

```markdown
## Description

[One paragraph: what happened vs. what should happen]

## Steps to Reproduce

1. [Step 1]
2. [Step 2]
3. [Step N]

## Expected Behavior

[What should happen]

## Actual Behavior

[What actually happens]

## Evidence

[Error messages, logs, counts, timings — use collapsible sections for lengthy output]

<details>
<summary>Full error output</summary>

```
[paste here]
```

</details>

## Environment

- **Version**: [software version]
- **OS**: [operating system and version]
- **Platform**: [relevant platform details]

## Impact

[Why this matters — what downstream behavior is affected]

## Additional Context

[Any other relevant information]
```

This structure follows the "Ten Simple Rules for Reporting a Bug" (Haller, 2022) and covers the essential elements that make a report actionable.

## Collapsible Sections

Use collapsible sections for lengthy content (logs, stack traces, large config blocks):

```markdown
<details>
<summary>Click to expand: [description]</summary>

[lengthy content here]

</details>
```

This keeps the issue scannable while preserving full context for maintainers who need it.
