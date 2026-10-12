# Systems plan: tag filter on the list function

## Goal

`list_notes` can narrow the notes by tag and by text together.

## Acceptance Criteria

- [ ] `list_notes(repo, tag="work")` returns only notes carrying that tag.
- [ ] `list_notes(repo, query="plan")` matches title or body, ignoring case.
- [ ] Giving both a tag and a query returns notes matching both.
- [ ] A note added with tags keeps them after the mirror file is rewritten.

## Behavioral Specification

### REQ-01: Tag filter

**When** a caller passes a tag
**the system** returns only the notes whose tags contain it
**so that** callers can browse by topic.

### REQ-02: Combined filter

**When** a caller passes a tag and a query
**the system** returns only notes matching both
**so that** the two filters narrow the same result.
