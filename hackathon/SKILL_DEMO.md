---
name: code-review-demo
description: >
  Hackathon demo skill — a deliberately sparse code-review methodology
  used as the self-improvement loop's starting point. The Editor will
  thicken its `## Gotchas` section based on Round 1's failure mode.
allowed-tools: [Read, Glob, Grep, Bash]
compatibility: Claude Code
---

# Code Review (demo skill)

Sparse review methodology for the hackathon's self-improving skill loop.
This skill starts intentionally thin so the Editor has room to add specific,
defect-class-aware rules between rounds.

## Gotchas

- **Review scope in PR context**: review only changed lines and their immediate
  context, not the entire file.

## Review Workflow

### 1. Scope

- Identify files under review from the diff or explicit list.
- Detect primary language from file extensions (`.py`, `.ts`, `.go`, etc.).

### 2. Look for Bugs

- Read each changed function and reason about correctness.
- Note edge cases the new code may not handle.
- Prefer concrete evidence over speculation.

### 3. Findings Format

For each issue, return a structured finding with these fields:

- **Severity**: `critical | high | medium | low`
- **File**: relative path
- **Line**: integer line number in the post-patch file
- **Rule**: short reference to the convention or principle the change violates
- **Evidence**: one or two sentences explaining why this is real, not speculative

## Output

Return only structured findings — no prose preamble, no closing summary.
If no defects are found, return an empty findings list.
- **Mutable Default Arguments as Shared State**: Watch for function or method parameters with mutable defaults (e.g., `def f(handlers=[])`) — Python evaluates default values once at definition time, so all callers share the same object, causing subtle cross-call state pollution.
- **Bare `except` / Silent Error Swallowing**: Watch for `except:` or `except Exception:` blocks that catch all exceptions and silently discard them (e.g., `pass`, returning a default, or only logging without re-raising), as these hide real failures and make debugging nearly impossible.
