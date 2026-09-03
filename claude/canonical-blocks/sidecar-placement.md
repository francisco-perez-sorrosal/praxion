## Praxion Sidecar Placement

This project onboarded with `--placement sidecar`: Praxion's project intelligence lives
**outside** this repository, in a separate git-tracked sidecar repository at
`~/.praxion/sidecars/<sidecar-id>`. The state mount at `<project>/.praxion` is a real
`git worktree` of that sidecar; `.ai-state/`, this file, and `.claude/settings.local.json`
are symlinks into it, excluded via `.git/info/exclude` — **your commits in this repository
never include Praxion state**, and a `git add` through one of these symlinks fails loudly
rather than silently leaking one in.

`docs/architecture.md`, when shared, cites ADRs by **id text** (e.g. `dec-NNN`), never by
an `.ai-state/` path — a path reference would dangle for anyone without sidecar access.

Run `praxion-sidecar doctor` to confirm the mount and shadow projection are intact (mount
present, shadows linked, no state branches awaiting merge-back). See
`docs/onboarding.md#placement` for the full placement model.
