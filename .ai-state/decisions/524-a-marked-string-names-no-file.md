---
id: dec-524
draft_id: dec-draft-8e054b0f
title: A string marked test-scope:not-a-path is no path literal in the test-scope resolver
status: accepted
category: behavioral
date: 2026-11-22
summary: A string constant on a line carrying test-scope:not-a-path is not indexed as a path literal, so it connects its module to no file; the eval catalog's outer-loop directory names, which name paths in the project an implementer task grades, carry it. The marker removes an edge only where a person writes it, and the selection audit still reports a read that only a marked literal named.
tags: [test-scope, resolver, path-literal, selection, eval]
made_by: agent
agent_type: orchestrator
branch: main
pipeline_tier: lightweight
affected_files:
  - scripts/_python_selection.py
  - scripts/test__python_selection.py
  - eval/src/praxion_evals/adherence/catalog.py
  - skills/testing-strategy/references/test-selection.md
  - scripts/CLAUDE.md
affected_reqs: []
---

## Context

The resolver reads every string constant in a pocket module as a possible path. A constant with a `/` and no wildcard matches the end of a path, including one of its directories, so a module holding `"tests/acceptance"` depends on every file under that directory, and every test importing the module comes with it. The eval catalog's `OUTER_LOOP_DIRECTORIES = ("tests/acceptance", "tests/e2e")` names directories of the scratch project an implementer task grades; it reads no file of this repository. Through it, a change to a step-loop driver file (named by an acceptance driver, which the catalog then "read") selected 115 of the eval pocket's 117 test files, a run of about 480 s, so a driven step's gate answered `gate-running` and took about three `record` calls (td-688).

The resolver's contract is that it never narrows: a change it cannot account for widens. A false edge is the opposite failure, a selection too wide, and the resolver cannot tell from a string alone whether a module reads the path it names.

## Decision

A string constant on a line whose text carries `test-scope:not-a-path` is no path literal: the literal index skips it, so it connects its module to no file. The check is line-scoped (the constant's first or last line), as the repository's other same-line markers are (`id-citation-discipline:ignore`, `gate-liveness:ignore`). Only path literals honour it; import, layout, declared and pocket-drive edges are unchanged. The eval catalog's constant carries the marker, with a comment naming whose directories they are.

## Considered Options

### A same-line marker (chosen)

A person states, at the string, that it names another tree. Narrowing happens only where someone wrote it and can be reviewed in the diff; the selection audit, which traces the files each test actually opens, still reports a test that reads a file only a marked literal named.

### A resolver rule: directory literals in production modules stop after one hop

It would need no marker, but it narrows every directory literal held by a production module, including modules that do scan the directory they name (checkers that walk `agents/` or `tests/fixtures`), whose importing tests then miss the changes they depend on. That breaks the never-narrows contract by rule rather than by declaration.

### Rewrite the catalog's constant so it is no literal path

Splitting the string or joining its parts at run time removes the edge with no resolver change, but it bends the code to the resolver's heuristic and leaves the next such constant to be found the same way.

## Consequences

- A step-loop driver file's change now selects 4 eval test files, not 115; a change to the catalog itself still selects every test that imports it.
- A wrong marker narrows a selection. The selection audit is the check that catches it, and CI's unfiltered suites still run everything.
- The marker is one more same-line convention to know; the test-selection reference and the resolver's module docstring state it.
