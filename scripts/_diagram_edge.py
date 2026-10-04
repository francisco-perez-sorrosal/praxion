"""The edge of the diagram renderer: the subprocesses and files around the pure core.

Every function acts on what it is given: the tool versions required, the PATH the tools are
found on, the diagram root. The module states no pin of its own. A regeneration failure is
raised as `RegenerationError`, carrying the record the command prints.
"""

from __future__ import annotations

import html
import json
import os
import re
import shlex
import shutil
import subprocess
import tempfile
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from _diagram_core import Projection, RegenerationFailure, View, emit_d2, project
from _diagram_tokens import DEFAULT_TOKENS, Token, UsageError, load_style

SOURCE_DIR = "src"
RENDER_DIR = "rendered"
STYLE_FILE = "style.json"
MODEL_GLOB = "*.c4"
RENDER_SUFFIXES = (".svg", ".d2")

# d2 stamps the build it came from into every SVG ("0.7.1" from Homebrew, "v0.7.1" from the
# release tarball); a fixed value keeps a render the same whichever build drew it.
D2_STAMP = re.compile(rb'data-d2-version="[^"]*"')
SCRUBBED_D2_STAMP = b'data-d2-version="pinned"'
VERSION_NUMBER = re.compile(r"\bv?(\d+\.\d+\.\d+)\b")
MARKUP_TAG = re.compile(r"<[^>]*>")

STAGED_CHANGES = ("diff", "--cached", "--name-only", "--diff-filter=ACMRD", "-z")


class RegenerationError(Exception):
    """A regeneration failure; `failure` is the record the command prints."""

    def __init__(self, failure: RegenerationFailure) -> None:
        super().__init__(failure.what)
        self.failure = failure


@dataclass(frozen=True)
class Toolchain:
    """The two tools, the versions required of them and the PATH they are found on."""

    likec4: str
    d2: str
    path: str

    @property
    def required(self) -> dict[str, str]:
        return {"likec4": self.likec4, "d2": self.d2}

    @property
    def env(self) -> dict[str, str]:
        return {**os.environ, "PATH": self.path}

    def find(self, tool: str) -> str | None:
        return shutil.which(tool, path=self.path)


@dataclass(frozen=True)
class ToolProblem:
    """A tool that cannot be used: `found` is None when it is not on PATH, else its version."""

    tool: str
    required: str
    found: str | None


# --- the toolchain ---------------------------------------------------------------------------


def toolchain_problems(toolchain: Toolchain) -> list[ToolProblem]:
    """Each tool that is absent or off its required version; a tool that cannot say raises."""
    problems = []
    for tool, required in toolchain.required.items():
        if toolchain.find(tool) is None:
            problems.append(ToolProblem(tool, required, None))
            continue
        said = _run(toolchain, tool, ["--version"], tool)
        found = VERSION_NUMBER.search(said.stdout + said.stderr)
        version = found.group(1) if found else (said.stdout.strip() or "no version")
        if version != required:
            problems.append(ToolProblem(tool, required, version))
    return problems


def _command(toolchain: Toolchain, tool: str, args: Sequence[str]) -> list[str]:
    return [toolchain.find(tool) or tool, *args]


def _run(
    toolchain: Toolchain, tool: str, args: Sequence[str], target: str
) -> subprocess.CompletedProcess:
    """Run a tool from the toolchain's PATH; a start failure or non-zero exit is a failure."""
    argv = _command(toolchain, tool, args)
    try:
        done = subprocess.run(argv, capture_output=True, text=True, env=toolchain.env)
    except OSError as error:
        raise _toolchain_error(target, argv, f"could not be run: {error}", "") from error
    if done.returncode != 0:
        status = f"exited with status {done.returncode}"
        raise _toolchain_error(target, argv, status, done.stderr.strip() or done.stdout.strip())
    return done


def _toolchain_error(target: str, argv: Sequence[str], what: str, output: str) -> RegenerationError:
    tool = Path(argv[0]).name
    cause = "\n".join(part for part in (shlex.join(argv), output) if part)
    fix = f"run the command above by hand and fix what {tool} reports"
    return _failure("toolchain-error", target, f"{tool} {what}", cause, fix)


def _failure(kind: str, target: str, what: str, cause: str, fix: str) -> RegenerationError:
    return RegenerationError(RegenerationFailure(kind, target, what, cause, fix))


# --- reading the workspace -------------------------------------------------------------------


def has_model(root: Path) -> bool:
    return any((root / SOURCE_DIR).glob(MODEL_GLOB))


def discover_roots(base: Path) -> list[Path]:
    """Every `<base>/<name>/` that holds a model source, in name order."""
    if not base.is_dir():
        return []
    return [child for child in sorted(base.iterdir()) if has_model(child)]


def read_style(root: Path) -> tuple[Token, ...]:
    """The default drawings, then the categories the root's `style.json` adds."""
    style = root / STYLE_FILE
    if not style.is_file():
        return DEFAULT_TOKENS
    try:
        return load_style(style.read_text(encoding="utf-8"))
    except UsageError as error:
        raise UsageError(f"{style}: {error}") from error


