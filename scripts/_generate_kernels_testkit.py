"""Shared builders for the kernel generator's tests (not a test module).

A synthetic repository (a contract rule, a shared rule, a condensed rule, the philosophy
template, three agents and a manifest over them) and the helpers that build it, run the
generator over it and read back what it wrote. The `repo` fixture lives here and each test
module binds it by name (`repo = kit.repo`), as the checker's tests do with `template`.
"""

from __future__ import annotations

import sys
from collections.abc import Mapping
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "hooks"))

import generate_kernels as gk  # noqa: E402
import kernel_model as km  # noqa: E402
import kernel_sources as ks  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent
CAP = km.MAX_STRING_CHARS
CONTRACT_RULE = gk.CONTRACT_SOURCE
SHARED_RULE = "rules/swe/shared.md"
CONDENSED_RULE = "rules/swe/condensed.md"
TEMPLATE = ks.USER_TEMPLATE
SECRET_TEXT = "Secret orchestrator text that no kernel may carry."
LONG_SOURCE = "## Condensed\n\nThe long source that a short form stands for.\n"
LINKS_TEXT = "**Praxion links.** Read a Praxion file from the plugin root."
RETURN_TEXT = "**Return contract.** End with one terminal marker."
USER_SENTENCE = "The user-level instruction file is not loaded for you."
TEMPLATE_TEXT = """## Template

User-level text.

## Principles

Framing sentence kept in the orchestrator's session.

### Wisdom

Wisdom text, as the template words it.

### Craft

Craft text, as the template words it.

## Closing

Text after the principles.
"""
CONTRACT_SOURCE_TEXT = """## Agent Behavioral Contract

Intro that points at the methodology.

- **Alpha** - first behavior.
- **Beta** - second behavior.

Self-test: did I follow the contract?

Tail about commit authorship.
"""
SHARED_SOURCE_TEXT = f"""## Shared

Shared text for every agent.

## Secret

{SECRET_TEXT}

## Duty

Duty text for the writer.
"""
AGENTS = {"writer": "", "reader": "", "failer": "The partial form says **Failed at** here.\n"}
TODAYS_PREAMBLE = (
    "[Praxion process active] Apply the behavioral contract: "
    "Surface Assumptions, Register Objection, Stay Surgical, Simplicity First. "
    "Use the tier selector; carry this contract into every delegation. "
    "Return a pointer, not a payload: a summary plus your .ai-work/ "
    "artifact path, not the full report."
)


def entry(source: str, heading: str, scope: str, **fields: object) -> dict:
    reason = "kept resident" if scope in ("orchestrator-only", "no-actor") else None
    return {"source": source, "heading": heading, "scope": scope, "reason": reason, **fields}


def core(source: str, heading: str, **fields: object) -> dict:
    return entry(source, heading, "core", **{"form": "verbatim", **fields})


def authored_row(text_id: str, module: str = "core", **fields: object) -> dict:
    path = f"claude/kernels/src/{text_id}.md"
    return {"id": text_id, "path": path, "module": module, "condenses": None, **fields}


def manifest_rows() -> dict:
    short_pin = ks.sha1_hex(LONG_SOURCE)
    condensed = authored_row(
        "short-form", condenses=f"{CONDENSED_RULE}#Condensed", pinned_sha=short_pin
    )
    return {
        "version": 1,
        "groups": {},
        "modules": {},
        "authored": [
            authored_row("praxion-links"),
            authored_row("return-contract"),
            authored_row("user-sentence"),
            condensed,
        ],
        "entries": [
            entry(CONTRACT_RULE, "Agent Behavioral Contract", "orchestrator-only", part="Intro"),
            core(CONTRACT_RULE, "Agent Behavioral Contract", part="- **Alpha**"),
            entry(CONTRACT_RULE, "Agent Behavioral Contract", "no-actor", part="Tail"),
            core(SHARED_RULE, "Shared"),
            entry(SHARED_RULE, "Secret", "orchestrator-only"),
            entry(SHARED_RULE, "Duty", "role", form="verbatim", agents=["writer"]),
            core(CONDENSED_RULE, "Condensed", form="condensed", text="short-form", pin=short_pin),
            entry(TEMPLATE, "Template", "no-actor"),
            entry(TEMPLATE, "Principles", "orchestrator-only"),
            entry(TEMPLATE, "Wisdom", "no-actor"),
            entry(TEMPLATE, "Craft", "no-actor"),
            entry(TEMPLATE, "Closing", "no-actor"),
        ],
    }


AUTHORED_TEXTS = {
    "praxion-links": LINKS_TEXT,
    "return-contract": RETURN_TEXT,
    "user-sentence": USER_SENTENCE,
    "short-form": "The short form.",
}


def write(root: Path, rel: str, text: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def build_repo(root: Path, *, manifest: Mapping | None = None) -> Path:
    write(root, CONTRACT_RULE, CONTRACT_SOURCE_TEXT)
    write(root, SHARED_RULE, SHARED_SOURCE_TEXT)
    write(root, CONDENSED_RULE, LONG_SOURCE)
    write(root, TEMPLATE, TEMPLATE_TEXT)
    for name, body in AGENTS.items():
        write(root, f"agents/{name}.md", f"---\nname: {name}\n---\n\n{body}")
    for text_id, text in AUTHORED_TEXTS.items():
        write(root, f"claude/kernels/src/{text_id}.md", text + "\n")
    write(root, km.MANIFEST_PATH, yaml.safe_dump(manifest or manifest_rows(), sort_keys=False))
    return root


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    return build_repo(tmp_path / "plugin")


def run(root: Path, *flags: str) -> int:
    return gk.main([*flags, "--repo-root", str(root)])


def kernel_texts(root: Path) -> dict[str, str]:
    return {p.name: p.read_text(encoding="utf-8") for p in (root / gk.KERNELS_DIR).glob("*.md")}


def disk_state(root: Path) -> dict[str, bytes]:
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob("*") if p.is_file()}
