# Systems plan: Export everything as one document

## Goal

Let the project hand all of its stored records to other tools as one JSON document, without changing how records are stored today.

## Design

A single exporter walks the store and serializes it; the store is read-only during the walk.
