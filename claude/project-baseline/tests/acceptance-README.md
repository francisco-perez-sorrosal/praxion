# Acceptance tests

Tests in this directory encode the project's acceptance criteria: what the system must do, stated from the outside. They are the outer loop, written from the specification and independently of the code that satisfies them.

**Ownership rule.** The implementer runs these tests and makes them pass by changing production code. The implementer never edits, deletes, skips or weakens a test here. A test that looks wrong is raised with its author, not changed to go green.
