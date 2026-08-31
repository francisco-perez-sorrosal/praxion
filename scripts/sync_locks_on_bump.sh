#!/usr/bin/env bash
# Commitizen pre_bump_hook: regenerate uv lockfiles after version_files are
# rewritten but before the bump commit, so the release tag points at a tree
# whose locks match the version it declares. cz bump commits with `git
# commit -a`, which folds these tracked-file updates into the bump commit.
#
# Registered in pyproject.toml [tool.commitizen] pre_bump_hooks; the release
# workflow (.github/workflows/release.yml) provides `uv` on the runner.
set -euo pipefail

repo_root="$(git rev-parse --show-toplevel)"

# Every uv project whose pyproject.toml version is bumped by commitizen
# (see [tool.commitizen] version_files) must re-lock here, or its uv.lock
# records the previous release's version inside the tagged tree.
for dir in "." "task-chronograph-mcp" "eval"; do
  echo "sync_locks_on_bump: uv lock in ${dir}" >&2
  (cd "${repo_root}/${dir}" && uv lock)
done
