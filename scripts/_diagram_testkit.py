"""Stub `likec4` and `d2` programs and a model reading for the diagram command's tests.

Not a test module. `Toolchain` writes two shell programs into a directory the command is
told to find its tools on: they answer `--version`, copy a model reading to the path
`export json` is given, and write a small SVG that spells the D2 text they received (or
nothing, or an exit status), and they log every call, so the command's subprocess and file
work runs offline and in milliseconds.

The core tests (`test_regenerate_diagrams_tokens.py`, `_projection.py` and `_emission.py`) share
`small_export`, `node_of` and `edge_of` from the end of this module. The fixture
`tests/fixtures/diagram_regen/export_small.json` has the real keys of the
`likec4 export json --skip-layout` reading, cut down to eleven elements, ten relationships
and six views (an element view of each kind, a dynamic view, two views with a wrong number
of C4 type tags, and a view of elements with no usable category).

Public surface these tests assume (a disagreement is raised with the planner, not
worked around here):

    UsageError                      Exception: a refused `style.json`, the exit-2 class

    Token (frozen dataclass)        one drawing per (category, form):
        category: str               exact vocabulary name
        frame: bool                 True when the element is drawn as an enclosing frame
        drawing_class: str          "category_" + snake_case(category), plus "_frame" for frames
        shape: str                  a D2 shape: rectangle, package, document, cylinder, queue
        fill: str | None            "#RRGGBB"; None when the frame has no fill
        stroke: str                 "#RRGGBB"
        stroke_width: float
        dash: int                   0 is solid, a positive value is the dash length
        radius: int                 0 is square
        extra: str                  "none", "3d" or "double-border"
        icon: str                   "none" or "person"
        text_colour: str            "#RRGGBB"
    DEFAULT_TOKENS: tuple[Token, ...]    every (category, form) the command draws by default
    UNCATEGORISED: Token                 category "Uncategorised", drawn when no category resolves
    VOCABULARIES: dict[str, tuple[str, ...]]
                                    "praxion" and "kit": the category names, in legend order
    load_style(text, base=DEFAULT_TOKENS) -> tuple[Token, ...]
                                    parse `style.json`; base tokens first, then the additions;
                                    raises UsageError naming the entry that fails

    resolve_category(element, specification) -> str | None
                                    `element["metadata"]["category"]` when it is a string, else
                                    the `notation` of its kind in `specification["elements"]`;
                                    None when neither gives a string

    project(model, tokens=DEFAULT_TOKENS) -> Projection
        Projection.views: tuple[View, ...]          View.id, title, c4_type, nodes, edges
        Projection.findings: tuple[Finding, ...]    Finding.check, view, status, evidence,
                                                    measured, threshold
        Node: id, name, category, technology, responsibility, is_frame
        Edge: source, target, label, line ("acts-on" | "read-only" | "step"), step_no
        All of these are frozen dataclasses.

    wrap_text(text, width) -> list[str]
    node_label_lines(node) -> list[str]
    legend_entries(view) -> list[LegendEntry]       LegendEntry.label, drawing_class
    emit_d2(view) -> str                            pure: no clock, no file, no network
"""

from __future__ import annotations

import json
import textwrap
from pathlib import Path

from regenerate_diagrams import D2_VERSION, LIKEC4_VERSION

LIKEC4_PIN = LIKEC4_VERSION
D2_PIN = D2_VERSION
FAILURE_MESSAGE = "simulated toolchain failure"
VIEWS_KEPT = ("index", "structure")
LONG_NAME = "Research & Development Platform Services"

LIKEC4_STUB = """\
    #!/bin/sh
    echo "likec4 $*" >> "@log@"
    echo "$0 PATH=$PATH" >> "@log@.env"
    if [ "$1" = "--version" ]; then echo "@likec4_version@"; exit @likec4_version_status@; fi
    if [ @export_status@ -ne 0 ]; then echo "@message@" >&2; exit @export_status@; fi
    out=""
    while [ $# -gt 0 ]; do
      if [ "$1" = "-o" ]; then out="$2"; fi
      shift
    done
    /bin/cp "@model_file@" "$out"
    """

D2_STUB = """\
    #!/bin/sh
    echo "d2 $*" >> "@log@"
    echo "$0 PATH=$PATH" >> "@log@.env"
    if [ "$1" = "--version" ]; then echo "@d2_version@"; exit @d2_version_status@; fi
    if [ @render_status@ -ne 0 ]; then echo "@message@" >&2; exit @render_status@; fi
    case "@output@" in
      names)
        printf '<svg data-d2-version="v0.7.1"><text><tspan>' > "$2"
        /usr/bin/sed 's/\\\\n/<\\/tspan><tspan>/g; s/&/\\&amp;/g' "$1" >> "$2"
        printf '</tspan></text></svg>' >> "$2"
        ;;
      blank) printf '<svg data-d2-version="v0.7.1"><text>nothing</text></svg>' > "$2" ;;
      none) ;;
    esac
    """


