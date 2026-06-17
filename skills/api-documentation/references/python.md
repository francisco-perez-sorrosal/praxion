# Documenting a Python API Surface

How to document a Python project's two doc surfaces — the **library** (a package others `import`) and the **service** (a REST endpoint others call) — and cross-link them when a project is both. Back to [SKILL.md](../SKILL.md).

Python is the canonical two-surface case: the same codebase often ships an importable library *and* a FastAPI service *and* (e.g. [sandbook](https://github.com/) — a Python lib + `/v1` REST + MCP) an MCP server. Document each surface from its own source of truth and cross-link; never triplicate the same content. The two surfaces map directly onto core item 1 of the skill body.

Versions below are **defaults at time of writing, not pins** — verify the current release before adopting (`pip index versions <pkg>` / the tool's changelog).

## Surface 1 — Library docs (from docstrings + type signatures)

The library surface is generated from the code: docstrings carry prose, type hints carry signatures. Pick one extractor and one docstring style, then lint the style.

### Tool decision

| | mkdocstrings (MkDocs Material) | Sphinx (+ napoleon + autoapi) | pdoc |
|---|---|---|---|
| Markup | Markdown only | reStructuredText (Markdown via MyST) | Markdown |
| Extraction | `griffe` — static, no import | `autodoc` (imports the module) or `autoapi` (static) | static, no import |
| Docstring styles | Google / NumPy / reST (auto-detected) | Google / NumPy via `napoleon`; native reST | Google / NumPy / reST |
| Cross-project links | weaker | `intersphinx` (mature, broad) | none |
| Config burden | low (one `mkdocs.yml`) | higher (`conf.py` + extensions) | zero |
| Best when | prose-first docs, API ref is one section among tutorials/how-tos, Markdown-native team | reference-dominant libraries (NumPy/Django pattern), need intersphinx / typehints ecosystem | small / internal packages, one-command output, limited theming |

**Recommendation:** **mkdocstrings + Material** for new prose-first, Markdown-native projects (lowest friction, single markup). **Sphinx** when the project is reference-heavy or needs the intersphinx ecosystem. **pdoc** for small/internal packages that want zero config.

### Docstring convention — pick one and lint it

Choose **Google-style** (most readable, widely tooled) or **NumPy-style** (scientific ecosystem). Both are consumed by `napoleon` *and* mkdocstrings; native reST is more verbose — avoid for new work. Mixed styles degrade every generator, so enforce the choice:

```toml
# pyproject.toml — ruff D (pydocstyle) rules
[tool.ruff.lint]
extend-select = ["D"]
[tool.ruff.lint.pydocstyle]
convention = "google"   # or "numpy"
```

Document deprecations explicitly — Python has no universal docstring deprecation tag, so state the replacement and removal timeline in the docstring (and raise `DeprecationWarning` at runtime).

### Minimal setup (mkdocstrings)

```toml
# pyproject.toml (docs dependency group)
# mkdocs-material, mkdocstrings[python]
```

```yaml
# mkdocs.yml
plugins:
  - search
  - mkdocstrings
```

```markdown
<!-- docs/reference.md -->
::: mypackage.module
```

Then `mkdocs serve`. That single `:::` directive renders the whole module's API from its docstrings.

## Surface 2 — Service docs (from the OpenAPI spec FastAPI emits)

**FastAPI auto-generates OpenAPI 3.1** from Pydantic models + path operations, with zero extra config:

| Artifact | URL | What it is |
|---|---|---|
| Swagger UI | `/docs` | interactive try-it reference |
| ReDoc | `/redoc` | read-optimized reference |
| Raw spec | `/openapi.json` | the canonical contract — *and the agent-consumable surface* |

The raw `/openapi.json` *is* the source of truth and the agent surface (skill core item 2). Everything the agent reasons over lives in the spec, so enrich the decorators:

```python
@app.get(
    "/items/{item_id}",
    summary="Fetch one item",            # one-line summary
    response_model=Item,                 # output schema
    tags=["items"],                      # grouping
    deprecated=False,                    # first-class deprecation flag
)
async def read_item(item_id: int):
    """State preconditions and what the return means — agents read this every call."""
```

This is the gold standard for code-first REST in Python. Because the spec is *generated*, it must be committed + linted + drift-checked in CI to stay honest — the spec layer, the Spectral ruleset, and the lint→diff→contract-test gate are shared across all REST surfaces and live in [`rest-openapi.md`](rest-openapi.md). Do not re-author them here; FastAPI is simply the code-first emitter feeding that pipeline.

## Both surfaces — the sandbook multi-surface case

A Python project that is library + REST + MCP publishes all three and bridges them with links:

- **Library docs** → mkdocstrings / Sphinx, from docstrings.
- **Service docs** → FastAPI `/docs` + `/redoc`, from `/openapi.json` (spec details: [`rest-openapi.md`](rest-openapi.md)).
- **MCP docs** → generated from the live server's `tools/list` introspection ([`mcp-docs.md`](mcp-docs.md)).

**Cross-link, don't triplicate:** the MkDocs/Sphinx site links to the live `/openapi.json` (and embeds or links Swagger/ReDoc); the service docs link back to the library reference for the model classes; the MCP docs link to whichever surface backs each tool. The user navigates one surface; links bridge to the others.

## Sources

- [Sphinx](https://www.sphinx-doc.org/) — autodoc / napoleon / intersphinx
- [mkdocstrings](https://mkdocstrings.github.io/) + [Griffe](https://mkdocstrings.github.io/griffe/) — static extraction, docstring-style support
- [pydevtools: MkDocs vs Sphinx for a Python package](https://pydevtools.com/handbook/how-to/how-to-set-up-documentation-for-a-python-package/) — decision guidance
- [pdoc](https://pdoc.dev/) — zero-config Python API docs
- [FastAPI](https://fastapi.tiangolo.com/) — automatic OpenAPI 3.1 + Swagger / ReDoc
- [`rest-openapi.md`](rest-openapi.md) — the shared OpenAPI spec layer and CI gate
