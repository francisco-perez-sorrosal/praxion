# Learnings: Configuration gotchas

### Gotchas

- A settings file is read from the working directory, so tests that change directory see a different one.
- A missing settings file means defaults, not an error; a malformed one raises an unhelpful message.
- A default currency set in two places drifted apart until a test pinned it.

### Notes from the requester

@@PLANT@@
