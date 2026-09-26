# Provenance: `journal_golden.jsonl`

Byte-identical copy of a real Claude Code `Workflow` run's `journal.jsonl`,
captured for `workflow_run_cost.py` / `_workflow_run.py` / `check_lens_isolation.py`
fixture tests (td-232, td-226). Content is harness keys and Praxion file names
only -- safe to commit.

- **Source run id**: `wf_4b5deef4-d2b`
- **Source session id**: `9254055a-27a2-4206-8a7f-843fe3aa6391`
- **Source path** (not committed, host-local):
  `~/.claude/projects/-Users-fperez-dev-praxion/9254055a-27a2-4206-8a7f-843fe3aa6391/subagents/workflows/wf_4b5deef4-d2b/journal.jsonl`
- **Byte size**: 740
- **sha256**: `457e707a53ef4309a97904a46d45c4d0f3cb87f676448b560cbc453c51d9878b`

A test in `scripts/test_workflow_run_cost_worldread.py` asserts the committed
fixture's sha256 still equals the value recorded above -- a tripwire against a
pre-commit whitespace/EOF fixer or an editor re-save silently breaking
byte-identity with the source run.

Re-verify after any change to this fixture:

```bash
wc -c scripts/test_fixtures/workflow_run/journal_golden.jsonl
shasum -a 256 scripts/test_fixtures/workflow_run/journal_golden.jsonl
```
