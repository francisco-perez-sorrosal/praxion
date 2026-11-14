# Plan: Characterize the note serialisation before it moves

## Goal

Pin what the code that turns notes into the JSON text of the mirror file writes today, so the structural change that follows can be checked against it.

## Steps

### Step 1: [Phase: Refactoring] Characterize the note serialisation before it moves

**Implementation**: `repository.py` is about to lose the code that turns the notes into the JSON text written to the mirror file to a new module `serialization.py` in the `notes` package. Before that move, write characterization tests of the current behaviour: the exact mirror file contents for a known set of notes.
**Tests**: new tests under `tests/` that go through the package's public surface, and no change to production code: if a behaviour cannot be reached without a seam, say so instead of adding one.
**Done when**: the tests pass against the code as it is today, cover the mirror file's contents for known notes, and nothing outside `tests/` is changed.
