# Memory JSON Schema

Full schema reference for `.ai-state/memory.json`. Loaded on-demand from the memory skill.

## Table of Contents

- [Top-Level Structure](#top-level-structure)
- [Memory Entry Schema](#memory-entry-schema)
- [Category Definitions](#category-definitions)
- [Field Constraints](#field-constraints)
- [Markdown-KV Format](#markdown-kv-format)
- [Consolidation Actions](#consolidation-actions)
- [Example Document](#example-document)

## Top-Level Structure

```json
{
  "schema_version": "1.3",
  "session_count": 0,
  "memories": {
    "user": {},
    "assistant": {},
    "project": {},
    "relationships": {},
    "tools": {},
    "learnings": {}
  }
}
```

| Field | Type | Description |
|-------|------|-------------|
| `schema_version` | string | `"1.3"`. No migration from earlier versions -- fresh start only |
| `session_count` | integer | Number of sessions started via `session_start`. Default `0` |
| `memories` | object | Container with one key per category |

## Memory Entry Schema

```json
{
  "memories": {
    "user": {
      "username": {
        "value": "@fperezsorrosal",
        "summary": "GitHub username for identification",
        "created_at": "2026-02-09T14:00:00Z",
        "updated_at": "2026-02-09T14:00:00Z",
        "valid_at": "2026-02-09T14:00:00Z",
        "invalid_at": null,
        "tags": ["personal", "identity"],
        "confidence": null,
        "importance": 8,
        "source": { "type": "user-stated", "detail": null },
        "access_count": 3,
        "last_accessed": "2026-02-10T10:00:00Z",
        "status": "active",
        "links": [
          { "target": "user.email", "relation": "related-to" }
        ]
      }
    }
  }
}
```

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `value` | string | Yes | -- | The memory content |
| `summary` | string | No | auto-generated | One-line description (~100 chars) for index browsing. Auto-generated from first 100 chars of `value` if not provided |
| `created_at` | string | Yes | -- | ISO 8601 UTC timestamp of creation |
| `updated_at` | string | Yes | -- | ISO 8601 UTC timestamp of last modification |
| `valid_at` | string \| null | No | `created_at` | When entry became valid. Set on creation |
| `invalid_at` | string \| null | No | `null` | When entry was soft-deleted. `null` for active entries |
| `tags` | string[] | No | `[]` | Classification labels for filtering and search |
| `confidence` | number \| null | No | `null` | Certainty level 0.0-1.0 for assistant self-knowledge |
| `importance` | integer | No | `5` | Priority from 1 (low) to 10 (critical) |
| `source` | object | No | `{"type": "session", "detail": null}` | Origin metadata |
| `source.type` | string | Yes | `"session"` | One of: `"session"`, `"user-stated"`, `"inferred"`, `"codebase"` |
| `source.detail` | string \| null | No | `null` | Additional source context |
| `access_count` | integer | No | `0` | Times recalled or found via search |
| `last_accessed` | string \| null | No | `null` | ISO 8601 UTC timestamp of last access |
| `status` | string | No | `"active"` | `"active"`, `"archived"`, or `"superseded"` |
| `links` | object[] | No | `[]` | Unidirectional links to other entries |
| `links[].target` | string | Yes | -- | `"category.key"` format |
| `links[].relation` | string | Yes | -- | One of: `"supersedes"`, `"elaborates"`, `"contradicts"`, `"related-to"`, `"depends-on"` |

## Category Definitions

### user

Personal information, preferences, and habits about the human user.

**Typical keys**: `first_name`, `last_name`, `username`, `email`, `github_url`, `response_style_preference`

**Tags**: `personal`, `identity`, `alias`, `preference`, `workflow`

### assistant

Self-identity and self-knowledge the assistant accumulates about its own patterns.

**Typical keys**: `name` (required), `response_style`, `effective_approaches`, `common_mistakes`

**Tags**: `identity`, `self-awareness`, `effectiveness`, `correction`

### project

Project-specific conventions, architecture decisions, and technical choices.

**Typical keys**: `tech_stack`, `architecture_pattern`, `naming_convention`, `testing_approach`

**Tags**: `convention`, `architecture`, `tooling`, `decision`

### relationships

How the user and assistant interact -- delegation style, trust, collaboration patterns.

**Typical keys**: `delegation_style`, `trust_level`, `feedback_style`, `preferred_autonomy`

**Tags**: `user-facing`, `collaboration`, `trust`, `feedback`

### tools

Tool preferences, environment configuration, CLI shortcuts.

**Typical keys**: `package_manager`, `editor`, `shell`, `clipboard_tool`, `version_control`

**Tags**: `user-preference`, `environment`, `cli`, `configuration`

### learnings

Cross-session insights, gotchas, discovered patterns, and debugging solutions.

**Typical keys**: Descriptive slugs like `hook_payload_field_names`, `api_drift_auth_service`

**Tags**: `gotcha`, `debugging`, `pattern`, `insight`

## Field Constraints

| Constraint | Rule |
|------------|------|
| Key format | Lowercase, `_` and `-` for separation |
| Key uniqueness | Unique within category |
| Timestamp format | ISO 8601 UTC: `YYYY-MM-DDTHH:MM:SSZ` |
| Tags | Lowercase, hyphen-separated, each under 50 chars |
| Confidence | `null` or float 0.0-1.0 |
| Importance | Integer 1-10, default 5 |
| Summary | ~100 chars, auto-generated if not provided |
| JSON formatting | 2-space indent, trailing newline |

## Markdown-KV Format

The `browse_index()` tool and `search(detail="index")` return entries in Markdown-KV format:

```markdown
## user (3 entries)
- **first_name**: Francisco [personal, identity]
- **email**: fperezsorrosal@gmail.com [personal, identity]
- **username**: GitHub username @fperezsorrosal [personal, identity]

## learnings (2 entries)
- **otel-relay-pattern**: OTel spans via chronograph relay, not direct hook export [observability]
- **api-drift-auth**: Auth service migrated from v2 to v3 endpoints [gotcha, api]
```

Soft-deleted entries (when `include_historical=True`) are annotated: `~~superseded~~`

## Consolidation Actions

The `consolidate()` tool accepts a JSON array of action objects:

### merge

Combine multiple entries into one. Sources are soft-deleted.

```json
{
  "action": "merge",
  "sources": [{"category": "learnings", "key": "old-entry-1"}, {"category": "learnings", "key": "old-entry-2"}],
  "target": {"category": "learnings", "key": "merged-entry"},
  "merged_value": "Combined insight from both entries",
  "merged_summary": "Combined insight covering both patterns"
}
```

### archive

Set entry status to `"archived"`.

```json
{"action": "archive", "category": "learnings", "key": "stale-entry"}
```

### adjust_confidence

Update an entry's confidence score.

```json
{"action": "adjust_confidence", "category": "assistant", "key": "response_style", "confidence": 0.9}
```

### update_summary

Replace an entry's summary field.

```json
{"action": "update_summary", "category": "project", "key": "tech_stack", "summary": "Python 3.13+ with uv, FastMCP for memory server"}
```

## Example Document

A complete v1.3 document:

```json
{
  "schema_version": "1.3",
  "session_count": 12,
  "memories": {
    "user": {
      "username": {
        "value": "@fperezsorrosal",
        "summary": "GitHub username for identification",
        "created_at": "2026-02-09T14:00:00Z",
        "updated_at": "2026-02-09T14:00:00Z",
        "valid_at": "2026-02-09T14:00:00Z",
        "invalid_at": null,
        "tags": ["personal", "identity"],
        "confidence": null,
        "importance": 8,
        "source": { "type": "user-stated", "detail": null },
        "access_count": 5,
        "last_accessed": "2026-02-10T16:30:00Z",
        "status": "active",
        "links": [{ "target": "user.email", "relation": "related-to" }]
      }
    },
    "learnings": {
      "hook-payload-fields": {
        "value": "Claude Code hooks receive JSON on stdin with hook_event_name, session_id, agent_id, cwd, tool_name, tool_input fields.",
        "summary": "Hook JSON stdin payload includes event name, session/agent IDs, cwd, tool info",
        "created_at": "2026-02-09T14:00:00Z",
        "updated_at": "2026-02-09T14:00:00Z",
        "valid_at": "2026-02-09T14:00:00Z",
        "invalid_at": null,
        "tags": ["gotcha", "claude-code", "hooks"],
        "confidence": 0.95,
        "importance": 8,
        "source": { "type": "session", "detail": null },
        "access_count": 2,
        "last_accessed": "2026-02-10T11:00:00Z",
        "status": "active",
        "links": []
      }
    }
  }
}
```
