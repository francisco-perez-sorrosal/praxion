---
description: Launch the Praxion pipeline dashboard for the current project. Opens a browser tab showing architecture, in-flight workshops, ADRs, sentinel reports, roadmap, and metrics. Requires the dashboard to be installed (part of the Praxion plugin). Delegates to praxion-dashboard for process management.
argument-hint: [project-root]
allowed-tools: Bash
---

Launch the Praxion pipeline dashboard for the current project. The dashboard is a read-only local web application over `.ai-state/` and `.ai-work/` artifacts — it never invokes an LLM.

## Process

### 1. Resolve project root

Use `$ARGUMENTS` as the project root if provided; otherwise default to `pwd`:

```bash
PROJECT_ROOT="${ARGUMENTS:-$(pwd)}"
```

### 2. Start the dashboard

Delegate to `praxion-dashboard start`:

```bash
scripts/praxion-dashboard start "$PROJECT_ROOT"
```

The script derives a deterministic port from the project root path, starts the dashboard process in the background, and prints the URL. If the dashboard is already running for this project, the script reports it as already running (idempotent — no duplicate process is started).

### 3. Surface the result

Report the URL printed by the script. If startup fails (e.g., dashboard not installed), surface the error and suggest running `scripts/praxion-dashboard install` first.

## Notes

- Manage lifecycle from the shell: `scripts/praxion-dashboard stop`, `scripts/praxion-dashboard status`, `scripts/praxion-dashboard restart`
- Use `/dashboard` again to get the URL if you've lost it — the script detects the running process and prints it
- The dashboard is macOS-only in v1; Linux users see a manual-launch hint in the script output