def _node(element_id: str, title: str) -> dict:
    return {
        "id": element_id,
        "modelRef": element_id,
        "title": title,
        "children": [],
        "parent": None,
    }


def reading(*views: str) -> dict:
    """A small `export json` reading holding only the named views."""
    kinds = {"developer": "person", "praxion": "system", "claude_code": "external"}
    titles = {"developer": "Developer", "praxion": "Praxion", "claude_code": "Claude Code"}
    elements = {key: {"id": key, "kind": kind, "title": titles[key]} for key, kind in kinds.items()}
    elements["mystery"] = {"id": "mystery", "kind": "component", "title": "Mystery"}
    elements["long_name"] = {"id": "long_name", "kind": "system", "title": LONG_NAME}
    nodes = [_node(key, title) for key, title in titles.items()]
    edge = {"id": "e1", "source": "developer", "target": "praxion", "label": "develops"}
    available = {
        "index": {"tags": ["c4_system_context"], "nodes": nodes, "edges": [edge]},
        "structure": {"tags": ["c4_system_landscape"], "nodes": nodes[:2], "edges": [edge]},
        "unresolved": {"tags": ["c4_system_context"], "nodes": [_node("mystery", "Mystery")]},
        "wrapped": {"tags": ["c4_system_context"], "nodes": [_node("long_name", LONG_NAME)]},
    }
    return {
        "specification": {
            "elements": {
                "person": {"notation": "Person"},
                "system": {"notation": "System in scope"},
                "external": {"notation": "External system"},
                "component": {},
            }
        },
        "elements": elements,
        "relations": {},
        "views": {key: {"_type": "element", "id": key, **available[key]} for key in views},
    }


class Toolchain:
    """Stub `likec4` and `d2` programs in one directory, and a log of how they were called."""

    def __init__(self, directory: Path) -> None:
        self.directory = directory
        self.log = directory / "calls.log"
        self.model = reading(*VIEWS_KEPT)
        self.settings = {
            "likec4_version": LIKEC4_PIN,
            "likec4_version_status": 0,
            "export_status": 0,
            "d2_version": f"v{D2_PIN}",
            "d2_version_status": 0,
            "render_status": 0,
            "output": "names",
            "model_text": None,
        }
        self.write()

    def set(self, **settings) -> None:
        self.settings.update(settings)
        self.write()

    def use_model(self, model: dict) -> None:
        self.model = model
        self.write()

    def write(self) -> None:
        self.directory.mkdir(parents=True, exist_ok=True)
        model_file = self.directory / "model.json"
        model_file.write_text(
            self.settings["model_text"] or json.dumps(self.model), encoding="utf-8"
        )
        values = {
            **self.settings,
            "log": self.log,
            "message": FAILURE_MESSAGE,
            "model_file": model_file,
        }
        for name, template in (("likec4", LIKEC4_STUB), ("d2", D2_STUB)):
            text = textwrap.dedent(template)
            for key, value in values.items():
                text = text.replace(f"@{key}@", str(value))
            (self.directory / name).write_text(text, encoding="utf-8")
            (self.directory / name).chmod(0o755)

    @property
    def calls(self) -> list[str]:
        return self.log.read_text(encoding="utf-8").splitlines() if self.log.exists() else []

    @property
    def launches(self) -> set[str]:
        """Each program as it was started (`<argv0> PATH=<its PATH>`)."""
        return set(Path(f"{self.log}.env").read_text(encoding="utf-8").splitlines())

    @property
    def renders_drawn(self) -> list[str]:
        return [call for call in self.calls if call.startswith("d2 ") and ".d2" in call]


# --- the core tests' shared reading and finders ---------------------------------------------

FIXTURES = next(
    parent / "tests" / "fixtures"
    for parent in Path(__file__).resolve().parents
    if (parent / "tests" / "fixtures").is_dir()
)
"""The repository's `tests/fixtures/`, found by walking up: a runner that copies this directory
elsewhere (the mutation sensor's mutmut copy) still finds the fixtures through a parent."""
CORE_EXPORT = FIXTURES / "diagram_regen" / "export_small.json"


def small_export() -> dict:
    """The small `likec4 export json --skip-layout` reading the core tests project (see above)."""
    return json.loads(CORE_EXPORT.read_text(encoding="utf-8"))


def node_of(view, element_id):
    """The node `view` draws for `element_id`."""
    return next(node for node in view.nodes if node.id == element_id)


def edge_of(view, source, target):
    """The edge `view` draws from `source` to `target`."""
    return next(edge for edge in view.edges if (edge.source, edge.target) == (source, target))
