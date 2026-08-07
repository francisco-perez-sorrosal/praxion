# Test Topology — parallel-safety fixture

Fixture for the `parallel_safe` canaries in `scripts/test_resolve_test_scope.py`.

Two safe groups plus two unsafe ones. The second unsafe group matters: the trunk
only forbids mixing unsafe groups with *safe* ones, but two unsafe groups may
each hold the same exclusive resource, so the resolver keeps them apart too.
Every group uses `pytest-globs` so that a merge failure shows up as paths landing
in one argv rather than as an unrelated strategy difference.

## Group: safe-one

```yaml
id: safe-one
title: Safe one
subsystems:
  - alpha
tier: unit
selectors:
  - strategy: pytest-globs
    arg: ["tests/test_safe_one.py"]
file_dependencies:
  - "src/safe_one/**"
parallel_safe: true
shared_fixture_scope: none
```

## Group: safe-two

```yaml
id: safe-two
title: Safe two
subsystems:
  - beta
tier: unit
selectors:
  - strategy: pytest-globs
    arg: ["tests/test_safe_two.py"]
file_dependencies:
  - "src/safe_two/**"
parallel_safe: true
shared_fixture_scope: none
```

## Group: exclusive-port

```yaml
id: exclusive-port
title: Binds a fixed port
subsystems:
  - gamma
tier: e2e
selectors:
  - strategy: pytest-globs
    arg: ["tests/test_exclusive_port.py"]
file_dependencies:
  - "src/server/**"
parallel_safe: false
shared_fixture_scope: per-suite
shared_state: network
```

## Group: exclusive-db

```yaml
id: exclusive-db
title: Owns the shared database
subsystems:
  - delta
tier: integration
selectors:
  - strategy: pytest-globs
    arg: ["tests/test_exclusive_db.py"]
file_dependencies:
  - "src/db/**"
parallel_safe: false
shared_fixture_scope: per-suite
shared_state: external_service
```
