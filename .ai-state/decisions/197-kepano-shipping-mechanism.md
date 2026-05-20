---
id: dec-197
title: Ship kepano/obsidian-skills via fetch-at-install (shallow git clone) to a global location
status: superseded
category: architectural
date: 2026-05-19
summary: Procedure 1 fetches kepano/obsidian-skills via `git clone --depth 1` into ~/.local/share/praxion/kepano-skills at install time; Procedure 2 links into per-project .claude/skills/obsidian/. No vendoring, no submodule.
tags: [obsidian, install, kepano, dependency-management, shape-b]
made_by: agent
agent_type: systems-architect
branch: worktree-obsidian-shape-b-onboarding
pipeline_tier: standard
affected_files:
  - install.sh
  - scripts/install-obsidian-deps.sh
  - commands/onboard-project.md
  - commands/new-project.md
re_affirms: dec-198
superseded_by: dec-199
---

## Context

Shape B (per its sibling ADR fragment) requires `kepano/obsidian-skills` to be present on the operator's machine and per-project linked into `<project>/.claude/skills/obsidian/`. Three credible shipping mechanisms exist:

- **Vendor** — copy the upstream repo contents into Praxion's tree (e.g., `vendor/kepano-skills/`) and update by re-copying on upstream changes.
- **Git submodule** — track upstream as a submodule; operators run `git submodule update` to refresh.
- **Fetch-at-install** — `install.sh` does a shallow `git clone` to a deterministic global location; refresh on `--relink`.

The choice has real costs. Vendoring fattens Praxion's repo and creates a maintenance burden every time upstream changes. Submodules add operator-side friction (every clone needs `--recurse-submodules` or a follow-up update) and tend to confuse new contributors. Fetch-at-install adds a network dependency at install time but mirrors the pattern Praxion already uses for `chub` (npm install) and `scc` (brew install / go install) — install-time external dependencies are well-precedented in `install.sh`.

The strategic-signal practitioner here (Steph Ango / kepano, Obsidian CEO) is the maintainer; while single-maintainer risk is real, the maintainer's incentive alignment (the upstream is reputation-bearing for the CEO of the product) makes the risk lower than a typical community plugin. Smart Connections' December 2025 paywall episode is the cautionary tale referenced in the research — that risk is real but addressable by switching shipping mechanism if it ever materializes.

## Decision

Procedure 1 (`install.sh`'s new `install_obsidian_deps` step, delegated to `scripts/install-obsidian-deps.sh`) installs `kepano/obsidian-skills` via:

```bash
git clone --depth 1 https://github.com/kepano/obsidian-skills "${KEPANO_SKILLS_ROOT:-${HOME}/.local/share/praxion/kepano-skills}"
```

A marker file at `${HOME}/.config/praxion/obsidian-skills.path` records the resolved checkout path so Procedure 2 can find it deterministically.

Refresh is opt-in via `./install.sh code --relink`, which performs `git -C <path> pull --ff-only`. Idempotent re-runs of the default install path are no-ops (the existing checkout is detected and left alone).

Procedure 2 links the global checkout into per-project `<project>/.claude/skills/obsidian/` (symlink on macOS/Linux; copy fallback on Windows or when `--copy` is requested).

If kepano-skills is later vendored as a follow-up, the marker file's recorded path moves from `${HOME}/.local/share/praxion/kepano-skills` to a Praxion-tree path; downstream consumers don't care.

## Considered Options

### Option 1 — Fetch-at-install via shallow git clone (chosen)

- **Pros:** Praxion's repo stays clean. Refresh is one operator action. Mirrors the existing chub/scc install-time external-dependency pattern. Easy to switch later if needed.
- **Cons:** Network dependency at install time; install on offline machines warns and skips. Operators may end up with different revisions over time (mitigated by `--relink` and the marker file's recorded revision).

### Option 2 — Vendor verbatim

- **Pros:** No network dependency at install time. Praxion controls the revision exactly.
- **Cons:** Fattens Praxion's repo with content Praxion didn't author. Drift between upstream and the vendored copy requires manual sync. Every kepano-skills update is a Praxion PR. Misaligns with the "shipped artifact" boundary in `rules/swe/shipped-artifact-isolation.md` (Praxion ships skills it authors; vendored skills muddy that contract).

### Option 3 — Git submodule

- **Pros:** Tracks upstream cleanly. Refresh is `git submodule update`.
- **Cons:** Operator friction — every `git clone` of Praxion needs `--recurse-submodules`. Submodules confuse new contributors. The submodule pointer commits add noise to Praxion's history every time upstream advances.

### Option 4 — Operator-installs-manually

- **Pros:** Zero new Praxion install logic.
- **Cons:** Operator burden; defeats Praxion's onboarding-ergonomics design. Inconsistent revisions across machines with no visibility.

## Consequences

**Positive:**

- Praxion's repo size and review surface unchanged.
- Operators get the latest kepano-skills on first install; refresh is opt-in via `--relink`.
- Easy to switch shipping mechanism later (vendoring becomes a one-PR change if kepano-skills upstream becomes a problem).
- Mirrors existing install-time external-dependency patterns in `install.sh` — no new operational shape introduced.

**Negative:**

- Network dependency at install time (graceful degradation: warn + skip).
- Single-maintainer upstream risk persists (mitigated by escape route: switch to vendoring if needed; documented in this ADR).
- Operators end up with different kepano-skills revisions across machines unless they all run `--relink` regularly. Documented in `docs/obsidian-shape-b.md`.

## Prior Decision

This ADR re-affirms `dec-198` (Shape B default-on) by specifying the shipping mechanism that makes the default-on choice operationally tractable. No prior decision is being superseded; the re-affirmation here is the cross-reference between the two coupled choices.
