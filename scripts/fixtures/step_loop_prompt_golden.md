Task slug: demo
Spawn request: s7-a2-implement
You are implementing Step 7 of IMPLEMENTATION_PLAN.md, attempt 2 of 2.

<step id="7">
### Step 7: [Phase: Refactoring] Add the widget [depends-on: 6]

**Assignee**: implementer
**Implementation**: Build the widget.
**Files**: `src/widget.py`, `tests/test_widget.py`
**Read-only**: `tests/acceptance/test_widget.py::test_widget_returns_its_id`
**Check**: `uv run pytest tests/test_widget.py -q` expects pass>=2 fail=0
**Done when**: the widget exists.
</step>

<previous-attempts>
attempt 1 · agent a3f9c2e17b55d0e1 · turn-cap 100/100 · check unmet: fail=: expected =0, observed 3 · no commit
Uncommitted edits to src/widget.py, tests/test_widget.py remain; read them first.
</previous-attempts>

<health-guards source="TASK_BRIEF.md § Health Guards">
- [ ] derived test scope green after every step
- [ ] no commit while a subagent runs
</health-guards>

<corrections source="WIP.md § Corrections in force">
- Run scratch work as scripts under the scratchpad.
- Give each unit-test file a unique basename.
</corrections>

<finish>
1. Record a `## Step 7` section in /repo/.ai-work/demo/TEST_RESULTS.md ending with your Check: Result: line.
2. Flip only Step 7's line in /repo/.ai-work/demo/WIP.md; never edit an Attempts: or Check: line.
3. Stop in a committable state and never commit: the step-loop driver commits once it verifies.
4. End with at most 5 lines whose last line is one marker: [COMPLETE], [BLOCKED] (add a Spec
   Question if a due outer-loop test contradicts the spec), [CONFLICT] or [PARTIAL].
</finish>
