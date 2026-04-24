# Fixture Specification — `minimal_repo/`

This document is the **authoritative specification** for the `minimal_repo/` git fixture consumed by `test_git_collector.py`. The implementer of Step 5a MUST build the fixture repo exactly to this spec; the test suite's golden-value assertions are pinned against the metric values derived here.

The implementer of Step 5a also creates three auxiliary fixtures: `empty_repo/` (single-commit baseline), `single_author_repo/` (truck-factor = 1 case), and `coupling_repo/` (dense co-change for change-coupling assertions). Those smaller fixtures are specified in separate sections below.

**Design rationale.** The fixture is intentionally small — ≤12 commits, ≤5 files, <50KB — so every golden value is hand-computable and verifiable by a reader without running the collector. Commits pin `GIT_AUTHOR_DATE` and `GIT_COMMITTER_DATE` to make SHAs deterministic, but tests assert **invariants** (commit counts, per-file churn sums, co-change pair counts, ownership percentages) rather than exact SHAs — this keeps the spec robust to any minor format drift in the implementer's commit recipe.

**Fixture root**: `scripts/project_metrics/tests/fixtures/minimal_repo/`.
**Committed to Praxion repo**: yes — the fixture's own `.git/` directory is tracked by Praxion (it is the subject of the test). The fixture's `.git/` must NOT be listed in any `.gitignore`; the implementer verifies with `git check-ignore scripts/project_metrics/tests/fixtures/minimal_repo/.git`.

---

## Authors

Three fictional authors, using the `.test` TLD (RFC 2606 reserved, safe for examples):

| Name        | Email                 | Role                                     |
|-------------|-----------------------|------------------------------------------|
| Alice Smith | `alice@example.test`  | Primary contributor (7 commits)          |
| Bob Jones   | `bob@example.test`    | Secondary contributor (2 commits)        |
| Carol Lee   | `carol@example.test`  | Minor contributor (1 commit)             |

## Files

| Path         | Purpose                                      |
|--------------|----------------------------------------------|
| `README.md`  | Repo readme (1 commit)                       |
| `core.py`    | Primary module (7 commits, Alice + Bob)      |
| `helpers.py` | Helper module (4 commits, Alice + Bob)       |
| `docs.md`    | Documentation (2 commits, Alice + Carol)     |

## Commit Timeline (10 commits, 2026-02-15 → 2026-03-30)

All timestamps are UTC; `GIT_AUTHOR_DATE` and `GIT_COMMITTER_DATE` are set to the same value so both the author-date and committer-date are fixed.

| # | Author | UTC timestamp             | Message                  | Files changed (after this commit)                                     |
|---|--------|---------------------------|--------------------------|-----------------------------------------------------------------------|
| 1 | Alice  | 2026-02-15T10:00:00+00:00 | `init: README`           | +`README.md` (3 lines)                                                |
| 2 | Alice  | 2026-02-20T10:00:00+00:00 | `feat: add core`         | +`core.py` (10 lines)                                                 |
| 3 | Alice  | 2026-02-25T10:00:00+00:00 | `feat: add helpers`      | `core.py` (+2 lines), +`helpers.py` (5 lines)                         |
| 4 | Bob    | 2026-03-01T10:00:00+00:00 | `refactor: core`         | `core.py` (+3 lines, -2 lines)                                        |
| 5 | Alice  | 2026-03-05T10:00:00+00:00 | `feat: extend helpers`   | `core.py` (+1 line, -1 line), `helpers.py` (+4 lines, -1 line)        |
| 6 | Bob    | 2026-03-10T10:00:00+00:00 | `fix: core and helpers`  | `core.py` (+2 lines, -1 line), `helpers.py` (+1 line, -1 line)        |
| 7 | Alice  | 2026-03-15T10:00:00+00:00 | `docs: add user guide`   | +`docs.md` (8 lines)                                                  |
| 8 | Alice  | 2026-03-20T10:00:00+00:00 | `feat: expand core`      | `core.py` (+5 lines, -2 lines)                                        |
| 9 | Carol  | 2026-03-25T10:00:00+00:00 | `docs: polish user guide`| `docs.md` (+3 lines, -1 line)                                         |
| 10| Alice  | 2026-03-30T10:00:00+00:00 | `chore: polish`          | `core.py` (+2 lines, -1 line), `helpers.py` (+2 lines, -1 line)       |

### File content after each commit

