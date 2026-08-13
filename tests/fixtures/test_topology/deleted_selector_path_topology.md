# Test Topology — deleted-selector-path fixture

Fixture for the selector-resolution canary in `scripts/test_resolve_test_scope.py`
(td-143). Reconstructs the incident this check exists for: a module split left a
`pytest-globs` selector naming the pre-split path, and nothing caught it -- the
group stayed green by exiting 4 without ever running. Four groups, each isolating
one shape, so the check must discriminate rather than fire on every selector.

## Group: has-real-path

`chain_topology.md` is a real sibling fixture in this same directory -- this
selector must NOT be flagged.

```yaml
id: has-real-path
title: Selector naming a real path
subsystems:
  - alpha
tier: unit
selectors:
  - strategy: pytest-globs
    arg: ["chain_topology.md"]
file_dependencies:
  - "src/alpha/**"
parallel_safe: true
shared_fixture_scope: none
```

## Group: has-deleted-path

The exact shape of the historical incident: a module was renamed or split, and
the selector kept naming the path that no longer exists.

```yaml
id: has-deleted-path
title: Selector naming a deleted path
subsystems:
  - beta
tier: unit
selectors:
  - strategy: pytest-globs
    arg: ["scripts/test_removed_module_shim.py"]
file_dependencies:
  - "src/beta/**"
parallel_safe: true
shared_fixture_scope: none
```

## Group: has-empty-glob

A glob that matches zero files is the same false-green in a different shape --
the group stays green by silently selecting nothing.

```yaml
id: has-empty-glob
title: Selector glob matching nothing
subsystems:
  - gamma
tier: unit
selectors:
  - strategy: pytest-globs
    arg: ["nonexistent_dir/*.py"]
file_dependencies:
  - "src/gamma/**"
parallel_safe: true
shared_fixture_scope: none
```

## Group: has-nonempty-glob

A glob matching at least one real file -- this selector must NOT be flagged.

```yaml
id: has-nonempty-glob
title: Selector glob matching something
subsystems:
  - delta
tier: unit
selectors:
  - strategy: pytest-globs
    arg: ["*.md"]
file_dependencies:
  - "src/delta/**"
parallel_safe: true
shared_fixture_scope: none
```
