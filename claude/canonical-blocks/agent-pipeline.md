## Agent Pipeline

This project follows Praxion's tier-driven agent pipeline (Direct → Lightweight → Standard → Full, plus exploratory Spike) under the **Understand, Plan, Verify** methodology. Ephemeral pipeline artifacts live in `.ai-work/<task-slug>/` (deleted after use); permanent decisions and design docs live in `.ai-state/` (committed to git).

When Praxion's assistant tooling is active, its agent coordination protocol rule and `software-planning` skill carry the full agent roster, delegation checklists, and pipeline-branch handling. Always include expected deliverables when delegating to an agent.

Human-readable process overview: [Praxion documentation](https://github.com/francisco-perez-sorrosal/praxion#readme).
