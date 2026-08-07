# Test Topology — glob-shape fixture

Fixture for the glob-semantics canaries in `scripts/test_resolve_test_scope.py`.

Each group isolates one glob shape so a matching regression names the shape that
broke. `**` gets three groups because it is the shape `fnmatch` cannot express
and `PurePath.match` only handles from 3.13 — the two obvious implementations a
future editor might reach for.

## Group: single-segment-star

`src/single/*.py` must NOT reach `src/single/nested/deep.py`. This is the
`fnmatch` trap: its `*` compiles to `.*`, which crosses `/`.

```yaml
id: single-segment-star
title: Single-segment star
subsystems:
  - alpha
tier: unit
selectors:
  - strategy: pytest-globs
    arg: ["tests/test_single.py"]
file_dependencies:
  - "src/single/*.py"
parallel_safe: true
shared_fixture_scope: none
```

## Group: trailing-doublestar

`src/tree/**` must reach every depth below `src/tree/`, and nothing at `src/`.

```yaml
id: trailing-doublestar
title: Trailing double star
subsystems:
  - beta
tier: unit
selectors:
  - strategy: pytest-globs
    arg: ["tests/test_tree.py"]
file_dependencies:
  - "src/tree/**"
parallel_safe: true
shared_fixture_scope: none
```

## Group: interior-doublestar

`src/mid/**/conf.py` must match zero intervening segments as well as many.

```yaml
id: interior-doublestar
title: Interior double star
subsystems:
  - gamma
tier: unit
selectors:
  - strategy: pytest-globs
    arg: ["tests/test_mid.py"]
file_dependencies:
  - "src/mid/**/conf.py"
parallel_safe: true
shared_fixture_scope: none
```

## Group: leading-doublestar

`**/legacy.py` must match at the repo root and at any depth.

```yaml
id: leading-doublestar
title: Leading double star
subsystems:
  - delta
tier: unit
selectors:
  - strategy: pytest-globs
    arg: ["tests/test_legacy.py"]
file_dependencies:
  - "**/legacy.py"
parallel_safe: true
shared_fixture_scope: none
```

## Group: exact-path

An unwildcarded pattern matches that path and nothing else. A bare directory
name is deliberately NOT expanded to its subtree: under-matching escalates,
which is the safe direction.

```yaml
id: exact-path
title: Exact path
subsystems:
  - epsilon
tier: unit
selectors:
  - strategy: pytest-globs
    arg: ["tests/test_exact.py"]
file_dependencies:
  - "src/exact/one.py"
  - "src/bare"
parallel_safe: true
shared_fixture_scope: none
```