File content is minimal and deterministic. The implementer uses any character content that produces the exact `+X/-Y` numstat values listed above. Recommended recipe: start each file with a comment block stamped `# file: <name>, rev N` and add/remove enumerated placeholder lines. Exact byte content is not load-bearing (tests do not read file bodies — only `git log --numstat`).

**Minimum viable content** for each commit (the implementer picks any deterministic content; below is one valid recipe):

Commit 1 — `README.md`:
```
# minimal_repo
Fixture repository for GitCollector tests.
Do not edit directly.
```

Commit 2 — `core.py` (new, 10 lines):
```
# core module
def f1():
    return 1

def f2():
    return 2

def f3():
    return 3
```
(blank lines between functions count toward the 10-line total; any 10-line body that produces numstat `10/0` is acceptable)

Commits 3–10 — append or replace lines to produce the exact `+X/-Y` numstat values per the table. The implementer validates with `git log --numstat --all` after building: every row must match the table.

---

## Commit Recipe (for implementer)

```bash
cd scripts/project_metrics/tests/fixtures/minimal_repo
git init -q -b main

# Commit 1 — Alice init
cat > README.md <<'EOF'
# minimal_repo
Fixture repository for GitCollector tests.
Do not edit directly.
EOF
GIT_AUTHOR_NAME="Alice Smith" \
GIT_AUTHOR_EMAIL="alice@example.test" \
GIT_AUTHOR_DATE="2026-02-15T10:00:00+00:00" \
GIT_COMMITTER_NAME="Alice Smith" \
GIT_COMMITTER_EMAIL="alice@example.test" \
GIT_COMMITTER_DATE="2026-02-15T10:00:00+00:00" \
  git add README.md && \
  GIT_AUTHOR_NAME="Alice Smith" GIT_AUTHOR_EMAIL="alice@example.test" \
  GIT_AUTHOR_DATE="2026-02-15T10:00:00+00:00" \
  GIT_COMMITTER_NAME="Alice Smith" GIT_COMMITTER_EMAIL="alice@example.test" \
  GIT_COMMITTER_DATE="2026-02-15T10:00:00+00:00" \
  git commit -q -m "init: README"

# (... repeat for commits 2-10 per the table above ...)
```

The implementer writes a build script (e.g., `build_minimal_repo.sh`) that executes the ten commits in order. The script is re-runnable: `rm -rf minimal_repo/.git` and re-run to rebuild from the content files. The content files themselves live in the final state after commit 10; the script replays history by checking out intermediate content for each commit.

**Alternative — simpler recipe**: build the repo with a Python script using `subprocess.run` and the `GIT_*_DATE` env vars; Python string formatting makes the 10-commit loop readable. Either approach is fine. The output (`.git/` directory) is what matters.

**Verification step** — after building, run:
```bash
git -C scripts/project_metrics/tests/fixtures/minimal_repo log --numstat --pretty=format:'%H%n%an%n%at' > /tmp/fixture-log.txt
```
and manually eyeball the output against the table above. All 10 commits, all 4 authors, all numstat values must match.

---

## Golden Metric Values (90-day window from 2026-04-23 reference)

All 10 commits fall within the 90-day window starting at `run_reference_time = 2026-04-23T00:00:00Z` (last commit on 2026-03-30, i.e., 24 days ago; first commit on 2026-02-15, i.e., 67 days ago).

### Per-file churn (`lines_added + lines_deleted`)

| File         | Breakdown                                                                     | Total |
|--------------|-------------------------------------------------------------------------------|-------|
| `core.py`    | 10+2 +(3+2)+(1+1)+(2+1)+(5+2)+(2+1)  = 10+2+5+2+3+7+3                         | **32** |
| `helpers.py` | 5 +(4+1)+(1+1)+(2+1)           = 5+5+2+3                                      | **15** |
| `docs.md`    | 8 +(3+1)                                                                       | **12** |
| `README.md`  | 3                                                                              |  **3** |

**`churn_total_90d` = 32 + 15 + 12 + 3 = 62**

### Per-file age (days since first commit, with `reference_time = 2026-04-23T00:00:00Z`)

| File         | First commit date | Age (days) |
|--------------|-------------------|------------|
| `README.md`  | 2026-02-15        | 67         |
| `core.py`    | 2026-02-20        | 62         |
| `helpers.py` | 2026-02-25        | 57         |
| `docs.md`    | 2026-03-15        | 39         |

