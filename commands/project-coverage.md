---
description: Run the project's canonical coverage target and render a terminal summary using the test-coverage skill
allowed-tools: [Bash, Read, Grep, Glob]
---

Locate, invoke, and render the project's test coverage via the [test-coverage](../skills/test-coverage/SKILL.md) skill. This command is a **thin wrapper** — target discovery, invocation, and rendering live in the skill; this file only handles pre-flight sanity, skill activation, and surfacing the rendered output.

Load the `test-coverage` skill when executing this command. Every non-trivial decision — which target to run, how to parse the artifact, what a "+2.1pp" delta means — is the skill's responsibility.

## Process

### 1. Pre-flight

Confirm the environment before activating the skill:

- **Git worktree check.** The skill discovers targets relative to the repo root and writes `coverage.xml` there. Fail fast if this is not a git checkout:

  ```bash
  git rev-parse --is-inside-work-tree
  ```

  If the command exits non-zero, stop and surface: "Not inside a git worktree — `/project-coverage` requires a git repository to locate the project root and a canonical coverage target."

- **Language detection.** Probe the repo for the primary language by inspecting project manifests (`pyproject.toml`, `package.json`, `Cargo.toml`, `go.mod`). The `test-coverage` skill ships a language-reference layer; v1 supports Python. If the detected language has no matching reference under `skills/test-coverage/references/`, stop and surface the gap — do not invent a probe order.

### 2. Load the Skill

Activate [`test-coverage`](../skills/test-coverage/SKILL.md) and load its language reference for the detected language (e.g., `skills/test-coverage/references/python.md` for Python projects). The skill defines three responsibilities — **locate, invoke, render** — and this command exercises all three in order.

### 3. Locate the Target

Delegate target discovery to the skill. Follow the probe order declared in the loaded language reference (for Python: pixi tasks → pytest-cov config in `pyproject.toml` → raw `pytest --cov` fallback → Makefile target). Stop at the first hit.

### 4. Invoke the Target

Run the located target via the project's package or environment manager when one is detected (the language reference prescribes the invocation pattern — for Python that means `pixi run <task>`, `uv run pytest`, or plain `pytest` depending on what the probe found). Stream coverage-tool output to stderr; reserve stdout for the rendered summary.

### 5. Render the Result

After successful invocation, locate the produced artifact (the Python reference pins `coverage.xml` at the project root by default), parse it, and render a terminal summary using the skill's presentation conventions:

- **Overall percentage** with threshold-band color: red `< 60%`, yellow `60% ≤ x < 80%`, green `x ≥ 80%`.
- **Delta** from the prior run, if one is discoverable, formatted as `+N.Npp` / `-N.Npp` / `+0.0pp` — never bare `%` and never `+N.N%`.
- **Per-file breakdown** with columns in the fixed order `path | covered/total | % | delta`. Paths are repo-relative; `covered/total` is a raw line ratio; `%` carries band color; `delta` is empty when no prior run exists.

A short legend ("pp = percentage points") is helpful on first render for readers unfamiliar with the notation.

## Failure Modes

All three failure modes are visible to the user; this command never silently swallows errors.

- **No target found.** All four probes in the language reference failed. Surface the structured result from the skill and point the user at the language reference's setup guidance (for Python: the copy-pasteable default coverage config block in `skills/test-coverage/references/python.md`). Do **not** attempt to install `pytest-cov` or any other coverage tool — the skill is a dispatcher, not an installer.

- **Target exited non-zero.** The invoked coverage target ran but failed (test failure, collection error, missing tool, environment mismatch). Surface the target's stderr as-is and the exit code. Do not parse or render a partial artifact if one was left behind — a failed run's artifact is unreliable.

- **No artifact produced.** The target ran to completion with exit 0, but the expected artifact path (for Python: `coverage.xml` at the project root) is absent. Surface the expected path and suggest the project's config may be writing to a non-default location — the language reference documents the expected path contract. Do not fall through to a guessed path.

## Notes

- **Thin wrapper, not a reimplementation.** Target-discovery order, invocation conventions, artifact-path contracts, and presentation invariants all live in the `test-coverage` skill and its language references. If behavior needs to change, change it in the skill — not here.
- **Freshness owned by the caller.** `/project-coverage` always invokes the target (the user explicitly asked). Other callers of the skill (the `/project-metrics --refresh-coverage` flag, the verifier at its discretion) own their own freshness decisions; this command does not coordinate with them.
- **Override points live in the skill.** Threshold cutoffs (60 / 80) and per-file column order are invariants the skill's render functions expose for per-project override. Projects that need different bands override them via the render API, not via this command's flags.
