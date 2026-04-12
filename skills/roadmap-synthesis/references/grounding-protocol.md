# Grounding Protocol

Back to: [../SKILL.md](../SKILL.md)

The non-negotiable rule: **every quantitative claim in a generated `ROADMAP.md` must cite a source.** Qualitative claims prefer evidence where it exists. Enforces SPIRIT dimension 3 (Quality, non-negotiable) and mitigates R1 (hallucinated features/metrics) from the audit risk register.

## The rule

A claim is *grounded* when a reader can reproduce or verify it from the cited source with no additional context. Two categories:

- **Quantitative claim** — any assertion containing a number, percentage, count, ratio, or date. *Must* cite a source.
- **Qualitative claim** — descriptive, evaluative, or recommendation. *Should* cite a source when one is available; must otherwise be clearly framed as judgment.

Unsourced quantitative claims are **rejected** by the Phase 7 self-verification pass. The cartographer regenerates the affected section rather than shipping a hallucinated metric.

## Evidence types

Accept any of the following as grounding:

| Evidence type | Citation format | Example |
|---|---|---|
| File reference (line-specific) | `` `path/to/file.py:42` `` | `src/auth.py:117` |
| File reference (whole file) | `` `path/to/file.md` `` | `skills/roadmap-planning/SKILL.md` |
| Command output | `` `$ command` → `summary` `` | `` `$ wc -l skills/**/*.md` → 7,312 lines total `` |
| External URL | `[title](url) (fetched YYYY-MM-DD)` | `[CNCF Roadmap Guide](https://contribute.cncf.io/...) (fetched 2026-04-12)` |
| ADR | `dec-NNN` (linked to `.ai-state/decisions/`) | `dec-033` |
| Memory entry | `memory: category/key (updated_at YYYY-MM-DD)` | `memory: learnings/aaif-standards-convergence-2026 (updated_at 2026-04-12)` |
| Sentinel report | `SENTINEL_REPORT_<timestamp>.md §<section>` | `SENTINEL_REPORT_2026-04-10_14-00-00.md §coherence` |

## Verification checklist (Phase 7 self-verify)

For each claim in the draft roadmap:

1. **Does it contain a number, percentage, count, ratio, or date?** If yes → quantitative; grounding mandatory.
2. **Is a source cited?** If no → either fetch grounding (re-run the audit) or demote the claim to qualitative framing.
3. **Is the citation reachable?** If it's a file, does it exist? If it's a URL, does the fetch date prove it was verified? If it's a command, can the command be re-run?
4. **Does the cited source actually support the claim?** (Sample 20–30% of claims for manual verification; flag any where the source says something different from the claim.)
5. **Are cross-run claims preserved?** If a claim came from the prior `ROADMAP.md`'s Decision Log, carry the original citation — do not re-cite to a new source without reconciliation.

## Citation patterns

### Good

- "Praxion's `skills/` contains 35 skills totaling 7,312 lines (`$ wc -l skills/**/SKILL.md`)."
- "The always-loaded context is at 106% of the 52,500-char ceiling (memory: project/always-loaded-budget-at-106pct-apr-2026)."
- "Anthropic's 2026 Agentic Coding Trends Report documents a shift to agentic cycles measured in hours ([overview](https://resources.anthropic.com/2026-agentic-coding-trends-report) (fetched 2026-04-12))."
- "Memory write:read ratio is 49:1 based on session logs from Feb–Apr 2026 (`.ai-state/observations.jsonl` grepped for `remember` vs `recall`)."

### Anti-patterns — reject these

| Anti-pattern | Why it fails | Fix |
|---|---|---|
| "Users frequently report X" | No source; "users" is vague | Cite the ticket, survey, or discussion |
| "Roughly 80% of memory entries are never accessed" | Round number, no command/file | Run `jq '.entries | map(select(.access_count == 0)) | length'` and cite exact result |
| "Industry standard is Y" | Appeals to authority without source | Cite a specific authority (Anthropic report, CNCF doc, benchmark paper) |
| "Recent best practices suggest Z" | Temporal vagueness | Cite publication date and source |
| "The codebase is slow" | No metric | Measure latency or name the bottleneck file |
| Importing a memory claim without verifying | Memory can be stale | Check `updated_at`; verify against current code when recommending action |

## Operational notes

- **Grounding takes time.** The audit phase must produce citations as researchers write their fragments; trying to retrofit citations during synthesis is the main way roadmaps drift into ungrounded territory.
- **When the evidence is uncertain**, say so. "Approximately 10 agents total (verified against `agents/*.md` on 2026-04-12)" is grounded. "Many agents" is not.
- **External citations expire.** Always include the fetch date; a year-old URL citation without a fetch stamp is suspect.
- **Internal file paths should be verified at cite time.** A path that pointed to a valid file last month may have moved; the Phase 7 checklist step 3 catches this.
- **Commands should be reproducible.** Prefer `wc -c`, `grep -c`, `jq`, `find | wc -l` — one-liners a reader can re-run — over complex pipelines that may not transport.