**Implementer note**: age depends on a reference time (`now`). For tests to be deterministic, the `GitCollector` MUST expose a `reference_time` injection point (constructor kwarg, or via `CollectionContext` extension, or module-level override). Recommended: honor a `PROJECT_METRICS_REFERENCE_TIME` env var (ISO 8601) when set, else `datetime.now(timezone.utc)`. Tests will set this env var to `2026-04-23T00:00:00Z` before invoking `collect()`. If the implementer prefers a different injection mechanism, update this spec and `test_git_collector.py` in lock-step.

### Change coupling (pairs co-changing in ≥3 commits)

Co-change counts (pairs touched together in a single commit):

| Pair                           | Commits       | Count |
|--------------------------------|---------------|-------|
| (`core.py`, `helpers.py`)      | 3, 5, 6, 10   | **4** |
| (`core.py`, `README.md`)       | —             | 0     |
| (`core.py`, `docs.md`)         | —             | 0     |
| (`helpers.py`, `docs.md`)      | —             | 0     |
| (`helpers.py`, `README.md`)    | —             | 0     |
| (`docs.md`, `README.md`)       | —             | 0     |

**Coupled pairs at threshold ≥3**: exactly one — `(core.py, helpers.py)` with count **4**.

### Bird ownership (per-file, added-line based)

Ownership = lines-added-by-author / total-lines-added-to-file. Author is "major" if ownership ≥ 5%; "minor" if < 5%.

| File         | Alice added | Bob added | Carol added | Total added | Alice %  | Bob %   | Carol % |
|--------------|-------------|-----------|-------------|-------------|----------|---------|---------|
| `core.py`    | 10+2+1+5+2=20 | 3+2=5    | 0           | 25          | **80.0%** | **20.0%** | 0%      |
| `helpers.py` | 5+4+2=11      | 1        | 0           | 12          | **91.67%** (11/12) | **8.33%** (1/12) | 0%      |
| `docs.md`    | 8             | 0        | 3           | 11          | **72.73%** (8/11)  | 0%       | **27.27%** (3/11) |
| `README.md`  | 3             | 0        | 0           | 3           | **100.0%** | 0%       | 0%      |

Per-file "top author % of lines" (major-contributor-pct):

| File         | Top author % |
|--------------|--------------|
| `core.py`    | 80.0%        |
| `helpers.py` | 91.67%       |
| `docs.md`    | 72.73%       |
| `README.md`  | 100.0%       |

Major owners per file (≥5% threshold):

| File         | Major owners     |
|--------------|------------------|
| `core.py`    | {Alice, Bob}     |
| `helpers.py` | {Alice, Bob}     |
| `docs.md`    | {Alice, Carol}   |
| `README.md`  | {Alice}          |

### Truck factor (Avelino greedy removal)

Total files: 4. Threshold: truck factor = number of authors to remove until fewer than 50% of files retain ≥1 major owner (i.e., ≤ floor(0.5 * 4) = 2 files; <50% means strictly ≤1 file covered).

Author cumulative ownership-contribution (for ordering the greedy removal): Alice owns 20+11+8+3 = 42 added lines; Bob owns 5+1 = 6; Carol owns 3. Greedy order: Alice → Bob → Carol.

| Step            | Files retaining major owner                                                        | Coverage |
|-----------------|------------------------------------------------------------------------------------|----------|
| Baseline        | core.py {A,B}, helpers.py {A,B}, docs.md {A,C}, README.md {A}                      | 4/4 = 100% |
| Remove Alice    | core.py {B}, helpers.py {B}, docs.md {C}, README.md {}                             | 3/4 = 75%  |
| Remove Alice, Bob | core.py {}, helpers.py {}, docs.md {C}, README.md {}                             | 1/4 = 25%  |

After removing {Alice, Bob}, 1 of 4 files (25%) retains a major owner — strictly less than 50%.

**`truck_factor` = 2**

### Change entropy — Hassan (2009): H = -Σ p_i * log2(p_i), summed across all in-window commits

Per-commit entropy (`p_i` = (lines touched in file i) / (total lines touched in commit)):

| Commit | Files touched (lines)                     | Per-commit entropy (bits)      |
|--------|-------------------------------------------|---------------------------------|
| 1      | README.md (3)                             | 0.0                             |
| 2      | core.py (10)                              | 0.0                             |
| 3      | core.py (2), helpers.py (5)               | ≈ 0.86312  (H of 2/7, 5/7)      |
| 4      | core.py (5)                               | 0.0                             |
| 5      | core.py (2), helpers.py (5)               | ≈ 0.86312                       |
| 6      | core.py (3), helpers.py (2)               | ≈ 0.97095  (H of 3/5, 2/5)      |
| 7      | docs.md (8)                               | 0.0                             |
| 8      | core.py (7)                               | 0.0                             |
| 9      | docs.md (4)                               | 0.0                             |
| 10     | core.py (3), helpers.py (3)               | 1.0         (H of 1/2, 1/2)     |

