## Decision Tracking

`.ai-state/decisions.jsonl` is an append-only, machine-readable audit log of decisions made during AI-assisted development sessions, committed to git.

### Dual-Path Model

Decisions reach the log via two complementary paths:

- **Primary (agent direct write)**: Agents call `decision-tracker write` CLI when documenting decisions in `LEARNINGS.md`. Produces high-quality entries with full context.
- **Secondary (commit-time hook)**: A PreToolUse hook extracts undocumented decisions from conversation transcripts and diffs at commit time. Acts as a safety net for decisions agents missed.

Both paths write to the same `decisions.jsonl` file. The hook deduplicates against agent-written entries before appending.

### JSONL Schema

Each line in `decisions.jsonl` is a JSON object:

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `id` | string | Yes | `"dec-"` + 12-char UUID fragment |
| `version` | int | Yes | Schema version (initially `1`) |
| `timestamp` | string | Yes | ISO 8601 UTC creation time |
| `status` | string | Yes | `pending` / `approved` / `auto-approved` / `documented` / `rejected` |
| `category` | string | Yes | `architectural` / `behavioral` / `implementation` / `configuration` / `calibration` |
| `question` | string | No | What was being decided |
| `decision` | string | Yes | The choice that was made |
| `rationale` | string | No | Why this choice was made |
| `alternatives` | string[] | No | What else was considered |
| `made_by` | string | Yes | `user` / `agent` |
| `agent_type` | string | No | Which agent originated the decision |
| `confidence` | float | No | 0.0-1.0 extraction confidence (hook path) |
| `source` | string | Yes | `agent` / `hook` |
| `affected_files` | string[] | No | File paths impacted by the decision |
| `affected_reqs` | string[] | No | REQ IDs linked to the decision |
| `commit_sha` | string | No | Git commit SHA (short, 7-char) |
| `branch` | string | No | Git branch name |
| `session_id` | string | No | Claude Code session ID |
| `pipeline_tier` | string | No | `direct` / `lightweight` / `standard` / `full` / `spike` |
| `supersedes` | string | No | ID of a decision this one replaces |
| `rejection_reason` | string | No | Why it was rejected (when status is `rejected`) |
| `user_note` | string | No | User annotation added during review |

### Status Semantics

- **`pending`** — extracted by the hook, awaiting user review (Standard/Full tiers only)
- **`approved`** — user explicitly approved during review (hook path)
- **`auto-approved`** — silently logged during Direct/Lightweight/Spike tiers (hook path)
- **`documented`** — written directly by an agent (primary path, no review needed)
- **`rejected`** — user rejected during review (still logged for audit trail)

### Source Semantics

- **`agent`** — written directly by a pipeline agent with full context. Always has rationale, alternatives, agent_type.
- **`hook`** — extracted by the commit-time hook from conversation + diff. May lack rationale or alternatives for implicit decisions.

### Tier Behavior

| Tier | Decision Extraction | Review Gate | Rationale |
|------|---------------------|-------------|-----------|
| Direct | Hook: silent auto-log | None | No overhead for single-file fixes |
| Lightweight | Hook: silent auto-log | None | Minimal overhead for small changes |
| Standard | Agent writes + hook safety net | Hook blocks commit for novel decisions | Full SDD — decisions deserve review |
| Full | Agent writes + hook safety net | Hook blocks commit for novel decisions | Heavy process — marginal cost |
| Spike | Hook: silent auto-log | None | Exploratory — decisions are preliminary |

### Agent Write Protocol

Agents call the CLI whenever they document a decision in `LEARNINGS.md ### Decisions Made`:

```
uv run --project <decision-tracker-path> python -m decision_tracker write \
  --decision "<text>" --category "<type>" --agent-type "<agent>" \
  [--rationale "<why>"] [--alternatives "<alt1>" "<alt2>"] \
  [--affected-reqs "<REQ-01>"] [--affected-files "<path>"] \
  [--tier "<tier>"] [--session-id "<id>"] [--branch "<branch>"] \
  [--commit-sha "<sha>"]
```

