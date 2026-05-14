# Rework Manifest — test-pipeline

Generated: 2026-05-14T08:00:00Z by verifier (report test-pipeline-2026-05-14T08).
Source: [VERIFICATION_REPORT.md](VERIFICATION_REPORT.md). 2 rework worktrees proposed.

| # | Worktree | Agent | Severity | Tier | Class | Headline |
|---|----------|-------|----------|------|-------|----------|
| 1 | `fix-auth-validation` | systems-architect | critical | standard | implementation | Session validator silently accepts expired tokens |
| 2 | `redesign-token-cache` | systems-architect | important | standard | architecture | Token cache layer mixes responsibilities |

## Row details

### Row 1 — fix-auth-validation

```json
{
  "id": "rw-3b9f6ba0",
  "worktree_name": "fix-auth-validation",
  "target_agent": "systems-architect",
  "severity": "critical",
  "recommended_tier": "standard",
  "class": "implementation",
  "headline": "Session validator silently accepts expired tokens",
  "finding_refs": ["#fail-1", "#fail-2"],
  "td_refs": ["td-041"],
  "confidence": "high",
  "dedup_against": [],
  "notes": ""
}
```

### Row 2 — redesign-token-cache

```json
{
  "id": "rw-a1c47e12",
  "worktree_name": "redesign-token-cache",
  "target_agent": "systems-architect",
  "severity": "important",
  "recommended_tier": "standard",
  "class": "architecture",
  "headline": "Token cache layer mixes responsibilities",
  "finding_refs": ["#warn-2", "#fail-3"],
  "td_refs": ["td-042"],
  "confidence": "high",
  "dedup_against": [],
  "notes": ""
}
```
