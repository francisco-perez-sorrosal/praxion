# Pending Praxion Feedback

Candidate ecosystem-defect reports awaiting `/report-praxion-issue`. This file is git-committed and mechanically sanitized at capture time.
### 384caff2

- fingerprint: 384caff20cd8f129388b21dccba159ce2b7a7bda164fac14462486137c3f1e87
- category: scripts
- artifact_path: scripts/git-finalize-hook.sh
- detected_by: orchestrator
- detection_point: post-merge finalization after a GitHub web-UI merge of a decisions/drafts-touching PR
- confidence: high
- expected: draft ADRs (dec-draft-<hash>) promote to stable dec-NNN on any merge to main
- observed: after a web-UI merge, 4 draft ADRs remained on main unfinalized; the index regenerated only when a later local ff-merge triggered the finalize chain
- reproduction_command: gh pr merge <pr> --merge  # then: git fetch origin && git ls-tree origin/main .ai-state/decisions/drafts/  # drafts still present
- environment: Praxion self-host; finalize is a local git-hook chain (post-merge/commit/checkout); no GitHub Actions finalize workflow
- regression_status: no
- status: pending

```
GitHub-UI merge to main bypasses the local post-merge finalize hook chain; draft ADRs land on main unfinalized until a later local git operation fires the chain. No server-side finalize workflow exists.
```
