---
id: dec-483
draft_id: dec-draft-20e33f68
title: The model-routing rule loads by path scope on the agent definitions, with a hook-delivered resident at session start
status: accepted
category: architectural
date: 2026-10-31
summary: rules/swe/agent-model-routing.md flips from hook-deliver to symlink with paths agents/** and the routing policy reference; a new hook-deliver rule rules/swe/agent-model-routing-resident.md declares resident_of and carries the resolution order, the alias note, the restated directive with its deviation list and the policy pointer; the tier table and its cells stay byte-identical so the Codex adapter and the parity gate are unchanged.
tags: [rules, startup-context-diet, moves, model-routing, path-scope]
made_by: agent
agent_type: systems-architect
branch: worktree-model-routing-move
pipeline_tier: standard
affected_files:
  - rules/swe/agent-model-routing.md
  - rules/swe/agent-model-routing-resident.md
  - rules/_manifest.yaml
  - scripts/regenerate_rules_manifest.py
re_affirms: dec-480
---
## Context

The tier table (~1,335 tokens) reached every session through SessionStart injection, though every spawn already routes by its definition's `model:` floor and `scripts/check_model_routing_parity.py` holds that floor equal to the table. A hook-delivered rule cannot be path-scoped: `hooks/inject_rules.py` injects whole bodies and never reads `paths:`; only Claude Code's native loading of linked rules honours a path scope.

## Decision

Reuse dec-480's resident machinery. The parent becomes `install: symlink`, `load: path_scoped`, `paths: [agents/**, skills/agent-crafting/references/model-routing-policy.md]` (first frontmatter key, inside the token reading's 8-line head). The resident is `core: false`, `load: always_on`, `install: hook-deliver`, `resident_of: rules/swe/agent-model-routing.md`, takes the parent's slot in `HOOK_DELIVER_ORDER`, and is skipped by the Cursor exporter and the Codex bridge through their existing checks. Every resident line is a parent line (kernel I1). The parent body changes only in its directive paragraph (see the companion directive decision).

## Considered Options

### Resident as a hook-deliver projection (chosen)
One move pattern; blacklistable; arrives with the plugin update; adapter and parity gate untouched.

### Rename: the resident takes the old path, the table moves to a new file
Keeps blacklist ids and eval probes, but breaks the Codex adapter's fixed path, the parity gate, the pre-commit pattern and every text locating the table.

### Keep the parent body byte-identical
Zero churn in earlier frozen tests, but the resident would carry the stale always-pass directive, its false fall-through claim and four table rows.

## Consequences

- Positive: ~900 always-loaded tokens saved; kernels, adapter output and parity unchanged; Codex reach unchanged (rule stays `claude_only`).
- Negative: four earlier frozen acceptance observations are re-declared; managed-project authors lack the path-loaded table until `install.sh` reruns; `agents/**` also fires on a managed project's own `agents/` tree; Windows ignores user-scope `paths:` (dec-480's limit).

Activation: no — the honest-uncertainty gate does not fire; dec-480's precedent and concrete option costs decide it.