**`change_entropy_90d` ≈ 3.6972 bits** (0 + 0 + 0.86312 + 0 + 0.86312 + 0.97095 + 0 + 0 + 0 + 1.0 = 3.69719).

Tests assert `pytest.approx(3.6972, abs=0.01)` — floating-point summation order in the production implementation may vary by up to a few ULP and the test should not depend on specific summation order. The test docstring documents the ± tolerance.

---

## Auxiliary Fixture Specs (smaller, scope-limited)

### `empty_repo/` — initial-commit-only baseline

- Single commit: Alice, `2026-02-15T10:00:00+00:00`, message `"initial commit"`, files: `README.md` with one line.
- Golden values: `churn_total_90d = 1`, `change_entropy_90d = 0.0`, `change_coupling = {}`, `truck_factor = 1`, `ownership = {"README.md": {"Alice Smith": 1.0}}`, files = {"README.md"}.

### `single_author_repo/` — truck factor = 1

- 5 commits, all by Alice Smith, over 5 days in 2026-03-01 → 2026-03-05.
- Files: `a.py` (3 commits) and `b.py` (2 commits); no commit touches both.
- Golden values: `truck_factor = 1`, `ownership["a.py"]["Alice Smith"] = 1.0`, `ownership["b.py"]["Alice Smith"] = 1.0`, `change_coupling = {}`.

### `coupling_repo/` — dense co-change

- 6 commits, all by Alice, touching `alpha.py` and `beta.py` together in every commit.
- Golden values: `change_coupling = {("alpha.py", "beta.py"): 6}`, which exceeds threshold ≥3.

---

## Shallow-Clone Fallback (no separate fixture — runtime clone)

The shallow-clone path does NOT require a pre-built fixture. The test builds it at runtime inside `tmp_path`:

```python
# Pseudocode sketch — the real test lives in test_git_collector.py
def test_shallow_clone_falls_back_to_commit_count(self, committed_fixture_path, tmp_path):
    shallow_path = tmp_path / "shallow_minimal_repo"
    subprocess.run(
        ["git", "clone", "--depth=1", "file://" + str(committed_fixture_path), str(shallow_path)],
        check=True,
    )
    result = GitCollector().collect(CollectionContext(repo_root=str(shallow_path), window_days=90, git_sha="..."))
    assert result.data["churn_source"] == "commit_count_fallback"
    # Shallow clone has exactly 1 commit after --depth=1 → commit-count churn is deterministic.
```

The implementer is responsible for detecting "numstat unavailable" (e.g., by checking whether `git log --numstat` on a known multi-commit SHA returns an empty numstat block, or via `git rev-parse --is-shallow-repository`). The test will verify the `churn_source` marker regardless of detection mechanism.

---

## Questions the implementer must answer (and their cost if unanswered)

1. **Where does `reference_time` come from?** See "Per-file age" section above — recommended env-var injection with fallback to `datetime.now(timezone.utc)`. Without a deterministic reference, per-file age cannot be asserted.

2. **How is `change_coupling` emitted?** The ADR and plan specify "top-N co-change pairs ≥ 3 commits." Suggested JSON shape: `{"change_coupling": {"pairs": [{"files": ["core.py", "helpers.py"], "count": 4}], "threshold": 3, "top_n": 10}}`. Tests will assert structural equivalence rather than exact dict ordering.

3. **How is `ownership` emitted?** Suggested shape: `{"ownership": {"core.py": {"major": [["Alice Smith", 0.8], ["Bob Jones", 0.2]], "minor": []}, ...}}`. Tests accept either (author-name → pct) dict form OR (major-list, minor-list) form — asserting on the top-author percentage per file rather than the full structure.

4. **Does `change_entropy_90d` include commits where only one file was touched?** Yes — these contribute 0.0 bits and are summed in. The test asserts `≈ 3.6972` total.

5. **Does `churn_total_90d` count `lines_added + lines_deleted` or just `lines_added`?** Per SYSTEMS_PLAN Hot-Spot dimension: `lines_added + lines_deleted`. The golden value 62 is computed that way. If the implementer deviates to "added only," the test fails and surfaces the drift.

If any of these choices conflict with the implementer's preferred shape, update this spec before building the fixture so the test and the production code agree.
