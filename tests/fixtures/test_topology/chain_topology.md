# Test Topology — closure-chain fixture

Fixture for the closure canaries in `scripts/test_resolve_test_scope.py`.

The boundary chain is deliberately three links long — `alpha -> beta -> gamma` —
because a two-link chain cannot tell one-hop closure apart from transitive
closure. Only `gamma` proves that `phase` stops after exactly one hop.

## Group: alpha

```yaml
id: alpha
title: Alpha subsystem
subsystems:
  - alpha
tier: unit
selectors:
  - strategy: pytest-globs
    arg: ["tests/test_alpha.py"]
file_dependencies:
  - "src/alpha/**"
integration_boundaries:
  - beta
parallel_safe: true
shared_fixture_scope: none
```

## Group: beta

```yaml
id: beta
title: Beta subsystem
subsystems:
  - beta
tier: integration
selectors:
  - strategy: pytest-globs
    arg: ["tests/test_beta.py"]
file_dependencies:
  - "src/beta/**"
integration_boundaries:
  - gamma
parallel_safe: true
shared_fixture_scope: per-file
```

## Group: gamma

```yaml
id: gamma
title: Gamma subsystem
subsystems:
  - gamma
tier: integration
selectors:
  - strategy: pytest-globs
    arg: ["tests/test_gamma.py"]
file_dependencies:
  - "src/gamma/**"
parallel_safe: true
shared_fixture_scope: none
```
