# Eval baselines

Committed baseline summaries consumed by `/eval regression`. Each baseline is a narrow JSON document — NOT a raw trace dump (see [`dec-040`](../decisions/040-eval-framework-out-of-band.md)).

## Schema

```json
{
  "task_slug": "phase3-quality-automation",
  "captured_at": "2026-04-12T18:00:00Z",
  "expected_phases": ["research", "architecture", "planning", "implementation", "verification"],
  "expected_deliverables": [
    ".ai-work/phase3-quality-automation/SYSTEMS_PLAN.md",
    ".ai-work/phase3-quality-automation/IMPLEMENTATION_PLAN.md",
    ".ai-work/phase3-quality-automation/VERIFICATION_REPORT.md"
  ],
  "expected_exit_status": "pass",
  "span_count": 142,
  "tool_call_count": 37,
  "duration_ms_p50": 1250,
  "duration_ms_p95": 4800,
  "agent_count": 5
}
```

### Required fields

- `task_slug` — pipeline identifier.
- `captured_at` — ISO 8601 UTC timestamp.

### Optional fields

All numeric fields are optional. The diff comparator only flags drift for fields that are present.

- `expected_phases`, `expected_deliverables`, `expected_exit_status` — structural expectations.
- `span_count`, `tool_call_count`, `agent_count` — span-level counts (15% drift threshold).
- `duration_ms_p50`, `duration_ms_p95` — latency percentiles (30% drift threshold).

## Files

- `baselines/<task-slug>.json` — one baseline per pipeline.

## Refresh workflow

A baseline is regenerated manually. Since `/eval` never writes to Phoenix, refreshing is always a deliberate developer action.

```sh
# Inspect current traces against an existing baseline.
uv run --project eval praxion-evals regression \
  --baseline .ai-state/evals/baselines/<task-slug>.json

# To replace a baseline, hand-edit the JSON or regenerate with a one-off script
# that calls praxion_evals.regression.trace_reader.read_current_summary().
```
