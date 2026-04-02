# context-hub Provider Reference

context-hub (`chub`) is a curated registry of ~600+ LLM-optimized API documentation packages by Andrew Ng's team. It is the default provider for the [external-api-docs](../SKILL.md) skill.

## Installation

```bash
npm install -g @aisuite/chub
```

Or use without global install via `npx`:

```bash
npx -y @aisuite/chub search "stripe"
```

**Prerequisite:** Node.js 18+.

## Configuration

Config file: `~/.chub/config.yaml` (optional -- sensible defaults without it).

```yaml
sources:
  - name: community
    url: https://cdn.aichub.org/v1       # Default public CDN
  - name: internal
    path: /path/to/local/docs            # Optional: private/team docs

source: "official,maintainer,community"  # Trust policy (filter by content source)
refresh_interval: 21600                  # Cache TTL in seconds (default: 6 hours)
output_dir: .context                     # Default output directory for -o flag
```

### Multi-Source Architecture

context-hub merges entries from multiple sources at query time. Add private documentation alongside the public registry:

1. Build private docs: `chub build /path/to/your/content/`
2. Add as a local source in `~/.chub/config.yaml`
3. Both public and private entries appear in search results

Author-prefixed IDs (`author/name`) prevent namespace collisions across sources.

## Telemetry and Feedback Controls

context-hub has two separate opt-out mechanisms:

- **`CHUB_TELEMETRY`** — passive usage analytics (PostHog). Disabled in all Praxion integrations.
- **`CHUB_FEEDBACK`** — enables the explicit `chub feedback` command for rating docs. Left **enabled** so agents can give feedback that improves doc quality for everyone.

**Per-command** (recommended in all skill examples):

```bash
CHUB_TELEMETRY=0 CHUB_FEEDBACK=1 chub <command>
```

**Persistent via config** (`~/.chub/config.yaml`):

```yaml
telemetry: false
feedback: true
```

**Environment variables** (shell profile):

```bash
export CHUB_TELEMETRY=0
export CHUB_FEEDBACK=1
```

## CLI Reference

### Search

```bash
chub search "<query>" [--json] [--source official,maintainer]
```

Returns matching docs and skills ranked by BM25 + lexical scoring. Use `--json` for machine-readable output. Use `--source` to filter by trust tier.

### Get

```bash
chub get <author/entry-id> [--lang <language>] [--file <path>] [--full] [-o <output>] [--json]
```

| Flag | Purpose |
|------|---------|
| `--lang <language>` | Language-specific version (e.g., `python`, `javascript`) |
| `--file <path>` | Fetch a specific reference file without the full doc |
| `--full` | Fetch all reference files (use sparingly -- large token cost) |
| `-o <path>` | Write to file or directory instead of stdout |
| `--json` | Machine-readable output |

Annotations (if any) auto-append to output.

### List

```bash
chub list [--json]
```

List all available entries in the registry.

### Annotate

```bash
chub annotate <author/entry-id> "<note>"
```

Store a local annotation that auto-appends to future `chub get` output. One annotation per entry (overwrites previous).

### Feedback

```bash
chub feedback <author/entry-id> <up|down> [--label <label>] ["comment"]
```

Rate an entry. Requires `CHUB_FEEDBACK=1` (the default). Available labels: `outdated`, `inaccurate`, `incomplete`, `wrong-examples`, `wrong-version`, `poorly-structured`, `accurate`, `well-structured`, `helpful`, `good-examples`.

### Cache Management

```bash
chub update              # Refresh registry from CDN
chub update --full       # Download all content for offline use
chub cache clear         # Clear local cache
```

## Content Format

context-hub entries follow the [Agent Skills specification](https://agentskills.io/specification):

- **DOC.md** -- API documentation entries. Versioned per-language (`python/1.52.0/DOC.md`). Can include reference files.
- **SKILL.md** -- Behavioral skill entries. Flat, no language/version nesting.

Both use YAML frontmatter with `name`, `description`, and `metadata` fields.

## Trust Tiers

| Tier | Meaning | Reliability |
|------|---------|-------------|
| `official` | Vendor-authored (e.g., Stripe writes Stripe docs) | Highest |
| `maintainer` | Core team or verified maintainer | High |
| `community` | Community-contributed | Variable |

Filter with `--source official,maintainer` to exclude community-contributed entries when accuracy is critical.

## Limitations

- **No semantic search** -- BM25 + lexical matching only; no embeddings
- **Pre-1.0** -- v0.1.3; API and content format may change
- **Single annotation per entry** -- overwrites, no history
- **No streaming** -- full content fetched at once
- **No programmatic API** -- CLI (`chub`) and MCP server (`chub-mcp`) only; cannot `import` as a library
