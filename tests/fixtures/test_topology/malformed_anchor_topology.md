# Test Topology — malformed fixture (parser canary input)

Deliberately broken. `scripts/test_resolve_test_scope.py` feeds this file to the
loader and asserts it fails loudly rather than dropping the group.

`alpha` is well-formed; `beta` reaches for a YAML alias. That ordering is the
point — the loader has already produced one good group by the time it meets the
construct it cannot read, which is exactly the situation in which "skip it and
carry on" looks harmless. It is not: an unparsed group is silently absent from
the topology, so its `file_dependencies` never match, so its tests never run and
nothing says so. The parser must raise with a file and a line instead.

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
parallel_safe: true
shared_fixture_scope: none
```

## Group: beta

```yaml
id: beta
title: Beta subsystem
subsystems:
  - beta
tier: unit
selectors:
  - strategy: pytest-globs
    arg: ["tests/test_beta.py"]
file_dependencies: *alpha_deps
parallel_safe: true
shared_fixture_scope: none
```
