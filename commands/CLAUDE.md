# Commands

Slash commands invocable during interactive sessions. Each `.md` file becomes a `/command-name` (or `/praxion:command-name` when namespaced by the plugin).

## Conventions

- Each command is a single `.md` file with YAML frontmatter
- Filename (minus `.md`) becomes the command name — choose concise, verb-first names
- `allowed-tools` frontmatter controls which tools the command can use
- Commands are user-invoked prompts, not autonomous agents — they execute in the main conversation context

## Registration

Commands use a directory glob in `.claude-plugin/plugin.json`: `"commands": ["./commands/"]`. New command files are discovered automatically — no manifest update needed.

## Modifying Commands

Load the `command-crafting` skill before creating or modifying commands. It covers frontmatter syntax, argument handling, and tool permissions.

## Canonical-Block Pairs

Several command pairs share content via `claude/canonical-blocks/<slug>.md`, embedded in each consumer command and kept byte-identical by `scripts/sync_canonical_blocks.py` (see the script's `BLOCKS` registry for the per-block fence style and consumer set). To update any canonical block, edit the canonical file and run `python3 scripts/sync_canonical_blocks.py --write`.

- **Onboarding pair** — `/new-project` (greenfield) and `/onboard-project` (existing project) share the canonical `## Agent Pipeline`, `## Compaction Guidance`, `## Behavioral Contract`, and `## Praxion Process` blocks (code-fenced; the commands install them into the user project's CLAUDE.md). Idempotency predicates are paired across both commands so re-runs and cross-runs compose without duplication. User-facing docs: `docs/greenfield-onboarding.md`, `docs/existing-project-onboarding.md`.
- **Commit-process pair** — `/co` (commit) and `/cop` (commit and push) share `commit-process` (HTML-comment-fenced; the block IS the prompt's Process steps 1–6, not an installed payload, so it reads inline as Markdown rather than as a code block).
