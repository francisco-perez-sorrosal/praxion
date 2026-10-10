"""Driver that reads Praxion's architecture model the way the toolchain sees it.

The model source is the LikeC4 workspace under `docs/diagrams/architecture/src/`.
Rather than parsing the DSL itself, the driver asks the pinned `likec4` binary for
the computed model (`likec4 export json --skip-layout`) and exposes the facts the
scenarios rely on: elements (identity, name, kind, description or summary,
technology), relationships (source, target, label) and views (title, the elements
each one draws and the arrows between them).

The model as it stood before this change is a frozen reading of the base commit's
workspace by the same instrument, kept at `fixtures/architecture_model_before.json`
(elements by id, title and kind; relationships by source, target and title), so
"still recorded" compares two readings by one instrument and needs no git history:
a shallow CI clone judges it too. Regenerate the fixture from the base commit with
`git archive --format=tar 2d6ec71e docs/diagrams/architecture/src`, `export_model`
over the extracted workspace, and the snapshot's three fields.

Isolation: `likec4` runs with no inherited `CLAUDE*`/`PRAXION_*` variables and with
proxies pointing at a closed local port, so a reading never depends on the network.
"""

from __future__ import annotations

import functools
import json
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
DIAGRAM_ROOT = REPO_ROOT / "docs" / "diagrams" / "architecture"
MODEL_WORKSPACE = DIAGRAM_ROOT / "src"
RENDER_DIR = DIAGRAM_ROOT / "rendered"
BASE_COMMIT = "2d6ec71e"
BASE_FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "architecture_model_before.json"

_DEAD_PROXY = "http://127.0.0.1:9"
KIND_NOTATION_KEY = "kind_notation"  # where `_parse` leaves an element's kind notation in `raw`


@dataclass(frozen=True)
class Element:
    id: str
    title: str
    kind: str
    description: str | None
    summary: str | None
    technology: str | None
    raw: dict = field(compare=False, repr=False)

    @property
    def boundary(self) -> bool:
        """Drawn as a frame around other elements of the same view."""
        return bool(self.raw.get("children"))

    @property
    def responsibilities(self) -> tuple[str, ...]:
        """The responsibility texts the model records (description and/or summary)."""
        return tuple(text for text in (self.summary, self.description) if text)


@dataclass(frozen=True)
class Relationship:
    source: str
    target: str
    title: str | None


@dataclass(frozen=True)
class ViewEdge:
    source: str
    target: str
    label: str | None


@dataclass(frozen=True)
class View:
    id: str
    title: str | None
    nodes: tuple[Element, ...]
    edges: tuple[ViewEdge, ...]


@dataclass(frozen=True)
class Model:
    elements: dict[str, Element]
    relationships: tuple[Relationship, ...]
    views: dict[str, View]


def offline_env(extra_path: str | None = None) -> dict[str, str]:
    """Environment with no inherited agent variables and no reachable network proxy."""
    env = {
        k: v
        for k, v in os.environ.items()
        if not k.startswith(("CLAUDE", "PRAXION_", "GIT_"))
        and k.lower() not in {"http_proxy", "https_proxy", "all_proxy", "no_proxy"}
    }
    for name in (
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "ALL_PROXY",
        "http_proxy",
        "https_proxy",
        "all_proxy",
    ):
        env[name] = _DEAD_PROXY
    env["NO_PROXY"] = ""
    env["no_proxy"] = ""
    env["NODE_USE_ENV_PROXY"] = "1"
    env["npm_config_offline"] = "true"
    if extra_path:
        env["PATH"] = f"{extra_path}{os.pathsep}{env.get('PATH', '')}"
    return env


def require_likec4() -> str:
    binary = shutil.which("likec4")
    if binary is None:
        pytest.skip("likec4 is not installed; the model cannot be read without the toolchain")
    return binary


