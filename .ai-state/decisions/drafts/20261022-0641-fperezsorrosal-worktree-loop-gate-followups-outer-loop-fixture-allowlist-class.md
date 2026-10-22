---
id: dec-draft-d47d4f40
title: "A scanner allowlist entry anchored in the outer-loop directories is its own path class and may ride the acceptance-design commit"
status: proposed
category: behavioral
date: 2026-10-22
summary: "New path class between inner-loop test and state/doc: a .gitleaks.toml change whose full diff only adds comments and allowlist paths entries beginning ^tests/acceptance/ or ^tests/e2e/ and removes or changes no non-comment line; any other change to the file is production; verifier and test-engineer follow"
tags: [acceptance-design, path-classes, secret-scanning]
made_by: agent
agent_type: systems-architect
branch: worktree-loop-gate-followups
pipeline_tier: full
affected_files:
  - skills/software-planning/references/coordination-details.md
  - agents/verifier.md
  - agents/test-engineer.md
affected_reqs: [REQ-21]
supersedes_in_part: [dec-410]
---

# A scanner allowlist entry anchored in the outer-loop directories is its own path class and may ride the acceptance-design commit

## Context

td-486. An outer-loop fixture that trips the secret scanner needs a `.gitleaks.toml` allowlist entry, which was class 5 (production); committing it before acceptance design made it the first production commit, breaking acceptance independence as written.

## Decision

Insert the class *outer-loop fixture allowlist* after inner-loop test: `.gitleaks.toml`, only in a commit whose whole change to that file (its full diff, each added line placed in the file as of that commit) removes or changes no line other than a comment and adds only comments and entries of the `[allowlist]` `paths` array, each a regex beginning `^tests/acceptance/` or `^tests/e2e/`, with no alternation and no wildcard reaching beyond them; any other change to the file (a removed or changed line, `useDefault`, a rule, a looser or unanchored entry) is production. The wording is stated once, at the `coordination-details.md` Path Classes anchor; the verifier and the test-engineer cite it by name. Such a change may ride the acceptance-design commit, a commit tied to an answered Spec Question, or a planned driver-binding step. The class is decided by the path and the commit's full diff of that file. The acceptance designer reads `.gitleaks.toml` only to place the entry (input class A3, listed under Sources Read). The verifier's commit-order audit cites the class by name with a golden bad and good case; the test-engineer's acceptance-design mode may write the entry and names it in its return.

## Considered Options

### Path plus the whole change to the file (chosen)

### Path only

Rejected: every later edit of the scanner config would escape the audit.

## Consequences

- Positive: acceptance independence holds when a fixture trips the scanner; the allowance cannot carry a rule or a production path.
- Negative: the classes are no longer a pure function of the path for this one class; the verifier reads a diff for it.

## Prior Decision

dec-410 enumerated the classes as driver, scenario, inner-loop test, state/doc, production. This decision narrows that enumeration by inserting one class; the rest of dec-410 stands.