The human-readable LEARNINGS.md entry and the machine-readable JSONL entry coexist — LEARNINGS.md is the authoring surface, `decisions.jsonl` is the audit log.

### Commit-Time Review Protocol (Standard/Full Tiers)

When the hook blocks a `git commit` (exit code 2), the agent receives a JSON message on stderr with `status: "review_required"` and a `decisions` array. The agent must:

1. **Present** each decision to the user with its `decision` text, `category`, and `confidence`
2. **Collect** the user's response for each: approve, reject (with optional reason), or edit (modify the text)
3. **Update** `.ai-work/.pending_decisions.json` — change each decision's `status` from `"pending"` to `"approved"` or `"rejected"`. For rejections, populate `rejection_reason`. For edits, update the `decision` text and set `status` to `"approved"`.
4. **Re-commit** — the hook will see the resolved pending file, append all decisions (both approved and rejected) to the log, delete the pending file, and allow the commit

If the user wants to skip review entirely, set all decisions to `"approved"` and re-commit.

### Spec Auto-Update Protocol (Standard/Full Tiers)

After collecting the user's approve/reject decisions in step 2 above, the agent checks whether any **approved** decisions have `affected_reqs` AND `.ai-work/SYSTEMS_PLAN.md` exists. If both conditions are met:

1. **Call** the amendment generator with approved decisions piped to stdin:
   ```
   echo '<decisions-json>' | uv run --project <decision-tracker-path> \
     python -m decision_tracker propose-amendment \
     --spec-path .ai-work/SYSTEMS_PLAN.md [--cwd .]
   ```
   Input: JSON array of approved decisions with `decision`, `affected_reqs`, and optional `rationale`.
   Output: JSON on stdout with `status`, `amendments` array, and optional `plan_impacts` array.

2. **Present** each proposed amendment to the user showing:
   - The REQ ID and current title vs. proposed title
   - A before/after diff of the requirement text (`current_text` vs. `proposed_text`)
   - The `change_summary` explaining what changed

3. **Collect** the user's response for each amendment: approve or reject

4. **Apply** approved amendments to `SYSTEMS_PLAN.md` using the Edit tool (replace the REQ block with `proposed_text`)

5. **Annotate the implementation plan.** If the output includes `plan_impacts`, annotate affected steps in `IMPLEMENTATION_PLAN.md` with a `[SPEC AMENDED]` blockquote warning. This can be done by calling `annotate_plan` from the decision-tracker, or by inserting the annotation manually via Edit. The annotation format:
   ```
   > **[SPEC AMENDED]** REQ-01: change summary. See SYSTEMS_PLAN.md for current requirement text.
   ```
   This makes spec drift visible to implementers and LLMs working on downstream steps.

6. **Stage** the updated `SYSTEMS_PLAN.md` and `IMPLEMENTATION_PLAN.md` alongside other changes

7. **Proceed** with step 3-4 of the commit-time review protocol (update pending file, re-commit)

The resulting commit includes code changes, spec amendments, and plan annotations atomically.

**Skip conditions**: If `propose-amendment` returns `no_spec`, `no_affected_reqs`, or `reqs_not_found`, skip this protocol entirely. If the user rejects an amendment, the spec remains unchanged for that REQ — this does not block the commit. If no `plan_impacts` are present, skip step 5.

**Scope**: This protocol applies only to the hook path (commit-time extraction) during gating tiers. Agents using the direct write path (`decision-tracker write --affected-reqs`) already manage the spec as part of their workflow.

### Consumption Patterns

| Consumer | Purpose |
|----------|---------|
| sentinel | DL01-DL05 health checks (validity, quality, coverage, frequency) |
| skill-genesis | Recurring decision patterns across features |
| verifier | Cross-reference `affected_reqs` against traceability matrix |
| systems-architect | Brownfield baseline for prior feature decisions |

### Relationship to LEARNINGS.md

- `LEARNINGS.md` is broader: gotchas, patterns, edge cases, tech debt, decisions
- `decisions.jsonl` is narrower: decisions only, machine-readable
- Decisions appear in both — not deprecated from either
- At end-of-feature, `LEARNINGS.md` is deleted per existing workflow; `decisions.jsonl` persists
