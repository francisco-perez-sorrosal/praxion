# Plan: Extract the note serialisation

## Goal

Give the code that turns notes into the JSON text of the mirror file a module of its own, without changing what the program does.

## Steps

### Step 1: [Phase: Refactoring] Extract the note serialisation into its own module

**Implementation**: Move the code in `repository.py` that turns the notes into the JSON text written to the mirror file into a new module `serialization.py` in the `notes` package, and re-wire every caller to use the new module. Behaviour stays exactly as it is: same file contents, same public names, no new feature. Delete what the move leaves unused, and leave no forwarding function or re-export behind.
**Tests**: the existing tests pass before and after the move; if the code to move has no test through the package's public surface, pin its current output first.
**Done when**: the serialisation code lives only in `serialization.py`, every caller imports it from there, no dead code or compatibility shim is left, behaviour is unchanged, and the tests pass.
