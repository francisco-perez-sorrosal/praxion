"""Doc-surface renderers for the Praxion dashboard.

Each renderer is a `render(surface, project_root)` callable that consumes a
manifest surface descriptor (per `skills/doc-management/references/
doc-manifest-schema.md`) and emits Streamlit widgets to display it.

Distinct from `streamlit_app/widgets/` (shared UI building blocks) — components
are *content renderers* keyed by `type` + `diataxis` quadrant.

Usage::

    from streamlit_app.components import dispatch
    dispatch(surface_descriptor, project_root)

The dispatcher selects the right renderer by:
  1. Explicit `surface["renderer"]` if present
  2. Default mapping based on `(type, diataxis)`
  3. Fallback to `default_markdown` for any markdown surface

Adding a new renderer: drop a module under `streamlit_app/components/<name>.py`
exposing `render(surface, project_root)` and register it in `_REGISTRY` below.
Update the reserved-renderer table in `skills/doc-management/references/
doc-manifest-schema.md` to keep the spec in sync.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, TYPE_CHECKING

if TYPE_CHECKING:  # avoid runtime import; renderers import lazily
    pass


# Renderer signature: Callable[[surface_dict, project_root_path], None]
# Renderers emit Streamlit widgets directly; they do not return values.
_RegisterT = Callable[[dict[str, Any], Path], None]


def _lazy(module_name: str, attr: str = "render") -> _RegisterT:
    """Defer import of the renderer module until first dispatch.

    Streamlit imports are heavy; we don't want every renderer loaded at
    package import time when only one or two will be used per page view.
    """

    def _wrapper(surface: dict[str, Any], project_root: Path) -> None:
        import importlib

        mod = importlib.import_module(f"streamlit_app.components.{module_name}")
        getattr(mod, attr)(surface, project_root)

    return _wrapper


# ---------------------------------------------------------------------------
# Renderer registry
# ---------------------------------------------------------------------------
# Keys match the reserved renderer names in the doc-manifest-schema reference.
# Values are lazy importers — calling them imports + invokes render().

_REGISTRY: dict[str, _RegisterT] = {
    # Tier 1 — shipped (this commit)
    "default_markdown": _lazy("default_markdown"),
    "tutorial_shell": _lazy("tutorial_shell"),
    "plan_view": _lazy("plan_view"),
    # Tier 2 — full Diátaxis quadrant set + adr_card shipped
    "adr_card": _lazy("adr_card"),
    "reference_shell": _lazy("reference_shell"),
    "explanation_shell": _lazy("explanation_shell"),
    "how_to_shell": _lazy("how_to_shell"),
    "verification_report": _lazy("verification_report"),
    "architecture_explorer": _lazy("default_markdown"),
    "traceability_matrix": _lazy("default_markdown"),
    "idea_grid": _lazy("default_markdown"),
    # Existing (predates HTML-B); not re-implemented here
    "metrics_view": _lazy("default_markdown"),  # use existing metrics page directly
}


def _default_renderer_name(surface: dict[str, Any]) -> str:
    """Pick a default renderer when `surface["renderer"]` is absent."""
    diataxis = (surface.get("diataxis") or "").strip().lower()
    type_ = (surface.get("type") or "markdown").strip().lower()

    if diataxis == "tutorial":
        return "tutorial_shell"
    if diataxis == "how-to":
        return "how_to_shell"
    if diataxis == "reference":
        return "reference_shell"
    if diataxis in ("explanation", "concepts"):
        return "explanation_shell"
    if type_ in ("yaml", "json"):
        return "default_markdown"  # JSON/YAML default — falls through to body display
    return "default_markdown"


def dispatch(surface: dict[str, Any], project_root: Path) -> None:
    """Render `surface` by dispatching to its registered renderer.

    Falls back to `default_markdown` for unregistered renderer names so the
    dashboard never errors on a missing/unexpected renderer.
    """
    name = surface.get("renderer") or _default_renderer_name(surface)
    renderer = _REGISTRY.get(name) or _REGISTRY["default_markdown"]
    renderer(surface, project_root)


def list_renderers() -> list[str]:
    """Return the registered renderer names (useful for tests + the
    manifest-schema cross-validation sentinel check)."""
    return sorted(_REGISTRY.keys())


__all__ = ["dispatch", "list_renderers"]
