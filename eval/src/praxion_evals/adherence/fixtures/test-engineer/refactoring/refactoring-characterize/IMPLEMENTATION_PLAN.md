# Plan: Characterize the entry serialisation before it moves

## Goal

Pin what the code that turns entries into JSON text and back writes and reads today, so the structural change that follows can be checked against it.

## Steps

### Step 1: [Phase: Refactoring] Characterize the entry serialisation before it moves

**Implementation**: `store.py` is about to lose the code that turns entries into the JSON text of the data file, and that text back into entries, to a new module `serialization.py`. Before that move, write characterization tests of the current behaviour: the exact file contents for a known set of entries and the entries a known file reads back to.
**Tests**: new tests under `tests/` that go through the package's public surface, and no change to production code: if a behaviour cannot be reached without a seam, say so instead of adding one.
**Done when**: the tests pass against the code as it is today, cover the entry serialisation's output and the way it is read back, and nothing outside `tests/` is changed.
