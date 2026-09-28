# End-to-end tests

Tests in this directory drive the whole system through its real entry points (a CLI, an HTTP API, a UI) the way a user or a client would. They are the outer loop: they prove the pieces work together, not how each piece works.

**Ownership rule.** The implementer runs these tests and makes them pass by changing production code. The implementer never edits, deletes, skips or weakens a test here. A test that looks wrong is raised with its author, not changed to go green.
