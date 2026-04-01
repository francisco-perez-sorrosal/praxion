# Decision Tracking Protocols

Procedural protocols for writing and reviewing decisions in `.ai-state/decisions.jsonl`. Reference material for the [Software Planning](../SKILL.md) skill. For the JSONL schema, status/source semantics, and tier behavior, see the [decision-tracking rule](../../../rules/swe/decision-tracking.md).

## Agent Write Protocol

Agents call the CLI whenever they document a decision in `LEARNINGS.md ### Decisions Made`:

```
uv run --project <decision-tracker-path> python -m decision_tracker write \
  --decision "<text>" --category "<type>" --agent-type "<agent>" \
  [--rationale "<why>"] [--alternatives "<alt1>" "<alt2>"] \
  [--affected-reqs "<REQ-01>"] [--affected-files "<path>"] \
  [--tier "<tier>"] [--session-id "<id>"] [--branch "<branch>"] \
  [--commit-sha "<sha>"]
```

The human-readable LEARNINGS.md entry and the machine-readable JSONL entry coexist -- LEARNINGS.md is the authoring surface, `decisions.jsonl` is the audit log.

## Commit-Time Review Protocol (Standard/Full Tiers)

When the hook blocks a `git commit` (exit code 2), the agent receives a JSON message on stderr with `status: "review_required"` and a `decisions` array. The agent must:

1. **Present** each decision to the user with its `decision` text, `category`, and `confidence`
2. **Collect** the user's response for each: approve, reject (with optional reason), or edit (modify the text)
3. **Update** `.ai-work/.pending_decisions.json` -- change each decision's `status` from `"pending"` to `"approved"` or `"rejected"`. For rejections, populate `rejection_reason`. For edits, update the `decision` text and set `status` to `"approved"`.
4. **Re-commit** -- the hook will see the resolved pending file, append all decisions (both approved and rejected) to the log, delete the pending file, and allow the commit

If the user wants to skip review entirely, set all decisions to `"approved"` and re-commit.

## Spec Auto-Update Protocol (Standard/Full Tiers)

After collecting the user's approve/reject decisions in step 2 above, the agent checks whether any **approved** decisions have `affected_reqs` AND `.ai-work/<task-slug>/SYSTEMS_PLAN.md` exists. If both conditions are met:

1. **Call** the amendment generator with approved decisions piped to stdin:
   ```
   echo '<decisions-json>' | uv run --project <decision-tracker-path> \
     python -m decision_tracker propose-amendment \
     --spec-path .ai-work/<task-slug>/SYSTEMS_PLAN.md [--cwd .]
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

**Skip conditions**: If `propose-amendment` returns `no_spec`, `no_affected_reqs`, or `reqs_not_found`, skip this protocol entirely. If the user rejects an amendment, the spec remains unchanged for that REQ -- this does not block the commit. If no `plan_impacts` are present, skip step 5.

**Scope**: This protocol applies only to the hook path (commit-time extraction) during gating tiers. Agents using the direct write path (`decision-tracker write --affected-reqs`) already manage the spec as part of their workflow.