def read_model(toolchain: Toolchain, root: Path) -> dict:
    """The model as `likec4 export json --skip-layout` reads it."""
    with tempfile.TemporaryDirectory(prefix="diagram-model-") as scratch:
        export = Path(scratch) / "model.json"
        args = ["export", "json", "--skip-layout", "-o", str(export), str(root / SOURCE_DIR)]
        _run(toolchain, "likec4", args, str(root))
        try:
            return json.loads(export.read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:
            argv = _command(toolchain, "likec4", args)
            raise _toolchain_error(
                str(root), argv, "wrote no readable model", str(error)
            ) from error


# --- building the renders --------------------------------------------------------------------


def build_root(
    toolchain: Toolchain, root: Path, tokens: Sequence[Token], built: Path
) -> Projection:
    """Read the root's model and render every view into `built`; touches nothing else."""
    projection = project(read_model(toolchain, root), tuple(tokens))
    require_drawable(projection, root)
    built.mkdir(parents=True, exist_ok=True)
    for view in projection.views:
        _render_view(toolchain, view, built)
    return projection


def require_drawable(projection: Projection, root: Path) -> None:
    """A model with no view showing an element, or a view showing none, cannot be rendered."""
    if not any(view.nodes for view in projection.views):
        what = "the model source yields no view that shows an element"
        cause = f"the toolchain read {len(projection.views)} view(s) and none includes an element"
        fix = "declare a view that includes elements, such as `view index { include * }`"
        raise _failure("no-views", str(root), what, cause, fix)
    for view in projection.views:
        if not view.nodes:
            what = f"view '{view.id}' includes no element"
            cause = "its include predicates match nothing, so there is nothing to draw"
            fix = f"add `include *` or an element to view '{view.id}', or delete the view"
            raise _failure("view-without-render", view.id, what, cause, fix)


def _render_view(toolchain: Toolchain, view: View, built: Path) -> None:
    source, svg = built / f"{view.id}.d2", built / f"{view.id}.svg"
    source.write_bytes(emit_d2(view).encode("utf-8"))
    _run(toolchain, "d2", [str(source), str(svg)], view.id)
    if not svg.is_file():
        what = f"d2 wrote no render for view '{view.id}'"
        cause = f"`d2 {source.name} {svg.name}` exited 0 and left no {svg.name}"
        fix = "run the same command by hand with the pinned d2"
        raise _failure("view-without-render", view.id, what, cause, fix)
    scrubbed = D2_STAMP.sub(SCRUBBED_D2_STAMP, svg.read_bytes())
    svg.write_bytes(scrubbed)
    _require_names(view, scrubbed)


def _require_names(view: View, svg: bytes) -> None:
    """The render must spell at least one of the view's element names."""
    text = html.unescape(MARKUP_TAG.sub("", svg.decode("utf-8", errors="replace")))
    drawn = "".join(text.split())
    if not any("".join(node.name.split()) in drawn for node in view.nodes):
        what = f"the render of view '{view.id}' shows no element's name"
        cause = f"none of its {len(view.nodes)} element names appears in {view.id}.svg"
        fix = "give the view's elements titles in the model, or report the renderer fault"
        raise _failure("render-without-names", view.id, what, cause, fix)


# --- publishing ------------------------------------------------------------------------------


def publish(built: Path, rendered: Path) -> None:
    """Make `rendered` hold exactly the built renders; every other file there is left alone."""
    rendered.mkdir(parents=True, exist_ok=True)
    fresh = {item.name for item in built.iterdir()}
    for name in fresh:
        shutil.copyfile(built / name, rendered / name)
    for stale in rendered.iterdir():
        if stale.is_file() and stale.suffix in RENDER_SUFFIXES and stale.name not in fresh:
            stale.unlink()


def staged_roots(roots: Sequence[Path]) -> list[Path]:
    """The roots with a staged `.c4` source change, found through git."""
    top = _toplevel()
    names = _git(list(STAGED_CHANGES), top).split("\0")
    staged = [(top / name).resolve() for name in names if name.endswith(".c4")]
    return [root for root in roots if _holds_any(root.resolve() / SOURCE_DIR, staged)]


def _holds_any(directory: Path, paths: Sequence[Path]) -> bool:
    return any(path.is_relative_to(directory) for path in paths)


def stage(rendered: Path) -> None:
    """`git add` the render directory from the work tree's top, so refreshed and pruned renders join the commit.

    Git exports `GIT_DIR` to hook processes, and a git call made from a subdirectory with
    `GIT_DIR` set and no `GIT_WORK_TREE` treats that subdirectory as the work tree. The
    pathspec is therefore given relative to the top and the call is made from the top.
    """
    top = _toplevel()
    target = rendered.resolve().relative_to(top)
    done = subprocess.run(
        ["git", "add", "--", str(target)],
        cwd=top,
        env=_git_env(top),
        capture_output=True,
        text=True,
    )
    if done.returncode != 0:
        raise _toolchain_error(
            str(rendered), ["git", "add", str(target)], "failed", done.stderr.strip()
        )


def _toplevel() -> Path:
    """The work tree's top, read from the process directory (a hook runs from the top)."""
    return Path(_git(["rev-parse", "--show-toplevel"], Path.cwd()).strip()).resolve()


def _git_env(work_tree: Path) -> dict[str, str]:
    """The process environment with the work tree made explicit when a hook exported `GIT_DIR`."""
    env = dict(os.environ)
    if "GIT_DIR" in env and "GIT_WORK_TREE" not in env:
        env["GIT_WORK_TREE"] = str(work_tree)
    return env


def _git(args: Sequence[str], cwd: Path) -> str:
    done = subprocess.run(
        ["git", *args], cwd=cwd, env=_git_env(cwd), capture_output=True, text=True
    )
    if done.returncode != 0:
        raise UsageError(f"git {' '.join(args)} failed in {cwd}: {done.stderr.strip()}")
    return done.stdout
