---
paths:
- rules/**
- skills/**
- agents/**
- commands/**
- claude/config/**
core: false
---

## Shipped Artifact Isolation

Shipped artifacts — the contents of `rules/`, `skills/`, `agents/`, `commands/`, and `claude/config/` that `install_claude.sh` installs into a user's global Claude config — must not reference **specific entries** inside `.ai-state/` or `.ai-work/`.

`.ai-state/` is a per-project meta-instrument (Praxion's own dogfooding state when working on this repo; the *user's* state once the plugin is installed elsewhere). `.ai-work/` is ephemeral per-pipeline-run state. Neither location is part of the Praxion product. Any specific `dec-NNN`, `ADR-NN`, `REQ-<slug>-NN`, `SPEC_<name>_YYYY-MM-DD.md`, `sentinel_reports/SENTINEL_REPORT_<timestamp>.md`, or `idea_ledgers/IDEA_LEDGER_<timestamp>.md` embedded in a shipped artifact dangles the moment the plugin lands in another project.

### What to do instead

- **Path *shapes* are fine and encouraged.** `.ai-state/decisions/<NNN>-<slug>.md`, `.ai-work/<task-slug>/`, `.ai-state/specs/SPEC_<name>_YYYY-MM-DD.md`, `.ai-state/sentinel_reports/SENTINEL_REPORT_<timestamp>.md`, `.ai-state/idea_ledgers/IDEA_LEDGER_<timestamp>.md`, `.ai-state/metrics_reports/METRICS_REPORT_<timestamp>.{md,json}` all describe conventions without hardcoding entries.
- **Inline the rationale.** When a shipped artifact wants to explain *why* a behavior exists, state the reason in words. Do not point at an ADR number — the reader has no way to resolve it.
- **Illustrative placeholders are fine.** Format examples like `REQ-01`, `dec-NNN`, `SPEC_auth_YYYY-MM-DD.md` teach a convention without referencing an entry. Prefer obviously-placeholder-looking values (`YYYY-MM-DD`, `NNN`) over plausible-looking concrete values that could be mistaken for real entries.

### Praxion-internal files are exempt

`ROADMAP.md`, `CHANGELOG.md`, `README*.md`, `docs/`, `memory-mcp/`, `task-chronograph-mcp/`, `eval/`, `hooks/`, `scripts/`, `install_*.sh`, `tests/`, `.github/` — these are Praxion's own narrative and internal implementation. Their content is **never injected into an agent's context window**: they are read by someone browsing this repo's source, or executed as code, so a concrete `dec-NNN` in them resolves for every reader who can see it. The isolation rule does not apply to them.

**This exemption is about context injection, not about delivery.** Several exempt paths *are* shipped: `install_claude.sh` symlinks `scripts/*` onto `~/.local/bin`, `/onboard-project` Phase 4 symlinks the user's `.git/hooks/*` at `scripts/git-finalize-hook.sh`, `hooks/` registers as plugin lifecycle hooks, and `task-chronograph-mcp/` ships as an MCP server. They are exempt because their text never lands in a downstream context window — not because they stay behind. Do not reuse this list as a "what reaches managed projects" boundary; it answers a different question and gets `hooks/` and `scripts/` backwards.

### Self-test before committing a shipped artifact

- Did I cite a specific ADR number, REQ-ID tied to an archived spec, SPEC filename, SENTINEL_REPORT timestamp, or IDEA_LEDGER date?
- If yes — can I describe the rationale inline, or point at the conventional shape (`dec-NNN`, `SPEC_<name>_YYYY-MM-DD.md`) instead?
- If a concrete reference feels load-bearing, the content probably belongs under an exempt file (e.g., `docs/architecture.md`, `ROADMAP.md`) rather than a shipped surface.
