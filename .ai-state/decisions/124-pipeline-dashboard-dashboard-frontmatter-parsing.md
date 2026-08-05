---
id: dec-124
title: Pipeline Dashboard frontmatter parsing — stdlib re + pyyaml, no python-frontmatter
status: retired
retired_by:
  - dec-134
category: implementation
date: 2026-05-07
summary: Use stdlib re + pyyaml (already a Streamlit transitive dep) for YAML frontmatter; rejecting the python-frontmatter library to match existing in-repo style and avoid a new external dep on a hot codepath.
tags: [dashboard, dependencies, parsing, frontmatter, pyyaml]
made_by: agent
agent_type: systems-architect
pipeline_tier: full
affected_files:
  - streamlit_app/data/parsers.py
affected_reqs: [REQ-06, REQ-04]
---

## Context

Most artifacts the dashboard reads carry YAML frontmatter:

- ADRs (`<NNN>-<slug>.md`, `drafts/*.md`) — frontmatter is the *primary* data structure, body is secondary
- Specs (`SPEC_<name>_YYYY-MM-DD.md`) — frontmatter for metadata
- Sentinel reports — header metadata in frontmatter

This is a hot codepath: the ADR browser fetches frontmatter from 120+ files on first load. A correct frontmatter parser is required.

Two choices:

1. **`python-frontmatter`** (PyPI, ~80 KB, MIT, actively maintained): one-line API `frontmatter.loads(text)` returning a `Post` object with `.metadata` and `.content`.
2. **Stdlib regex + `pyyaml`**: `re.match(r"^---\n(.+?)\n---\n", ...)` then `yaml.safe_load(group(1))`. ~10 lines.

Praxion's existing parsing scripts (`scripts/finalize_adrs.py`, `scripts/regenerate_adr_index.py`) all use raw regex — no Markdown library is in-repo.

## Decision

Use **stdlib `re` + `pyyaml`** in `streamlit_app/data/parsers.py`:

```python
import re, yaml

_FRONTMATTER_RE = re.compile(r"^---\n(.+?)\n---\n", re.DOTALL)

def parse_frontmatter(text: str) -> tuple[dict, str]:
    m = _FRONTMATTER_RE.match(text)
    if not m:
        return {}, text
    return yaml.safe_load(m.group(1)) or {}, text[m.end():]
```

`pyyaml` is already a Streamlit transitive dependency — no new dep cost. The code matches the regex-based style established by `scripts/finalize_adrs.py`.

## Considered Options

### Option A — `python-frontmatter` library

**Pros**: One-line API; `Post` object with `.metadata`, `.content`, `.handler`; supports JSON and TOML frontmatter (not used in Praxion); maintained.

**Cons**: New external dependency (~80 KB) for what amounts to 10 lines of stdlib + yaml; introduces a parsing style inconsistent with existing in-repo patterns; one more thing to version-pin and audit; trivially replaceable with regex; transitive `pyyaml` already in tree.

### Option B — Stdlib `re` + `pyyaml` (chosen)

**Pros**: Zero new deps; matches `scripts/finalize_adrs.py` style; ~10 lines of code; full control over edge cases (empty frontmatter, malformed YAML); same `yaml.safe_load` behavior agents and scripts use elsewhere.

**Cons**: Slightly more code in `parsers.py` (10 lines vs 1); custom regex must handle the few edge cases the library handles for free (no trailing newline, BOM, CRLF). All trivial.

### Option C — Hand-rolled state machine, no yaml lib

**Pros**: Zero deps including yaml. **Cons**: Re-implementing yaml is absurd; rejected immediately.

## Consequences

**Positive**: No new dependency added to a fresh `~/.praxion-dashboard/venv/`; consistency with existing in-repo parsing style; the parser lives in 10 testable lines; code review is simpler.

**Negative**: A future need for richer frontmatter handling (TOML, multi-doc YAML streams) would re-open this decision. Acceptable: Praxion's frontmatter is uniformly YAML, has been since the convention took effect, and the ADR conventions rule pins this format.

**Risks accepted**: Slightly more parser code to test; mitigated by colocating tests with `data/parsers.py`.

## Prior Decision

Retired by `dec-134`, which replaced the Streamlit runtime. This decision's subject was a specific six-line function in a Python module that no longer exists, so the question it answered — how *that* parser reads frontmatter — went away with it.

**The successor made the opposite call, and this is the record of that.** The Next.js dashboard parses frontmatter with `gray-matter`, a dedicated library, adopted alongside the rewrite; `dashboard_app/src/server/parsers/content.ts` imports it directly and imports `yaml` separately for other parsing. That is precisely the trade rejected here — a dedicated frontmatter dependency added on top of an available YAML one.

It is recorded here rather than as its own decision because the reasoning above does not transfer: the argument was that `pyyaml` was already a transitive dependency and a frontmatter library would be a *new* one, and TypeScript offers no equivalent already-present path. A library choice inside a single component, in a different language, under different premises, changes neither the component inventory nor a published contract, so it is implementation rather than a decision the corpus needs to carry.

This decision matters again only if a component parses frontmatter in Python with a YAML library already on hand — at which point the reasoning still holds: a six-line regex is cheaper than a dependency.
