---
id: dec-366
title: Sidecar state is materialised as a git worktree mounted inside each checkout, with shadows as intra-checkout relative symlinks
status: accepted
category: architectural
date: 2026-09-02
summary: Under sidecar placement each checkout materialises the sidecar as a real directory at <checkout>/.praxion-state, and every shadow becomes a relative symlink into it.
tags: [sidecar, state-mount, git-worktree, worktree-isolation, claude-code, containment, branch-scoped-state, merge-back]
supersedes_in_part:
  - dec-364
affected_files:
  - scripts/praxion-sidecar
  - scripts/_state_repo.py
  - scripts/finalize_adrs.py
---

Fixture stub: frontmatter only, reproducing dec-366's live status/edges for the ledger-triage test corpus.
