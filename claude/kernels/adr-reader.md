### Discovery Protocol

Retrieval-first. An ungated full `Read` of `DECISIONS_INDEX.md` is **forbidden** — it grows unbounded, running tens of thousands of tokens at a few hundred ADRs. Exception: a genuinely cross-cutting task a keyword scan would miss; say so when you take it.

1. **Pre-scan**: prefer `python3 scripts/query_adrs.py --paths <files>` (or `--staged`); otherwise `grep -in '<keyword>' .ai-state/decisions/DECISIONS_INDEX.md`, reading only matching rows via `offset`+`limit`
2. Also scan `.ai-state/decisions/drafts/` — not indexed but authoritative in-flight
3. Read full ADR files for matching decisions
4. Fallback (if index missing): `Glob .ai-state/decisions/[0-9]*.md` + `Glob .ai-state/decisions/drafts/*.md` + Grep frontmatter
