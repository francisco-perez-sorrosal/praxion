## Compaction Guidance

When this conversation compacts, always preserve: the active pipeline stage and task slug, the current WIP step number and status, acceptance criteria from the systems plan, and the list of files modified in the current step. The Praxion `PreCompact` hook snapshots in-flight pipeline documents to `.ai-work/PIPELINE_STATE.md` (one consolidated snapshot at the `.ai-work/` root, with a per-task-slug section for each active pipeline) — re-read that file after compaction to restore orientation.
