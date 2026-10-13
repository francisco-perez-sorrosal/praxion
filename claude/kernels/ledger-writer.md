**Tech-debt ledger.** `.ai-state/TECH_DEBT_LEDGER.md` holds the active debt rows (`status` open or in-flight) and `.ai-state/TECH_DEBT_RESOLVED.md` the terminal ones (resolved or wontfix). They share one `td-NNN` namespace; `id` and `dedup_key` are unique across both files. A row is a grounded finding: a problem anchored in current source against current goals, or the reverse. It is not a gotcha (`LEARNINGS.md`) and not a speculative idea.

**Who writes.** Only four writers create rows: the verifier (per-change findings), the sentinel (repo-wide audit findings), the orchestrator (under explicit user direction, or for adjacent debt a fix surfaced) and the architect-validator (per-PR drift findings). Every other agent only reads the ledger and, when it addresses an item, updates `status`, `resolved-by` and `last-seen` on the existing row. No other agent adds a row.

**Append, update, migrate.**
- Producers append to the active ledger only, never to the resolved file.
- Before appending, look for a row with the same `dedup_key`. If one exists, set its `last-seen` to today and leave its `status`, `notes` and `owner-role` alone: consumers own those fields.
- Consumers update rows in place, in whichever file holds them.
- A row that becomes resolved or wontfix moves whole to the resolved file (`scripts/finalize_tech_debt_ledger.py` does it at merge). A new finding whose `dedup_key` matches a resolved row re-opens that row (`status` open, `last-seen` today, a recurrence note in `notes`) and collapses into it.
- Rows are never deleted. Changing a row's `class` recomputes its `dedup_key`.
- Pipelines in separate worktrees write independently and reconcile at merge to main.

**Row fields** (fill every one):
- `id`: `td-NNN`, the next free number, stable across updates.
- `severity`: critical | important | suggested.
- `class`: duplication | complexity | dead-code | drift | stale-todo | coverage-gap | cyclic-dep | token-budget | other. `other` is the escape hatch: pick a named class when the notes match one. `topology-drift` is retired; never file it.
- `direction`: code-to-goals | goals-to-code.
- `location`: affected paths, one per entry, optionally with `:start-end` line ranges.
- `goal-ref-type`: adr | spec-req | architecture | claude-md | code-quality.
- `goal-ref-value`: the decision id, requirement id, design-document section path or principle name that anchors the row; empty only when `goal-ref-type` is code-quality.
- `source`: verifier | sentinel | orchestrator | architect-validator (your own identity).
- `first-seen`: ISO date, set once at creation. `last-seen`: ISO date, updated on every re-detection by the same source.
- `owner-role`: systems-architect | implementation-planner | implementer | test-engineer | doc-engineer | unassigned, from the mapping below.
- `status`: open | in-flight | resolved | wontfix.
- `resolved-by`: a decision id, commit SHA or PR URL when resolved; empty otherwise. A wontfix row gives its rationale in `notes` instead.
- `notes`: one sentence: intent, rationale, scope hint or a survivor flag.
- `dedup_key`: `sha1(class|location|direction|goal-ref-type|goal-ref-value)[:12]`, with `location` the sorted, comma-joined paths without line ranges. When that key collides with a different existing row, extend the hashed string with `|` and `sha1(notes)[:8]`. After writing, run `check_state_ledgers.py --backfill` and then `--check` (from a Praxion checkout: `python3 scripts/check_state_ledgers.py`).

**Owner-role mapping** (look it up; do not re-derive; a consumer may re-assign with a note):
- duplication: implementer (architecture goal: systems-architect; systemic across modules: implementation-planner).
- complexity: implementer (module restructuring: implementation-planner; invariant violation: systems-architect).
- dead-code: implementer (under `tests/`: test-engineer; documentation only: doc-engineer).
- drift: doc-engineer (adr or architecture goal: systems-architect).
- stale-todo: unassigned (an owner named in `notes`: that role; under `tests/`: test-engineer).
- coverage-gap: test-engineer.
- cyclic-dep: implementation-planner.
- token-budget: implementer (implementation-planner when the cut coordinates skill frontmatter or agent injection).
- other: unassigned, with a proposed owner in `notes`.

When to write, the field defaults and the severity tiers for each writer are the Producer overlays in `skills/software-planning/references/tech-debt-ledger.md`; the schema above is complete, so do not copy it into other documents.
