# Decision Tracker

CLI utility for extracting and logging decisions made during AI-assisted development. Pipeline agents use `decision-tracker write` to record decisions to `.ai-state/decisions.jsonl`.

## Development

- Python 3.13+, managed with **uv** (see `pyproject.toml`)
- Source: `src/decision_tracker/`
- Tests: `tests/` — run with `uv run pytest`
- Lint/format: `uv run ruff check --fix` and `uv run ruff format`
- Dependencies: `anthropic` (LLM extraction), `pydantic` (schema validation)

## Relevant Skills

- `python-development` for Python conventions and testing patterns

## Integration

Consumed by pipeline agents (primary path) and the `extract_decisions.py` hook (safety net). Output follows the JSONL schema defined in the `decision-tracking` rule. Decisions accumulate in `.ai-state/decisions.jsonl` and are committed to git.
