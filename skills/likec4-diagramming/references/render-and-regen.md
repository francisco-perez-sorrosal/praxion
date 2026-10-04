# Render and regeneration

The one statement of how a LikeC4 model becomes the committed SVG renders: the pinned toolchain, the single
command, what the hook and the CI gate do with it, and how to reproduce a run by hand. Back to
[`../SKILL.md`](../SKILL.md).

## Pinned toolchain

| Tool | Pinned version | Install |
|---|---|---|
| likec4 | 1.59.4 | `npm install -g likec4@1.59.4` |
| d2 | 0.7.1 | `curl -fsSL https://d2lang.com/install.sh \| sh -s -- --version v0.7.1 --method standalone` |

Both pins are exact. A different d2 can lay a diagram out differently and a different likec4 can export a
different model, so the renders are only byte-reproducible at these two versions. Every other file names the
tools without a version and links here. Use the standalone d2 build rather than a package-manager one: the
two builds stamp the version differently, and the command scrubs that stamp.

## The command

```
python3 scripts/regenerate_diagrams.py [ROOT ...] [--staged] [--check] [--json]
```

- **ROOT** is a diagram root: a directory `<dir>/<name>/` holding `src/*.c4` and `rendered/`. Praxion's is
  `docs/diagrams/architecture/`. With no ROOT the command takes every root under `docs/diagrams/`.
- **Default mode** renders in place: one `<view-id>.svg` and one `<view-id>.d2` per view in `rendered/`,
  deleting every other `.svg` and `.d2` there. The implicit `index` view counts as a view.
- **`--staged`** is the pre-commit mode: only roots with a staged `src/*.c4`; afterwards it runs
  `git add <root>/rendered/`. Review findings print as non-blocking `WARN` lines.
- **`--check`** writes nothing in the checkout: it renders into a temporary directory, byte-compares with the
  committed `rendered/`, and prints one finding per [review check](review-checks.md) and view.
- **`--json`** prints findings as JSON Lines instead of text lines.
- The command never reaches the network: icons are vendored files.

| Exit | Meaning |
|---|---|
| 0 | Success. Default and `--staged`: renders written. `--check`: no drift and no failed check. `--staged` also exits 0 when `likec4` or `d2` is not on PATH, after a warning |
| 1 | Regeneration failure in any mode; under `--check` also drift or at least one failed check |
| 2 | Usage error: unknown flag, a ROOT without `src/*.c4`, or `--staged` together with `--check` |
| 3 | Default and `--check` only: `likec4` or `d2` not on PATH, or a local version that differs from the pin |

A binary that is found but exits non-zero, even on `--version`, is a toolchain error (exit 1). `--staged`
with a version mismatch warns and proceeds.

**Regeneration failures** are the only four things that stop a run; each prints three lines on stderr:

```
[diagram-regen] FAIL <kind> <view-id|root>: <what happened>
[diagram-regen]   cause: <why>
[diagram-regen]   fix: <the exact action>
```

where kind is one of `toolchain-error`, `no-views`, `view-without-render`, `render-without-names`. Findings
go to stdout as `<CHECK-ID> <VIEW> <PASS|FAIL> <evidence>`; progress and the summary line go to stderr.

## Where it runs

- **Pre-commit hook `diagram-regen`.** A staged `.c4` runs the command with `--staged`. Toolchain absent: a
  warning and the commit proceeds. A regeneration failure aborts the commit and the three lines say why.
- **CI job `regenerate-and-diff`.** Installs the two pins, runs the command (non-zero fails the job), then
  fails when `git status --porcelain -- docs/diagrams/` is non-empty (this catches modified, deleted and
  untracked renders) and prints `git diff --exit-code -- docs/diagrams/`. The review checks run through
  `--check`, never inside this job, so the job passes whenever the renders match the model.
- **Managed projects** run a project-local copy of the command, installed by onboarding together with the
  workflow; the copy is not refreshed automatically.

## Reproduce by hand

1. Install the two pins above.
2. From the repository root, run `python3 scripts/regenerate_diagrams.py`.
3. Run `git status --porcelain -- docs/diagrams/`; anything it lists is what the CI gate would reject.
4. For the full verdict, run `python3 scripts/regenerate_diagrams.py --check`.

## Determinism

The same model at the same pins gives byte-identical files. What makes that hold: the version stamp d2
writes is scrubbed to a constant, line endings are LF, ids and label titles are emitted in sorted order,
icons are embedded as data URIs from vendored files, and the layout is computed by d2 with ELK, never by
LikeC4 (the model is exported with `--skip-layout`). So the LikeC4 UI and the committed renders lay out
differently, by design. The first CI run on a new machine class is the real cross-machine probe: local
byte-equality does not prove it.
