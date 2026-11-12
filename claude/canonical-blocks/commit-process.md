1. Run `git status` and `git diff --staged` (or `git diff` if nothing staged)
   - After a hook or script rewrote the tree, re-read `git status --short` before staging. `git add <path>` stages nothing, and errors, for a tracked path whose file is gone; stage the deletion with `git rm` or `git add -u`, and check the commit with `git show --stat` afterwards.
   - Read every row of `git diff --cached --name-status`, the `D` rows you never added included: a `git rm` staged earlier rides into the next commit, even a pathspec one.
2. Analyze the changes to understand their purpose and scope
3. **Quality gate**: If any staged or changed files are source code (not docs or config), detect the project's formatters and linters from config files (`pyproject.toml`, `package.json`, etc.) and run them on the changed code files: format, then lint in fix mode, then type check if configured. If violations remain after auto-fix, stop and present them before proceeding. Re-stage any files modified by formatters.
4. **Single vs multiple commits**: If the diff clearly mixes distinct targets (e.g. `feat` + `fix`, `docs` + `refactor`, `test` + `chore`), treat as multiple logical tasks. Otherwise, proceed with one commit.
5. **When splitting**:
   - Group changes by logical task (by file and/or by diff hunks). Prefer grouping by file when files have a single clear purpose; use partial staging (`git add -p` or file subsets) when one file contains unrelated edits.
   - For each group in a sensible order (e.g. fix before feat, code before docs): stage only that group, craft a conventional commit message for that type, create the commit. Repeat until all changes are committed.
6. **When not splitting**: Stage files if needed (prefer specific files over `git add -A`), craft the commit message following our commit conventions, create the commit.
   - A `.pre-commit-config.yaml` with unstaged edits makes pre-commit refuse every commit ("Your pre-commit configuration is unstaged"): commit that file, or the gate fix, first.
   - A message passed with `-F` must not end with a blank line: the authorship hook reports it as a modification.