def _text(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value.strip() or None
    if isinstance(value, dict):
        for key in ("txt", "md", "text"):
            if isinstance(value.get(key), str) and value[key].strip():
                return value[key].strip()
    return None


def _element(raw: dict, fallback_id: str | None = None) -> Element:
    ident = raw.get("modelRef") or raw.get("id") or fallback_id
    return Element(
        id=str(ident),
        title=str(raw.get("title") or ""),
        kind=str(raw.get("kind") or ""),
        description=_text(raw.get("description")),
        summary=_text(raw.get("summary")),
        technology=_text(raw.get("technology")),
        raw=raw,
    )


def _endpoint(value: object) -> str:
    if isinstance(value, dict):
        return str(value.get("model") or value.get("id") or "")
    return str(value)


def _kind_notations(data: dict) -> dict[str, str]:
    """Each element kind's `notation` from the specification: the name legends show for it."""
    kinds = (data.get("specification") or {}).get("elements") or {}
    return {
        kind: notation
        for kind, spec in kinds.items()
        if isinstance(notation := (spec or {}).get("notation"), str) and notation.strip()
    }


def _parse(data: dict) -> Model:
    notations = _kind_notations(data)

    def with_notation(raw: dict) -> dict:
        return {**raw, KIND_NOTATION_KEY: notations.get(str(raw.get("kind")))}

    elements = {
        key: _element(with_notation(raw), key) for key, raw in (data.get("elements") or {}).items()
    }
    relationships = tuple(
        Relationship(
            _endpoint(raw.get("source")), _endpoint(raw.get("target")), _text(raw.get("title"))
        )
        for raw in (data.get("relations") or {}).values()
    )
    views: dict[str, View] = {}
    for view_id, raw in (data.get("views") or {}).items():
        nodes = []
        for node in raw.get("nodes") or []:
            ref = node.get("modelRef") or node.get("id")
            # A view node carries what the view shows; the model element fills gaps.
            base = elements.get(str(ref))
            merged = dict(base.raw) if base else {}
            merged.update({k: v for k, v in node.items() if v not in (None, "", {})})
            merged["modelRef"] = ref
            nodes.append(_element(with_notation(merged)))
        edges = tuple(
            ViewEdge(str(edge.get("source")), str(edge.get("target")), _text(edge.get("label")))
            for edge in raw.get("edges") or []
        )
        views[view_id] = View(view_id, _text(raw.get("title")), tuple(nodes), edges)
    return Model(elements, relationships, views)


def export_model(workspace: Path) -> Model:
    binary = require_likec4()
    with tempfile.TemporaryDirectory() as scratch:
        outfile = Path(scratch) / "model.json"
        result = subprocess.run(
            [binary, "export", "json", "--skip-layout", "-o", str(outfile), str(workspace)],
            capture_output=True,
            text=True,
            env=offline_env(),
            timeout=180,
        )
        detail = f"(exit {result.returncode}):\n{result.stdout[-1500:]}{result.stderr[-1500:]}"
        assert result.returncode == 0, f"likec4 could not read the model at {workspace} {detail}"
        assert outfile.is_file(), f"likec4 wrote no model reading for {workspace} {detail}"
        return _parse(json.loads(outfile.read_text(encoding="utf-8")))


@functools.cache
def current_model() -> Model:
    return export_model(MODEL_WORKSPACE)


@functools.cache
def base_model() -> Model:
    """The model as recorded at the base commit: the frozen reading in `BASE_FIXTURE`.

    The fixture carries what the identity scenarios compare (element ids, titles and
    kinds; relationship source, target and title) and names the commit it was read
    from, so the comparison never reaches into git history.
    """
    snapshot = json.loads(BASE_FIXTURE.read_text(encoding="utf-8"))
    assert snapshot["base_commit"] == BASE_COMMIT, (
        f"the frozen base model is from {snapshot['base_commit']}, not {BASE_COMMIT}"
    )
    elements = {
        e["id"]: Element(e["id"], e["title"], e["kind"], None, None, None, {})
        for e in snapshot["elements"]
    }
    relationships = tuple(
        Relationship(r["source"], r["target"], r["title"]) for r in snapshot["relationships"]
    )
    return Model(elements, relationships, {})


def category_of(element: Element) -> str:
    """The name of the category of the category vocabulary the element belongs to.

    The element's own `metadata.category` when it is a string, else its kind's
    `notation`. An element with neither, or whose `category` the toolchain merged
    into a list, has no category: the empty string, so a scenario reports a
    violation instead of the driver raising.
    """
    metadata = element.raw.get("metadata")
    declared = metadata.get("category") if isinstance(metadata, dict) else None
    if isinstance(declared, str):
        return declared.strip()
    if declared is not None:
        return ""
    return str(element.raw.get(KIND_NOTATION_KEY) or "").strip()
