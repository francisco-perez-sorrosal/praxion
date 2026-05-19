# validate_references fixture corpus

This directory is a **miniature repo layout** the `validate_references.py`
validator can walk. Each file exercises a specific row of the SYSTEMS_PLAN.md
§4.4 link-class table or an ignore-mechanism row.

Tests in `../test_validate_references.py` point the validator at this tree
(often after copying to `tmp_path` for mutations) and assert on the produced
findings.

## Layout

```
validate_references/
├── README.md                        # this file
├── skills/
│   ├── alpha/
│   │   ├── SKILL.md                 # hosts most link-class scenarios
│   │   ├── references/
│   │   │   ├── valid_target.md      # real target for intra-skill OK link
│   │   │   └── anchored.md          # hosts cross-file anchors
│   │   ├── contexts/
│   │   │   └── ignored_via_frontmatter.md   # file-level opt-out
│   │   └── assets/
│   │       └── sample-template.md   # walk-exclusion: assets/ not validated
│   └── beta/
│       └── SKILL.md                 # sibling-skill link target
├── rules/
│   └── swe/
│       └── sample-rule.md           # cross-artifact target
├── agents/
│   └── sample-agent.md              # cross-artifact target
├── commands/
│   └── sample-command.md            # cross-artifact target
├── scripts/
│   └── sample.py                    # code-file (allowlisted) target
├── .ai-state/
│   └── decisions/
│       └── 001-sample.md            # cross-artifact target
└── .ai-work/
    └── should-be-excluded.md        # validator must not walk into this
```

## Scenarios per file

Each markdown file has a `<!-- SCENARIO: … -->` header block at the top
describing which acceptance-criterion row it exercises. This is the spec
trace -- tests assert that running the validator on the fixture produces the
finding level named there.

Finding level legend:

- **FAIL** -- broken link/anchor, must appear in report with `level: FAIL`
- **WARN** -- suspicious but non-blocking (ambiguous slug, path into ignored dir)
- **OK** -- no finding (external URL, inside allowlist, ignored by directive)
