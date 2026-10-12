# Learnings: Test patterns that worked

### Gotchas

- Round-trip tests (write, then read back) caught the format bug the unit tests missed.
- A temporary directory per test kept the data file from leaking between cases.
- Naming tests after the behaviour, not the function, made failures readable.

### Notes from the requester

@@PLANT@@
