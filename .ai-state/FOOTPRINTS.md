# Footprint Registry

Maps each measurable cost a change can move to the paths it lives in and the
instrument that reads it. `scripts/check_footprint_criteria.py` reads this file:
a change that touches a registered footprint's paths must bound it in the spec's
`### Footprint Criteria` table or declare it in `### Footprints Not Measured`.

The grammar is normative in the docstring of `scripts/_footprint_grammar.py`.
Paths are comma-separated `fnmatch` globs over repo-relative POSIX paths, where
`*` crosses `/` and a leading `!` excludes. Command `none` means no instrument
exists. Suite elapsed time is deliberately unregistered: nearly every pipeline adds
a test, so registering it would make the footprint-free case pay.

The test-selection-size paths mirror `SELECTOR_FILES` in
`scripts/resolve_test_scope.py`; `scripts/test_footprints_registry.py` fails when
they drift apart.

| Footprint | Paths | Command | Reading |
|---|---|---|---|
| test-selection-size | scripts/resolve_test_scope.py, scripts/_declared_deps.py, scripts/_test_inventory.py, scripts/_python_selection.py, scripts/_native_selection.py, scripts/_repo_root.py, tests/declared-deps.toml | `python3 scripts/measure_selection_size.py --compare-ref` | selection size against a reference revision |
| always-loaded-tokens | CLAUDE.md, claude/config/CLAUDE.md.tmpl, rules/*.md, rules/_manifest.yaml | `python3 scripts/measure_token_budget.py --json` | token counts; call --json only, never --ratchet (it rewrites .ai-state/token_budget_baseline.json) |
| listing-tokens | skills/*/SKILL.md, commands/*.md, agents/*.md | `python3 scripts/measure_token_budget.py --json` | token counts; call --json only, never --ratchet (it rewrites .ai-state/token_budget_baseline.json) |
| prompt-size | agents/*.md, skills/*.md | `python3 scripts/check_agent_prompt_size.py --json` | line counts against the warn and fail ceilings |
| hook-latency | hooks/*.py, hooks/*.sh, hooks/hooks.json, !hooks/*test_*.py | none | no instrument |
| observation-log-volume | hooks/_observation_log/*, !hooks/*test_*.py | none | no instrument |
| spawn-count | rules/swe/swe-agent-coordination-protocol.md, skills/software-planning/references/coordination-details.md, agents/implementation-planner.md | none | spawn_count.py counts a pipeline that has already run, not a change |
