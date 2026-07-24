---
name: Ecosystem Defect
about: A defect in a shipped Praxion artifact (hook, block, agent, script, skill), captured by the healing sidecar. Filed automatically via /report-praxion-issue, or manually here.
title: "[ecosystem-defect] "
labels: bug, auto-filed, from-managed-project
assignees: ''
---

<!--
This body IS the §5.2 schema the reporter renders: one artifact, both entry
paths. Filing automatically? /report-praxion-issue fills every section for you.
Filing manually? Complete the human sections below and leave the machine-only
sections blank -- a maintainer will backfill them from the capture ledger.
-->

## Fingerprint

<!-- leave blank if filing manually -->

## Plugin / Component

- Category: <!-- hooks | blocks | agents | scripts | skills -->
- Artifact: <!-- repo-relative path to the shipped artifact, e.g. scripts/report_praxion_issue.py -->

## Capture Provenance

<!-- leave blank if filing manually -->

## Expected vs Observed

- Expected: <!-- what the artifact should do -->
- Observed: <!-- what it actually did -->

## Reproduction Command

<!-- the exact command that surfaces the defect -->

## Evidence Excerpt (sanitized)

```
paste the minimal sanitized evidence here (no secrets, no absolute paths, no usernames)
```

## Environment

<!-- OS, Python version, Praxion / plugin version -->

## Regression Status

<!-- new | regression | unknown -->
