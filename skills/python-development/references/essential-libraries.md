# Essential Libraries

Curated, battle-tested third-party libraries by project archetype. Reference material for
the [Python Development](../SKILL.md) skill.

## Purpose

This catalog exists so a Python project doesn't reinvent functionality that a well-known,
actively-maintained library already solves well. It is a **shortlist**, not a mandate:

- Pick from here before naming a candidate library for a new capability.
- Still run the version/capability check described in the coordination protocol's
  "Library version and capability verification" step afterward — this catalog says
  *what* tends to be the right default; that check confirms the *current* version and
  capability fit before it's pinned.
- If a project already has an established stack, prefer consistency with what's already
  there over introducing a second library for the same job, even if this catalog lists a
  newer alternative.
- Every entry favors wide community adoption and a track record over trendy-but-unproven
  options. Where there's a clear current consensus pick, the table says so directly. Where
  there's a genuine ongoing debate between two solid options, both are listed with an
  honest tradeoff instead of a forced winner.

## Library Catalog by Archetype
<!-- last-verified: 2026-07-29 -->

| Archetype | Covers |
|---|---|
| [Web API / backend service](libraries-web-api.md) | HTTP frameworks, ORMs, validation, background jobs, HTTP clients |
| [CLI tools](libraries-cli.md) | Argument parsing, terminal output/TUI, packaging as an executable |
| [Data / ML pipelines](libraries-data-ml.md) | Dataframes, dataframe validation, orchestration |
| [Async / event-driven services](libraries-async.md) | Async runtimes, message queues, async task queues |
| [General-purpose](libraries-general.md) | Testing, logging, config management — useful in nearly any project |
| [Scripting / automation](libraries-scripting.md) | Small-script ergonomics: HTTP, retries, formatted output |

Most projects span more than one archetype (e.g. a web API project also needs the
general-purpose testing/logging/config picks). Read the archetype pages relevant to the
task, not the whole catalog.

## Not a Package-Manager Guide

This catalog says *which* library; it does not cover *how* to add it to a project. For
`pixi`/`uv` commands, dependency pinning, and environment setup, see the
[Python Project Management](../../python-prj-mgmt/SKILL.md) skill.
