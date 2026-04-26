---
id: dec-draft-145b6ce7
title: Use Anthropic SDK messages.parse(output_format=PydanticModel) for structured output
status: proposed
category: implementation
date: 2026-04-25
summary: All three LLM call sites (run_review.py, rewrite_skill.py, fix.py) use messages.parse with Pydantic output schemas instead of system-prompt-plus-json.loads, removing ~40 lines of glue code.
tags: [hackathon, anthropic-sdk, structured-output, pydantic]
made_by: agent
agent_type: systems-architect
pipeline_tier: standard
affected_files:
  - hackathon/run_review.py
  - hackathon/rewrite_skill.py
  - hackathon/fix.py
  - hackathon/models.py
affected_reqs: []
---

## Context

The demo has three structured-output call sites: Reviewer (`findings.json` from PR diff), Editor (Gotcha bullet text), Fixer (`proposed_fix.patch` + `missing_test.py`). Anthropic SDK 0.97.0 (the version pinned in `hackathon/requirements.txt` and the sandbox image) exposes `client.messages.parse(output_format=PydanticModel)` for native typed output. The alternative is the older system-prompt-plus-`json.loads()` pattern, which requires hand-written validation, retry on malformed JSON, and ~15-20 extra lines per call site. Pydantic is already a hard dependency (`SkillRunEntry` definition; sandbox image includes it per ADR-2), so adding a Pydantic output type costs zero marginal weight.

## Decision

Use `client.messages.parse(model=..., max_tokens=..., system=..., messages=..., output_format=OutputModel)` everywhere, returning `resp.parsed_output` as a typed Pydantic instance. Define output schemas in `hackathon/models.py`:

- `FindingsOutput(findings: list[Finding])` for Reviewer
- `RewriteOutput(gotcha_bullet: str)` for Editor
- `FixOutput(patch_text: str, test_text: str)` for Fixer

If `messages.parse()` is somehow unavailable in the resolved 0.97.0 install, fall back to `messages.create()` + `json.loads(resp.content[0].text)` — adds ~20 lines, same logic.

## Considered Options

### Option A: messages.parse() with Pydantic output_format (selected)

- **Pro:** ~40 lines saved across 3 call sites
- **Pro:** SDK handles retry on schema validation failure
- **Pro:** typed downstream consumers — no `[0]['key']` dict diving
- **Con:** ties demo to a recent SDK feature

### Option B: messages.create() + system-prompt JSON instruction + json.loads()

- **Pro:** works in any anthropic SDK version
- **Pro:** zero new SDK surface to learn
- **Con:** brittle on malformed responses
- **Con:** ~20 lines of validation glue per call site

## Consequences

- Positive: code is shorter, more readable, and type-checked end-to-end
- Positive: aligns with Anthropic's stated direction for structured output
- Negative: locked to ≥0.94.0 (confirmed by researcher; 0.97.0 has it)
- Risk accepted: fallback to Option B if `messages.parse` not resolvable at install time — the implementer can switch in <10 minutes
