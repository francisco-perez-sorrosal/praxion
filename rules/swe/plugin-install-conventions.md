---
paths: ["install*.sh", "scripts/install*.sh", "claude/canonical-blocks/**/*.md", "commands/onboard-project*.md", "commands/new-project.md", "new_project.sh"]
core: false
---

## Plugin Install Conventions

When shipping a foreign skill bundle from a Claude Code marketplace repository,
prefer the upstream-documented install method. This rule encodes the preference order
and flags the anti-patterns that produce subtly broken installs.

### Prefer the upstream-documented install method, in order

1. **Marketplace install** — if the upstream repo has `.claude-plugin/marketplace.json`
   and `.claude-plugin/plugin.json`, use Claude Code's plugin marketplace:
   ```bash
   claude plugin marketplace add <github-source>
   claude plugin install <plugin-id>@<marketplace>
   ```
   Bash-invocable non-interactively; the same code path the in-session slash commands
   `/plugin marketplace add` and `/plugin install` reach. Do not fetch and place files
   manually when the upstream ships a marketplace manifest.

2. **`npx skills add`** — if the upstream documents the Skills Registry pattern and the
   package is published there, use that path. Requires Node.js; less preferred than the
   Claude Code native marketplace.

3. **Manual fetch** — only when neither of the above is available. Mirror the upstream's
   documented layout exactly, and verify discovery depth before committing (see Self-test
   below).

### Self-test before shipping any new skill-bundle integration

- Does the upstream repo have `.claude-plugin/marketplace.json` or `plugin.json`?
  If yes — use marketplace; do not reimplement the install lifecycle.
- After install, does `find -L <install-location> -name "SKILL.md"` return the expected
  SKILL.md files at the depth Claude Code's skill discovery expects?
  If not — the layout is broken; fix the depth, not the symptom.
- Are you owning `--check` / `--uninstall` / `--update` lifecycle for a resource the
  Claude Code plugin system already manages? If so, thin-wrap to `claude plugin <verb>`;
  do not reimplement.
- Does the install write anything to the per-project tree (symlinks, directories)?
  Marketplace-installed plugins land at user scope (`~/.claude/plugins/cache/`) — no
  per-project mutation should be needed for skill discovery.

### Anti-patterns to avoid

- **Cloning + symlinking the upstream repo at the wrong depth.** The kepano/obsidian-skills
  repo layout is `skills/<name>/SKILL.md`. Placing the cloned repo root at
  `<project>/.claude/skills/<plugin-name>/` causes SKILL.md files to land at
  `.claude/skills/<plugin-name>/skills/<name>/SKILL.md` — Claude Code's skill resolver
  does not look two levels deep, so the skills appear present on disk but are never loaded.
  Always verify `find -L <install-path> -name "SKILL.md"` before committing to a
  non-marketplace install path.

- **Inventing a parallel install path** (e.g., `~/.local/share/<your-project>/<plugin>/`)
  when Claude Code's own plugin system already manages where plugins land. Marker files
  and env-var pointers add plumbing with no benefit when `claude plugin list` provides
  the same discoverability contract.

- **Owning the install lifecycle** (`--check`/`--uninstall`/`--refresh`) for resources
  the Claude Code plugin system manages. Thin-wrap the CLI verbs when the install script
  must surface these operations; do not reimplement them.

### Reference

See `rules/swe/shipped-artifact-isolation.md` for the constraint against referencing
specific `.ai-state/` entries in shipped artifacts — the same discipline applies here:
describe anti-patterns by their shape, not by internal decision record identifiers.
