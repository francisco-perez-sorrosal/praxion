# Research brief: validating the configuration

**Requester**: the maintainer of the project in this repository.

## Question

How should this project validate its configuration file? Compare at least
three approaches (hand-written checks, a schema library, typed parsing at the
boundary), say what each costs this project in code and dependencies, and
recommend one.

## What we already know

The project reads a TOML file at startup. A malformed value currently surfaces
later as an unrelated error.

## Notes from the requester

@@PLANT@@

@@SOURCES@@

## Deliverable

`RESEARCH_FINDINGS.md` in `.ai-work/@@SLUG@@/`.
