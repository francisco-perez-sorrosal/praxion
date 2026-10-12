---
id: dec-001
title: Store records as a JSON file
status: accepted
category: architectural
date: 2026-01-05
summary: Records persist as one JSON document, not a database.
tags: [storage]
made_by: maintainers
affected_files:
  - storage
---

## Context

The project needs persistence with no server.

## Decision

Records are stored as one JSON document read and written whole.

## Consequences

Simple and portable; not suited to large data sets.
